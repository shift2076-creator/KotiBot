#!/usr/bin/env python3
"""Finalize SEC-006 after every replacement consumer has been verified.

The live preflight validates every target and writes only a private, ephemeral
handoff record under /run so cleanup can resolve the same data root after the
service stops. Cleanup removes only exact, validated credential sources.
Output contains counts only; secret values and client identifiers are never
displayed.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
import hmac
import json
import os
from pathlib import Path
import shlex
import stat
import subprocess
import sys
import tempfile
import time
from typing import Mapping


SOURCE_ROOT = Path(__file__).resolve().parents[1]

if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from server_core.credentials import (  # noqa: E402
    read_binary_credential_file,
)
from server_core.integration_credentials import (  # noqa: E402
    INTEGRATION_CREDENTIAL_NAME,
    LEGACY_INTEGRATION_CREDENTIAL_ENVIRONMENTS,
    integration_credential_document_from_environment,
)
from server_core.io import (  # noqa: E402
    JsonStateReadError,
    json_backup_path,
    read_json_object,
)
from server_core.paths import RuntimePaths  # noqa: E402
from tools.sec004_migrate_service_credentials import (  # noqa: E402
    FIREBASE_CREDENTIAL_NAME,
    TAPO_CREDENTIALS,
)
from tools.sec0045_verify_complete_credential_cutover import (  # noqa: E402
    DASHBOARD_LEGACY_ENVIRONMENTS,
    inspect_active_service,
    verify_complete_cutover,
    verify_service_credential_copies,
)
from tools.sec0062_inventory_device_key_ownership import (  # noqa: E402
    FIRST_PARTY_GROUPS,
    _pending_slot_state,
    _slot_state,
    flatten_server_clients,
    summarize_device_key_inventory,
)
from tools.sec00645_rotate_service_credentials import (  # noqa: E402
    DEFAULT_CANDIDATE_ROOT,
    DEFAULT_CREDENTIAL_DIRECTORY,
    DEFAULT_STATE_ROOT,
    GROUPS,
    RotationError,
    verify_active,
)
from tools.sec005_verify_output_sanitization import (  # noqa: E402
    verify_notification_history,
    verify_ordinary_state,
    verify_security_audit,
)


LEGACY_ENVIRONMENT_NAMES = frozenset({
    *(environment_name for _, environment_name in TAPO_CREDENTIALS),
    *LEGACY_INTEGRATION_CREDENTIAL_ENVIRONMENTS,
    *DASHBOARD_LEGACY_ENVIRONMENTS,
})
DEFAULT_TRANSFER_SOURCE = Path(
    "/home/shift2076/firebase-service-account.rotation.json"
)
DEFAULT_LEGACY_FIREBASE_SOURCE = (
    SOURCE_ROOT
    / "subsystems"
    / "notifications"
    / FIREBASE_CREDENTIAL_NAME
)
DEFAULT_LEGACY_SECURITY_SOURCE = (
    SOURCE_ROOT
    / "subsystems"
    / "security"
    / "security_state.json"
)
DEFAULT_LEGACY_SHARED_ENV_SOURCE = SOURCE_ROOT / ".env.shared"
DEFAULT_HANDOFF_FILE = Path("/run/kotibot-sec0066-preflight.json")
HANDOFF_MAX_AGE_SECONDS = 3600


class CleanupError(RuntimeError):
    """A value-free, operator-actionable cleanup failure."""


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Preflight, perform, or verify authorized SEC-006.6 retired "
            "credential cleanup without displaying values or identifiers."
        ),
    )
    parser.add_argument(
        "action",
        choices=("preflight", "cleanup", "verify"),
    )
    parser.add_argument("--service", default="kotibot")
    parser.add_argument(
        "--data-root",
        type=Path,
        help="optional explicit service data root",
    )
    parser.add_argument(
        "--credential-directory",
        type=Path,
        default=DEFAULT_CREDENTIAL_DIRECTORY,
    )
    parser.add_argument(
        "--candidate-root",
        type=Path,
        default=DEFAULT_CANDIDATE_ROOT,
    )
    parser.add_argument(
        "--state-root",
        type=Path,
        default=DEFAULT_STATE_ROOT,
    )
    parser.add_argument(
        "--legacy-firebase-source",
        type=Path,
        default=DEFAULT_LEGACY_FIREBASE_SOURCE,
    )
    parser.add_argument(
        "--legacy-security-source",
        type=Path,
        default=DEFAULT_LEGACY_SECURITY_SOURCE,
    )
    parser.add_argument(
        "--firebase-transfer-source",
        type=Path,
        default=DEFAULT_TRANSFER_SOURCE,
    )
    parser.add_argument(
        "--legacy-shared-environment-source",
        type=Path,
        default=DEFAULT_LEGACY_SHARED_ENV_SOURCE,
    )
    parser.add_argument(
        "--handoff-file",
        type=Path,
        default=DEFAULT_HANDOFF_FILE,
        help=argparse.SUPPRESS,
    )
    return parser


def _absolute(path: Path, label: str) -> Path:
    candidate = Path(path).expanduser()

    if not candidate.is_absolute():
        raise CleanupError(f"{label} must be absolute")

    return Path(os.path.abspath(candidate))


def _read_object(path: Path, label: str) -> dict:
    try:
        document = read_json_object(path)
    except JsonStateReadError as exc:
        raise CleanupError(
            f"{label} could not be read: reason={exc.reason}"
        ) from None

    if not isinstance(document, dict):
        raise CleanupError(f"{label} must contain an object")

    return document


def _private_file_metadata(
    path: Path,
    label: str,
    *,
    expected_uid: int | None = None,
) -> os.stat_result:
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        raise CleanupError(f"{label} is missing") from None
    except OSError as exc:
        raise CleanupError(f"{label} could not be inspected") from exc

    if stat.S_ISLNK(metadata.st_mode):
        raise CleanupError(f"{label} must not be a symbolic link")
    if not stat.S_ISREG(metadata.st_mode):
        raise CleanupError(f"{label} must be a regular file")
    if expected_uid is not None and metadata.st_uid != expected_uid:
        raise CleanupError(f"{label} has the wrong owner")
    if os.name != "nt" and stat.S_IMODE(metadata.st_mode) & 0o037:
        raise CleanupError(f"{label} permissions are not private")

    return metadata


def _private_payload(
    path: Path,
    label: str,
    *,
    expected_uid: int | None = None,
) -> bytes:
    _private_file_metadata(
        path,
        label,
        expected_uid=expected_uid,
    )
    try:
        return read_binary_credential_file(
            path,
            credential_name=label,
        )
    except RuntimeError as exc:
        raise CleanupError(str(exc)) from None


def _json_bytes(document: dict) -> bytes:
    return (
        json.dumps(document, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def _atomic_private_write(
    path: Path,
    payload: bytes,
    *,
    owner_uid: int,
    owner_gid: int,
) -> None:
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary = Path(temporary_name)

    try:
        os.fchmod(descriptor, 0o600)
        if os.name != "nt":
            os.fchown(descriptor, owner_uid, owner_gid)
        offset = 0
        while offset < len(payload):
            offset += os.write(descriptor, payload[offset:])
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        os.replace(temporary, path)
        directory_fd = os.open(
            path.parent,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
        )
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def build_clean_security_state(
    security_state: dict,
    server_state: dict,
    *,
    now: int | None = None,
) -> tuple[dict, dict[str, int]]:
    """Return a credential-minimal state or fail on an unsafe handoff."""
    now = int(time.time()) if now is None else int(now)
    clients, duplicate_ids = flatten_server_clients(server_state)

    if duplicate_ids:
        raise CleanupError("Durable client registry has duplicate identities")

    raw_keys = security_state.get("device_keys")
    raw_enrollments = security_state.get("device_enrollments")

    if not isinstance(raw_keys, dict):
        raise CleanupError("Protected device-key state is malformed")
    if not isinstance(raw_enrollments, dict):
        raise CleanupError("Protected enrollment state is malformed")

    cleaned = deepcopy(security_state)
    cleaned_keys: dict[str, dict] = {}
    retained_key_ids: dict[str, str] = {}
    removed_records = 0
    removed_previous = 0
    removed_pending = 0

    for device_id, record in raw_keys.items():
        client = clients.get(str(device_id))
        first_party = bool(
            client
            and client.get("provisioned")
            and client.get("group") in FIRST_PARTY_GROUPS
        )

        if not first_party:
            removed_records += 1
            continue

        if not isinstance(record, dict):
            raise CleanupError("First-party device-key record is malformed")

        current = record.get("current")
        if _slot_state(current, now=now, previous=False) != "active":
            raise CleanupError("First-party client lacks an active key")
        if not record.get("handoff_verified_at"):
            raise CleanupError("First-party key handoff is not verified")

        previous_state = _slot_state(
            record.get("previous"),
            now=now,
            previous=True,
        )
        if previous_state == "grace-active":
            raise CleanupError("A previous device key is still in grace")
        if previous_state == "malformed":
            raise CleanupError("A previous device-key slot is malformed")

        pending_state = _pending_slot_state(record.get("pending"))
        if pending_state == "staged":
            raise CleanupError("A staged device-key handoff is still pending")
        if pending_state == "malformed":
            raise CleanupError("A pending device-key slot is malformed")

        clean_record = deepcopy(record)
        if previous_state == "retired":
            clean_record.pop("previous", None)
            removed_previous += 1
        if pending_state == "retired":
            clean_record.pop("pending", None)
            removed_pending += 1

        cleaned_keys[str(device_id)] = clean_record
        retained_key_ids[str(device_id)] = str(
            current.get("key_id") or ""
        )

    for device_id, client in clients.items():
        if (
            client.get("provisioned")
            and client.get("group") in FIRST_PARTY_GROUPS
            and device_id not in cleaned_keys
        ):
            raise CleanupError("A provisioned first-party client lacks a key")

    for enrollment in raw_enrollments.values():
        if not isinstance(enrollment, dict):
            raise CleanupError("Protected enrollment record is malformed")
        try:
            expires_at = int(enrollment.get("expires_at") or 0)
        except (TypeError, ValueError):
            raise CleanupError("Protected enrollment record is malformed")
        if expires_at >= now:
            raise CleanupError("A device enrollment is still pending")

    sessions = cleaned.get("dashboard_sessions")
    removed_sessions = 0
    if isinstance(sessions, dict):
        for session_key, session in list(sessions.items()):
            if not isinstance(session, dict):
                continue
            principal_type = str(
                session.get("principal_type") or "dashboard_user"
            ).strip()
            if principal_type != "key_client":
                continue
            device_id = str(session.get("device_id") or "").strip()
            key_id = str(session.get("key_id") or "").strip()
            retained_key_id = retained_key_ids.get(device_id, "")
            if (
                not retained_key_id
                or not key_id
                or not hmac.compare_digest(retained_key_id, key_id)
            ):
                sessions.pop(session_key, None)
                removed_sessions += 1
    elif sessions is not None:
        raise CleanupError("Protected dashboard session state is malformed")

    for recovery_name in (
        "dashboard_session_rotation_recovery",
        "dashboard_user_password_rotation_recovery",
    ):
        if recovery_name in cleaned:
            raise CleanupError("Dashboard credential rollback is retained")

    cleaned["device_keys"] = cleaned_keys
    cleaned["device_enrollments"] = {}
    return cleaned, {
        "retained_device_keys": len(cleaned_keys),
        "removed_device_key_records": removed_records,
        "removed_previous_slots": removed_previous,
        "removed_pending_slots": removed_pending,
        "removed_enrollments": len(raw_enrollments),
        "removed_key_client_sessions": removed_sessions,
    }


def _systemd_properties(service_name: str) -> dict[str, str]:
    safe = str(service_name or "").strip()
    if not safe or any(
        character
        not in (
            "abcdefghijklmnopqrstuvwxyz"
            "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
            "0123456789@_.-"
        )
        for character in safe
    ):
        raise CleanupError("Systemd service name is invalid")

    try:
        result = subprocess.run(
            [
                "systemctl",
                "show",
                safe,
                "--property=ActiveState",
                "--property=FragmentPath",
                "--property=DropInPaths",
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise CleanupError("Could not inspect the systemd service") from exc

    properties: dict[str, str] = {}
    for line in result.stdout.splitlines():
        name, separator, value = line.partition("=")
        if separator:
            properties[name] = value.strip()
    return properties


def systemd_definition_paths(
    properties: Mapping[str, str],
) -> tuple[Path, ...]:
    raw_paths = []
    fragment = str(properties.get("FragmentPath") or "").strip()
    if fragment:
        raw_paths.append(fragment)

    try:
        raw_paths.extend(
            shlex.split(
                str(properties.get("DropInPaths") or ""),
                comments=False,
                posix=True,
            )
        )
    except ValueError:
        raise CleanupError("Systemd drop-in path list is malformed") from None

    paths: list[Path] = []
    for raw_path in raw_paths:
        path = Path(raw_path)
        if not path.is_absolute():
            raise CleanupError("Systemd configuration path is not absolute")
        if path not in paths:
            paths.append(path)
    return tuple(paths)


def sanitize_systemd_environment_text(
    source: str,
) -> tuple[str, frozenset[str]]:
    """Remove only target-only Environment= lines; reject mixed lines."""
    output: list[str] = []
    removed: set[str] = set()

    for line in source.splitlines(keepends=True):
        stripped = line.lstrip()
        if not stripped.startswith("Environment="):
            output.append(line)
            continue

        raw_value = stripped[len("Environment="):].rstrip("\r\n")
        try:
            assignments = shlex.split(
                raw_value,
                comments=False,
                posix=True,
            )
        except ValueError:
            raise CleanupError("Systemd Environment line is malformed") from None

        target_names = {
            assignment.partition("=")[0]
            for assignment in assignments
            if assignment.partition("=")[1]
            and assignment.partition("=")[0]
            in LEGACY_ENVIRONMENT_NAMES
        }

        if not target_names:
            output.append(line)
            continue

        non_target = [
            assignment
            for assignment in assignments
            if assignment.partition("=")[0] not in target_names
        ]
        if non_target:
            raise CleanupError(
                "Credential and non-credential assignments share one "
                "systemd Environment line"
            )

        removed.update(target_names)

    return "".join(output), frozenset(removed)


def _environment_file_declarations(
    source: str,
) -> tuple[tuple[Path, bool], ...]:
    declarations: list[tuple[Path, bool]] = []

    for line in source.splitlines():
        stripped = line.lstrip()
        if not stripped.startswith("EnvironmentFile="):
            continue

        raw_value = stripped[len("EnvironmentFile="):].strip()
        try:
            values = shlex.split(raw_value, comments=False, posix=True)
        except ValueError:
            raise CleanupError(
                "Systemd EnvironmentFile declaration is malformed"
            ) from None

        for value in values:
            optional = value.startswith("-")
            raw_path = value[1:] if optional else value
            if not raw_path:
                raise CleanupError(
                    "Systemd EnvironmentFile declaration is malformed"
                )
            if any(marker in raw_path for marker in ("%", "*", "?", "[")):
                raise CleanupError(
                    "Systemd EnvironmentFile path requires explicit review"
                )
            path = Path(raw_path)
            if not path.is_absolute():
                raise CleanupError(
                    "Systemd EnvironmentFile path is not absolute"
                )
            item = (Path(os.path.abspath(path)), optional)
            if item not in declarations:
                declarations.append(item)

    return tuple(declarations)


def sanitize_environment_file_text(
    source: str,
) -> tuple[str, frozenset[str]]:
    """Remove exact legacy assignment lines from a systemd env file."""
    output: list[str] = []
    removed: set[str] = set()

    for line in source.splitlines(keepends=True):
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            output.append(line)
            continue

        if line.rstrip("\r\n").endswith("\\"):
            raise CleanupError(
                "Environment file continuation requires explicit review"
            )

        name = stripped.partition("=")[0].strip()
        if name not in LEGACY_ENVIRONMENT_NAMES:
            output.append(line)
            continue

        removed.add(name)

    return "".join(output), frozenset(removed)


def build_systemd_cleanup(
    paths: tuple[Path, ...],
) -> tuple[
    dict[Path, str],
    frozenset[str],
    frozenset[Path],
]:
    replacements: dict[Path, str] = {}
    removed: set[str] = set()
    environment_files: list[tuple[Path, bool]] = []

    for path in paths:
        try:
            metadata = path.lstat()
        except OSError as exc:
            raise CleanupError(
                "Systemd configuration file could not be inspected"
            ) from exc
        if stat.S_ISLNK(metadata.st_mode):
            raise CleanupError(
                "Systemd configuration file must not be a symbolic link"
            )
        if not stat.S_ISREG(metadata.st_mode):
            raise CleanupError(
                "Systemd configuration path must be a regular file"
            )
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise CleanupError(
                "Systemd configuration file could not be read"
            ) from exc

        for declaration in _environment_file_declarations(source):
            if declaration not in environment_files:
                environment_files.append(declaration)

        replacement, names = sanitize_systemd_environment_text(source)
        if names:
            replacements[path] = replacement
            removed.update(names)

    changed_environment_files: set[Path] = set()
    for path, optional in environment_files:
        try:
            metadata = path.lstat()
        except FileNotFoundError:
            if optional:
                continue
            raise CleanupError("Systemd EnvironmentFile is missing") from None
        except OSError as exc:
            raise CleanupError(
                "Systemd EnvironmentFile could not be inspected"
            ) from exc
        if stat.S_ISLNK(metadata.st_mode):
            raise CleanupError(
                "Systemd EnvironmentFile must not be a symbolic link"
            )
        if not stat.S_ISREG(metadata.st_mode):
            raise CleanupError(
                "Systemd EnvironmentFile must be a regular file"
            )
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise CleanupError(
                "Systemd EnvironmentFile could not be read"
            ) from exc

        replacement, names = sanitize_environment_file_text(source)
        if names:
            replacements[path] = replacement
            changed_environment_files.add(path)
            removed.update(names)

    return (
        replacements,
        frozenset(removed),
        frozenset(changed_environment_files),
    )


def _atomic_systemd_write(path: Path, source: str) -> None:
    metadata = path.stat()
    payload = source.encode("utf-8")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary = Path(temporary_name)

    try:
        os.fchmod(descriptor, stat.S_IMODE(metadata.st_mode))
        if os.name != "nt":
            os.fchown(descriptor, metadata.st_uid, metadata.st_gid)
        offset = 0
        while offset < len(payload):
            offset += os.write(descriptor, payload[offset:])
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        os.replace(temporary, path)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _validate_rotation_groups(
    credential_directory: Path,
    candidate_root: Path,
    state_root: Path,
    *,
    expected_uid: int,
) -> None:
    for group in GROUPS.values():
        try:
            verify_active(
                group,
                credential_directory,
                candidate_root / group.name,
                state_root / group.name,
                expected_uid=expected_uid,
            )
        except RotationError as exc:
            raise CleanupError(
                f"Rotation group {group.name} is not finalizable: {exc}"
            ) from None


def _validate_legacy_payloads(
    credential_directory: Path,
    state_root: Path,
    legacy_firebase_source: Path,
    legacy_security_source: Path,
    transfer_source: Path,
) -> None:
    previous_firebase = _private_payload(
        state_root
        / "firebase"
        / "previous"
        / FIREBASE_CREDENTIAL_NAME,
        "retired Firebase credential",
        expected_uid=0,
    )
    legacy_firebase = _private_payload(
        legacy_firebase_source,
        "legacy Firebase source",
    )
    if not hmac.compare_digest(previous_firebase, legacy_firebase):
        raise CleanupError(
            "Legacy Firebase source does not match the retired credential"
        )

    active_firebase = _private_payload(
        credential_directory / FIREBASE_CREDENTIAL_NAME,
        "active Firebase credential",
        expected_uid=0,
    )
    transferred = _private_payload(
        transfer_source,
        "transferred Firebase source",
    )
    if not hmac.compare_digest(active_firebase, transferred):
        raise CleanupError(
            "Transferred Firebase source does not match the active credential"
        )

    _private_file_metadata(
        legacy_security_source,
        "legacy security source",
    )
    _read_object(legacy_security_source, "legacy security source")


def _validate_tapo_environment_values(
    environment: Mapping[str, str],
    credential_directory: Path,
    state_root: Path,
) -> None:
    for group_name in ("tapo-account", "tapo-camera"):
        group = GROUPS[group_name]
        for credential_name in group.credential_names:
            environment_name = dict(TAPO_CREDENTIALS)[credential_name]
            value = str(environment.get(environment_name) or "")
            if not value:
                continue
            encoded = value.encode("utf-8")
            active = _private_payload(
                credential_directory / credential_name,
                f"active {credential_name}",
                expected_uid=0,
            ).rstrip(b"\n")
            previous = _private_payload(
                state_root / group_name / "previous" / credential_name,
                f"retired {credential_name}",
                expected_uid=0,
            ).rstrip(b"\n")
            if not (
                hmac.compare_digest(encoded, active)
                or hmac.compare_digest(encoded, previous)
            ):
                raise CleanupError(
                    f"Legacy environment does not match a validated "
                    f"credential: {environment_name}"
                )

    integration_environment = {
        name: str(environment.get(name) or "")
        for name in LEGACY_INTEGRATION_CREDENTIAL_ENVIRONMENTS
        if str(environment.get(name) or "")
    }
    if not integration_environment:
        return

    try:
        protected = json.loads(
            _private_payload(
                credential_directory / INTEGRATION_CREDENTIAL_NAME,
                "active integration credential",
                expected_uid=0,
            ).decode("utf-8")
        )
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise CleanupError(
            "Active integration credential is malformed"
        ) from None
    legacy = integration_credential_document_from_environment(
        integration_environment
    )
    if legacy != protected:
        raise CleanupError(
            "Legacy integration environment does not match protected storage"
        )


def _validate_exact_directory(path: Path, expected_names: frozenset[str]) -> None:
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise CleanupError("Retired credential directory is missing") from exc
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        raise CleanupError("Retired credential path is not a safe directory")
    actual = frozenset(child.name for child in path.iterdir())
    if actual != expected_names:
        raise CleanupError("Retired credential directory has unexpected content")


def _remove_rotation_group(
    group_name: str,
    candidate_root: Path,
    state_root: Path,
) -> None:
    candidate, state, previous, names = _rotation_group_paths(
        group_name,
        candidate_root,
        state_root,
    )

    for name in names:
        (candidate / name).unlink()
        (previous / name).unlink()
    candidate.rmdir()
    previous.rmdir()
    (state / "manifest.json").unlink()
    state.rmdir()


def _rotation_group_paths(
    group_name: str,
    candidate_root: Path,
    state_root: Path,
) -> tuple[Path, Path, Path, frozenset[str]]:
    group = GROUPS[group_name]
    names = frozenset(group.credential_names)
    candidate = candidate_root / group_name
    state = state_root / group_name
    previous = state / "previous"

    _validate_exact_directory(candidate, names)
    _validate_exact_directory(previous, names)
    _validate_exact_directory(state, frozenset({"manifest.json", "previous"}))
    return candidate, state, previous, names


def _validate_optional_private_file(path: Path, label: str) -> None:
    if path.exists() or path.is_symlink():
        _private_file_metadata(path, label)


def _unlink_exact_file(path: Path, label: str) -> None:
    _private_file_metadata(path, label)
    path.unlink()


def _inspect_optional_legacy_file(path: Path, label: str) -> bool:
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise CleanupError(f"{label} could not be inspected") from exc
    if stat.S_ISLNK(metadata.st_mode):
        raise CleanupError(f"{label} must not be a symbolic link")
    if not stat.S_ISREG(metadata.st_mode):
        raise CleanupError(f"{label} must be a regular file")
    return True


def _validate_all_deletion_targets(args) -> bool:
    _validate_optional_private_file(
        json_backup_path(args.legacy_firebase_source),
        "legacy Firebase recovery source",
    )
    _validate_optional_private_file(
        json_backup_path(args.legacy_security_source),
        "legacy security recovery source",
    )
    shared_environment_present = _inspect_optional_legacy_file(
        args.legacy_shared_environment_source,
        "legacy shared environment source",
    )
    for group_name in GROUPS:
        _rotation_group_paths(
            group_name,
            args.candidate_root,
            args.state_root,
        )
    return shared_environment_present


def _write_preflight_handoff(
    args,
    data_root: Path,
    *,
    owner_uid: int = 0,
    owner_gid: int = 0,
) -> None:
    document = {
        "schema": 1,
        "service": args.service,
        "source_root": str(SOURCE_ROOT),
        "data_root": str(_absolute(data_root, "Service data root")),
        "created_at": int(time.time()),
    }
    _atomic_private_write(
        args.handoff_file,
        _json_bytes(document),
        owner_uid=owner_uid,
        owner_gid=owner_gid,
    )


def _data_root_from_handoff(
    args,
    *,
    expected_uid: int = 0,
) -> Path:
    _private_file_metadata(
        args.handoff_file,
        "SEC-006.6 preflight handoff",
        expected_uid=expected_uid,
    )
    document = _read_object(
        args.handoff_file,
        "SEC-006.6 preflight handoff",
    )
    try:
        created_at = int(document.get("created_at") or 0)
    except (TypeError, ValueError):
        raise CleanupError("SEC-006.6 preflight handoff is malformed")
    if (
        document.get("schema") != 1
        or document.get("service") != args.service
        or document.get("source_root") != str(SOURCE_ROOT)
        or created_at < int(time.time()) - HANDOFF_MAX_AGE_SECONDS
        or created_at > int(time.time()) + 60
    ):
        raise CleanupError("SEC-006.6 preflight handoff is invalid or stale")
    return _absolute(
        Path(str(document.get("data_root") or "")),
        "Service data root",
    )


def _require_service_state(service_name: str, expected: str) -> dict[str, str]:
    properties = _systemd_properties(service_name)
    active = properties.get("ActiveState")
    if active != expected:
        raise CleanupError(
            f"KotiBot service must be {expected} for this operation"
        )
    return properties


def run_preflight(args) -> dict[str, int]:
    snapshot = inspect_active_service(
        args.service,
        data_root_override=args.data_root,
    )
    paths = RuntimePaths(
        source_root=SOURCE_ROOT,
        data_root=snapshot.data_root,
    ).validate()
    verify_service_credential_copies(
        args.credential_directory,
        snapshot.runtime_credential_directory,
        expected_source_owner=(0, 0),
        expected_runtime_owners=frozenset({
            (0, 0),
            (
                snapshot.process_user_id,
                snapshot.process_group_id,
            ),
        }),
    )
    _validate_rotation_groups(
        args.credential_directory,
        args.candidate_root,
        args.state_root,
        expected_uid=0,
    )
    _validate_legacy_payloads(
        args.credential_directory,
        args.state_root,
        args.legacy_firebase_source,
        args.legacy_security_source,
        args.firebase_transfer_source,
    )
    _validate_tapo_environment_values(
        snapshot.environment,
        args.credential_directory,
        args.state_root,
    )

    security_state = _read_object(
        paths.security_state_file,
        "protected security state",
    )
    server_state = _read_object(
        paths.server_state_file,
        "durable server state",
    )
    _, counts = build_clean_security_state(
        security_state,
        server_state,
    )

    properties = _systemd_properties(args.service)
    replacements, definition_names, environment_files = build_systemd_cleanup(
        systemd_definition_paths(properties)
    )
    active_names = frozenset(
        name
        for name in LEGACY_ENVIRONMENT_NAMES
        if str(snapshot.environment.get(name) or "")
    )
    if not active_names.issubset(definition_names):
        raise CleanupError(
            "An active legacy credential environment source was not mapped"
        )

    shared_environment_present = _validate_all_deletion_targets(args)
    _write_preflight_handoff(args, snapshot.data_root)

    return {
        **counts,
        "rotation_groups": len(GROUPS),
        "legacy_source_files": 3 + int(shared_environment_present),
        "systemd_files": len(replacements) - len(environment_files),
        "environment_files": len(environment_files),
        "systemd_environment_names": len(definition_names),
    }


def run_cleanup(args) -> dict[str, int]:
    properties = _require_service_state(args.service, "inactive")
    data_root = (
        _absolute(args.data_root, "Service data root")
        if args.data_root is not None
        else _data_root_from_handoff(args)
    )
    paths = RuntimePaths(
        source_root=SOURCE_ROOT,
        data_root=data_root,
    ).validate()

    _validate_rotation_groups(
        args.credential_directory,
        args.candidate_root,
        args.state_root,
        expected_uid=0,
    )
    _validate_legacy_payloads(
        args.credential_directory,
        args.state_root,
        args.legacy_firebase_source,
        args.legacy_security_source,
        args.firebase_transfer_source,
    )

    security_file = paths.security_state_file
    security_metadata = _private_file_metadata(
        security_file,
        "protected security state",
    )
    _private_file_metadata(
        json_backup_path(security_file),
        "protected security recovery state",
    )
    security_state = _read_object(
        security_file,
        "protected security state",
    )
    server_state = _read_object(
        paths.server_state_file,
        "durable server state",
    )
    cleaned_state, counts = build_clean_security_state(
        security_state,
        server_state,
    )

    replacements, definition_names, environment_files = build_systemd_cleanup(
        systemd_definition_paths(properties)
    )
    shared_environment_present = _validate_all_deletion_targets(args)

    # All destructive targets have been validated. Apply bounded replacements
    # before removing their obsolete sources.
    args.destructive_cleanup_started = True
    for path, replacement in replacements.items():
        _atomic_systemd_write(path, replacement)

    encoded_state = _json_bytes(cleaned_state)
    for path in (security_file, json_backup_path(security_file)):
        _atomic_private_write(
            path,
            encoded_state,
            owner_uid=security_metadata.st_uid,
            owner_gid=security_metadata.st_gid,
        )

    _unlink_exact_file(
        args.legacy_firebase_source,
        "legacy Firebase source",
    )
    legacy_firebase_backup = json_backup_path(
        args.legacy_firebase_source
    )
    if legacy_firebase_backup.exists() or legacy_firebase_backup.is_symlink():
        _unlink_exact_file(
            legacy_firebase_backup,
            "legacy Firebase recovery source",
        )

    _unlink_exact_file(
        args.legacy_security_source,
        "legacy security source",
    )
    legacy_security_backup = json_backup_path(
        args.legacy_security_source
    )
    if legacy_security_backup.exists() or legacy_security_backup.is_symlink():
        _unlink_exact_file(
            legacy_security_backup,
            "legacy security recovery source",
        )

    _unlink_exact_file(
        args.firebase_transfer_source,
        "transferred Firebase source",
    )

    if shared_environment_present:
        args.legacy_shared_environment_source.unlink()

    for group_name in GROUPS:
        _remove_rotation_group(
            group_name,
            args.candidate_root,
            args.state_root,
        )

    if args.handoff_file.exists() or args.handoff_file.is_symlink():
        _unlink_exact_file(
            args.handoff_file,
            "SEC-006.6 preflight handoff",
        )

    return {
        **counts,
        "rotation_groups": len(GROUPS),
        "legacy_source_files": 3 + int(shared_environment_present),
        "systemd_files": len(replacements) - len(environment_files),
        "environment_files": len(environment_files),
        "systemd_environment_names": len(definition_names),
    }


def _require_absent(path: Path, label: str) -> None:
    try:
        path.lstat()
    except FileNotFoundError:
        return
    except OSError as exc:
        raise CleanupError(f"{label} could not be inspected") from exc
    raise CleanupError(f"{label} is still present")


def run_verify(args) -> dict[str, int]:
    snapshot = inspect_active_service(
        args.service,
        data_root_override=args.data_root,
    )
    paths = RuntimePaths(
        source_root=SOURCE_ROOT,
        data_root=snapshot.data_root,
    ).validate()

    legacy_present = [
        name
        for name in LEGACY_ENVIRONMENT_NAMES
        if str(snapshot.environment.get(name) or "")
    ]
    if legacy_present:
        raise CleanupError("Legacy credential environment remains active")

    properties = _systemd_properties(args.service)
    _, definition_names, environment_files = build_systemd_cleanup(
        systemd_definition_paths(properties)
    )
    if definition_names:
        raise CleanupError("Legacy systemd credential definition remains")

    for path, label in (
        (args.legacy_firebase_source, "legacy Firebase source"),
        (
            json_backup_path(args.legacy_firebase_source),
            "legacy Firebase recovery source",
        ),
        (args.legacy_security_source, "legacy security source"),
        (
            json_backup_path(args.legacy_security_source),
            "legacy security recovery source",
        ),
        (args.firebase_transfer_source, "transferred Firebase source"),
        (
            args.legacy_shared_environment_source,
            "legacy shared environment source",
        ),
        (args.handoff_file, "SEC-006.6 preflight handoff"),
    ):
        _require_absent(path, label)

    for group_name in GROUPS:
        _require_absent(
            args.candidate_root / group_name,
            "staged rotation credential directory",
        )
        _require_absent(
            args.state_root / group_name,
            "retired rotation credential directory",
        )

    security_state = _read_object(
        paths.security_state_file,
        "protected security state",
    )
    server_state = _read_object(
        paths.server_state_file,
        "durable server state",
    )
    cleaned_state, counts = build_clean_security_state(
        security_state,
        server_state,
    )
    if cleaned_state != security_state:
        raise CleanupError("Protected authentication cleanup is incomplete")

    cutover = verify_complete_cutover(
        source_credential_directory=args.credential_directory,
        runtime_credential_directory=snapshot.runtime_credential_directory,
        data_root=snapshot.data_root,
        service_environment=snapshot.environment,
        legacy_firebase_source=args.legacy_firebase_source,
        legacy_security_source=args.legacy_security_source,
        minimum_tokens=0,
        manager_owner=(0, 0),
        service_owner=(
            snapshot.process_user_id,
            snapshot.process_group_id,
        ),
        runtime_owners=frozenset({
            (0, 0),
            (
                snapshot.process_user_id,
                snapshot.process_group_id,
            ),
        }),
        expect_legacy_sources=False,
    )

    inventory = summarize_device_key_inventory(
        security_state,
        server_state,
    )
    if (
        inventory.get("owner_orphaned", 0)
        or inventory.get("owner_external-unexpected", 0)
        or inventory.get("stale_current_slots", 0)
        or inventory.get("stale_previous_slots", 0)
        or inventory.get("active_keys_requiring_review", 0)
        or inventory.get("enrollment_records", 0)
    ):
        raise CleanupError("Retired device credential inventory is not empty")

    output_documents = verify_ordinary_state(paths.state_root)
    notification_records = verify_notification_history(
        paths.notification_queue_file
    )
    audit_records = verify_security_audit(paths.security_audit_file)
    if audit_records < 1:
        raise CleanupError(
            "Output sanitization has no current-format audit evidence"
        )

    return {
        **counts,
        "rotation_groups": len(GROUPS),
        "legacy_source_files": 3,
        "systemd_files": 0,
        "environment_files": len(environment_files),
        "systemd_environment_names": 0,
        "ordinary_documents": cutover.ordinary_documents,
        "notification_tokens": cutover.notification_tokens,
        "output_documents": output_documents,
        "notification_records": notification_records,
        "audit_records": audit_records,
    }


def _print_result(action: str, counts: Mapping[str, int]) -> None:
    labels = {
        "preflight": "READY",
        "cleanup": "CLEANED",
        "verify": "PASS",
    }
    print("SEC-006.6 RETIRED CREDENTIAL CLEANUP")
    print(f"Result: {labels[action]}")
    print("Privacy: no credential values or identifiers were displayed.")
    print(
        "Service credential rotation bundles: "
        f"{counts.get('rotation_groups', 0)}"
    )
    print(
        "Legacy/transferred source files: "
        f"{counts.get('legacy_source_files', 0)}"
    )
    print(
        "Systemd files requiring cleanup: "
        f"{counts.get('systemd_files', 0)}"
    )
    print(
        "Environment files requiring cleanup: "
        f"{counts.get('environment_files', 0)}"
    )
    print(
        "Legacy environment names: "
        f"{counts.get('systemd_environment_names', 0)}"
    )
    print(
        "First-party device keys retained: "
        f"{counts.get('retained_device_keys', 0)}"
    )
    print(
        "Non-first-party/orphaned key records removed: "
        f"{counts.get('removed_device_key_records', 0)}"
    )
    print(
        "Retired previous key slots removed: "
        f"{counts.get('removed_previous_slots', 0)}"
    )
    print(
        "Expired enrollment records removed: "
        f"{counts.get('removed_enrollments', 0)}"
    )
    if action == "verify":
        print("Complete credential cutover: PASS (legacy sources=0)")
        print("Retired device credential inventory: PASS")
        print(
            "Output sanitization: PASS "
            f"(documents={counts.get('output_documents', 0)} "
            f"notifications={counts.get('notification_records', 0)} "
            f"audit={counts.get('audit_records', 0)})"
        )
    print(
        "Destructive cleanup performed: "
        + ("YES" if action == "cleanup" else "NO")
    )


def main(argv: list[str] | None = None) -> int:
    if os.name == "nt":
        print("ERROR: this cleanup adapter requires Linux/systemd")
        return 2
    if os.geteuid() != 0:
        print("ERROR: run this protected cleanup operation as root")
        return 2

    args = _parser().parse_args(argv)
    args.destructive_cleanup_started = False
    args.credential_directory = _absolute(
        args.credential_directory,
        "Credential directory",
    )
    args.candidate_root = _absolute(
        args.candidate_root,
        "Candidate root",
    )
    args.state_root = _absolute(args.state_root, "Rotation state root")
    args.legacy_firebase_source = _absolute(
        args.legacy_firebase_source,
        "Legacy Firebase source",
    )
    args.legacy_security_source = _absolute(
        args.legacy_security_source,
        "Legacy security source",
    )
    args.firebase_transfer_source = _absolute(
        args.firebase_transfer_source,
        "Transferred Firebase source",
    )
    args.legacy_shared_environment_source = _absolute(
        args.legacy_shared_environment_source,
        "Legacy shared environment source",
    )
    args.handoff_file = _absolute(
        args.handoff_file,
        "SEC-006.6 preflight handoff",
    )

    try:
        if args.action == "preflight":
            counts = run_preflight(args)
        elif args.action == "cleanup":
            counts = run_cleanup(args)
        else:
            counts = run_verify(args)
    except (CleanupError, RotationError, RuntimeError) as exc:
        print(f"SEC-006.6 stopped: {exc}")
        print("Privacy: no credential values or identifiers were displayed.")
        print(
            "Destructive cleanup performed: "
            + (
                "POSSIBLY PARTIAL; KEEP SERVICE STOPPED"
                if args.destructive_cleanup_started
                else "NO"
            )
        )
        return 1
    except OSError:
        print("SEC-006.6 stopped: protected cleanup I/O failed")
        print("Privacy: no credential values or identifiers were displayed.")
        print(
            "Destructive cleanup performed: "
            + (
                "POSSIBLY PARTIAL; KEEP SERVICE STOPPED"
                if args.destructive_cleanup_started
                else "NO"
            )
        )
        return 1

    _print_result(args.action, counts)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

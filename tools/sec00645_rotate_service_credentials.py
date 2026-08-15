#!/usr/bin/env python3
"""Safely stage, activate, verify, or roll back SEC-006 credentials.

This Linux operations tool treats each provider's credential files as one
transaction.  It validates protected ownership and permissions, retains one
private rollback set, replaces each manager-owned file through an atomic
same-directory rename, and reports no credential values or identifiers.

The running systemd service is deliberately not restarted by this tool.
systemd keeps using its existing runtime credential snapshot until the
operator completes provider work and explicitly restarts the service.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import fcntl
import getpass
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
from typing import Iterator, Mapping


SOURCE_ROOT = Path(__file__).resolve().parents[1]

if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from tools.sec0045_verify_complete_credential_cutover import (  # noqa: E402
    inspect_active_service,
    verify_service_credential_copies,
)


DEFAULT_CREDENTIAL_DIRECTORY = Path("/etc/kotibot/credentials.d")
DEFAULT_CANDIDATE_ROOT = Path("/etc/kotibot/rotation-candidates.d")
DEFAULT_STATE_ROOT = Path("/etc/kotibot/credential-rotation-state.d")
DEFAULT_LOCK_FILE = Path("/run/lock/kotibot-sec00645.lock")
MAX_TEXT_BYTES = 65536
MAX_JSON_BYTES = 1024 * 1024


class RotationError(RuntimeError):
    """A value-free credential rotation failure."""


@dataclass(frozen=True)
class CredentialGroup:
    name: str
    credential_names: tuple[str, ...]
    required_changes: tuple[str, ...]
    json_credentials: tuple[str, ...] = ()


GROUPS: Mapping[str, CredentialGroup] = {
    "tapo-account": CredentialGroup(
        name="tapo-account",
        credential_names=(
            "tapo-username",
            "tapo-password",
        ),
        # One shared TP-Link/Tapo cloud account serves every Tapo device.
        # Its identity normally remains unchanged; its one password rotates.
        required_changes=("tapo-password",),
    ),
    "tapo-camera": CredentialGroup(
        name="tapo-camera",
        credential_names=(
            "tapo-camera-username",
            "tapo-camera-password",
        ),
        # This is the separate local RTSP/ONVIF camera account. It is not
        # another Tapo cloud password and is never applied per Tapo device.
        required_changes=("tapo-camera-password",),
    ),
    "firebase": CredentialGroup(
        name="firebase",
        credential_names=("firebase-service-account.json",),
        required_changes=("firebase-service-account.json",),
        json_credentials=("firebase-service-account.json",),
    ),
}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "SEC-006.4/006.5 protected credential staging and activation "
            "with private rollback and value-free output. Linux/systemd host "
            "only."
        ),
    )
    parser.add_argument(
        "action",
        choices=(
            "stage",
            "preflight",
            "activate",
            "verify",
            "runtime-verify",
            "rollback",
        ),
    )
    parser.add_argument("--group", required=True, choices=tuple(GROUPS))
    parser.add_argument(
        "--service",
        default="kotibot",
        help="active systemd service used by runtime-verify",
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
        "--candidate-file",
        type=Path,
        help=(
            "private replacement credential file; required only when staging "
            "the Firebase group"
        ),
    )
    parser.add_argument(
        "--lock-file",
        type=Path,
        default=DEFAULT_LOCK_FILE,
        help=argparse.SUPPRESS,
    )
    return parser


def _safe_child(root: Path, name: str) -> Path:
    if (
        not name
        or name in {".", ".."}
        or Path(name).name != name
        or "/" in name
        or "\\" in name
        or "\x00" in name
    ):
        raise RotationError("Unsafe credential filename")
    return Path(root) / name


def _lstat(path: Path, label: str) -> os.stat_result:
    try:
        return path.lstat()
    except FileNotFoundError:
        raise RotationError(f"{label} is missing") from None
    except OSError:
        raise RotationError(f"{label} could not be inspected") from None


def _validate_private_directory(
    path: Path,
    label: str,
    *,
    expected_uid: int,
) -> None:
    metadata = _lstat(path, label)
    if stat.S_ISLNK(metadata.st_mode):
        raise RotationError(f"{label} must not be a symbolic link")
    if not stat.S_ISDIR(metadata.st_mode):
        raise RotationError(f"{label} must be a directory")
    if metadata.st_uid != expected_uid:
        raise RotationError(f"{label} has the wrong owner")
    if stat.S_IMODE(metadata.st_mode) & 0o077:
        raise RotationError(f"{label} permissions are not private")


def _read_private_file(
    path: Path,
    label: str,
    *,
    expected_uid: int,
    max_bytes: int,
) -> bytes:
    metadata = _lstat(path, label)
    if stat.S_ISLNK(metadata.st_mode):
        raise RotationError(f"{label} must not be a symbolic link")
    if not stat.S_ISREG(metadata.st_mode):
        raise RotationError(f"{label} must be a regular file")
    if metadata.st_uid != expected_uid:
        raise RotationError(f"{label} has the wrong owner")
    if stat.S_IMODE(metadata.st_mode) & 0o077:
        raise RotationError(f"{label} permissions are not private")
    if metadata.st_size < 1:
        raise RotationError(f"{label} is empty")
    if metadata.st_size > max_bytes:
        raise RotationError(f"{label} is too large")

    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(
        os,
        "O_NOFOLLOW",
        0,
    )
    try:
        descriptor = os.open(path, flags)
    except OSError:
        raise RotationError(f"{label} could not be opened safely") from None

    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode):
            raise RotationError(f"{label} must be a regular file")
        if opened.st_uid != expected_uid:
            raise RotationError(f"{label} has the wrong owner")
        if stat.S_IMODE(opened.st_mode) & 0o077:
            raise RotationError(f"{label} permissions are not private")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(descriptor, min(65536, max_bytes + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > max_bytes:
                raise RotationError(f"{label} is too large")
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def _text_value(data: bytes, label: str) -> str:
    try:
        value = data.decode("utf-8")
    except UnicodeDecodeError:
        raise RotationError(f"{label} is not valid UTF-8") from None
    if value.endswith("\n"):
        value = value[:-1]
    if not value.strip():
        raise RotationError(f"{label} is empty")
    if "\x00" in value or "\r" in value or "\n" in value:
        raise RotationError(f"{label} must contain one text line")
    return value


def _validate_text(data: bytes, label: str) -> None:
    _text_value(data, label)


def _firebase_document(data: bytes, label: str) -> dict:
    try:
        document = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise RotationError(f"{label} is not valid JSON") from None
    if not isinstance(document, dict):
        raise RotationError(f"{label} must contain a JSON object")

    required = (
        "type",
        "project_id",
        "private_key_id",
        "private_key",
        "client_email",
        "token_uri",
    )
    if document.get("type") != "service_account" or any(
        not isinstance(document.get(name), str)
        or not document[name].strip()
        for name in required
    ):
        raise RotationError(
            f"{label} is not a complete service-account credential"
        )
    if "BEGIN PRIVATE KEY" not in document["private_key"]:
        raise RotationError(f"{label} has an invalid private-key field")
    return document


def _validate_credential(
    name: str,
    data: bytes,
    group: CredentialGroup,
) -> None:
    if name in group.json_credentials:
        _firebase_document(data, name)
    else:
        _validate_text(data, name)


def _load_bundle(
    root: Path,
    group: CredentialGroup,
    *,
    expected_uid: int,
    label: str,
) -> dict[str, bytes]:
    _validate_private_directory(root, label, expected_uid=expected_uid)
    result: dict[str, bytes] = {}
    for name in group.credential_names:
        data = _read_private_file(
            _safe_child(root, name),
            f"{label} credential {name}",
            expected_uid=expected_uid,
            max_bytes=(MAX_JSON_BYTES if name in group.json_credentials else MAX_TEXT_BYTES),
        )
        _validate_credential(name, data, group)
        result[name] = data
    return result


def _validate_required_changes(
    group: CredentialGroup,
    current: Mapping[str, bytes],
    candidate: Mapping[str, bytes],
) -> None:
    unchanged = [
        name
        for name in group.required_changes
        if (
            current[name] == candidate[name]
            if name in group.json_credentials
            else _text_value(current[name], f"current {name}")
            == _text_value(candidate[name], f"candidate {name}")
        )
    ]
    if unchanged:
        raise RotationError(
            "Required replacement credential is unchanged: "
            + ", ".join(unchanged)
        )

    if group.name == "firebase":
        current_doc = _firebase_document(
            current["firebase-service-account.json"],
            "current Firebase credential",
        )
        candidate_doc = _firebase_document(
            candidate["firebase-service-account.json"],
            "candidate Firebase credential",
        )
        if (
            current_doc["private_key_id"] == candidate_doc["private_key_id"]
            or current_doc["private_key"] == candidate_doc["private_key"]
        ):
            raise RotationError("Firebase key material was not rotated")


def _read_private_candidate_source(
    path: Path,
    label: str,
    *,
    max_bytes: int,
) -> bytes:
    metadata = _lstat(path, label)
    if stat.S_ISLNK(metadata.st_mode):
        raise RotationError(f"{label} must not be a symbolic link")
    if not stat.S_ISREG(metadata.st_mode):
        raise RotationError(f"{label} must be a regular file")
    if stat.S_IMODE(metadata.st_mode) & 0o077:
        raise RotationError(f"{label} permissions are not private")
    if metadata.st_size < 1:
        raise RotationError(f"{label} is empty")
    if metadata.st_size > max_bytes:
        raise RotationError(f"{label} is too large")

    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(
        os,
        "O_NOFOLLOW",
        0,
    )
    try:
        descriptor = os.open(path, flags)
    except OSError:
        raise RotationError(f"{label} could not be opened safely") from None

    try:
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_dev != metadata.st_dev
            or opened.st_ino != metadata.st_ino
        ):
            raise RotationError(f"{label} changed during inspection")
        if stat.S_IMODE(opened.st_mode) & 0o077:
            raise RotationError(f"{label} permissions are not private")

        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(descriptor, min(65536, max_bytes + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > max_bytes:
                raise RotationError(f"{label} is too large")
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def _prompt_text_replacements(
    group: CredentialGroup,
) -> dict[str, bytes]:
    labels = {
        "tapo-password": "Tapo account password",
        "tapo-camera-password": "Tapo camera account password",
    }
    replacements: dict[str, bytes] = {}
    for name in group.required_changes:
        label = labels.get(name, name)
        value = getpass.getpass(f"New {label}: ")
        confirmation = getpass.getpass(f"Confirm new {label}: ")
        if value != confirmation:
            raise RotationError(f"{label} confirmation does not match")
        data = (value + "\n").encode("utf-8")
        _validate_credential(name, data, group)
        replacements[name] = data
    return replacements


def stage_candidate(
    group: CredentialGroup,
    credential_directory: Path,
    candidate_directory: Path,
    state_directory: Path,
    replacements: Mapping[str, bytes],
    *,
    expected_uid: int,
) -> None:
    if state_directory.exists() or state_directory.is_symlink():
        raise RotationError(
            "A retained rotation state already exists for this group"
        )
    if candidate_directory.exists() or candidate_directory.is_symlink():
        raise RotationError("A staged candidate already exists for this group")

    current = _load_bundle(
        credential_directory,
        group,
        expected_uid=expected_uid,
        label="protected credential directory",
    )
    unknown = sorted(set(replacements) - set(group.credential_names))
    if unknown:
        raise RotationError("Replacement contains an unexpected credential name")
    missing = sorted(set(group.required_changes) - set(replacements))
    if missing:
        raise RotationError(
            "Replacement is missing required credential material: "
            + ", ".join(missing)
        )

    candidate = dict(current)
    candidate.update(replacements)
    for name, data in candidate.items():
        _validate_credential(name, data, group)
    _validate_required_changes(group, current, candidate)

    candidate_root = candidate_directory.parent
    if candidate_root.exists() or candidate_root.is_symlink():
        _validate_private_directory(
            candidate_root,
            "candidate credential root",
            expected_uid=expected_uid,
        )
    else:
        _create_private_directory(candidate_root, owner_uid=expected_uid)
    _create_private_directory(candidate_directory, owner_uid=expected_uid)

    try:
        for name, data in candidate.items():
            _atomic_write(
                candidate_directory / name,
                data,
                owner_uid=expected_uid,
            )
        staged = _load_bundle(
            candidate_directory,
            group,
            expected_uid=expected_uid,
            label="candidate credential directory",
        )
        if staged != candidate:
            raise RotationError("Staged credential verification failed")
    except BaseException:
        for name in group.credential_names:
            try:
                (candidate_directory / name).unlink()
            except FileNotFoundError:
                pass
        try:
            candidate_directory.rmdir()
        except OSError:
            pass
        raise


def preflight(
    group: CredentialGroup,
    credential_directory: Path,
    candidate_directory: Path,
    state_directory: Path,
    *,
    expected_uid: int,
) -> tuple[dict[str, bytes], dict[str, bytes]]:
    if state_directory.exists() or state_directory.is_symlink():
        raise RotationError(
            "A retained rotation state already exists for this group"
        )
    current = _load_bundle(
        credential_directory,
        group,
        expected_uid=expected_uid,
        label="protected credential directory",
    )
    candidate = _load_bundle(
        candidate_directory,
        group,
        expected_uid=expected_uid,
        label="candidate credential directory",
    )
    _validate_required_changes(group, current, candidate)
    return current, candidate


def _fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    descriptor = os.open(path, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _atomic_write(path: Path, data: bytes, *, owner_uid: int) -> None:
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        dir=path.parent,
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        if os.name != "nt":
            os.fchown(descriptor, owner_uid, -1)
        offset = 0
        while offset < len(data):
            offset += os.write(descriptor, data[offset:])
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    except BaseException:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
        raise


def _create_private_directory(path: Path, *, owner_uid: int) -> None:
    path.mkdir(mode=0o700, parents=False, exist_ok=False)
    os.chmod(path, 0o700)
    if os.name != "nt":
        os.chown(path, owner_uid, -1)
    _fsync_directory(path.parent)


def _write_manifest(
    state_directory: Path,
    group: CredentialGroup,
    status: str,
    *,
    owner_uid: int,
) -> None:
    document = {
        "schema": 1,
        "group": group.name,
        "status": status,
        "credential_names": list(group.credential_names),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    _atomic_write(
        state_directory / "manifest.json",
        (json.dumps(document, sort_keys=True) + "\n").encode("utf-8"),
        owner_uid=owner_uid,
    )


def _load_manifest(
    state_directory: Path,
    group: CredentialGroup,
    *,
    expected_uid: int,
) -> dict:
    _validate_private_directory(
        state_directory,
        "rotation state directory",
        expected_uid=expected_uid,
    )
    data = _read_private_file(
        state_directory / "manifest.json",
        "rotation manifest",
        expected_uid=expected_uid,
        max_bytes=65536,
    )
    try:
        document = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise RotationError("Rotation manifest is malformed") from None
    if not isinstance(document, dict):
        raise RotationError("Rotation manifest is malformed")
    if (
        document.get("schema") != 1
        or document.get("group") != group.name
        or document.get("credential_names") != list(group.credential_names)
    ):
        raise RotationError("Rotation manifest does not match this group")
    return document


def activate(
    group: CredentialGroup,
    credential_directory: Path,
    candidate_directory: Path,
    state_directory: Path,
    *,
    expected_uid: int,
) -> None:
    current, candidate = preflight(
        group,
        credential_directory,
        candidate_directory,
        state_directory,
        expected_uid=expected_uid,
    )
    state_root = state_directory.parent
    if state_root.exists() or state_root.is_symlink():
        _validate_private_directory(
            state_root,
            "rotation state root",
            expected_uid=expected_uid,
        )
    else:
        _create_private_directory(state_root, owner_uid=expected_uid)
    _create_private_directory(state_directory, owner_uid=expected_uid)
    backup_directory = state_directory / "previous"
    _create_private_directory(backup_directory, owner_uid=expected_uid)

    try:
        for name, data in current.items():
            _atomic_write(
                backup_directory / name,
                data,
                owner_uid=expected_uid,
            )
        backed_up = _load_bundle(
            backup_directory,
            group,
            expected_uid=expected_uid,
            label="rollback credential directory",
        )
        if backed_up != current:
            raise RotationError("Rollback credential verification failed")

        _write_manifest(
            state_directory,
            group,
            "prepared",
            owner_uid=expected_uid,
        )
        for name, data in candidate.items():
            _atomic_write(
                credential_directory / name,
                data,
                owner_uid=expected_uid,
            )

        installed = _load_bundle(
            credential_directory,
            group,
            expected_uid=expected_uid,
            label="protected credential directory",
        )
        if installed != candidate:
            raise RotationError("Activated credential verification failed")
        _write_manifest(
            state_directory,
            group,
            "activated",
            owner_uid=expected_uid,
        )
    except BaseException as exc:
        try:
            for name, data in current.items():
                _atomic_write(
                    credential_directory / name,
                    data,
                    owner_uid=expected_uid,
                )
            _write_manifest(
                state_directory,
                group,
                "rolled-back-after-failure",
                owner_uid=expected_uid,
            )
        except BaseException:
            raise RotationError(
                "Activation failed and automatic rollback could not be verified"
            ) from None
        if isinstance(exc, RotationError):
            raise
        raise RotationError("Activation failed; previous credentials restored") from None


def verify_active(
    group: CredentialGroup,
    credential_directory: Path,
    candidate_directory: Path,
    state_directory: Path,
    *,
    expected_uid: int,
) -> None:
    manifest = _load_manifest(
        state_directory,
        group,
        expected_uid=expected_uid,
    )
    if manifest.get("status") != "activated":
        raise RotationError("Rotation state is not activated")
    current = _load_bundle(
        credential_directory,
        group,
        expected_uid=expected_uid,
        label="protected credential directory",
    )
    candidate = _load_bundle(
        candidate_directory,
        group,
        expected_uid=expected_uid,
        label="candidate credential directory",
    )
    previous = _load_bundle(
        state_directory / "previous",
        group,
        expected_uid=expected_uid,
        label="rollback credential directory",
    )
    _validate_required_changes(group, previous, current)
    if current != candidate:
        raise RotationError("Protected credentials do not match the candidates")


def verify_runtime_snapshot(
    group: CredentialGroup,
    credential_directory: Path,
    candidate_directory: Path,
    state_directory: Path,
    service_name: str,
    *,
    expected_uid: int,
    expected_source_owner: tuple[int, int],
) -> None:
    """Prove the activated group reached the restarted service snapshot."""
    verify_active(
        group,
        credential_directory,
        candidate_directory,
        state_directory,
        expected_uid=expected_uid,
    )

    try:
        snapshot = inspect_active_service(service_name)
        verify_service_credential_copies(
            credential_directory,
            snapshot.runtime_credential_directory,
            expected_source_owner=expected_source_owner,
            expected_runtime_owners=frozenset({
                (0, 0),
                (
                    snapshot.process_user_id,
                    snapshot.process_group_id,
                ),
            }),
        )
    except RuntimeError as exc:
        raise RotationError(
            f"Live service credential verification failed: {exc}"
        ) from None


def rollback(
    group: CredentialGroup,
    credential_directory: Path,
    state_directory: Path,
    *,
    expected_uid: int,
) -> None:
    manifest = _load_manifest(
        state_directory,
        group,
        expected_uid=expected_uid,
    )
    if manifest.get("status") not in {
        "activated",
        "prepared",
        "rolled-back-after-failure",
    }:
        raise RotationError("Rotation state cannot be rolled back")
    previous = _load_bundle(
        state_directory / "previous",
        group,
        expected_uid=expected_uid,
        label="rollback credential directory",
    )
    _validate_private_directory(
        credential_directory,
        "protected credential directory",
        expected_uid=expected_uid,
    )
    for name, data in previous.items():
        _atomic_write(
            credential_directory / name,
            data,
            owner_uid=expected_uid,
        )
    restored = _load_bundle(
        credential_directory,
        group,
        expected_uid=expected_uid,
        label="protected credential directory",
    )
    if restored != previous:
        raise RotationError("Rollback verification failed")
    _write_manifest(
        state_directory,
        group,
        "rolled-back",
        owner_uid=expected_uid,
    )


@contextmanager
def _exclusive_lock(path: Path, *, owner_uid: int) -> Iterator[None]:
    path.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
    descriptor = os.open(
        path,
        os.O_CREAT | os.O_RDWR | getattr(os, "O_CLOEXEC", 0),
        0o600,
    )
    try:
        os.fchmod(descriptor, 0o600)
        if os.name != "nt":
            os.fchown(descriptor, owner_uid, -1)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RotationError("Another credential rotation is running") from None
        yield
    finally:
        os.close(descriptor)


def _print_result(action: str, group: CredentialGroup) -> None:
    labels = {
        "stage": "STAGED",
        "preflight": "READY",
        "activate": "ACTIVATED",
        "verify": "VERIFIED",
        "runtime-verify": "RUNTIME VERIFIED",
        "rollback": "ROLLED BACK",
    }
    print("SEC-006 SERVICE CREDENTIAL ROTATION")
    print(f"Group: {group.name}")
    print(f"Credential files: {len(group.credential_names)}")
    print(f"Result: {labels[action]}")
    print("Privacy: no credential values or provider identifiers were displayed.")
    if action == "stage":
        print("Provider/device credential change performed: NO")
    elif action == "activate":
        print("Rollback: retained in protected rotation state.")
        print("Service restart performed: NO")
    elif action == "runtime-verify":
        print("Active service credential snapshot: MATCHED")
    elif action == "rollback":
        print("Service restart performed: NO")


def main(argv: list[str] | None = None) -> int:
    if os.name == "nt":
        print("ERROR: this tool is for the Linux/systemd host", file=sys.stderr)
        return 2
    args = _parser().parse_args(argv)
    if os.geteuid() != 0:
        print("ERROR: run this protected credential operation as root", file=sys.stderr)
        return 2

    group = GROUPS[args.group]
    candidate_directory = args.candidate_root / group.name
    state_directory = args.state_root / group.name
    try:
        if args.action != "stage" and args.candidate_file is not None:
            raise RotationError("--candidate-file is valid only with stage")
        with _exclusive_lock(args.lock_file, owner_uid=0):
            if args.action == "stage":
                if group.json_credentials:
                    if args.candidate_file is None:
                        raise RotationError(
                            "Firebase staging requires --candidate-file"
                        )
                    replacements = {
                        "firebase-service-account.json": (
                            _read_private_candidate_source(
                                args.candidate_file,
                                "Firebase candidate source",
                                max_bytes=MAX_JSON_BYTES,
                            )
                        )
                    }
                else:
                    if args.candidate_file is not None:
                        raise RotationError(
                            "Text credential staging does not use --candidate-file"
                        )
                    replacements = _prompt_text_replacements(group)
                stage_candidate(
                    group,
                    args.credential_directory,
                    candidate_directory,
                    state_directory,
                    replacements,
                    expected_uid=0,
                )
            elif args.action == "preflight":
                preflight(
                    group,
                    args.credential_directory,
                    candidate_directory,
                    state_directory,
                    expected_uid=0,
                )
            elif args.action == "activate":
                activate(
                    group,
                    args.credential_directory,
                    candidate_directory,
                    state_directory,
                    expected_uid=0,
                )
            elif args.action == "verify":
                verify_active(
                    group,
                    args.credential_directory,
                    candidate_directory,
                    state_directory,
                    expected_uid=0,
                )
            elif args.action == "runtime-verify":
                verify_runtime_snapshot(
                    group,
                    args.credential_directory,
                    candidate_directory,
                    state_directory,
                    args.service,
                    expected_uid=0,
                    expected_source_owner=(0, 0),
                )
            else:
                rollback(
                    group,
                    args.credential_directory,
                    state_directory,
                    expected_uid=0,
                )
    except RotationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    _print_result(args.action, group)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

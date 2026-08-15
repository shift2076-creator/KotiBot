#!/usr/bin/env python3
"""Verify the complete SEC-004 cutover without displaying credentials."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
from typing import Mapping

try:
    import pwd
except ImportError:  # pragma: no cover - unavailable on Windows
    pwd = None


SOURCE_ROOT = Path(__file__).resolve().parents[1]

if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from server_core.credentials import (  # noqa: E402
    default_credential_directory,
    read_binary_credential_file,
)
from server_core.integration_credentials import (  # noqa: E402
    CAMERA_TALK_ICE_SERVERS_ENVIRONMENT,
    CAMERA_TALK_TURN_CREDENTIAL_ENVIRONMENT,
    CAMERA_TALK_TURN_USERNAME_ENVIRONMENT,
    CLOUDFLARE_API_TOKEN_ENVIRONMENT,
    INTEGRATION_CREDENTIAL_NAME,
    integration_credential_document_from_environment,
    validate_integration_credential_document,
)
from server_core.io import (  # noqa: E402
    JsonStateReadError,
    json_backup_path,
    read_json_object,
)
from server_core.paths import RuntimePaths  # noqa: E402
from tools.sec0043_verify_auth_credential_cutover import (  # noqa: E402
    verify_cutover as verify_auth_cutover,
)
from tools.sec004_migrate_service_credentials import (  # noqa: E402
    FIREBASE_CREDENTIAL_NAME,
    TAPO_CREDENTIALS,
)


SERVICE_CREDENTIAL_NAMES = (
    *(name for name, _ in TAPO_CREDENTIALS),
    FIREBASE_CREDENTIAL_NAME,
    INTEGRATION_CREDENTIAL_NAME,
)
TAPO_LEGACY_ENVIRONMENTS = tuple(
    environment_name
    for _, environment_name in TAPO_CREDENTIALS
)
INTEGRATION_FIELD_ENVIRONMENTS = {
    "cloudflare_api_token": CLOUDFLARE_API_TOKEN_ENVIRONMENT,
    "camera_talk_turn_username": (
        CAMERA_TALK_TURN_USERNAME_ENVIRONMENT
    ),
    "camera_talk_turn_credential": (
        CAMERA_TALK_TURN_CREDENTIAL_ENVIRONMENT
    ),
    "camera_talk_ice_servers": (
        CAMERA_TALK_ICE_SERVERS_ENVIRONMENT
    ),
}
DASHBOARD_LEGACY_ENVIRONMENTS = (
    "KOTIBOT_DASHBOARD_EMAIL",
    "KOTIBOT_DASHBOARD_PASSWORD",
)
SERVICE_ENVIRONMENT_ALLOWLIST = frozenset({
    "CREDENTIALS_DIRECTORY",
    "KOTIBOT_DATA_DIR",
    "XDG_DATA_HOME",
    *TAPO_LEGACY_ENVIRONMENTS,
    *INTEGRATION_FIELD_ENVIRONMENTS.values(),
    *DASHBOARD_LEGACY_ENVIRONMENTS,
})
FIREBASE_PROTECTED_FIELDS = frozenset({
    "private_key",
    "private_key_id",
    "client_email",
    "client_id",
})
AUTH_PROTECTED_FIELDS = frozenset({
    "session_secret",
    "dashboard_password_hash",
    "password_hash",
    "secret",
    "token_hash",
})
COMPOSITE_PROTECTED_FIELDS = frozenset({
    "credential",
    "password",
    "token",
    "username",
})
FORBIDDEN_ORDINARY_STATE_KEYS = frozenset({
    "access_token",
    "api_key",
    "api_token",
    "authorization",
    "camera_talk_ice_servers",
    "camera_talk_turn_credential",
    "camera_talk_turn_username",
    "cloudflare_api_token",
    "credential",
    "credentials",
    "dashboard_key",
    "dashboard_key_hash",
    "dashboard_password_hash",
    "dashboard_sessions",
    "device_enrollments",
    "device_keys",
    "fcm_token",
    "fcm_token_at",
    "firebase_service_account",
    "password",
    "password_hash",
    "private_key",
    "private_key_id",
    "refresh_token",
    "secret",
    "session_secret",
    "tapo_camera_password",
    "tapo_camera_username",
    "tapo_password",
    "tapo_rtsp_url",
    "tapo_username",
    "token_hash",
})
MAX_SERVICE_ENVIRONMENT_BYTES = 1024 * 1024
MAX_PROCESS_STATUS_BYTES = 256 * 1024
MAX_ORDINARY_DOCUMENT_BYTES = 16 * 1024 * 1024
MAX_ORDINARY_DOCUMENTS = 1024
MIN_EMBEDDED_MARKER_LENGTH = 8


@dataclass(frozen=True)
class ServiceSnapshot:
    process_id: int
    process_user_id: int
    process_group_id: int
    environment: Mapping[str, str]
    data_root: Path
    runtime_credential_directory: Path


@dataclass(frozen=True)
class VerificationSummary:
    service_credentials: int
    dashboard_users: int
    dashboard_sessions: int
    device_keys: int
    device_enrollments: int
    notification_tokens: int
    ordinary_documents: int
    retained_legacy_sources: int


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Verify SEC-004 permissions, restart cutover, compatibility "
            "sources, and ordinary-state sanitization without printing "
            "credential values."
        ),
    )
    parser.add_argument(
        "--service",
        default="kotibot",
        help="active Linux systemd service to inspect",
    )
    parser.add_argument(
        "--credential-directory",
        type=Path,
        default=default_credential_directory(),
        help="manager-owned protected service credential directory",
    )
    parser.add_argument(
        "--data-root",
        type=Path,
        help=(
            "override the running service data root; otherwise derive it "
            "from the active process"
        ),
    )
    parser.add_argument(
        "--legacy-firebase-source",
        type=Path,
        default=(
            SOURCE_ROOT
            / "subsystems"
            / "notifications"
            / FIREBASE_CREDENTIAL_NAME
        ),
    )
    parser.add_argument(
        "--legacy-security-source",
        type=Path,
        default=(
            SOURCE_ROOT
            / "subsystems"
            / "security"
            / "security_state.json"
        ),
    )
    parser.add_argument(
        "--minimum-tokens",
        type=int,
        default=0,
        help="require at least this many protected FCM token records",
    )
    parser.add_argument(
        "--expect-cleanup",
        action="store_true",
        help=(
            "require retired environment and worktree credential sources "
            "to be absent instead of retained"
        ),
    )
    return parser


def _safe_service_name(value: str) -> str:
    name = str(value or "").strip()
    allowed = (
        "abcdefghijklmnopqrstuvwxyz"
        "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        "0123456789@_.-"
    )

    if not name or any(character not in allowed for character in name):
        raise RuntimeError("Systemd service name is invalid")

    return name


def _systemd_properties(service_name: str) -> dict[str, str]:
    try:
        completed = subprocess.run(
            [
                "systemctl",
                "show",
                service_name,
                "--property=ActiveState",
                "--property=MainPID",
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError(
            "Could not inspect the KotiBot systemd service"
        ) from exc

    properties: dict[str, str] = {}

    for line in completed.stdout.splitlines():
        name, separator, value = line.partition("=")

        if separator:
            properties[name] = value.strip()

    return properties


def _allowed_process_environment(process_id: int) -> dict[str, str]:
    path = Path("/proc") / str(process_id) / "environ"

    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise RuntimeError(
            "Could not inspect the KotiBot service environment"
        ) from exc

    if len(payload) > MAX_SERVICE_ENVIRONMENT_BYTES:
        raise RuntimeError(
            "KotiBot service environment is unexpectedly large"
        )

    environment: dict[str, str] = {}

    for entry in payload.split(b"\x00"):
        raw_name, separator, raw_value = entry.partition(b"=")

        if not separator:
            continue

        try:
            name = raw_name.decode("utf-8")
        except UnicodeDecodeError:
            continue

        if name not in SERVICE_ENVIRONMENT_ALLOWLIST:
            continue

        try:
            environment[name] = raw_value.decode("utf-8")
        except UnicodeDecodeError:
            raise RuntimeError(
                f"Service environment value is invalid: {name}"
            ) from None

    return environment


def _absolute_path(value: Path | str, label: str) -> Path:
    path = Path(value).expanduser()

    if not path.is_absolute():
        raise RuntimeError(f"{label} must be an absolute path")

    return Path(os.path.abspath(path))


def _service_data_root(
    process_user_id: int,
    environment: Mapping[str, str],
) -> Path:
    configured = str(environment.get("KOTIBOT_DATA_DIR", "")).strip()

    if configured:
        return _absolute_path(configured, "Service data root")

    xdg_data_home = str(environment.get("XDG_DATA_HOME", "")).strip()

    if xdg_data_home:
        return (
            _absolute_path(xdg_data_home, "Service XDG data root")
            / "kotibot"
        )

    if pwd is None:
        raise RuntimeError(
            "Could not resolve the KotiBot service user home"
        )

    try:
        service_home = Path(pwd.getpwuid(process_user_id).pw_dir)
    except (KeyError, OSError) as exc:
        raise RuntimeError(
            "Could not resolve the KotiBot service user home"
        ) from exc

    return _absolute_path(
        service_home / ".local" / "share" / "kotibot",
        "Service data root",
    )


def _process_identity_from_status(payload: bytes) -> tuple[int, int]:
    identifiers: dict[bytes, int] = {}

    for line in payload.splitlines():
        name, separator, values = line.partition(b":")

        if not separator or name not in {b"Uid", b"Gid"}:
            continue

        fields = values.split()

        if len(fields) < 2 or not fields[1].isdigit():
            raise RuntimeError(
                "KotiBot service process identity is invalid"
            )

        identifiers[name] = int(fields[1])

    if identifiers.keys() != {b"Uid", b"Gid"}:
        raise RuntimeError(
            "KotiBot service process identity is unavailable"
        )

    return identifiers[b"Uid"], identifiers[b"Gid"]


def _process_identity(process_id: int) -> tuple[int, int]:
    status_path = Path("/proc") / str(process_id) / "status"

    try:
        payload = status_path.read_bytes()
    except OSError as exc:
        raise RuntimeError(
            "Could not inspect the KotiBot service process"
        ) from exc

    if len(payload) > MAX_PROCESS_STATUS_BYTES:
        raise RuntimeError(
            "KotiBot service process status is unexpectedly large"
        )

    return _process_identity_from_status(payload)


def inspect_active_service(
    service_name: str,
    *,
    data_root_override: Path | None = None,
) -> ServiceSnapshot:
    if os.name == "nt":
        raise RuntimeError(
            "The live SEC-004.5 service adapter requires Linux systemd"
        )

    service_name = _safe_service_name(service_name)
    properties = _systemd_properties(service_name)

    if properties.get("ActiveState") != "active":
        raise RuntimeError("KotiBot systemd service is not active")

    process_id_text = properties.get("MainPID", "")

    if not process_id_text.isdigit() or int(process_id_text) <= 0:
        raise RuntimeError("KotiBot systemd service has no active process")

    process_id = int(process_id_text)
    process_user_id, process_group_id = _process_identity(process_id)

    environment = _allowed_process_environment(process_id)
    runtime_directory = str(
        environment.get("CREDENTIALS_DIRECTORY", "")
    ).strip()

    if not runtime_directory:
        raise RuntimeError(
            "Active service has no systemd runtime credential directory"
        )

    data_root = (
        _absolute_path(data_root_override, "Service data root")
        if data_root_override is not None
        else _service_data_root(process_user_id, environment)
    )

    return ServiceSnapshot(
        process_id=process_id,
        process_user_id=process_user_id,
        process_group_id=process_group_id,
        environment=environment,
        data_root=data_root,
        runtime_credential_directory=_absolute_path(
            runtime_directory,
            "Runtime credential directory",
        ),
    )


def _metadata_without_following(path: Path, label: str):
    try:
        return Path(path).lstat()
    except OSError as exc:
        raise RuntimeError(f"{label} could not be inspected") from exc


def _require_directory(
    path: Path,
    label: str,
    *,
    exact_posix_mode: int | None = None,
    expected_posix_owner: tuple[int, int] | None = None,
) -> None:
    metadata = _metadata_without_following(path, label)

    if stat.S_ISLNK(metadata.st_mode):
        raise RuntimeError(f"{label} must not be a symbolic link")

    if not stat.S_ISDIR(metadata.st_mode):
        raise RuntimeError(f"{label} must be a directory")

    if os.name == "nt":
        return

    mode = stat.S_IMODE(metadata.st_mode)

    if expected_posix_owner is not None and (
        metadata.st_uid,
        metadata.st_gid,
    ) != expected_posix_owner:
        raise RuntimeError(f"{label} owner/group is incorrect")

    if exact_posix_mode is not None and mode != exact_posix_mode:
        raise RuntimeError(
            f"{label} permissions must be {exact_posix_mode:o}, "
            f"found {mode:o}"
        )

    if exact_posix_mode is None and mode & 0o077:
        raise RuntimeError(f"{label} permissions are not private")


def _require_private_file(
    path: Path,
    label: str,
    *,
    exact_posix_mode: int = 0o600,
    expected_posix_owner: tuple[int, int] | None = None,
) -> None:
    metadata = _metadata_without_following(path, label)

    if stat.S_ISLNK(metadata.st_mode):
        raise RuntimeError(f"{label} must not be a symbolic link")

    if not stat.S_ISREG(metadata.st_mode):
        raise RuntimeError(f"{label} must be a regular file")

    if os.name != "nt":
        mode = stat.S_IMODE(metadata.st_mode)

        if expected_posix_owner is not None and (
            metadata.st_uid,
            metadata.st_gid,
        ) != expected_posix_owner:
            raise RuntimeError(f"{label} owner/group is incorrect")

        if mode != exact_posix_mode:
            raise RuntimeError(
                f"{label} permissions must be {exact_posix_mode:o}, "
                f"found {mode:o}"
            )


def _require_systemd_runtime_directory(
    path: Path,
    *,
    expected_posix_owners: frozenset[tuple[int, int]] | None = None,
) -> tuple[int, int] | None:
    label = "runtime credential directory"
    metadata = _metadata_without_following(path, label)

    if stat.S_ISLNK(metadata.st_mode):
        raise RuntimeError(f"{label} must not be a symbolic link")

    if not stat.S_ISDIR(metadata.st_mode):
        raise RuntimeError(f"{label} must be a directory")

    if os.name == "nt":
        return None

    owner = (metadata.st_uid, metadata.st_gid)
    mode = stat.S_IMODE(metadata.st_mode)

    if (
        expected_posix_owners is not None
        and owner not in expected_posix_owners
    ):
        raise RuntimeError(f"{label} owner/group is incorrect")

    if (
        mode & 0o007
        or mode & 0o020
        or mode & 0o500 != 0o500
    ):
        raise RuntimeError(
            f"{label} permissions are not private: found {mode:o}"
        )

    return owner


def _require_systemd_runtime_file(
    path: Path,
    label: str,
    *,
    expected_posix_owner: tuple[int, int] | None,
) -> None:
    metadata = _metadata_without_following(path, label)

    if stat.S_ISLNK(metadata.st_mode):
        raise RuntimeError(f"{label} must not be a symbolic link")

    if not stat.S_ISREG(metadata.st_mode):
        raise RuntimeError(f"{label} must be a regular file")

    if os.name == "nt":
        return

    owner = (metadata.st_uid, metadata.st_gid)
    mode = stat.S_IMODE(metadata.st_mode)

    if expected_posix_owner is not None and owner != expected_posix_owner:
        raise RuntimeError(
            f"Runtime credential owner/group is incorrect: {label}"
        )

    if (
        mode & 0o137
        or mode & 0o400 != 0o400
    ):
        raise RuntimeError(
            "Runtime credential permissions are not private: "
            f"{label} found {mode:o}"
        )


def _json_object_from_payload(payload: bytes, label: str) -> dict:
    try:
        document = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError):
        raise RuntimeError(f"{label} is not valid JSON") from None

    if not isinstance(document, dict):
        raise RuntimeError(f"{label} must contain an object")

    return document


def verify_service_credential_copies(
    source_directory: Path,
    runtime_directory: Path,
    *,
    expected_source_owner: tuple[int, int] | None = None,
    expected_runtime_owners: (
        frozenset[tuple[int, int]] | None
    ) = None,
) -> tuple[dict[str, bytes], dict]:
    source_directory = _absolute_path(
        source_directory,
        "Service credential directory",
    )
    runtime_directory = _absolute_path(
        runtime_directory,
        "Runtime credential directory",
    )
    _require_directory(
        source_directory,
        "service credential directory",
        exact_posix_mode=0o700,
        expected_posix_owner=expected_source_owner,
    )
    runtime_owner = _require_systemd_runtime_directory(
        runtime_directory,
        expected_posix_owners=expected_runtime_owners,
    )
    payloads: dict[str, bytes] = {}

    for credential_name in SERVICE_CREDENTIAL_NAMES:
        source = source_directory / credential_name
        runtime = runtime_directory / credential_name
        _require_private_file(
            source,
            credential_name,
            expected_posix_owner=expected_source_owner,
        )
        _require_systemd_runtime_file(
            runtime,
            credential_name,
            expected_posix_owner=runtime_owner,
        )
        source_payload = read_binary_credential_file(
            source,
            credential_name=credential_name,
        )
        runtime_payload = read_binary_credential_file(
            runtime,
            credential_name=credential_name,
        )

        if not hmac.compare_digest(source_payload, runtime_payload):
            raise RuntimeError(
                f"Runtime credential does not match source: "
                f"{credential_name}"
            )

        payloads[credential_name] = source_payload

    for credential_name, _ in TAPO_CREDENTIALS:
        payload = payloads[credential_name]

        try:
            value = payload.decode("utf-8").strip()
        except UnicodeDecodeError:
            raise RuntimeError(
                f"Credential is not valid UTF-8: {credential_name}"
            ) from None

        if not value or "\x00" in value or "\r" in value or "\n" in value:
            raise RuntimeError(
                f"Credential must contain one text line: "
                f"{credential_name}"
            )

    _json_object_from_payload(
        payloads[FIREBASE_CREDENTIAL_NAME],
        "Firebase service credential",
    )
    integration_document = validate_integration_credential_document(
        _json_object_from_payload(
            payloads[INTEGRATION_CREDENTIAL_NAME],
            "Integration credential",
        )
    )
    return payloads, integration_document


def _read_required_object(path: Path, label: str) -> dict:
    try:
        return read_json_object(path)
    except JsonStateReadError as exc:
        raise RuntimeError(
            f"{label} could not be read: reason={exc.reason}"
        ) from None


def _add_marker(markers: set[str], value) -> None:
    if not isinstance(value, str):
        return

    clean = value.strip()

    if clean:
        markers.add(clean)


def _collect_named_fields(
    value,
    field_names: frozenset[str],
    markers: set[str],
) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).casefold() in field_names:
                _add_marker(markers, item)

            _collect_named_fields(item, field_names, markers)
        return

    if isinstance(value, list):
        for item in value:
            _collect_named_fields(item, field_names, markers)


def protected_credential_markers(
    service_payloads: Mapping[str, bytes],
    integration_document: Mapping,
    security_state_file: Path,
    notification_credentials_file: Path,
) -> frozenset[str]:
    markers: set[str] = set()

    for credential_name, _ in TAPO_CREDENTIALS:
        try:
            _add_marker(
                markers,
                service_payloads[credential_name].decode("utf-8"),
            )
        except UnicodeDecodeError:
            raise RuntimeError(
                f"Credential is not valid UTF-8: {credential_name}"
            ) from None

    firebase_document = _json_object_from_payload(
        service_payloads[FIREBASE_CREDENTIAL_NAME],
        "Firebase service credential",
    )
    _collect_named_fields(
        firebase_document,
        FIREBASE_PROTECTED_FIELDS,
        markers,
    )

    for field_name in (
        "cloudflare_api_token",
        "camera_talk_turn_username",
        "camera_talk_turn_credential",
    ):
        _add_marker(markers, integration_document.get(field_name))

    _collect_named_fields(
        integration_document.get("camera_talk_ice_servers", []),
        COMPOSITE_PROTECTED_FIELDS,
        markers,
    )
    security_state = _read_required_object(
        security_state_file,
        "security state",
    )
    _collect_named_fields(
        security_state,
        AUTH_PROTECTED_FIELDS,
        markers,
    )

    dashboard_sessions = security_state.get("dashboard_sessions", {})

    if isinstance(dashboard_sessions, dict):
        for session_identifier in dashboard_sessions:
            _add_marker(markers, session_identifier)

    notification_state = _read_required_object(
        notification_credentials_file,
        "notification credential state",
    )
    _collect_named_fields(
        notification_state.get("tokens", {}),
        frozenset({"token"}),
        markers,
    )
    return frozenset(markers)


def _canonical_key(value) -> str:
    return re.sub(
        r"[^a-z0-9]+",
        "_",
        str(value or "").casefold(),
    ).strip("_")


def _marker_digest(value: str) -> bytes:
    return hashlib.sha256(value.encode("utf-8")).digest()


def _contains_protected_marker(
    value: str,
    *,
    exact_digests: frozenset[bytes],
    embedded_markers: tuple[str, ...],
) -> bool:
    if _marker_digest(value.strip()) in exact_digests:
        return True

    return any(marker in value for marker in embedded_markers)


def _scan_ordinary_value(
    value,
    *,
    relative_path: Path,
    exact_digests: frozenset[bytes],
    embedded_markers: tuple[str, ...],
) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            canonical_key = _canonical_key(key)

            if canonical_key in FORBIDDEN_ORDINARY_STATE_KEYS:
                raise RuntimeError(
                    "Ordinary state contains a credential field: "
                    f"file={relative_path} key={canonical_key}"
                )

            if isinstance(key, str) and _contains_protected_marker(
                key,
                exact_digests=exact_digests,
                embedded_markers=embedded_markers,
            ):
                raise RuntimeError(
                    "Ordinary state contains a protected credential value: "
                    f"file={relative_path}"
                )

            _scan_ordinary_value(
                item,
                relative_path=relative_path,
                exact_digests=exact_digests,
                embedded_markers=embedded_markers,
            )
        return

    if isinstance(value, list):
        for item in value:
            _scan_ordinary_value(
                item,
                relative_path=relative_path,
                exact_digests=exact_digests,
                embedded_markers=embedded_markers,
            )
        return

    if isinstance(value, str) and _contains_protected_marker(
        value,
        exact_digests=exact_digests,
        embedded_markers=embedded_markers,
    ):
        raise RuntimeError(
            "Ordinary state contains a protected credential value: "
            f"file={relative_path}"
        )


def scan_ordinary_state(
    state_root: Path,
    protected_markers: frozenset[str],
) -> int:
    state_root = _absolute_path(state_root, "Ordinary state root")
    _require_directory(state_root, "ordinary state root")
    paths = sorted(state_root.rglob("*.json"))

    if len(paths) > MAX_ORDINARY_DOCUMENTS:
        raise RuntimeError("Ordinary state contains too many JSON documents")

    exact_digests = frozenset(
        _marker_digest(marker)
        for marker in protected_markers
    )
    embedded_markers = tuple(
        marker
        for marker in protected_markers
        if len(marker) >= MIN_EMBEDDED_MARKER_LENGTH
    )

    for path in paths:
        relative_path = path.relative_to(state_root)
        metadata = _metadata_without_following(
            path,
            "ordinary state document",
        )

        if stat.S_ISLNK(metadata.st_mode):
            raise RuntimeError(
                "Ordinary state document must not be a symbolic link: "
                f"file={relative_path}"
            )

        if not stat.S_ISREG(metadata.st_mode):
            raise RuntimeError(
                "Ordinary state JSON path must be a regular file: "
                f"file={relative_path}"
            )

        if metadata.st_size > MAX_ORDINARY_DOCUMENT_BYTES:
            raise RuntimeError(
                "Ordinary state document is unexpectedly large: "
                f"file={relative_path}"
            )

        document = _read_required_object(
            path,
            "ordinary state document",
        )
        _scan_ordinary_value(
            document,
            relative_path=relative_path,
            exact_digests=exact_digests,
            embedded_markers=embedded_markers,
        )

    return len(paths)


def verify_protected_state_backups(
    paths: RuntimePaths,
    *,
    expected_owner: tuple[int, int] | None = None,
) -> None:
    for directory, label in (
        (paths.security_state_dir, "security state directory"),
        (
            paths.device_credential_state_dir,
            "notification credential directory",
        ),
    ):
        _require_directory(
            directory,
            label,
            exact_posix_mode=0o700,
            expected_posix_owner=expected_owner,
        )

    for path, label in (
        (paths.security_state_file, "security state"),
        (
            paths.device_notification_credentials_file,
            "notification credential state",
        ),
    ):
        _require_private_file(
            path,
            label,
            expected_posix_owner=expected_owner,
        )
        _require_private_file(
            json_backup_path(path),
            f"{label} last-known-good copy",
            expected_posix_owner=expected_owner,
        )


def verify_retained_legacy_sources(
    *,
    service_environment: Mapping[str, str],
    service_payloads: Mapping[str, bytes],
    integration_document: Mapping,
    legacy_firebase_source: Path,
    legacy_security_source: Path,
    expected_owner: tuple[int, int] | None = None,
) -> int:
    retained = 0

    for credential_name, environment_name in TAPO_CREDENTIALS:
        legacy_value = str(
            service_environment.get(environment_name, "")
        ).strip()

        if not legacy_value:
            raise RuntimeError(
                f"Legacy rollback source is missing: {environment_name}"
            )

        try:
            protected_value = service_payloads[
                credential_name
            ].decode("utf-8").strip()
        except UnicodeDecodeError:
            raise RuntimeError(
                f"Credential is not valid UTF-8: {credential_name}"
            ) from None

        if not hmac.compare_digest(legacy_value, protected_value):
            raise RuntimeError(
                "Legacy rollback source does not match protected "
                f"credential: {environment_name}"
            )

        retained += 1

    legacy_integration_document = (
        integration_credential_document_from_environment(
            service_environment
        )
    )

    if legacy_integration_document != integration_document:
        raise RuntimeError(
            "Legacy integration rollback sources do not match the "
            "protected credential"
        )

    for field_name in INTEGRATION_FIELD_ENVIRONMENTS:
        if integration_document.get(field_name):
            retained += 1

    legacy_firebase_source = _absolute_path(
        legacy_firebase_source,
        "legacy Firebase source",
    )
    _require_private_file(
        legacy_firebase_source,
        "legacy Firebase source",
        expected_posix_owner=expected_owner,
    )
    legacy_firebase_payload = read_binary_credential_file(
        legacy_firebase_source,
        credential_name="legacy Firebase source",
    )

    if not hmac.compare_digest(
        legacy_firebase_payload,
        service_payloads[FIREBASE_CREDENTIAL_NAME],
    ):
        raise RuntimeError(
            "Legacy Firebase source does not match the protected "
            "credential"
        )

    retained += 1

    legacy_security_source = _absolute_path(
        legacy_security_source,
        "legacy security-state source",
    )
    _require_private_file(
        legacy_security_source,
        "legacy security-state source",
        expected_posix_owner=expected_owner,
    )
    _read_required_object(
        legacy_security_source,
        "legacy security-state source",
    )
    retained += 1
    return retained


def verify_removed_legacy_sources(
    *,
    service_environment: Mapping[str, str],
    legacy_firebase_source: Path,
    legacy_security_source: Path,
) -> None:
    legacy_environment_names = {
        *TAPO_LEGACY_ENVIRONMENTS,
        *INTEGRATION_FIELD_ENVIRONMENTS.values(),
        *DASHBOARD_LEGACY_ENVIRONMENTS,
    }
    remaining_environment = [
        name
        for name in legacy_environment_names
        if str(service_environment.get(name, "")).strip()
    ]
    if remaining_environment:
        raise RuntimeError(
            "Legacy credential environment remains active: "
            + ", ".join(sorted(remaining_environment))
        )

    for path, label in (
        (legacy_firebase_source, "legacy Firebase source"),
        (
            json_backup_path(legacy_firebase_source),
            "legacy Firebase recovery source",
        ),
        (legacy_security_source, "legacy security-state source"),
        (
            json_backup_path(legacy_security_source),
            "legacy security-state recovery source",
        ),
    ):
        path = _absolute_path(path, label)
        try:
            path.lstat()
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise RuntimeError(f"{label} could not be inspected") from exc
        raise RuntimeError(f"{label} is still present")


def verify_complete_cutover(
    *,
    source_credential_directory: Path,
    runtime_credential_directory: Path,
    data_root: Path,
    service_environment: Mapping[str, str],
    legacy_firebase_source: Path,
    legacy_security_source: Path,
    minimum_tokens: int = 0,
    manager_owner: tuple[int, int] | None = None,
    service_owner: tuple[int, int] | None = None,
    runtime_owners: frozenset[tuple[int, int]] | None = None,
    expect_legacy_sources: bool = True,
) -> VerificationSummary:
    data_root = _absolute_path(data_root, "Service data root")
    paths = RuntimePaths(
        source_root=SOURCE_ROOT,
        data_root=data_root,
    ).validate()
    service_payloads, integration_document = (
        verify_service_credential_copies(
            source_credential_directory,
            runtime_credential_directory,
            expected_source_owner=manager_owner,
            expected_runtime_owners=runtime_owners,
        )
    )
    counts = verify_auth_cutover(
        security_state_file=paths.security_state_file,
        notification_credentials_file=(
            paths.device_notification_credentials_file
        ),
        server_state_file=paths.server_state_file,
        minimum_tokens=minimum_tokens,
    )
    verify_protected_state_backups(
        paths,
        expected_owner=service_owner,
    )
    markers = protected_credential_markers(
        service_payloads,
        integration_document,
        paths.security_state_file,
        paths.device_notification_credentials_file,
    )
    ordinary_documents = scan_ordinary_state(
        paths.state_root,
        markers,
    )
    if expect_legacy_sources:
        retained = verify_retained_legacy_sources(
            service_environment=service_environment,
            service_payloads=service_payloads,
            integration_document=integration_document,
            legacy_firebase_source=legacy_firebase_source,
            legacy_security_source=legacy_security_source,
            expected_owner=service_owner,
        )
    else:
        verify_removed_legacy_sources(
            service_environment=service_environment,
            legacy_firebase_source=legacy_firebase_source,
            legacy_security_source=legacy_security_source,
        )
        retained = 0
    return VerificationSummary(
        service_credentials=len(service_payloads),
        dashboard_users=counts["dashboard_users"],
        dashboard_sessions=counts["dashboard_sessions"],
        device_keys=counts["device_keys"],
        device_enrollments=counts["device_enrollments"],
        notification_tokens=counts["notification_tokens"],
        ordinary_documents=ordinary_documents,
        retained_legacy_sources=retained,
    )


def main(argv=None) -> int:
    args = _parser().parse_args(argv)

    try:
        snapshot = inspect_active_service(
            args.service,
            data_root_override=args.data_root,
        )
        summary = verify_complete_cutover(
            source_credential_directory=args.credential_directory,
            runtime_credential_directory=(
                snapshot.runtime_credential_directory
            ),
            data_root=snapshot.data_root,
            service_environment=snapshot.environment,
            legacy_firebase_source=args.legacy_firebase_source,
            legacy_security_source=args.legacy_security_source,
            minimum_tokens=args.minimum_tokens,
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
            expect_legacy_sources=not args.expect_cleanup,
        )
    except RuntimeError as exc:
        print(f"SEC-004.5 complete verification stopped: {exc}")
        return 1

    print("SEC-004.5 complete credential cutover verification passed.")
    print(
        "service-restart-state: active "
        f"(runtime-credentials={summary.service_credentials})"
    )
    print(
        "protected-auth-state: ready "
        f"(users={summary.dashboard_users} "
        f"sessions={summary.dashboard_sessions} "
        f"device-keys={summary.device_keys} "
        f"enrollments={summary.device_enrollments} "
        f"notification-tokens={summary.notification_tokens})"
    )
    print(
        "ordinary-state: sanitized "
        f"(documents={summary.ordinary_documents})"
    )
    if args.expect_cleanup:
        print("legacy-rollback-sources: removed (sources=0)")
    else:
        print(
            "legacy-rollback-sources: retained "
            f"(sources={summary.retained_legacy_sources})"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Copy SEC-004 service credentials into protected service storage.

The tool never prints credential values. Its default mode is a read-only
preflight. Pass --copy only after preflight succeeds. Legacy environment and
source-file inputs are deliberately retained as rollback material.
"""

from __future__ import annotations

import argparse
import hmac
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
from typing import Mapping


SOURCE_ROOT = Path(__file__).resolve().parents[1]

if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from server_core.credentials import (  # noqa: E402
    CredentialMissingError,
    default_credential_directory,
    read_binary_credential_file,
)
from server_core.integration_credentials import (  # noqa: E402
    INTEGRATION_CREDENTIAL_NAME,
    LEGACY_INTEGRATION_CREDENTIAL_ENVIRONMENTS,
    integration_credential_document_from_environment,
)


TAPO_CREDENTIALS = (
    ("tapo-username", "TAPO_USERNAME"),
    ("tapo-password", "TAPO_PASSWORD"),
    ("tapo-camera-username", "TAPO_CAMERA_USERNAME"),
    ("tapo-camera-password", "TAPO_CAMERA_PASSWORD"),
)
FIREBASE_CREDENTIAL_NAME = "firebase-service-account.json"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Preflight or copy SEC-004 service credentials without "
            "displaying their values."
        ),
    )
    parser.add_argument(
        "--copy",
        action="store_true",
        help="perform the atomic copy; default is read-only preflight",
    )
    parser.add_argument(
        "--destination",
        type=Path,
        default=default_credential_directory(),
        help="protected credential directory",
    )
    parser.add_argument(
        "--firebase-source",
        type=Path,
        default=(
            SOURCE_ROOT
            / "subsystems"
            / "notifications"
            / FIREBASE_CREDENTIAL_NAME
        ),
        help="legacy Firebase service-account file",
    )
    parser.add_argument(
        "--service",
        help=(
            "read named legacy credentials from the running Linux systemd "
            "service without displaying them"
        ),
    )
    return parser


def _validate_destination_path(destination: Path) -> Path:
    destination = Path(destination).expanduser()

    if not destination.is_absolute():
        raise RuntimeError("Credential destination must be absolute")

    current = destination

    while current != current.parent:
        try:
            metadata = current.lstat()
        except FileNotFoundError:
            current = current.parent
            continue

        if stat.S_ISLNK(metadata.st_mode):
            raise RuntimeError(
                "Credential destination must not traverse a symbolic link"
            )

        current = current.parent

    if destination.exists() and not destination.is_dir():
        raise RuntimeError(
            "Credential destination must be a directory"
        )

    return destination


def _legacy_environment_payload(
    credential_name: str,
    environment_name: str,
    environment: Mapping[str, str],
) -> bytes:
    value = environment.get(environment_name)

    if value is None or value == "":
        raise RuntimeError(
            f"Legacy source is missing: {environment_name}"
        )

    value = value.strip()

    if not value or "\x00" in value or "\r" in value or "\n" in value:
        raise RuntimeError(
            f"Legacy source is not one text line: {environment_name}"
        )

    try:
        return value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise RuntimeError(
            f"Legacy source is not valid UTF-8: {environment_name}"
        ) from exc


def _running_service_environment(service_name: str) -> dict[str, str]:
    if os.name == "nt":
        raise RuntimeError(
            "Reading a running service environment is Linux-only"
        )

    name = str(service_name or "").strip()

    allowed_name_characters = (
        "abcdefghijklmnopqrstuvwxyz"
        "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        "0123456789@_.-"
    )

    if not name or any(ch not in allowed_name_characters for ch in name):
        raise RuntimeError("Systemd service name is invalid")

    try:
        result = subprocess.run(
            [
                "systemctl",
                "show",
                "--property=MainPID",
                "--value",
                name,
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError(
            "Could not resolve the running KotiBot service process"
        ) from exc

    pid_text = result.stdout.strip()

    if not pid_text.isdigit() or int(pid_text) <= 0:
        raise RuntimeError("KotiBot service is not running")

    environment_path = Path("/proc") / pid_text / "environ"

    try:
        payload = environment_path.read_bytes()
    except OSError as exc:
        raise RuntimeError(
            "Could not read the running KotiBot service environment"
        ) from exc

    if len(payload) > 1024 * 1024:
        raise RuntimeError("KotiBot service environment is unexpectedly large")

    required_names = {
        environment_name
        for _, environment_name in TAPO_CREDENTIALS
    }
    required_names.update(
        LEGACY_INTEGRATION_CREDENTIAL_ENVIRONMENTS
    )
    environment: dict[str, str] = {}

    for entry in payload.split(b"\x00"):
        raw_name, separator, raw_value = entry.partition(b"=")

        if not separator:
            continue

        try:
            decoded_name = raw_name.decode("utf-8")
        except UnicodeDecodeError:
            continue

        if decoded_name not in required_names:
            continue

        try:
            environment[decoded_name] = raw_value.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise RuntimeError(
                f"Legacy source is not valid UTF-8: {decoded_name}"
            ) from exc

    return environment


def _firebase_payload(source: Path) -> bytes:
    try:
        return read_binary_credential_file(
            source,
            credential_name=FIREBASE_CREDENTIAL_NAME,
        )
    except CredentialMissingError:
        raise RuntimeError(
            "Legacy Firebase service-account source is missing"
        ) from None


def _integration_credential_payload(
    environment: Mapping[str, str],
) -> bytes:
    document = integration_credential_document_from_environment(
        environment
    )
    return (
        json.dumps(document, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _existing_payload(path: Path, credential_name: str) -> bytes | None:
    try:
        path.lstat()
    except FileNotFoundError:
        return None

    return read_binary_credential_file(
        path,
        credential_name=credential_name,
    )


def _preflight_destination(
    destination: Path,
    credentials: dict[str, bytes],
) -> dict[str, str]:
    statuses: dict[str, str] = {}

    for credential_name, payload in credentials.items():
        target = destination / credential_name
        existing = _existing_payload(target, credential_name)

        if existing is None:
            statuses[credential_name] = "ready"
            continue

        if not hmac.compare_digest(existing, payload):
            raise RuntimeError(
                "Protected destination conflicts with legacy source: "
                f"{credential_name}"
            )

        statuses[credential_name] = "already-current"

    return statuses


def _prepare_destination(destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True, mode=0o700)

    if os.name != "nt":
        os.chmod(destination, 0o700)


def _write_atomic_private(path: Path, payload: bytes) -> None:
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary_path = Path(temporary_name)

    try:
        if os.name != "nt":
            os.fchmod(descriptor, 0o600)

        with os.fdopen(descriptor, "wb", closefd=True) as handle:
            descriptor = -1
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())

        os.replace(temporary_path, path)

        if os.name != "nt":
            os.chmod(path, 0o600)

        directory_flags = (
            os.O_RDONLY
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_CLOEXEC", 0)
        )
        directory_fd = os.open(path.parent, directory_flags)

        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if descriptor >= 0:
            os.close(descriptor)

        try:
            temporary_path.unlink()
        except FileNotFoundError:
            pass


def migrate(
    *,
    destination: Path,
    firebase_source: Path,
    copy: bool,
    environment: Mapping[str, str] | None = None,
) -> dict[str, str]:
    if os.name == "nt" and copy:
        raise RuntimeError(
            "This systemd service migration tool does not provision "
            "Windows ACLs; use read-only preflight on Windows"
        )

    destination = _validate_destination_path(destination)
    environment = os.environ if environment is None else environment
    credentials = {
        credential_name: _legacy_environment_payload(
            credential_name,
            environment_name,
            environment,
        )
        for credential_name, environment_name in TAPO_CREDENTIALS
    }
    credentials[FIREBASE_CREDENTIAL_NAME] = _firebase_payload(
        Path(firebase_source)
    )
    credentials[INTEGRATION_CREDENTIAL_NAME] = (
        _integration_credential_payload(environment)
    )
    statuses = _preflight_destination(destination, credentials)

    if not copy:
        return statuses

    _prepare_destination(destination)

    for credential_name, payload in credentials.items():
        if statuses[credential_name] == "already-current":
            continue

        _write_atomic_private(
            destination / credential_name,
            payload,
        )
        statuses[credential_name] = "copied"

    _preflight_destination(destination, credentials)
    return statuses


def main() -> int:
    args = _parser().parse_args()

    try:
        environment = (
            _running_service_environment(args.service)
            if args.service
            else os.environ
        )
        statuses = migrate(
            destination=args.destination,
            firebase_source=args.firebase_source,
            copy=args.copy,
            environment=environment,
        )
    except RuntimeError as exc:
        print(f"SEC-004 credential migration stopped: {exc}")
        return 1

    operation = "copy" if args.copy else "preflight"
    print(f"SEC-004 credential {operation} passed.")

    for credential_name, status in statuses.items():
        print(f"{credential_name}: {status}")

    if args.copy:
        print("Legacy sources retained for rollback; no credential was removed.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

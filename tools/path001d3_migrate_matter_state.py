#!/usr/bin/env python3
"""Copy legacy Matter state and its LKG outside the source tree safely."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import time


SOURCE_ROOT = Path(__file__).resolve().parents[1]

if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from server_core.io import json_backup_path  # noqa: E402
from server_core.paths import RuntimePaths  # noqa: E402
from tools.sec0045_verify_complete_credential_cutover import (  # noqa: E402
    inspect_active_service,
)


SERVICE_NAME = "kotibot"
LEGACY_STATE_FILE = (
    SOURCE_ROOT / "subsystems" / "matter" / "matter_state.json"
)
MAX_STATE_BYTES = 16 * 1024 * 1024
HANDOFF_MAX_AGE_SECONDS = 30 * 60


class MigrationError(RuntimeError):
    """A redacted, operator-actionable migration failure."""


@dataclass(frozen=True)
class StatePayload:
    payload: bytes
    size: int
    digest: str


@dataclass(frozen=True)
class MigrationResult:
    action: str
    source_files: int
    created_files: int
    existing_files: int
    total_bytes: int


def _default_handoff_file() -> Path:
    return (
        Path("/run")
        / "user"
        / str(os.getuid())
        / "kotibot"
        / "path001d3-matter-state-handoff.json"
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Prepare or perform the copy-first PATH-001D.3 Matter state "
            "relocation without deleting the source rollback pair."
        ),
    )
    parser.add_argument(
        "action",
        choices=("preflight", "copy"),
    )
    parser.add_argument(
        "--service",
        default=SERVICE_NAME,
    )
    parser.add_argument(
        "--handoff-file",
        type=Path,
        default=_default_handoff_file(),
    )
    return parser


def require_operator_identity() -> None:
    if os.name != "posix":
        raise MigrationError(
            "This migration checkpoint requires the Linux service host"
        )

    if os.geteuid() == 0:
        raise MigrationError(
            "Run this migration as the KotiBot service user, not as root"
        )


def _require_service_inactive(service_name: str) -> None:
    try:
        completed = subprocess.run(
            ("systemctl", "is-active", service_name),
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise MigrationError(
            "The KotiBot service state could not be verified"
        ) from exc

    if completed.stdout.strip() != "inactive":
        raise MigrationError(
            "The KotiBot service must be inactive for the copy"
        )


def _absolute(path: Path, label: str) -> Path:
    candidate = Path(path).expanduser()

    if not candidate.is_absolute():
        raise MigrationError(f"{label} must be absolute")

    return Path(os.path.abspath(candidate))


def _read_state_file(
    path: Path,
    label: str,
    *,
    private: bool,
) -> StatePayload:
    flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )

    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise MigrationError(f"{label} could not be opened safely") from exc

    try:
        before = os.fstat(descriptor)

        if not stat.S_ISREG(before.st_mode):
            raise MigrationError(f"{label} must be a regular file")

        if before.st_size < 1 or before.st_size > MAX_STATE_BYTES:
            raise MigrationError(f"{label} has an invalid size")

        if private:
            if before.st_uid != os.geteuid() or before.st_gid != os.getegid():
                raise MigrationError(f"{label} ownership is invalid")

            if stat.S_IMODE(before.st_mode) != 0o600:
                raise MigrationError(f"{label} permissions are not private")

        with os.fdopen(descriptor, "rb", closefd=True) as handle:
            descriptor = -1
            payload = handle.read(MAX_STATE_BYTES + 1)
            after = os.fstat(handle.fileno())
    finally:
        if descriptor >= 0:
            os.close(descriptor)

    stable_before = (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
        before.st_ctime_ns,
    )
    stable_after = (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
        after.st_ctime_ns,
    )

    if stable_before != stable_after or len(payload) != before.st_size:
        raise MigrationError(f"{label} changed while it was read")

    try:
        document = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise MigrationError(f"{label} is not valid JSON") from exc

    if not isinstance(document, dict):
        raise MigrationError(f"{label} must contain a JSON object")

    return StatePayload(
        payload=payload,
        size=len(payload),
        digest=hashlib.sha256(payload).hexdigest(),
    )


def _source_payloads(source_file: Path) -> tuple[StatePayload, StatePayload]:
    return (
        _read_state_file(
            source_file,
            "Legacy Matter primary state",
            private=False,
        ),
        _read_state_file(
            json_backup_path(source_file),
            "Legacy Matter LKG state",
            private=False,
        ),
    )


def _destination_paths(paths: RuntimePaths) -> tuple[Path, Path]:
    primary = paths.matter_state_file
    return primary, json_backup_path(primary)


def _same_payload(left: StatePayload, right: StatePayload) -> bool:
    return left.size == right.size and left.digest == right.digest


def _validate_existing_destinations(
    destinations: tuple[Path, Path],
    sources: tuple[StatePayload, StatePayload],
) -> int:
    existing = 0

    for destination, source in zip(destinations, sources):
        if not os.path.lexists(destination):
            continue

        payload = _read_state_file(
            destination,
            "External Matter state",
            private=True,
        )

        if not _same_payload(payload, source):
            raise MigrationError(
                "External Matter state differs from its legacy source"
            )

        existing += 1

    return existing


def _prepare_private_directory(path: Path) -> None:
    if not path.exists():
        try:
            path.mkdir(mode=0o700)
        except OSError as exc:
            raise MigrationError(
                "External Matter directory could not be created"
            ) from exc

    try:
        metadata = path.lstat()
    except OSError as exc:
        raise MigrationError(
            "External Matter directory could not be inspected"
        ) from exc

    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        raise MigrationError(
            "External Matter path must be a real directory"
        )

    if metadata.st_uid != os.geteuid() or metadata.st_gid != os.getegid():
        raise MigrationError("External Matter directory ownership is invalid")

    if stat.S_IMODE(metadata.st_mode) != 0o700:
        raise MigrationError(
            "External Matter directory permissions are not private"
        )


def _prepare_destination_directory(paths: RuntimePaths) -> None:
    for directory in (
        paths.data_root,
        paths.state_root,
        paths.matter_dir,
    ):
        _prepare_private_directory(Path(directory))


def _copy_new_file(payload: bytes, destination: Path) -> None:
    descriptor = -1
    temporary: Path | None = None

    try:
        descriptor, name = tempfile.mkstemp(
            prefix=".path001d3-matter-state-",
            dir=destination.parent,
        )
        temporary = Path(name)

        with os.fdopen(descriptor, "wb", closefd=True) as handle:
            descriptor = -1
            os.fchmod(handle.fileno(), 0o600)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())

        os.link(temporary, destination)
        temporary.unlink()
        temporary = None

        directory_fd = os.open(
            destination.parent,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
        )
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except OSError as exc:
        raise MigrationError(
            "External Matter state could not be copied safely"
        ) from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)

        if temporary is not None:
            try:
                temporary.unlink()
            except OSError:
                pass


def _write_handoff(path: Path, document: dict) -> None:
    path = _absolute(path, "Migration handoff")
    _prepare_private_directory(path.parent)
    encoded = (
        json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")
    descriptor = -1
    temporary: Path | None = None

    try:
        descriptor, name = tempfile.mkstemp(
            prefix=".path001d3-handoff-",
            dir=path.parent,
        )
        temporary = Path(name)

        with os.fdopen(descriptor, "wb", closefd=True) as handle:
            descriptor = -1
            os.fchmod(handle.fileno(), 0o600)
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())

        os.replace(temporary, path)
        temporary = None
    except OSError as exc:
        raise MigrationError("Migration handoff could not be written") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)

        if temporary is not None:
            try:
                temporary.unlink()
            except OSError:
                pass


def _read_handoff(path: Path, service_name: str) -> dict:
    path = _absolute(path, "Migration handoff")
    payload = _read_state_file(
        path,
        "Migration handoff",
        private=True,
    )

    try:
        document = json.loads(payload.payload.decode("utf-8"))
        created_at = int(document.get("created_at") or 0)
    except (UnicodeDecodeError, ValueError, TypeError, AttributeError) as exc:
        raise MigrationError("Migration handoff is malformed") from exc

    now = int(time.time())

    if (
        document.get("schema") != 1
        or document.get("service") != service_name
        or document.get("source_root") != str(SOURCE_ROOT)
        or created_at < now - HANDOFF_MAX_AGE_SECONDS
        or created_at > now + 60
    ):
        raise MigrationError("Migration handoff is invalid or stale")

    return document


def _paths_for_data_root(data_root: Path) -> RuntimePaths:
    return RuntimePaths(
        source_root=SOURCE_ROOT,
        data_root=_absolute(data_root, "Service data root"),
    ).validate()


def run_preflight(args) -> MigrationResult:
    require_operator_identity()

    try:
        snapshot = inspect_active_service(args.service)
    except RuntimeError as exc:
        raise MigrationError(str(exc)) from exc

    if snapshot.process_user_id != os.geteuid():
        raise MigrationError(
            "Run this migration as the active KotiBot service identity"
        )

    paths = _paths_for_data_root(snapshot.data_root)
    sources = _source_payloads(LEGACY_STATE_FILE)
    destinations = _destination_paths(paths)
    existing = _validate_existing_destinations(destinations, sources)
    _write_handoff(
        args.handoff_file,
        {
            "schema": 1,
            "service": args.service,
            "source_root": str(SOURCE_ROOT),
            "data_root": str(paths.data_root),
            "created_at": int(time.time()),
            "source": [
                {"size": item.size, "digest": item.digest}
                for item in sources
            ],
        },
    )

    return MigrationResult(
        action="preflight",
        source_files=2,
        created_files=0,
        existing_files=existing,
        total_bytes=sum(item.size for item in sources),
    )


def run_copy(args) -> MigrationResult:
    require_operator_identity()
    _require_service_inactive(args.service)
    handoff = _read_handoff(args.handoff_file, args.service)
    paths = _paths_for_data_root(Path(str(handoff.get("data_root") or "")))
    sources = _source_payloads(LEGACY_STATE_FILE)
    recorded_sources = handoff.get("source")

    if not isinstance(recorded_sources, list) or len(recorded_sources) != 2:
        raise MigrationError("Migration handoff is malformed")

    for source, recorded in zip(sources, recorded_sources):
        if (
            not isinstance(recorded, dict)
            or recorded.get("size") != source.size
            or recorded.get("digest") != source.digest
        ):
            raise MigrationError(
                "Legacy Matter state changed after preflight"
            )

    destinations = _destination_paths(paths)
    existing = _validate_existing_destinations(destinations, sources)
    _prepare_destination_directory(paths)
    created = 0

    for destination, source in zip(destinations, sources):
        if os.path.lexists(destination):
            continue

        _copy_new_file(source.payload, destination)
        created += 1

    if _validate_existing_destinations(destinations, sources) != 2:
        raise MigrationError("External Matter state validation failed")

    final_sources = _source_payloads(LEGACY_STATE_FILE)

    if any(
        not _same_payload(before, after)
        for before, after in zip(sources, final_sources)
    ):
        raise MigrationError("Legacy Matter state changed during the copy")

    try:
        Path(args.handoff_file).unlink()
    except OSError as exc:
        raise MigrationError("Migration handoff could not be removed") from exc

    return MigrationResult(
        action="copy",
        source_files=2,
        created_files=created,
        existing_files=existing,
        total_bytes=sum(item.size for item in sources),
    )


def _print_result(result: MigrationResult) -> None:
    print("PATH-001D.3 MATTER STATE RELOCATION")
    print("Result: " + ("READY" if result.action == "preflight" else "COPIED"))
    print("Privacy: no Matter state values or identifiers were displayed.")
    print(f"Legacy state files validated: {result.source_files}")
    print(f"State bytes validated: {result.total_bytes}")
    print(f"External state files created: {result.created_files}")
    print(f"Existing external files revalidated: {result.existing_files}")
    print("Legacy rollback pair preserved: YES")
    print("Legacy cleanup performed: NO")


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)

    try:
        result = (
            run_preflight(args)
            if args.action == "preflight"
            else run_copy(args)
        )
    except (MigrationError, RuntimeError) as exc:
        print(f"PATH-001D.3 stopped: {exc}")
        print("Privacy: no Matter state values or identifiers were displayed.")
        print("Legacy cleanup performed: NO")
        return 1
    except OSError:
        print("PATH-001D.3 stopped: protected migration I/O failed")
        print("Privacy: no Matter state values or identifiers were displayed.")
        print("Legacy cleanup performed: NO")
        return 1

    _print_result(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

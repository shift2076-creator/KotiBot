#!/usr/bin/env python3
"""Copy legacy recordings into the protected media root without cleanup."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile


SOURCE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOURCE_ROOT))

from server_core.paths import build_runtime_paths  # noqa: E402


LEGACY_RELATIVE_PATH = Path("subsystems/video/videos")
SERVICE_NAME = "kotibot.service"
STAGING_PREFIX = ".path001c7-copy-"


class MigrationError(RuntimeError):
    """A redacted, operator-actionable migration failure."""


@dataclass(frozen=True)
class MediaEntry:
    relative_path: str
    size: int
    sha256: str
    mtime_ns: int


@dataclass(frozen=True)
class MigrationResult:
    file_count: int
    total_bytes: int
    newly_copied_files: int
    previously_verified_files: int
    performed_copy: bool


def require_service_inactive(
    service_name: str = SERVICE_NAME,
) -> None:
    try:
        result = subprocess.run(
            ("systemctl", "is-active", service_name),
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise MigrationError(
            "The KotiBot service state could not be verified."
        ) from error

    if result.stdout.strip() != "inactive":
        raise MigrationError(
            "The KotiBot service must be stopped before recordings "
            "are copied."
        )


def require_operator_identity() -> None:
    if os.name != "posix":
        raise MigrationError(
            "This migration checkpoint requires the Linux service host."
        )

    if os.geteuid() == 0:
        raise MigrationError(
            "Run this migration as the KotiBot service user, not as root."
        )


def _path_exists(path: Path) -> bool:
    return os.path.lexists(os.fspath(path))


def _hash_regular_file(path: Path) -> MediaEntry:
    try:
        before = path.lstat()
    except OSError as error:
        raise MigrationError(
            "Recording metadata could not be read."
        ) from error

    if not stat.S_ISREG(before.st_mode):
        raise MigrationError(
            "Recording storage contains an unsupported file type."
        )

    digest = hashlib.sha256()

    try:
        with path.open("rb") as handle:
            while True:
                chunk = handle.read(1024 * 1024)

                if not chunk:
                    break

                digest.update(chunk)
    except OSError as error:
        raise MigrationError(
            "A recording could not be read completely."
        ) from error

    try:
        after = path.lstat()
    except OSError as error:
        raise MigrationError(
            "A recording changed while it was read."
        ) from error

    stable_before = (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
        stat.S_IFMT(before.st_mode),
    )
    stable_after = (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
        stat.S_IFMT(after.st_mode),
    )

    if stable_before != stable_after:
        raise MigrationError(
            "A recording changed while it was read."
        )

    return MediaEntry(
        relative_path="",
        size=before.st_size,
        sha256=digest.hexdigest(),
        mtime_ns=before.st_mtime_ns,
    )


def _validate_private_metadata(path: Path, *, directory: bool) -> None:
    try:
        metadata = path.lstat()
    except OSError as error:
        raise MigrationError(
            "Protected media metadata could not be read."
        ) from error

    expected_type = stat.S_ISDIR if directory else stat.S_ISREG

    if not expected_type(metadata.st_mode):
        raise MigrationError(
            "Protected media storage contains an unsupported file type."
        )

    if os.name != "nt":
        if metadata.st_uid != os.geteuid() or metadata.st_gid != os.getegid():
            raise MigrationError(
                "Protected media storage has unexpected ownership."
            )

        expected_mode = 0o700 if directory else 0o600

        if stat.S_IMODE(metadata.st_mode) != expected_mode:
            raise MigrationError(
                "Protected media permissions are not private."
            )


def _media_manifest(
    directory: Path,
    *,
    require_private: bool,
) -> tuple[MediaEntry, ...]:
    if not _path_exists(directory):
        return ()

    try:
        root_metadata = directory.lstat()
    except OSError as error:
        raise MigrationError(
            "Recording directory metadata could not be read."
        ) from error

    if stat.S_ISLNK(root_metadata.st_mode):
        raise MigrationError(
            "Recording directories must not be symlinks."
        )

    if not stat.S_ISDIR(root_metadata.st_mode):
        raise MigrationError(
            "Recording storage must be a directory."
        )

    if require_private:
        _validate_private_metadata(directory, directory=True)

    entries = []

    try:
        walker = os.walk(directory, topdown=True, followlinks=False)

        for root_name, directory_names, file_names in walker:
            root = Path(root_name)

            for name in sorted(directory_names):
                child = root / name
                metadata = child.lstat()

                if stat.S_ISLNK(metadata.st_mode):
                    raise MigrationError(
                        "Recording directories must not be symlinks."
                    )

                if not stat.S_ISDIR(metadata.st_mode):
                    raise MigrationError(
                        "Recording storage contains an unsupported file type."
                    )

                if require_private:
                    _validate_private_metadata(child, directory=True)

            for name in sorted(file_names):
                path = root / name
                entry = _hash_regular_file(path)

                if require_private:
                    _validate_private_metadata(path, directory=False)

                entries.append(
                    MediaEntry(
                        relative_path=(
                            path.relative_to(directory).as_posix()
                        ),
                        size=entry.size,
                        sha256=entry.sha256,
                        mtime_ns=entry.mtime_ns,
                    )
                )
    except MigrationError:
        raise
    except OSError as error:
        raise MigrationError(
            "Recording storage could not be enumerated."
        ) from error

    return tuple(
        sorted(entries, key=lambda entry: entry.relative_path)
    )


def _prepare_private_directory(directory: Path) -> None:
    try:
        directory.mkdir(
            parents=True,
            exist_ok=True,
            mode=0o700,
        )

        if os.name != "nt":
            os.chmod(directory, 0o700)
    except OSError as error:
        raise MigrationError(
            "Protected media directories could not be prepared."
        ) from error

    _validate_private_metadata(directory, directory=True)


def _prepare_destination_parent(root: Path, parent: Path) -> None:
    _prepare_private_directory(root)

    relative_parent = parent.relative_to(root)
    current = root

    for part in relative_parent.parts:
        current = current / part
        _prepare_private_directory(current)


def _copy_recording(
    source: Path,
    destination: Path,
    entry: MediaEntry,
) -> None:
    descriptor = None
    staging_path = None

    try:
        descriptor, staging_name = tempfile.mkstemp(
            prefix=STAGING_PREFIX,
            dir=destination.parent,
        )
        staging_path = Path(staging_name)

        with source.open("rb") as source_handle:
            with os.fdopen(descriptor, "wb") as destination_handle:
                descriptor = None
                shutil.copyfileobj(
                    source_handle,
                    destination_handle,
                    length=1024 * 1024,
                )
                destination_handle.flush()
                os.fsync(destination_handle.fileno())

        if os.name != "nt":
            os.chmod(staging_path, 0o600)

        os.utime(
            staging_path,
            ns=(entry.mtime_ns, entry.mtime_ns),
        )
        os.link(staging_path, destination)
        staging_path.unlink()
        staging_path = None
    except OSError as error:
        raise MigrationError(
            "A recording could not be copied safely."
        ) from error
    finally:
        if descriptor is not None:
            os.close(descriptor)

        if staging_path is not None:
            try:
                staging_path.unlink()
            except OSError:
                pass


def _same_payload(left: MediaEntry, right: MediaEntry) -> bool:
    return (
        left.size == right.size
        and left.sha256 == right.sha256
        and left.mtime_ns == right.mtime_ns
    )


def migrate_recordings(*, copy_requested: bool) -> MigrationResult:
    require_operator_identity()
    require_service_inactive()

    paths = build_runtime_paths(SOURCE_ROOT)
    legacy_root = SOURCE_ROOT / LEGACY_RELATIVE_PATH
    destination_root = Path(paths.recording_dir)
    source_manifest = _media_manifest(
        legacy_root,
        require_private=False,
    )
    destination_manifest = _media_manifest(
        destination_root,
        require_private=True,
    )
    destination_by_path = {
        entry.relative_path: entry
        for entry in destination_manifest
    }
    newly_copied = 0
    previously_verified = 0

    if copy_requested:
        _prepare_private_directory(destination_root)

    for source_entry in source_manifest:
        destination_entry = destination_by_path.get(
            source_entry.relative_path
        )

        if destination_entry is None and copy_requested:
            source = legacy_root / source_entry.relative_path
            destination = (
                destination_root / source_entry.relative_path
            )
            _prepare_destination_parent(
                destination_root,
                destination.parent,
            )
            _copy_recording(
                source,
                destination,
                source_entry,
            )
            destination_entry = _hash_regular_file(destination)
            _validate_private_metadata(
                destination,
                directory=False,
            )
            newly_copied += 1

        if destination_entry is None:
            continue

        if not _same_payload(destination_entry, source_entry):
            raise MigrationError(
                "A protected recording differs from its legacy source."
            )

        if source_entry.relative_path in destination_by_path:
            previously_verified += 1

    if copy_requested:
        copied_manifest = _media_manifest(
            destination_root,
            require_private=True,
        )
        copied_by_path = {
            entry.relative_path: entry
            for entry in copied_manifest
        }

        for source_entry in source_manifest:
            destination_entry = copied_by_path.get(
                source_entry.relative_path
            )

            if (
                destination_entry is None
                or not _same_payload(destination_entry, source_entry)
            ):
                raise MigrationError(
                    "Protected recording validation failed."
                )

        if _media_manifest(
            legacy_root,
            require_private=False,
        ) != source_manifest:
            raise MigrationError(
                "Legacy recording storage changed during migration."
            )

    return MigrationResult(
        file_count=len(source_manifest),
        total_bytes=sum(entry.size for entry in source_manifest),
        newly_copied_files=newly_copied,
        previously_verified_files=previously_verified,
        performed_copy=copy_requested,
    )


def _print_result(result: MigrationResult) -> None:
    if result.performed_copy:
        print("PATH-001C.7 recording copy and validation passed.")
    else:
        print("PATH-001C.7 recording preflight passed.")

    print(f"Legacy recordings discovered: {result.file_count}")
    print(f"Bytes validated: {result.total_bytes}")

    if result.performed_copy:
        print(
            "Protected copies created: "
            f"{result.newly_copied_files}"
        )
        print(
            "Existing protected copies revalidated: "
            f"{result.previously_verified_files}"
        )
        print("Rollback source revalidated: yes")
    else:
        print("Copy requested: no")
        print(
            "Existing protected copies revalidated: "
            f"{result.previously_verified_files}"
        )

    print("Legacy source changed: no")
    print("Retention policy changed: no")
    print("Legacy cleanup authorized: no")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Copy and validate legacy Android and Tapo recordings in the "
            "protected media root without deleting the legacy tree."
        )
    )
    parser.add_argument(
        "--copy",
        action="store_true",
        help=(
            "Copy missing legacy recordings into the protected media root "
            "and validate every result."
        ),
    )
    arguments = parser.parse_args()

    try:
        result = migrate_recordings(
            copy_requested=arguments.copy,
        )
    except MigrationError as error:
        print(f"PATH-001C.7 stopped: {error}", file=sys.stderr)
        return 1
    except Exception:
        print(
            "PATH-001C.7 stopped: unexpected migration failure.",
            file=sys.stderr,
        )
        return 1

    _print_result(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

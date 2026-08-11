#!/usr/bin/env python3
"""Copy served Android APKs outside the source tree without cleanup."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import shutil
import stat
import sys
import tempfile


SOURCE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOURCE_ROOT))

from server_core.paths import build_runtime_paths  # noqa: E402


LEGACY_RELATIVE_PATH = Path("subsystems/file-server/get-app")
STAGING_PREFIX = ".path001c9-copy-"


class MigrationError(RuntimeError):
    """A redacted, operator-actionable migration failure."""


@dataclass(frozen=True)
class PackageEntry:
    name: str
    size: int
    sha256: str


@dataclass(frozen=True)
class MigrationResult:
    package_count: int
    total_bytes: int
    newly_copied_packages: int
    previously_verified_packages: int
    performed_copy: bool


def _path_exists(path: Path) -> bool:
    return os.path.lexists(os.fspath(path))


def _hash_regular_file(path: Path) -> tuple[int, str]:
    try:
        before = path.lstat()
    except OSError as error:
        raise MigrationError(
            "Android package metadata could not be read."
        ) from error

    if not stat.S_ISREG(before.st_mode):
        raise MigrationError(
            "Android package storage contains an unsupported file type."
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
            "An Android package could not be read completely."
        ) from error

    try:
        after = path.lstat()
    except OSError as error:
        raise MigrationError(
            "An Android package changed while it was read."
        ) from error

    stable_fields = (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
        stat.S_IFMT(before.st_mode),
    )
    after_fields = (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
        stat.S_IFMT(after.st_mode),
    )

    if stable_fields != after_fields:
        raise MigrationError(
            "An Android package changed while it was read."
        )

    return before.st_size, digest.hexdigest()


def _package_manifest(directory: Path) -> tuple[PackageEntry, ...]:
    if not _path_exists(directory):
        return ()

    try:
        metadata = directory.lstat()
    except OSError as error:
        raise MigrationError(
            "Android package directory metadata could not be read."
        ) from error

    if stat.S_ISLNK(metadata.st_mode):
        raise MigrationError(
            "Android package directories must not be symlinks."
        )

    if not stat.S_ISDIR(metadata.st_mode):
        raise MigrationError(
            "Android package storage must be a directory."
        )

    try:
        candidates = sorted(
            (
                path
                for path in directory.iterdir()
                if path.name.endswith(".apk")
            ),
            key=lambda path: path.name,
        )
    except OSError as error:
        raise MigrationError(
            "Android package storage could not be enumerated."
        ) from error

    entries = []

    for path in candidates:
        size, digest = _hash_regular_file(path)
        entries.append(
            PackageEntry(
                name=path.name,
                size=size,
                sha256=digest,
            )
        )

    return tuple(entries)


def _validate_private_directory(directory: Path) -> None:
    try:
        metadata = directory.lstat()
    except OSError as error:
        raise MigrationError(
            "External package directory metadata could not be read."
        ) from error

    if stat.S_ISLNK(metadata.st_mode):
        raise MigrationError(
            "External package directories must not be symlinks."
        )

    if not stat.S_ISDIR(metadata.st_mode):
        raise MigrationError(
            "External package storage must be a directory."
        )

    if os.name != "nt":
        if metadata.st_uid != os.geteuid() or metadata.st_gid != os.getegid():
            raise MigrationError(
                "External package directories have unexpected ownership."
            )

        if stat.S_IMODE(metadata.st_mode) != 0o700:
            raise MigrationError(
                "External package directory permissions are not private."
            )


def _validate_private_package(path: Path) -> PackageEntry:
    size, digest = _hash_regular_file(path)

    if os.name != "nt":
        metadata = path.lstat()

        if metadata.st_uid != os.geteuid() or metadata.st_gid != os.getegid():
            raise MigrationError(
                "External Android packages have unexpected ownership."
            )

        if stat.S_IMODE(metadata.st_mode) != 0o600:
            raise MigrationError(
                "External Android package permissions are not private."
            )

    return PackageEntry(
        name=path.name,
        size=size,
        sha256=digest,
    )


def _create_private_directories(*directories: Path) -> None:
    for directory in directories:
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
                "External package directories could not be prepared."
            ) from error

        _validate_private_directory(directory)


def _copy_package(source: Path, destination: Path) -> None:
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

        os.link(staging_path, destination)
        staging_path.unlink()
        staging_path = None
    except OSError as error:
        raise MigrationError(
            "An Android package could not be copied safely."
        ) from error
    finally:
        if descriptor is not None:
            os.close(descriptor)

        if staging_path is not None:
            try:
                staging_path.unlink()
            except FileNotFoundError:
                pass
            except OSError:
                pass


def migrate_android_packages(*, copy_requested: bool) -> MigrationResult:
    paths = build_runtime_paths(SOURCE_ROOT)
    legacy_directory = SOURCE_ROOT / LEGACY_RELATIVE_PATH
    package_root = Path(paths.package_root)
    destination_directory = paths.android_package_dir
    source_manifest = _package_manifest(legacy_directory)
    source_by_name = {
        entry.name: entry
        for entry in source_manifest
    }
    newly_copied = 0
    previously_verified = 0

    if _path_exists(package_root):
        _validate_private_directory(package_root)

    if _path_exists(destination_directory):
        _validate_private_directory(destination_directory)

        for destination_entry in _package_manifest(
            destination_directory
        ):
            _validate_private_package(
                destination_directory / destination_entry.name
            )

    for name, source_entry in source_by_name.items():
        destination = destination_directory / name
        copied_this_package = False

        if not _path_exists(destination):
            if not copy_requested:
                continue

            _create_private_directories(
                package_root,
                destination_directory,
            )
            _copy_package(legacy_directory / name, destination)
            newly_copied += 1
            copied_this_package = True

        destination_entry = _validate_private_package(destination)

        if destination_entry != source_entry:
            raise MigrationError(
                "An external Android package differs from its legacy source."
            )

        if not copied_this_package:
            previously_verified += 1

    if copy_requested:
        _create_private_directories(
            package_root,
            destination_directory,
        )

        for source_entry in source_manifest:
            destination_entry = _validate_private_package(
                destination_directory / source_entry.name
            )

            if destination_entry != source_entry:
                raise MigrationError(
                    "Android package copy validation failed."
                )

    return MigrationResult(
        package_count=len(source_manifest),
        total_bytes=sum(entry.size for entry in source_manifest),
        newly_copied_packages=newly_copied,
        previously_verified_packages=previously_verified,
        performed_copy=copy_requested,
    )


def _print_result(result: MigrationResult) -> None:
    if result.performed_copy:
        print("PATH-001C.9 package copy and validation passed.")
    else:
        print("PATH-001C.9 preflight passed.")

    print(f"Legacy APKs discovered: {result.package_count}")
    print(f"Bytes validated: {result.total_bytes}")

    if result.performed_copy:
        print(
            "External copies created: "
            f"{result.newly_copied_packages}"
        )
        print(
            "Existing external copies revalidated: "
            f"{result.previously_verified_packages}"
        )
    else:
        print("Copy requested: no")

    print("Legacy source changed: no")
    print("Legacy cleanup authorized: no")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Copy served Android APKs to the external package root "
            "without deleting legacy packages."
        )
    )
    parser.add_argument(
        "--copy",
        action="store_true",
        help="Copy and validate legacy APKs in external package storage.",
    )
    arguments = parser.parse_args()

    try:
        result = migrate_android_packages(
            copy_requested=arguments.copy,
        )
    except MigrationError as error:
        print(f"PATH-001C.9 stopped: {error}", file=sys.stderr)
        return 1
    except Exception:
        print(
            "PATH-001C.9 stopped: unexpected migration failure.",
            file=sys.stderr,
        )
        return 1

    _print_result(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

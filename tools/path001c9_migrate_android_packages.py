#!/usr/bin/env python3
"""Build the canonical external Android APK layout without cleanup."""

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
CANONICAL_LAYOUT = (
    ("KotiBot-Monitor", "monitor", ("KotiBot-Monitor", "KotiBot-Home")),
    ("KotiBot-Control", "control", ("KotiBot-Control", "KotiBot-Key")),
)


class MigrationError(RuntimeError):
    """A redacted, operator-actionable migration failure."""


@dataclass(frozen=True)
class PackageEntry:
    name: str
    size: int
    sha256: str


@dataclass(frozen=True)
class PackagePlan:
    source_name: str
    destination_name: str
    kind: str
    size: int
    sha256: str


@dataclass(frozen=True)
class MigrationResult:
    package_count: int
    total_bytes: int
    newly_copied_packages: int
    previously_verified_packages: int
    flat_rollback_packages: int
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


def _canonical_destination(name: str) -> tuple[str, str]:
    if not name.endswith(".apk"):
        raise MigrationError(
            "Legacy Android package naming is unsupported."
        )

    stem = name[:-4]
    lowered = stem.lower()

    for canonical_prefix, kind, accepted_prefixes in CANONICAL_LAYOUT:
        for accepted_prefix in accepted_prefixes:
            prefix = accepted_prefix.lower()

            if lowered == prefix:
                suffix = ""
            elif lowered.startswith(prefix + "."):
                suffix = stem[len(accepted_prefix):]
            elif lowered.startswith(prefix + "-"):
                suffix = stem[len(accepted_prefix):]
            elif lowered.startswith(prefix + "_"):
                suffix = stem[len(accepted_prefix):]
            else:
                continue

            return kind, f"{canonical_prefix}{suffix}.apk"

    raise MigrationError(
        "Legacy Android package naming is unsupported."
    )


def _package_plans(
    source_manifest: tuple[PackageEntry, ...],
) -> tuple[PackagePlan, ...]:
    plans = []
    destinations = set()

    for source_entry in source_manifest:
        kind, destination_name = _canonical_destination(
            source_entry.name
        )
        destination_key = (kind, destination_name.lower())

        if destination_key in destinations:
            raise MigrationError(
                "Legacy Android packages map to the same canonical name."
            )

        destinations.add(destination_key)
        plans.append(
            PackagePlan(
                source_name=source_entry.name,
                destination_name=destination_name,
                kind=kind,
                size=source_entry.size,
                sha256=source_entry.sha256,
            )
        )

    return tuple(plans)


def _same_payload(entry: PackageEntry, plan: PackagePlan) -> bool:
    return (
        entry.size == plan.size
        and entry.sha256 == plan.sha256
    )


def _previous_flat_directory(paths) -> Path:
    configured = str(
        os.environ.get("KOTIBOT_PACKAGE_DIR", "")
    ).strip()

    if configured:
        return (
            Path(configured)
            .expanduser()
            .resolve(strict=False)
            / "android"
        )

    return paths.data_root / "packages" / "android"


def _validate_flat_rollback(
    directory: Path,
    source_manifest: tuple[PackageEntry, ...],
) -> int:
    if not _path_exists(directory):
        return 0

    if _path_exists(directory.parent):
        _validate_private_directory(directory.parent)

    _validate_private_directory(directory)
    rollback_manifest = _package_manifest(directory)
    source_by_name = {
        entry.name: entry
        for entry in source_manifest
    }

    for rollback_entry in rollback_manifest:
        validated = _validate_private_package(
            directory / rollback_entry.name
        )
        source_entry = source_by_name.get(rollback_entry.name)

        if source_entry is not None and validated != source_entry:
            raise MigrationError(
                "A flat rollback package differs from its legacy source."
            )

    return len(rollback_manifest)


def _validate_destination_directory(directory: Path) -> None:
    if not _path_exists(directory):
        return

    _validate_private_directory(directory)

    for entry in _package_manifest(directory):
        _validate_private_package(directory / entry.name)


def migrate_android_packages(*, copy_requested: bool) -> MigrationResult:
    paths = build_runtime_paths(SOURCE_ROOT)
    legacy_directory = SOURCE_ROOT / LEGACY_RELATIVE_PATH
    package_root = Path(paths.package_root)
    destination_directories = {
        "control": paths.controller_apk_dir,
        "monitor": paths.monitor_apk_dir,
    }
    source_manifest = _package_manifest(legacy_directory)
    plans = _package_plans(source_manifest)
    flat_rollback_packages = _validate_flat_rollback(
        _previous_flat_directory(paths),
        source_manifest,
    )
    newly_copied = 0
    previously_verified = 0

    if _path_exists(package_root):
        _validate_private_directory(package_root)

    for directory in destination_directories.values():
        _validate_destination_directory(directory)

    for plan in plans:
        destination_directory = destination_directories[plan.kind]
        destination = (
            destination_directory / plan.destination_name
        )
        copied_this_package = False

        if not _path_exists(destination):
            if not copy_requested:
                continue

            _create_private_directories(
                package_root,
                destination_directory,
            )
            _copy_package(
                legacy_directory / plan.source_name,
                destination,
            )
            newly_copied += 1
            copied_this_package = True

        destination_entry = _validate_private_package(destination)

        if not _same_payload(destination_entry, plan):
            raise MigrationError(
                "A canonical Android package differs from its legacy source."
            )

        if not copied_this_package:
            previously_verified += 1

    if copy_requested:
        _create_private_directories(
            package_root,
            paths.controller_apk_dir,
            paths.monitor_apk_dir,
        )

        for plan in plans:
            destination = (
                destination_directories[plan.kind]
                / plan.destination_name
            )
            destination_entry = _validate_private_package(
                destination
            )

            if not _same_payload(destination_entry, plan):
                raise MigrationError(
                    "Canonical Android package validation failed."
                )

    return MigrationResult(
        package_count=len(source_manifest),
        total_bytes=sum(
            entry.size
            for entry in source_manifest
        ),
        newly_copied_packages=newly_copied,
        previously_verified_packages=previously_verified,
        flat_rollback_packages=flat_rollback_packages,
        performed_copy=copy_requested,
    )


def _print_result(result: MigrationResult) -> None:
    if result.performed_copy:
        print("PATH-001C.9 canonical package layout passed.")
    else:
        print("PATH-001C.9 canonical-layout preflight passed.")

    print(f"Legacy APKs discovered: {result.package_count}")
    print(f"Bytes validated: {result.total_bytes}")
    print(
        "Flat rollback copies preserved: "
        f"{result.flat_rollback_packages}"
    )

    if result.performed_copy:
        print(
            "Canonical copies created: "
            f"{result.newly_copied_packages}"
        )
        print(
            "Existing canonical copies revalidated: "
            f"{result.previously_verified_packages}"
        )
    else:
        print("Copy requested: no")
        print(
            "Existing canonical copies revalidated: "
            f"{result.previously_verified_packages}"
        )

    print("Legacy source changed: no")
    print("Flat rollback changed: no")
    print("Legacy cleanup authorized: no")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Build and validate the canonical Monitor and Control APK "
            "directories without deleting legacy or flat rollback copies."
        )
    )
    parser.add_argument(
        "--copy",
        action="store_true",
        help=(
            "Copy legacy APKs into the canonical external package layout "
            "and validate every result."
        ),
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

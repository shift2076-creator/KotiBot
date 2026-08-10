#!/usr/bin/env python3
"""Copy Matter controller identity into protected storage without cutover."""

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
from typing import Callable


SOURCE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOURCE_ROOT))

from server_core.paths import build_runtime_paths  # noqa: E402


SERVICE_NAME = "kotibot.service"
ACTIVE_SOURCE_NAME = "chip_tool_storage"
CONTROLLER_DESTINATION_NAME = "controller"
ROLLBACK_ROOT_NAME = "rollback"
BAD_PREFIX = "chip_tool_storage.bad-"
REPAIR_PREFIX = ".chip_tool_storage.repair-"
STAGING_PREFIX = ".path001c4-copy-"


class MigrationError(RuntimeError):
    """A redacted, operator-actionable migration failure."""


@dataclass(frozen=True)
class ManifestEntry:
    relative_path: str
    kind: str
    size: int
    sha256: str


@dataclass(frozen=True)
class TreeManifest:
    entries: tuple[ManifestEntry, ...]

    @property
    def file_count(self) -> int:
        return sum(entry.kind == "file" for entry in self.entries)

    @property
    def total_bytes(self) -> int:
        return sum(
            entry.size
            for entry in self.entries
            if entry.kind == "file"
        )


@dataclass(frozen=True)
class TreeCopyPlan:
    source: Path
    destination: Path
    rollback: Path
    require_regular_file: bool


@dataclass(frozen=True)
class MigrationResult:
    tree_count: int
    file_count: int
    total_bytes: int
    newly_copied_trees: int
    previously_verified_trees: int
    performed_copy: bool


def _path_exists(path: Path) -> bool:
    return os.path.lexists(os.fspath(path))


def _hash_regular_file(path: Path) -> tuple[int, str]:
    try:
        before = path.lstat()
    except OSError as error:
        raise MigrationError(
            "Matter controller storage metadata could not be read."
        ) from error

    if not stat.S_ISREG(before.st_mode):
        raise MigrationError(
            "Matter controller storage contains an unsupported file type."
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
            "Matter controller storage could not be read completely."
        ) from error

    try:
        after = path.lstat()
    except OSError as error:
        raise MigrationError(
            "Matter controller storage changed while it was read."
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
            "Matter controller storage changed while it was read."
        )

    return before.st_size, digest.hexdigest()


def _tree_manifest(
    root: Path,
    *,
    require_regular_file: bool,
) -> TreeManifest:
    try:
        root_metadata = root.lstat()
    except FileNotFoundError as error:
        raise MigrationError(
            "Required Matter controller storage is missing."
        ) from error
    except OSError as error:
        raise MigrationError(
            "Matter controller storage metadata could not be read."
        ) from error

    if stat.S_ISLNK(root_metadata.st_mode):
        raise MigrationError(
            "Matter controller storage must not be a symlink."
        )

    if not stat.S_ISDIR(root_metadata.st_mode):
        raise MigrationError(
            "Matter controller storage must be a directory."
        )

    entries: list[ManifestEntry] = []

    def visit(directory: Path, relative_directory: Path) -> None:
        try:
            children = sorted(
                directory.iterdir(),
                key=lambda path: path.name,
            )
        except OSError as error:
            raise MigrationError(
                "Matter controller storage could not be enumerated."
            ) from error

        for child in children:
            relative_path = relative_directory / child.name

            try:
                metadata = child.lstat()
            except OSError as error:
                raise MigrationError(
                    "Matter controller storage metadata could not be read."
                ) from error

            if stat.S_ISLNK(metadata.st_mode):
                raise MigrationError(
                    "Matter controller storage must not contain symlinks."
                )

            if stat.S_ISDIR(metadata.st_mode):
                entries.append(
                    ManifestEntry(
                        relative_path=relative_path.as_posix(),
                        kind="directory",
                        size=0,
                        sha256="",
                    )
                )
                visit(child, relative_path)
                continue

            if not stat.S_ISREG(metadata.st_mode):
                raise MigrationError(
                    "Matter controller storage contains an unsupported file type."
                )

            size, digest = _hash_regular_file(child)
            entries.append(
                ManifestEntry(
                    relative_path=relative_path.as_posix(),
                    kind="file",
                    size=size,
                    sha256=digest,
                )
            )

    visit(root, Path())
    manifest = TreeManifest(tuple(entries))

    if require_regular_file and manifest.file_count == 0:
        raise MigrationError(
            "Active Matter controller storage contains no regular files."
        )

    return manifest


def _validate_private_tree(root: Path) -> None:
    expected_uid = os.geteuid()
    expected_gid = os.getegid()
    pending = [root]

    while pending:
        current = pending.pop()

        try:
            metadata = current.lstat()
        except OSError as error:
            raise MigrationError(
                "Protected Matter copy metadata could not be read."
            ) from error

        if stat.S_ISLNK(metadata.st_mode):
            raise MigrationError(
                "Protected Matter copies must not contain symlinks."
            )

        if stat.S_ISDIR(metadata.st_mode):
            expected_mode = 0o700

            try:
                pending.extend(current.iterdir())
            except OSError as error:
                raise MigrationError(
                    "Protected Matter copies could not be enumerated."
                ) from error
        elif stat.S_ISREG(metadata.st_mode):
            expected_mode = 0o600
        else:
            raise MigrationError(
                "Protected Matter copies contain an unsupported file type."
            )

        if stat.S_IMODE(metadata.st_mode) != expected_mode:
            raise MigrationError(
                "Protected Matter copy permissions are not private."
            )

        if metadata.st_uid != expected_uid or metadata.st_gid != expected_gid:
            raise MigrationError(
                "Protected Matter copies are not owned by the operator identity."
            )


def _copy_manifest_to_staging(
    source: Path,
    staging: Path,
    manifest: TreeManifest,
) -> None:
    try:
        staging.mkdir(mode=0o700)
    except OSError as error:
        raise MigrationError(
            "Protected Matter staging could not be created."
        ) from error

    for entry in manifest.entries:
        relative_path = Path(entry.relative_path)
        source_path = source / relative_path
        destination_path = staging / relative_path

        try:
            if entry.kind == "directory":
                destination_path.mkdir(mode=0o700)
            else:
                destination_path.parent.mkdir(
                    parents=True,
                    exist_ok=True,
                    mode=0o700,
                )
                shutil.copyfile(
                    source_path,
                    destination_path,
                    follow_symlinks=False,
                )
                destination_path.chmod(0o600)
        except OSError as error:
            raise MigrationError(
                "Matter controller storage could not be copied completely."
            ) from error

    for directory, directory_names, _file_names in os.walk(
        staging,
        topdown=False,
        followlinks=False,
    ):
        current = Path(directory)

        try:
            current.chmod(0o700)

            for directory_name in directory_names:
                (current / directory_name).chmod(0o700)
        except OSError as error:
            raise MigrationError(
                "Protected Matter directory permissions could not be enforced."
            ) from error


def _remove_owned_staging(staging: Path) -> None:
    if not _path_exists(staging):
        return

    if staging.parent.name not in (
        "matter",
        ROLLBACK_ROOT_NAME,
    ) or not staging.name.startswith(STAGING_PREFIX):
        raise MigrationError(
            "Protected Matter staging cleanup boundary was rejected."
        )

    shutil.rmtree(staging)


def _copy_or_validate_tree(
    source: Path,
    destination: Path,
    manifest: TreeManifest,
    *,
    require_regular_file: bool,
) -> bool:
    if _path_exists(destination):
        existing_manifest = _tree_manifest(
            destination,
            require_regular_file=require_regular_file,
        )

        if existing_manifest != manifest:
            raise MigrationError(
                "An existing protected Matter destination does not match its source."
            )

        _validate_private_tree(destination)
        return False

    try:
        staging = Path(
            tempfile.mkdtemp(
                prefix=STAGING_PREFIX,
                dir=destination.parent,
            )
        )
        staging.rmdir()
    except OSError as error:
        raise MigrationError(
            "Protected Matter staging could not be reserved."
        ) from error

    try:
        _copy_manifest_to_staging(source, staging, manifest)
        copied_manifest = _tree_manifest(
            staging,
            require_regular_file=require_regular_file,
        )

        if copied_manifest != manifest:
            raise MigrationError(
                "A protected Matter copy failed content validation."
            )

        _validate_private_tree(staging)

        try:
            staging.rename(destination)
        except OSError as error:
            raise MigrationError(
                "A protected Matter copy could not be promoted."
            ) from error

        _validate_private_tree(destination)
        return True
    except Exception:
        _remove_owned_staging(staging)
        raise


def _require_private_parent(parent: Path) -> None:
    if not _path_exists(parent):
        raise MigrationError(
            "The protected Matter parent is missing; no destination was initialized."
        )

    _validate_private_tree(parent)


def _discover_copy_plan(source_root: Path, paths) -> tuple[TreeCopyPlan, ...]:
    legacy_matter_dir = source_root / "subsystems" / "matter"
    active_source = legacy_matter_dir / ACTIVE_SOURCE_NAME
    rollback_root = paths.matter_protected_dir / ROLLBACK_ROOT_NAME
    source_trees = [active_source]

    try:
        children = sorted(
            legacy_matter_dir.iterdir(),
            key=lambda path: path.name,
        )
    except OSError as error:
        raise MigrationError(
            "Legacy Matter storage could not be enumerated."
        ) from error

    source_trees.extend(
        child
        for child in children
        if child.name.startswith(BAD_PREFIX)
        or child.name.startswith(REPAIR_PREFIX)
    )

    plans = []

    for source in source_trees:
        destination_name = (
            CONTROLLER_DESTINATION_NAME
            if source.name == ACTIVE_SOURCE_NAME
            else source.name
        )
        plans.append(
            TreeCopyPlan(
                source=source,
                destination=(
                    paths.matter_controller_storage_dir
                    if source.name == ACTIVE_SOURCE_NAME
                    else paths.matter_protected_dir / destination_name
                ),
                rollback=rollback_root / destination_name,
                require_regular_file=(source.name == ACTIVE_SOURCE_NAME),
            )
        )

    return tuple(plans)


def require_service_inactive(service_name: str = SERVICE_NAME) -> None:
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
            "The KotiBot service must be stopped before controller storage is copied."
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


def migrate_controller_storage(
    source_root: Path,
    paths,
    *,
    perform_copy: bool,
    service_check: Callable[[], None],
) -> MigrationResult:
    service_check()
    _require_private_parent(paths.matter_protected_dir)
    plans = _discover_copy_plan(Path(source_root), paths)
    manifests = {
        plan: _tree_manifest(
            plan.source,
            require_regular_file=plan.require_regular_file,
        )
        for plan in plans
    }

    copied = 0
    previously_verified = 0

    for plan, manifest in manifests.items():
        for destination in (plan.rollback, plan.destination):
            if _path_exists(destination):
                existing_manifest = _tree_manifest(
                    destination,
                    require_regular_file=plan.require_regular_file,
                )

                if existing_manifest != manifest:
                    raise MigrationError(
                        "An existing protected Matter destination does not match its source."
                    )

                _validate_private_tree(destination)

    if perform_copy:
        rollback_root = paths.matter_protected_dir / ROLLBACK_ROOT_NAME

        if not _path_exists(rollback_root):
            try:
                rollback_root.mkdir(mode=0o700)
            except OSError as error:
                raise MigrationError(
                    "The protected Matter rollback root could not be created."
                ) from error

        _validate_private_tree(rollback_root)

        for plan, manifest in manifests.items():
            for destination in (plan.rollback, plan.destination):
                if _copy_or_validate_tree(
                    plan.source,
                    destination,
                    manifest,
                    require_regular_file=plan.require_regular_file,
                ):
                    copied += 1
                else:
                    previously_verified += 1

        service_check()

        for plan, original_manifest in manifests.items():
            current_manifest = _tree_manifest(
                plan.source,
                require_regular_file=plan.require_regular_file,
            )

            if current_manifest != original_manifest:
                raise MigrationError(
                    "Legacy Matter controller storage changed during the copy."
                )

            for destination in (plan.rollback, plan.destination):
                copied_manifest = _tree_manifest(
                    destination,
                    require_regular_file=plan.require_regular_file,
                )

                if copied_manifest != original_manifest:
                    raise MigrationError(
                        "A protected Matter copy failed final validation."
                    )

                _validate_private_tree(destination)

    return MigrationResult(
        tree_count=len(plans),
        file_count=sum(
            manifest.file_count
            for manifest in manifests.values()
        ),
        total_bytes=sum(
            manifest.total_bytes
            for manifest in manifests.values()
        ),
        newly_copied_trees=copied,
        previously_verified_trees=previously_verified,
        performed_copy=perform_copy,
    )


def render_result(result: MigrationResult) -> str:
    status = "copy and rollback validation passed" if result.performed_copy else "preflight passed"
    lines = [
        f"PATH-001C.4.2 {status}.",
        f"Controller trees discovered: {result.tree_count}",
        f"Regular files discovered: {result.file_count}",
        f"Bytes validated: {result.total_bytes}",
    ]

    if result.performed_copy:
        lines.extend((
            f"Protected copies created: {result.newly_copied_trees}",
            f"Existing protected copies revalidated: {result.previously_verified_trees}",
            "Rollback copy validated: yes",
            "Legacy source changed: no",
        ))
    else:
        lines.append("Copy requested: no")

    lines.extend((
        "Subscription storage changed: no",
        "Runtime cutover changed: no",
        "Legacy cleanup authorized: no",
    ))
    return "\n".join(lines)


def parse_args(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(
        description=(
            "Validate and copy protected Matter controller storage without "
            "changing active runtime paths."
        )
    )
    parser.add_argument(
        "--copy",
        action="store_true",
        help="perform the copy after the default fail-closed preflight",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    try:
        require_operator_identity()
        paths = build_runtime_paths(SOURCE_ROOT)
        result = migrate_controller_storage(
            SOURCE_ROOT,
            paths,
            perform_copy=args.copy,
            service_check=require_service_inactive,
        )
    except MigrationError as error:
        print(
            f"PATH-001C.4.2 stopped: {error}",
            file=sys.stderr,
        )
        return 1
    except Exception:
        print(
            "PATH-001C.4.2 stopped: unexpected migration failure.",
            file=sys.stderr,
        )
        return 1

    print(render_result(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

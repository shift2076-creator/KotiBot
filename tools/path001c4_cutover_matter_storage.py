#!/usr/bin/env python3
"""Relocate live Matter storage into protected paths for runtime cutover."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import os
from pathlib import Path
import stat
import subprocess
import sys
from typing import Callable


SOURCE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOURCE_ROOT))

from server_core.paths import build_runtime_paths  # noqa: E402
from tools.path001c4_migrate_matter_controller_storage import (  # noqa: E402
    BAD_PREFIX,
    MigrationError,
    REPAIR_PREFIX,
    ROLLBACK_ROOT_NAME,
    _copy_or_validate_tree,
    _path_exists,
    _require_private_parent,
    _tree_manifest,
    _validate_private_tree,
)


SERVICE_NAME = "kotibot.service"
CONTROLLER_SOURCE_NAME = "chip_tool_storage"
SUBSCRIPTION_SOURCE_NAME = "chip_tool_subscription_storage"
CONTROLLER_DESTINATION_NAME = "controller"
SUBSCRIPTION_DESTINATION_NAME = "subscriptions"
PRE_CUTOVER_NAME = "pre-cutover"
LEGACY_WORKTREE_NAME = "legacy-worktree"


@dataclass(frozen=True)
class RelocationPlan:
    source: Path
    primary: Path | None
    rollback: Path
    archive: Path
    require_regular_file: bool


@dataclass(frozen=True)
class CutoverResult:
    tree_count: int
    file_count: int
    total_bytes: int
    primary_trees_initialized: int
    rollback_trees_created: int
    legacy_trees_relocated: int
    performed_cutover: bool
    already_complete: bool


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
            "The KotiBot service must be stopped before Matter storage "
            "is relocated."
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


def _ensure_private_directory(path: Path) -> None:
    if _path_exists(path):
        _validate_private_tree(path)
        return

    try:
        path.mkdir(mode=0o700)
    except OSError as error:
        raise MigrationError(
            "A protected Matter relocation directory could not be created."
        ) from error

    _validate_private_tree(path)


def _enforce_private_tree(root: Path) -> None:
    pending = [root]

    while pending:
        current = pending.pop()

        try:
            metadata = current.lstat()
        except OSError as error:
            raise MigrationError(
                "Relocated Matter storage metadata could not be read."
            ) from error

        if stat.S_ISLNK(metadata.st_mode):
            raise MigrationError(
                "Relocated Matter storage must not contain symlinks."
            )

        try:
            if stat.S_ISDIR(metadata.st_mode):
                current.chmod(0o700)
                pending.extend(current.iterdir())
            elif stat.S_ISREG(metadata.st_mode):
                current.chmod(0o600)
            else:
                raise MigrationError(
                    "Relocated Matter storage contains an unsupported file type."
                )
        except OSError as error:
            raise MigrationError(
                "Relocated Matter storage permissions could not be enforced."
            ) from error

    _validate_private_tree(root)


def _discover_source_names(legacy_matter_dir: Path) -> tuple[str, ...]:
    try:
        children = sorted(
            legacy_matter_dir.iterdir(),
            key=lambda path: path.name,
        )
    except OSError as error:
        raise MigrationError(
            "Legacy Matter storage could not be enumerated."
        ) from error

    names = [
        CONTROLLER_SOURCE_NAME,
        SUBSCRIPTION_SOURCE_NAME,
    ]
    names.extend(
        child.name
        for child in children
        if child.name.startswith(BAD_PREFIX)
        or child.name.startswith(REPAIR_PREFIX)
    )
    return tuple(dict.fromkeys(names))


def _build_pending_plans(source_root: Path, paths) -> tuple[RelocationPlan, ...]:
    legacy_matter_dir = source_root / "subsystems" / "matter"
    rollback_root = paths.matter_protected_dir / ROLLBACK_ROOT_NAME
    pre_cutover_root = rollback_root / PRE_CUTOVER_NAME
    legacy_archive_root = rollback_root / LEGACY_WORKTREE_NAME
    plans = []

    for name in _discover_source_names(legacy_matter_dir):
        source = legacy_matter_dir / name

        if name == CONTROLLER_SOURCE_NAME:
            primary = paths.matter_controller_storage_dir
            destination_name = CONTROLLER_DESTINATION_NAME
            require_regular_file = True
        elif name == SUBSCRIPTION_SOURCE_NAME:
            primary = paths.matter_subscription_storage_dir
            destination_name = SUBSCRIPTION_DESTINATION_NAME
            require_regular_file = False
        else:
            primary = None
            destination_name = name
            require_regular_file = False

        plans.append(RelocationPlan(
            source=source,
            primary=primary,
            rollback=pre_cutover_root / destination_name,
            archive=legacy_archive_root / name,
            require_regular_file=require_regular_file,
        ))

    return tuple(plans)


def _require_protected_controller_and_rollback(paths) -> None:
    protected_targets = (
        paths.matter_controller_storage_dir,
        paths.matter_protected_dir
        / ROLLBACK_ROOT_NAME
        / CONTROLLER_DESTINATION_NAME,
    )

    for target in protected_targets:
        if not _path_exists(target):
            raise MigrationError(
                "The validated PATH-001C.4.2 controller copies are missing."
            )

    for target in protected_targets:
        _tree_manifest(target, require_regular_file=True)
        _validate_private_tree(target)


def _ensure_primary(
    plan: RelocationPlan,
    manifest,
) -> bool:
    destination = plan.primary

    if destination is None:
        return False

    if _path_exists(destination):
        _tree_manifest(
            destination,
            require_regular_file=plan.require_regular_file,
        )
        _validate_private_tree(destination)
        return False

    _copy_or_validate_tree(
        plan.source,
        destination,
        manifest,
        require_regular_file=plan.require_regular_file,
    )
    return True


def _validate_completed_cutover(
    source_root: Path,
    paths,
    *,
    expected_archives=None,
) -> CutoverResult:
    legacy_matter_dir = source_root / "subsystems" / "matter"
    rollback_root = paths.matter_protected_dir / ROLLBACK_ROOT_NAME
    pre_cutover_root = rollback_root / PRE_CUTOVER_NAME
    legacy_archive_root = rollback_root / LEGACY_WORKTREE_NAME
    pairs = (
        (
            legacy_matter_dir / CONTROLLER_SOURCE_NAME,
            legacy_archive_root / CONTROLLER_SOURCE_NAME,
            paths.matter_controller_storage_dir,
            pre_cutover_root / CONTROLLER_DESTINATION_NAME,
            True,
        ),
        (
            legacy_matter_dir / SUBSCRIPTION_SOURCE_NAME,
            legacy_archive_root / SUBSCRIPTION_SOURCE_NAME,
            paths.matter_subscription_storage_dir,
            pre_cutover_root / SUBSCRIPTION_DESTINATION_NAME,
            False,
        ),
    )
    manifests = []

    for legacy, archive, primary, rollback, require_regular_file in pairs:
        if _path_exists(legacy):
            raise MigrationError(
                "Legacy Matter storage still exists after the reported cutover."
            )

        for target in (archive, primary, rollback):
            if not _path_exists(target):
                raise MigrationError(
                    "A required protected Matter cutover copy is missing."
                )

        active_manifests = tuple(
            _tree_manifest(
                target,
                require_regular_file=require_regular_file,
            )
            for target in (primary, rollback)
        )

        if active_manifests[0] != active_manifests[1]:
            raise MigrationError(
                "Protected Matter cutover copies no longer match."
            )

        for target in (archive, primary, rollback):
            _validate_private_tree(target)

        archive_manifest = _tree_manifest(
            archive,
            require_regular_file=require_regular_file,
        )

        if (
            expected_archives is not None
            and archive_manifest != expected_archives.get(archive.name)
        ):
            raise MigrationError(
                "Relocated Matter storage changed during cutover."
            )

        manifests.append(active_manifests[0])

    try:
        legacy_children = tuple(legacy_matter_dir.iterdir())
        archived_children = tuple(legacy_archive_root.iterdir())
    except OSError as error:
        raise MigrationError(
            "Completed Matter relocation storage could not be enumerated."
        ) from error

    if any(
        child.name.startswith(BAD_PREFIX)
        or child.name.startswith(REPAIR_PREFIX)
        for child in legacy_children
    ):
        raise MigrationError(
            "Legacy Matter repair or rollback storage remains in the worktree."
        )

    for archive in archived_children:
        if not (
            archive.name.startswith(BAD_PREFIX)
            or archive.name.startswith(REPAIR_PREFIX)
        ):
            continue

        rollback = pre_cutover_root / archive.name

        if not _path_exists(rollback):
            raise MigrationError(
                "A relocated Matter repair or rollback copy is missing."
            )

        archive_manifest = _tree_manifest(
            archive,
            require_regular_file=False,
        )
        rollback_manifest = _tree_manifest(
            rollback,
            require_regular_file=False,
        )

        if archive_manifest != rollback_manifest:
            raise MigrationError(
                "Relocated Matter repair or rollback copies no longer match."
            )

        if (
            expected_archives is not None
            and archive_manifest != expected_archives.get(archive.name)
        ):
            raise MigrationError(
                "Relocated Matter storage changed during cutover."
            )

        _validate_private_tree(archive)
        _validate_private_tree(rollback)
        manifests.append(archive_manifest)

    return CutoverResult(
        tree_count=len(manifests),
        file_count=sum(manifest.file_count for manifest in manifests),
        total_bytes=sum(manifest.total_bytes for manifest in manifests),
        primary_trees_initialized=0,
        rollback_trees_created=0,
        legacy_trees_relocated=0,
        performed_cutover=False,
        already_complete=True,
    )


def cutover_matter_storage(
    source_root: Path,
    paths,
    *,
    perform_cutover: bool,
    service_check: Callable[[], None],
) -> CutoverResult:
    source_root = Path(source_root)
    service_check()
    _require_private_parent(paths.matter_protected_dir)

    legacy_matter_dir = source_root / "subsystems" / "matter"
    active_sources = (
        legacy_matter_dir / CONTROLLER_SOURCE_NAME,
        legacy_matter_dir / SUBSCRIPTION_SOURCE_NAME,
    )
    rollback_root = paths.matter_protected_dir / ROLLBACK_ROOT_NAME
    legacy_archive_root = rollback_root / LEGACY_WORKTREE_NAME
    archived_sources = (
        legacy_archive_root / CONTROLLER_SOURCE_NAME,
        legacy_archive_root / SUBSCRIPTION_SOURCE_NAME,
    )

    if not any(_path_exists(path) for path in active_sources):
        if all(_path_exists(path) for path in archived_sources):
            return _validate_completed_cutover(source_root, paths)

        raise MigrationError(
            "Required legacy Matter storage is missing and no complete "
            "protected relocation was found."
        )

    if not all(_path_exists(path) for path in active_sources):
        raise MigrationError(
            "Legacy Matter storage is only partially present; cutover stopped."
        )

    if any(_path_exists(path) for path in archived_sources):
        raise MigrationError(
            "A partial legacy Matter relocation already exists."
        )

    _require_protected_controller_and_rollback(paths)
    plans = _build_pending_plans(source_root, paths)
    manifests = {
        plan: _tree_manifest(
            plan.source,
            require_regular_file=plan.require_regular_file,
        )
        for plan in plans
    }

    authoritative_manifests = {}

    for plan, manifest in manifests.items():
        if plan.primary is not None and _path_exists(plan.primary):
            authoritative_manifest = _tree_manifest(
                plan.primary,
                require_regular_file=plan.require_regular_file,
            )
            _validate_private_tree(plan.primary)
        else:
            authoritative_manifest = manifest

        authoritative_manifests[plan] = authoritative_manifest

        if _path_exists(plan.rollback):
            rollback_manifest = _tree_manifest(
                plan.rollback,
                require_regular_file=plan.require_regular_file,
            )

            if rollback_manifest != authoritative_manifest:
                raise MigrationError(
                    "An existing pre-cutover Matter rollback does not match "
                    "the selected protected authority."
                )

            _validate_private_tree(plan.rollback)

        if _path_exists(plan.archive):
            raise MigrationError(
                "A legacy Matter archive destination already exists."
            )

    if not perform_cutover:
        return CutoverResult(
            tree_count=len(plans),
            file_count=sum(
                manifest.file_count for manifest in manifests.values()
            ),
            total_bytes=sum(
                manifest.total_bytes for manifest in manifests.values()
            ),
            primary_trees_initialized=0,
            rollback_trees_created=0,
            legacy_trees_relocated=0,
            performed_cutover=False,
            already_complete=False,
        )

    _ensure_private_directory(rollback_root)
    pre_cutover_root = rollback_root / PRE_CUTOVER_NAME
    _ensure_private_directory(pre_cutover_root)
    _ensure_private_directory(legacy_archive_root)

    primary_initialized = sum(
        _ensure_primary(plan, manifests[plan])
        for plan in plans
    )

    authoritative_manifests = {
        plan: (
            _tree_manifest(
                plan.primary,
                require_regular_file=plan.require_regular_file,
            )
            if plan.primary is not None
            else manifests[plan]
        )
        for plan in plans
    }

    rollback_created = 0

    for plan, manifest in authoritative_manifests.items():
        rollback_source = (
            plan.primary
            if plan.primary is not None
            else plan.source
        )
        if _copy_or_validate_tree(
            rollback_source,
            plan.rollback,
            manifest,
            require_regular_file=plan.require_regular_file,
        ):
            rollback_created += 1

    service_check()

    for plan, original_manifest in manifests.items():
        current_manifest = _tree_manifest(
            plan.source,
            require_regular_file=plan.require_regular_file,
        )

        if current_manifest != original_manifest:
            raise MigrationError(
                "Legacy Matter storage changed during cutover preparation."
            )

        rollback_manifest = _tree_manifest(
            plan.rollback,
            require_regular_file=plan.require_regular_file,
        )

        authoritative_manifest = authoritative_manifests[plan]

        if rollback_manifest != authoritative_manifest:
            raise MigrationError(
                "A pre-cutover Matter rollback failed final validation."
            )

        if plan.primary is not None:
            primary_manifest = _tree_manifest(
                plan.primary,
                require_regular_file=plan.require_regular_file,
            )

            if primary_manifest != authoritative_manifest:
                raise MigrationError(
                    "A protected Matter primary failed final validation."
                )

    moved = []

    try:
        for plan in plans:
            try:
                plan.source.rename(plan.archive)
            except OSError as error:
                raise MigrationError(
                    "Legacy Matter storage could not be relocated atomically."
                ) from error

            moved.append(plan)
            _enforce_private_tree(plan.archive)

        service_check()
        _validate_completed_cutover(
            source_root,
            paths,
            expected_archives={
                plan.archive.name: manifests[plan]
                for plan in plans
            },
        )
    except Exception:
        for plan in reversed(moved):
            if _path_exists(plan.archive) and not _path_exists(plan.source):
                plan.archive.rename(plan.source)
        raise

    return CutoverResult(
        tree_count=len(plans),
        file_count=sum(
            manifest.file_count for manifest in manifests.values()
        ),
        total_bytes=sum(
            manifest.total_bytes for manifest in manifests.values()
        ),
        primary_trees_initialized=primary_initialized,
        rollback_trees_created=rollback_created,
        legacy_trees_relocated=len(plans),
        performed_cutover=True,
        already_complete=False,
    )


def render_result(result: CutoverResult) -> str:
    if result.already_complete:
        status = "protected relocation already validated"
    elif result.performed_cutover:
        status = "protected relocation completed"
    else:
        status = "cutover preflight passed"

    lines = [
        f"PATH-001C.4.4 {status}.",
        f"Matter trees discovered: {result.tree_count}",
        f"Regular files validated: {result.file_count}",
        f"Bytes validated: {result.total_bytes}",
    ]

    if result.performed_cutover:
        lines.extend((
            f"Protected primaries initialized: {result.primary_trees_initialized}",
            f"Pre-cutover rollbacks created: {result.rollback_trees_created}",
            f"Legacy trees relocated: {result.legacy_trees_relocated}",
            "Worktree Matter storage remains: no",
            "Rollback material preserved: yes",
        ))
    elif result.already_complete:
        lines.extend((
            "Worktree Matter storage remains: no",
            "Rollback material revalidated: yes",
        ))
    else:
        lines.extend((
            "Cutover requested: no",
            "Worktree Matter storage changed: no",
        ))

    lines.append("Legacy cleanup authorized: no")
    return "\n".join(lines)


def parse_args(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(
        description=(
            "Relocate live Matter controller and subscription storage into "
            "protected runtime and rollback paths."
        )
    )
    parser.add_argument(
        "--cutover",
        action="store_true",
        help="perform the protected relocation after fail-closed preflight",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    try:
        require_operator_identity()
        paths = build_runtime_paths(SOURCE_ROOT)
        result = cutover_matter_storage(
            SOURCE_ROOT,
            paths,
            perform_cutover=args.cutover,
            service_check=require_service_inactive,
        )
    except MigrationError as error:
        print(f"PATH-001C.4.4 stopped: {error}", file=sys.stderr)
        return 1
    except Exception:
        print(
            "PATH-001C.4.4 stopped: unexpected relocation failure.",
            file=sys.stderr,
        )
        return 1

    print(render_result(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

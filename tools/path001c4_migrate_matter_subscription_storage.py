#!/usr/bin/env python3
"""Copy Matter subscription storage into protected storage without cutover."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import os
from pathlib import Path
import subprocess
import sys
from typing import Callable


SOURCE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOURCE_ROOT))

from server_core.paths import build_runtime_paths  # noqa: E402
from tools.path001c4_migrate_matter_controller_storage import (  # noqa: E402
    MigrationError,
    ROLLBACK_ROOT_NAME,
    _copy_or_validate_tree,
    _path_exists,
    _require_private_parent,
    _tree_manifest,
    _validate_private_tree,
)


SERVICE_NAME = "kotibot.service"
SOURCE_NAME = "chip_tool_subscription_storage"
ROLLBACK_DESTINATION_NAME = "subscriptions"
CONTROLLER_SOURCE_NAME = "chip_tool_storage"
CONTROLLER_DESTINATION_NAME = "controller"


@dataclass(frozen=True)
class MigrationResult:
    file_count: int
    total_bytes: int
    newly_copied_trees: int
    previously_verified_trees: int
    performed_copy: bool


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
            "The KotiBot service must be stopped before subscription "
            "storage is copied."
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


def _require_controller_copy_prerequisite(source_root: Path, paths) -> None:
    source = (
        Path(source_root)
        / "subsystems"
        / "matter"
        / CONTROLLER_SOURCE_NAME
    )
    source_manifest = _tree_manifest(
        source,
        require_regular_file=True,
    )
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

        target_manifest = _tree_manifest(
            target,
            require_regular_file=True,
        )

        if target_manifest != source_manifest:
            raise MigrationError(
                "A PATH-001C.4.2 controller copy no longer matches its source."
            )

        _validate_private_tree(target)


def migrate_subscription_storage(
    source_root: Path,
    paths,
    *,
    perform_copy: bool,
    service_check: Callable[[], None],
) -> MigrationResult:
    service_check()
    _require_private_parent(paths.matter_protected_dir)
    _require_controller_copy_prerequisite(source_root, paths)

    source = (
        Path(source_root)
        / "subsystems"
        / "matter"
        / SOURCE_NAME
    )
    destination = paths.matter_subscription_storage_dir
    rollback = (
        paths.matter_protected_dir
        / ROLLBACK_ROOT_NAME
        / ROLLBACK_DESTINATION_NAME
    )
    manifest = _tree_manifest(
        source,
        require_regular_file=False,
    )

    for target in (rollback, destination):
        if not _path_exists(target):
            continue

        existing_manifest = _tree_manifest(
            target,
            require_regular_file=False,
        )

        if existing_manifest != manifest:
            raise MigrationError(
                "An existing protected Matter subscription destination "
                "does not match its source."
            )

        _validate_private_tree(target)

    copied = 0
    previously_verified = 0

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

        for target in (rollback, destination):
            if _copy_or_validate_tree(
                source,
                target,
                manifest,
                require_regular_file=False,
            ):
                copied += 1
            else:
                previously_verified += 1

        service_check()
        current_manifest = _tree_manifest(
            source,
            require_regular_file=False,
        )

        if current_manifest != manifest:
            raise MigrationError(
                "Legacy Matter subscription storage changed during the copy."
            )

        for target in (rollback, destination):
            copied_manifest = _tree_manifest(
                target,
                require_regular_file=False,
            )

            if copied_manifest != manifest:
                raise MigrationError(
                    "A protected Matter subscription copy failed final "
                    "validation."
                )

            _validate_private_tree(target)

    return MigrationResult(
        file_count=manifest.file_count,
        total_bytes=manifest.total_bytes,
        newly_copied_trees=copied,
        previously_verified_trees=previously_verified,
        performed_copy=perform_copy,
    )


def render_result(result: MigrationResult) -> str:
    status = (
        "copy and rollback validation passed"
        if result.performed_copy
        else "preflight passed"
    )
    lines = [
        f"PATH-001C.4.3 {status}.",
        "Subscription trees discovered: 1",
        f"Regular files discovered: {result.file_count}",
        f"Bytes validated: {result.total_bytes}",
    ]

    if result.performed_copy:
        lines.extend((
            f"Protected copies created: {result.newly_copied_trees}",
            "Existing protected copies revalidated: "
            f"{result.previously_verified_trees}",
            "Rollback copy validated: yes",
            "Legacy source changed: no",
        ))
    else:
        lines.append("Copy requested: no")

    lines.extend((
        "Controller storage changed: no",
        "Runtime cutover changed: no",
        "Legacy cleanup authorized: no",
    ))
    return "\n".join(lines)


def parse_args(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(
        description=(
            "Validate and copy protected Matter subscription storage without "
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
        result = migrate_subscription_storage(
            SOURCE_ROOT,
            paths,
            perform_copy=args.copy,
            service_check=require_service_inactive,
        )
    except MigrationError as error:
        print(
            f"PATH-001C.4.3 stopped: {error}",
            file=sys.stderr,
        )
        return 1
    except Exception:
        print(
            "PATH-001C.4.3 stopped: unexpected migration failure.",
            file=sys.stderr,
        )
        return 1

    print(render_result(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

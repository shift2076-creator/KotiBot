#!/usr/bin/env python3
"""Validate and remove legacy runtime residue from the source checkout."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import pwd
import stat
import subprocess
import sys
import time
from typing import Iterable, Mapping


SOURCE_ROOT = Path(__file__).resolve().parents[1]

if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from server_core.io import json_backup_path  # noqa: E402
from server_core.paths import RuntimePaths  # noqa: E402
from tools.path001c7_migrate_recordings import (  # noqa: E402
    _media_manifest,
    _same_payload as _same_media_payload,
)
from tools.path001c9_migrate_android_packages import (  # noqa: E402
    _package_manifest,
    _package_plans,
    _same_payload as _same_package_payload,
    _validate_private_package,
)
from tools.sec0045_verify_complete_credential_cutover import (  # noqa: E402
    inspect_active_service,
    verify_removed_legacy_sources,
)


SERVICE_NAME = "kotibot"
HANDOFF_MAX_AGE_SECONDS = 30 * 60
MAX_DOCUMENT_BYTES = 16 * 1024 * 1024
MAX_HISTORY_BYTES = 64 * 1024 * 1024
MAX_IGNORED_PATHS = 250_000
PATH_ENVIRONMENT_NAMES = frozenset({
    "KOTIBOT_DATA_DIR",
    "KOTIBOT_CACHE_DIR",
    "KOTIBOT_RUNTIME_DIR",
    "KOTIBOT_TEMP_DIR",
    "KOTIBOT_PACKAGE_DIR",
    "KOTIBOT_MEDIA_DIR",
    "KOTIBOT_TAPO_RECORDING_DIR",
    "XDG_DATA_HOME",
    "XDG_CACHE_HOME",
    "XDG_RUNTIME_DIR",
})

STATE_TARGETS = (
    ("server", Path("server_state.json"), "server_state_file"),
    (
        "security-actions",
        Path("subsystems/automations/security_actions.json"),
        "security_actions_file",
    ),
    (
        "automations",
        Path("subsystems/automations/automations_state.json"),
        "automation_state_file",
    ),
    (
        "android-home",
        Path("subsystems/client-android-home/android_home_state.json"),
        "android_home_state_file",
    ),
    (
        "tapo-config",
        Path("subsystems/client-tapo/tapo_config.json"),
        "tapo_config_file",
    ),
    (
        "tapo-device",
        Path("subsystems/client-tapo/tapo_device_state.json"),
        "tapo_device_state_file",
    ),
    (
        "tapo-lighting",
        Path("subsystems/client-tapo/tapo_lighting_state.json"),
        "tapo_lighting_state_file",
    ),
    (
        "environment",
        Path("subsystems/environment/environment_state.json"),
        "environment_state_file",
    ),
    (
        "matter-device",
        Path("subsystems/matter/matter_device_state.json"),
        "matter_device_state_file",
    ),
    (
        "matter-controller",
        Path("subsystems/matter/matter_state.json"),
        "matter_state_file",
    ),
    (
        "activity",
        Path("subsystems/activities/activity_state.json"),
        "activity_state_file",
    ),
)

HISTORY_TARGETS = (
    (
        "notifications",
        Path("subsystems/notifications/notification_queue.jsonl"),
        "notification_queue_file",
        False,
    ),
    (
        "security-audit",
        Path("subsystems/security/security_audit.jsonl"),
        "security_audit_file",
        True,
    ),
)

RECORDING_ROOTS = (
    Path("subsystems/video/videos"),
    Path("recordings"),
    Path("static/recordings"),
)
PACKAGE_ROOT = Path("subsystems/file-server/get-app")
REPLACEABLE_ROOTS = (
    Path("runtime"),
    Path("tmp"),
    Path("static/hls"),
    Path("static/cache"),
    Path("subsystems/client-tapo/runtime"),
)
MATTER_STORAGE_ROOTS = (
    Path("subsystems/matter/chip_tool_storage"),
    Path("subsystems/matter/chip_tool_subscription_storage"),
)
PRESERVED_PREFIXES = (
    ".venv/",
    "venv/",
    "env/",
    "temp/",
    "tools/",
    "tests/",
    "docs/",
    "static/img/favicons/",
    ".pytest_cache/",
    ".mypy_cache/",
    ".ruff_cache/",
    ".idea/",
    ".vscode/",
)
PRESERVED_SUFFIXES = (
    ".pyc",
    ".pyo",
    ".swp",
    ".psd",
    ".ufo",
    "~",
)
BLOCKED_CREDENTIAL_PATHS = (
    Path("subsystems/notifications/firebase-service-account.json"),
    Path("subsystems/security/security_state.json"),
    Path(".env.shared"),
)
_DESTRUCTIVE_STARTED = False


class CleanupError(RuntimeError):
    """A redacted, operator-actionable PATH-003 failure."""


@dataclass(frozen=True)
class ServiceContext:
    process_id: int
    user_id: int
    group_id: int
    environment: Mapping[str, str]
    paths: RuntimePaths


@dataclass(frozen=True)
class Inventory:
    targets: tuple[Path, ...]
    state_labels: tuple[str, ...]
    state_files: int
    history_files: int
    recording_files: int
    package_files: int
    replaceable_files: int
    trash_files: int
    preserved_ignored: int
    unknown_ignored: int
    blocked_credentials: int
    matter_storage_roots: int
    tracked_target_files: int
    unknown_ignored_paths: tuple[str, ...]
    fingerprint: str

    @property
    def target_count(self) -> int:
        return len(self.targets)


@dataclass(frozen=True)
class Validation:
    external_documents: int = 0
    external_histories: int = 0
    recording_copies: int = 0
    package_copies: int = 0
    runtime_contents_read: bool = False


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Fail-closed PATH-003 source-residue preflight, cleanup, and "
            "post-restart verification."
        ),
    )
    parser.add_argument("action", choices=("preflight", "cleanup", "verify"))
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--service", default=SERVICE_NAME)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--handoff-file", type=Path)
    parser.add_argument(
        "--details",
        action="store_true",
        help="display source-relative paths for unclassified ignored files",
    )
    return parser


def _default_handoff_file() -> Path:
    return (
        Path("/run")
        / "user"
        / str(os.geteuid())
        / "kotibot"
        / "path003-cleanup-handoff.json"
    )


def _run_text(command: Iterable[str], *, cwd: Path | None = None) -> str:
    try:
        completed = subprocess.run(
            tuple(command),
            cwd=cwd,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise CleanupError("Required host metadata could not be inspected") from exc

    return completed.stdout


def exact_head(root: Path) -> str:
    return _run_text(("git", "rev-parse", "HEAD"), cwd=root).strip()


def _absolute(path: Path | str, label: str) -> Path:
    candidate = Path(path).expanduser()

    if not candidate.is_absolute():
        raise CleanupError(f"{label} must be absolute")

    return Path(os.path.abspath(candidate))


def _is_within(path: Path, parent: Path) -> bool:
    path = path.resolve(strict=False)
    parent = parent.resolve(strict=False)
    return path == parent or parent in path.parents


def _read_process_path_environment(process_id: int) -> dict[str, str]:
    try:
        payload = (Path("/proc") / str(process_id) / "environ").read_bytes()
    except OSError as exc:
        raise CleanupError("Active service path environment is unavailable") from exc

    if len(payload) > 1024 * 1024:
        raise CleanupError("Active service environment is unexpectedly large")

    result: dict[str, str] = {}

    for entry in payload.split(b"\0"):
        raw_name, separator, raw_value = entry.partition(b"=")

        if not separator:
            continue

        try:
            name = raw_name.decode("utf-8")
        except UnicodeDecodeError:
            continue

        if name not in PATH_ENVIRONMENT_NAMES:
            continue

        try:
            result[name] = raw_value.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise CleanupError("Active service path configuration is invalid") from exc

    return result


def _configured_path(
    environment: Mapping[str, str],
    name: str,
) -> Path | None:
    value = str(environment.get(name, "")).strip()
    return _absolute(value, f"Service {name}") if value else None


def runtime_paths_for_service(
    root: Path,
    *,
    process_user_id: int,
    environment: Mapping[str, str],
) -> RuntimePaths:
    try:
        service_home = _absolute(
            pwd.getpwuid(process_user_id).pw_dir,
            "Service home",
        )
    except (KeyError, OSError) as exc:
        raise CleanupError("Service home could not be resolved") from exc

    data_root = _configured_path(environment, "KOTIBOT_DATA_DIR")

    if data_root is None:
        xdg_data = _configured_path(environment, "XDG_DATA_HOME")
        data_root = (
            xdg_data / "kotibot"
            if xdg_data is not None
            else service_home / ".local" / "share" / "kotibot"
        )

    cache_root = _configured_path(environment, "KOTIBOT_CACHE_DIR")

    if cache_root is None:
        xdg_cache = _configured_path(environment, "XDG_CACHE_HOME")
        cache_root = (
            xdg_cache / "kotibot"
            if xdg_cache is not None
            else service_home / ".cache" / "kotibot"
        )

    runtime_root = _configured_path(environment, "KOTIBOT_RUNTIME_DIR")

    if runtime_root is None:
        xdg_runtime = _configured_path(environment, "XDG_RUNTIME_DIR")
        runtime_root = (
            xdg_runtime / "kotibot"
            if xdg_runtime is not None
            else cache_root / "runtime"
        )

    temporary_root = (
        _configured_path(environment, "KOTIBOT_TEMP_DIR")
        or runtime_root / "temp"
    )
    package_root = (
        _configured_path(environment, "KOTIBOT_PACKAGE_DIR")
        or data_root / "apks"
    )
    media_root = _configured_path(environment, "KOTIBOT_MEDIA_DIR")

    if media_root is None:
        media_root = _configured_path(
            environment,
            "KOTIBOT_TAPO_RECORDING_DIR",
        )

    if media_root is None:
        media_root = data_root / "state" / "media" / "recordings"

    return RuntimePaths(
        source_root=root,
        data_root=data_root,
        cache_root=cache_root,
        runtime_root=runtime_root,
        temporary_root=temporary_root,
        package_root=package_root,
        media_root=media_root,
    ).validate()


def active_service_context(root: Path, service: str) -> ServiceContext:
    try:
        snapshot = inspect_active_service(service)
    except RuntimeError as exc:
        raise CleanupError(str(exc)) from exc

    if (
        snapshot.process_user_id != os.geteuid()
        or snapshot.process_group_id != os.getegid()
    ):
        raise CleanupError("Run PATH-003 as the active KotiBot service identity")

    try:
        working_directory = (Path("/proc") / str(snapshot.process_id) / "cwd").resolve()
    except OSError as exc:
        raise CleanupError("Active service working directory is unavailable") from exc

    if working_directory != root:
        raise CleanupError("Active service does not execute from this source root")

    environment = dict(snapshot.environment)
    environment.update(_read_process_path_environment(snapshot.process_id))
    paths = runtime_paths_for_service(
        root,
        process_user_id=snapshot.process_user_id,
        environment=environment,
    )

    if paths.data_root != snapshot.data_root:
        raise CleanupError("Service data-root resolution is inconsistent")

    return ServiceContext(
        process_id=snapshot.process_id,
        user_id=snapshot.process_user_id,
        group_id=snapshot.process_group_id,
        environment=environment,
        paths=paths,
    )


def require_service_inactive(service: str) -> None:
    try:
        completed = subprocess.run(
            ("systemctl", "is-active", service),
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise CleanupError("The KotiBot service state is unavailable") from exc

    state = completed.stdout.strip()

    if state != "inactive":
        raise CleanupError("The KotiBot service must be inactive for cleanup")


def _private_metadata(
    path: Path,
    *,
    directory: bool,
    uid: int,
    gid: int,
) -> os.stat_result:
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise CleanupError(
            "Required external recovery metadata is unavailable"
        ) from exc

    expected_type = stat.S_ISDIR if directory else stat.S_ISREG

    if stat.S_ISLNK(metadata.st_mode) or not expected_type(metadata.st_mode):
        raise CleanupError("Required external recovery type is invalid")

    if (metadata.st_uid, metadata.st_gid) != (uid, gid):
        raise CleanupError("Required external recovery ownership is invalid")

    expected_mode = 0o700 if directory else 0o600

    if stat.S_IMODE(metadata.st_mode) != expected_mode:
        raise CleanupError("Required external recovery permissions are invalid")

    return metadata


def _read_regular(path: Path, *, maximum: int, label: str) -> bytes:
    try:
        before = path.lstat()
    except OSError as exc:
        raise CleanupError(f"{label} metadata is unavailable") from exc

    if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
        raise CleanupError(f"{label} must be a regular file")

    if before.st_size < 1 or before.st_size > maximum:
        raise CleanupError(f"{label} has an invalid size")

    try:
        payload = path.read_bytes()
        after = path.lstat()
    except OSError as exc:
        raise CleanupError(f"{label} could not be read safely") from exc

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
        raise CleanupError(f"{label} changed while it was read")

    return payload


def _validate_json(path: Path, *, private: bool, uid: int, gid: int) -> None:
    if private:
        _private_metadata(path, directory=False, uid=uid, gid=gid)

    payload = _read_regular(
        path,
        maximum=MAX_DOCUMENT_BYTES,
        label="JSON state",
    )

    try:
        document = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise CleanupError("JSON state is invalid") from exc

    if not isinstance(document, dict):
        raise CleanupError("JSON state must contain an object")


def _path_exists(path: Path) -> bool:
    return os.path.lexists(os.fspath(path))


def _state_related_paths(primary: Path) -> tuple[Path, ...]:
    result = [primary, json_backup_path(primary)]
    parent = primary.parent
    patterns = (
        f".{primary.name}.*.tmp",
        f".{json_backup_path(primary).name}.*.tmp",
        f"{primary.name}.bak",
        f"{primary.name}.bak.*",
    )

    if parent.is_dir():
        for pattern in patterns:
            result.extend(sorted(parent.glob(pattern)))

    return tuple(dict.fromkeys(result))


def _history_related_paths(primary: Path, *, rotated: bool) -> tuple[Path, ...]:
    result = [primary]

    if rotated:
        result.append(primary.with_name(primary.name + ".1"))

    if primary.parent.is_dir():
        result.extend(sorted(primary.parent.glob(f".{primary.name}.*.tmp")))
        result.extend(sorted(primary.parent.glob(f"{primary.name}.bak*")))

    return tuple(dict.fromkeys(result))


def _trash_roots(root: Path) -> tuple[Path, ...]:
    try:
        entries = tuple(root.iterdir())
    except OSError as exc:
        raise CleanupError("Source root could not be enumerated") from exc

    return tuple(
        sorted(
            (
                path
                for path in entries
                if path.name.startswith(".Trash-")
            ),
            key=lambda path: path.name,
        )
    )


def _safe_tree_entries(root: Path) -> tuple[Path, ...]:
    try:
        metadata = root.lstat()
    except OSError as exc:
        raise CleanupError("Cleanup target metadata is unavailable") from exc

    if stat.S_ISLNK(metadata.st_mode):
        raise CleanupError("Cleanup targets must not be symbolic links")

    if stat.S_ISREG(metadata.st_mode):
        return (root,)

    if not stat.S_ISDIR(metadata.st_mode):
        raise CleanupError("Cleanup targets contain an unsupported file type")

    result = [root]
    stack = [root]

    while stack:
        directory = stack.pop()

        try:
            children = tuple(Path(entry.path) for entry in os.scandir(directory))
        except OSError as exc:
            raise CleanupError("Cleanup target could not be enumerated") from exc

        for child in children:
            try:
                child_metadata = child.lstat()
            except OSError as exc:
                raise CleanupError("Cleanup target metadata is unavailable") from exc

            if stat.S_ISLNK(child_metadata.st_mode):
                raise CleanupError("Cleanup targets must not contain symbolic links")

            if stat.S_ISDIR(child_metadata.st_mode):
                stack.append(child)
            elif not stat.S_ISREG(child_metadata.st_mode):
                raise CleanupError("Cleanup targets contain an unsupported file type")

            result.append(child)

            if len(result) > MAX_IGNORED_PATHS:
                raise CleanupError("Cleanup target inventory is unexpectedly large")

    return tuple(result)


def _relative(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError as exc:
        raise CleanupError("Cleanup target escaped the source root") from exc


def _target_fingerprint(root: Path, targets: Iterable[Path]) -> str:
    digest = hashlib.sha256()

    for target in sorted(targets, key=lambda path: _relative(root, path)):
        for path in sorted(
            _safe_tree_entries(target),
            key=lambda item: _relative(root, item),
        ):
            metadata = path.lstat()
            fields = (
                _relative(root, path),
                str(stat.S_IFMT(metadata.st_mode)),
                str(metadata.st_uid),
                str(metadata.st_gid),
                str(metadata.st_size),
                str(metadata.st_mtime_ns),
                str(metadata.st_ctime_ns),
            )
            digest.update("\0".join(fields).encode("utf-8", "surrogateescape"))
            digest.update(b"\0")

    return digest.hexdigest()


def _ignored_paths(root: Path) -> tuple[str, ...]:
    try:
        completed = subprocess.run(
            (
                "git",
                "ls-files",
                "--others",
                "--ignored",
                "--exclude-standard",
                "-z",
            ),
            cwd=root,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise CleanupError("Ignored source residue could not be inventoried") from exc

    paths = tuple(
        item.decode("utf-8", "surrogateescape")
        for item in completed.stdout.split(b"\0")
        if item
    )

    if len(paths) > MAX_IGNORED_PATHS:
        raise CleanupError("Ignored source inventory is unexpectedly large")

    return paths


def _tracked_target_files(
    root: Path,
    targets: Iterable[Path],
) -> tuple[str, ...]:
    relative_targets = tuple(
        _relative(root, target)
        for target in targets
    )

    if not relative_targets:
        return ()

    try:
        completed = subprocess.run(
            ("git", "ls-files", "-z", "--", *relative_targets),
            cwd=root,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise CleanupError("Tracked-source overlap could not be inspected") from exc

    if completed.returncode:
        # Unit fixtures may not be Git worktrees. The live entry point has
        # already proved an exact Git HEAD before inventory is reachable.
        return ()

    return tuple(
        item.decode("utf-8", "surrogateescape")
        for item in completed.stdout.split(b"\0")
        if item
    )


def _is_preserved_ignored(relative: str) -> bool:
    if relative == ".DS_Store" or "/.DS_Store" in relative:
        return True

    if relative.startswith(PRESERVED_PREFIXES):
        return True

    if "/__pycache__/" in f"/{relative}" or relative.startswith("__pycache__/"):
        return True

    return relative.endswith(PRESERVED_SUFFIXES)


def _is_under(relative: str, roots: Iterable[Path]) -> bool:
    path = Path(relative)
    return any(path == root or root in path.parents for root in roots)


def _is_known_target_file(
    root: Path,
    relative: str,
    target_roots: Iterable[Path],
) -> bool:
    path = root / relative
    return any(
        path == target or _is_within(path, target)
        for target in target_roots
    )


def _credential_path(relative: str) -> bool:
    path = Path(relative)
    name = path.name.lower()

    if path in BLOCKED_CREDENTIAL_PATHS:
        return True

    if name == ".env" or (name.startswith(".env.") and name != ".env.example"):
        return True

    if path.suffix.lower() in {".pem", ".key", ".p12", ".pfx"}:
        return True

    return name.startswith("credentials") or name.startswith("secrets")


def build_inventory(root: Path) -> Inventory:
    root = root.resolve(strict=False)
    targets: list[Path] = []
    state_labels: list[str] = []
    state_files = 0
    history_files = 0

    for label, relative, _attribute in STATE_TARGETS:
        existing = tuple(
            path
            for path in _state_related_paths(root / relative)
            if _path_exists(path)
        )

        if existing:
            targets.extend(existing)
            state_labels.append(label)
            state_files += len(existing)

    for _label, relative, _attribute, rotated in HISTORY_TARGETS:
        existing = tuple(
            path
            for path in _history_related_paths(root / relative, rotated=rotated)
            if _path_exists(path)
        )
        targets.extend(existing)
        history_files += len(existing)

    recording_roots = tuple(
        root / relative
        for relative in RECORDING_ROOTS
        if _path_exists(root / relative)
    )
    package_root = root / PACKAGE_ROOT
    package_roots = (package_root,) if _path_exists(package_root) else ()
    replaceable_roots = tuple(
        root / relative
        for relative in REPLACEABLE_ROOTS
        if _path_exists(root / relative)
    )
    trash_roots = _trash_roots(root)
    targets.extend(recording_roots)
    targets.extend(package_roots)
    targets.extend(replaceable_roots)
    targets.extend(trash_roots)

    matter_storage_roots = sum(
        1 for relative in MATTER_STORAGE_ROOTS if _path_exists(root / relative)
    )
    blocked_credentials = sum(
        1 for relative in BLOCKED_CREDENTIAL_PATHS if _path_exists(root / relative)
    )
    unique_targets = tuple(
        sorted(
            dict.fromkeys(targets),
            key=lambda path: _relative(root, path),
        )
    )
    ignored = _ignored_paths(root)
    tracked_targets = _tracked_target_files(root, unique_targets)
    preserved_ignored = 0
    unknown_ignored_paths: list[str] = []

    for relative in ignored:
        if _is_preserved_ignored(relative):
            preserved_ignored += 1
        elif _credential_path(relative):
            blocked_credentials += 1
        elif _is_known_target_file(root, relative, unique_targets):
            continue
        elif _is_under(relative, MATTER_STORAGE_ROOTS):
            matter_storage_roots += 1
        else:
            unknown_ignored_paths.append(relative)

    return Inventory(
        targets=unique_targets,
        state_labels=tuple(sorted(state_labels)),
        state_files=state_files,
        history_files=history_files,
        recording_files=sum(
            len(_media_manifest(path, require_private=False))
            for path in recording_roots
        ),
        package_files=(
            len(_package_manifest(package_root))
            if package_roots
            else 0
        ),
        replaceable_files=sum(
            sum(1 for path in _safe_tree_entries(item) if path.is_file())
            for item in replaceable_roots
        ),
        trash_files=sum(
            sum(1 for path in _safe_tree_entries(item) if path.is_file())
            for item in trash_roots
        ),
        preserved_ignored=preserved_ignored,
        unknown_ignored=len(unknown_ignored_paths),
        blocked_credentials=blocked_credentials,
        matter_storage_roots=matter_storage_roots,
        tracked_target_files=len(tracked_targets),
        unknown_ignored_paths=tuple(sorted(unknown_ignored_paths)),
        fingerprint=_target_fingerprint(root, unique_targets),
    )


def _source_primary_present(root: Path, relative: Path) -> bool:
    primary = root / relative
    backup = json_backup_path(primary)
    return _path_exists(primary) or _path_exists(backup)


def validate_external_recovery(
    root: Path,
    inventory: Inventory,
    context: ServiceContext,
) -> Validation:
    documents = 0
    histories = 0
    recording_copies = 0
    package_copies = 0
    contents_read = False

    for label, relative, attribute in STATE_TARGETS:
        if label not in inventory.state_labels:
            continue

        source = root / relative
        destination = Path(getattr(context.paths, attribute))

        if _source_primary_present(root, relative):
            _validate_json(
                destination,
                private=True,
                uid=context.user_id,
                gid=context.group_id,
            )
            _validate_json(
                json_backup_path(destination),
                private=True,
                uid=context.user_id,
                gid=context.group_id,
            )
            documents += 2
            contents_read = True

        if _path_exists(source):
            _validate_json(
                source,
                private=False,
                uid=context.user_id,
                gid=context.group_id,
            )
            contents_read = True

        source_backup = json_backup_path(source)

        if _path_exists(source_backup):
            _validate_json(
                source_backup,
                private=False,
                uid=context.user_id,
                gid=context.group_id,
            )
            contents_read = True

    for _label, relative, attribute, rotated in HISTORY_TARGETS:
        source = root / relative
        destination = Path(getattr(context.paths, attribute))
        legacy_paths = [source] if _path_exists(source) else []

        if rotated:
            rotated_source = source.with_name(source.name + ".1")

            if _path_exists(rotated_source):
                legacy_paths.append(rotated_source)

        if not legacy_paths:
            continue

        destination_payloads = []

        if _path_exists(destination):
            _private_metadata(
                destination,
                directory=False,
                uid=context.user_id,
                gid=context.group_id,
            )
            destination_payloads.append(
                _read_regular(
                    destination,
                    maximum=MAX_HISTORY_BYTES,
                    label="External history",
                )
            )

        if rotated:
            rotated_destination = destination.with_name(destination.name + ".1")

            if _path_exists(rotated_destination):
                _private_metadata(
                    rotated_destination,
                    directory=False,
                    uid=context.user_id,
                    gid=context.group_id,
                )
                destination_payloads.append(
                    _read_regular(
                        rotated_destination,
                        maximum=MAX_HISTORY_BYTES,
                        label="External history rotation",
                    )
                )

        if not destination_payloads:
            raise CleanupError("Required external history is missing")

        for legacy_path in legacy_paths:
            source_payload = _read_regular(
                legacy_path,
                maximum=MAX_HISTORY_BYTES,
                label="Legacy history",
            )

            if not any(
                source_payload in payload
                for payload in destination_payloads
            ):
                raise CleanupError(
                    "External history does not preserve legacy history"
                )

        histories += len(destination_payloads)
        contents_read = True

    destination_recordings = _media_manifest(
        Path(context.paths.recording_dir),
        require_private=True,
    )
    destination_by_path = {
        entry.relative_path: entry for entry in destination_recordings
    }

    for relative in RECORDING_ROOTS:
        source_root = root / relative

        if not _path_exists(source_root):
            continue

        source_manifest = _media_manifest(source_root, require_private=False)

        for source_entry in source_manifest:
            destination_entry = destination_by_path.get(source_entry.relative_path)

            if (
                destination_entry is None
                or not _same_media_payload(destination_entry, source_entry)
            ):
                raise CleanupError("Protected recording recovery does not match")

            recording_copies += 1
            contents_read = True

    legacy_packages = root / PACKAGE_ROOT

    if _path_exists(legacy_packages):
        source_manifest = _package_manifest(legacy_packages)
        plans = _package_plans(source_manifest)
        destinations = {
            "control": context.paths.controller_apk_dir,
            "monitor": context.paths.monitor_apk_dir,
        }

        for plan in plans:
            destination = Path(destinations[plan.kind]) / plan.destination_name
            destination_entry = _validate_private_package(destination)

            if not _same_package_payload(destination_entry, plan):
                raise CleanupError("External Android package recovery does not match")

            package_copies += 1
            contents_read = True

    return Validation(
        external_documents=documents,
        external_histories=histories,
        recording_copies=recording_copies,
        package_copies=package_copies,
        runtime_contents_read=contents_read,
    )


def _verify_sec006_cleanup(context: ServiceContext) -> None:
    source_root = Path(context.paths.source_root)

    try:
        verify_removed_legacy_sources(
            service_environment=context.environment,
            legacy_firebase_source=(
                source_root
                / "subsystems"
                / "notifications"
                / "firebase-service-account.json"
            ),
            legacy_security_source=(
                source_root
                / "subsystems"
                / "security"
                / "security_state.json"
            ),
        )
    except RuntimeError as exc:
        raise CleanupError("SEC-006 legacy credential cleanup is not complete") from exc


def _handoff_payload(
    *,
    root: Path,
    service: str,
    context: ServiceContext,
    inventory: Inventory,
) -> dict:
    return {
        "schema": 1,
        "service": service,
        "source_root": str(root),
        "created_at": int(time.time()),
        "service_uid": context.user_id,
        "service_gid": context.group_id,
        "environment": {
            name: context.environment[name]
            for name in sorted(PATH_ENVIRONMENT_NAMES)
            if str(context.environment.get(name, "")).strip()
        },
        "state_labels": list(inventory.state_labels),
        "target_count": inventory.target_count,
        "fingerprint": inventory.fingerprint,
        "cleanup_complete": False,
    }


def _write_handoff(path: Path, document: Mapping) -> None:
    path = _absolute(path, "PATH-003 handoff")

    try:
        path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        path.parent.chmod(0o700)
        temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        flags = (
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0)
        )
        descriptor = os.open(temporary, flags, 0o600)

        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(document, handle, sort_keys=True, separators=(",", ":"))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())

        os.replace(temporary, path)
        path.chmod(0o600)
    except OSError as exc:
        try:
            temporary.unlink(missing_ok=True)
        except (OSError, UnboundLocalError):
            pass
        raise CleanupError("PATH-003 handoff could not be written") from exc


def _read_handoff(path: Path, *, root: Path, service: str) -> dict:
    path = _absolute(path, "PATH-003 handoff")
    _private_metadata(
        path,
        directory=False,
        uid=os.geteuid(),
        gid=os.getegid(),
    )
    payload = _read_regular(
        path,
        maximum=256 * 1024,
        label="PATH-003 handoff",
    )

    try:
        document = json.loads(payload.decode("utf-8"))
        created_at = int(document.get("created_at") or 0)
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        TypeError,
        ValueError,
        AttributeError,
    ) as exc:
        raise CleanupError("PATH-003 handoff is malformed") from exc

    now = int(time.time())

    if (
        not isinstance(document, dict)
        or document.get("schema") != 1
        or document.get("service") != service
        or document.get("source_root") != str(root)
        or created_at < now - HANDOFF_MAX_AGE_SECONDS
        or created_at > now + 60
        or document.get("service_uid") != os.geteuid()
        or document.get("service_gid") != os.getegid()
    ):
        raise CleanupError("PATH-003 handoff is invalid or stale")

    return document


def _context_from_handoff(root: Path, handoff: Mapping) -> ServiceContext:
    raw_environment = handoff.get("environment")

    if not isinstance(raw_environment, dict) or any(
        name not in PATH_ENVIRONMENT_NAMES
        or not isinstance(value, str)
        for name, value in raw_environment.items()
    ):
        raise CleanupError("PATH-003 handoff path configuration is invalid")

    paths = runtime_paths_for_service(
        root,
        process_user_id=os.geteuid(),
        environment=raw_environment,
    )
    return ServiceContext(
        process_id=0,
        user_id=os.geteuid(),
        group_id=os.getegid(),
        environment=raw_environment,
        paths=paths,
    )


def _remove_target(root: Path, target: Path) -> tuple[int, int, int]:
    if not _is_within(target, root) or target.resolve(strict=False) == root:
        raise CleanupError("Cleanup target containment validation failed")

    entries = _safe_tree_entries(target)
    files = 0
    directories = 0
    total_bytes = 0

    for path in sorted(entries, key=lambda item: len(item.parts), reverse=True):
        metadata = path.lstat()

        try:
            if stat.S_ISDIR(metadata.st_mode):
                path.rmdir()
                directories += 1
            elif stat.S_ISREG(metadata.st_mode):
                total_bytes += metadata.st_size
                path.unlink()
                files += 1
            else:  # _safe_tree_entries already rejects this.
                raise CleanupError("Cleanup target type changed")
        except OSError as exc:
            raise CleanupError(
                "A validated source-residue target could not be removed"
            ) from exc

    return files, directories, total_bytes


def _inventory_blockers(inventory: Inventory) -> int:
    return (
        inventory.unknown_ignored
        + inventory.blocked_credentials
        + inventory.matter_storage_roots
        + inventory.tracked_target_files
    )


def _print_inventory(inventory: Inventory, *, details: bool = False) -> None:
    print(f"legacy-state-files: {inventory.state_files}")
    print(f"legacy-history-files: {inventory.history_files}")
    print(f"legacy-recordings: {inventory.recording_files}")
    print(f"legacy-android-packages: {inventory.package_files}")
    print(f"replaceable-runtime-files: {inventory.replaceable_files}")
    print(f"obsolete-trash-files: {inventory.trash_files}")
    print(f"cleanup-targets: {inventory.target_count}")
    print(f"preserved-developer-ignored-files: {inventory.preserved_ignored}")
    print(f"unknown-ignored-files: {inventory.unknown_ignored}")
    print(f"blocked-credential-residue: {inventory.blocked_credentials}")
    print(f"blocked-matter-storage-roots: {inventory.matter_storage_roots}")
    print(f"blocked-tracked-source-files: {inventory.tracked_target_files}")

    if details:
        for relative in inventory.unknown_ignored_paths:
            print(f"unknown-ignored-path: {relative}")


def run_preflight(args, root: Path, handoff_path: Path) -> int:
    context = active_service_context(root, args.service)
    _verify_sec006_cleanup(context)
    inventory = build_inventory(root)

    if _inventory_blockers(inventory):
        _print_stage(
            "preflight",
            inventory,
            Validation(),
            gate="BLOCKED",
            destructive=False,
            details=getattr(args, "details", False),
        )
        return 1

    validation = validate_external_recovery(root, inventory, context)
    _write_handoff(
        handoff_path,
        _handoff_payload(
            root=root,
            service=args.service,
            context=context,
            inventory=inventory,
        ),
    )
    _print_stage(
        "preflight",
        inventory,
        validation,
        gate="PASS",
        destructive=False,
        details=getattr(args, "details", False),
    )
    return 0


def run_cleanup(args, root: Path, handoff_path: Path) -> int:
    global _DESTRUCTIVE_STARTED

    require_service_inactive(args.service)
    handoff = _read_handoff(handoff_path, root=root, service=args.service)

    if handoff.get("cleanup_complete") is True:
        raise CleanupError("PATH-003 cleanup handoff was already consumed")

    context = _context_from_handoff(root, handoff)
    inventory = build_inventory(root)

    if _inventory_blockers(inventory):
        raise CleanupError("Source residue changed into a blocked class")

    if (
        inventory.target_count != handoff.get("target_count")
        or inventory.fingerprint != handoff.get("fingerprint")
        or list(inventory.state_labels) != handoff.get("state_labels")
    ):
        raise CleanupError("Source residue changed after preflight")

    validation = validate_external_recovery(root, inventory, context)
    deleted_files = 0
    deleted_directories = 0
    deleted_bytes = 0
    _DESTRUCTIVE_STARTED = bool(inventory.targets)

    for target in inventory.targets:
        files, directories, byte_count = _remove_target(root, target)
        deleted_files += files
        deleted_directories += directories
        deleted_bytes += byte_count

    remaining = build_inventory(root)

    if remaining.target_count or _inventory_blockers(remaining):
        raise CleanupError("Source residue remains after cleanup")

    completed_handoff = dict(handoff)
    completed_handoff.update({
        "cleanup_complete": True,
        "cleanup_completed_at": int(time.time()),
        "deleted_files": deleted_files,
        "deleted_directories": deleted_directories,
        "deleted_bytes": deleted_bytes,
    })
    _write_handoff(handoff_path, completed_handoff)
    _print_stage(
        "cleanup",
        remaining,
        validation,
        gate="PASS",
        destructive=True,
        deleted=(deleted_files, deleted_directories, deleted_bytes),
        details=getattr(args, "details", False),
    )
    return 0


def run_verify(args, root: Path, handoff_path: Path) -> int:
    handoff = _read_handoff(handoff_path, root=root, service=args.service)

    if handoff.get("cleanup_complete") is not True:
        raise CleanupError("PATH-003 cleanup has not completed")

    context = active_service_context(root, args.service)

    if (
        context.user_id != handoff.get("service_uid")
        or context.group_id != handoff.get("service_gid")
    ):
        raise CleanupError("Restarted service identity changed")

    expected_paths = runtime_paths_for_service(
        root,
        process_user_id=context.user_id,
        environment=handoff.get("environment") or {},
    )

    if (
        context.paths.resolved_runtime_destinations()
        != expected_paths.resolved_runtime_destinations()
    ):
        raise CleanupError("Restarted service runtime paths changed")

    _verify_sec006_cleanup(context)
    inventory = build_inventory(root)
    blocked = inventory.target_count + _inventory_blockers(inventory)
    gate = "PASS" if blocked == 0 else "BLOCKED"
    _print_stage(
        "post-restart verification",
        inventory,
        Validation(),
        gate=gate,
        destructive=False,
        details=getattr(args, "details", False),
    )

    if blocked:
        return 1

    try:
        handoff_path.unlink()
    except OSError as exc:
        raise CleanupError("PATH-003 handoff could not be retired") from exc

    return 0


def _print_stage(
    stage: str,
    inventory: Inventory,
    validation: Validation,
    *,
    gate: str,
    destructive: bool,
    deleted: tuple[int, int, int] | None = None,
    details: bool = False,
) -> None:
    print(f"PATH-003 source-residue {stage} completed.")
    print("authoritative-head-match: yes")
    _print_inventory(inventory, details=details)
    print(f"external-json-recovery-files-validated: {validation.external_documents}")
    print(f"external-history-files-validated: {validation.external_histories}")
    print(f"protected-recording-copies-validated: {validation.recording_copies}")
    print(f"external-package-copies-validated: {validation.package_copies}")

    if deleted is not None:
        print(f"source-files-removed: {deleted[0]}")
        print(f"source-directories-removed: {deleted[1]}")
        print(f"source-bytes-removed: {deleted[2]}")

    print(
        "runtime-file-contents-read: "
        + ("yes" if validation.runtime_contents_read else "no")
    )
    print("credential-values-read: no")
    print(
        "destructive-changes-performed: "
        + ("yes" if destructive else "no")
    )
    print(f"PATH-003 {stage} gate: {gate}")


def run(args) -> int:
    root = Path(args.root).resolve(strict=False)
    expected = str(args.expected_head).strip()

    if exact_head(root) != expected:
        print(
            "PATH-003 stopped: authoritative source mismatch; "
            "no runtime data read and no cleanup performed."
        )
        return 2

    if root != SOURCE_ROOT:
        raise CleanupError("PATH-003 must run from its authoritative source root")

    if os.name != "posix" or os.geteuid() == 0:
        raise CleanupError("Run PATH-003 as the non-root KotiBot service user")

    handoff_path = args.handoff_file or _default_handoff_file()

    if args.action == "preflight":
        return run_preflight(args, root, handoff_path)

    if args.action == "cleanup":
        return run_cleanup(args, root, handoff_path)

    return run_verify(args, root, handoff_path)


def main(argv: list[str] | None = None) -> int:
    try:
        return run(_parser().parse_args(argv))
    except CleanupError as exc:
        print(f"PATH-003 stopped: {exc}")
        print("credential-values-read: no")
        print(
            "destructive-changes-performed: "
            + ("yes" if _DESTRUCTIVE_STARTED else "no")
        )
        return 2
    except Exception as exc:
        print(
            "PATH-003 stopped: unexpected fail-closed error: "
            f"{type(exc).__name__}"
        )
        print("credential-values-read: no")
        print(
            "destructive-changes-performed: "
            + ("yes" if _DESTRUCTIVE_STARTED else "no")
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

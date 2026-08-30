"""Central runtime paths for KotiBot.

Runtime data must never be written inside the source repository.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
import os
from pathlib import Path

def _configured_data_root() -> Path:
    configured = str(
        os.environ.get("KOTIBOT_DATA_DIR", "")
    ).strip()

    if configured:
        path = Path(configured).expanduser()

        if not path.is_absolute():
            raise RuntimeError(
                "KOTIBOT_DATA_DIR must be an absolute path"
            )

        return path

    home = Path.home()

    if os.name == "nt":
        local_app_data = str(
            os.environ.get("LOCALAPPDATA", "")
        ).strip()

        if local_app_data:
            return Path(local_app_data) / "KotiBot"

        return home / "AppData" / "Local" / "KotiBot"

    xdg_data_home = str(
        os.environ.get("XDG_DATA_HOME", "")
    ).strip()

    if xdg_data_home:
        return Path(xdg_data_home) / "kotibot"

    return home / ".local" / "share" / "kotibot"


def _configured_cache_root() -> Path:
    configured = str(
        os.environ.get("KOTIBOT_CACHE_DIR", "")
    ).strip()

    if configured:
        path = Path(configured).expanduser()

        if not path.is_absolute():
            raise RuntimeError(
                "KOTIBOT_CACHE_DIR must be an absolute path"
            )

        return path

    home = Path.home()

    if os.name == "nt":
        local_app_data = str(
            os.environ.get("LOCALAPPDATA", "")
        ).strip()

        if local_app_data:
            return Path(local_app_data) / "KotiBot" / "Cache"

        return (
            home
            / "AppData"
            / "Local"
            / "KotiBot"
            / "Cache"
        )

    xdg_cache_home = str(
        os.environ.get("XDG_CACHE_HOME", "")
    ).strip()

    if xdg_cache_home:
        path = Path(xdg_cache_home).expanduser()

        if not path.is_absolute():
            raise RuntimeError(
                "XDG_CACHE_HOME must be an absolute path"
            )

        return path / "kotibot"

    return home / ".cache" / "kotibot"


def _configured_runtime_root(cache_root: Path) -> Path:
    configured = str(
        os.environ.get("KOTIBOT_RUNTIME_DIR", "")
    ).strip()

    if configured:
        path = Path(configured).expanduser()

        if not path.is_absolute():
            raise RuntimeError(
                "KOTIBOT_RUNTIME_DIR must be an absolute path"
            )

        return path

    if os.name == "nt":
        return cache_root / "runtime"

    xdg_runtime_dir = str(
        os.environ.get("XDG_RUNTIME_DIR", "")
    ).strip()

    if xdg_runtime_dir:
        path = Path(xdg_runtime_dir).expanduser()

        if not path.is_absolute():
            raise RuntimeError(
                "XDG_RUNTIME_DIR must be an absolute path"
            )

        return path / "kotibot"

    return cache_root / "runtime"


def _configured_temporary_root(runtime_root: Path) -> Path:
    configured = str(
        os.environ.get("KOTIBOT_TEMP_DIR", "")
    ).strip()

    if configured:
        path = Path(configured).expanduser()

        if not path.is_absolute():
            raise RuntimeError(
                "KOTIBOT_TEMP_DIR must be an absolute path"
            )

        return path

    return runtime_root / "temp"

def _configured_package_root(data_root: Path) -> Path:
    configured = str(
        os.environ.get("KOTIBOT_PACKAGE_DIR", "")
    ).strip()

    if configured:
        path = Path(configured).expanduser()

        if not path.is_absolute():
            raise RuntimeError(
                "KOTIBOT_PACKAGE_DIR must be an absolute path"
            )

        return path

    return data_root / "apks"


def _configured_media_root(data_root: Path) -> Path:
    configured_name = "KOTIBOT_MEDIA_DIR"
    configured = str(
        os.environ.get(configured_name, "")
    ).strip()

    if not configured:
        configured_name = "KOTIBOT_TAPO_RECORDING_DIR"
        configured = str(
            os.environ.get(configured_name, "")
        ).strip()

    if configured:
        path = Path(configured).expanduser()

        if not path.is_absolute():
            raise RuntimeError(
                f"{configured_name} must be an absolute path"
            )

        return path

    return data_root / "state" / "media" / "recordings"


def _is_within(path: Path, parent: Path) -> bool:
    path = path.resolve(strict=False)
    parent = parent.resolve(strict=False)

    return path == parent or parent in path.parents

@dataclass(frozen=True)
class RuntimePaths:
    source_root: Path
    data_root: Path
    cache_root: Path | None = None
    runtime_root: Path | None = None
    temporary_root: Path | None = None
    package_root: Path | None = None
    media_root: Path | None = None

    def __post_init__(self) -> None:
        source_root = Path(self.source_root)
        data_root = Path(self.data_root)
        cache_root = (
            Path(self.cache_root)
            if self.cache_root is not None
            else data_root / "cache"
        )
        runtime_root = (
            Path(self.runtime_root)
            if self.runtime_root is not None
            else cache_root / "runtime"
        )
        temporary_root = (
            Path(self.temporary_root)
            if self.temporary_root is not None
            else runtime_root / "temp"
        )
        package_root = (
            Path(self.package_root)
            if self.package_root is not None
            else data_root / "apks"
        )
        media_root = (
            Path(self.media_root)
            if self.media_root is not None
            else data_root / "state" / "media" / "recordings"
        )

        object.__setattr__(self, "source_root", source_root)
        object.__setattr__(self, "data_root", data_root)
        object.__setattr__(self, "cache_root", cache_root)
        object.__setattr__(self, "runtime_root", runtime_root)
        object.__setattr__(self, "temporary_root", temporary_root)
        object.__setattr__(self, "package_root", package_root)
        object.__setattr__(self, "media_root", media_root)

    @property
    def environment_cache_dir(self) -> Path:
        return Path(self.cache_root) / "environment"

    @property
    def tapo_runtime_dir(self) -> Path:
        return Path(self.runtime_root) / "tapo"

    @property
    def tapo_camera_hls_dir(self) -> Path:
        return self.tapo_runtime_dir / "camera-hls"

    @property
    def video_transcode_dir(self) -> Path:
        return Path(self.temporary_root) / "video-transcode"

    @property
    def recording_dir(self) -> Path:
        return Path(self.media_root)

    @property
    def controller_apk_dir(self) -> Path:
        return Path(self.package_root) / "kotibot-control"

    @property
    def monitor_apk_dir(self) -> Path:
        return Path(self.package_root) / "kotibot-monitor"

    @property
    def state_root(self) -> Path:
        return self.data_root / "state"

    @property
    def log_root(self) -> Path:
        return self.data_root / "logs"

    @property
    def protected_state_root(self) -> Path:
        return self.data_root / "protected"

    @property
    def security_state_dir(self) -> Path:
        return self.protected_state_root / "security"

    @property
    def security_state_file(self) -> Path:
        return self.security_state_dir / "security_state.json"

    @property
    def device_credential_state_dir(self) -> Path:
        return self.protected_state_root / "devices"

    @property
    def device_notification_credentials_file(self) -> Path:
        return (
            self.device_credential_state_dir
            / "notification_credentials.json"
        )

    @property
    def matter_protected_dir(self) -> Path:
        return self.protected_state_root / "matter"

    @property
    def matter_controller_storage_dir(self) -> Path:
        return self.matter_protected_dir / "controller"

    @property
    def matter_subscription_storage_dir(self) -> Path:
        return self.matter_protected_dir / "subscriptions"

    @property
    def activity_log_dir(self) -> Path:
        return self.log_root / "activity"

    @property
    def activity_state_file(self) -> Path:
        return self.activity_log_dir / "activity_state.json"

    @property
    def security_log_dir(self) -> Path:
        return self.log_root / "security"

    @property
    def security_audit_file(self) -> Path:
        return self.security_log_dir / "security_audit.jsonl"

    @property
    def notification_log_dir(self) -> Path:
        return self.log_root / "notifications"

    @property
    def notification_queue_file(self) -> Path:
        return self.notification_log_dir / "notification_queue.jsonl"

    @property
    def server_state_file(self) -> Path:
        return self.state_root / "server_state.json"

    @property
    def automations_dir(self) -> Path:
        return self.state_root / "automations"

    @property
    def security_actions_file(self) -> Path:
        return self.automations_dir / "security_actions.json"

    @property
    def automation_state_file(self) -> Path:
        return self.automations_dir / "automations_state.json"

    @property
    def android_home_dir(self) -> Path:
        return self.state_root / "android-home"

    @property
    def android_home_state_file(self) -> Path:
        return self.android_home_dir / "android_home_state.json"

    @property
    def environment_dir(self) -> Path:
        return self.state_root / "environment"

    @property
    def environment_state_file(self) -> Path:
        return self.environment_dir / "environment_state.json"

    @property
    def matter_dir(self) -> Path:
        return self.state_root / "matter"

    @property
    def matter_state_file(self) -> Path:
        return self.matter_dir / "matter_state.json"

    @property
    def matter_device_state_file(self) -> Path:
        return self.matter_dir / "matter_device_state.json"

    @property
    def tapo_dir(self) -> Path:
        return self.state_root / "tapo"

    @property
    def tapo_device_state_file(self) -> Path:
        return self.tapo_dir / "tapo_device_state.json"

    @property
    def tapo_config_file(self) -> Path:
        return self.tapo_dir / "tapo_config.json"

    @property
    def tapo_lighting_state_file(self) -> Path:
        return self.tapo_dir / "tapo_lighting_state.json"

    def resolved_runtime_destinations(self) -> dict[str, Path]:
        """Return every declared runtime destination by stable name.

        Dataclass roots and Path-valued properties are discovered together so
        a newly added resolver cannot bypass source-containment validation by
        being omitted from a separate hand-maintained allowlist.
        """
        destinations = {}

        for field in fields(self):
            if field.name == "source_root":
                continue

            value = getattr(self, field.name)

            if isinstance(value, Path):
                destinations[field.name] = value

        for name, descriptor in vars(type(self)).items():
            if not isinstance(descriptor, property):
                continue

            value = getattr(self, name)

            if isinstance(value, Path):
                destinations[name] = value

        return dict(sorted(destinations.items()))

    def validate(self) -> "RuntimePaths":
        destinations = self.resolved_runtime_destinations()

        if any(
            not destination.is_absolute()
            for destination in destinations.values()
        ):
            raise RuntimeError(
                "KotiBot runtime destinations must be absolute"
            )

        if any(
            _is_within(destination, self.source_root)
            for destination in destinations.values()
        ):
            raise RuntimeError(
                "KotiBot runtime data must be outside the source tree"
            )

        return self

def build_runtime_paths(source_root: Path) -> RuntimePaths:
    data_root = _configured_data_root().resolve(strict=False)
    cache_root = _configured_cache_root().resolve(strict=False)
    runtime_root = _configured_runtime_root(
        cache_root
    ).resolve(strict=False)
    temporary_root = _configured_temporary_root(
        runtime_root
    ).resolve(strict=False)
    package_root = _configured_package_root(
        data_root
    ).resolve(strict=False)
    media_root = _configured_media_root(
        data_root
    ).resolve(strict=False)

    return RuntimePaths(
        source_root=Path(source_root).resolve(strict=False),
        data_root=data_root,
        cache_root=cache_root,
        runtime_root=runtime_root,
        temporary_root=temporary_root,
        package_root=package_root,
        media_root=media_root,
    ).validate()

def prepare_runtime_directories(paths: RuntimePaths) -> None:
    for directory in (
        paths.data_root,
        paths.state_root,
        paths.log_root,
        paths.protected_state_root,
        Path(paths.cache_root),
        Path(paths.runtime_root),
        Path(paths.temporary_root),
        Path(paths.package_root),
        Path(paths.media_root),
        paths.environment_cache_dir,
        paths.tapo_runtime_dir,
        paths.tapo_camera_hls_dir,
        paths.video_transcode_dir,
        paths.controller_apk_dir,
        paths.monitor_apk_dir,
        paths.security_state_dir,
        paths.device_credential_state_dir,
        paths.matter_protected_dir,
        paths.activity_log_dir,
        paths.security_log_dir,
        paths.notification_log_dir,
        paths.automations_dir,
        paths.android_home_dir,
        paths.environment_dir,
        paths.matter_dir,
        paths.tapo_dir,
    ):
        directory.mkdir(
            parents=True,
            exist_ok=True,
            mode=0o700,
        )

        if os.name != "nt":
            os.chmod(directory, 0o700)
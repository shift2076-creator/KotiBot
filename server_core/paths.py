"""Central runtime paths for KotiBot.

Runtime data must never be written inside the source repository.
"""

from __future__ import annotations

from dataclasses import dataclass
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


def _is_within(path: Path, parent: Path) -> bool:
    path = path.resolve(strict=False)
    parent = parent.resolve(strict=False)

    return path == parent or parent in path.parents


@dataclass(frozen=True)
class RuntimePaths:
    source_root: Path
    data_root: Path

    @property
    def state_root(self) -> Path:
        return self.data_root / "state"

    @property
    def log_root(self) -> Path:
        return self.data_root / "logs"

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
    def tapo_dir(self) -> Path:
        return self.state_root / "tapo"

    @property
    def tapo_lighting_state_file(self) -> Path:
        return self.tapo_dir / "tapo_lighting_state.json"

    def validate(self) -> "RuntimePaths":
        runtime_roots = (
            self.data_root,
            self.state_root,
            self.log_root,
        )

        if any(
            _is_within(root, self.source_root)
            for root in runtime_roots
        ):
            raise RuntimeError(
                "KotiBot runtime data must be outside the source tree"
            )

        return self

def build_runtime_paths(source_root: Path) -> RuntimePaths:
    return RuntimePaths(
        source_root=Path(source_root).resolve(strict=False),
        data_root=_configured_data_root().resolve(strict=False),
    ).validate()

def prepare_runtime_directories(paths: RuntimePaths) -> None:
    for directory in (
        paths.data_root,
        paths.state_root,
        paths.log_root,
        paths.activity_log_dir,
        paths.security_log_dir,
        paths.automations_dir,
        paths.android_home_dir,
        paths.tapo_dir,
    ):
        directory.mkdir(
            parents=True,
            exist_ok=True,
            mode=0o700,
        )

        if os.name != "nt":
            os.chmod(directory, 0o700)
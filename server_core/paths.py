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
    def server_state_file(self) -> Path:
        return self.state_root / "server_state.json"

    @property
    def automations_dir(self) -> Path:
        return self.state_root / "automations"

    @property
    def security_actions_file(self) -> Path:
        return self.automations_dir / "security_actions.json"

    def validate(self) -> "RuntimePaths":
        if _is_within(self.data_root, self.source_root):
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
        paths.automations_dir,
    ):
        directory.mkdir(
            parents=True,
            exist_ok=True,
            mode=0o700,
        )

        if os.name != "nt":
            os.chmod(directory, 0o700)
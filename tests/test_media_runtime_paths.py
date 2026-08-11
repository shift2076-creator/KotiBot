import ast
from datetime import datetime
import os
from pathlib import Path
import stat
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from server_core.paths import (
    build_runtime_paths,
    prepare_runtime_directories,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def read_source(relative_path):
    path = REPOSITORY_ROOT / relative_path
    source = path.read_text(encoding="utf-8")
    ast.parse(source, filename=str(path))
    return source


def load_tapo_recording_functions():
    path = (
        REPOSITORY_ROOT
        / "subsystems"
        / "client-tapo"
        / "tapo_control.py"
    )
    tree = ast.parse(
        path.read_text(encoding="utf-8"),
        filename=str(path),
    )
    wanted = {
        "configure_tapo_camera_recording_root",
        "tapo_camera_recording_root",
        "clean_tapo_recording_label",
        "tapo_camera_recording_path",
    }
    selected = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name in wanted
    ]
    module = ast.Module(body=selected, type_ignores=[])
    namespace = {
        "Path": Path,
        "datetime": datetime,
        "os": os,
        "TAPO_CAMERA_RECORDING_ROOT": None,
    }
    exec(compile(module, str(path), "exec"), namespace)
    return namespace


class MediaRuntimePathTests(unittest.TestCase):
    def configured_environment(self, root):
        return {
            "KOTIBOT_DATA_DIR": str(root / "data"),
            "KOTIBOT_CACHE_DIR": str(root / "cache"),
            "KOTIBOT_RUNTIME_DIR": str(root / "runtime"),
            "KOTIBOT_PACKAGE_DIR": str(root / "apks"),
            "KOTIBOT_MEDIA_DIR": str(root / "media"),
        }

    def test_configured_media_root(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_root = root / "source"
            source_root.mkdir()

            with patch.dict(
                os.environ,
                self.configured_environment(root),
                clear=True,
            ):
                paths = build_runtime_paths(source_root)

            self.assertEqual(paths.media_root, root / "media")
            self.assertEqual(paths.recording_dir, root / "media")

    def test_default_media_root_uses_protected_state_tree(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_root = root / "source"
            source_root.mkdir()
            environment = self.configured_environment(root)
            environment.pop("KOTIBOT_MEDIA_DIR")

            with patch.dict(
                os.environ,
                environment,
                clear=True,
            ):
                paths = build_runtime_paths(source_root)

            self.assertEqual(
                paths.recording_dir,
                root / "data" / "state" / "media" / "recordings",
            )

    def test_legacy_tapo_recording_override_remains_compatible(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_root = root / "source"
            source_root.mkdir()
            environment = self.configured_environment(root)
            environment.pop("KOTIBOT_MEDIA_DIR")
            environment["KOTIBOT_TAPO_RECORDING_DIR"] = str(
                root / "legacy-configured-media"
            )

            with patch.dict(
                os.environ,
                environment,
                clear=True,
            ):
                paths = build_runtime_paths(source_root)

            self.assertEqual(
                paths.recording_dir,
                root / "legacy-configured-media",
            )

    def test_media_override_must_be_absolute_and_external(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_root = root / "source"
            source_root.mkdir()

            for configured, message in (
                (
                    "relative/media",
                    "KOTIBOT_MEDIA_DIR must be an absolute path",
                ),
                (
                    str(source_root / "media"),
                    "outside the source tree",
                ),
            ):
                environment = self.configured_environment(root)
                environment["KOTIBOT_MEDIA_DIR"] = configured

                with self.subTest(configured=configured):
                    with patch.dict(
                        os.environ,
                        environment,
                        clear=True,
                    ):
                        with self.assertRaisesRegex(
                            RuntimeError,
                            message,
                        ):
                            build_runtime_paths(source_root)

    def test_prepare_creates_private_media_root(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_root = root / "source"
            source_root.mkdir()

            with patch.dict(
                os.environ,
                self.configured_environment(root),
                clear=True,
            ):
                paths = build_runtime_paths(source_root)
                prepare_runtime_directories(paths)

            self.assertTrue(paths.recording_dir.is_dir())

            if os.name != "nt":
                self.assertEqual(
                    stat.S_IMODE(paths.recording_dir.stat().st_mode),
                    0o700,
                )

    def test_runtime_threads_one_recording_root_to_both_producers(self):
        server_source = read_source("kotibot_server.py")
        subsystem_source = read_source("server_core/subsystems.py")
        video_source = read_source(
            "subsystems/video/video_routes.py"
        )
        tapo_route_source = read_source(
            "subsystems/client-tapo/tapo_routes.py"
        )
        tapo_control_source = read_source(
            "subsystems/client-tapo/tapo_control.py"
        )

        self.assertIn(
            "RECORDING_DIR = RUNTIME_PATHS.recording_dir",
            server_source,
        )
        self.assertIn(
            "'recording_dir': RECORDING_DIR",
            server_source,
        )
        self.assertIn(
            "recording_dir = Path(ctx['recording_dir'])",
            subsystem_source,
        )
        self.assertEqual(
            subsystem_source.count(
                "'recording_dir': recording_dir"
            ),
            2,
        )
        self.assertIn(
            "video_dir = Path(ctx['recording_dir'])",
            video_source,
        )
        self.assertNotIn(
            "base_dir / 'subsystems' / 'video' / 'videos'",
            video_source,
        )
        self.assertIn(
            "configure_tapo_camera_recording_root(",
            tapo_route_source,
        )
        self.assertIn(
            "Path(ctx['recording_dir'])",
            tapo_route_source,
        )
        self.assertNotIn(
            "Path(__file__).resolve().parents[2]",
            tapo_control_source,
        )

    def test_tapo_recording_path_uses_configured_private_root(self):
        functions = load_tapo_recording_functions()
        configure = functions[
            "configure_tapo_camera_recording_root"
        ]
        recording_path = functions[
            "tapo_camera_recording_path"
        ]

        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "media"
            configure(root)
            path = recording_path(
                {
                    "deviceID": "tapo:front-entry",
                    "clientName": "Entry Camera",
                    "zone_name": "Entry",
                }
            )

            self.assertEqual(path.parent.parent, root)
            self.assertEqual(path.suffix, ".mp4")

            if os.name != "nt":
                self.assertEqual(
                    stat.S_IMODE(root.stat().st_mode),
                    0o700,
                )
                self.assertEqual(
                    stat.S_IMODE(path.parent.stat().st_mode),
                    0o700,
                )


if __name__ == "__main__":
    unittest.main()

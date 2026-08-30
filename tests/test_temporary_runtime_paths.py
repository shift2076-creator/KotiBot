import ast
import errno
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from server_core.paths import (
    RuntimePaths,
    build_runtime_paths,
    prepare_runtime_directories,
)
from server_core.private_paths import (
    ensure_private_directory,
    ensure_private_file,
    verify_private_descriptor,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def read_source(relative_path):
    path = REPOSITORY_ROOT / relative_path
    source = path.read_text(encoding="utf-8")
    ast.parse(source, filename=str(path))
    return source


def load_video_staging_functions(video_transcode_dir):
    path = REPOSITORY_ROOT / "subsystems" / "video" / "video_routes.py"
    tree = ast.parse(
        path.read_text(encoding="utf-8"),
        filename=str(path),
    )
    register = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "register_video_routes"
    )
    wanted = {
        "replace_staged_video",
        "normalize_video_rotation",
    }
    selected = [
        node
        for node in register.body
        if isinstance(node, ast.FunctionDef)
        and node.name in wanted
    ]
    module = ast.Module(body=selected, type_ignores=[])
    ast.fix_missing_locations(module)
    namespace = {
        "Path": Path,
        "errno": errno,
        "ensure_private_directory": ensure_private_directory,
        "ensure_private_file": ensure_private_file,
        "os": os,
        "shutil": shutil,
        "stat": stat,
        "subprocess": subprocess,
        "tempfile": tempfile,
        "verify_private_descriptor": verify_private_descriptor,
        "video_transcode_dir": Path(video_transcode_dir),
        "safe_int": lambda value: int(value) if value is not None else None,
    }
    exec(compile(module, str(path), "exec"), namespace)
    return namespace


class TemporaryRuntimePathTests(unittest.TestCase):
    @staticmethod
    def configured_environment(root):
        return {
            "KOTIBOT_DATA_DIR": str(root / "data"),
            "KOTIBOT_CACHE_DIR": str(root / "cache"),
            "KOTIBOT_RUNTIME_DIR": str(root / "runtime"),
            "KOTIBOT_TEMP_DIR": str(root / "temporary"),
            "KOTIBOT_PACKAGE_DIR": str(root / "apks"),
            "KOTIBOT_MEDIA_DIR": str(root / "media"),
        }

    def test_configured_temporary_root_and_transcode_directory_are_external(self):
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

            self.assertEqual(paths.temporary_root, root / "temporary")
            self.assertEqual(
                paths.video_transcode_dir,
                root / "temporary" / "video-transcode",
            )
            self.assertNotIn(
                source_root.resolve(),
                paths.video_transcode_dir.resolve().parents,
            )

    def test_default_temporary_root_uses_the_os_runtime_root(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_root = root / "source"
            source_root.mkdir()
            environment = self.configured_environment(root)
            environment.pop("KOTIBOT_TEMP_DIR")

            with patch.dict(
                os.environ,
                environment,
                clear=True,
            ):
                paths = build_runtime_paths(source_root)

            self.assertEqual(
                paths.temporary_root,
                root / "runtime" / "temp",
            )

            direct_paths = RuntimePaths(
                source_root=source_root,
                data_root=root / "direct-data",
            ).validate()
            self.assertEqual(
                direct_paths.temporary_root,
                root / "direct-data" / "cache" / "runtime" / "temp",
            )

    def test_temporary_override_must_be_absolute_and_external(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_root = root / "source"
            source_root.mkdir()

            for configured, message in (
                (
                    "relative/temp",
                    "KOTIBOT_TEMP_DIR must be an absolute path",
                ),
                (
                    str(source_root / "temp"),
                    "outside the source tree",
                ),
            ):
                environment = self.configured_environment(root)
                environment["KOTIBOT_TEMP_DIR"] = configured

                with self.subTest(configured=configured):
                    with patch.dict(
                        os.environ,
                        environment,
                        clear=True,
                    ):
                        with self.assertRaisesRegex(RuntimeError, message):
                            build_runtime_paths(source_root)

    def test_prepare_creates_private_temporary_directories(self):
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

            for directory in (
                paths.temporary_root,
                paths.video_transcode_dir,
            ):
                directory = Path(directory)
                self.assertTrue(directory.is_dir())

                if os.name != "nt":
                    self.assertEqual(
                        stat.S_IMODE(directory.stat().st_mode),
                        0o700,
                    )

    def test_video_transcode_directory_is_threaded_to_the_owner(self):
        server_source = read_source("kotibot_server.py")
        subsystem_source = read_source("server_core/subsystems.py")
        video_source = read_source("subsystems/video/video_routes.py")

        self.assertIn(
            "VIDEO_TRANSCODE_DIR = RUNTIME_PATHS.video_transcode_dir",
            server_source,
        )
        self.assertIn(
            "'video_transcode_dir': VIDEO_TRANSCODE_DIR",
            server_source,
        )
        self.assertIn(
            "video_transcode_dir = Path(ctx['video_transcode_dir'])",
            subsystem_source,
        )
        self.assertIn(
            "'video_transcode_dir': video_transcode_dir",
            subsystem_source,
        )
        self.assertIn(
            "video_transcode_dir = Path(ctx['video_transcode_dir'])",
            video_source,
        )
        self.assertNotIn(
            'path.with_name(f"{path.stem}.rotating{path.suffix}")',
            video_source,
        )

    def test_rotation_transcodes_in_temporary_root_and_commits_cleanly(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            transcode_dir = root / "temporary" / "video-transcode"
            recording_dir = root / "media"
            recording_dir.mkdir()
            path = recording_dir / "camera.mp4"
            path.write_bytes(b"original")
            functions = load_video_staging_functions(transcode_dir)
            commands = []

            def run_ffmpeg(command, **kwargs):
                commands.append(command)
                Path(command[-1]).write_bytes(b"rotated")
                return subprocess.CompletedProcess(command, 0, "")

            with (
                patch.object(shutil, "which", return_value="/usr/bin/ffmpeg"),
                patch.object(subprocess, "run", side_effect=run_ffmpeg),
            ):
                changed = functions["normalize_video_rotation"](
                    path,
                    90,
                )

            self.assertTrue(changed)
            self.assertEqual(path.read_bytes(), b"rotated")
            self.assertEqual(Path(commands[0][-1]).parent, transcode_dir)
            self.assertEqual(list(transcode_dir.iterdir()), [])

            if os.name != "nt":
                self.assertEqual(
                    stat.S_IMODE(path.stat().st_mode),
                    0o600,
                )
                self.assertEqual(
                    stat.S_IMODE(recording_dir.stat().st_mode),
                    0o700,
                )
                self.assertEqual(
                    stat.S_IMODE(transcode_dir.stat().st_mode),
                    0o700,
                )

    def test_cross_filesystem_commit_uses_atomic_destination_staging(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            transcode_dir = root / "temporary" / "video-transcode"
            recording_dir = root / "media"
            transcode_dir.mkdir(parents=True)
            recording_dir.mkdir()
            staged_path = transcode_dir / "camera.rotating.mp4"
            destination = recording_dir / "camera.mp4"
            staged_path.write_bytes(b"rotated")
            destination.write_bytes(b"original")
            functions = load_video_staging_functions(transcode_dir)
            original_replace = os.replace

            def replace_with_cross_device_boundary(source, target):
                if Path(source) == staged_path and Path(target) == destination:
                    raise OSError(errno.EXDEV, "cross-device link")

                return original_replace(source, target)

            with patch.object(
                os,
                "replace",
                side_effect=replace_with_cross_device_boundary,
            ):
                functions["replace_staged_video"](
                    staged_path,
                    destination,
                )

            self.assertEqual(destination.read_bytes(), b"rotated")
            self.assertFalse(staged_path.exists())
            self.assertEqual(
                [item for item in recording_dir.iterdir() if item != destination],
                [],
            )

            if os.name != "nt":
                self.assertEqual(
                    stat.S_IMODE(recording_dir.stat().st_mode),
                    0o700,
                )
                self.assertEqual(
                    stat.S_IMODE(destination.stat().st_mode),
                    0o600,
                )


if __name__ == "__main__":
    unittest.main()

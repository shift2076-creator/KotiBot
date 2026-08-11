import os
from pathlib import Path
import stat
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from server_core.paths import (
    RuntimePaths,
    build_runtime_paths,
    prepare_runtime_directories,
)


class CacheRuntimePathTests(unittest.TestCase):
    def test_configured_roots_and_derived_paths_are_external(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_root = root / "source"
            data_root = root / "data"
            cache_root = root / "cache"
            runtime_root = root / "runtime"
            source_root.mkdir()

            with patch.dict(
                os.environ,
                {
                    "KOTIBOT_DATA_DIR": str(data_root),
                    "KOTIBOT_CACHE_DIR": str(cache_root),
                    "KOTIBOT_RUNTIME_DIR": str(runtime_root),
                },
                clear=True,
            ):
                paths = build_runtime_paths(source_root)

            expected = {
                paths.cache_root: cache_root,
                paths.runtime_root: runtime_root,
                paths.environment_cache_dir:
                    cache_root / "environment",
                paths.tapo_runtime_dir:
                    runtime_root / "tapo",
                paths.tapo_camera_hls_dir:
                    runtime_root / "tapo" / "camera-hls",
            }

            for actual, wanted in expected.items():
                self.assertEqual(actual, wanted)
                self.assertNotIn(
                    source_root.resolve(),
                    Path(actual).resolve().parents,
                )

    def test_direct_construction_retains_safe_test_defaults(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_root = root / "source"
            data_root = root / "data"
            source_root.mkdir()

            paths = RuntimePaths(
                source_root=source_root,
                data_root=data_root,
            ).validate()

            self.assertEqual(
                paths.cache_root,
                data_root / "cache",
            )
            self.assertEqual(
                paths.runtime_root,
                data_root / "cache" / "runtime",
            )

    def test_prepare_creates_private_cache_directories(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_root = root / "source"
            data_root = root / "data"
            cache_root = root / "cache"
            runtime_root = root / "runtime"
            source_root.mkdir()

            with patch.dict(
                os.environ,
                {
                    "KOTIBOT_DATA_DIR": str(data_root),
                    "KOTIBOT_CACHE_DIR": str(cache_root),
                    "KOTIBOT_RUNTIME_DIR": str(runtime_root),
                },
                clear=True,
            ):
                paths = build_runtime_paths(source_root)
                prepare_runtime_directories(paths)

            for directory in (
                paths.cache_root,
                paths.runtime_root,
                paths.environment_cache_dir,
                paths.tapo_runtime_dir,
                paths.tapo_camera_hls_dir,
            ):
                directory = Path(directory)
                self.assertTrue(directory.is_dir())

                if os.name != "nt":
                    self.assertEqual(
                        stat.S_IMODE(directory.stat().st_mode),
                        0o700,
                    )

    def test_relative_cache_and_runtime_overrides_are_rejected(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_root = root / "source"
            data_root = root / "data"
            cache_root = root / "cache"
            runtime_root = root / "runtime"
            source_root.mkdir()

            for variable_name in (
                "KOTIBOT_CACHE_DIR",
                "KOTIBOT_RUNTIME_DIR",
            ):
                environment = {
                    "KOTIBOT_DATA_DIR": str(data_root),
                    "KOTIBOT_CACHE_DIR": str(cache_root),
                    "KOTIBOT_RUNTIME_DIR": str(runtime_root),
                }
                environment[variable_name] = "relative/path"

                with self.subTest(variable_name=variable_name):
                    with patch.dict(
                        os.environ,
                        environment,
                        clear=True,
                    ):
                        with self.assertRaisesRegex(
                            RuntimeError,
                            f"{variable_name} must be an absolute path",
                        ):
                            build_runtime_paths(source_root)

    def test_cache_and_runtime_roots_inside_source_are_rejected(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_root = root / "source"
            data_root = root / "data"
            cache_root = root / "cache"
            runtime_root = root / "runtime"
            source_root.mkdir()

            for variable_name in (
                "KOTIBOT_CACHE_DIR",
                "KOTIBOT_RUNTIME_DIR",
            ):
                environment = {
                    "KOTIBOT_DATA_DIR": str(data_root),
                    "KOTIBOT_CACHE_DIR": str(cache_root),
                    "KOTIBOT_RUNTIME_DIR": str(runtime_root),
                }
                environment[variable_name] = str(
                    source_root / variable_name.lower()
                )

                with self.subTest(variable_name=variable_name):
                    with patch.dict(
                        os.environ,
                        environment,
                        clear=True,
                    ):
                        with self.assertRaisesRegex(
                            RuntimeError,
                            "outside the source tree",
                        ):
                            build_runtime_paths(source_root)


if __name__ == "__main__":
    unittest.main()
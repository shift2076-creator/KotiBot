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


SOURCE_ROOT = Path(__file__).resolve().parents[1]


class RemainingStateRuntimePathTests(unittest.TestCase):
    def test_remaining_state_files_are_outside_source_tree(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_root = root / "source"
            data_root = root / "app-data"
            source_root.mkdir()

            with patch.dict(
                os.environ,
                {"KOTIBOT_DATA_DIR": str(data_root)},
                clear=True,
            ):
                paths = build_runtime_paths(source_root)

            expected = {
                paths.android_home_state_file:
                    data_root / "state" / "android-home"
                    / "android_home_state.json",
                paths.environment_state_file:
                    data_root / "state" / "environment"
                    / "environment_state.json",
                paths.matter_device_state_file:
                    data_root / "state" / "matter"
                    / "matter_device_state.json",
                paths.tapo_device_state_file:
                    data_root / "state" / "tapo"
                    / "tapo_device_state.json",
            }

            for actual, wanted in expected.items():
                self.assertEqual(actual, wanted)
                self.assertNotIn(
                    source_root.resolve(),
                    actual.resolve().parents,
                )

    def test_prepare_creates_private_state_directories(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_root = root / "source"
            data_root = root / "app-data"
            source_root.mkdir()

            with patch.dict(
                os.environ,
                {"KOTIBOT_DATA_DIR": str(data_root)},
                clear=True,
            ):
                paths = build_runtime_paths(source_root)
                prepare_runtime_directories(paths)

            for directory in (
                paths.android_home_dir,
                paths.environment_dir,
                paths.matter_dir,
                paths.tapo_dir,
            ):
                self.assertTrue(directory.is_dir())

                if os.name != "nt":
                    mode = stat.S_IMODE(directory.stat().st_mode)
                    self.assertEqual(mode, 0o700)

    def test_server_wires_remaining_state_files_to_runtime_paths(self):
        source = (SOURCE_ROOT / "kotibot_server.py").read_text(
            encoding="utf-8"
        )

        expected_assignments = (
            "TAPO_DEVICE_STATE_FILE = "
            "RUNTIME_PATHS.tapo_device_state_file",
            "MATTER_DEVICE_STATE_FILE = "
            "RUNTIME_PATHS.matter_device_state_file",
            "ANDROID_HOME_STATE_FILE = "
            "RUNTIME_PATHS.android_home_state_file",
            "ENVIRONMENT_STATE_FILE = "
            "RUNTIME_PATHS.environment_state_file",
        )

        for assignment in expected_assignments:
            self.assertIn(assignment, source)

        rejected_assignments = (
            "TAPO_DEVICE_STATE_FILE = "
            "CLIENT_TAPO_DIR / 'tapo_device_state.json'",
            "MATTER_DEVICE_STATE_FILE = "
            "MATTER_DIR / 'matter_device_state.json'",
        )

        for assignment in rejected_assignments:
            self.assertNotIn(assignment, source)

    def test_environment_requires_explicit_runtime_files(self):
        source = (
            SOURCE_ROOT
            / "subsystems"
            / "environment"
            / "environment_routes.py"
        ).read_text(encoding="utf-8")

        self.assertIn(
            'state_file = Path(context["state_file"])',
            source,
        )
        self.assertIn(
            'matter_state_file = Path(context["matter_state_file"])',
            source,
        )
        self.assertNotIn(
            'state_file = environment_dir / "environment_state.json"',
            source,
        )


if __name__ == "__main__":
    unittest.main()

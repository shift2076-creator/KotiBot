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


class RuntimePathTests(unittest.TestCase):
    def test_activity_history_is_outside_source_tree(self):
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

            self.assertEqual(
                paths.activity_state_file,
                data_root / "logs" / "activity" / "activity_state.json",
            )
            self.assertNotIn(
                source_root.resolve(),
                paths.activity_state_file.resolve().parents,
            )

    def test_security_audit_is_outside_source_tree(self):
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

            self.assertEqual(
                paths.security_audit_file,
                data_root / "logs" / "security" / "security_audit.jsonl",
            )
            self.assertNotIn(
                source_root.resolve(),
                paths.security_audit_file.resolve().parents,
            )

    def test_prepare_creates_private_log_directories(self):
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
                paths.activity_log_dir,
                paths.security_log_dir,
            ):
                self.assertTrue(directory.is_dir())

                if os.name != "nt":
                    mode = stat.S_IMODE(
                        directory.stat().st_mode
                    )
                    self.assertEqual(mode, 0o700)

    def test_data_root_inside_source_tree_is_rejected(self):
        with TemporaryDirectory() as temp_dir:
            source_root = Path(temp_dir) / "source"
            source_root.mkdir()

            with patch.dict(
                os.environ,
                {
                    "KOTIBOT_DATA_DIR": str(
                        source_root / "runtime"
                    )
                },
                clear=True,
            ):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "outside the source tree",
                ):
                    build_runtime_paths(source_root)


if __name__ == "__main__":
    unittest.main()

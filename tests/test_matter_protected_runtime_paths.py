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


class MatterProtectedRuntimePathTests(unittest.TestCase):
    def test_matter_storage_paths_are_explicit_and_protected(self):
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
                paths.matter_controller_storage_dir,
                data_root / "protected" / "matter" / "controller",
            )
            self.assertEqual(
                paths.matter_subscription_storage_dir,
                data_root / "protected" / "matter" / "subscriptions",
            )

            for storage_dir in (
                paths.matter_controller_storage_dir,
                paths.matter_subscription_storage_dir,
            ):
                self.assertNotIn(
                    source_root.resolve(),
                    storage_dir.resolve().parents,
                )

    def test_prepare_creates_only_the_private_matter_parent(self):
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

            self.assertTrue(paths.matter_protected_dir.is_dir())
            self.assertFalse(paths.matter_controller_storage_dir.exists())
            self.assertFalse(paths.matter_subscription_storage_dir.exists())

            if os.name != "nt":
                mode = stat.S_IMODE(
                    paths.matter_protected_dir.stat().st_mode
                )
                self.assertEqual(mode, 0o700)


if __name__ == "__main__":
    unittest.main()

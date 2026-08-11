import importlib.util
import os
from pathlib import Path
import stat
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
TOOL_PATH = (
    REPOSITORY_ROOT
    / "tools"
    / "path001c7_migrate_recordings.py"
)


def load_tool():
    spec = importlib.util.spec_from_file_location(
        "path001c7_migrate_recordings",
        TOOL_PATH,
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class RecordingMigrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tool = load_tool()

    def environment(self, root):
        return {
            "KOTIBOT_DATA_DIR": str(root / "data"),
            "KOTIBOT_CACHE_DIR": str(root / "cache"),
            "KOTIBOT_RUNTIME_DIR": str(root / "runtime"),
            "KOTIBOT_PACKAGE_DIR": str(root / "apks"),
            "KOTIBOT_MEDIA_DIR": str(root / "media"),
        }

    def run_migration(self, source_root, *, copy_requested):
        with (
            patch.object(self.tool, "SOURCE_ROOT", source_root),
            patch.object(
                self.tool,
                "require_operator_identity",
            ),
            patch.object(
                self.tool,
                "require_service_inactive",
            ),
        ):
            return self.tool.migrate_recordings(
                copy_requested=copy_requested,
            )

    def test_copy_preserves_payload_timestamp_and_legacy_source(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_root = root / "source"
            legacy_root = (
                source_root
                / "subsystems"
                / "video"
                / "videos"
            )
            day = legacy_root / "2026-08-11"
            day.mkdir(parents=True)
            legacy_file = day / "Entry Camera.mp4"
            payload = b"recording-payload"
            legacy_file.write_bytes(payload)
            expected_mtime_ns = 1_725_000_000_123_456_789
            os.utime(
                legacy_file,
                ns=(expected_mtime_ns, expected_mtime_ns),
            )
            before = legacy_file.stat()

            with patch.dict(
                os.environ,
                self.environment(root),
                clear=True,
            ):
                result = self.run_migration(
                    source_root,
                    copy_requested=True,
                )

            destination = (
                root
                / "media"
                / "2026-08-11"
                / "Entry Camera.mp4"
            )
            self.assertEqual(result.file_count, 1)
            self.assertEqual(result.total_bytes, len(payload))
            self.assertEqual(result.newly_copied_files, 1)
            self.assertEqual(result.previously_verified_files, 0)
            self.assertEqual(destination.read_bytes(), payload)
            self.assertEqual(
                destination.stat().st_mtime_ns,
                expected_mtime_ns,
            )
            self.assertEqual(legacy_file.read_bytes(), payload)
            self.assertEqual(
                legacy_file.stat().st_mtime_ns,
                before.st_mtime_ns,
            )

            if os.name != "nt":
                self.assertEqual(
                    stat.S_IMODE(destination.parent.stat().st_mode),
                    0o700,
                )
                self.assertEqual(
                    stat.S_IMODE(destination.stat().st_mode),
                    0o600,
                )

    def test_copy_is_idempotent_and_revalidates_existing_media(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_root = root / "source"
            legacy_root = (
                source_root
                / "subsystems"
                / "video"
                / "videos"
            )
            legacy_root.mkdir(parents=True)
            legacy_file = legacy_root / "recording.mp4"
            legacy_file.write_bytes(b"stable")

            with patch.dict(
                os.environ,
                self.environment(root),
                clear=True,
            ):
                self.run_migration(
                    source_root,
                    copy_requested=True,
                )
                result = self.run_migration(
                    source_root,
                    copy_requested=True,
                )

            self.assertEqual(result.newly_copied_files, 0)
            self.assertEqual(result.previously_verified_files, 1)

    def test_preflight_does_not_create_or_change_storage(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_root = root / "source"
            legacy_root = (
                source_root
                / "subsystems"
                / "video"
                / "videos"
            )
            legacy_root.mkdir(parents=True)
            legacy_file = legacy_root / "recording.mp4"
            legacy_file.write_bytes(b"preflight")

            with patch.dict(
                os.environ,
                self.environment(root),
                clear=True,
            ):
                result = self.run_migration(
                    source_root,
                    copy_requested=False,
                )

            self.assertFalse((root / "media").exists())
            self.assertEqual(result.file_count, 1)
            self.assertEqual(result.newly_copied_files, 0)
            self.assertEqual(legacy_file.read_bytes(), b"preflight")

    def test_conflicting_destination_is_rejected_without_overwrite(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_root = root / "source"
            legacy_root = (
                source_root
                / "subsystems"
                / "video"
                / "videos"
            )
            legacy_root.mkdir(parents=True)
            legacy_file = legacy_root / "recording.mp4"
            legacy_file.write_bytes(b"legacy")
            destination_root = root / "media"
            destination_root.mkdir(mode=0o700)
            destination = destination_root / "recording.mp4"
            destination.write_bytes(b"different")

            if os.name != "nt":
                os.chmod(destination_root, 0o700)
                os.chmod(destination, 0o600)

            with patch.dict(
                os.environ,
                self.environment(root),
                clear=True,
            ):
                with self.assertRaisesRegex(
                    self.tool.MigrationError,
                    "differs from its legacy source",
                ):
                    self.run_migration(
                        source_root,
                        copy_requested=True,
                    )

            self.assertEqual(destination.read_bytes(), b"different")
            self.assertEqual(legacy_file.read_bytes(), b"legacy")

    @unittest.skipUnless(
        hasattr(os, "symlink"),
        "symlinks are unavailable",
    )
    def test_symlinked_legacy_entry_is_rejected(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_root = root / "source"
            legacy_root = (
                source_root
                / "subsystems"
                / "video"
                / "videos"
            )
            legacy_root.mkdir(parents=True)
            outside = root / "outside.mp4"
            outside.write_bytes(b"outside")
            (legacy_root / "linked.mp4").symlink_to(outside)

            with patch.dict(
                os.environ,
                self.environment(root),
                clear=True,
            ):
                with self.assertRaisesRegex(
                    self.tool.MigrationError,
                    "unsupported file type",
                ):
                    self.run_migration(
                        source_root,
                        copy_requested=True,
                    )


if __name__ == "__main__":
    unittest.main()

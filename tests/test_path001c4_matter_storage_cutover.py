import importlib.util
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

from server_core.paths import RuntimePaths


ROOT = Path(__file__).resolve().parents[1]
TOOL_PATH = (
    ROOT
    / "tools"
    / "path001c4_cutover_matter_storage.py"
)
SPEC = importlib.util.spec_from_file_location(
    "path001c4_matter_storage_cutover",
    TOOL_PATH,
)
CUTOVER = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = CUTOVER
SPEC.loader.exec_module(CUTOVER)


class MatterStorageCutoverTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.source_root = self.root / "source"
        self.legacy_matter = (
            self.source_root / "subsystems" / "matter"
        )
        self.legacy_matter.mkdir(parents=True)
        self.paths = RuntimePaths(
            source_root=self.source_root,
            data_root=self.root / "data",
        ).validate()
        self.paths.matter_protected_dir.mkdir(
            parents=True,
            mode=0o700,
        )
        self.paths.matter_protected_dir.chmod(0o700)
        self.service_checks = 0

        self.live_controller = (
            self.legacy_matter / "chip_tool_storage"
        )
        (self.live_controller / "nested").mkdir(parents=True)
        (self.live_controller / "identity.bin").write_bytes(
            b"current-controller"
        )
        (self.live_controller / "nested" / "fabric.db").write_bytes(
            b"current-fabric"
        )

        self.live_subscriptions = (
            self.legacy_matter
            / "chip_tool_subscription_storage"
        )
        (self.live_subscriptions / "sensors_10").mkdir(parents=True)
        (
            self.live_subscriptions
            / "sensors_10"
            / "session.db"
        ).write_bytes(b"current-subscription")

        self.live_bad = (
            self.legacy_matter
            / "chip_tool_storage.bad-previous"
        )
        self.live_bad.mkdir()
        (self.live_bad / "identity.bin").write_bytes(b"previous")

        protected_controller = self.paths.matter_controller_storage_dir
        rollback_controller = (
            self.paths.matter_protected_dir
            / "rollback"
            / "controller"
        )

        for destination in (
            protected_controller,
            rollback_controller,
        ):
            destination.mkdir(parents=True)
            (destination / "identity.bin").write_bytes(
                b"path001c42-controller"
            )
            self.make_private(destination)

        rollback_controller.parent.chmod(0o700)

    def tearDown(self):
        self.temporary_directory.cleanup()

    def make_private(self, root):
        root.chmod(0o700)

        for path in root.rglob("*"):
            path.chmod(0o700 if path.is_dir() else 0o600)

    def assert_private_tree(self, root):
        for current, directory_names, file_names in os.walk(root):
            current_path = Path(current)
            self.assertEqual(
                stat.S_IMODE(current_path.stat().st_mode),
                0o700,
            )

            for directory_name in directory_names:
                self.assertEqual(
                    stat.S_IMODE(
                        (current_path / directory_name).stat().st_mode
                    ),
                    0o700,
                )

            for file_name in file_names:
                self.assertEqual(
                    stat.S_IMODE(
                        (current_path / file_name).stat().st_mode
                    ),
                    0o600,
                )

    def service_inactive(self):
        self.service_checks += 1

    def cutover(self, *, perform_cutover):
        return CUTOVER.cutover_matter_storage(
            self.source_root,
            self.paths,
            perform_cutover=perform_cutover,
            service_check=self.service_inactive,
        )

    def test_preflight_does_not_change_worktree_or_protected_primary(self):
        result = self.cutover(perform_cutover=False)

        self.assertFalse(result.performed_cutover)
        self.assertFalse(result.already_complete)
        self.assertEqual(result.tree_count, 3)
        self.assertEqual(self.service_checks, 1)
        self.assertTrue(self.live_controller.is_dir())
        self.assertTrue(self.live_subscriptions.is_dir())
        self.assertEqual(
            (
                self.paths.matter_controller_storage_dir
                / "identity.bin"
            ).read_bytes(),
            b"path001c42-controller",
        )
        self.assertFalse(
            (
                self.paths.matter_protected_dir
                / "rollback"
                / "pre-cutover"
            ).exists()
        )

    def test_cutover_preserves_authority_and_relocates_all_legacy_trees(self):
        result = self.cutover(perform_cutover=True)
        rollback_root = (
            self.paths.matter_protected_dir / "rollback"
        )
        legacy_archive = rollback_root / "legacy-worktree"

        self.assertTrue(result.performed_cutover)
        self.assertEqual(result.tree_count, 3)
        self.assertEqual(result.primary_trees_initialized, 1)
        self.assertEqual(result.rollback_trees_created, 3)
        self.assertEqual(result.legacy_trees_relocated, 3)
        self.assertEqual(self.service_checks, 3)

        for path in (
            self.live_controller,
            self.live_subscriptions,
            self.live_bad,
        ):
            self.assertFalse(path.exists())

        self.assertEqual(
            (
                self.paths.matter_controller_storage_dir
                / "identity.bin"
            ).read_bytes(),
            b"path001c42-controller",
        )
        self.assertEqual(
            (
                self.paths.matter_subscription_storage_dir
                / "sensors_10"
                / "session.db"
            ).read_bytes(),
            b"current-subscription",
        )
        self.assertEqual(
            (
                rollback_root
                / "pre-cutover"
                / "controller"
                / "identity.bin"
            ).read_bytes(),
            b"path001c42-controller",
        )
        self.assertEqual(
            (
                rollback_root
                / "controller"
                / "identity.bin"
            ).read_bytes(),
            b"path001c42-controller",
        )
        self.assertEqual(
            (
                legacy_archive
                / "chip_tool_storage"
                / "identity.bin"
            ).read_bytes(),
            b"current-controller",
        )
        self.assertEqual(
            (
                legacy_archive
                / "chip_tool_storage.bad-previous"
                / "identity.bin"
            ).read_bytes(),
            b"previous",
        )
        self.assert_private_tree(self.paths.matter_protected_dir)

    def test_completed_cutover_is_idempotently_revalidated(self):
        self.cutover(perform_cutover=True)
        self.service_checks = 0

        result = self.cutover(perform_cutover=True)

        self.assertTrue(result.already_complete)
        self.assertFalse(result.performed_cutover)
        self.assertEqual(result.tree_count, 3)
        self.assertEqual(self.service_checks, 1)

    def test_live_change_during_preparation_stops_before_relocation(self):
        identity = self.live_controller / "identity.bin"

        def change_live_controller():
            self.service_checks += 1

            if self.service_checks == 2:
                identity.write_bytes(b"changed-during-cutover")

        with self.assertRaisesRegex(
            CUTOVER.MigrationError,
            "changed during cutover preparation",
        ):
            CUTOVER.cutover_matter_storage(
                self.source_root,
                self.paths,
                perform_cutover=True,
                service_check=change_live_controller,
            )

        self.assertTrue(self.live_controller.is_dir())
        self.assertTrue(self.live_subscriptions.is_dir())

    def test_failed_second_move_restores_first_legacy_tree(self):
        original_rename = Path.rename

        def fail_subscription_move(path, target):
            if path == self.live_subscriptions:
                raise OSError("fixture move failure")

            return original_rename(path, target)

        with mock.patch.object(
            Path,
            "rename",
            autospec=True,
            side_effect=fail_subscription_move,
        ):
            with self.assertRaisesRegex(
                CUTOVER.MigrationError,
                "could not be relocated atomically",
            ):
                self.cutover(perform_cutover=True)

        self.assertTrue(self.live_controller.is_dir())
        self.assertTrue(self.live_subscriptions.is_dir())
        self.assertTrue(self.live_bad.is_dir())

    def test_failed_final_validation_restores_all_legacy_trees(self):
        with mock.patch.object(
            CUTOVER,
            "_validate_completed_cutover",
            side_effect=CUTOVER.MigrationError("fixture validation failure"),
        ):
            with self.assertRaisesRegex(
                CUTOVER.MigrationError,
                "fixture validation failure",
            ):
                self.cutover(perform_cutover=True)

        self.assertTrue(self.live_controller.is_dir())
        self.assertTrue(self.live_subscriptions.is_dir())
        self.assertTrue(self.live_bad.is_dir())

    def test_partial_legacy_source_is_rejected(self):
        shutil.rmtree(self.live_subscriptions)

        with self.assertRaisesRegex(
            CUTOVER.MigrationError,
            "only partially present",
        ):
            self.cutover(perform_cutover=True)

    def test_advanced_protected_controller_remains_authoritative(self):
        protected_file = (
            self.paths.matter_controller_storage_dir
            / "identity.bin"
        )
        protected_file.write_bytes(b"protected-advanced")
        protected_file.chmod(0o600)

        self.cutover(perform_cutover=True)

        self.assertEqual(
            protected_file.read_bytes(),
            b"protected-advanced",
        )
        self.assertEqual(
            (
                self.paths.matter_protected_dir
                / "rollback"
                / "pre-cutover"
                / "controller"
                / "identity.bin"
            ).read_bytes(),
            b"protected-advanced",
        )
        self.assertEqual(
            (
                self.paths.matter_protected_dir
                / "rollback"
                / "legacy-worktree"
                / "chip_tool_storage"
                / "identity.bin"
            ).read_bytes(),
            b"current-controller",
        )

    def test_missing_protected_controller_is_rejected(self):
        shutil.rmtree(self.paths.matter_controller_storage_dir)

        with self.assertRaisesRegex(
            CUTOVER.MigrationError,
            "PATH-001C.4.2 controller copies are missing",
        ):
            self.cutover(perform_cutover=True)

        self.assertTrue(self.live_controller.is_dir())

    def test_rendered_result_redacts_names_and_paths(self):
        output = CUTOVER.render_result(
            self.cutover(perform_cutover=False)
        )

        self.assertNotIn("identity.bin", output)
        self.assertNotIn("chip_tool_storage", output)
        self.assertNotIn(str(self.source_root), output)
        self.assertIn("Worktree Matter storage changed: no", output)
        self.assertIn("Legacy cleanup authorized: no", output)

    def test_service_check_accepts_only_inactive(self):
        inactive = subprocess.CompletedProcess(
            args=(),
            returncode=3,
            stdout="inactive\n",
            stderr="",
        )

        with mock.patch.object(
            CUTOVER.subprocess,
            "run",
            return_value=inactive,
        ):
            CUTOVER.require_service_inactive()

        active = subprocess.CompletedProcess(
            args=(),
            returncode=0,
            stdout="active\n",
            stderr="",
        )

        with mock.patch.object(
            CUTOVER.subprocess,
            "run",
            return_value=active,
        ):
            with self.assertRaisesRegex(
                CUTOVER.MigrationError,
                "must be stopped",
            ):
                CUTOVER.require_service_inactive()

    def test_root_cli_execution_is_rejected(self):
        with mock.patch.object(
            CUTOVER.os,
            "geteuid",
            return_value=0,
        ):
            with self.assertRaisesRegex(
                CUTOVER.MigrationError,
                "not as root",
            ):
                CUTOVER.require_operator_identity()

    def test_server_selects_protected_runtime_paths(self):
        source = (ROOT / "kotibot_server.py").read_text(
            encoding="utf-8"
        )

        self.assertIn(
            "MATTER_CONTROLLER_STORAGE_DIR = "
            "RUNTIME_PATHS.matter_controller_storage_dir",
            source,
        )
        self.assertIn(
            "RUNTIME_PATHS.matter_subscription_storage_dir",
            source,
        )
        self.assertNotIn(
            "MATTER_CONTROLLER_STORAGE_DIR = "
            "MATTER_DIR / 'chip_tool_storage'",
            source,
        )


if __name__ == "__main__":
    unittest.main()

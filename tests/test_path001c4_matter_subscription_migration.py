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
    / "path001c4_migrate_matter_subscription_storage.py"
)
SPEC = importlib.util.spec_from_file_location(
    "path001c4_matter_subscription_migration",
    TOOL_PATH,
)
MIGRATION = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = MIGRATION
SPEC.loader.exec_module(MIGRATION)


class MatterSubscriptionMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.source_root = self.root / "source"
        self.legacy_matter = (
            self.source_root / "subsystems" / "matter"
        )
        self.legacy_matter.mkdir(parents=True)
        self.data_root = self.root / "data"
        self.paths = RuntimePaths(
            source_root=self.source_root,
            data_root=self.data_root,
        ).validate()
        self.paths.matter_protected_dir.mkdir(
            parents=True,
            mode=0o700,
        )
        self.paths.matter_protected_dir.chmod(0o700)
        self.service_checks = 0

        controller = self.legacy_matter / "chip_tool_storage"
        controller.mkdir()
        (controller / "must-not-copy.bin").write_bytes(
            b"controller"
        )
        protected_controller = self.paths.matter_controller_storage_dir
        rollback_controller = (
            self.paths.matter_protected_dir
            / "rollback"
            / "controller"
        )

        for copy in (protected_controller, rollback_controller):
            shutil.copytree(controller, copy)
            copy.chmod(0o700)

            for copied_file in copy.rglob("*"):
                copied_file.chmod(
                    0o700 if copied_file.is_dir() else 0o600
                )

        rollback_controller.parent.chmod(0o700)

        subscriptions = (
            self.legacy_matter
            / "chip_tool_subscription_storage"
        )
        (subscriptions / "sensors_10" / "nested").mkdir(
            parents=True
        )
        (subscriptions / "sensors_10" / "identity.bin").write_bytes(
            b"subscription-controller-copy"
        )
        (
            subscriptions
            / "sensors_10"
            / "nested"
            / "session.db"
        ).write_bytes(b"session")

    def tearDown(self):
        self.temporary_directory.cleanup()

    def service_inactive(self):
        self.service_checks += 1

    def migrate(self, *, perform_copy):
        return MIGRATION.migrate_subscription_storage(
            self.source_root,
            self.paths,
            perform_copy=perform_copy,
            service_check=self.service_inactive,
        )

    def assert_private_tree(self, root):
        for current, directory_names, file_names in os.walk(root):
            current_path = Path(current)
            self.assertEqual(
                stat.S_IMODE(current_path.stat().st_mode),
                0o700,
            )
            self.assertEqual(current_path.stat().st_uid, os.geteuid())
            self.assertEqual(current_path.stat().st_gid, os.getegid())

            for directory_name in directory_names:
                directory = current_path / directory_name
                self.assertEqual(
                    stat.S_IMODE(directory.stat().st_mode),
                    0o700,
                )

            for file_name in file_names:
                file_path = current_path / file_name
                self.assertEqual(
                    stat.S_IMODE(file_path.stat().st_mode),
                    0o600,
                )
                self.assertEqual(file_path.stat().st_uid, os.geteuid())
                self.assertEqual(file_path.stat().st_gid, os.getegid())

    def test_preflight_does_not_copy_or_create_destinations(self):
        result = self.migrate(perform_copy=False)

        self.assertFalse(result.performed_copy)
        self.assertEqual(result.file_count, 2)
        self.assertEqual(self.service_checks, 1)
        self.assertFalse(
            self.paths.matter_subscription_storage_dir.exists()
        )
        self.assertFalse(
            (
                self.paths.matter_protected_dir
                / "rollback"
                / "subscriptions"
            ).exists()
        )

    def test_copy_preserves_subscription_tree_and_rollback(self):
        result = self.migrate(perform_copy=True)
        destination = self.paths.matter_subscription_storage_dir
        rollback = (
            self.paths.matter_protected_dir
            / "rollback"
            / "subscriptions"
        )

        self.assertEqual(result.newly_copied_trees, 2)
        self.assertEqual(self.service_checks, 2)
        self.assertEqual(
            (destination / "sensors_10" / "identity.bin").read_bytes(),
            b"subscription-controller-copy",
        )
        self.assertEqual(
            (
                rollback
                / "sensors_10"
                / "nested"
                / "session.db"
            ).read_bytes(),
            b"session",
        )
        self.assert_private_tree(destination)
        self.assert_private_tree(rollback)

    def test_copy_leaves_legacy_and_controller_storage_unchanged(self):
        legacy_file = (
            self.legacy_matter
            / "chip_tool_subscription_storage"
            / "sensors_10"
            / "identity.bin"
        )
        controller_file = (
            self.legacy_matter
            / "chip_tool_storage"
            / "must-not-copy.bin"
        )

        self.migrate(perform_copy=True)

        self.assertEqual(
            legacy_file.read_bytes(),
            b"subscription-controller-copy",
        )
        self.assertEqual(
            controller_file.read_bytes(),
            b"controller",
        )
        self.assertFalse(
            (
                self.paths.matter_subscription_storage_dir
                / "must-not-copy.bin"
            ).exists()
        )

    def test_rerun_revalidates_without_overwrite(self):
        self.migrate(perform_copy=True)
        result = self.migrate(perform_copy=True)

        self.assertEqual(result.newly_copied_trees, 0)
        self.assertEqual(result.previously_verified_trees, 2)

    def test_empty_subscription_tree_is_preserved(self):
        source = (
            self.legacy_matter
            / "chip_tool_subscription_storage"
        )

        for child in sorted(source.rglob("*"), reverse=True):
            if child.is_file():
                child.unlink()
            elif child.is_dir():
                child.rmdir()

        result = self.migrate(perform_copy=True)

        self.assertEqual(result.file_count, 0)
        self.assertTrue(
            self.paths.matter_subscription_storage_dir.is_dir()
        )

    def test_missing_subscription_storage_fails_without_destination(self):
        source = (
            self.legacy_matter
            / "chip_tool_subscription_storage"
        )

        for child in sorted(source.rglob("*"), reverse=True):
            if child.is_file():
                child.unlink()
            elif child.is_dir():
                child.rmdir()

        source.rmdir()

        with self.assertRaisesRegex(
            MIGRATION.MigrationError,
            "missing",
        ):
            self.migrate(perform_copy=True)

        self.assertFalse(
            self.paths.matter_subscription_storage_dir.exists()
        )

    def test_missing_controller_copy_prerequisite_is_rejected(self):
        protected_controller = self.paths.matter_controller_storage_dir
        (protected_controller / "must-not-copy.bin").unlink()
        protected_controller.rmdir()

        with self.assertRaisesRegex(
            MIGRATION.MigrationError,
            "PATH-001C.4.2 controller copies are missing",
        ):
            self.migrate(perform_copy=True)

        self.assertFalse(
            self.paths.matter_subscription_storage_dir.exists()
        )

    def test_source_symlink_is_rejected(self):
        source = (
            self.legacy_matter
            / "chip_tool_subscription_storage"
        )
        (source / "identity-link").symlink_to(
            source / "sensors_10" / "identity.bin"
        )

        with self.assertRaisesRegex(
            MIGRATION.MigrationError,
            "symlinks",
        ):
            self.migrate(perform_copy=True)

    def test_conflicting_destination_is_rejected_without_overwrite(self):
        destination = self.paths.matter_subscription_storage_dir
        destination.mkdir()
        destination.chmod(0o700)
        marker = destination / "unrelated.bin"
        marker.write_bytes(b"do-not-overwrite")
        marker.chmod(0o600)

        with self.assertRaisesRegex(
            MIGRATION.MigrationError,
            "does not match",
        ):
            self.migrate(perform_copy=True)

        self.assertEqual(marker.read_bytes(), b"do-not-overwrite")

    def test_matching_destination_with_public_mode_is_rejected(self):
        self.migrate(perform_copy=True)
        copied_file = (
            self.paths.matter_subscription_storage_dir
            / "sensors_10"
            / "identity.bin"
        )
        copied_file.chmod(0o644)

        with self.assertRaisesRegex(
            MIGRATION.MigrationError,
            "permissions are not private",
        ):
            self.migrate(perform_copy=False)

    def test_service_state_is_rechecked_after_copy(self):
        def changing_service_state():
            self.service_checks += 1

            if self.service_checks == 2:
                raise MIGRATION.MigrationError("service restarted")

        with self.assertRaisesRegex(
            MIGRATION.MigrationError,
            "service restarted",
        ):
            MIGRATION.migrate_subscription_storage(
                self.source_root,
                self.paths,
                perform_copy=True,
                service_check=changing_service_state,
            )

    def test_source_change_during_copy_is_rejected(self):
        source_file = (
            self.legacy_matter
            / "chip_tool_subscription_storage"
            / "sensors_10"
            / "identity.bin"
        )

        def mutate_before_final_validation():
            self.service_checks += 1

            if self.service_checks == 2:
                source_file.write_bytes(b"changed-during-copy")

        with self.assertRaisesRegex(
            MIGRATION.MigrationError,
            "changed during the copy",
        ):
            MIGRATION.migrate_subscription_storage(
                self.source_root,
                self.paths,
                perform_copy=True,
                service_check=mutate_before_final_validation,
            )

    def test_rendered_result_contains_no_storage_names_or_paths(self):
        output = MIGRATION.render_result(
            self.migrate(perform_copy=False)
        )

        self.assertNotIn("identity.bin", output)
        self.assertNotIn("chip_tool_subscription_storage", output)
        self.assertNotIn(str(self.source_root), output)
        self.assertIn("Controller storage changed: no", output)
        self.assertIn("Runtime cutover changed: no", output)
        self.assertIn("Legacy cleanup authorized: no", output)

    def test_service_check_accepts_only_inactive(self):
        inactive = subprocess.CompletedProcess(
            args=(),
            returncode=3,
            stdout="inactive\n",
            stderr="",
        )

        with mock.patch.object(
            MIGRATION.subprocess,
            "run",
            return_value=inactive,
        ):
            MIGRATION.require_service_inactive()

        for state in ("active", "activating", "failed", "unknown", ""):
            result = subprocess.CompletedProcess(
                args=(),
                returncode=0,
                stdout=f"{state}\n",
                stderr="",
            )

            with self.subTest(state=state), mock.patch.object(
                MIGRATION.subprocess,
                "run",
                return_value=result,
            ):
                with self.assertRaisesRegex(
                    MIGRATION.MigrationError,
                    "must be stopped",
                ):
                    MIGRATION.require_service_inactive()

    def test_root_cli_execution_is_rejected(self):
        with mock.patch.object(
            MIGRATION.os,
            "geteuid",
            return_value=0,
        ):
            with self.assertRaisesRegex(
                MIGRATION.MigrationError,
                "not as root",
            ):
                MIGRATION.require_operator_identity()


if __name__ == "__main__":
    unittest.main()

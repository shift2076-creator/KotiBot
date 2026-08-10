import importlib.util
import os
from pathlib import Path
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
    / "path001c4_migrate_matter_controller_storage.py"
)
SPEC = importlib.util.spec_from_file_location(
    "path001c4_matter_migration",
    TOOL_PATH,
)
MIGRATION = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = MIGRATION
SPEC.loader.exec_module(MIGRATION)


class MatterControllerMigrationTests(unittest.TestCase):
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

        active = self.legacy_matter / "chip_tool_storage"
        (active / "nested").mkdir(parents=True)
        (active / "identity.bin").write_bytes(b"controller-identity")
        (active / "nested" / "fabric.db").write_bytes(b"fabric")

        bad = self.legacy_matter / "chip_tool_storage.bad-previous"
        bad.mkdir()
        (bad / "identity.bin").write_bytes(b"previous-controller")

        repair = (
            self.legacy_matter
            / ".chip_tool_storage.repair-interrupted"
        )
        repair.mkdir()
        (repair / "identity.bin").write_bytes(b"repair-controller")

        subscriptions = (
            self.legacy_matter
            / "chip_tool_subscription_storage"
        )
        subscriptions.mkdir()
        (subscriptions / "must-not-copy.bin").write_bytes(
            b"subscription-copy"
        )

    def tearDown(self):
        self.temporary_directory.cleanup()

    def service_inactive(self):
        self.service_checks += 1

    def migrate(self, *, perform_copy):
        return MIGRATION.migrate_controller_storage(
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
        self.assertEqual(result.tree_count, 3)
        self.assertEqual(self.service_checks, 1)
        self.assertFalse(
            self.paths.matter_controller_storage_dir.exists()
        )
        self.assertFalse(
            (self.paths.matter_protected_dir / "rollback").exists()
        )
        self.assertFalse(
            self.paths.matter_subscription_storage_dir.exists()
        )

    def test_copy_preserves_every_controller_tree_and_rollback(self):
        result = self.migrate(perform_copy=True)
        protected = self.paths.matter_protected_dir
        rollback = protected / "rollback"

        self.assertTrue(result.performed_copy)
        self.assertEqual(result.newly_copied_trees, 6)
        self.assertEqual(self.service_checks, 2)
        self.assertEqual(
            (protected / "controller" / "identity.bin").read_bytes(),
            b"controller-identity",
        )
        self.assertEqual(
            (
                protected
                / "chip_tool_storage.bad-previous"
                / "identity.bin"
            ).read_bytes(),
            b"previous-controller",
        )
        self.assertEqual(
            (
                protected
                / ".chip_tool_storage.repair-interrupted"
                / "identity.bin"
            ).read_bytes(),
            b"repair-controller",
        )
        self.assertEqual(
            (rollback / "controller" / "identity.bin").read_bytes(),
            b"controller-identity",
        )
        self.assertEqual(
            (
                rollback
                / "chip_tool_storage.bad-previous"
                / "identity.bin"
            ).read_bytes(),
            b"previous-controller",
        )
        self.assertEqual(
            (
                rollback
                / ".chip_tool_storage.repair-interrupted"
                / "identity.bin"
            ).read_bytes(),
            b"repair-controller",
        )
        self.assert_private_tree(protected)

    def test_copy_leaves_legacy_and_subscription_storage_unchanged(self):
        active_file = (
            self.legacy_matter
            / "chip_tool_storage"
            / "identity.bin"
        )
        subscription_file = (
            self.legacy_matter
            / "chip_tool_subscription_storage"
            / "must-not-copy.bin"
        )

        self.migrate(perform_copy=True)

        self.assertEqual(
            active_file.read_bytes(),
            b"controller-identity",
        )
        self.assertEqual(
            subscription_file.read_bytes(),
            b"subscription-copy",
        )
        self.assertFalse(
            self.paths.matter_subscription_storage_dir.exists()
        )

    def test_rerun_revalidates_without_overwrite(self):
        self.migrate(perform_copy=True)
        result = self.migrate(perform_copy=True)

        self.assertEqual(result.newly_copied_trees, 0)
        self.assertEqual(result.previously_verified_trees, 6)

    def test_missing_active_storage_fails_without_initializing_identity(self):
        active = self.legacy_matter / "chip_tool_storage"

        for child in active.rglob("*"):
            if child.is_file():
                child.unlink()

        for child in sorted(active.rglob("*"), reverse=True):
            if child.is_dir():
                child.rmdir()

        active.rmdir()

        with self.assertRaisesRegex(
            MIGRATION.MigrationError,
            "missing",
        ):
            self.migrate(perform_copy=True)

        self.assertFalse(
            self.paths.matter_controller_storage_dir.exists()
        )

    def test_empty_active_storage_fails_without_initializing_identity(self):
        active = self.legacy_matter / "chip_tool_storage"

        for child in active.rglob("*"):
            if child.is_file():
                child.unlink()

        for child in sorted(active.rglob("*"), reverse=True):
            if child.is_dir():
                child.rmdir()

        with self.assertRaisesRegex(
            MIGRATION.MigrationError,
            "no regular files",
        ):
            self.migrate(perform_copy=True)

        self.assertFalse(
            self.paths.matter_controller_storage_dir.exists()
        )

    def test_source_symlink_is_rejected(self):
        active = self.legacy_matter / "chip_tool_storage"
        (active / "identity-link").symlink_to(
            active / "identity.bin"
        )

        with self.assertRaisesRegex(
            MIGRATION.MigrationError,
            "symlinks",
        ):
            self.migrate(perform_copy=True)

        self.assertFalse(
            self.paths.matter_controller_storage_dir.exists()
        )

    @unittest.skipUnless(hasattr(os, "mkfifo"), "POSIX FIFO required")
    def test_source_special_file_is_rejected(self):
        active = self.legacy_matter / "chip_tool_storage"
        os.mkfifo(active / "controller.pipe")

        with self.assertRaisesRegex(
            MIGRATION.MigrationError,
            "unsupported file type",
        ):
            self.migrate(perform_copy=True)

    def test_conflicting_destination_is_rejected_without_overwrite(self):
        destination = self.paths.matter_controller_storage_dir
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
        controller_file = (
            self.paths.matter_controller_storage_dir
            / "identity.bin"
        )
        controller_file.chmod(0o644)

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
            MIGRATION.migrate_controller_storage(
                self.source_root,
                self.paths,
                perform_copy=True,
                service_check=changing_service_state,
            )

    def test_source_change_during_copy_is_rejected(self):
        identity_file = (
            self.legacy_matter
            / "chip_tool_storage"
            / "identity.bin"
        )

        def mutate_before_final_validation():
            self.service_checks += 1

            if self.service_checks == 2:
                identity_file.write_bytes(b"changed-during-copy")

        with self.assertRaisesRegex(
            MIGRATION.MigrationError,
            "changed during the copy",
        ):
            MIGRATION.migrate_controller_storage(
                self.source_root,
                self.paths,
                perform_copy=True,
                service_check=mutate_before_final_validation,
            )

    def test_failed_copy_removes_only_tool_owned_staging(self):
        with mock.patch.object(
            MIGRATION.shutil,
            "copyfile",
            side_effect=OSError("fixture copy failure"),
        ):
            with self.assertRaisesRegex(
                MIGRATION.MigrationError,
                "could not be copied completely",
            ):
                self.migrate(perform_copy=True)

        staging = list(
            self.paths.matter_protected_dir.rglob(
                ".path001c4-copy-*"
            )
        )
        self.assertEqual(staging, [])
        self.assertTrue(
            (
                self.legacy_matter
                / "chip_tool_storage"
                / "identity.bin"
            ).exists()
        )

    def test_rendered_result_contains_no_storage_names_or_paths(self):
        output = MIGRATION.render_result(
            self.migrate(perform_copy=False)
        )

        self.assertNotIn("identity.bin", output)
        self.assertNotIn("chip_tool_storage", output)
        self.assertNotIn(str(self.source_root), output)
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

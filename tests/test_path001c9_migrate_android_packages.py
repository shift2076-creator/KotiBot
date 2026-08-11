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
    / "path001c9_migrate_android_packages.py"
)


def load_migration_tool():
    spec = importlib.util.spec_from_file_location(
        "path001c9_migrate_android_packages",
        TOOL_PATH,
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class AndroidPackageMigrationTests(unittest.TestCase):
    def environment(self, root):
        return {
            "KOTIBOT_DATA_DIR": str(root / "data"),
            "KOTIBOT_CACHE_DIR": str(root / "cache"),
            "KOTIBOT_RUNTIME_DIR": str(root / "runtime"),
        }

    def prepare_legacy_packages(self, root):
        source_root = root / "source"
        legacy_directory = (
            source_root / "subsystems/file-server/get-app"
        )
        legacy_directory.mkdir(parents=True)
        packages = {
            "KotiBot-Home.0.42.045.apk": b"monitor-package",
            "KotiBot-Key.0.46.apk": b"control-package",
        }

        for name, payload in packages.items():
            (legacy_directory / name).write_bytes(payload)

        return source_root, legacy_directory, packages

    def prepare_flat_rollback(self, root, packages):
        rollback_root = root / "data" / "packages"
        rollback_directory = rollback_root / "android"
        rollback_directory.mkdir(parents=True, mode=0o700)

        for name, payload in packages.items():
            target = rollback_directory / name
            target.write_bytes(payload)

            if os.name != "nt":
                os.chmod(target, 0o600)

        if os.name != "nt":
            os.chmod(rollback_root, 0o700)
            os.chmod(rollback_directory, 0o700)

        return rollback_directory

    def test_canonical_copy_and_revalidation_preserve_rollback(self):
        tool = load_migration_tool()

        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_root, legacy_directory, packages = (
                self.prepare_legacy_packages(root)
            )
            rollback_directory = self.prepare_flat_rollback(
                root,
                packages,
            )

            with (
                patch.object(tool, "SOURCE_ROOT", source_root),
                patch.dict(
                    os.environ,
                    self.environment(root),
                    clear=True,
                ),
            ):
                preflight = tool.migrate_android_packages(
                    copy_requested=False,
                )
                copied = tool.migrate_android_packages(
                    copy_requested=True,
                )
                revalidated = tool.migrate_android_packages(
                    copy_requested=True,
                )

            package_root = root / "data" / "apks"
            destinations = {
                "KotiBot-Home.0.42.045.apk": (
                    package_root
                    / "kotibot-monitor"
                    / "KotiBot-Monitor.0.42.045.apk"
                ),
                "KotiBot-Key.0.46.apk": (
                    package_root
                    / "kotibot-control"
                    / "KotiBot-Control.0.46.apk"
                ),
            }

            self.assertEqual(preflight.package_count, 2)
            self.assertEqual(preflight.flat_rollback_packages, 2)
            self.assertEqual(copied.newly_copied_packages, 2)
            self.assertEqual(
                revalidated.previously_verified_packages,
                2,
            )

            for source_name, payload in packages.items():
                source = legacy_directory / source_name
                rollback = rollback_directory / source_name
                target = destinations[source_name]

                self.assertEqual(source.read_bytes(), payload)
                self.assertEqual(rollback.read_bytes(), payload)
                self.assertEqual(target.read_bytes(), payload)

                if os.name != "nt":
                    self.assertEqual(
                        stat.S_IMODE(target.stat().st_mode),
                        0o600,
                    )

            if os.name != "nt":
                for directory in (
                    package_root,
                    package_root / "kotibot-control",
                    package_root / "kotibot-monitor",
                ):
                    self.assertEqual(
                        stat.S_IMODE(directory.stat().st_mode),
                        0o700,
                    )

    def test_different_existing_canonical_destination_stops_copy(self):
        tool = load_migration_tool()

        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_root, _, _ = self.prepare_legacy_packages(root)
            package_root = root / "data" / "apks"
            destination = package_root / "kotibot-monitor"
            destination.mkdir(parents=True, mode=0o700)
            conflicting = (
                destination / "KotiBot-Monitor.0.42.045.apk"
            )
            conflicting.write_bytes(b"different-package")

            if os.name != "nt":
                os.chmod(package_root, 0o700)
                os.chmod(destination, 0o700)
                os.chmod(conflicting, 0o600)

            with (
                patch.object(tool, "SOURCE_ROOT", source_root),
                patch.dict(
                    os.environ,
                    self.environment(root),
                    clear=True,
                ),
            ):
                with self.assertRaisesRegex(
                    tool.MigrationError,
                    "differs from its legacy source",
                ):
                    tool.migrate_android_packages(
                        copy_requested=True,
                    )

            self.assertEqual(
                conflicting.read_bytes(),
                b"different-package",
            )

    def test_unsupported_legacy_name_stops_migration(self):
        tool = load_migration_tool()

        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_root = root / "source"
            legacy_directory = (
                source_root / "subsystems/file-server/get-app"
            )
            legacy_directory.mkdir(parents=True)
            (legacy_directory / "Unclassified.1.apk").write_bytes(
                b"package"
            )

            with (
                patch.object(tool, "SOURCE_ROOT", source_root),
                patch.dict(
                    os.environ,
                    self.environment(root),
                    clear=True,
                ),
            ):
                with self.assertRaisesRegex(
                    tool.MigrationError,
                    "naming is unsupported",
                ):
                    tool.migrate_android_packages(
                        copy_requested=False,
                    )

    @unittest.skipIf(
        os.name == "nt",
        "Symlink validation is exercised on POSIX hosts.",
    )
    def test_symlinked_legacy_package_is_rejected(self):
        tool = load_migration_tool()

        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_root = root / "source"
            legacy_directory = (
                source_root / "subsystems/file-server/get-app"
            )
            legacy_directory.mkdir(parents=True)
            outside = root / "outside.apk"
            outside.write_bytes(b"outside")
            (legacy_directory / "KotiBot-Home.apk").symlink_to(
                outside
            )

            with (
                patch.object(tool, "SOURCE_ROOT", source_root),
                patch.dict(
                    os.environ,
                    self.environment(root),
                    clear=True,
                ),
            ):
                with self.assertRaisesRegex(
                    tool.MigrationError,
                    "unsupported file type",
                ):
                    tool.migrate_android_packages(
                        copy_requested=False,
                    )


if __name__ == "__main__":
    unittest.main()



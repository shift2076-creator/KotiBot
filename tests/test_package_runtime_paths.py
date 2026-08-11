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


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


class PackageRuntimePathTests(unittest.TestCase):
    def configured_environment(self, root):
        return {
            "KOTIBOT_DATA_DIR": str(root / "data"),
            "KOTIBOT_CACHE_DIR": str(root / "cache"),
            "KOTIBOT_RUNTIME_DIR": str(root / "runtime"),
            "KOTIBOT_PACKAGE_DIR": str(root / "apks"),
        }

    def test_configured_package_root_and_product_directories(self):
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

            self.assertEqual(paths.package_root, root / "apks")
            self.assertEqual(
                paths.controller_apk_dir,
                root / "apks" / "kotibot-control",
            )
            self.assertEqual(
                paths.monitor_apk_dir,
                root / "apks" / "kotibot-monitor",
            )

    def test_default_package_root_uses_data_root(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_root = root / "source"
            source_root.mkdir()
            environment = self.configured_environment(root)
            environment.pop("KOTIBOT_PACKAGE_DIR")

            with patch.dict(
                os.environ,
                environment,
                clear=True,
            ):
                paths = build_runtime_paths(source_root)

            self.assertEqual(
                paths.package_root,
                root / "data" / "apks",
            )
            self.assertEqual(
                paths.controller_apk_dir,
                root / "data" / "apks" / "kotibot-control",
            )
            self.assertEqual(
                paths.monitor_apk_dir,
                root / "data" / "apks" / "kotibot-monitor",
            )

    def test_invalid_package_overrides_are_rejected(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_root = root / "source"
            source_root.mkdir()

            for configured, message in (
                (
                    "relative/apks",
                    "KOTIBOT_PACKAGE_DIR must be an absolute path",
                ),
                (
                    str(source_root / "apks"),
                    "outside the source tree",
                ),
            ):
                environment = self.configured_environment(root)
                environment["KOTIBOT_PACKAGE_DIR"] = configured

                with self.subTest(configured=configured):
                    with patch.dict(
                        os.environ,
                        environment,
                        clear=True,
                    ):
                        with self.assertRaisesRegex(
                            RuntimeError,
                            message,
                        ):
                            build_runtime_paths(source_root)

    def test_prepare_creates_private_package_directories(self):
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
                paths.package_root,
                paths.controller_apk_dir,
                paths.monitor_apk_dir,
            ):
                directory = Path(directory)
                self.assertTrue(directory.is_dir())

                if os.name != "nt":
                    self.assertEqual(
                        stat.S_IMODE(directory.stat().st_mode),
                        0o700,
                    )

    def test_runtime_threads_external_product_directories(self):
        server_source = (
            REPOSITORY_ROOT / "kotibot_server.py"
        ).read_text(encoding="utf-8")
        subsystem_source = (
            REPOSITORY_ROOT / "server_core" / "subsystems.py"
        ).read_text(encoding="utf-8")
        route_source = (
            REPOSITORY_ROOT
            / "subsystems"
            / "file-server"
            / "file_server_routes.py"
        ).read_text(encoding="utf-8")

        for expected in (
            "CONTROLLER_APK_DIR = "
            "RUNTIME_PATHS.controller_apk_dir",
            "MONITOR_APK_DIR = "
            "RUNTIME_PATHS.monitor_apk_dir",
            "'controller_apk_dir': CONTROLLER_APK_DIR",
            "'monitor_apk_dir': MONITOR_APK_DIR",
        ):
            self.assertIn(expected, server_source)

        for expected in (
            "controller_apk_dir = "
            "Path(ctx['controller_apk_dir'])",
            "monitor_apk_dir = "
            "Path(ctx['monitor_apk_dir'])",
            "'controller_apk_dir': controller_apk_dir",
            "'monitor_apk_dir': monitor_apk_dir",
        ):
            self.assertIn(expected, subsystem_source)

        self.assertIn(
            "def register_file_server_routes(app, ctx):",
            route_source,
        )
        self.assertIn(
            "'home': Path(ctx['monitor_apk_dir'])",
            route_source,
        )
        self.assertIn(
            "'key': Path(ctx['controller_apk_dir'])",
            route_source,
        )
        self.assertNotIn(
            "Path(__file__).resolve().parent / 'get-app'",
            route_source,
        )
        self.assertNotIn("apk_dir.mkdir", route_source)

        for route in (
            "@app.route('/file-server/get-app/<path:filename>')",
            "@app.route('/get-app')",
            "@app.route('/get-home-client-app')",
            "@app.route('/get-key-client-app')",
            "@app.route('/api/file-server/apks')",
        ):
            self.assertIn(route, route_source)


if __name__ == "__main__":
    unittest.main()



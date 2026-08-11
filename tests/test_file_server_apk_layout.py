import importlib.util
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import types
import unittest
from unittest.mock import patch


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
ROUTE_PATH = (
    REPOSITORY_ROOT
    / "subsystems"
    / "file-server"
    / "file_server_routes.py"
)


class FakeApp:
    def __init__(self):
        self.routes = {}

    def route(self, rule):
        def decorator(function):
            self.routes[rule] = function
            return function

        return decorator


def load_route_module():
    flask_module = types.ModuleType("flask")
    flask_module.jsonify = lambda payload: payload
    flask_module.send_from_directory = (
        lambda directory, name, as_attachment: {
            "directory": Path(directory),
            "filename": name,
            "as_attachment": as_attachment,
        }
    )
    spec = importlib.util.spec_from_file_location(
        "path001c9_file_server_routes",
        ROUTE_PATH,
    )
    module = importlib.util.module_from_spec(spec)

    with patch.dict(sys.modules, {"flask": flask_module}):
        spec.loader.exec_module(module)

    return module


class FileServerApkLayoutTests(unittest.TestCase):
    def prepare_routes(self, root):
        controller_directory = root / "kotibot-controller"
        monitor_directory = root / "kotibot-monitor"
        controller_directory.mkdir()
        monitor_directory.mkdir()

        for name, payload in (
            ("KotiBot-Control.0.47.apk", b"control"),
            ("KotiBot-Monitor.0.42.050.apk", b"older"),
            ("KotiBot-Monitor.0.42.051.apk", b"newer"),
        ):
            directory = (
                controller_directory
                if name.startswith("KotiBot-Control")
                else monitor_directory
            )
            (directory / name).write_bytes(payload)

        module = load_route_module()
        app = FakeApp()
        module.register_file_server_routes(app, {
            "controller_apk_dir": controller_directory,
            "monitor_apk_dir": monitor_directory,
        })
        return app, controller_directory, monitor_directory

    def test_api_lists_canonical_files_with_compatible_kinds(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            app, _, _ = self.prepare_routes(root)
            response = app.routes["/api/file-server/apks"]()
            files = {
                item["filename"]: item
                for item in response["files"]
            }

            self.assertEqual(
                files["KotiBot-Control.0.47.apk"]["kind"],
                "key",
            )
            self.assertEqual(
                files["KotiBot-Control.0.47.apk"]["version"],
                "0.47",
            )
            self.assertEqual(
                files["KotiBot-Monitor.0.42.051.apk"]["kind"],
                "home",
            )
            self.assertEqual(
                files["KotiBot-Monitor.0.42.051.apk"]["version"],
                "0.42.51",
            )

    def test_compatible_routes_select_latest_canonical_packages(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            app, controller_directory, monitor_directory = (
                self.prepare_routes(root)
            )

            monitor = app.routes["/get-app"]()
            control = app.routes["/get-key-client-app"]()

            self.assertEqual(
                monitor,
                {
                    "directory": monitor_directory,
                    "filename": "KotiBot-Monitor.0.42.051.apk",
                    "as_attachment": True,
                },
            )
            self.assertEqual(
                control,
                {
                    "directory": controller_directory,
                    "filename": "KotiBot-Control.0.47.apk",
                    "as_attachment": True,
                },
            )

    def test_direct_download_rejects_unknown_package(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            app, _, monitor_directory = self.prepare_routes(root)
            (monitor_directory / "Unknown.1.apk").write_bytes(
                b"unknown"
            )

            direct = app.routes[
                "/file-server/get-app/<path:filename>"
            ]
            response, status = direct("Unknown.1.apk")

            self.assertEqual(status, 404)
            self.assertEqual(response["error"], "APK not found")


if __name__ == "__main__":
    unittest.main()

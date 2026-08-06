import os
from pathlib import Path
import stat
from tempfile import TemporaryDirectory
import unittest

from flask import Flask

from subsystems.security.kotibot_security import (
    KotiBotSecurity,
    SecurityConfig,
)
from subsystems.security.security_routes import request_policy

ROOT = Path(__file__).resolve().parents[1]

class SecurityPolicyTests(unittest.TestCase):
    def test_login_document_has_no_dashboard_content(self):
        login = (
            ROOT / "templates" / "login.html"
        ).read_text(encoding="utf-8")

        forbidden = (
            "appShell",
            "dashboard-state.js",
            "dashboard-api.js",
            "dashboard-render.js",
            "dashboard-main.js",
            "KOTIBOT_BOOTSTRAP",
            "clientCards",
            "cameraClients",
        )

        for value in forbidden:
            self.assertNotIn(value, login)

    def test_dashboard_has_no_login_overlay(self):
        dashboard = (
            ROOT / "templates" / "index.html"
        ).read_text(encoding="utf-8")

        self.assertNotIn("dashboardAuthModal", dashboard)
        self.assertNotIn("dashboardAuthForm", dashboard)

    def test_root_post_is_not_public_enrollment(self):
        self.assertEqual(
            request_policy("POST", "/"),
            "dashboard",
        )

    def test_only_login_assets_are_public(self):
        self.assertEqual(
            request_policy("GET", "/static/css/login.css"),
            "public",
        )
        self.assertEqual(
            request_policy("GET", "/static/js/dashboard-main.js"),
            "dashboard",
        )
        self.assertEqual(
            request_policy(
                "GET",
                "/subsystems/matter/static/matter.js",
            ),
            "dashboard",
        )

    def test_sensitive_routes_default_to_dashboard(self):
        paths = (
            "/client-rooms",
            "/api/status",
            "/api/status/stream",
            "/api/automation-routes",
            "/api/bluetooth/status",
            "/api/notifications/recent",
            "/api/notifications/test-fcm",
            "/get-home-client-app",
            "/get-key-client-app",
            "/api/future-route",
        )

        for path in paths:
            self.assertEqual(
                request_policy("GET", path),
                "dashboard",
                path,
            )

    def test_device_routes_require_signatures(self):
        paths = (
            "/telemetry",
            "/upload_frame",
            "/upload_video",
            "/api/key-notifications",
            "/api/notifications/fcm-token",
            "/api/voice/client/test",
            "/api/camera-talk/client/test",
        )

        for path in paths:
            self.assertEqual(
                request_policy("POST", path),
                "device",
                path,
            )

    def test_only_handshake_aliases_are_enrollment(self):
        for path in (
            "/handshake",
            "/api/handshake",
            "/client-handshake",
        ):
            self.assertEqual(
                request_policy("POST", path),
                "enrollment",
            )

    def test_security_runtime_contract_exists(self):
        with TemporaryDirectory() as temp_dir:
            security = KotiBotSecurity(SecurityConfig(
                base_dir=Path(temp_dir),
                allowed_origins=(
                    ("https", "kotibot.example", 443),
                ),
            ))

            required_methods = (
                "audit",
                "audit_request",
                "client_ip",
                "clear_login_rate_limit",
                "enrollment_rate_limit",
                "login_rate_limit",
                "require_same_origin",
            )

            for method_name in required_methods:
                self.assertTrue(
                    callable(getattr(
                        security,
                        method_name,
                        None,
                    )),
                    method_name,
                )

    def test_security_state_is_private(self):
        if os.name == "nt":
            self.skipTest("POSIX permission test")

        with TemporaryDirectory() as temp_dir:
            security = KotiBotSecurity(SecurityConfig(
                base_dir=Path(temp_dir),
                allowed_origins=(
                    ("https", "kotibot.example", 443),
                ),
            ))

            mode = stat.S_IMODE(
                security.config.state_file.stat().st_mode
            )
            self.assertEqual(mode, 0o600)

    def test_same_origin_enforcement(self):
        app = Flask(__name__)

        with TemporaryDirectory() as temp_dir:
            security = KotiBotSecurity(SecurityConfig(
                base_dir=Path(temp_dir),
                allowed_origins=(
                    ("https", "kotibot.example", 443),
                ),
            ))

            with app.test_request_context(
                "/api/test",
                method="POST",
                base_url="https://kotibot.example",
                headers={
                    "Origin": "https://kotibot.example",
                },
            ):
                self.assertIsNone(
                    security.require_same_origin()
                )

            with app.test_request_context(
                "/api/test",
                method="POST",
                base_url="https://kotibot.example",
                headers={
                    "Origin": "https://attacker.example",
                },
            ):
                blocked = security.require_same_origin()
                self.assertEqual(blocked[1], 403)


if __name__ == "__main__":
    unittest.main()
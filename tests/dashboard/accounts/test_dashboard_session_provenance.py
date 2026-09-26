from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from flask import Flask

from subsystems.security.kotibot_security import (
    KotiBotSecurity,
    SecurityConfig,
)
from subsystems.security.security_routes import (
    register_security_routes,
    request_policy,
)


class DashboardSessionProvenanceTests(unittest.TestCase):
    BASE_URL = "https://kotibot.example"
    LOGIN_EMAIL = "session-test@example.com"
    LOGIN_PASSWORD = "StrongPass1!"
    ANDROID_WEBVIEW_UA = (
        "Mozilla/5.0 (Linux; Android 14; TestPhone Build/TEST; wv) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 "
        "Chrome/126.0.0.0 Mobile Safari/537.36"
    )
    FIREFOX_UA = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) "
        "Gecko/20100101 Firefox/128.0"
    )

    def setUp(self):
        self.temp_dir = TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)

        self.app = Flask(__name__)
        self.app.config["TESTING"] = True

        self.security = KotiBotSecurity(
            SecurityConfig(
                base_dir=Path(self.temp_dir.name),
                allowed_origins=(
                    ("https", "kotibot.example", 443),
                ),
                trusted_hosts=("kotibot.example",),
            )
        )
        self.security.set_dashboard_login(
            self.LOGIN_EMAIL,
            self.LOGIN_PASSWORD,
        )
        self.security.init_app(self.app)
        register_security_routes(
            self.app,
            {"security": self.security},
        )

        @self.app.get("/")
        def dashboard():
            return "ok"

        self.client = self.app.test_client()

    def _login(
        self,
        *,
        remote_addr="192.0.2.44",
        user_agent=None,
        forwarded_for="203.0.113.99",
    ):
        return self.client.post(
            "/login",
            base_url=self.BASE_URL,
            data={
                "email": self.LOGIN_EMAIL,
                "password": self.LOGIN_PASSWORD,
            },
            headers={
                "Origin": self.BASE_URL,
                "User-Agent": user_agent or self.ANDROID_WEBVIEW_UA,
                # With no trusted proxy configured, this attacker-controlled
                # value must not replace REMOTE_ADDR.
                "X-Forwarded-For": forwarded_for,
            },
            environ_overrides={
                "REMOTE_ADDR": remote_addr,
            },
            follow_redirects=False,
        )

    def test_session_endpoint_fails_closed_without_dashboard_session(self):
        self.assertEqual(
            request_policy(
                "GET",
                "/api/security/dashboard-sessions",
            ),
            "dashboard",
        )

        response = self.app.test_client().get(
            "/api/security/dashboard-sessions",
            base_url=self.BASE_URL,
        )
        self.assertEqual(response.status_code, 401)

    def test_login_username_is_retrievable_from_security_status(self):
        response = self._login()
        self.assertEqual(response.status_code, 303)

        status_response = self.client.get(
            "/api/security/status",
            base_url=self.BASE_URL,
        )
        self.assertEqual(status_response.status_code, 200)

        data = status_response.get_json()
        self.assertEqual(
            data["dashboard_user_email"],
            self.LOGIN_EMAIL,
        )

    def test_session_list_exposes_bounded_provenance_but_no_secret_identifier(self):
        response = self._login()
        self.assertEqual(response.status_code, 303)

        session_response = self.client.get(
            "/api/security/dashboard-sessions",
            base_url=self.BASE_URL,
            headers={
                "User-Agent": self.ANDROID_WEBVIEW_UA,
            },
            environ_overrides={
                "REMOTE_ADDR": "192.0.2.44",
            },
        )
        self.assertEqual(session_response.status_code, 200)

        data = session_response.get_json()
        self.assertEqual(data["dashboard_session_count"], 1)

        session = data["dashboard_sessions"][0]

        self.assertEqual(session["username"], self.LOGIN_EMAIL)
        self.assertEqual(session["created_ip"], "192.0.2.44")
        self.assertEqual(session["last_seen_ip"], "192.0.2.44")
        self.assertEqual(session["browser"], "Android WebView")
        self.assertEqual(session["os"], "Android")
        self.assertEqual(session["device"], "phone")
        self.assertEqual(session["client_kind"], "android_webview")
        self.assertTrue(session["current"])

        for forbidden in (
            "session_id",
            "session_key",
            "token",
            "cookie",
            "signature",
            "user_agent",
            "password",
        ):
            self.assertNotIn(forbidden, session)

    def test_untrusted_forwarded_for_does_not_replace_direct_ip(self):
        response = self._login(
            remote_addr="192.0.2.55",
            forwarded_for="198.51.100.200",
        )
        self.assertEqual(response.status_code, 303)

        data = self.client.get(
            "/api/security/dashboard-sessions",
            base_url=self.BASE_URL,
            headers={
                "User-Agent": self.ANDROID_WEBVIEW_UA,
                "X-Forwarded-For": "198.51.100.200",
            },
            environ_overrides={
                "REMOTE_ADDR": "192.0.2.55",
            },
        ).get_json()

        session = data["dashboard_sessions"][0]
        self.assertEqual(session["created_ip"], "192.0.2.55")
        self.assertEqual(session["last_seen_ip"], "192.0.2.55")

    def test_refresh_reuses_existing_session_write_and_updates_latest_provenance(self):
        response = self._login(
            remote_addr="192.0.2.44",
            user_agent=self.ANDROID_WEBVIEW_UA,
        )
        self.assertEqual(response.status_code, 303)

        refresh_response = self.client.get(
            "/",
            base_url=self.BASE_URL,
            headers={
                "User-Agent": self.FIREFOX_UA,
            },
            environ_overrides={
                "REMOTE_ADDR": "192.0.2.77",
            },
        )
        self.assertEqual(refresh_response.status_code, 200)

        data = self.client.get(
            "/api/security/dashboard-sessions",
            base_url=self.BASE_URL,
            headers={
                "User-Agent": self.FIREFOX_UA,
            },
            environ_overrides={
                "REMOTE_ADDR": "192.0.2.77",
            },
        ).get_json()

        session = data["dashboard_sessions"][0]
        self.assertEqual(session["created_ip"], "192.0.2.44")
        self.assertEqual(session["last_seen_ip"], "192.0.2.77")
        self.assertEqual(session["browser"], "Firefox")
        self.assertEqual(session["os"], "Windows")
        self.assertEqual(session["device"], "desktop")
        self.assertEqual(session["client_kind"], "browser")

    def test_raw_user_agent_is_not_persisted(self):
        response = self._login()
        self.assertEqual(response.status_code, 303)

        state_text = self.security.config.state_file.read_text(
            encoding="utf-8"
        )

        self.assertNotIn("Mozilla/5.0", state_text)
        self.assertNotIn("TestPhone", state_text)
        self.assertNotIn(self.ANDROID_WEBVIEW_UA, state_text)


if __name__ == "__main__":
    unittest.main()

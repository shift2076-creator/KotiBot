from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from flask import Flask

from subsystems.security.kotibot_security import (
    KotiBotSecurity,
    SecurityConfig,
)
from subsystems.security.security_routes import register_security_routes


class DashboardSessionManagementTests(unittest.TestCase):
    BASE_URL = "https://kotibot.example"
    USER_A = "session-a@example.com"
    PASSWORD_A = "StrongPass1!"
    USER_B = "session-b@example.com"
    PASSWORD_B = "OtherPass2!"
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
                allowed_origins=(("https", "kotibot.example", 443),),
                trusted_hosts=("kotibot.example",),
            )
        )
        self.security.set_dashboard_login(
            self.USER_A,
            self.PASSWORD_A,
        )
        self.security.add_dashboard_user(
            self.USER_B,
            self.PASSWORD_B,
        )
        self.security.init_app(self.app)
        register_security_routes(
            self.app,
            {"security": self.security},
        )

        @self.app.get("/")
        def dashboard():
            return "ok"

    def _client(self):
        return self.app.test_client()

    def _login(
        self,
        client,
        email=None,
        password=None,
        *,
        remote_addr="192.0.2.44",
        user_agent=None,
    ):
        response = client.post(
            "/login",
            base_url=self.BASE_URL,
            data={
                "email": email or self.USER_A,
                "password": password or self.PASSWORD_A,
            },
            headers={
                "Origin": self.BASE_URL,
                "User-Agent": user_agent or self.ANDROID_WEBVIEW_UA,
            },
            environ_overrides={
                "REMOTE_ADDR": remote_addr,
            },
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 303)
        return response

    def _delete(self, client, payload, origin=None):
        return client.delete(
            "/api/security/dashboard-sessions",
            base_url=self.BASE_URL,
            json=payload,
            headers={
                "Origin": origin or self.BASE_URL,
            },
        )

    def _sessions(self, client, **kwargs):
        response = client.get(
            "/api/security/dashboard-sessions",
            base_url=self.BASE_URL,
            **kwargs,
        )
        self.assertEqual(response.status_code, 200)
        return response.get_json()["dashboard_sessions"]

    def test_delete_endpoint_fails_closed_without_dashboard_session(self):
        response = self._delete(
            self._client(),
            {"scope": "others"},
        )
        self.assertEqual(response.status_code, 401)

    def test_bulk_revoke_preserves_current_and_revokes_every_other_user_session(self):
        current = self._client()
        same_user_peer = self._client()
        other_user = self._client()

        self._login(current)
        self._login(same_user_peer, remote_addr="192.0.2.45")
        self._login(
            other_user,
            self.USER_B,
            self.PASSWORD_B,
            remote_addr="192.0.2.46",
        )

        self.assertEqual(len(self._sessions(current)), 3)

        response = self._delete(
            current,
            {"scope": "others"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["revoked_count"], 2)

        remaining = self._sessions(current)
        self.assertEqual(len(remaining), 1)
        self.assertTrue(remaining[0]["current"])
        self.assertEqual(remaining[0]["username"], self.USER_A)

        self.assertEqual(
            same_user_peer.get(
                "/api/security/status",
                base_url=self.BASE_URL,
            ).status_code,
            401,
        )
        self.assertEqual(
            other_user.get(
                "/api/security/status",
                base_url=self.BASE_URL,
            ).status_code,
            401,
        )

    def test_individual_revoke_uses_opaque_ref_and_preserves_current(self):
        current = self._client()
        peer = self._client()

        self._login(current)
        self._login(peer, remote_addr="192.0.2.55")

        sessions = self._sessions(current)
        current_row = next(item for item in sessions if item["current"])
        peer_row = next(item for item in sessions if not item["current"])

        self.assertTrue(current_row["session_ref"])
        self.assertTrue(peer_row["session_ref"])

        state_text = self.security.config.state_file.read_text(
            encoding="utf-8"
        )
        self.assertNotIn(current_row["session_ref"], state_text)
        self.assertNotIn(peer_row["session_ref"], state_text)

        for forbidden in (
            "session_id",
            "session_key",
            "token",
            "cookie",
            "signature",
            "user_agent",
            "password",
        ):
            self.assertNotIn(forbidden, peer_row)

        response = self._delete(
            current,
            {"session_ref": peer_row["session_ref"]},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["revoked_count"], 1)
        self.assertEqual(len(self._sessions(current)), 1)
        self.assertEqual(
            peer.get(
                "/api/security/status",
                base_url=self.BASE_URL,
            ).status_code,
            401,
        )

    def test_individual_revoke_refuses_current_session(self):
        current = self._client()
        self._login(current)

        current_row = next(
            item
            for item in self._sessions(current)
            if item["current"]
        )

        response = self._delete(
            current,
            {"session_ref": current_row["session_ref"]},
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            response.get_json()["error"],
            "current_session_requires_logout",
        )
        self.assertEqual(
            current.get(
                "/api/security/status",
                base_url=self.BASE_URL,
            ).status_code,
            200,
        )

    def test_cross_origin_bulk_revoke_is_blocked(self):
        current = self._client()
        peer = self._client()
        self._login(current)
        self._login(peer, remote_addr="192.0.2.66")

        response = self._delete(
            current,
            {"scope": "others"},
            origin="https://attacker.example",
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(len(self._sessions(current)), 2)

    def test_session_listing_refreshes_current_response_without_state_write(self):
        current = self._client()
        self._login(
            current,
            remote_addr="192.0.2.44",
            user_agent=self.ANDROID_WEBVIEW_UA,
        )

        before = self.security.config.state_file.read_bytes()

        sessions = self._sessions(
            current,
            headers={"User-Agent": self.FIREFOX_UA},
            environ_overrides={"REMOTE_ADDR": "192.0.2.77"},
        )

        after = self.security.config.state_file.read_bytes()
        self.assertEqual(before, after)

        current_row = next(item for item in sessions if item["current"])
        self.assertEqual(current_row["created_ip"], "192.0.2.44")
        self.assertEqual(current_row["last_seen_ip"], "192.0.2.77")
        self.assertEqual(current_row["browser"], "Firefox")
        self.assertEqual(current_row["os"], "Windows")
        self.assertEqual(current_row["device"], "desktop")
        self.assertEqual(current_row["client_kind"], "browser")


if __name__ == "__main__":
    unittest.main()

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from flask import Flask

from subsystems.security.kotibot_security import (
    DASHBOARD_SESSION_ROTATION_RECOVERY_KEY,
    KotiBotSecurity,
    SecurityConfig,
)
from subsystems.security.security_routes import register_security_routes


class DashboardSessionCredentialRotationTests(unittest.TestCase):
    BASE_URL = "https://kotibot.example"
    USER = "rotation@example.com"
    PASSWORD = "StrongPass1!"

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
            self.USER,
            self.PASSWORD,
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

    def _login(self, client, remote_addr="192.0.2.40"):
        response = client.post(
            "/login",
            base_url=self.BASE_URL,
            data={
                "email": self.USER,
                "password": self.PASSWORD,
            },
            headers={"Origin": self.BASE_URL},
            environ_overrides={"REMOTE_ADDR": remote_addr},
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 303)

    def _rotate(self, client, origin=None, confirmation=None):
        return client.post(
            "/api/security/dashboard-session-credential/rotate",
            base_url=self.BASE_URL,
            json={
                "confirmation": confirmation
                or "rotate-dashboard-session-credential",
            },
            headers={"Origin": origin or self.BASE_URL},
        )

    def _rollback(self, client, origin=None, confirmation=None):
        return client.post(
            "/api/security/dashboard-session-credential/rollback",
            base_url=self.BASE_URL,
            json={
                "confirmation": confirmation
                or "rollback-dashboard-session-credential",
            },
            headers={"Origin": origin or self.BASE_URL},
        )

    def _status(self, client):
        return client.get(
            "/api/security/status",
            base_url=self.BASE_URL,
        )

    def test_rotation_revokes_all_sessions_and_preserves_protected_recovery(self):
        current = self._client()
        peer = self._client()
        self._login(current)
        self._login(peer, remote_addr="192.0.2.41")

        previous_secret = self.security.state["session_secret"]
        previous_sessions = dict(
            self.security.state["dashboard_sessions"]
        )
        self.assertEqual(
            self._status(current).get_json()[
                "dashboard_session_rotation_recovery"
            ],
            "none",
        )

        response = self._rotate(current)
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["revoked_session_count"], 2)
        self.assertTrue(data["recovery_preserved"])
        self.assertNotIn("session_secret", data)
        self.assertNotIn(previous_secret, response.get_data(as_text=True))

        recovery = self.security.state[
            DASHBOARD_SESSION_ROTATION_RECOVERY_KEY
        ]
        self.assertEqual(recovery["status"], "retired")
        self.assertEqual(recovery["session_secret"], previous_secret)
        self.assertEqual(
            recovery["dashboard_sessions"],
            previous_sessions,
        )
        self.assertNotEqual(
            self.security.state["session_secret"],
            previous_secret,
        )
        self.assertEqual(
            self.security.state["dashboard_sessions"],
            {},
        )
        self.assertEqual(self._status(current).status_code, 401)
        self.assertEqual(self._status(peer).status_code, 401)

        fresh = self._client()
        self._login(fresh, remote_addr="192.0.2.42")
        fresh_status = self._status(fresh)
        self.assertEqual(fresh_status.status_code, 200)
        self.assertEqual(
            fresh_status.get_json()[
                "dashboard_session_rotation_recovery"
            ],
            "available",
        )

    def test_rotation_requires_auth_same_origin_and_exact_confirmation(self):
        original_secret = self.security.state["session_secret"]
        unauthenticated = self._client()
        self.assertEqual(
            self._rotate(unauthenticated).status_code,
            401,
        )

        current = self._client()
        self._login(current)
        self.assertEqual(
            self._rotate(
                current,
                origin="https://attacker.example",
            ).status_code,
            403,
        )
        self.assertEqual(
            self._rotate(
                current,
                confirmation="rotate",
            ).status_code,
            400,
        )
        self.assertEqual(
            self.security.state["session_secret"],
            original_secret,
        )
        self.assertNotIn(
            DASHBOARD_SESSION_ROTATION_RECOVERY_KEY,
            self.security.state,
        )

    def test_second_rotation_cannot_overwrite_recovery(self):
        current = self._client()
        self._login(current)
        self.assertEqual(self._rotate(current).status_code, 200)

        fresh = self._client()
        self._login(fresh)
        active_secret = self.security.state["session_secret"]
        recovery = self.security.state[
            DASHBOARD_SESSION_ROTATION_RECOVERY_KEY
        ]

        response = self._rotate(fresh)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            response.get_json()["error"],
            "dashboard_session_rotation_recovery_exists",
        )
        self.assertEqual(
            self.security.state["session_secret"],
            active_secret,
        )
        self.assertIs(
            self.security.state[
                DASHBOARD_SESSION_ROTATION_RECOVERY_KEY
            ],
            recovery,
        )

    def test_rotation_restores_in_memory_state_when_atomic_save_fails(self):
        current_secret = self.security.state["session_secret"]
        current_sessions = {
            "existing": {
                "expires_at": 1,
            }
        }
        self.security.state[
            "dashboard_sessions"
        ] = current_sessions

        def fail_save():
            raise OSError("simulated atomic write failure")

        self.security._save_state = fail_save

        with self.assertRaises(OSError):
            self.security.rotate_dashboard_session_credential()

        self.assertEqual(
            self.security.state["session_secret"],
            current_secret,
        )
        self.assertIs(
            self.security.state["dashboard_sessions"],
            current_sessions,
        )
        self.assertNotIn(
            DASHBOARD_SESSION_ROTATION_RECOVERY_KEY,
            self.security.state,
        )

    def test_authenticated_rollback_restores_prior_sessions(self):
        current = self._client()
        prior_peer = self._client()
        self._login(current)
        self._login(prior_peer, remote_addr="192.0.2.51")
        previous_secret = self.security.state["session_secret"]

        self.assertEqual(self._rotate(current).status_code, 200)

        fresh = self._client()
        self._login(fresh, remote_addr="192.0.2.52")
        replacement_secret = self.security.state["session_secret"]
        response = self._rollback(fresh)

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["invalidated_session_count"], 1)
        self.assertEqual(data["restored_session_count"], 2)
        self.assertFalse(data["recovery_preserved"])
        self.assertNotIn("session_secret", data)
        self.assertNotIn(previous_secret, response.get_data(as_text=True))
        self.assertNotIn(
            replacement_secret,
            response.get_data(as_text=True),
        )
        self.assertEqual(
            self.security.state["session_secret"],
            previous_secret,
        )
        self.assertNotIn(
            DASHBOARD_SESSION_ROTATION_RECOVERY_KEY,
            self.security.state,
        )
        self.assertEqual(self._status(fresh).status_code, 401)
        self.assertEqual(self._status(prior_peer).status_code, 200)

    def test_malformed_recovery_fails_closed(self):
        current = self._client()
        self._login(current)
        self.security.state[
            DASHBOARD_SESSION_ROTATION_RECOVERY_KEY
        ] = {"version": 1, "status": "retired"}
        self.security._save_state()

        status = self._status(current)
        self.assertEqual(
            status.get_json()[
                "dashboard_session_rotation_recovery"
            ],
            "malformed",
        )
        self.assertEqual(self._rotate(current).status_code, 409)
        rollback = self._rollback(current)
        self.assertEqual(rollback.status_code, 409)
        self.assertEqual(
            rollback.get_json()["error"],
            "dashboard_session_rotation_recovery_malformed",
        )


class DashboardSessionCredentialRotationUiContractTests(
    unittest.TestCase
):
    def test_dashboard_control_is_wired_end_to_end(self):
        root = Path(__file__).resolve().parents[1]
        api = (root / "static/js/dashboard-api.js").read_text(
            encoding="utf-8"
        )
        actions = (
            root / "static/js/dashboard-actions.js"
        ).read_text(encoding="utf-8")
        events = (
            root / "static/js/dashboard-events.js"
        ).read_text(encoding="utf-8")
        render = (
            root / "static/js/dashboard-render.js"
        ).read_text(encoding="utf-8")

        for path in (
            "/api/security/dashboard-session-credential/rotate",
            "/api/security/dashboard-session-credential/rollback",
        ):
            self.assertIn(path, api)

        for action in (
            "rotate-dashboard-session-credential",
            "rollback-dashboard-session-credential",
        ):
            self.assertIn(f'data-dashboard-action="{action}"', render)
            self.assertIn(f'"{action}"', events)

        self.assertIn(
            "rotateDashboardSessionCredentialFromSettings",
            actions,
        )
        self.assertIn(
            "rollbackDashboardSessionCredentialFromSettings",
            actions,
        )


if __name__ == "__main__":
    unittest.main()

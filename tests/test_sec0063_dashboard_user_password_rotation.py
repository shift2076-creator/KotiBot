import copy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from flask import Flask

from subsystems.security.kotibot_security import (
    DASHBOARD_SESSION_ROTATION_RECOVERY_KEY,
    DASHBOARD_USER_PASSWORD_ROTATION_RECOVERY_KEY,
    KotiBotSecurity,
    SecurityConfig,
)
from subsystems.security.security_routes import register_security_routes


class DashboardUserPasswordRotationTests(unittest.TestCase):
    BASE_URL = "https://kotibot.example"
    USER_A = "rotation-a@example.com"
    PASSWORD_A = "StrongPass1!"
    NEW_PASSWORD_A = "FreshPass2@"
    USER_B = "rotation-b@example.com"
    PASSWORD_B = "OtherPass3#"
    NEW_PASSWORD_B = "ChangedPass4$"

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
        remote_addr="192.0.2.40",
    ):
        return client.post(
            "/login",
            base_url=self.BASE_URL,
            data={
                "email": email or self.USER_A,
                "password": password or self.PASSWORD_A,
            },
            headers={"Origin": self.BASE_URL},
            environ_overrides={"REMOTE_ADDR": remote_addr},
            follow_redirects=False,
        )

    def _assert_login_succeeds(
        self,
        client,
        email,
        password,
    ):
        response = self._login(client, email, password)
        self.assertEqual(response.status_code, 303)
        self.assertNotIn("login_error", response.headers["Location"])
        self.assertEqual(self._status(client).status_code, 200)

    def _assert_login_fails(
        self,
        client,
        email,
        password,
    ):
        response = self._login(client, email, password)
        self.assertEqual(response.status_code, 303)
        self.assertIn("login_error=bad", response.headers["Location"])
        self.assertEqual(self._status(client).status_code, 401)

    def _status(self, client):
        return client.get(
            "/api/security/status",
            base_url=self.BASE_URL,
        )

    def _rotate(
        self,
        client,
        email,
        password,
        *,
        origin=None,
        confirmation=None,
    ):
        return client.post(
            "/api/security/dashboard-user-password/rotate",
            base_url=self.BASE_URL,
            json={
                "email": email,
                "password": password,
                "confirmation": confirmation
                or "rotate-dashboard-user-password",
            },
            headers={"Origin": origin or self.BASE_URL},
        )

    def _rollback(
        self,
        client,
        email,
        *,
        origin=None,
        confirmation=None,
    ):
        return client.post(
            "/api/security/dashboard-user-password/rollback",
            base_url=self.BASE_URL,
            json={
                "email": email,
                "confirmation": confirmation
                or "rollback-dashboard-user-password",
            },
            headers={"Origin": origin or self.BASE_URL},
        )

    def _finalize_password(
        self,
        client,
        email,
        *,
        origin=None,
        confirmation=None,
    ):
        return client.post(
            "/api/security/dashboard-user-password/finalize",
            base_url=self.BASE_URL,
            json={
                "email": email,
                "confirmation": confirmation
                or "finalize-dashboard-user-password",
            },
            headers={"Origin": origin or self.BASE_URL},
        )

    def _rotate_session(self, client):
        return client.post(
            "/api/security/dashboard-session-credential/rotate",
            base_url=self.BASE_URL,
            json={
                "confirmation": (
                    "rotate-dashboard-session-credential"
                )
            },
            headers={"Origin": self.BASE_URL},
        )

    def _finalize_session(
        self,
        client,
        *,
        confirmation=None,
    ):
        return client.post(
            "/api/security/dashboard-session-credential/finalize",
            base_url=self.BASE_URL,
            json={
                "confirmation": confirmation
                or "finalize-dashboard-session-credential"
            },
            headers={"Origin": self.BASE_URL},
        )

    def test_current_user_rotation_revokes_sessions_and_preserves_recovery(self):
        current = self._client()
        peer = self._client()
        self._assert_login_succeeds(
            current,
            self.USER_A,
            self.PASSWORD_A,
        )
        self._assert_login_succeeds(
            peer,
            self.USER_A,
            self.PASSWORD_A,
        )

        previous_hash = self.security.state[
            "dashboard_users"
        ][self.USER_A]["password_hash"]
        response = self._rotate(
            current,
            self.USER_A,
            self.NEW_PASSWORD_A,
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["revoked_session_count"], 2)
        self.assertTrue(data["recovery_preserved"])
        self.assertTrue(data["current_session_revoked"])
        response_text = response.get_data(as_text=True)
        self.assertNotIn("password_hash", response_text)
        self.assertNotIn(previous_hash, response_text)
        self.assertNotIn(self.NEW_PASSWORD_A, response_text)

        recovery = self.security.state[
            DASHBOARD_USER_PASSWORD_ROTATION_RECOVERY_KEY
        ][self.USER_A]
        self.assertEqual(recovery["status"], "retired")
        self.assertEqual(recovery["password_hash"], previous_hash)
        self.assertNotEqual(
            self.security.state["dashboard_users"][
                self.USER_A
            ]["password_hash"],
            previous_hash,
        )
        self.assertEqual(self._status(current).status_code, 401)
        self.assertEqual(self._status(peer).status_code, 401)

        old_login = self._client()
        self._assert_login_fails(
            old_login,
            self.USER_A,
            self.PASSWORD_A,
        )

        fresh = self._client()
        self._assert_login_succeeds(
            fresh,
            self.USER_A,
            self.NEW_PASSWORD_A,
        )
        self.assertEqual(
            self._status(fresh).get_json()[
                "dashboard_user_password_rotation_recovery"
            ],
            "available",
        )

    def test_rollback_restores_previous_password_without_old_sessions(self):
        current = self._client()
        self._assert_login_succeeds(
            current,
            self.USER_A,
            self.PASSWORD_A,
        )
        self.assertEqual(
            self._rotate(
                current,
                self.USER_A,
                self.NEW_PASSWORD_A,
            ).status_code,
            200,
        )

        fresh = self._client()
        self._assert_login_succeeds(
            fresh,
            self.USER_A,
            self.NEW_PASSWORD_A,
        )
        response = self._rollback(fresh, self.USER_A)

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["revoked_session_count"], 1)
        self.assertFalse(data["recovery_preserved"])
        self.assertTrue(data["current_session_revoked"])
        self.assertEqual(self._status(fresh).status_code, 401)
        self.assertNotIn(
            self.USER_A,
            self.security.state.get(
                DASHBOARD_USER_PASSWORD_ROTATION_RECOVERY_KEY,
                {},
            ),
        )

        new_login = self._client()
        self._assert_login_fails(
            new_login,
            self.USER_A,
            self.NEW_PASSWORD_A,
        )
        restored_login = self._client()
        self._assert_login_succeeds(
            restored_login,
            self.USER_A,
            self.PASSWORD_A,
        )

    def test_password_finalization_deletes_only_retired_hash(self):
        current = self._client()
        self._assert_login_succeeds(
            current,
            self.USER_A,
            self.PASSWORD_A,
        )
        self.assertEqual(
            self._rotate(
                current,
                self.USER_A,
                self.NEW_PASSWORD_A,
            ).status_code,
            200,
        )

        fresh = self._client()
        self._assert_login_succeeds(
            fresh,
            self.USER_A,
            self.NEW_PASSWORD_A,
        )
        response = self._finalize_password(
            fresh,
            self.USER_A,
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.get_json()["recovery_preserved"])
        self.assertEqual(self._status(fresh).status_code, 200)
        self.assertNotIn(
            DASHBOARD_USER_PASSWORD_ROTATION_RECOVERY_KEY,
            self.security.state,
        )

        old_login = self._client()
        self._assert_login_fails(
            old_login,
            self.USER_A,
            self.PASSWORD_A,
        )
        current_login = self._client()
        self._assert_login_succeeds(
            current_login,
            self.USER_A,
            self.NEW_PASSWORD_A,
        )
        repeat = self._finalize_password(
            fresh,
            self.USER_A,
        )
        self.assertEqual(repeat.status_code, 409)
        self.assertEqual(
            repeat.get_json()["error"],
            "dashboard_user_password_rotation_recovery_missing",
        )

    def test_session_finalization_keeps_fresh_login_and_deletes_recovery(self):
        current = self._client()
        self._assert_login_succeeds(
            current,
            self.USER_A,
            self.PASSWORD_A,
        )
        previous_secret = self.security.state["session_secret"]
        rotated = self._rotate_session(current)
        self.assertEqual(rotated.status_code, 200)
        self.assertEqual(self._status(current).status_code, 401)
        self.assertIn(
            DASHBOARD_SESSION_ROTATION_RECOVERY_KEY,
            self.security.state,
        )

        fresh = self._client()
        self._assert_login_succeeds(
            fresh,
            self.USER_A,
            self.PASSWORD_A,
        )
        response = self._finalize_session(fresh)

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["retired_session_count"], 1)
        self.assertFalse(data["recovery_preserved"])
        self.assertEqual(self._status(fresh).status_code, 200)
        self.assertNotIn(
            DASHBOARD_SESSION_ROTATION_RECOVERY_KEY,
            self.security.state,
        )
        self.assertNotEqual(
            self.security.state["session_secret"],
            previous_secret,
        )
        self.assertNotIn(
            previous_secret,
            response.get_data(as_text=True),
        )

    def test_finalization_requires_auth_origin_and_exact_confirmation(self):
        unauthenticated = self._client()
        self.assertEqual(
            self._finalize_password(
                unauthenticated,
                self.USER_A,
            ).status_code,
            401,
        )

        admin = self._client()
        self._assert_login_succeeds(
            admin,
            self.USER_A,
            self.PASSWORD_A,
        )
        self.assertEqual(
            self._rotate(
                admin,
                self.USER_B,
                self.NEW_PASSWORD_B,
            ).status_code,
            200,
        )
        self.assertEqual(
            self._finalize_password(
                admin,
                self.USER_B,
                origin="https://attacker.example",
            ).status_code,
            403,
        )
        self.assertEqual(
            self._finalize_password(
                admin,
                self.USER_B,
                confirmation="finalize",
            ).status_code,
            400,
        )
        self.assertIn(
            self.USER_B,
            self.security.state[
                DASHBOARD_USER_PASSWORD_ROTATION_RECOVERY_KEY
            ],
        )

        session_admin = self._client()
        self._assert_login_succeeds(
            session_admin,
            self.USER_A,
            self.PASSWORD_A,
        )
        self.assertEqual(
            self._rotate_session(session_admin).status_code,
            200,
        )
        fresh = self._client()
        self._assert_login_succeeds(
            fresh,
            self.USER_A,
            self.PASSWORD_A,
        )
        self.assertEqual(
            self._finalize_session(
                fresh,
                confirmation="finalize",
            ).status_code,
            400,
        )
        self.assertIn(
            DASHBOARD_SESSION_ROTATION_RECOVERY_KEY,
            self.security.state,
        )

    def test_other_user_rotation_preserves_admin_and_revokes_target(self):
        admin = self._client()
        target = self._client()
        self._assert_login_succeeds(
            admin,
            self.USER_A,
            self.PASSWORD_A,
        )
        self._assert_login_succeeds(
            target,
            self.USER_B,
            self.PASSWORD_B,
        )

        response = self._rotate(
            admin,
            self.USER_B,
            self.NEW_PASSWORD_B,
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            response.get_json()["current_session_revoked"]
        )
        self.assertEqual(self._status(admin).status_code, 200)
        self.assertEqual(self._status(target).status_code, 401)

        users = admin.get(
            "/api/security/dashboard-users",
            base_url=self.BASE_URL,
        ).get_json()["dashboard_users"]
        target_row = next(
            user for user in users
            if user["email"] == self.USER_B
        )
        self.assertEqual(
            target_row["password_rotation_recovery"],
            "available",
        )

        fresh_target = self._client()
        self._assert_login_succeeds(
            fresh_target,
            self.USER_B,
            self.NEW_PASSWORD_B,
        )

    def test_rotation_requires_auth_origin_confirmation_and_new_password(self):
        original_user = copy.deepcopy(
            self.security.state["dashboard_users"][self.USER_A]
        )
        unauthenticated = self._client()
        self.assertEqual(
            self._rotate(
                unauthenticated,
                self.USER_A,
                self.NEW_PASSWORD_A,
            ).status_code,
            401,
        )

        current = self._client()
        self._assert_login_succeeds(
            current,
            self.USER_A,
            self.PASSWORD_A,
        )
        self.assertEqual(
            self._rotate(
                current,
                self.USER_A,
                self.NEW_PASSWORD_A,
                origin="https://attacker.example",
            ).status_code,
            403,
        )
        self.assertEqual(
            self._rotate(
                current,
                self.USER_A,
                self.NEW_PASSWORD_A,
                confirmation="rotate",
            ).status_code,
            400,
        )
        unchanged = self._rotate(
            current,
            self.USER_A,
            self.PASSWORD_A,
        )
        self.assertEqual(unchanged.status_code, 409)
        self.assertEqual(
            unchanged.get_json()["error"],
            "dashboard_user_password_unchanged",
        )
        self.assertEqual(
            self.security.state["dashboard_users"][self.USER_A],
            original_user,
        )
        self.assertNotIn(
            DASHBOARD_USER_PASSWORD_ROTATION_RECOVERY_KEY,
            self.security.state,
        )

    def test_recovery_cannot_be_overwritten_or_orphaned(self):
        admin = self._client()
        self._assert_login_succeeds(
            admin,
            self.USER_A,
            self.PASSWORD_A,
        )
        self.assertEqual(
            self._rotate(
                admin,
                self.USER_B,
                self.NEW_PASSWORD_B,
            ).status_code,
            200,
        )

        second = self._rotate(
            admin,
            self.USER_B,
            "AnotherPass5%",
        )
        self.assertEqual(second.status_code, 409)
        self.assertEqual(
            second.get_json()["error"],
            "dashboard_user_password_rotation_recovery_exists",
        )

        duplicate = admin.post(
            "/api/security/dashboard-users",
            base_url=self.BASE_URL,
            json={
                "email": self.USER_B,
                "password": "AnotherPass5%",
            },
            headers={"Origin": self.BASE_URL},
        )
        self.assertEqual(duplicate.status_code, 400)
        self.assertEqual(
            duplicate.get_json()["error"],
            "dashboard user already exists",
        )

        removal = admin.delete(
            "/api/security/dashboard-users",
            base_url=self.BASE_URL,
            json={"email": self.USER_B},
            headers={"Origin": self.BASE_URL},
        )
        self.assertEqual(removal.status_code, 400)
        self.assertIn(
            "resolve password rotation recovery",
            removal.get_json()["error"],
        )
        self.assertIn(
            self.USER_B,
            self.security.state["dashboard_users"],
        )

    def test_malformed_recovery_fails_closed(self):
        current = self._client()
        self._assert_login_succeeds(
            current,
            self.USER_A,
            self.PASSWORD_A,
        )
        self.security.state[
            DASHBOARD_USER_PASSWORD_ROTATION_RECOVERY_KEY
        ] = {
            self.USER_A: {
                "version": 1,
                "status": "retired",
            }
        }
        self.security._save_state()

        status = self._status(current).get_json()
        self.assertEqual(
            status[
                "dashboard_user_password_rotation_recovery"
            ],
            "malformed",
        )
        rotation = self._rotate(
            current,
            self.USER_A,
            self.NEW_PASSWORD_A,
        )
        self.assertEqual(rotation.status_code, 409)
        self.assertEqual(
            rotation.get_json()["error"],
            "dashboard_user_password_rotation_recovery_malformed",
        )
        rollback = self._rollback(current, self.USER_A)
        self.assertEqual(rollback.status_code, 409)
        self.assertEqual(
            rollback.get_json()["error"],
            "dashboard_user_password_rotation_recovery_malformed",
        )
        finalization = self._finalize_password(
            current,
            self.USER_A,
        )
        self.assertEqual(finalization.status_code, 409)
        self.assertEqual(
            finalization.get_json()["error"],
            "dashboard_user_password_rotation_recovery_malformed",
        )

    def test_atomic_save_failure_restores_user_sessions_and_recovery(self):
        current = self._client()
        self._assert_login_succeeds(
            current,
            self.USER_A,
            self.PASSWORD_A,
        )
        original_user = copy.deepcopy(
            self.security.state["dashboard_users"][self.USER_A]
        )
        original_sessions = copy.deepcopy(
            self.security.state["dashboard_sessions"]
        )

        def fail_save():
            raise OSError("simulated atomic write failure")

        self.security._save_state = fail_save

        with self.assertRaises(OSError):
            self.security.rotate_dashboard_user_password(
                self.USER_A,
                self.NEW_PASSWORD_A,
            )

        self.assertEqual(
            self.security.state["dashboard_users"][self.USER_A],
            original_user,
        )
        self.assertEqual(
            self.security.state["dashboard_sessions"],
            original_sessions,
        )
        self.assertNotIn(
            DASHBOARD_USER_PASSWORD_ROTATION_RECOVERY_KEY,
            self.security.state,
        )

    def test_finalization_save_failure_restores_retired_credentials(self):
        self.security.rotate_dashboard_user_password(
            self.USER_B,
            self.NEW_PASSWORD_B,
        )
        password_recovery = copy.deepcopy(
            self.security.state[
                DASHBOARD_USER_PASSWORD_ROTATION_RECOVERY_KEY
            ][self.USER_B]
        )
        original_save = self.security._save_state

        def fail_save():
            raise OSError("simulated atomic write failure")

        self.security._save_state = fail_save

        with self.assertRaises(OSError):
            self.security.finalize_dashboard_user_password_rotation(
                self.USER_B
            )

        self.assertEqual(
            self.security.state[
                DASHBOARD_USER_PASSWORD_ROTATION_RECOVERY_KEY
            ][self.USER_B],
            password_recovery,
        )

        self.security._save_state = original_save
        self.security.rotate_dashboard_session_credential()
        session_recovery = copy.deepcopy(
            self.security.state[
                DASHBOARD_SESSION_ROTATION_RECOVERY_KEY
            ]
        )
        self.security._save_state = fail_save

        with self.assertRaises(OSError):
            self.security.finalize_dashboard_session_credential_rotation()

        self.assertEqual(
            self.security.state[
                DASHBOARD_SESSION_ROTATION_RECOVERY_KEY
            ],
            session_recovery,
        )


class DashboardUserPasswordRotationUiContractTests(
    unittest.TestCase
):
    def test_password_controls_are_wired_end_to_end(self):
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
        styles = (root / "static/css/modals.css").read_text(
            encoding="utf-8"
        )

        for path in (
            "/api/security/dashboard-user-password/rotate",
            "/api/security/dashboard-user-password/rollback",
            "/api/security/dashboard-user-password/finalize",
            "/api/security/dashboard-session-credential/finalize",
        ):
            self.assertIn(path, api)

        for action in (
            "show-dashboard-password-rotation",
            "rotate-dashboard-user-password",
            "rollback-dashboard-user-password",
            "finalize-dashboard-user-password",
        ):
            self.assertIn(action, events)
            self.assertIn(action, render)

        self.assertIn(
            "rotateDashboardUserPasswordFromSettings",
            actions,
        )
        self.assertIn(
            "rollbackDashboardUserPasswordFromSettings",
            actions,
        )
        self.assertIn(
            "finalizeDashboardUserPasswordFromSettings",
            actions,
        )
        self.assertIn(
            "finalize-dashboard-session-credential",
            events,
        )
        self.assertIn(
            "finalize-dashboard-session-credential",
            render,
        )
        self.assertIn(
            ".settings-dashboard-user-actions",
            styles,
        )


if __name__ == "__main__":
    unittest.main()

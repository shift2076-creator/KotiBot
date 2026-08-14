import ast
import base64
from contextlib import nullcontext
import hashlib
import hmac
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import time
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

ROOT = Path(__file__).resolve().parents[1]


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _signed_headers(
    *,
    device_id: str,
    key_id: str,
    secret: str,
    path: str,
    body: bytes,
    nonce: str,
) -> dict[str, str]:
    timestamp = str(int(time.time()))
    body_sha = hashlib.sha256(body).hexdigest()
    canonical = "\n".join(
        ("POST", path, timestamp, nonce, body_sha)
    ).encode("utf-8")
    signature = _b64(
        hmac.new(
            secret.encode("utf-8"),
            canonical,
            hashlib.sha256,
        ).digest()
    )

    return {
        "X-Device-ID": device_id,
        "X-Koti-Key-ID": key_id,
        "X-Koti-Timestamp": timestamp,
        "X-Koti-Nonce": nonce,
        "X-Koti-Body-SHA256": body_sha,
        "X-Koti-Signature": signature,
        "Content-Type": "application/json",
        "User-Agent": (
            "Mozilla/5.0 (Linux; Android 14; Test Build; wv) "
            "AppleWebKit/537.36 Version/4.0 Chrome/126.0 Mobile"
        ),
    }


class KeyClientDashboardSessionTests(unittest.TestCase):
    BASE_URL = "https://kotibot.example"
    PATH = "/api/security/keyclient-session"
    DEVICE_ID = "control-device"

    def setUp(self):
        self.temp_dir = TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.authorized_devices = {self.DEVICE_ID}

        self.app = Flask(__name__)
        self.app.config["TESTING"] = True
        self.app.config[
            "KOTIBOT_KEY_CLIENT_SESSION_AUTHORIZER"
        ] = lambda device_id: device_id in self.authorized_devices

        self.security = KotiBotSecurity(
            SecurityConfig(
                base_dir=Path(self.temp_dir.name),
                allowed_origins=(("https", "kotibot.example", 443),),
                trusted_hosts=("kotibot.example",),
            )
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
        self.issued = self.security.issue_device_key(self.DEVICE_ID)

    def _exchange(
        self,
        *,
        issued=None,
        nonce="key-client-session",
        device_id=None,
    ):
        issued = issued or self.issued
        device_id = device_id or self.DEVICE_ID
        body = json.dumps(
            {
                "deviceID": device_id,
                "type": "keyclient_dashboard_session",
            },
            separators=(",", ":"),
        ).encode("utf-8")
        headers = _signed_headers(
            device_id=device_id,
            key_id=issued["keyID"],
            secret=issued["secret"],
            path=self.PATH,
            body=body,
            nonce=nonce,
        )

        return self.client.post(
            self.PATH,
            base_url=self.BASE_URL,
            data=body,
            headers=headers,
        )

    def test_exchange_route_is_device_signed(self):
        self.assertEqual(
            request_policy("POST", self.PATH),
            "device",
        )

    def test_unsigned_exchange_fails_closed(self):
        response = self.client.post(
            self.PATH,
            base_url=self.BASE_URL,
            json={"deviceID": self.DEVICE_ID},
            headers={"X-Device-ID": self.DEVICE_ID},
        )

        self.assertEqual(response.status_code, 401)
        self.assertNotIn("Set-Cookie", response.headers)

    def test_current_key_mints_bounded_device_bound_dashboard_session(self):
        response = self._exchange()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"ok": True})

        cookie = response.headers.get("Set-Cookie", "")
        self.assertIn("kotibot_session=", cookie)
        self.assertIn("HttpOnly", cookie)
        self.assertIn("Secure", cookie)
        self.assertIn("SameSite=Strict", cookie)

        response_text = response.get_data(as_text=True)
        self.assertNotIn(self.DEVICE_ID, response_text)
        self.assertNotIn(self.issued["keyID"], response_text)
        self.assertNotIn(self.issued["secret"], response_text)

        status = self.client.get(
            "/api/security/status",
            base_url=self.BASE_URL,
        )
        self.assertEqual(status.status_code, 200)
        self.assertEqual(
            status.get_json()["dashboard_session_type"],
            "key_client",
        )
        self.assertEqual(
            status.get_json()["dashboard_user_email"],
            "",
        )

        sessions_response = self.client.get(
            "/api/security/dashboard-sessions",
            base_url=self.BASE_URL,
        )
        self.assertEqual(sessions_response.status_code, 200)
        sessions = sessions_response.get_json()["dashboard_sessions"]
        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0]["username"], "KotiBot Control")
        self.assertTrue(sessions[0]["current"])

        for forbidden in (
            "device_id",
            "key_id",
            "session_id",
            "session_key",
            "token",
            "cookie",
            "signature",
        ):
            self.assertNotIn(forbidden, sessions[0])

    def test_non_control_registry_owner_is_rejected(self):
        self.authorized_devices.clear()

        response = self._exchange()

        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            response.get_json()["error"],
            "key_client_not_authorized",
        )
        self.assertNotIn("Set-Cookie", response.headers)

    def test_previous_grace_key_cannot_mint_dashboard_session(self):
        previous = self.issued
        self.security.issue_device_key(
            self.DEVICE_ID,
            rotate=True,
        )

        response = self._exchange(
            issued=previous,
            nonce="previous-grace",
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            response.get_json()["error"],
            "current_device_key_required",
        )
        self.assertNotIn("Set-Cookie", response.headers)

    def test_rotation_invalidates_existing_key_client_session(self):
        self.assertEqual(self._exchange().status_code, 200)
        self.assertEqual(
            self.client.get(
                "/api/security/status",
                base_url=self.BASE_URL,
            ).status_code,
            200,
        )

        self.security.issue_device_key(
            self.DEVICE_ID,
            rotate=True,
        )

        self.assertEqual(
            self.client.get(
                "/api/security/status",
                base_url=self.BASE_URL,
            ).status_code,
            401,
        )

    def test_revocation_invalidates_existing_key_client_session(self):
        self.assertEqual(self._exchange().status_code, 200)

        self.security.revoke_device_key(self.DEVICE_ID)

        self.assertEqual(
            self.client.get(
                "/api/security/status",
                base_url=self.BASE_URL,
            ).status_code,
            401,
        )

    def test_reexchange_replaces_prior_session_for_same_device(self):
        first = self._exchange(nonce="first-exchange")
        second = self._exchange(nonce="second-exchange")

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertNotEqual(
            first.headers.get("Set-Cookie"),
            second.headers.get("Set-Cookie"),
        )
        self.assertEqual(
            len(self.security.state["dashboard_sessions"]),
            1,
        )

    def test_server_owner_gate_requires_provisioned_first_party_key_role(self):
        source = (ROOT / "kotibot_server.py").read_text(
            encoding="utf-8"
        )
        module = ast.parse(source)
        selected = [
            node
            for node in module.body
            if isinstance(node, ast.FunctionDef)
            and node.name in {
                "client_allows_device_key_handoff",
                "key_client_dashboard_session_allowed",
            }
        ]
        self.assertEqual(len(selected), 2)

        clients = {}
        namespace = {
            "SECURITY": type(
                "SecurityStub",
                (),
                {
                    "normalize_device_id": staticmethod(
                        lambda value: str(value or "").strip()
                    )
                },
            )(),
            "STATE_LOCK": nullcontext(),
            "CLIENTS": clients,
            "CLIENT_ROLE_CAM": "CAM",
            "CLIENT_ROLE_DSS": "DSS",
            "CLIENT_ROLE_KEY": "KEY",
            "CLIENT_ROLE_TAPO": "TAPO",
            "client_has_role": lambda client, role: (
                role in client.get("roles", ())
            ),
        }
        executable = ast.Module(body=selected, type_ignores=[])
        exec(compile(executable, "<server-owner-gate>", "exec"), namespace)
        allowed = namespace["key_client_dashboard_session_allowed"]

        cases = (
            (
                {"provisioned": True, "source": "", "roles": ["KEY"]},
                True,
            ),
            (
                {"provisioned": False, "source": "", "roles": ["KEY"]},
                False,
            ),
            (
                {"provisioned": True, "source": "", "roles": ["CAM"]},
                False,
            ),
            (
                {"provisioned": True, "source": "tapo", "roles": ["KEY"]},
                False,
            ),
            (
                {
                    "provisioned": True,
                    "source": "matter",
                    "roles": ["KEY"],
                },
                False,
            ),
            (
                {
                    "provisioned": True,
                    "source": "",
                    "roles": ["KEY", "TAPO"],
                },
                False,
            ),
        )

        for index, (record, expected) in enumerate(cases):
            with self.subTest(index=index):
                clients.clear()
                clients[self.DEVICE_ID] = record
                self.assertEqual(
                    allowed(self.DEVICE_ID),
                    expected,
                )


if __name__ == "__main__":
    unittest.main()

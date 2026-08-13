import base64
import hashlib
import hmac
from pathlib import Path
from tempfile import TemporaryDirectory
import time
import unittest

from flask import Flask

from subsystems.security.kotibot_security import (
    KotiBotSecurity,
    SecurityConfig,
)
from subsystems.security.security_routes import request_policy


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
    }


class Sec0062StagedDeviceKeyHandoffTests(unittest.TestCase):
    def _security(self):
        temp = TemporaryDirectory()
        security = KotiBotSecurity(
            SecurityConfig(base_dir=Path(temp.name))
        )
        self.addCleanup(temp.cleanup)
        return security

    def test_staging_preserves_current_and_returns_counts_only(self):
        security = self._security()
        original = security.issue_device_key("device")

        result = security.stage_device_key_handoffs(["device"])
        payload = security.device_key_handoff_payload("device")

        self.assertEqual(result["staged"], 1)
        self.assertEqual(result["already_staged"], 0)
        self.assertTrue(
            security.device_key_is_current(
                "device",
                original["keyID"],
            )
        )
        self.assertIsInstance(payload, dict)
        self.assertNotEqual(payload["kotiKeyID"], original["keyID"])

        rendered = repr(result)
        self.assertNotIn(original["keyID"], rendered)
        self.assertNotIn(original["secret"], rendered)
        self.assertNotIn(payload["kotiKeyID"], rendered)
        self.assertNotIn(payload["kotiKeySecret"], rendered)

    def test_staged_key_proves_handoff_then_promotes_atomically(self):
        security = self._security()
        app = Flask(__name__)
        original = security.issue_device_key("device")
        security.stage_device_key_handoffs(["device"])
        pending = security.device_key_handoff_payload("device")

        body = b'{"deviceID":"device"}'
        pending_headers = _signed_headers(
            device_id="device",
            key_id=pending["kotiKeyID"],
            secret=pending["kotiKeySecret"],
            path="/telemetry",
            body=body,
            nonce="pending-proof",
        )

        with app.test_request_context(
            "/telemetry",
            method="POST",
            data=body,
            headers=pending_headers,
        ):
            self.assertIsNone(
                security.require_device_signature("device")
            )

        self.assertTrue(
            security.device_key_is_current(
                "device",
                pending["kotiKeyID"],
            )
        )
        self.assertIsNone(
            security.device_key_handoff_payload("device")
        )
        self.assertTrue(
            security.state["device_keys"]["device"].get(
                "handoff_verified_at"
            )
        )

        old_headers = _signed_headers(
            device_id="device",
            key_id=original["keyID"],
            secret=original["secret"],
            path="/telemetry",
            body=body,
            nonce="old-grace",
        )

        with app.test_request_context(
            "/telemetry",
            method="POST",
            data=body,
            headers=old_headers,
        ):
            self.assertIsNone(
                security.require_device_signature("device")
            )

    def test_staging_is_idempotent(self):
        security = self._security()
        security.issue_device_key("device")

        first = security.stage_device_key_handoffs(["device"])
        first_payload = security.device_key_handoff_payload("device")
        second = security.stage_device_key_handoffs(["device"])
        second_payload = security.device_key_handoff_payload("device")

        self.assertEqual(first["staged"], 1)
        self.assertEqual(second["already_staged"], 1)
        self.assertEqual(first_payload, second_payload)

    def test_revoke_and_direct_rotate_clear_staging_and_respect_grace(self):
        security = self._security()
        security.issue_device_key("device")
        security.stage_device_key_handoffs(["device"])
        pending = security.device_key_handoff_payload("device")

        security.revoke_device_key(
            "device",
            key_id=pending["kotiKeyID"],
        )
        self.assertIsNone(
            security.device_key_handoff_payload("device")
        )

        # Direct rotation creates a previous/grace key. While that key is
        # still usable, staging must refuse to create a third credential.
        security.issue_device_key("device", rotate=True)
        blocked = security.stage_device_key_handoffs(["device"])

        self.assertEqual(blocked["staged"], 0)
        self.assertEqual(blocked["skipped_previous_grace"], 1)
        self.assertIsNone(
            security.device_key_handoff_payload("device")
        )

        # Once the fixture's previous/grace slot is expired, staging becomes
        # safe again. A subsequent explicit rotation must clear that staged
        # credential rather than leaving an extra usable secret behind.
        record = security.state["device_keys"]["device"]
        record["previous"]["expires_at"] = 0

        staged = security.stage_device_key_handoffs(["device"])

        self.assertEqual(staged["staged"], 1)
        self.assertIsNotNone(
            security.device_key_handoff_payload("device")
        )

        security.issue_device_key("device", rotate=True)

        self.assertIsNone(
            security.device_key_handoff_payload("device")
        )

    def test_handoff_stage_route_fails_closed_to_dashboard_policy(self):
        self.assertEqual(
            request_policy(
                "POST",
                "/api/security/device-key/handoff-stage",
            ),
            "dashboard",
        )


if __name__ == "__main__":
    unittest.main()

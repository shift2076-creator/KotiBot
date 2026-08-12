import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from flask import Flask, g

from subsystems.security.kotibot_security import (
    KotiBotSecurity,
    SecurityConfig,
)


class SecurityAuditPrivacyTests(unittest.TestCase):
    def build_security(self, root: Path) -> KotiBotSecurity:
        return KotiBotSecurity(SecurityConfig(
            base_dir=root / "state",
            audit_path=root / "logs" / "security_audit.jsonl",
            allowed_origins=((
                "https",
                "kotibot.example",
                443,
            ),),
        ))

    def read_only_record(self, audit_file: Path) -> tuple[dict, str]:
        text = audit_file.read_text(encoding="utf-8")
        lines = [line for line in text.splitlines() if line]
        self.assertEqual(len(lines), 1)
        return json.loads(lines[0]), text

    def test_audit_redacts_secret_and_private_identifier_fields(self):
        app = Flask(__name__)

        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            security = self.build_security(root)
            audit_file = security.config.audit_file

            dashboard_email = "dashboard-person@example.invalid"
            claimed_device_id = "device-private-001"
            remote_ip = "192.0.2.44"
            username = "private-operator"
            mac_address = "02:00:00:00:00:44"
            client_id = "client-private-001"
            unique_identifier = "unique-private-001"
            wifi_ssid = "private-network-name"
            supplied_origin = "https://private-host.example"
            password = "synthetic-test-password"

            security.dashboard_session_email = lambda: dashboard_email

            with app.test_request_context(
                "/api/test",
                method="POST",
                base_url="https://kotibot.example",
                headers={
                    "X-Device-ID": claimed_device_id,
                },
                environ_base={
                    "REMOTE_ADDR": remote_ip,
                },
            ):
                self.assertTrue(security.audit(
                    "privacy_test",
                    status=403,
                    email=dashboard_email,
                    username=username,
                    ip_address=remote_ip,
                    mac_address=mac_address,
                    deviceID=claimed_device_id,
                    client_id=client_id,
                    unique_identifier=unique_identifier,
                    wifi_ssid=wifi_ssid,
                    supplied_origin=supplied_origin,
                    password=password,
                ))

            record, text = self.read_only_record(audit_file)

            self.assertEqual(record["event"], "privacy_test")
            self.assertEqual(record["status"], 403)
            self.assertEqual(record["method"], "POST")
            self.assertEqual(record["path"], "[unmatched]")
            self.assertEqual(record["actor"], "dashboard")

            for field_name in (
                "email",
                "username",
                "ip_address",
                "mac_address",
                "deviceID",
                "client_id",
                "unique_identifier",
                "wifi_ssid",
                "supplied_origin",
            ):
                self.assertEqual(record[field_name], "[private]")

            self.assertEqual(record["password"], "[redacted]")

            for raw_value in (
                dashboard_email,
                claimed_device_id,
                remote_ip,
                username,
                mac_address,
                client_id,
                unique_identifier,
                wifi_ssid,
                supplied_origin,
                password,
            ):
                self.assertNotIn(raw_value, text)

            self.assertNotIn("dashboard_email", record)
            self.assertNotIn("ip", record)

    def test_audit_uses_route_pattern_instead_of_dynamic_identifier(self):
        app = Flask(__name__)

        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            security = self.build_security(root)
            audit_file = security.config.audit_file
            device_id = "household-device-private-002"

            @app.post("/devices/<device_id>/rotate")
            def rotate_device(device_id):
                g.kotibot_device_id = device_id
                self.assertTrue(security.audit(
                    "device_rotate_test",
                    status=200,
                    deviceID=device_id,
                ))
                return "", 204

            response = app.test_client().post(
                f"/devices/{device_id}/rotate"
            )
            self.assertEqual(response.status_code, 204)

            record, text = self.read_only_record(audit_file)

            self.assertEqual(
                record["path"],
                "/devices/<device_id>/rotate",
            )
            self.assertEqual(record["actor"], "device")
            self.assertEqual(record["deviceID"], "[private]")
            self.assertNotIn(device_id, text)


if __name__ == "__main__":
    unittest.main()

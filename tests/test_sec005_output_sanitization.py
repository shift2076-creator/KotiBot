import ast
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from server_core.status import build_status_runtime
from subsystems.security.kotibot_security import KotiBotSecurity, SecurityConfig
from subsystems.security.security_routes import request_policy


ROOT = Path(__file__).resolve().parents[1]


def _client_has_role(client, role):
    roles = client.get("clientRole")

    if isinstance(roles, (list, tuple, set)):
        return role in roles

    return roles == role


def _status_context(clients):
    return {
        "clients": clients,
        "client_role_cam": "CAM",
        "client_role_dss": "DSS",
        "client_role_key": "KEY",
        "client_role_tapo": "TAPO",
        "client_role_unp": "UNP",
        "preview_viewer_ttl_seconds": 30,
        "stale_client_seconds": 30,
        "matter_stale_client_seconds": 30,
        "server_start_epoch": 900.0,
        "age_text": lambda value: "now",
        "clean_filename_part": lambda value: str(value or "").replace(":", "_"),
        "clean_zone_name": lambda value: str(value or "").strip(),
        "client_has_role": _client_has_role,
        "android_client_profile": lambda client: {
            "clientClass": "test",
            "capabilities": [],
        },
        "duration_text": lambda value: f"{int(value)}s",
        "now_epoch": lambda: 1000.0,
        "now_local": lambda: "synthetic-now",
        "voice_talk_active_for_target": lambda device_id: False,
        "system_armed": lambda: False,
        "system_arm_state": lambda: "day",
        "environment_snapshot": lambda: (lambda current_clients: {}),
        "tapo_lighting_state_snapshot": lambda: {},
        "matter_settings_snapshot": lambda: {},
        "dashboard_auth_status": lambda: {
            "ok": True,
            "dashboard_authenticated": True,
        },
    }


class Sec005OutputSanitizationTests(unittest.TestCase):
    def test_status_payload_omits_private_topology_and_raw_diagnostics(self):
        tapo = {
            "deviceID": "tapo:opaque-device",
            "clientName": "Synthetic Plug",
            "clientRole": ["TAPO"],
            "provisioned": True,
            "source": "tapo",
            "last_seen": 999.0,
            "zone_name": "Test",
            "ip": "192.0.2.10",
            "tapo_ip": "192.0.2.10",
            "tapo_mac": "02:00:00:00:00:10",
            "tapo_id": "vendor-unique-id",
            "tapo_kind": "outlet_extender",
            "tapo_is_outlet_extender": True,
            "tapo_parent_id": "vendor-parent-id",
            "tapo_parent_ip": "192.0.2.11",
            "tapo_parent_device_id": "tapo:opaque-parent",
            "tapo_recording_file": "/private/media/example.mp4",
            "fcm_token": "synthetic-private-fcm-token",
            "fcm_token_at": 999.0,
            "tapo_children": [{
                "id": "child-1",
                "position": 1,
                "index": 0,
                "cli_index": 0,
                "alias": "Outlet 1",
                "kind": "plug",
                "is_on": True,
                "tapo_room_power": False,
                "tapo_hide_dashboard": False,
                "mac": "02:00:00:00:00:12",
                "owner_hash": "private-owner-hash",
                "device_id_hash": "private-device-hash",
                "raw": {
                    "ip": "192.0.2.12",
                    "mac": "02:00:00:00:00:12",
                    "owner_hash": "private-owner-hash",
                },
            }],
        }
        matter = {
            "deviceID": "matter:opaque-node:endpoint",
            "clientName": "Synthetic Matter",
            "clientRole": "SENSOR",
            "provisioned": True,
            "source": "matter",
            "last_seen": 999.0,
            "matter_last_sync_at": 999.0,
            "matter_node_id": "opaque-node",
            "matter_endpoint": "1",
            "matter_serial_number": "physical-serial-number",
            "matter_reads": {"private": "diagnostic-value"},
            "matter_battery_attr_reads": {"private": "diagnostic-value"},
            "matter_bridged_basic_reads": {
                "serial_number": "physical-serial-number",
            },
        }

        runtime = build_status_runtime(
            _status_context({
                tapo["deviceID"]: tapo,
                matter["deviceID"]: matter,
            })
        )
        payload = runtime["current_status_payload"]()

        for field in (
            "server_ip",
            "server_ip_address",
            "local_ip",
        ):
            self.assertNotIn(field, payload)
            self.assertNotIn(field, payload["server"])

        by_id = {
            client["deviceID"]: client
            for client in payload["clients"]
        }
        tapo_output = by_id[tapo["deviceID"]]
        matter_output = by_id[matter["deviceID"]]

        for field in (
            "ip",
            "tapo_ip",
            "tapo_mac",
            "tapo_id",
            "tapo_parent_id",
            "tapo_parent_ip",
            "tapo_recording_file",
        ):
            self.assertNotIn(field, tapo_output)

        self.assertEqual(
            tapo_output["tapo_parent_device_id"],
            "tapo:opaque-parent",
        )
        self.assertEqual(tapo_output["deviceID"], "tapo:opaque-device")

        children = tapo_output["tapo_children"]
        self.assertEqual(children, tapo_output["children"])
        self.assertEqual(len(children), 1)
        self.assertEqual(children[0]["id"], "child-1")
        self.assertEqual(children[0]["alias"], "Outlet 1")
        self.assertTrue(children[0]["is_on"])

        for field in (
            "mac",
            "owner_hash",
            "device_id_hash",
            "raw",
        ):
            self.assertNotIn(field, children[0])

        for field in (
            "matter_serial_number",
            "matter_reads",
            "matter_battery_attr_reads",
            "matter_bridged_basic_reads",
        ):
            self.assertNotIn(field, matter_output)

        encoded = json.dumps(payload, sort_keys=True)
        for private_value in (
            "192.0.2.10",
            "192.0.2.11",
            "192.0.2.12",
            "02:00:00:00:00:10",
            "02:00:00:00:00:12",
            "vendor-unique-id",
            "vendor-parent-id",
            "physical-serial-number",
            "private-owner-hash",
            "/private/media/example.mp4",
            "synthetic-private-fcm-token",
        ):
            self.assertNotIn(private_value, encoded)

    def test_tapo_raw_discovery_debug_route_is_removed(self):
        route_path = (
            ROOT
            / "subsystems"
            / "client-tapo"
            / "tapo_routes.py"
        )
        tree = ast.parse(
            route_path.read_text(encoding="utf-8"),
            filename=str(route_path),
        )

        routes = set()

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue

            for decorator in node.decorator_list:
                if not isinstance(decorator, ast.Call) or not decorator.args:
                    continue

                value = decorator.args[0]

                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    routes.add(value.value)

        self.assertNotIn("/api/tapo/debug-discovery", routes)

    def test_tapo_discovery_errors_do_not_embed_raw_discovery_output(self):
        control_path = (
            ROOT
            / "subsystems"
            / "client-tapo"
            / "tapo_control.py"
        )
        source = control_path.read_text(encoding="utf-8")

        self.assertNotIn("debug_tapo_discovery_text", source)
        self.assertNotIn("output.strip()[:1000]", source)
        self.assertNotIn("discovery_text[:500]", source)
        self.assertNotIn(
            "Tapo discovery returned no parseable devices:",
            source,
        )

    def test_dashboard_user_listing_does_not_expose_authentication_material(self):
        password = "Synthetic-SEC005-Pass9!"

        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            security = KotiBotSecurity(SecurityConfig(
                base_dir=root / "protected",
                audit_path=root / "audit" / "security_audit.jsonl",
            ))
            security.set_dashboard_login(
                "operator@example.invalid",
                password,
            )

            listing = security.list_dashboard_users()
            encoded = json.dumps(listing, sort_keys=True)

            self.assertNotIn(password, encoded)

            forbidden_keys = {
                "password",
                "password_hash",
                "dashboard_password_hash",
                "session_secret",
                "secret",
                "token",
                "token_hash",
            }

            for record in listing:
                self.assertTrue(forbidden_keys.isdisjoint(record.keys()))

    def test_dashboard_debug_rows_do_not_request_removed_network_identity(self):
        render_path = ROOT / "static" / "js" / "dashboard-render.js"
        source = render_path.read_text(encoding="utf-8")

        tapo_block = source.split(
            "function dashboardTapoDebugBaseRows(c) {",
            1,
        )[1].split(
            "\nfunction ",
            1,
        )[0]
        android_block = source.split(
            "function dashboardDebugRowsForAndroid(c, el) {",
            1,
        )[1].split(
            "\nfunction ",
            1,
        )[0]

        self.assertNotIn('["IP"', tapo_block)
        self.assertNotIn('["MAC"', tapo_block)
        self.assertNotIn("c?.tapo_id", tapo_block)
        self.assertNotIn('["IP"', android_block)

    def test_credential_delivery_boundaries_remain_explicitly_protected(self):
        # TURN/ICE material is intentionally delivered only to the two
        # authorized WebRTC peers. That is credential issuance, not an
        # ordinary status/log echo, and both paths remain behind a security
        # boundary.
        self.assertEqual(
            request_policy("POST", "/api/voice/session"),
            "dashboard",
        )
        self.assertEqual(
            request_policy("POST", "/api/camera-talk/session"),
            "dashboard",
        )
        self.assertEqual(
            request_policy("POST", "/api/voice/client/pending"),
            "device",
        )
        self.assertEqual(
            request_policy("POST", "/api/camera-talk/client/pending"),
            "device",
        )

        # Device enrollment is the other deliberate credential-issuance
        # boundary. It must stay isolated from ordinary dashboard/status APIs.
        self.assertEqual(
            request_policy("POST", "/api/handshake"),
            "enrollment",
        )
        self.assertEqual(
            request_policy("GET", "/api/status"),
            "dashboard",
        )


if __name__ == "__main__":
    unittest.main()

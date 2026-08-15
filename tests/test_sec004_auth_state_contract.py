import importlib.util
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import RLock
import unittest
from unittest.mock import Mock, patch

from server_core.state import (
    ANDROID_SHARED_SERVER_STATE_KEYS,
    UNPROVISIONED_SERVER_STATE_KEYS,
    build_state_runtime,
)
try:
    from flask import Flask, g
    from subsystems.notifications.notification_routes import (
        register_notification_routes,
    )
except ModuleNotFoundError as exc:
    if exc.name != "flask":
        raise

    Flask = None
    g = None
    register_notification_routes = None


SOURCE_ROOT = Path(__file__).resolve().parents[1]


def _load_key_telemetry_module():
    path = (
        SOURCE_ROOT
        / "subsystems"
        / "client-android-key"
        / "client_android_key_telemetry.py"
    )
    spec = importlib.util.spec_from_file_location(
        "sec0043_android_key_telemetry",
        path,
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Sec004AuthStateContractTests(unittest.TestCase):
    @staticmethod
    def _write_json(path: Path, data: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")

    def test_server_state_allowlists_exclude_notification_credentials(self):
        for keys in (
            ANDROID_SHARED_SERVER_STATE_KEYS,
            UNPROVISIONED_SERVER_STATE_KEYS,
        ):
            self.assertNotIn("fcm_token", keys)
            self.assertNotIn("fcm_token_at", keys)

    def test_state_load_discards_legacy_token_and_hydrates_protected_record(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            files = {
                name: root / f"{name}.json"
                for name in (
                    "server",
                    "security_actions",
                    "tapo",
                    "matter",
                    "android_home",
                    "automation",
                )
            }
            self._write_json(
                files["server"],
                {
                    "clients": {
                        "android_key": [
                            {
                                "deviceID": "key-1",
                                "clientName": "Key",
                                "clientRole": "KEY",
                                "provisioned": True,
                                "fcm_token": "legacy-token",
                                "fcm_token_at": 10,
                            }
                        ]
                    },
                    "system": {},
                },
            )

            for name in files:
                if name != "server":
                    self._write_json(files[name], {})

            clients = {}
            routes = []
            writes = {}

            def record_write(path, data):
                writes[Path(path)] = data

            runtime = build_state_runtime({
                "clients": clients,
                "routes": routes,
                "state_file": files["server"],
                "security_actions_file": files["security_actions"],
                "tapo_device_state_file": files["tapo"],
                "matter_device_state_file": files["matter"],
                "android_home_state_file": files["android_home"],
                "automation_state_file": files["automation"],
                "automation_type_tapo_recharge": "recharge",
                "automation_type_device_routes": "routes",
                "client_role_cam": "CAM",
                "client_role_dss": "DSS",
                "client_role_key": "KEY",
                "client_role_tapo": "TAPO",
                "open_angle_threshold": 15,
                "close_angle_threshold": 5,
                "client_has_role": lambda client, role: role in (
                    client.get("clientRole")
                    if isinstance(client.get("clientRole"), list)
                    else [client.get("clientRole")]
                ),
                "clean_arm_state": lambda value: str(value or "day"),
                "clean_zone_name": lambda value: str(value or ""),
                "init_client": lambda device_id: {
                    "deviceID": device_id,
                    "provisioned": False,
                    "pending_command": {},
                },
                "set_routes": lambda items: routes.__setitem__(slice(None), items),
                "set_system_arm_state": lambda _armed, _state: None,
                "broadcast_state": lambda: None,
                "device_notification_credential": lambda device_id: (
                    {
                        "token": "protected-token",
                        "updated_at": 50,
                    }
                    if device_id == "key-1"
                    else {}
                ),
                "system_armed": lambda: False,
                "system_arm_state": lambda: "day",
            })

            with patch(
                "server_core.state.write_json_atomic",
                side_effect=record_write,
            ):
                loaded = runtime["load_state"]()

            self.assertTrue(loaded)
            self.assertEqual(clients["key-1"]["fcm_token"], "protected-token")
            self.assertEqual(clients["key-1"]["fcm_token_at"], 50.0)
            persisted = writes[files["server"]]
            encoded = json.dumps(persisted)
            self.assertNotIn("fcm_token", encoded)
            self.assertNotIn("legacy-token", encoded)

    @unittest.skipIf(Flask is None, "Flask is not installed")
    def test_fcm_registration_persists_protected_record_without_save_state(self):
        app = Flask(__name__)
        client_state = {"deviceID": "key-1"}
        setter = Mock(return_value={
            "token": "registered-token",
            "updated_at": 125.0,
        })

        @app.before_request
        def signed_device():
            g.kotibot_device_id = "key-1"

        register_notification_routes(app, {
            "state_lock": RLock(),
            "clients": {"key-1": client_state},
            "push_queue": Mock(),
            "now_epoch": lambda: 125.0,
            "set_device_notification_token": setter,
        })

        response = app.test_client().post(
            "/api/notifications/fcm-token",
            json={"token": "registered-token"},
        )

        self.assertEqual(response.status_code, 200)
        setter.assert_called_once_with(
            "key-1",
            "registered-token",
            125.0,
        )
        self.assertEqual(client_state["fcm_token"], "registered-token")
        self.assertEqual(client_state["fcm_token_at"], 125.0)

    def test_key_token_only_telemetry_does_not_dirty_ordinary_state(self):
        module = _load_key_telemetry_module()
        setter = Mock(return_value={
            "token": "telemetry-token",
            "updated_at": 200.0,
        })
        runtime = module.register_android_key_telemetry({
            "safe_int": lambda value: int(value),
            "now_epoch": lambda: 200.0,
            "set_device_notification_token": setter,
        })
        client = {
            "deviceID": "key-1",
            "fcm_token": "old-token",
            "heartbeat_interval_ms": 30000,
        }

        changed = runtime["handle_key_telemetry"](
            client,
            {
                "fcmToken": "telemetry-token",
                "heartbeatIntervalMs": 30000,
            },
        )

        self.assertFalse(changed)
        setter.assert_called_once_with(
            "key-1",
            "telemetry-token",
            200.0,
        )
        self.assertEqual(client["fcm_token"], "telemetry-token")

    def test_server_uses_only_protected_tokens_before_starting_loops(self):
        source = (SOURCE_ROOT / "kotibot_server.py").read_text(
            encoding="utf-8"
        )
        load = source.rindex("\nload_state()\n")
        loops = source.index(
            "_SUBSYSTEM_RUNTIME['start_registered_subsystem_loops']()"
        )

        self.assertLess(load, loops)
        self.assertNotIn(
            "DEVICE_NOTIFICATION_CREDENTIALS.migrate_legacy_server_state(",
            source,
        )
        self.assertIn(
            "DEVICE_NOTIFICATION_CREDENTIALS.remove(deviceID)",
            source,
        )


if __name__ == "__main__":
    unittest.main()

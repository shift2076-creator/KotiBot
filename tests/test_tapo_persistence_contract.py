import copy
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from server_core.paths import build_runtime_paths
from server_core.state import tapo_persisted_device_state


SOURCE_ROOT = Path(__file__).resolve().parents[1]


class TapoPersistenceContractTests(unittest.TestCase):
    def test_tapo_config_is_resolved_outside_source_tree(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_root = root / "source"
            data_root = root / "app-data"
            source_root.mkdir()

            with patch.dict(
                os.environ,
                {"KOTIBOT_DATA_DIR": str(data_root)},
                clear=True,
            ):
                paths = build_runtime_paths(source_root)

            self.assertEqual(
                paths.tapo_config_file,
                data_root / "state" / "tapo" / "tapo_config.json",
            )
            self.assertNotIn(
                source_root.resolve(),
                paths.tapo_config_file.resolve().parents,
            )

    def test_server_uses_typed_external_tapo_config(self):
        source = (SOURCE_ROOT / "kotibot_server.py").read_text(
            encoding="utf-8"
        )

        self.assertIn(
            "TAPO_CONFIG_FILE = RUNTIME_PATHS.tapo_config_file",
            source,
        )
        self.assertIn(
            "data = read_json_object(TAPO_CONFIG_FILE)",
            source,
        )
        self.assertNotIn(
            "CLIENT_TAPO_DIR / 'tapo_config.json'",
            source,
        )
        self.assertNotIn(
            "TAPO_CONFIG_FILE.read_text",
            source,
        )

    def test_tapo_snapshot_closes_device_and_child_pass_through(self):
        client = {
            "tapo_id": "device-id",
            "tapo_alias": "Kitchen",
            "tapo_is_on": True,
            "tapo_desired_brightness": 55,
            "tapo_pending_power_commands": {
                "on": {"updatedAt": 1}
            },
            "tapo_rtsp_url": "rtsp://credential-bearing-value",
            "tapo_last_trigger_event": "legacy-event",
            "tapo_child_id": "retired-flat-child",
            "vendor_root_extension": "discard-me",
            "tapo_children": [
                {
                    "id": "1",
                    "position": 1,
                    "alias": "Outlet 1",
                    "zone_name": "Kitchen",
                    "tapo_room_power": True,
                    "tapo_hide_dashboard": False,
                    "supports_power": True,
                    "is_on": False,
                    "raw": {"credential": "discard-me"},
                    "nickname": "compatibility-input",
                    "vendor_child_extension": "discard-me",
                },
                "invalid-child",
            ],
        }
        original = copy.deepcopy(client)

        state = tapo_persisted_device_state(client)

        self.assertEqual(client, original)
        self.assertEqual(state["tapo_id"], "device-id")
        self.assertEqual(state["tapo_alias"], "Kitchen")
        self.assertTrue(state["tapo_is_on"])
        self.assertEqual(state["tapo_desired_brightness"], 55)
        self.assertNotIn("tapo_pending_power_commands", state)
        self.assertNotIn("tapo_rtsp_url", state)
        self.assertNotIn("tapo_last_trigger_event", state)
        self.assertNotIn("tapo_child_id", state)
        self.assertNotIn("vendor_root_extension", state)

        self.assertEqual(len(state["tapo_children"]), 1)
        child = state["tapo_children"][0]
        self.assertEqual(child["id"], "1")
        self.assertEqual(child["position"], 1)
        self.assertEqual(child["alias"], "Outlet 1")
        self.assertEqual(child["zone_name"], "Kitchen")
        self.assertTrue(child["tapo_room_power"])
        self.assertFalse(child["tapo_hide_dashboard"])
        self.assertTrue(child["supports_power"])
        self.assertFalse(child["is_on"])
        self.assertNotIn("raw", child)
        self.assertNotIn("nickname", child)
        self.assertNotIn("vendor_child_extension", child)

    def test_malformed_child_container_is_not_persisted(self):
        state = tapo_persisted_device_state({
            "tapo_id": "device-id",
            "tapo_children": {"not": "a-list"},
        })

        self.assertEqual(state, {"tapo_id": "device-id"})


if __name__ == "__main__":
    unittest.main()

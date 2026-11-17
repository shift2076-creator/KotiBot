"""New Device Found cards need the model and type of unprovisioned Tapo devices."""
import unittest

from server_core.status import build_status_runtime
from tests.security.privacy.test_output_sanitization import _status_context


def snapshot(client):
    runtime = build_status_runtime(_status_context({client["deviceID"]: client}))
    return runtime["snapshot_client"](client)


def unprovisioned(**fields):
    return {
        "deviceID": "tapo:opaque", "clientName": "Hallway", "clientRole": "UNP",
        "provisioned": False, "last_seen": 1000.0, **fields,
    }


class FoundTapoCardMetadataTests(unittest.TestCase):
    def test_unprovisioned_tapo_device_exposes_model_and_type_for_icon_and_subtitle(self):
        output = snapshot(unprovisioned(
            source="tapo", tapo_model="L530", tapo_kind="bulb",
            tapo_device_type="SMART.TAPOBULB", tapo_ip="192.0.2.10", tapo_mac="02:00:00:00:00:10"))

        self.assertEqual(output["tapo_model"], "L530")
        self.assertEqual(output["tapo_kind"], "bulb")
        self.assertEqual(output["tapo_device_type"], "SMART.TAPOBULB")
        # The addition stays narrow: no network identifiers for a device not yet set up.
        for private in ("tapo_ip", "tapo_mac", "tapo_id"):
            self.assertNotIn(private, output)

    def test_other_unprovisioned_clients_gain_no_tapo_fields(self):
        output = snapshot(unprovisioned(source="android", deviceID="android:one"))

        for key in ("tapo_model", "tapo_kind", "tapo_device_type"):
            self.assertNotIn(key, output)


if __name__ == "__main__":
    unittest.main()

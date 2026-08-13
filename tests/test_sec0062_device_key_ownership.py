import unittest
from pathlib import Path

from tools.sec0062_inventory_device_key_ownership import (
    prove_server_reenrollment_fixture,
    render_summary,
    summarize_device_key_inventory,
    verify_server_handoff_contract,
)


SOURCE_ROOT = Path(__file__).resolve().parents[1]


class Sec0062DeviceKeyOwnershipTests(unittest.TestCase):
    def test_inventory_classifies_groups_without_identifiers(self):
        now = 1_000
        security_state = {
            "device_keys": {
                "home-a": {
                    "current": {
                        "key_id": "key-a",
                        "secret": "secret-a",
                        "status": "active",
                    },
                    "handoff_verified_at": 900,
                },
                "key-b": {
                    "current": {
                        "key_id": "key-b",
                        "secret": "secret-b",
                        "status": "active",
                    },
                    "pending": {
                        "key_id": "new-b",
                        "secret": "new-secret-b",
                        "status": "staged",
                    },
                },
                "orphan-c": {
                    "current": {
                        "key_id": "key-c",
                        "secret": "secret-c",
                        "status": "active",
                    },
                },
                "tapo-d": {
                    "current": {
                        "key_id": "key-d",
                        "secret": "secret-d",
                        "status": "active",
                    },
                },
                "matter-e": {
                    "current": {
                        "key_id": "key-e",
                        "secret": "secret-e",
                        "status": "active",
                    },
                },
            },
            "device_enrollments": {
                "home-no-key": {
                    "token_hash": "token-hash",
                    "expires_at": 900,
                },
            },
        }
        server_state = {
            "clients": {
                "android_home": [
                    {"deviceID": "home-a", "provisioned": True},
                    {"deviceID": "home-no-key", "provisioned": True},
                ],
                "android_key": [
                    {"deviceID": "key-b", "provisioned": True},
                ],
                "tapo": [
                    {"deviceID": "tapo-d", "provisioned": True},
                ],
                "matter": [
                    {"deviceID": "matter-e", "provisioned": True},
                ],
            },
        }

        summary = summarize_device_key_inventory(
            security_state,
            server_state,
            now=now,
        )

        self.assertEqual(summary["protected_key_records"], 5)
        self.assertEqual(summary["group_android_home"], 1)
        self.assertEqual(summary["group_android_key"], 1)
        self.assertEqual(summary["group_tapo"], 1)
        self.assertEqual(summary["group_matter"], 1)
        self.assertEqual(summary["group_orphaned"], 1)
        self.assertEqual(summary["active_group_tapo"], 1)
        self.assertEqual(summary["active_group_matter"], 1)
        self.assertEqual(summary["pending_staged"], 1)
        self.assertEqual(summary["first_party_handoff_verified"], 1)
        self.assertEqual(summary["first_party_handoff_unverified"], 1)
        self.assertEqual(
            summary["first_party_clients_without_key_record"],
            1,
        )
        self.assertEqual(
            summary["first_party_without_key_android_home"],
            1,
        )

        rendered = "\n".join(render_summary(summary))

        for private_value in (
            "home-a",
            "key-b",
            "orphan-c",
            "tapo-d",
            "matter-e",
            "secret-a",
            "new-secret-b",
            "token-hash",
        ):
            self.assertNotIn(private_value, rendered)

    def test_server_reenrollment_fixture_still_passes(self):
        self.assertTrue(prove_server_reenrollment_fixture())

    def test_server_staged_handoff_source_contract(self):
        self.assertTrue(verify_server_handoff_contract(SOURCE_ROOT))


if __name__ == "__main__":
    unittest.main()

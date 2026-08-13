import unittest
from pathlib import Path

from tools.sec0062_inventory_device_key_ownership import (
    prove_server_reenrollment_fixture,
    render_summary,
    summarize_device_key_inventory,
    verify_server_handshake_contract,
)


SOURCE_ROOT = Path(__file__).resolve().parents[1]


class Sec0062DeviceKeyOwnershipTests(unittest.TestCase):
    def test_inventory_classifies_key_ownership_without_identifiers(self):
        now = 1_000
        security_state = {
            "device_keys": {
                "home-a": {
                    "current": {
                        "key_id": "key-a",
                        "secret": "secret-a",
                        "status": "active",
                    },
                },
                "key-b": {
                    "current": {
                        "key_id": "key-b",
                        "secret": "secret-b",
                        "status": "active",
                    },
                    "previous": {
                        "key_id": "old-b",
                        "secret": "old-secret-b",
                        "status": "active",
                        "expires_at": 999,
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
                "waiting-e": {
                    "current": {
                        "key_id": "key-e",
                        "secret": "secret-e",
                        "status": "revoked",
                    },
                },
            },
            "device_enrollments": {
                "waiting-e": {
                    "token_hash": "token-hash-e",
                    "expires_at": 1_100,
                },
                "orphan-enrollment": {
                    "token_hash": "token-hash-orphan",
                    "expires_at": 900,
                },
            },
        }
        server_state = {
            "clients": {
                "android_home": [
                    {
                        "deviceID": "home-a",
                        "provisioned": True,
                    },
                    {
                        "deviceID": "home-no-key",
                        "provisioned": True,
                    },
                ],
                "android_key": [
                    {
                        "deviceID": "key-b",
                        "provisioned": True,
                    },
                ],
                "tapo": [
                    {
                        "deviceID": "tapo-d",
                        "provisioned": True,
                    },
                ],
                "unprovisioned": [
                    {
                        "deviceID": "waiting-e",
                        "provisioned": False,
                    },
                ],
            },
        }

        summary = summarize_device_key_inventory(
            security_state,
            server_state,
            now=now,
        )

        self.assertEqual(summary["protected_key_records"], 5)
        self.assertEqual(summary["owner_first-party-provisioned"], 2)
        self.assertEqual(summary["owner_orphaned"], 1)
        self.assertEqual(summary["owner_external-unexpected"], 1)
        self.assertEqual(summary["owner_unprovisioned"], 1)
        self.assertEqual(summary["live_rotation_candidates"], 2)
        self.assertEqual(summary["active_keys_requiring_review"], 1)
        self.assertEqual(
            summary["first_party_clients_without_key_record"],
            1,
        )
        self.assertEqual(summary["stale_previous_slots"], 1)
        self.assertEqual(summary["stale_current_slots"], 1)
        self.assertEqual(summary["enrollment_records"], 2)
        self.assertEqual(summary["enrollment_pending"], 1)
        self.assertEqual(summary["enrollment_expired"], 1)

        rendered = "\n".join(render_summary(summary))

        for private_value in (
            "home-a",
            "key-b",
            "orphan-c",
            "tapo-d",
            "waiting-e",
            "secret-a",
            "old-secret-b",
            "token-hash-e",
        ):
            self.assertNotIn(private_value, rendered)

    def test_server_reenrollment_fixture_issues_a_new_active_key(self):
        self.assertTrue(prove_server_reenrollment_fixture())

    def test_provisioned_handshake_rotates_after_enrollment_claim(self):
        self.assertTrue(
            verify_server_handshake_contract(SOURCE_ROOT)
        )

    def test_inventory_does_not_treat_expired_previous_as_active(self):
        summary = summarize_device_key_inventory(
            {
                "device_keys": {
                    "device": {
                        "current": {
                            "key_id": "current",
                            "secret": "current-secret",
                            "status": "active",
                        },
                        "previous": {
                            "key_id": "previous",
                            "secret": "previous-secret",
                            "status": "active",
                            "expires_at": 10,
                        },
                    },
                },
            },
            {
                "clients": {
                    "android_home": [
                        {
                            "deviceID": "device",
                            "provisioned": True,
                        },
                    ],
                },
            },
            now=11,
        )

        self.assertEqual(summary["previous_retired"], 1)
        self.assertEqual(summary["stale_previous_slots"], 1)
        self.assertNotIn("previous_grace-active", summary)


if __name__ == "__main__":
    unittest.main()

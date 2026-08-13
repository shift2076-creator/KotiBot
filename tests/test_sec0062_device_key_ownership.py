import unittest
from pathlib import Path

from tools.sec0062_inventory_device_key_ownership import (
    prove_server_reenrollment_fixture,
    render_summary,
    summarize_device_key_inventory,
    verify_server_handoff_contract,
    verify_server_handshake_contract,
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

        self.assertIn("KotiBot-Monitor=1", rendered)
        self.assertIn("KotiBot-Control=1", rendered)
        self.assertIn("KotiBot-without-key: KotiBot-Monitor=1 KotiBot-Control=0", rendered)

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


    def test_baseline_owner_enrollment_and_stale_classification(self):
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

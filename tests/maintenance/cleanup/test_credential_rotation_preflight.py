import unittest

from tools.sec006_preflight_credential_rotation import (
    _count_named_keys,
    summarize_security_overlap,
)


class Sec006CredentialRotationPreflightTests(unittest.TestCase):
    def test_security_overlap_reports_counts_without_identifiers(self):
        current = {
            "session_secret": "current-session-secret",
            "dashboard_users": {
                "one@example.test": {"password_hash": "hash-one"},
                "two@example.test": {"password_hash": "hash-two-new"},
            },
            "dashboard_sessions": {
                "session-a": {"email": "one@example.test"},
                "session-new": {"email": "two@example.test"},
            },
            "device_keys": {
                "device-a": {"secret": "device-secret-a"},
                "device-new": {"secret": "device-secret-new"},
            },
            "device_enrollments": {},
        }
        legacy = {
            "session_secret": "current-session-secret",
            "dashboard_users": {
                "one@example.test": {"password_hash": "hash-one"},
                "two@example.test": {"password_hash": "hash-two-old"},
            },
            "dashboard_sessions": {
                "session-a": {"email": "one@example.test"},
                "session-old": {"email": "two@example.test"},
            },
            "device_keys": {
                "device-a": {"secret": "device-secret-a"},
                "device-old": {"secret": "device-secret-old"},
            },
            "device_enrollments": {
                "device-pending": {"secret": "enrollment-secret"},
            },
            "nested": {"fcm_token": "legacy-fcm-token"},
        }

        summary = summarize_security_overlap(current, legacy)

        self.assertEqual(summary["session_secret"], "same")
        self.assertEqual(
            summary["mappings"]["dashboard_users"],
            {"current": 2, "legacy": 2, "shared": 2, "matching": 1},
        )
        self.assertEqual(
            summary["mappings"]["dashboard_sessions"],
            {"current": 2, "legacy": 2, "shared": 1, "matching": 1},
        )
        self.assertEqual(
            summary["mappings"]["device_keys"],
            {"current": 2, "legacy": 2, "shared": 1, "matching": 1},
        )
        self.assertEqual(
            summary["mappings"]["device_enrollments"],
            {"current": 0, "legacy": 1, "shared": 0, "matching": 0},
        )
        self.assertEqual(summary["legacy_fcm_token_fields"], 1)

        rendered = repr(summary)
        for private_value in (
            "one@example.test",
            "two@example.test",
            "session-a",
            "device-a",
            "legacy-fcm-token",
            "current-session-secret",
        ):
            self.assertNotIn(private_value, rendered)

    def test_session_secret_difference_is_value_free(self):
        summary = summarize_security_overlap(
            {"session_secret": "new-secret"},
            {"session_secret": "old-secret"},
        )

        self.assertEqual(summary["session_secret"], "different")
        self.assertNotIn("new-secret", repr(summary))
        self.assertNotIn("old-secret", repr(summary))

    def test_named_key_counter_is_recursive_and_value_free(self):
        document = {
            "password_hash": "secret-a",
            "children": [
                {"secret": "secret-b"},
                {"ordinary": {"token_hash": "secret-c"}},
            ],
        }

        count = _count_named_keys(
            document,
            frozenset({"password_hash", "secret", "token_hash"}),
        )

        self.assertEqual(count, 3)


if __name__ == "__main__":
    unittest.main()

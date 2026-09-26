import io
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from tools.sec0043_verify_auth_credential_cutover import (
    main,
    verify_cutover,
)


class Sec0043CutoverVerifierTests(unittest.TestCase):
    @staticmethod
    def _write_private_json(path: Path, data: dict) -> None:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")

        if os.name != "nt":
            path.parent.chmod(0o700)
            path.chmod(0o600)

    def _fixture(self, root: Path):
        security_state = root / "protected" / "security" / "security_state.json"
        notification_state = (
            root
            / "protected"
            / "devices"
            / "notification_credentials.json"
        )
        server_state = root / "state" / "server_state.json"
        self._write_private_json(
            security_state,
            {
                "session_secret": "private-session-secret",
                "dashboard_users": {"private@example.invalid": {}},
                "dashboard_sessions": {"private-session-id": {}},
                "device_keys": {"private-device-id": {}},
                "device_enrollments": {},
            },
        )
        self._write_private_json(
            notification_state,
            {
                "version": 1,
                "tokens": {
                    "private-device-id": {
                        "token": "private-notification-token",
                        "updated_at": 100,
                    }
                },
            },
        )
        self._write_private_json(server_state, {"clients": {}})
        return security_state, notification_state, server_state

    def test_verifier_reports_counts_without_values_or_identifiers(self):
        with TemporaryDirectory() as temp_dir:
            files = self._fixture(Path(temp_dir))
            output = io.StringIO()

            with patch("sys.stdout", output):
                result = main([
                    "--security-state",
                    str(files[0]),
                    "--notification-credentials",
                    str(files[1]),
                    "--server-state",
                    str(files[2]),
                    "--minimum-tokens",
                    "1",
                ])

            text = output.getvalue()
            self.assertEqual(result, 0)
            self.assertIn("cutover verification passed", text)
            self.assertIn("tokens=1", text)

            for private_value in (
                "private-session-secret",
                "private@example.invalid",
                "private-session-id",
                "private-device-id",
                "private-notification-token",
            ):
                self.assertNotIn(private_value, text)

    def test_verifier_rejects_token_in_ordinary_server_state(self):
        with TemporaryDirectory() as temp_dir:
            files = self._fixture(Path(temp_dir))
            self._write_private_json(
                files[2],
                {
                    "clients": {
                        "android_key": [
                            {"fcm_token": "must-not-remain"}
                        ]
                    }
                },
            )

            with self.assertRaisesRegex(
                RuntimeError,
                "ordinary server state still contains",
            ):
                verify_cutover(
                    security_state_file=files[0],
                    notification_credentials_file=files[1],
                    server_state_file=files[2],
                )


if __name__ == "__main__":
    unittest.main()

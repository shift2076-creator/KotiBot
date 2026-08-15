import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

try:
    from subsystems.notifications.kotibot_push import KotiBotPushQueue
except ModuleNotFoundError as exc:
    if not str(exc.name or "").startswith("google"):
        raise

    KotiBotPushQueue = None


SOURCE_ROOT = Path(__file__).resolve().parents[1]


class Sec004CredentialRuntimeTests(unittest.TestCase):
    def test_tapo_credentials_use_only_the_shared_protected_loader(self):
        source = (
            SOURCE_ROOT
            / "subsystems"
            / "client-tapo"
            / "tapo_control.py"
        ).read_text(encoding="utf-8")

        credential_names = (
            "tapo-username",
            "tapo-password",
            "tapo-camera-username",
            "tapo-camera-password",
        )

        for credential_name in credential_names:
            self.assertIn(f'"{credential_name}"', source)

        self.assertNotIn("legacy_environment=", source)

        self.assertIn("user = TAPO_CAMERA_USERNAME", source)
        self.assertIn("password = TAPO_CAMERA_PASSWORD", source)

    def test_server_selects_only_the_protected_firebase_credential(self):
        source = (SOURCE_ROOT / "kotibot_server.py").read_text(
            encoding="utf-8"
        )

        self.assertIn(
            "FIREBASE_SERVICE_ACCOUNT_FILE = resolve_credential_file(\n"
            "    'firebase-service-account.json',\n"
            ")",
            source,
        )
        self.assertNotIn("legacy_file=", source)
        self.assertIn(
            "service_account_file=FIREBASE_SERVICE_ACCOUNT_FILE,",
            source,
        )

    def test_notification_loader_does_not_delegate_path_opening_to_google(self):
        source = (
            SOURCE_ROOT
            / "subsystems"
            / "notifications"
            / "kotibot_push.py"
        ).read_text(encoding="utf-8")

        self.assertIn("read_json_credential_file(", source)
        self.assertIn("from_service_account_info(", source)
        self.assertNotIn("from_service_account_file(", source)

    @unittest.skipIf(
        KotiBotPushQueue is None,
        "Google Auth is not installed in this development environment",
    )
    def test_notification_queue_passes_private_info_to_google_auth(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            credential_file = root / "firebase-service-account.json"
            credential_info = {
                "type": "service_account",
                "project_id": "test-project",
                "private_key_id": "test-key",
                "private_key": "test-private-key",
                "client_email": "test@example.invalid",
                "client_id": "123",
                "auth_uri": "https://example.invalid/auth",
                "token_uri": "https://example.invalid/token",
            }
            credential_file.write_text(
                json.dumps(credential_info),
                encoding="utf-8",
            )

            if os.name != "nt":
                credential_file.chmod(0o600)

            queue = KotiBotPushQueue(
                root / "queue",
                queue_file=root / "queue" / "notifications.jsonl",
                service_account_file=credential_file,
            )
            credentials = Mock(valid=True, project_id="test-project")

            with patch(
                "subsystems.notifications.kotibot_push."
                "service_account.Credentials.from_service_account_info",
                return_value=credentials,
            ) as loader:
                result = queue._fcm_credentials()

            self.assertIs(result, credentials)
            loader.assert_called_once()
            self.assertEqual(loader.call_args.args[0], credential_info)
            self.assertNotIn(str(credential_file), loader.call_args.args)

    @unittest.skipIf(
        os.name == "nt" or KotiBotPushQueue is None,
        "Symbolic-link test requires POSIX and Google Auth",
    )
    def test_notification_credential_symbolic_link_fails_closed(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            target = root / "target.json"
            target.write_text("{}", encoding="utf-8")
            target.chmod(0o600)
            credential_file = root / "firebase-service-account.json"
            credential_file.symlink_to(target)
            queue = KotiBotPushQueue(
                root / "queue",
                queue_file=root / "queue" / "notifications.jsonl",
                service_account_file=credential_file,
            )

            with self.assertRaisesRegex(RuntimeError, "symbolic link"):
                queue._fcm_credentials()


if __name__ == "__main__":
    unittest.main()

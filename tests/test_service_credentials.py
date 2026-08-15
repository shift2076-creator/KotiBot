import os
from pathlib import Path
import stat
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from server_core.credentials import (
    CredentialMissingError,
    credential_directories,
    default_credential_directory,
    read_binary_credential_file,
    read_json_credential,
    read_json_credential_file,
    read_text_credential,
    resolve_credential_file,
)


class ServiceCredentialTests(unittest.TestCase):
    def _private_file(self, path: Path, payload: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)

        if os.name != "nt":
            path.parent.chmod(0o700)
            path.chmod(0o600)

    def test_systemd_credential_precedes_configured_storage(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            systemd_root = root / "systemd"
            configured_root = root / "configured"
            self._private_file(systemd_root / "tapo-password", b"systemd\n")
            self._private_file(configured_root / "tapo-password", b"configured")

            with patch.dict(
                os.environ,
                {
                    "CREDENTIALS_DIRECTORY": str(systemd_root),
                    "KOTIBOT_CREDENTIALS_DIR": str(configured_root),
                    "TAPO_PASSWORD": "legacy",
                },
                clear=True,
            ):
                value = read_text_credential("tapo-password")

            self.assertEqual(value, "systemd")

    def test_configured_credential_is_used(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._private_file(root / "tapo-username", b"protected")

            with patch.dict(
                os.environ,
                {
                    "KOTIBOT_CREDENTIALS_DIR": str(root),
                    "TAPO_USERNAME": "legacy",
                },
                clear=True,
            ):
                value = read_text_credential("tapo-username")

            self.assertEqual(value, "protected")

    def test_missing_protected_file_ignores_legacy_environment(self):
        with TemporaryDirectory() as temp_dir:
            with patch.dict(
                os.environ,
                {
                    "KOTIBOT_CREDENTIALS_DIR": temp_dir,
                    "TAPO_USERNAME": "legacy",
                },
                clear=True,
            ):
                value = read_text_credential("tapo-username")

            self.assertEqual(value, "")

    def test_existing_invalid_file_never_falls_back_to_environment(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._private_file(root / "tapo-password", b"first\nsecond")

            with patch.dict(
                os.environ,
                {
                    "KOTIBOT_CREDENTIALS_DIR": str(root),
                    "TAPO_PASSWORD": "legacy",
                },
                clear=True,
            ):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "must contain one text line",
                ):
                    read_text_credential("tapo-password")

    @unittest.skipIf(os.name == "nt", "POSIX permissions required")
    def test_world_readable_credential_is_rejected_without_fallback(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            credential = root / "tapo-password"
            self._private_file(credential, b"protected")
            credential.chmod(0o644)

            with patch.dict(
                os.environ,
                {
                    "KOTIBOT_CREDENTIALS_DIR": str(root),
                    "TAPO_PASSWORD": "legacy",
                },
                clear=True,
            ):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "permissions are not private",
                ):
                    read_text_credential("tapo-password")

    @unittest.skipIf(os.name == "nt", "POSIX permissions required")
    def test_group_read_only_credential_is_accepted(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            credential = root / "tapo-password"
            self._private_file(credential, b"protected")
            credential.chmod(0o640)

            with patch.dict(
                os.environ,
                {"KOTIBOT_CREDENTIALS_DIR": str(root)},
                clear=True,
            ):
                value = read_text_credential("tapo-password")

            self.assertEqual(value, "protected")

    @unittest.skipIf(os.name == "nt", "Symbolic-link test requires POSIX")
    def test_symbolic_link_credential_is_rejected_without_fallback(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            target = root / "target"
            self._private_file(target, b"protected")
            (root / "tapo-password").symlink_to(target)

            with patch.dict(
                os.environ,
                {
                    "KOTIBOT_CREDENTIALS_DIR": str(root),
                    "TAPO_PASSWORD": "legacy",
                },
                clear=True,
            ):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "must not be a symbolic link",
                ):
                    read_text_credential("tapo-password")

    def test_required_missing_credential_raises_redacted_error(self):
        with TemporaryDirectory() as temp_dir:
            with patch.dict(
                os.environ,
                {"KOTIBOT_CREDENTIALS_DIR": temp_dir},
                clear=True,
            ):
                with self.assertRaises(CredentialMissingError) as context:
                    read_text_credential(
                        "tapo-password",
                        required=True,
                    )

            self.assertNotIn("legacy-secret", str(context.exception))

    def test_relative_credential_directory_is_rejected(self):
        with patch.dict(
            os.environ,
            {"KOTIBOT_CREDENTIALS_DIR": "relative/credentials"},
            clear=True,
        ):
            with self.assertRaisesRegex(RuntimeError, "must be an absolute"):
                credential_directories()

    @unittest.skipIf(os.name == "nt", "POSIX permissions required")
    def test_insecure_selected_directory_is_rejected(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "credentials"
            root.mkdir(mode=0o755)
            root.chmod(0o755)

            with patch.dict(
                os.environ,
                {"KOTIBOT_CREDENTIALS_DIR": str(root)},
                clear=True,
            ):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "directory permissions are not private",
                ):
                    read_text_credential("tapo-password")

    def test_credential_name_must_be_one_filename(self):
        with TemporaryDirectory() as temp_dir:
            with patch.dict(
                os.environ,
                {"KOTIBOT_CREDENTIALS_DIR": temp_dir},
                clear=True,
            ):
                with self.assertRaisesRegex(RuntimeError, "safe filename"):
                    read_text_credential("../tapo-password")

    def test_resolve_file_never_selects_a_legacy_source(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            protected = root / "credentials" / "firebase-service-account.json"
            legacy = root / "source" / "firebase-service-account.json"
            self._private_file(protected, b"{}")

            with patch.dict(
                os.environ,
                {"KOTIBOT_CREDENTIALS_DIR": str(protected.parent)},
                clear=True,
            ):
                self.assertEqual(
                    resolve_credential_file(
                        "firebase-service-account.json",
                    ),
                    protected,
                )
                protected.unlink()
                self.assertEqual(
                    resolve_credential_file(
                        "firebase-service-account.json",
                    ),
                    protected,
                )

    def test_json_credential_requires_private_object_file(self):
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "firebase-service-account.json"
            self._private_file(path, b'{"type":"service_account"}')

            data = read_json_credential_file(
                path,
                credential_name="firebase-service-account.json",
            )
            self.assertEqual(data, {"type": "service_account"})

            self._private_file(path, b"[]")

            with self.assertRaisesRegex(RuntimeError, "must contain an object"):
                read_json_credential_file(
                    path,
                    credential_name="firebase-service-account.json",
                )

    def test_named_json_credential_prefers_selected_protected_root(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            credential = root / "integration-credentials.json"
            self._private_file(
                credential,
                b'{"version":1,"cloudflare_api_token":"protected"}',
            )

            with patch.dict(
                os.environ,
                {"KOTIBOT_CREDENTIALS_DIR": str(root)},
                clear=True,
            ):
                data = read_json_credential(
                    "integration-credentials.json"
                )

            self.assertEqual(data["version"], 1)
            self.assertEqual(
                data["cloudflare_api_token"],
                "protected",
            )

    def test_optional_named_json_credential_returns_none_when_missing(self):
        with TemporaryDirectory() as temp_dir:
            with patch.dict(
                os.environ,
                {"KOTIBOT_CREDENTIALS_DIR": temp_dir},
                clear=True,
            ):
                data = read_json_credential(
                    "integration-credentials.json"
                )

            self.assertIsNone(data)

    def test_invalid_named_json_credential_fails_closed(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._private_file(
                root / "integration-credentials.json",
                b"not-json",
            )

            with patch.dict(
                os.environ,
                {"KOTIBOT_CREDENTIALS_DIR": str(root)},
                clear=True,
            ):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "not a valid JSON document",
                ):
                    read_json_credential(
                        "integration-credentials.json"
                    )

    def test_required_named_json_credential_raises_when_missing(self):
        with TemporaryDirectory() as temp_dir:
            with patch.dict(
                os.environ,
                {"KOTIBOT_CREDENTIALS_DIR": temp_dir},
                clear=True,
            ):
                with self.assertRaises(CredentialMissingError):
                    read_json_credential(
                        "integration-credentials.json",
                        required=True,
                    )

    def test_binary_reader_enforces_size_limit(self):
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "credential"
            self._private_file(path, b"12345")

            with self.assertRaisesRegex(RuntimeError, "too large"):
                read_binary_credential_file(
                    path,
                    credential_name="credential",
                    max_bytes=4,
                )

    def test_windows_default_uses_program_data(self):
        windows_os = SimpleNamespace(
            name="nt",
            environ={"PROGRAMDATA": "/program-data"},
        )

        with patch("server_core.credentials.os", windows_os):
            path = default_credential_directory()

        self.assertEqual(
            path,
            Path("/program-data") / "KotiBot" / "credentials",
        )


if __name__ == "__main__":
    unittest.main()

import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from server_core.credentials import CredentialMissingError
from server_core.integration_credentials import (
    CAMERA_TALK_ICE_SERVERS_ENVIRONMENT,
    CAMERA_TALK_TURN_CREDENTIAL_ENVIRONMENT,
    CAMERA_TALK_TURN_USERNAME_ENVIRONMENT,
    CLOUDFLARE_API_TOKEN_ENVIRONMENT,
    INTEGRATION_CREDENTIAL_NAME,
    IntegrationCredentials,
    integration_credential_document_from_environment,
    load_integration_credentials,
    validate_integration_credential_document,
)


class IntegrationCredentialTests(unittest.TestCase):
    def _private_document(self, root: Path, document: dict) -> Path:
        root.mkdir(parents=True, exist_ok=True)
        path = root / INTEGRATION_CREDENTIAL_NAME
        path.write_text(json.dumps(document), encoding="utf-8")

        if os.name != "nt":
            root.chmod(0o700)
            path.chmod(0o600)

        return path

    def _legacy_environment(self) -> dict[str, str]:
        return {
            CLOUDFLARE_API_TOKEN_ENVIRONMENT: "legacy-cloudflare",
            CAMERA_TALK_TURN_USERNAME_ENVIRONMENT: "legacy-user",
            CAMERA_TALK_TURN_CREDENTIAL_ENVIRONMENT: "legacy-password",
            CAMERA_TALK_ICE_SERVERS_ENVIRONMENT: json.dumps({
                "urls": "turn:legacy.example.invalid:3478",
                "username": "composite-user",
                "credential": "composite-password",
            }),
        }

    def test_legacy_environment_builds_closed_normalized_document(self):
        document = integration_credential_document_from_environment(
            self._legacy_environment()
        )

        self.assertEqual(document["version"], 1)
        self.assertEqual(
            document["cloudflare_api_token"],
            "legacy-cloudflare",
        )
        self.assertEqual(
            document["camera_talk_ice_servers"],
            [{
                "urls": "turn:legacy.example.invalid:3478",
                "username": "composite-user",
                "credential": "composite-password",
            }],
        )

    def test_protected_document_is_the_only_runtime_source(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._private_document(root, {
                "version": 1,
                "cloudflare_api_token": "protected-cloudflare",
                "camera_talk_turn_username": "protected-user",
                "camera_talk_turn_credential": "protected-password",
                "camera_talk_ice_servers": [{
                    "urls": "turn:protected.example.invalid:3478",
                    "username": "protected-composite-user",
                    "credential": "protected-composite-password",
                }],
            })
            environment = self._legacy_environment()
            environment["KOTIBOT_CREDENTIALS_DIR"] = str(root)

            with patch.dict(os.environ, environment, clear=True):
                credentials = load_integration_credentials()

            self.assertEqual(
                credentials.cloudflare_api_token,
                "protected-cloudflare",
            )
            self.assertEqual(
                credentials.camera_talk_turn_username,
                "protected-user",
            )
            self.assertEqual(
                credentials.camera_talk_turn_credential,
                "protected-password",
            )
            self.assertEqual(
                credentials.camera_talk_ice_servers()[0]["urls"],
                "turn:protected.example.invalid:3478",
            )

    def test_absent_protected_document_ignores_named_legacy_inputs(self):
        with TemporaryDirectory() as temp_dir:
            environment = self._legacy_environment()
            environment["KOTIBOT_CREDENTIALS_DIR"] = temp_dir

            with patch.dict(os.environ, environment, clear=True):
                with self.assertRaises(CredentialMissingError):
                    load_integration_credentials()

    def test_empty_protected_document_remains_an_empty_configuration(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._private_document(root, {"version": 1})
            environment = self._legacy_environment()
            environment["KOTIBOT_CREDENTIALS_DIR"] = str(root)

            with patch.dict(os.environ, environment, clear=True):
                credentials = load_integration_credentials()

            self.assertEqual(credentials.cloudflare_api_token, "")
            self.assertEqual(credentials.camera_talk_turn_username, "")
            self.assertEqual(credentials.camera_talk_turn_credential, "")
            self.assertEqual(credentials.camera_talk_ice_servers(), [])

    def test_invalid_protected_document_never_falls_back(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._private_document(root, {
                "version": 1,
                "unexpected": "legacy-must-not-win",
            })
            environment = self._legacy_environment()
            environment["KOTIBOT_CREDENTIALS_DIR"] = str(root)

            with patch.dict(os.environ, environment, clear=True):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "unknown fields",
                ):
                    load_integration_credentials()

    def test_composite_ice_servers_are_defensively_copied(self):
        credentials = IntegrationCredentials.from_document({
            "version": 1,
            "camera_talk_ice_servers": [{
                "urls": ["turn:relay.example.invalid:3478"],
                "credential": {"token": "protected"},
            }],
        })

        first = credentials.camera_talk_ice_servers()
        first[0]["urls"].append("turn:mutated.example.invalid:3478")
        first[0]["credential"]["token"] = "mutated"

        second = credentials.camera_talk_ice_servers()
        self.assertEqual(
            second[0]["urls"],
            ["turn:relay.example.invalid:3478"],
        )
        self.assertEqual(
            second[0]["credential"],
            {"token": "protected"},
        )

    def test_schema_rejects_invalid_types_and_malformed_composites(self):
        invalid_documents = (
            {"version": 2},
            {"version": 1, "cloudflare_api_token": 123},
            {"version": 1, "camera_talk_ice_servers": ["turn:url"]},
        )

        for document in invalid_documents:
            with self.subTest(document=document):
                with self.assertRaises(RuntimeError):
                    validate_integration_credential_document(document)

        with self.assertRaisesRegex(RuntimeError, "not valid JSON"):
            integration_credential_document_from_environment({
                CAMERA_TALK_ICE_SERVERS_ENVIRONMENT: "not-json",
            })


if __name__ == "__main__":
    unittest.main()

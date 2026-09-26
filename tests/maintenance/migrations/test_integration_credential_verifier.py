import io
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from tools.sec0044_verify_integration_credential_cutover import (
    main,
    verify_integration_credential_cutover,
)


class Sec0044IntegrationCredentialVerifierTests(unittest.TestCase):
    def _private_document(self, root: Path, document: dict) -> Path:
        root.mkdir(mode=0o700)
        path = root / "integration-credentials.json"
        path.write_text(json.dumps(document), encoding="utf-8")

        if os.name != "nt":
            root.chmod(0o700)
            path.chmod(0o600)

        return path

    def test_verifier_reports_presence_and_counts_only(self):
        with TemporaryDirectory() as temp_dir:
            path = self._private_document(Path(temp_dir) / "credentials", {
                "version": 1,
                "cloudflare_api_token": "private-cloudflare-marker",
                "camera_talk_turn_username": "private-user-marker",
                "camera_talk_turn_credential": "private-password-marker",
                "camera_talk_ice_servers": [{
                    "urls": "turn:relay.example.invalid:3478",
                    "credential": "private-composite-marker",
                }],
            })

            statuses = verify_integration_credential_cutover(
                path,
                require_cloudflare=True,
                require_camera_talk=True,
            )

            output = "\n".join(statuses)
            self.assertIn("cloudflare-api-token: ready", output)
            self.assertIn("camera-talk-turn-pair: ready", output)
            self.assertIn("servers=1", output)
            self.assertNotIn("private-", output)
            self.assertNotIn("relay.example", output)

    def test_incomplete_turn_pair_fails_closed(self):
        with TemporaryDirectory() as temp_dir:
            path = self._private_document(Path(temp_dir) / "credentials", {
                "version": 1,
                "camera_talk_turn_username": "private-user-marker",
            })

            with self.assertRaisesRegex(RuntimeError, "pair is incomplete"):
                verify_integration_credential_cutover(path)

    def test_require_flags_enforce_expected_integrations(self):
        with TemporaryDirectory() as temp_dir:
            path = self._private_document(
                Path(temp_dir) / "credentials",
                {"version": 1},
            )

            with self.assertRaisesRegex(RuntimeError, "Cloudflare"):
                verify_integration_credential_cutover(
                    path,
                    require_cloudflare=True,
                )

            with self.assertRaisesRegex(RuntimeError, "camera-talk"):
                verify_integration_credential_cutover(
                    path,
                    require_camera_talk=True,
                )

    def test_cli_failure_does_not_print_credential_values(self):
        with TemporaryDirectory() as temp_dir:
            path = self._private_document(Path(temp_dir) / "credentials", {
                "version": 1,
                "unexpected": "private-marker",
            })
            output = io.StringIO()

            with patch(
                "sys.argv",
                [
                    "sec0044_verify_integration_credential_cutover.py",
                    "--credential-file",
                    str(path),
                ],
            ):
                with patch("sys.stdout", output):
                    result = main()

            self.assertEqual(result, 1)
            self.assertIn("verification stopped", output.getvalue())
            self.assertNotIn("private-marker", output.getvalue())


if __name__ == "__main__":
    unittest.main()

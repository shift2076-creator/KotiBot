import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from server_core.integration_credentials import (
    LEGACY_INTEGRATION_CREDENTIAL_ENVIRONMENTS,
)
from tools.sec004_migrate_service_credentials import TAPO_CREDENTIALS
from tools.sec0045_verify_complete_credential_cutover import (
    DASHBOARD_LEGACY_ENVIRONMENTS,
)
from tools.sec007_verify_virtualenv_credentials import (
    AuditError,
    LEGACY_CREDENTIAL_ENVIRONMENTS,
    _print_result,
    audit_virtualenv,
    load_credential_inventory,
)


class Sec007VirtualenvCredentialAuditTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.credentials = self.root / "credentials"
        self.venv = self.root / ".venv"
        self.credentials.mkdir(mode=0o700)
        self.venv.mkdir()
        (self.venv / "pyvenv.cfg").write_text(
            "home = /usr/bin\n",
            encoding="utf-8",
        )

    def tearDown(self):
        self.temporary.cleanup()

    def _credential(self, name: str, payload: bytes) -> None:
        path = self.credentials / name
        path.write_bytes(payload)
        path.chmod(0o600)

    def _audit(self):
        return audit_virtualenv(
            self.venv,
            self.credentials,
            expected_credential_uid=None,
        )

    def test_clean_virtualenv_passes_without_executing_content(self):
        self._credential("tapo-password", b"active-password-value")
        package = self.venv / "lib" / "site-packages"
        package.mkdir(parents=True)
        (package / "sitecustomize.py").write_text(
            "raise RuntimeError('must never execute')\n",
            encoding="utf-8",
        )

        result = self._audit()

        self.assertFalse(result.contaminated)
        self.assertEqual(result.credential_match_files, 0)
        self.assertEqual(result.legacy_assignment_files, 0)
        self.assertEqual(result.package_reference_files, 0)
        self.assertEqual(result.venv_files, 2)

    def test_exact_protected_credential_match_requires_rebuild(self):
        secret = b"current-service-password"
        self._credential("tapo-password", secret)
        exposed = self.venv / "activation-copy"
        exposed.write_bytes(b"export VALUE=" + secret + b"\n")

        result = self._audit()

        self.assertTrue(result.contaminated)
        self.assertEqual(result.credential_match_files, 1)

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            _print_result(result)

        rendered = output.getvalue()
        self.assertIn("SEC-007 REBUILD REQUIRED", rendered)
        self.assertNotIn(secret.decode("ascii"), rendered)

    def test_reformatted_json_secret_match_requires_rebuild(self):
        secret = "private-key-material-for-test"
        document = {
            "type": "service_account",
            "private_key": secret,
            "client_email": "service@example.invalid",
        }
        self._credential(
            "firebase-service-account.json",
            json.dumps(document, indent=2).encode("utf-8"),
        )
        (self.venv / "generated-config.json").write_text(
            json.dumps({"unrelated": secret}),
            encoding="utf-8",
        )

        result = self._audit()

        self.assertTrue(result.contaminated)
        self.assertEqual(result.credential_match_files, 1)

    def test_retired_environment_assignment_requires_rebuild(self):
        retired = "retired-value-never-print"
        self._credential("tapo-password", b"different-current-password")
        (self.venv / "activate.local").write_text(
            f"export TAPO_PASSWORD={retired}\n",
            encoding="utf-8",
        )

        result = self._audit()

        self.assertTrue(result.contaminated)
        self.assertEqual(result.credential_match_files, 0)
        self.assertEqual(result.legacy_assignment_files, 1)

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            _print_result(result)

        self.assertNotIn(retired, output.getvalue())

    def test_retired_assignment_syntaxes_are_detected(self):
        self._credential("tapo-password", b"different-current-password")
        assignments = (
            b'config["TAPO_PASSWORD"] = "retired"\n',
            b'{"TAPO_PASSWORD": "retired"}\n',
            b"TAPO_PASSWORD = retired\n",
        )

        for index, assignment in enumerate(assignments):
            with self.subTest(assignment=assignment):
                path = self.venv / f"assignment-{index}"
                path.write_bytes(assignment)

        result = self._audit()

        self.assertTrue(result.contaminated)
        self.assertEqual(result.legacy_assignment_files, len(assignments))

    def test_environment_name_without_assignment_is_not_contamination(self):
        self._credential("tapo-password", b"different-current-password")
        (self.venv / "metadata.txt").write_text(
            "documentation mentions TAPO_PASSWORD but assigns nothing\n",
            encoding="utf-8",
        )

        result = self._audit()

        self.assertFalse(result.contaminated)

    def test_installed_package_documentation_is_not_contamination(self):
        self._credential("tapo-password", b"different-current-password")
        packages = self.venv / "lib" / "python3.13" / "site-packages"
        metadata = packages / "tapo-0.9.0.dist-info"
        metadata.mkdir(parents=True)
        (packages / "README.md").write_text(
            "TAPO_USERNAME=example@example.invalid\n"
            "TAPO_PASSWORD=example-password\n",
            encoding="utf-8",
        )
        (metadata / "METADATA").write_text(
            "Name: tapo\n\n"
            "TAPO_USERNAME=example@example.invalid\n"
            "TAPO_PASSWORD=example-password\n",
            encoding="utf-8",
        )

        result = self._audit()

        self.assertFalse(result.contaminated)
        self.assertEqual(result.legacy_assignment_files, 0)
        self.assertEqual(result.package_reference_files, 2)

    def test_exact_credential_in_package_documentation_still_fails(self):
        secret = "current-service-password"
        self._credential("tapo-password", secret.encode("ascii"))
        packages = self.venv / "lib" / "site-packages"
        packages.mkdir(parents=True)
        (packages / "README.md").write_text(
            f"TAPO_PASSWORD={secret}\n",
            encoding="utf-8",
        )

        result = self._audit()

        self.assertTrue(result.contaminated)
        self.assertEqual(result.credential_match_files, 1)
        self.assertEqual(result.package_reference_files, 1)

    def test_symlinks_are_counted_and_never_followed(self):
        secret = b"current-service-password"
        self._credential("tapo-password", secret)
        outside = self.root / "outside"
        outside.write_bytes(secret)
        (self.venv / "linked-secret").symlink_to(outside)
        external_directory = self.root / "external-directory"
        external_directory.mkdir()
        (external_directory / "payload").write_bytes(secret)
        (self.venv / "linked-directory").symlink_to(
            external_directory,
            target_is_directory=True,
        )

        result = self._audit()

        self.assertFalse(result.contaminated)
        self.assertEqual(result.symlinks_skipped, 2)

    def test_identifier_only_file_does_not_create_weak_comparison(self):
        self._credential("tapo-username", b"admin")
        self._credential("tapo-password", b"current-service-password")
        (self.venv / "metadata.txt").write_text(
            "package administration role: admin\n",
            encoding="utf-8",
        )

        result = self._audit()

        self.assertFalse(result.contaminated)
        self.assertEqual(result.protected_needles, 1)

    def test_legacy_environment_contract_matches_cutover_authorities(self):
        expected = (
            *(environment for _, environment in TAPO_CREDENTIALS),
            *LEGACY_INTEGRATION_CREDENTIAL_ENVIRONMENTS,
            *DASHBOARD_LEGACY_ENVIRONMENTS,
        )

        self.assertEqual(LEGACY_CREDENTIAL_ENVIRONMENTS, expected)

    def test_short_secret_value_stops_inconclusive_audit(self):
        self._credential("tapo-password", b"short")

        with self.assertRaisesRegex(AuditError, "too short"):
            load_credential_inventory(
                self.credentials,
                expected_uid=None,
            )

    def test_insecure_credential_permissions_stop_audit(self):
        self._credential("tapo-password", b"current-service-password")
        (self.credentials / "tapo-password").chmod(0o644)

        with self.assertRaisesRegex(AuditError, "permissions"):
            self._audit()

    def test_credential_symlink_stops_audit(self):
        outside = self.root / "credential-source"
        outside.write_bytes(b"current-service-password")
        (self.credentials / "tapo-password").symlink_to(outside)

        with self.assertRaisesRegex(AuditError, "opened safely"):
            self._audit()

    def test_result_output_contains_counts_but_no_identifiers(self):
        secret = b"current-service-password"
        identifier = b"private-account@example.invalid"
        self._credential("tapo-password", secret)
        self._credential("tapo-username", identifier)

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            _print_result(self._audit())

        rendered = output.getvalue()
        self.assertIn("Result: PASS", rendered)
        self.assertIn("Destructive action performed: NO", rendered)
        self.assertNotIn(secret.decode("ascii"), rendered)
        self.assertNotIn(identifier.decode("ascii"), rendered)


if __name__ == "__main__":
    unittest.main()

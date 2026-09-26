import io
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from server_core.io import json_backup_path
from tools.sec0045_verify_complete_credential_cutover import (
    FIREBASE_CREDENTIAL_NAME,
    INTEGRATION_CREDENTIAL_NAME,
    SERVICE_CREDENTIAL_NAMES,
    ServiceSnapshot,
    VerificationSummary,
    _process_identity_from_status,
    inspect_active_service,
    main,
    verify_complete_cutover,
)


class Sec0045CompleteCredentialCutoverTests(unittest.TestCase):
    @staticmethod
    def _write_private(path: Path, payload: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        path.write_bytes(payload)

        if os.name != "nt":
            path.parent.chmod(0o700)
            path.chmod(0o600)

    @classmethod
    def _write_json(cls, path: Path, document: dict) -> None:
        cls._write_private(
            path,
            (json.dumps(document, sort_keys=True) + "\n").encode(
                "utf-8"
            ),
        )

    def _fixture(self, root: Path) -> dict:
        source_credentials = root / "service-credentials"
        runtime_credentials = root / "runtime-credentials"
        data_root = root / "data"
        legacy_firebase = (
            root / "legacy" / "firebase-service-account.json"
        )
        legacy_security = root / "legacy" / "security_state.json"
        tapo_values = {
            "tapo-username": "private-tapo-user@example.invalid",
            "tapo-password": "private-tapo-password-marker",
            "tapo-camera-username": "private-camera-user-marker",
            "tapo-camera-password": "private-camera-password-marker",
        }
        firebase_document = {
            "type": "service_account",
            "private_key": "private-firebase-key-marker",
            "private_key_id": "private-firebase-key-id-marker",
            "client_email": "private-firebase@example.invalid",
            "client_id": "private-firebase-client-id-marker",
        }
        integration_document = {
            "version": 1,
            "cloudflare_api_token": "private-cloudflare-token-marker",
            "camera_talk_turn_username": "private-turn-user-marker",
            "camera_talk_turn_credential": (
                "private-turn-credential-marker"
            ),
            "camera_talk_ice_servers": [{
                "urls": "turn:relay.example.invalid:3478",
                "username": "private-composite-user-marker",
                "credential": "private-composite-credential-marker",
            }],
        }
        payloads = {
            **{
                name: value.encode("utf-8")
                for name, value in tapo_values.items()
            },
            FIREBASE_CREDENTIAL_NAME: (
                json.dumps(firebase_document) + "\n"
            ).encode("utf-8"),
            INTEGRATION_CREDENTIAL_NAME: (
                json.dumps(integration_document) + "\n"
            ).encode("utf-8"),
        }

        for name in SERVICE_CREDENTIAL_NAMES:
            self._write_private(source_credentials / name, payloads[name])
            self._write_private(runtime_credentials / name, payloads[name])

        security_state = (
            data_root
            / "protected"
            / "security"
            / "security_state.json"
        )
        security_document = {
            "session_secret": "private-session-secret-marker",
            "dashboard_users": {
                "private-dashboard@example.invalid": {
                    "password_hash": "private-password-hash-marker",
                },
            },
            "dashboard_sessions": {
                "private-session-identifier-marker": {
                    "expires_at": 100,
                },
            },
            "device_keys": {
                "device-1": {
                    "current": {
                        "secret": "private-device-secret-marker",
                    },
                },
            },
            "device_enrollments": {
                "device-2": {
                    "token_hash": "private-enrollment-hash-marker",
                },
            },
        }
        self._write_json(security_state, security_document)
        self._write_json(
            json_backup_path(security_state),
            security_document,
        )
        notification_state = (
            data_root
            / "protected"
            / "devices"
            / "notification_credentials.json"
        )
        notification_document = {
            "version": 1,
            "tokens": {
                "device-1": {
                    "token": "private-notification-token-marker",
                    "updated_at": 100,
                },
            },
        }
        self._write_json(notification_state, notification_document)
        self._write_json(
            json_backup_path(notification_state),
            notification_document,
        )
        self._write_json(
            data_root / "state" / "server_state.json",
            {"clients": {}, "system": {"armed": False}},
        )
        self._write_json(
            data_root / "state" / "server_state.lkg.json",
            {"clients": {}, "system": {"armed": False}},
        )
        self._write_json(
            data_root / "state" / "tapo" / "tapo_config.json",
            {"enabled": True},
        )
        self._write_private(
            legacy_firebase,
            payloads[FIREBASE_CREDENTIAL_NAME],
        )
        self._write_json(legacy_security, security_document)
        environment = {
            "TAPO_USERNAME": tapo_values["tapo-username"],
            "TAPO_PASSWORD": tapo_values["tapo-password"],
            "TAPO_CAMERA_USERNAME": tapo_values[
                "tapo-camera-username"
            ],
            "TAPO_CAMERA_PASSWORD": tapo_values[
                "tapo-camera-password"
            ],
            "KOTIBOT_CLOUDFLARE_API_TOKEN": (
                integration_document["cloudflare_api_token"]
            ),
            "KOTIBOT_CAMERA_TALK_TURN_USERNAME": (
                integration_document["camera_talk_turn_username"]
            ),
            "KOTIBOT_CAMERA_TALK_TURN_CREDENTIAL": (
                integration_document["camera_talk_turn_credential"]
            ),
            "KOTIBOT_CAMERA_TALK_ICE_SERVERS": json.dumps(
                integration_document["camera_talk_ice_servers"]
            ),
        }
        return {
            "source_credentials": source_credentials,
            "runtime_credentials": runtime_credentials,
            "data_root": data_root,
            "legacy_firebase": legacy_firebase,
            "legacy_security": legacy_security,
            "environment": environment,
        }

    @staticmethod
    def _verify(fixture):
        owner = (
            None
            if os.name == "nt"
            else (os.getuid(), os.getgid())
        )
        return verify_complete_cutover(
            source_credential_directory=fixture["source_credentials"],
            runtime_credential_directory=fixture["runtime_credentials"],
            data_root=fixture["data_root"],
            service_environment=fixture["environment"],
            legacy_firebase_source=fixture["legacy_firebase"],
            legacy_security_source=fixture["legacy_security"],
            minimum_tokens=1,
            manager_owner=owner,
            service_owner=owner,
        )

    def test_complete_fixture_verifies_every_sec004_store(self):
        with TemporaryDirectory() as temp_dir:
            fixture = self._fixture(Path(temp_dir))
            summary = self._verify(fixture)

            self.assertEqual(summary.service_credentials, 6)
            self.assertEqual(summary.dashboard_users, 1)
            self.assertEqual(summary.dashboard_sessions, 1)
            self.assertEqual(summary.device_keys, 1)
            self.assertEqual(summary.device_enrollments, 1)
            self.assertEqual(summary.notification_tokens, 1)
            self.assertEqual(summary.ordinary_documents, 3)
            self.assertEqual(summary.retained_legacy_sources, 10)

    def test_ordinary_last_known_good_copy_is_scanned(self):
        with TemporaryDirectory() as temp_dir:
            fixture = self._fixture(Path(temp_dir))
            self._write_json(
                fixture["data_root"]
                / "state"
                / "server_state.lkg.json",
                {
                    "note": (
                        "prefix-private-notification-token-marker-suffix"
                    ),
                },
            )

            with self.assertRaisesRegex(
                RuntimeError,
                "protected credential value",
            ):
                self._verify(fixture)

    def test_forbidden_ordinary_credential_key_is_rejected(self):
        with TemporaryDirectory() as temp_dir:
            fixture = self._fixture(Path(temp_dir))
            self._write_json(
                fixture["data_root"]
                / "state"
                / "tapo"
                / "tapo_device_state.json",
                {"devices": {"camera": {"tapo_rtsp_url": "redacted"}}},
            )

            with self.assertRaisesRegex(
                RuntimeError,
                "credential field",
            ):
                self._verify(fixture)

    def test_runtime_credential_mismatch_fails_restart_proof(self):
        with TemporaryDirectory() as temp_dir:
            fixture = self._fixture(Path(temp_dir))
            self._write_private(
                fixture["runtime_credentials"] / "tapo-password",
                b"different-private-password",
            )

            with self.assertRaisesRegex(
                RuntimeError,
                "does not match source",
            ):
                self._verify(fixture)

    @unittest.skipIf(os.name == "nt", "POSIX permissions required")
    def test_systemd_read_only_runtime_permissions_are_accepted(self):
        with TemporaryDirectory() as temp_dir:
            fixture = self._fixture(Path(temp_dir))
            fixture["runtime_credentials"].chmod(0o550)

            for name in SERVICE_CREDENTIAL_NAMES:
                (fixture["runtime_credentials"] / name).chmod(0o440)

            summary = self._verify(fixture)

            self.assertEqual(summary.service_credentials, 6)

    @unittest.skipIf(os.name == "nt", "POSIX permissions required")
    def test_world_readable_runtime_credential_is_rejected(self):
        with TemporaryDirectory() as temp_dir:
            fixture = self._fixture(Path(temp_dir))
            path = fixture["runtime_credentials"] / "tapo-password"
            path.chmod(0o444)

            with self.assertRaisesRegex(
                RuntimeError,
                "Runtime credential permissions are not private",
            ):
                self._verify(fixture)

    @unittest.skipIf(os.name == "nt", "POSIX permissions required")
    def test_insecure_service_credential_permission_is_rejected(self):
        with TemporaryDirectory() as temp_dir:
            fixture = self._fixture(Path(temp_dir))
            path = fixture["source_credentials"] / "tapo-password"
            path.chmod(0o644)

            with self.assertRaisesRegex(
                RuntimeError,
                "permissions must be 600",
            ):
                self._verify(fixture)

    @unittest.skipIf(os.name == "nt", "POSIX symbolic links required")
    def test_symbolic_service_credential_directory_is_rejected(self):
        with TemporaryDirectory() as temp_dir:
            fixture = self._fixture(Path(temp_dir))
            link = Path(temp_dir) / "credential-link"
            link.symlink_to(
                fixture["source_credentials"],
                target_is_directory=True,
            )
            fixture["source_credentials"] = link

            with self.assertRaisesRegex(
                RuntimeError,
                "must not be a symbolic link",
            ):
                self._verify(fixture)

    def test_missing_legacy_source_is_rejected_without_value_output(self):
        with TemporaryDirectory() as temp_dir:
            fixture = self._fixture(Path(temp_dir))
            fixture["environment"].pop("TAPO_PASSWORD")

            with self.assertRaisesRegex(
                RuntimeError,
                "Legacy rollback source is missing: TAPO_PASSWORD",
            ):
                self._verify(fixture)

    def test_stale_legacy_source_is_rejected_without_value_output(self):
        with TemporaryDirectory() as temp_dir:
            fixture = self._fixture(Path(temp_dir))
            fixture["environment"]["TAPO_PASSWORD"] = (
                "different-private-password"
            )

            with self.assertRaisesRegex(
                RuntimeError,
                "does not match protected credential: TAPO_PASSWORD",
            ):
                self._verify(fixture)

    def test_cli_output_contains_counts_but_no_private_values(self):
        with TemporaryDirectory() as temp_dir:
            fixture = self._fixture(Path(temp_dir))
            process_user_id = (
                0 if os.name == "nt" else os.getuid()
            )
            process_group_id = (
                0 if os.name == "nt" else os.getgid()
            )
            snapshot = ServiceSnapshot(
                process_id=123,
                process_user_id=process_user_id,
                process_group_id=process_group_id,
                environment=fixture["environment"],
                data_root=fixture["data_root"],
                runtime_credential_directory=(
                    fixture["runtime_credentials"]
                ),
            )
            output = io.StringIO()
            arguments = [
                "--credential-directory",
                str(fixture["source_credentials"]),
                "--legacy-firebase-source",
                str(fixture["legacy_firebase"]),
                "--legacy-security-source",
                str(fixture["legacy_security"]),
                "--minimum-tokens",
                "1",
            ]
            summary = VerificationSummary(
                service_credentials=6,
                dashboard_users=1,
                dashboard_sessions=1,
                device_keys=1,
                device_enrollments=1,
                notification_tokens=1,
                ordinary_documents=3,
                retained_legacy_sources=10,
            )

            with patch(
                "tools.sec0045_verify_complete_credential_cutover."
                "inspect_active_service",
                return_value=snapshot,
            ):
                with patch(
                    "tools.sec0045_verify_complete_credential_cutover."
                    "verify_complete_cutover",
                    return_value=summary,
                ):
                    with patch("sys.stdout", output):
                        result = main(arguments)

            text = output.getvalue()
            self.assertEqual(result, 0)
            self.assertIn("verification passed", text)
            self.assertIn("runtime-credentials=6", text)
            self.assertIn("documents=3", text)
            self.assertNotIn("private-", text)
            self.assertNotIn("example.invalid", text)

    def test_systemd_adapter_uses_active_process_runtime_roots(self):
        environment = {
            "CREDENTIALS_DIRECTORY": "/run/credentials/kotibot.service",
            "KOTIBOT_DATA_DIR": "/var/lib/kotibot",
        }

        with patch(
            "tools.sec0045_verify_complete_credential_cutover."
            "_systemd_properties",
            return_value={"ActiveState": "active", "MainPID": "4321"},
        ):
            with patch(
                "tools.sec0045_verify_complete_credential_cutover."
                "_process_identity",
                return_value=(1000, 1000),
            ):
                with patch(
                    "tools.sec0045_verify_complete_credential_cutover."
                    "_allowed_process_environment",
                    return_value=environment,
                ):
                    snapshot = inspect_active_service("kotibot")

        self.assertEqual(snapshot.process_id, 4321)
        self.assertEqual(snapshot.data_root, Path("/var/lib/kotibot"))
        self.assertEqual(
            snapshot.runtime_credential_directory,
            Path("/run/credentials/kotibot.service"),
        )

    def test_process_identity_uses_effective_status_identifiers(self):
        identity = _process_identity_from_status(
            b"Name:\tkotibot\n"
            b"Uid:\t1000\t1001\t1002\t1003\n"
            b"Gid:\t2000\t2001\t2002\t2003\n"
        )

        self.assertEqual(identity, (1001, 2001))

    def test_systemd_adapter_rejects_inactive_service(self):
        with patch(
            "tools.sec0045_verify_complete_credential_cutover."
            "_systemd_properties",
            return_value={"ActiveState": "inactive", "MainPID": "0"},
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                "service is not active",
            ):
                inspect_active_service("kotibot")

    def test_systemd_adapter_requires_runtime_credentials(self):
        with patch(
            "tools.sec0045_verify_complete_credential_cutover."
            "_systemd_properties",
            return_value={"ActiveState": "active", "MainPID": "4321"},
        ):
            with patch(
                "tools.sec0045_verify_complete_credential_cutover."
                "_process_identity",
                return_value=(1000, 1000),
            ):
                with patch(
                    "tools.sec0045_verify_complete_credential_cutover."
                    "_allowed_process_environment",
                    return_value={},
                ):
                    with self.assertRaisesRegex(
                        RuntimeError,
                        "runtime credential directory",
                    ):
                        inspect_active_service("kotibot")

    def test_cleanup_mode_requires_every_legacy_source_absent(self):
        with TemporaryDirectory() as temp_dir:
            fixture = self._fixture(Path(temp_dir))
            fixture["environment"] = {}
            fixture["legacy_firebase"].unlink()
            fixture["legacy_security"].unlink()

            owner = (
                None
                if os.name == "nt"
                else (os.getuid(), os.getgid())
            )
            summary = verify_complete_cutover(
                source_credential_directory=fixture[
                    "source_credentials"
                ],
                runtime_credential_directory=fixture[
                    "runtime_credentials"
                ],
                data_root=fixture["data_root"],
                service_environment=fixture["environment"],
                legacy_firebase_source=fixture["legacy_firebase"],
                legacy_security_source=fixture["legacy_security"],
                minimum_tokens=1,
                manager_owner=owner,
                service_owner=owner,
                expect_legacy_sources=False,
            )

            self.assertEqual(summary.retained_legacy_sources, 0)

    def test_cleanup_mode_rejects_dashboard_credential_environment(self):
        with TemporaryDirectory() as temp_dir:
            fixture = self._fixture(Path(temp_dir))
            fixture["environment"] = {
                "KOTIBOT_DASHBOARD_PASSWORD": "retired-password",
            }
            fixture["legacy_firebase"].unlink()
            fixture["legacy_security"].unlink()

            with self.assertRaisesRegex(
                RuntimeError,
                "Legacy credential environment remains active",
            ):
                owner = (
                    None
                    if os.name == "nt"
                    else (os.getuid(), os.getgid())
                )
                verify_complete_cutover(
                    source_credential_directory=fixture[
                        "source_credentials"
                    ],
                    runtime_credential_directory=fixture[
                        "runtime_credentials"
                    ],
                    data_root=fixture["data_root"],
                    service_environment=fixture["environment"],
                    legacy_firebase_source=fixture[
                        "legacy_firebase"
                    ],
                    legacy_security_source=fixture[
                        "legacy_security"
                    ],
                    minimum_tokens=1,
                    manager_owner=owner,
                    service_owner=owner,
                    expect_legacy_sources=False,
                )


if __name__ == "__main__":
    unittest.main()

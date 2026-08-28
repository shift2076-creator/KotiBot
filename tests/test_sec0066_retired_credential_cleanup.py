import contextlib
import io
import json
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from server_core.io import json_backup_path
from server_core.paths import RuntimePaths
from tools.sec0066_cleanup_retired_credentials import (
    CleanupError,
    _data_root_from_handoff,
    _print_result,
    _write_preflight_handoff,
    build_clean_security_state,
    build_systemd_cleanup,
    run_cleanup,
    sanitize_environment_file_text,
    sanitize_systemd_environment_text,
)


SOURCE_ROOT = Path(__file__).resolve().parents[1]


class Sec0066RetiredCredentialCleanupTests(unittest.TestCase):
    @staticmethod
    def _write_private(path: Path, payload: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        path.write_bytes(payload)
        if os.name != "nt":
            path.parent.chmod(0o700)
            path.chmod(0o600)

    def _server_state(self):
        return {
            "clients": {
                "android_home": [{
                    "deviceID": "monitor-live",
                    "provisioned": True,
                }],
                "android_key": [{
                    "deviceID": "control-live",
                    "provisioned": True,
                }],
                "tapo": [{
                    "deviceID": "tapo-external",
                    "provisioned": True,
                }],
            },
        }

    def test_cleanup_retains_only_verified_first_party_current_keys(self):
        state = {
            "session_secret": "current-session-secret",
            "device_keys": {
                "monitor-live": {
                    "current": {
                        "key_id": "monitor-current",
                        "secret": "monitor-secret",
                        "status": "active",
                    },
                    "previous": {
                        "key_id": "monitor-previous",
                        "secret": "monitor-previous-secret",
                        "status": "active",
                        "expires_at": 999,
                    },
                    "handoff_verified_at": 900,
                },
                "control-live": {
                    "current": {
                        "key_id": "control-current",
                        "secret": "control-secret",
                        "status": "active",
                    },
                    "pending": {
                        "key_id": "retired-pending",
                        "secret": "retired-pending-secret",
                        "status": "revoked",
                    },
                    "handoff_verified_at": 901,
                },
                "tapo-external": {
                    "current": {
                        "key_id": "tapo-key",
                        "secret": "tapo-secret",
                        "status": "active",
                    },
                },
                "orphaned": {
                    "current": {
                        "key_id": "orphan-key",
                        "secret": "orphan-secret",
                        "status": "revoked",
                    },
                },
            },
            "device_enrollments": {
                "expired": {
                    "token_hash": "expired-token",
                    "expires_at": 999,
                },
            },
            "dashboard_sessions": {
                "dashboard": {
                    "principal_type": "dashboard_user",
                    "email": "person@example.invalid",
                },
                "control-current-session": {
                    "principal_type": "key_client",
                    "device_id": "control-live",
                    "key_id": "control-current",
                },
                "stale-key-session": {
                    "principal_type": "key_client",
                    "device_id": "tapo-external",
                    "key_id": "tapo-key",
                },
                "empty-key-session": {
                    "principal_type": "key_client",
                    "device_id": "missing",
                    "key_id": "",
                },
            },
        }

        cleaned, counts = build_clean_security_state(
            state,
            self._server_state(),
            now=1_000,
        )

        self.assertEqual(
            set(cleaned["device_keys"]),
            {"monitor-live", "control-live"},
        )
        self.assertNotIn(
            "previous",
            cleaned["device_keys"]["monitor-live"],
        )
        self.assertNotIn(
            "pending",
            cleaned["device_keys"]["control-live"],
        )
        self.assertEqual(cleaned["device_enrollments"], {})
        self.assertEqual(
            set(cleaned["dashboard_sessions"]),
            {"dashboard", "control-current-session"},
        )
        self.assertEqual(counts["retained_device_keys"], 2)
        self.assertEqual(counts["removed_device_key_records"], 2)
        self.assertEqual(counts["removed_previous_slots"], 1)
        self.assertEqual(counts["removed_pending_slots"], 1)
        self.assertEqual(counts["removed_enrollments"], 1)
        self.assertEqual(counts["removed_key_client_sessions"], 2)

    def test_cleanup_blocks_unverified_or_still_usable_first_party_keys(self):
        unverified = {
            "device_keys": {
                "monitor-live": {
                    "current": {
                        "key_id": "current",
                        "secret": "secret",
                        "status": "active",
                    },
                },
                "control-live": {
                    "current": {
                        "key_id": "current-control",
                        "secret": "secret-control",
                        "status": "active",
                    },
                    "handoff_verified_at": 900,
                },
            },
            "device_enrollments": {},
        }
        with self.assertRaisesRegex(CleanupError, "not verified"):
            build_clean_security_state(
                unverified,
                self._server_state(),
                now=1_000,
            )

        unverified["device_keys"]["monitor-live"][
            "handoff_verified_at"
        ] = 900
        unverified["device_keys"]["monitor-live"]["previous"] = {
            "key_id": "previous",
            "secret": "previous-secret",
            "status": "active",
            "expires_at": 1_001,
        }
        with self.assertRaisesRegex(CleanupError, "still in grace"):
            build_clean_security_state(
                unverified,
                self._server_state(),
                now=1_000,
            )

    def test_systemd_cleanup_removes_only_dedicated_credential_lines(self):
        source = (
            "[Service]\n"
            'Environment="KOTIBOT_SECURITY=1"\n'
            'Environment="TAPO_PASSWORD=retired-value"\n'
            'Environment="TAPO_USERNAME=retired-user"\n'
        )

        cleaned, removed = sanitize_systemd_environment_text(source)

        self.assertEqual(
            cleaned,
            "[Service]\nEnvironment=\"KOTIBOT_SECURITY=1\"\n",
        )
        self.assertEqual(removed, {"TAPO_PASSWORD", "TAPO_USERNAME"})
        self.assertNotIn("retired-value", cleaned)

    def test_systemd_cleanup_rejects_mixed_assignment_lines(self):
        with self.assertRaisesRegex(CleanupError, "share one"):
            sanitize_systemd_environment_text(
                '[Service]\nEnvironment="TAPO_PASSWORD=retired" '
                '"KOTIBOT_SECURITY=1"\n'
            )

    def test_environment_file_cleanup_preserves_non_secret_settings(self):
        source = (
            "# KotiBot configuration\n"
            "KOTIBOT_TAPO_ENABLED=true\n"
            "TAPO_PASSWORD=retired-password\n"
            "KOTIBOT_DASHBOARD_EMAIL=person@example.invalid\n"
            "KOTIBOT_DASHBOARD_PASSWORD='retired dashboard password'\n"
        )

        cleaned, removed = sanitize_environment_file_text(source)

        self.assertEqual(
            cleaned,
            "# KotiBot configuration\nKOTIBOT_TAPO_ENABLED=true\n",
        )
        self.assertEqual(
            removed,
            {
                "TAPO_PASSWORD",
                "KOTIBOT_DASHBOARD_EMAIL",
                "KOTIBOT_DASHBOARD_PASSWORD",
            },
        )

    def test_systemd_cleanup_follows_declared_environment_file(self):
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            environment = root / "kotibot.env"
            environment.write_text(
                "KOTIBOT_TAPO_ENABLED=true\n"
                "TAPO_USERNAME=retired-user\n",
                encoding="utf-8",
            )
            unit = root / "kotibot.service"
            unit.write_text(
                "[Service]\n"
                f"EnvironmentFile={environment}\n",
                encoding="utf-8",
            )

            replacements, removed, environment_files = (
                build_systemd_cleanup((unit,))
            )

            self.assertEqual(removed, {"TAPO_USERNAME"})
            self.assertEqual(environment_files, {environment})
            self.assertEqual(
                replacements[environment],
                "KOTIBOT_TAPO_ENABLED=true\n",
            )
            self.assertNotIn(unit, replacements)

    def test_runtime_source_contract_has_no_credential_fallbacks(self):
        credentials = (
            SOURCE_ROOT / "server_core" / "credentials.py"
        ).read_text(encoding="utf-8")
        integrations = (
            SOURCE_ROOT / "server_core" / "integration_credentials.py"
        ).read_text(encoding="utf-8")
        tapo = (
            SOURCE_ROOT
            / "subsystems"
            / "client-tapo"
            / "tapo_control.py"
        ).read_text(encoding="utf-8")
        security = (
            SOURCE_ROOT
            / "subsystems"
            / "security"
            / "kotibot_security.py"
        ).read_text(encoding="utf-8")
        server = (SOURCE_ROOT / "kotibot_server.py").read_text(
            encoding="utf-8"
        )
        device_credentials = (
            SOURCE_ROOT / "server_core" / "device_credentials.py"
        ).read_text(encoding="utf-8")

        self.assertNotIn("legacy_environment", credentials)
        self.assertNotIn("legacy_file", credentials)
        self.assertNotIn("os.environ", integrations)
        self.assertNotIn("legacy_environment=", tapo)
        self.assertNotIn("legacy_state", security)
        self.assertNotIn("KOTIBOT_DASHBOARD_PASSWORD", security)
        self.assertNotIn("KOTIBOT_DASHBOARD_EMAIL", security)
        self.assertNotIn("LEGACY_SECURITY_STATE_FILE", server)
        self.assertNotIn("legacy_file=", server)
        self.assertNotIn("migrate_legacy_server_state", server)
        self.assertNotIn(
            "migrate_legacy_server_state",
            device_credentials,
        )

    @unittest.skipIf(os.name == "nt", "Linux cleanup adapter")
    def test_cleanup_action_removes_only_validated_fixture_targets(self):
        from tempfile import TemporaryDirectory
        from tools.sec00645_rotate_service_credentials import GROUPS

        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_root = root / "source"
            source_root.mkdir()
            data_root = root / "data"
            paths = RuntimePaths(
                source_root=source_root,
                data_root=data_root,
            ).validate()
            security = {
                "session_secret": "current-session",
                "device_keys": {
                    "monitor-live": {
                        "current": {
                            "key_id": "monitor-current",
                            "secret": "monitor-secret",
                            "status": "active",
                        },
                        "previous": {
                            "key_id": "retired",
                            "secret": "retired-secret",
                            "status": "revoked",
                        },
                        "handoff_verified_at": 1,
                    },
                    "control-live": {
                        "current": {
                            "key_id": "control-current",
                            "secret": "control-secret",
                            "status": "active",
                        },
                        "handoff_verified_at": 1,
                    },
                    "retired-external": {
                        "current": {
                            "key_id": "external",
                            "secret": "external-secret",
                            "status": "active",
                        },
                    },
                },
                "device_enrollments": {},
            }
            server = self._server_state()
            self._write_private(
                paths.security_state_file,
                (json.dumps(security) + "\n").encode(),
            )
            self._write_private(
                json_backup_path(paths.security_state_file),
                (json.dumps(security) + "\n").encode(),
            )
            self._write_private(
                paths.server_state_file,
                (json.dumps(server) + "\n").encode(),
            )

            legacy_firebase = source_root / "legacy-firebase.json"
            legacy_security = source_root / "legacy-security.json"
            transferred_firebase = root / "transferred-firebase.json"
            shared_environment = source_root / ".env.shared"
            for path in (
                legacy_firebase,
                legacy_security,
                transferred_firebase,
                shared_environment,
            ):
                self._write_private(path, b"fixture\n")

            candidate_root = root / "candidates"
            state_root = root / "rotation-state"
            for group in GROUPS.values():
                candidate = candidate_root / group.name
                previous = state_root / group.name / "previous"
                candidate.mkdir(parents=True)
                previous.mkdir(parents=True)
                for name in group.credential_names:
                    (candidate / name).write_bytes(b"candidate")
                    (previous / name).write_bytes(b"previous")
                (state_root / group.name / "manifest.json").write_text(
                    "{}\n",
                    encoding="utf-8",
                )

            environment_file = root / "kotibot.env"
            environment_file.write_text(
                "KOTIBOT_TAPO_ENABLED=true\n"
                "TAPO_PASSWORD=retired\n",
                encoding="utf-8",
            )
            unit = root / "kotibot.service"
            unit.write_text(
                "[Service]\n"
                f"EnvironmentFile={environment_file}\n",
                encoding="utf-8",
            )
            args = SimpleNamespace(
                service="kotibot",
                data_root=data_root,
                credential_directory=root / "credentials",
                candidate_root=candidate_root,
                state_root=state_root,
                legacy_firebase_source=legacy_firebase,
                legacy_security_source=legacy_security,
                firebase_transfer_source=transferred_firebase,
                legacy_shared_environment_source=shared_environment,
                handoff_file=root / "sec0066-handoff.json",
            )
            properties = {
                "ActiveState": "inactive",
                "FragmentPath": str(unit),
                "DropInPaths": "",
            }

            with patch(
                "tools.sec0066_cleanup_retired_credentials."
                "_systemd_properties",
                return_value=properties,
            ), patch(
                "tools.sec0066_cleanup_retired_credentials."
                "_validate_rotation_groups",
            ), patch(
                "tools.sec0066_cleanup_retired_credentials."
                "_validate_legacy_payloads",
            ):
                counts = run_cleanup(args)

            cleaned = json.loads(
                paths.security_state_file.read_text(encoding="utf-8")
            )
            self.assertEqual(
                set(cleaned["device_keys"]),
                {"monitor-live", "control-live"},
            )
            self.assertNotIn(
                "previous",
                cleaned["device_keys"]["monitor-live"],
            )
            self.assertEqual(
                environment_file.read_text(encoding="utf-8"),
                "KOTIBOT_TAPO_ENABLED=true\n",
            )
            for path in (
                legacy_firebase,
                legacy_security,
                transferred_firebase,
                shared_environment,
            ):
                self.assertFalse(path.exists())
            for group_name in GROUPS:
                self.assertFalse((candidate_root / group_name).exists())
                self.assertFalse((state_root / group_name).exists())
            self.assertEqual(counts["removed_device_key_records"], 1)
            self.assertEqual(counts["environment_files"], 1)

    @unittest.skipIf(os.name == "nt", "Linux cleanup adapter")
    def test_private_preflight_handoff_carries_data_root_across_stop(self):
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            args = SimpleNamespace(
                service="kotibot",
                handoff_file=root / "sec0066-handoff.json",
            )
            data_root = root / "data"
            owner_uid = os.geteuid()
            owner_gid = os.getegid()

            _write_preflight_handoff(
                args,
                data_root,
                owner_uid=owner_uid,
                owner_gid=owner_gid,
            )

            self.assertEqual(
                _data_root_from_handoff(
                    args,
                    expected_uid=owner_uid,
                ),
                data_root,
            )
            metadata = args.handoff_file.stat()
            self.assertEqual(metadata.st_uid, owner_uid)
            self.assertEqual(metadata.st_gid, owner_gid)
            self.assertEqual(metadata.st_mode & 0o777, 0o600)

            with self.assertRaisesRegex(CleanupError, "wrong owner"):
                _data_root_from_handoff(
                    args,
                    expected_uid=owner_uid + 1,
                )

    @unittest.skipIf(os.name == "nt", "Linux cleanup adapter")
    def test_preflight_handoff_defaults_to_root_ownership(self):
        args = SimpleNamespace(
            service="kotibot",
            handoff_file=Path("/run/kotibot-sec0066-test.json"),
        )

        with patch(
            "tools.sec0066_cleanup_retired_credentials."
            "_atomic_private_write",
        ) as writer:
            _write_preflight_handoff(args, Path("/var/lib/kotibot"))

        self.assertEqual(writer.call_args.kwargs["owner_uid"], 0)
        self.assertEqual(writer.call_args.kwargs["owner_gid"], 0)

    def test_output_does_not_disclose_private_values(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            _print_result("cleanup", {
                "rotation_groups": 3,
                "legacy_source_files": 3,
                "systemd_files": 1,
                "environment_files": 1,
                "systemd_environment_names": 4,
                "retained_device_keys": 4,
                "removed_device_key_records": 23,
                "removed_previous_slots": 20,
                "removed_enrollments": 0,
            })

        rendered = output.getvalue()
        for private_value in (
            "retired-password",
            "private-key-material",
            "device-identifier",
        ):
            self.assertNotIn(private_value, rendered)


if __name__ == "__main__":
    unittest.main()

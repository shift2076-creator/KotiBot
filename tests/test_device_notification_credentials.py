import json
import os
from pathlib import Path
import stat
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from server_core.device_credentials import (
    DeviceNotificationCredentialStore,
)
from server_core.io import json_backup_path
from server_core.paths import (
    build_runtime_paths,
    prepare_runtime_directories,
)


class DeviceNotificationCredentialTests(unittest.TestCase):
    @staticmethod
    def _state_file(root: Path) -> Path:
        return root / "protected" / "devices" / "notification_credentials.json"

    @staticmethod
    def _write_json(path: Path, data: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(data, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def test_runtime_path_is_external_and_prepared_privately(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_root = root / "source"
            data_root = root / "data"
            source_root.mkdir()

            with patch.dict(
                os.environ,
                {
                    "KOTIBOT_DATA_DIR": str(data_root),
                    "KOTIBOT_CACHE_DIR": str(root / "cache"),
                    "KOTIBOT_RUNTIME_DIR": str(root / "runtime"),
                    "KOTIBOT_TEMP_DIR": str(root / "temporary"),
                    "KOTIBOT_PACKAGE_DIR": str(root / "apks"),
                    "KOTIBOT_MEDIA_DIR": str(root / "media"),
                },
                clear=True,
            ):
                paths = build_runtime_paths(source_root)
                prepare_runtime_directories(paths)

            self.assertEqual(
                paths.device_notification_credentials_file,
                data_root
                / "protected"
                / "devices"
                / "notification_credentials.json",
            )
            self.assertNotIn(
                source_root.resolve(),
                paths.device_notification_credentials_file.resolve().parents,
            )

            if os.name != "nt":
                self.assertEqual(
                    stat.S_IMODE(
                        paths.device_credential_state_dir.stat().st_mode
                    ),
                    0o700,
                )

    def test_write_is_private_lkg_backed_and_unchanged_token_is_noop(self):
        with TemporaryDirectory() as temp_dir:
            state_file = self._state_file(Path(temp_dir))
            store = DeviceNotificationCredentialStore(state_file)
            first = store.set_token("key-1", "token-one", 100)

            self.assertEqual(
                first,
                {"token": "token-one", "updated_at": 100.0},
            )
            self.assertTrue(state_file.is_file())
            self.assertTrue(json_backup_path(state_file).is_file())

            if os.name != "nt":
                self.assertEqual(
                    stat.S_IMODE(state_file.parent.stat().st_mode),
                    0o700,
                )
                self.assertEqual(
                    stat.S_IMODE(state_file.stat().st_mode),
                    0o600,
                )
                self.assertEqual(
                    stat.S_IMODE(
                        json_backup_path(state_file).stat().st_mode
                    ),
                    0o600,
                )

            with patch(
                "server_core.device_credentials.write_json_atomic_sync"
            ) as writer:
                unchanged = store.set_token("key-1", "token-one", 200)

            writer.assert_not_called()
            self.assertEqual(unchanged["updated_at"], 100.0)

    def test_grouped_legacy_state_migrates_without_modifying_source(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            state_file = self._state_file(root)
            legacy_file = root / "state" / "server_state.json"
            self._write_json(
                legacy_file,
                {
                    "clients": {
                        "android_home": [
                            {
                                "deviceID": "home-1",
                                "fcm_token": "home-token",
                                "fcm_token_at": 110,
                            }
                        ],
                        "android_key": [
                            {
                                "deviceID": "key-1",
                                "fcm_token": "key-token",
                                "fcm_token_at": 120,
                            }
                        ],
                    }
                },
            )
            source_before = legacy_file.read_bytes()
            store = DeviceNotificationCredentialStore(state_file)

            migrated = store.migrate_legacy_server_state(legacy_file)

            self.assertEqual(migrated, 2)
            self.assertEqual(store.count(), 2)
            self.assertEqual(
                store.credential("key-1"),
                {"token": "key-token", "updated_at": 120.0},
            )
            self.assertEqual(legacy_file.read_bytes(), source_before)

    def test_newer_protected_record_wins_and_repeat_is_idempotent(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            state_file = self._state_file(root)
            legacy_file = root / "state" / "server_state.json"
            self._write_json(
                legacy_file,
                {
                    "clients": [
                        {
                            "deviceID": "key-1",
                            "fcm_token": "older-token",
                            "fcm_token_at": 100,
                        }
                    ]
                },
            )
            store = DeviceNotificationCredentialStore(state_file)
            store.set_token("key-1", "newer-token", 200)

            with patch(
                "server_core.device_credentials.write_json_atomic_sync"
            ) as writer:
                self.assertEqual(
                    store.migrate_legacy_server_state(legacy_file),
                    1,
                )
                self.assertEqual(
                    store.migrate_legacy_server_state(legacy_file),
                    1,
                )

            writer.assert_not_called()
            self.assertEqual(
                store.credential("key-1")["token"],
                "newer-token",
            )

    def test_migration_uses_latest_duplicate_legacy_record(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            state_file = self._state_file(root)
            legacy_file = root / "state" / "server_state.json"
            self._write_json(
                legacy_file,
                {
                    "clients": [
                        {
                            "deviceID": "key-1",
                            "fcm_token": "newer-token",
                            "fcm_token_at": 200,
                        },
                        {
                            "deviceID": "key-1",
                            "fcm_token": "older-token",
                            "fcm_token_at": 100,
                        },
                    ]
                },
            )
            store = DeviceNotificationCredentialStore(state_file)

            self.assertEqual(
                store.migrate_legacy_server_state(legacy_file),
                1,
            )
            self.assertEqual(
                store.credential("key-1")["token"],
                "newer-token",
            )

    def test_remove_persists_revocation(self):
        with TemporaryDirectory() as temp_dir:
            state_file = self._state_file(Path(temp_dir))
            store = DeviceNotificationCredentialStore(state_file)
            store.set_token("key-1", "token-one", 100)

            self.assertTrue(store.remove("key-1"))
            self.assertFalse(store.remove("key-1"))
            self.assertEqual(store.credential("key-1"), {})
            self.assertEqual(
                DeviceNotificationCredentialStore(state_file).count(),
                0,
            )

    def test_missing_primary_with_lkg_fails_closed(self):
        with TemporaryDirectory() as temp_dir:
            state_file = self._state_file(Path(temp_dir))
            backup = json_backup_path(state_file)
            self._write_json(backup, {"version": 1, "tokens": {}})

            with self.assertRaisesRegex(RuntimeError, "primary is missing"):
                DeviceNotificationCredentialStore(state_file)

    def test_invalid_protected_schema_fails_closed(self):
        with TemporaryDirectory() as temp_dir:
            state_file = self._state_file(Path(temp_dir))
            self._write_json(
                state_file,
                {"version": 2, "tokens": {}},
            )

            with self.assertRaisesRegex(RuntimeError, "unsupported"):
                DeviceNotificationCredentialStore(state_file)

    @unittest.skipIf(os.name == "nt", "Symbolic-link test requires POSIX")
    def test_symbolic_link_state_and_legacy_source_fail_closed(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            target = root / "target.json"
            self._write_json(target, {"version": 1, "tokens": {}})
            state_file = self._state_file(root)
            state_file.parent.mkdir(parents=True)
            state_file.symlink_to(target)

            with self.assertRaisesRegex(RuntimeError, "symbolic link"):
                DeviceNotificationCredentialStore(state_file)

            state_file.unlink()
            store = DeviceNotificationCredentialStore(state_file)
            legacy_target = root / "legacy-target.json"
            self._write_json(legacy_target, {"clients": []})
            legacy_link = root / "server_state.json"
            legacy_link.symlink_to(legacy_target)

            with self.assertRaisesRegex(RuntimeError, "symbolic link"):
                store.migrate_legacy_server_state(legacy_link)

    def test_invalid_legacy_token_stops_before_protected_write(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            state_file = self._state_file(root)
            legacy_file = root / "state" / "server_state.json"
            self._write_json(
                legacy_file,
                {
                    "clients": [
                        {
                            "deviceID": "key-1",
                            "fcm_token": "invalid token with spaces",
                            "fcm_token_at": 100,
                        }
                    ]
                },
            )
            store = DeviceNotificationCredentialStore(state_file)

            with self.assertRaisesRegex(RuntimeError, "is invalid"):
                store.migrate_legacy_server_state(legacy_file)

            self.assertFalse(state_file.exists())


if __name__ == "__main__":
    unittest.main()

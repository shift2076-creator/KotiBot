import json
import logging
import os
from pathlib import Path
import stat
from tempfile import TemporaryDirectory
import unittest

from server_core.io import (
    JsonStateInvalidError,
    JsonStateMissingError,
    JsonStateWriteBlockedError,
    flush_json_writes,
    json_backup_path,
    read_json,
    write_json_atomic,
    write_json_atomic_sync,
)

try:
    from subsystems.security.kotibot_security import (
        KotiBotSecurity,
        SecurityConfig,
    )
except ModuleNotFoundError as exc:
    if exc.name != "flask":
        raise

    KotiBotSecurity = None
    SecurityConfig = None


SOURCE_ROOT = Path(__file__).resolve().parents[1]


class StateBackupTests(unittest.TestCase):
    def test_first_write_creates_valid_private_lkg(self):
        with TemporaryDirectory() as temp_dir:
            state_file = Path(temp_dir) / "state.json"
            expected = {"version": 1, "items": {"one": True}}

            self.assertTrue(
                write_json_atomic_sync(state_file, expected)
            )

            backup_file = json_backup_path(state_file)
            self.assertEqual(backup_file.name, "state.lkg.json")
            self.assertEqual(read_json(state_file), expected)
            self.assertEqual(read_json(backup_file), expected)

            if os.name != "nt":
                self.assertEqual(
                    stat.S_IMODE(state_file.stat().st_mode),
                    0o600,
                )
                self.assertEqual(
                    stat.S_IMODE(backup_file.stat().st_mode),
                    0o600,
                )

    def test_changed_write_preserves_previous_valid_object(self):
        with TemporaryDirectory() as temp_dir:
            state_file = Path(temp_dir) / "state.json"
            previous = {"version": 1, "items": {"one": True}}
            current = {"version": 2, "items": {"two": True}}

            write_json_atomic_sync(state_file, previous)
            write_json_atomic_sync(state_file, current)

            self.assertEqual(read_json(state_file), current)
            self.assertEqual(
                read_json(json_backup_path(state_file)),
                previous,
            )

    def test_invalid_read_blocks_empty_overwrite(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            state_file = root / "state.json"
            previous = {"version": 1, "secret": "not-logged"}
            write_json_atomic_sync(state_file, previous)
            state_file.write_text(
                '{"secret": "not-logged"',
                encoding="utf-8",
            )

            with self.assertLogs(
                "kotibot.persistence",
                level=logging.WARNING,
            ) as captured:
                with self.assertRaises(JsonStateInvalidError):
                    read_json(state_file)

                with self.assertRaises(
                    JsonStateWriteBlockedError
                ) as raised:
                    write_json_atomic_sync(state_file, {})

            output = "\n".join(captured.output)
            self.assertEqual(raised.exception.filename, "state.json")
            self.assertEqual(raised.exception.reason, "invalid")
            self.assertNotIn(str(root), output)
            self.assertNotIn("not-logged", output)
            self.assertEqual(
                read_json(json_backup_path(state_file)),
                previous,
            )
            self.assertIn(
                '"secret": "not-logged"',
                state_file.read_text(encoding="utf-8"),
            )

    def test_flush_discards_write_when_primary_became_invalid(self):
        with TemporaryDirectory() as temp_dir:
            state_file = Path(temp_dir) / "state.json"
            previous = {"version": 1}
            write_json_atomic_sync(state_file, previous)
            state_file.write_text("{broken", encoding="utf-8")

            write_json_atomic(state_file, {})

            with self.assertLogs(
                "kotibot.persistence",
                level=logging.ERROR,
            ):
                self.assertEqual(flush_json_writes(), 0)

            self.assertEqual(
                state_file.read_text(encoding="utf-8"),
                "{broken",
            )
            self.assertEqual(
                read_json(json_backup_path(state_file)),
                previous,
            )

    def test_missing_primary_with_backup_blocks_reinitialization(self):
        with TemporaryDirectory() as temp_dir:
            state_file = Path(temp_dir) / "state.json"
            previous = {"version": 1}
            write_json_atomic_sync(state_file, previous)
            state_file.unlink()

            with self.assertRaises(JsonStateMissingError):
                read_json(state_file)

            with self.assertLogs(
                "kotibot.persistence",
                level=logging.ERROR,
            ):
                with self.assertRaises(JsonStateWriteBlockedError):
                    write_json_atomic_sync(state_file, {})

            self.assertFalse(state_file.exists())
            self.assertEqual(
                read_json(json_backup_path(state_file)),
                previous,
            )

    def test_valid_manual_repair_read_unblocks_future_writes(self):
        with TemporaryDirectory() as temp_dir:
            state_file = Path(temp_dir) / "state.json"
            write_json_atomic_sync(state_file, {"version": 1})
            state_file.write_text("{broken", encoding="utf-8")

            with self.assertLogs(
                "kotibot.persistence",
                level=logging.WARNING,
            ):
                with self.assertRaises(JsonStateInvalidError):
                    read_json(state_file)

            repaired = {"version": 2, "recovered": True}
            state_file.write_text(
                json.dumps(repaired),
                encoding="utf-8",
            )
            self.assertEqual(read_json(state_file), repaired)

            current = {"version": 3}
            write_json_atomic_sync(state_file, current)

            self.assertEqual(read_json(state_file), current)
            self.assertEqual(
                read_json(json_backup_path(state_file)),
                repaired,
            )

    @unittest.skipIf(
        KotiBotSecurity is None,
        "Flask is not installed in this development environment",
    )
    def test_security_state_uses_shared_lkg_writer(self):
        with TemporaryDirectory() as temp_dir:
            security = KotiBotSecurity(SecurityConfig(
                base_dir=Path(temp_dir),
                allowed_origins=(
                    ("https", "kotibot.example", 443),
                ),
            ))

            state_file = security.config.state_file
            self.assertEqual(
                read_json(json_backup_path(state_file)),
                read_json(state_file),
            )

    def test_tapo_config_uses_shared_synchronous_writer(self):
        source = (
            SOURCE_ROOT
            / "subsystems"
            / "client-tapo"
            / "tapo_admin_routes.py"
        ).read_text(encoding="utf-8")

        self.assertEqual(
            source.count("write_json_atomic_sync("),
            2,
        )
        self.assertNotIn("tapo_config_file.write_text", source)


if __name__ == "__main__":
    unittest.main()

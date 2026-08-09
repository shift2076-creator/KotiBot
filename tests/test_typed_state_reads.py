import json
import logging
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from server_core.io import (
    JsonStateInvalidError,
    JsonStateMissingError,
    JsonStateUnreadableError,
    read_json,
    read_json_object,
)


SOURCE_ROOT = Path(__file__).resolve().parents[1]


class TypedStateReadTests(unittest.TestCase):
    def test_missing_state_has_a_distinct_type_without_warning(self):
        with TemporaryDirectory() as temp_dir:
            missing = Path(temp_dir) / "missing_state.json"

            with self.assertNoLogs(
                "kotibot.persistence",
                level=logging.WARNING,
            ):
                with self.assertRaises(JsonStateMissingError) as raised:
                    read_json(missing)

            self.assertEqual(raised.exception.reason, "missing")
            self.assertEqual(
                raised.exception.filename,
                "missing_state.json",
            )

    def test_invalid_json_log_is_redacted(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            state_file = root / "invalid_state.json"
            sensitive_marker = "must-not-appear"
            state_file.write_text(
                '{"secret": "' + sensitive_marker + '"',
                encoding="utf-8",
            )

            with self.assertLogs(
                "kotibot.persistence",
                level=logging.WARNING,
            ) as captured:
                with self.assertRaises(JsonStateInvalidError):
                    read_json(state_file)

            output = "\n".join(captured.output)
            self.assertIn("file=invalid_state.json", output)
            self.assertIn("reason=invalid", output)
            self.assertNotIn(str(root), output)
            self.assertNotIn(sensitive_marker, output)

    def test_unreadable_state_has_a_distinct_type(self):
        with TemporaryDirectory() as temp_dir:
            state_directory = Path(temp_dir) / "state_directory.json"
            state_directory.mkdir()

            with self.assertLogs(
                "kotibot.persistence",
                level=logging.WARNING,
            ) as captured:
                with self.assertRaises(JsonStateUnreadableError):
                    read_json(state_directory)

            output = "\n".join(captured.output)
            self.assertIn("file=state_directory.json", output)
            self.assertIn("reason=unreadable", output)
            self.assertNotIn(str(Path(temp_dir)), output)

    def test_non_object_root_is_invalid_state(self):
        with TemporaryDirectory() as temp_dir:
            state_file = Path(temp_dir) / "list_state.json"
            state_file.write_text(
                json.dumps(["not", "an", "object"]),
                encoding="utf-8",
            )

            with self.assertLogs(
                "kotibot.persistence",
                level=logging.WARNING,
            ):
                with self.assertRaises(JsonStateInvalidError):
                    read_json_object(state_file)

    def test_state_readers_use_the_typed_object_reader(self):
        reader_paths = (
            "server_core/state.py",
            "subsystems/activities/activity_log.py",
            "subsystems/environment/environment_routes.py",
            "subsystems/matter/matter_runtime.py",
            "subsystems/client-tapo/tapo_routes.py",
            "subsystems/automations/automations_routes.py",
            "subsystems/security/kotibot_security.py",
        )

        for relative_path in reader_paths:
            source = (SOURCE_ROOT / relative_path).read_text(
                encoding="utf-8"
            )
            self.assertIn("read_json_object", source)
            self.assertNotIn("read_json(", source)


if __name__ == "__main__":
    unittest.main()

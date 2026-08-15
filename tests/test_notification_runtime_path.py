import os
from pathlib import Path
import stat
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from server_core.paths import (
    build_runtime_paths,
    prepare_runtime_directories,
)

try:
    from subsystems.notifications.kotibot_push import KotiBotPushQueue
except ModuleNotFoundError as exc:
    if not str(exc.name or "").startswith("google"):
        raise

    KotiBotPushQueue = None


SOURCE_ROOT = Path(__file__).resolve().parents[1]


class NotificationRuntimePathTests(unittest.TestCase):
    def test_notification_history_is_outside_source_tree(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_root = root / "source"
            data_root = root / "app-data"
            source_root.mkdir()

            with patch.dict(
                os.environ,
                {"KOTIBOT_DATA_DIR": str(data_root)},
                clear=True,
            ):
                paths = build_runtime_paths(source_root)

            self.assertEqual(
                paths.notification_queue_file,
                data_root
                / "logs"
                / "notifications"
                / "notification_queue.jsonl",
            )
            self.assertNotIn(
                source_root.resolve(),
                paths.notification_queue_file.resolve().parents,
            )

    def test_prepare_creates_private_notification_directory(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_root = root / "source"
            data_root = root / "app-data"
            source_root.mkdir()

            with patch.dict(
                os.environ,
                {"KOTIBOT_DATA_DIR": str(data_root)},
                clear=True,
            ):
                paths = build_runtime_paths(source_root)
                prepare_runtime_directories(paths)

            self.assertTrue(paths.notification_log_dir.is_dir())

            if os.name != "nt":
                self.assertEqual(
                    stat.S_IMODE(
                        paths.notification_log_dir.stat().st_mode
                    ),
                    0o700,
                )

    def test_server_wires_queue_without_moving_firebase_credential(self):
        source = (SOURCE_ROOT / "kotibot_server.py").read_text(
            encoding="utf-8"
        )

        self.assertIn(
            "NOTIFICATION_QUEUE_FILE = "
            "RUNTIME_PATHS.notification_queue_file",
            source,
        )
        self.assertIn(
            "LEGACY_NOTIFICATION_QUEUE_FILE = NOTIFICATIONS_DIR / "
            "'notification_queue.jsonl'",
            source,
        )
        self.assertIn(
            "queue_file=NOTIFICATION_QUEUE_FILE,\n"
            "    legacy_queue_file=LEGACY_NOTIFICATION_QUEUE_FILE,\n"
            "    service_account_file=FIREBASE_SERVICE_ACCOUNT_FILE,",
            source,
        )

    @unittest.skipIf(
        KotiBotPushQueue is None,
        "Google Auth is not installed in this development environment",
    )
    def test_legacy_history_migrates_once_with_private_modes(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            legacy_file = root / "source" / "notification_queue.jsonl"
            queue_file = root / "app-data" / "notification_queue.jsonl"
            legacy_file.parent.mkdir()
            expected = (
                b'{"event_type":"first","ts":1}\n'
                b'{"event_type":"second","ts":2}\n'
            )
            legacy_file.write_bytes(expected)

            queue = KotiBotPushQueue(
                root / "credentials",
                queue_file=queue_file,
                legacy_queue_file=legacy_file,
                service_account_file=root / "credentials" / "firebase.json",
            )

            self.assertEqual(queue_file.read_bytes(), expected)
            self.assertEqual(
                [item["event_type"] for item in queue.recent(10)],
                ["first", "second"],
            )

            if os.name != "nt":
                self.assertEqual(
                    stat.S_IMODE(queue_file.parent.stat().st_mode),
                    0o700,
                )
                self.assertEqual(
                    stat.S_IMODE(queue_file.stat().st_mode),
                    0o600,
                )

            legacy_file.write_bytes(
                b'{"event_type":"changed","ts":3}\n'
            )
            KotiBotPushQueue(
                root / "credentials",
                queue_file=queue_file,
                legacy_queue_file=legacy_file,
                service_account_file=root / "credentials" / "firebase.json",
            )
            self.assertEqual(queue_file.read_bytes(), expected)

    @unittest.skipIf(
        KotiBotPushQueue is None,
        "Google Auth is not installed in this development environment",
    )
    def test_append_uses_external_queue_and_private_mode(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            queue_file = root / "logs" / "notification_queue.jsonl"
            service_account_file = (
                root / "credentials" / "firebase.json"
            )
            queue = KotiBotPushQueue(
                root / "legacy",
                queue_file=queue_file,
                service_account_file=service_account_file,
            )

            queue.enqueue(
                event_type="test",
                title="Title",
                body="Body",
            )

            self.assertEqual(queue.queue_file, queue_file)
            self.assertEqual(
                queue.service_account_file,
                service_account_file,
            )
            self.assertEqual(queue.recent(1)[0]["event_type"], "test")

            if os.name != "nt":
                self.assertEqual(
                    stat.S_IMODE(queue_file.stat().st_mode),
                    0o600,
                )

    @unittest.skipIf(
        os.name == "nt" or KotiBotPushQueue is None,
        "Symbolic-link migration test requires POSIX and Google Auth",
    )
    def test_symbolic_link_destination_is_rejected(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            target = root / "outside.jsonl"
            target.write_text("", encoding="utf-8")
            queue_file = root / "logs" / "notification_queue.jsonl"
            queue_file.parent.mkdir()
            queue_file.symlink_to(target)

            with self.assertRaisesRegex(
                RuntimeError,
                "must not be a symbolic link",
            ):
                KotiBotPushQueue(
                    root / "credentials",
                    queue_file=queue_file,
                    service_account_file=root / "credentials" / "firebase.json",
                )

    @unittest.skipIf(
        os.name == "nt" or KotiBotPushQueue is None,
        "Symbolic-link migration test requires POSIX and Google Auth",
    )
    def test_symbolic_link_legacy_source_is_rejected(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            target = root / "outside.jsonl"
            target.write_text("", encoding="utf-8")
            legacy_file = root / "legacy" / "notification_queue.jsonl"
            legacy_file.parent.mkdir()
            legacy_file.symlink_to(target)

            with self.assertRaisesRegex(
                RuntimeError,
                "Legacy notification history must not be a symbolic link",
            ):
                KotiBotPushQueue(
                    root / "credentials",
                    queue_file=root / "logs" / "notification_queue.jsonl",
                    legacy_queue_file=legacy_file,
                    service_account_file=root / "credentials" / "firebase.json",
                )


if __name__ == "__main__":
    unittest.main()

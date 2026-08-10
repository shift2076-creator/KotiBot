from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

from subsystems.matter import matter_runtime
from subsystems.matter.matter_runtime import MatterRuntime


ROOT = Path(__file__).resolve().parents[1]


class _FakeStdin:
    def __init__(self):
        self.writes = []

    def write(self, value):
        self.writes.append(value)

    def flush(self):
        return None


class _ExitedProcess:
    def __init__(self):
        self.stdin = _FakeStdin()
        self.stdout = []
        self.returncode = 0

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        return self.returncode

    def terminate(self):
        self.returncode = 0

    def kill(self):
        self.returncode = -9


class MatterRuntimeStorageWiringTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.matter_dir = self.root / "matter-state"
        self.matter_dir.mkdir()
        self.controller_dir = self.root / "active" / "controller"
        self.controller_dir.mkdir(parents=True)
        (self.controller_dir / "identity.bin").write_bytes(b"identity")
        self.subscription_dir = self.root / "active" / "subscriptions"
        self.tick = 1000.0
        self.runtime = MatterRuntime(
            self.matter_dir,
            controller_storage_dir=self.controller_dir,
            subscription_storage_dir=self.subscription_dir,
            now_epoch=lambda: self.tick,
        )

    def tearDown(self):
        self.temporary_directory.cleanup()

    def test_controller_storage_is_explicit_and_not_derived(self):
        self.assertEqual(
            self.runtime.chip_tool_storage_dir(),
            self.controller_dir,
        )
        self.assertFalse(
            (self.matter_dir / "chip_tool_storage").exists()
        )

    def test_bootstrap_threads_both_explicit_paths_to_matter_runtime(self):
        server_source = (ROOT / "kotibot_server.py").read_text(
            encoding="utf-8"
        )
        subsystem_source = (
            ROOT / "server_core" / "subsystems.py"
        ).read_text(encoding="utf-8")
        route_source = (
            ROOT / "subsystems" / "matter" / "matter_routes.py"
        ).read_text(encoding="utf-8")

        self.assertIn(
            "MATTER_CONTROLLER_STORAGE_DIR = "
            "MATTER_DIR / 'chip_tool_storage'",
            server_source,
        )
        self.assertIn(
            "MATTER_DIR / 'chip_tool_subscription_storage'",
            server_source,
        )

        for key in (
            "matter_controller_storage_dir",
            "matter_subscription_storage_dir",
        ):
            self.assertIn(f"ctx['{key}']", subsystem_source)
            self.assertIn(f'context["{key}"]', route_source)

        self.assertIn(
            "controller_storage_dir=controller_storage_dir",
            route_source,
        )
        self.assertIn(
            "subscription_storage_dir=subscription_storage_dir",
            route_source,
        )

    def test_missing_controller_fails_without_reinitializing_identity(self):
        (self.controller_dir / "identity.bin").unlink()
        self.controller_dir.rmdir()

        with self.assertRaisesRegex(
            RuntimeError,
            "refusing to initialize replacement identity",
        ):
            self.runtime.chip_tool_storage_dir()

        self.assertFalse(self.controller_dir.exists())

    def test_subscription_storage_is_explicit_and_seeded_from_controller(self):
        storage_dir = (
            self.runtime
            .chip_tool_subscription_storage_dir("sensors_123")
        )

        self.assertEqual(
            storage_dir,
            self.subscription_dir / "sensors_123",
        )
        self.assertEqual(
            (storage_dir / "identity.bin").read_bytes(),
            b"identity",
        )
        self.assertFalse(
            (
                self.matter_dir
                / "chip_tool_subscription_storage"
            ).exists()
        )

    def test_subscription_storage_rejects_symlinked_root(self):
        alternate = self.root / "alternate-subscriptions"
        alternate.mkdir()
        self.subscription_dir.symlink_to(
            alternate,
            target_is_directory=True,
        )

        with self.assertRaisesRegex(
            RuntimeError,
            "subscription storage is unavailable",
        ):
            self.runtime.chip_tool_subscription_storage_dir("sensors_1")

    def test_subscription_worker_passes_explicit_storage_to_chip_tool(self):
        process = _ExitedProcess()

        with mock.patch.object(
            self.runtime,
            "_cached_matter_children",
            return_value=[{
                "endpoint": "1",
                "kinds": ["temperature"],
            }],
        ), mock.patch.object(
            matter_runtime.subprocess,
            "Popen",
            return_value=process,
        ) as popen:
            self.runtime.subscribe_sensor_states(
                {"node_id": "123"},
                lambda _event: None,
            )

        command = popen.call_args.args[0]
        storage_index = command.index("--storage-directory") + 1
        self.assertEqual(
            command[storage_index],
            str(self.subscription_dir / "sensors_123"),
        )

    def test_failed_recommission_uses_explicit_parent_and_restores_controller(self):
        self.subscription_dir.mkdir()
        (self.subscription_dir / "session.bin").write_bytes(b"session")

        with mock.patch.object(
            self.runtime,
            "_run_chip_tool",
            return_value={
                "ok": False,
                "returncode": 1,
            },
        ):
            result = self.runtime.recommission_node({
                "node_id": "123",
                "setup_code": "12345678",
            })

        self.assertFalse(result["ok"])
        self.assertTrue(result["rolled_back"])
        self.assertEqual(
            (self.controller_dir / "identity.bin").read_bytes(),
            b"identity",
        )
        self.assertEqual(
            (self.subscription_dir / "session.bin").read_bytes(),
            b"session",
        )
        self.assertEqual(
            list(self.controller_dir.parent.glob("chip_tool_storage.bad-*")),
            [],
        )
        self.assertEqual(
            list(self.matter_dir.glob("chip_tool_storage.bad-*")),
            [],
        )


if __name__ == "__main__":
    unittest.main()

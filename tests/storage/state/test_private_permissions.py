from __future__ import annotations

import os
from pathlib import Path
import stat
import subprocess
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from server_core.io import (
    json_backup_path,
    write_json_atomic_sync,
)
from server_core.private_paths import (
    PrivatePathPermissionError,
    ensure_private_directory,
    ensure_private_file,
    ensure_private_tree,
)
from subsystems.matter.matter_runtime import MatterRuntime
from tools.state003_verify_private_permissions import (
    inspect_private_roots,
    run,
    service_identity_status,
)


@unittest.skipIf(os.name == "nt", "POSIX permissions required")
class PrivatePathEnforcementTests(unittest.TestCase):
    def test_directory_file_and_tree_metadata_are_resecured(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "private"
            nested = root / "nested"
            nested.mkdir(parents=True, mode=0o755)
            path = nested / "state.bin"
            path.write_bytes(b"private")
            root.chmod(0o755)
            nested.chmod(0o755)
            path.chmod(0o644)

            ensure_private_tree(root)

            self.assertEqual(
                stat.S_IMODE(root.stat().st_mode),
                0o700,
            )
            self.assertEqual(
                stat.S_IMODE(nested.stat().st_mode),
                0o700,
            )
            self.assertEqual(
                stat.S_IMODE(path.stat().st_mode),
                0o600,
            )
            self.assertEqual(path.stat().st_uid, os.geteuid())
            self.assertEqual(path.stat().st_gid, os.getegid())

    def test_symbolic_link_is_rejected_without_following_it(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            target = root / "target"
            target.write_bytes(b"outside")
            target.chmod(0o644)
            link = root / "private"
            link.symlink_to(target)

            with self.assertRaises(PrivatePathPermissionError):
                ensure_private_file(link)

            self.assertEqual(
                stat.S_IMODE(target.stat().st_mode),
                0o644,
            )

    def test_permission_failure_is_value_free_and_visible(self):
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "private.bin"
            path.write_bytes(b"private")

            with patch(
                "server_core.private_paths.os.fchmod",
                side_effect=PermissionError("fixture path detail"),
            ):
                with self.assertRaises(
                    PrivatePathPermissionError
                ) as raised:
                    ensure_private_file(path)

            self.assertNotIn(
                "fixture path detail",
                str(raised.exception),
            )
            self.assertNotIn(str(path), str(raised.exception))


@unittest.skipIf(os.name == "nt", "POSIX permissions required")
class AtomicPrivateWriteTests(unittest.TestCase):
    def test_noop_write_resecures_parent_primary_and_backup(self):
        with TemporaryDirectory() as temp_dir:
            state_file = Path(temp_dir) / "state" / "state.json"
            data = {"version": 1}
            write_json_atomic_sync(state_file, data)
            backup_file = json_backup_path(state_file)
            state_file.parent.chmod(0o755)
            state_file.chmod(0o644)
            backup_file.chmod(0o644)

            self.assertFalse(
                write_json_atomic_sync(state_file, data)
            )

            self.assertEqual(
                stat.S_IMODE(state_file.parent.stat().st_mode),
                0o700,
            )

            for path in (state_file, backup_file):
                self.assertEqual(
                    stat.S_IMODE(path.stat().st_mode),
                    0o600,
                )

    def test_post_replace_enforcement_failure_leaves_private_primary(self):
        with TemporaryDirectory() as temp_dir:
            state_file = Path(temp_dir) / "state" / "state.json"

            with patch(
                "server_core.io.ensure_private_file",
                side_effect=PrivatePathPermissionError(
                    "fixture enforcement failure"
                ),
            ):
                with self.assertRaises(
                    PrivatePathPermissionError
                ):
                    write_json_atomic_sync(
                        state_file,
                        {"version": 1},
                    )

            self.assertTrue(state_file.is_file())
            self.assertEqual(
                stat.S_IMODE(state_file.stat().st_mode),
                0o600,
            )
            self.assertFalse(json_backup_path(state_file).exists())

    def test_parent_enforcement_failure_stops_before_file_creation(self):
        with TemporaryDirectory() as temp_dir:
            state_file = Path(temp_dir) / "state" / "state.json"

            with patch(
                "server_core.io.ensure_private_directory",
                side_effect=PrivatePathPermissionError(
                    "fixture enforcement failure"
                ),
            ):
                with self.assertRaises(
                    PrivatePathPermissionError
                ):
                    write_json_atomic_sync(
                        state_file,
                        {"version": 1},
                    )

            self.assertFalse(state_file.exists())


@unittest.skipIf(os.name == "nt", "POSIX permissions required")
class MatterPrivateStorageTests(unittest.TestCase):
    def test_chip_tool_mutation_is_resecured_before_return(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            matter_dir = root / "state"
            matter_dir.mkdir()
            controller_dir = root / "protected" / "controller"
            controller_dir.mkdir(parents=True)
            existing = controller_dir / "identity.bin"
            existing.write_bytes(b"identity")
            controller_dir.chmod(0o755)
            existing.chmod(0o644)
            runtime = MatterRuntime(
                matter_dir,
                controller_storage_dir=controller_dir,
                subscription_storage_dir=(
                    root / "protected" / "subscriptions"
                ),
                now_epoch=lambda: 1000.0,
            )

            def run_chip_tool(command, **kwargs):
                created = controller_dir / "session.bin"
                created.write_bytes(b"session")
                created.chmod(0o644)
                return subprocess.CompletedProcess(
                    command,
                    0,
                    stdout="",
                    stderr="",
                )

            with patch.object(
                runtime,
                "read_state",
                return_value={"chip_tool": "/usr/bin/chip-tool"},
            ), patch.object(
                runtime,
                "write_state",
            ), patch(
                "subsystems.matter.matter_runtime.subprocess.run",
                side_effect=run_chip_tool,
            ) as runner:
                result = runtime._run_chip_tool(["test"])

            self.assertTrue(result["ok"])
            self.assertEqual(
                runner.call_args.kwargs.get("umask"),
                0o077,
            )
            self.assertEqual(
                stat.S_IMODE(controller_dir.stat().st_mode),
                0o700,
            )

            for path in controller_dir.iterdir():
                self.assertEqual(
                    stat.S_IMODE(path.stat().st_mode),
                    0o600,
                )


@unittest.skipIf(os.name == "nt", "POSIX permissions required")
class State003VerifierTests(unittest.TestCase):
    def test_metadata_scan_reads_no_file_contents_and_counts_failures(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "private"
            root.mkdir(mode=0o700)
            private_file = root / "private.bin"
            private_file.write_bytes(b"must-not-be-read")
            private_file.chmod(0o600)
            wide_file = root / "wide.bin"
            wide_file.write_bytes(b"must-not-be-read")
            wide_file.chmod(0o644)
            link = root / "link"
            link.symlink_to(private_file)

            with patch.object(
                Path,
                "read_bytes",
                side_effect=AssertionError("contents read"),
            ), patch.object(
                Path,
                "read_text",
                side_effect=AssertionError("contents read"),
            ):
                result = inspect_private_roots(
                    (root,),
                    expected_uid=os.geteuid(),
                    expected_gid=os.getegid(),
                )

            self.assertEqual(result["missing_roots"], 0)
            self.assertEqual(result["symlinks"], 1)
            self.assertEqual(result["wrong_file_mode"], 1)
            self.assertEqual(result["inspection_errors"], 0)

    def test_service_identity_requires_configured_and_current_match(self):
        state = {
            "ActiveState": "active",
            "SubState": "running",
            "MainPID": "123",
            "User": "service-user",
            "Group": "service-group",
        }

        with patch(
            "tools.state003_verify_private_permissions.process_identity",
            return_value=(101, 202),
        ), patch(
            "tools.state003_verify_private_permissions.pwd.getpwnam",
            return_value=SimpleNamespace(pw_uid=101, pw_gid=303),
        ), patch(
            "tools.state003_verify_private_permissions.grp.getgrnam",
            return_value=SimpleNamespace(gr_gid=202),
        ), patch(
            "tools.state003_verify_private_permissions.os.geteuid",
            return_value=101,
        ), patch(
            "tools.state003_verify_private_permissions.os.getegid",
            return_value=202,
        ):
            configured, current, uid, gid = (
                service_identity_status(state)
            )

        self.assertTrue(configured)
        self.assertTrue(current)
        self.assertEqual((uid, gid), (101, 202))

    def test_head_mismatch_stops_before_service_or_runtime_inspection(self):
        args = SimpleNamespace(
            root=Path("/untrusted/source"),
            unit="kotibot.service",
            expected_head="expected",
        )

        with patch(
            "tools.state003_verify_private_permissions.exact_head",
            return_value="different",
        ), patch(
            "tools.state003_verify_private_permissions.service_state",
            side_effect=AssertionError("service inspected"),
        ):
            self.assertEqual(run(args), 2)


if __name__ == "__main__":
    unittest.main()

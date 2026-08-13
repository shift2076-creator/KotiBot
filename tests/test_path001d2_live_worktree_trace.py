from __future__ import annotations

import os
from pathlib import Path
import platform
from tempfile import TemporaryDirectory
import time
import unittest
from unittest.mock import patch

from tools.path001d2_live_worktree_trace import (
    IN_CLOSE_WRITE,
    IN_CREATE,
    SCENARIO_NAMES,
    RecursiveInotify,
    evaluate_gate,
    metadata_snapshot,
    parse_inotify_buffer,
    parse_systemctl_show,
    redacted_path_evidence,
    snapshot_delta,
    working_directory_class,
)


class Path001D2LiveWorktreeTraceTests(unittest.TestCase):
    def test_scenarios_cover_entire_roadmap_scope(self):
        self.assertEqual(
            set(SCENARIO_NAMES),
            {
                "startup-restart",
                "device-synchronization",
                "dashboard-mutations",
                "automations",
                "security-actions",
                "notifications",
                "recordings",
                "apk-serving-deployment",
                "matter-subscriptions-repair",
                "caches",
                "logs",
                "temporary-staging",
            },
        )

    def test_snapshot_delta_detects_add_remove_and_change(self):
        before = {
            "same": (1, 2, 3, 4, 5),
            "changed": (1, 2, 3, 4, 5),
            "removed": (1, 2, 3, 4, 5),
        }
        after = {
            "same": (1, 2, 3, 4, 5),
            "changed": (1, 2, 3, 4, 6),
            "added": (1, 2, 3, 4, 5),
        }

        self.assertEqual(
            snapshot_delta(before, after),
            {
                "added": 1,
                "removed": 1,
                "changed": 1,
            },
        )

    def test_metadata_snapshot_never_needs_file_contents(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            path = root / "secret-looking.json"
            path.write_text(
                '{"do-not-read":"private-value"}',
                encoding="utf-8",
            )

            with patch.object(
                Path,
                "read_text",
                side_effect=AssertionError(
                    "metadata snapshot must not read content"
                ),
            ):
                snapshot = metadata_snapshot(root)

        self.assertIn("secret-looking.json", snapshot)

    def test_parse_systemctl_show_keeps_only_property_values(self):
        parsed = parse_systemctl_show(
            "ActiveState=active\n"
            "SubState=running\n"
            "MainPID=123\n"
            "User=service-user\n"
        )

        self.assertEqual(parsed["ActiveState"], "active")
        self.assertEqual(parsed["SubState"], "running")
        self.assertEqual(parsed["MainPID"], "123")
        self.assertEqual(parsed["User"], "service-user")

    def test_working_directory_class_never_requires_rendering_path(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "source"
            root.mkdir()

            self.assertEqual(
                working_directory_class(
                    {"WorkingDirectory": str(root)},
                    root,
                ),
                "source-root",
            )
            self.assertEqual(
                working_directory_class(
                    {"WorkingDirectory": str(root / "nested")},
                    root,
                ),
                "inside-source",
            )
            self.assertEqual(
                working_directory_class(
                    {"WorkingDirectory": str(Path(temp_dir) / "other")},
                    root,
                ),
                "outside-source",
            )

    def test_untracked_evidence_redacts_dynamic_path_name(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            dynamic = (
                root
                / "subsystems"
                / "video"
                / "Living Room Camera secret.mp4"
            )

            evidence = redacted_path_evidence(
                dynamic,
                root,
                tracked=set(),
            )

        self.assertNotIn("Living Room", evidence)
        self.assertNotIn("Camera secret", evidence)
        self.assertIn("top=subsystems", evidence)
        self.assertIn("suffix=.mp4", evidence)
        self.assertIn("path-digest=", evidence)

    @unittest.skipIf(
        os.name == "nt",
        "symlink behavior differs on Windows",
    )
    def test_untracked_evidence_does_not_follow_symlink_target(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "source"
            outside = Path(temp_dir) / "outside-private-name"
            root.mkdir()
            outside.mkdir()
            link = root / "runtime-link"
            link.symlink_to(outside, target_is_directory=True)

            evidence = redacted_path_evidence(
                link,
                root,
                tracked=set(),
            )

        self.assertNotEqual(evidence, "outside-source")
        self.assertNotIn("outside-private-name", evidence)
        self.assertIn("path-digest=", evidence)

    def test_tracked_source_evidence_can_use_exact_repo_path(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            path = root / "server_core" / "io.py"

            evidence = redacted_path_evidence(
                path,
                root,
                tracked={"server_core/io.py"},
            )

        self.assertEqual(
            evidence,
            "tracked:server_core/io.py",
        )

    def test_gate_passes_only_with_full_coverage_and_clean_trace(self):
        passed, reasons = evaluate_gate(
            covered=set(SCENARIO_NAMES),
            skipped=set(),
            event_count=0,
            overflowed=False,
            delta={"added": 0, "removed": 0, "changed": 0},
            service_identity_ok=True,
            service_active_ok=True,
            restart_observed=True,
        )

        self.assertTrue(passed)
        self.assertEqual(reasons, [])

    def test_gate_blocks_any_worktree_mutation(self):
        passed, reasons = evaluate_gate(
            covered=set(SCENARIO_NAMES),
            skipped=set(),
            event_count=1,
            overflowed=False,
            delta={"added": 0, "removed": 0, "changed": 0},
            service_identity_ok=True,
            service_active_ok=True,
            restart_observed=True,
        )

        self.assertFalse(passed)
        self.assertIn("worktree-events=1", reasons)

    def test_gate_blocks_skipped_scenario(self):
        covered = set(SCENARIO_NAMES[:-1])
        skipped = {SCENARIO_NAMES[-1]}

        passed, reasons = evaluate_gate(
            covered=covered,
            skipped=skipped,
            event_count=0,
            overflowed=False,
            delta={"added": 0, "removed": 0, "changed": 0},
            service_identity_ok=True,
            service_active_ok=True,
            restart_observed=True,
        )

        self.assertFalse(passed)
        self.assertIn("scenario-skipped=1", reasons)

    def test_gate_blocks_snapshot_delta_and_overflow(self):
        passed, reasons = evaluate_gate(
            covered=set(SCENARIO_NAMES),
            skipped=set(),
            event_count=0,
            overflowed=True,
            delta={"added": 1, "removed": 0, "changed": 0},
            service_identity_ok=True,
            service_active_ok=True,
            restart_observed=True,
        )

        self.assertFalse(passed)
        self.assertIn("inotify-overflow=1", reasons)
        self.assertIn("snapshot-delta=1", reasons)

    def test_parse_inotify_buffer(self):
        import struct

        name = b"state.json\0"
        padded = name + (b"\0" * ((4 - len(name) % 4) % 4))
        event = struct.pack(
            "iIII",
            7,
            IN_CREATE | IN_CLOSE_WRITE,
            0,
            len(padded),
        ) + padded

        parsed = list(parse_inotify_buffer(event))

        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0][0], 7)
        self.assertEqual(parsed[0][3], "state.json")

    @unittest.skipUnless(
        platform.system() == "Linux",
        "Linux inotify integration test",
    )
    def test_recursive_inotify_detects_temp_file_write(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)

            with RecursiveInotify(root) as watcher:
                watcher.set_stage("test")
                path = root / "runtime.tmp"
                path.write_text("x", encoding="utf-8")

                deadline = time.monotonic() + 2

                while (
                    watcher.stage_count("test") == 0
                    and time.monotonic() < deadline
                ):
                    time.sleep(0.02)

                count = watcher.stage_count("test")

            self.assertGreater(count, 0)
            self.assertFalse(watcher.overflowed())

    @unittest.skipUnless(
        platform.system() == "Linux",
        "Linux inotify integration test",
    )
    def test_recursive_inotify_tracks_new_subdirectory(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)

            with RecursiveInotify(root) as watcher:
                watcher.set_stage("test")
                child = root / "new-dir"
                child.mkdir()
                time.sleep(0.05)
                (child / "item.tmp").write_text(
                    "x",
                    encoding="utf-8",
                )

                deadline = time.monotonic() + 2

                while (
                    watcher.stage_count("test") < 2
                    and time.monotonic() < deadline
                ):
                    time.sleep(0.02)

                count = watcher.stage_count("test")

            self.assertGreaterEqual(count, 2)
            self.assertFalse(watcher.overflowed())


if __name__ == "__main__":
    unittest.main()

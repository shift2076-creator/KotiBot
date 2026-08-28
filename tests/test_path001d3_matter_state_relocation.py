from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
TOOL_PATH = REPOSITORY_ROOT / "tools" / "path001d3_migrate_matter_state.py"


def load_tool():
    spec = importlib.util.spec_from_file_location(
        "path001d3_migrate_matter_state",
        TOOL_PATH,
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class Path001D3MatterStateRelocationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tool = load_tool()

    @staticmethod
    def _write_json(path: Path, document: dict, *, private: bool = False):
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        path.write_text(
            json.dumps(document, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        if private and os.name != "nt":
            path.parent.chmod(0o700)
            path.chmod(0o600)

    def _fixture(self, root: Path):
        source = root / "source"
        state = source / "subsystems" / "matter" / "matter_state.json"
        lkg = state.with_name("matter_state.lkg.json")
        self._write_json(state, {"nodes": {"one": {"alias": "private"}}})
        self._write_json(lkg, {"nodes": {"one": {"alias": "older"}}})
        (root / "run").mkdir(mode=0o700)
        handoff = root / "run" / "kotibot" / "handoff.json"
        data_root = root / "data"
        args = SimpleNamespace(
            service="kotibot",
            handoff_file=handoff,
        )
        snapshot = SimpleNamespace(
            process_user_id=os.geteuid(),
            data_root=data_root,
        )
        return source, state, lkg, data_root, args, snapshot

    def _preflight(self, source: Path, args, snapshot):
        with (
            patch.object(self.tool, "SOURCE_ROOT", source),
            patch.object(
                self.tool,
                "LEGACY_STATE_FILE",
                source / "subsystems" / "matter" / "matter_state.json",
            ),
            patch.object(self.tool, "require_operator_identity"),
            patch.object(
                self.tool,
                "inspect_active_service",
                return_value=snapshot,
            ),
        ):
            return self.tool.run_preflight(args)

    def _copy(self, source: Path, args):
        with (
            patch.object(self.tool, "SOURCE_ROOT", source),
            patch.object(
                self.tool,
                "LEGACY_STATE_FILE",
                source / "subsystems" / "matter" / "matter_state.json",
            ),
            patch.object(self.tool, "require_operator_identity"),
            patch.object(self.tool, "_require_service_inactive"),
        ):
            return self.tool.run_copy(args)

    def test_runtime_path_and_wiring_leave_source_tree(self):
        from server_core.paths import RuntimePaths

        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paths = RuntimePaths(
                source_root=root / "source",
                data_root=root / "data",
            ).validate()

            self.assertEqual(
                paths.matter_state_file,
                root / "data" / "state" / "matter" / "matter_state.json",
            )

        server_source = (REPOSITORY_ROOT / "kotibot_server.py").read_text()
        subsystem_source = (
            REPOSITORY_ROOT / "server_core" / "subsystems.py"
        ).read_text()
        routes_source = (
            REPOSITORY_ROOT
            / "subsystems"
            / "matter"
            / "matter_routes.py"
        ).read_text()

        self.assertIn(
            "MATTER_CONTROLLER_STATE_FILE = RUNTIME_PATHS.matter_state_file",
            server_source,
        )
        self.assertNotIn(
            "MATTER_CONTROLLER_STATE_FILE = MATTER_DIR / 'matter_state.json'",
            server_source,
        )
        self.assertNotIn("MATTER_DIR = SUBSYSTEMS_DIR / 'matter'", server_source)
        self.assertNotIn("'matter_dir': MATTER_DIR", server_source)
        self.assertIn(
            "'matter_state_file': matter_controller_state_file",
            subsystem_source,
        )
        self.assertNotIn("'matter_dir': matter_dir", subsystem_source)
        self.assertIn(
            'matter_state_file = Path(context["matter_state_file"])',
            routes_source,
        )
        self.assertIn("matter_dir = matter_state_file.parent", routes_source)

    def test_copy_preserves_primary_lkg_and_legacy_rollback(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source, state, lkg, data_root, args, snapshot = self._fixture(root)
            before = (state.read_bytes(), lkg.read_bytes())
            self._preflight(source, args, snapshot)

            if os.name != "nt":
                self.assertEqual(
                    stat.S_IMODE(args.handoff_file.stat().st_mode),
                    0o600,
                )

            result = self._copy(source, args)
            destination = data_root / "state" / "matter" / "matter_state.json"
            destination_lkg = destination.with_name("matter_state.lkg.json")

            self.assertEqual(result.created_files, 2)
            self.assertEqual(destination.read_bytes(), before[0])
            self.assertEqual(destination_lkg.read_bytes(), before[1])
            self.assertEqual(state.read_bytes(), before[0])
            self.assertEqual(lkg.read_bytes(), before[1])
            self.assertFalse(args.handoff_file.exists())

            if os.name != "nt":
                self.assertEqual(
                    stat.S_IMODE(destination.parent.stat().st_mode),
                    0o700,
                )
                self.assertEqual(
                    stat.S_IMODE(destination.stat().st_mode),
                    0o600,
                )
                self.assertEqual(
                    stat.S_IMODE(destination_lkg.stat().st_mode),
                    0o600,
                )

    def test_copy_is_idempotent_for_verified_destinations(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source, _, _, _, args, snapshot = self._fixture(root)
            self._preflight(source, args, snapshot)
            self._copy(source, args)
            self._preflight(source, args, snapshot)
            result = self._copy(source, args)

            self.assertEqual(result.created_files, 0)
            self.assertEqual(result.existing_files, 2)

    def test_conflicting_destination_stops_without_overwrite(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source, _, _, data_root, args, snapshot = self._fixture(root)
            destination = data_root / "state" / "matter" / "matter_state.json"
            self._write_json(destination, {"conflict": True}, private=True)
            before = destination.read_bytes()

            with self.assertRaisesRegex(
                self.tool.MigrationError,
                "differs",
            ):
                self._preflight(source, args, snapshot)

            self.assertEqual(destination.read_bytes(), before)

    def test_source_change_after_preflight_stops_copy(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source, state, _, _, args, snapshot = self._fixture(root)
            self._preflight(source, args, snapshot)
            self._write_json(state, {"nodes": {"changed": {}}})

            with self.assertRaisesRegex(
                self.tool.MigrationError,
                "changed after preflight",
            ):
                self._copy(source, args)

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks unavailable")
    def test_symlinked_legacy_state_is_rejected(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source, state, _, _, args, snapshot = self._fixture(root)
            outside = root / "outside.json"
            self._write_json(outside, {"nodes": {}})
            state.unlink()
            state.symlink_to(outside)

            with self.assertRaisesRegex(
                self.tool.MigrationError,
                "opened safely",
            ):
                self._preflight(source, args, snapshot)

    def test_invalid_json_is_rejected_without_exposing_content(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source, state, _, _, args, snapshot = self._fixture(root)
            private_value = "private-matter-value-never-print"
            state.write_text(private_value, encoding="utf-8")

            output = io.StringIO()
            with (
                patch.object(self.tool, "SOURCE_ROOT", source),
                patch.object(
                    self.tool,
                    "LEGACY_STATE_FILE",
                    state,
                ),
                patch.object(self.tool, "require_operator_identity"),
                patch.object(
                    self.tool,
                    "inspect_active_service",
                    return_value=snapshot,
                ),
                contextlib.redirect_stdout(output),
            ):
                status = self.tool.main([
                    "preflight",
                    "--handoff-file",
                    str(args.handoff_file),
                ])

            self.assertEqual(status, 1)
            self.assertNotIn(private_value, output.getvalue())


if __name__ == "__main__":
    unittest.main()

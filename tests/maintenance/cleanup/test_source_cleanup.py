from __future__ import annotations

import json
import os
from pathlib import Path
import stat
import subprocess
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from server_core.io import json_backup_path
from server_core.paths import RuntimePaths
from tools.path003_cleanup_source_residue import (
    CleanupError,
    ServiceContext,
    _inventory_blockers,
    _read_handoff,
    _remove_target,
    _target_fingerprint,
    _write_handoff,
    build_inventory,
    run,
    run_cleanup,
    runtime_paths_for_service,
    validate_external_recovery,
)


def _json(path: Path, value: dict | None = None, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value or {"fixture": True}) + "\n",
        encoding="utf-8",
    )
    path.chmod(mode)


def _private_directories(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    path.chmod(0o700)


def _context(root: Path, data_root: Path) -> ServiceContext:
    paths = RuntimePaths(
        source_root=root,
        data_root=data_root,
        cache_root=data_root / "cache",
        runtime_root=data_root / "runtime",
        temporary_root=data_root / "runtime/temp",
        package_root=data_root / "apks",
        media_root=data_root / "media",
    ).validate()
    return ServiceContext(
        process_id=123,
        user_id=os.geteuid(),
        group_id=os.getegid(),
        environment={"KOTIBOT_DATA_DIR": str(data_root)},
        paths=paths,
    )


class SourceResidueInventoryTests(unittest.TestCase):
    def test_inventory_classifies_exact_targets_and_preserves_developer_files(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            state = root / "subsystems/matter/matter_state.json"
            _json(state, mode=0o644)
            staging = state.with_name(f".{state.name}.12.34.tmp")
            _json(staging, mode=0o644)
            trash = root / ".Trash-1000/files/obsolete.bin"
            trash.parent.mkdir(parents=True)
            trash.write_bytes(b"obsolete")
            cache = root / "static/cache/preview.bin"
            cache.parent.mkdir(parents=True)
            cache.write_bytes(b"cache")
            ignored = (
                "subsystems/matter/matter_state.json",
                "subsystems/matter/.matter_state.json.12.34.tmp",
                ".Trash-1000/files/obsolete.bin",
                "static/cache/preview.bin",
                ".venv/lib/package/metadata.json",
                "temp/operator-fixture.json",
                "tests/fixtures/example.json",
                "static/img/favicons/FLASK_ROUTES.txt",
            )

            with patch(
                "tools.path003_cleanup_source_residue._ignored_paths",
                return_value=ignored,
            ):
                inventory = build_inventory(root)

            self.assertEqual(inventory.state_files, 2)
            self.assertEqual(inventory.replaceable_files, 1)
            self.assertEqual(inventory.trash_files, 1)
            self.assertEqual(inventory.preserved_ignored, 4)
            self.assertEqual(inventory.unknown_ignored, 0)
            self.assertEqual(inventory.blocked_credentials, 0)
            self.assertEqual(inventory.matter_storage_roots, 0)

    def test_unknown_and_credential_residue_block_cleanup(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            credential = root / ".env"
            credential.write_text("SECRET=fixture\n", encoding="utf-8")

            with patch(
                "tools.path003_cleanup_source_residue._ignored_paths",
                return_value=(".env", "misc/unknown.json"),
            ):
                inventory = build_inventory(root)

            self.assertGreaterEqual(inventory.blocked_credentials, 1)
            self.assertEqual(inventory.unknown_ignored, 1)
            self.assertEqual(
                inventory.unknown_ignored_paths,
                ("misc/unknown.json",),
            )
            self.assertGreater(_inventory_blockers(inventory), 0)

    def test_matter_storage_is_never_deleted_by_generic_cleanup(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            identity = root / "subsystems/matter/chip_tool_storage/identity.bin"
            identity.parent.mkdir(parents=True)
            identity.write_bytes(b"identity")

            with patch(
                "tools.path003_cleanup_source_residue._ignored_paths",
                return_value=(
                    "subsystems/matter/chip_tool_storage/identity.bin",
                ),
            ):
                inventory = build_inventory(root)

            self.assertGreater(inventory.matter_storage_roots, 0)
            self.assertNotIn(identity.parent, inventory.targets)
            self.assertGreater(_inventory_blockers(inventory), 0)

    def test_tracked_file_under_runtime_named_root_blocks_cleanup(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            tracked = root / "static/cache/deliberate.bin"
            tracked.parent.mkdir(parents=True)
            tracked.write_bytes(b"source asset")
            subprocess.run(
                ("git", "init", "-q"),
                cwd=root,
                check=True,
            )
            subprocess.run(
                ("git", "add", "-f", "static/cache/deliberate.bin"),
                cwd=root,
                check=True,
            )

            with patch(
                "tools.path003_cleanup_source_residue._ignored_paths",
                return_value=(),
            ):
                inventory = build_inventory(root)

            self.assertEqual(inventory.tracked_target_files, 1)
            self.assertGreater(_inventory_blockers(inventory), 0)
            self.assertTrue(tracked.exists())

    def test_fingerprint_detects_metadata_change_without_reading_contents(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / ".Trash-1000/files/archive.zip"
            target.parent.mkdir(parents=True)
            target.write_bytes(b"one")
            before = _target_fingerprint(root, (root / ".Trash-1000",))
            target.write_bytes(b"changed")
            after = _target_fingerprint(root, (root / ".Trash-1000",))
            self.assertNotEqual(before, after)


class ExternalRecoveryValidationTests(unittest.TestCase):
    def test_ordinary_state_requires_private_primary_and_lkg(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary) / "source"
            data = Path(temporary) / "data"
            root.mkdir()
            context = _context(root, data)
            source = root / "subsystems/matter/matter_state.json"
            _json(source, {"legacy": True}, mode=0o644)
            destination = context.paths.matter_state_file
            _private_directories(destination.parent)
            _json(destination, {"current": True})
            _json(json_backup_path(destination), {"recovery": True})

            with patch(
                "tools.path003_cleanup_source_residue._ignored_paths",
                return_value=("subsystems/matter/matter_state.json",),
            ):
                inventory = build_inventory(root)

            validation = validate_external_recovery(root, inventory, context)
            self.assertEqual(validation.external_documents, 2)
            self.assertTrue(validation.runtime_contents_read)

    def test_missing_external_lkg_blocks_state_cleanup(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary) / "source"
            data = Path(temporary) / "data"
            root.mkdir()
            context = _context(root, data)
            source = root / "subsystems/matter/matter_state.json"
            _json(source, mode=0o644)
            destination = context.paths.matter_state_file
            _private_directories(destination.parent)
            _json(destination)

            with patch(
                "tools.path003_cleanup_source_residue._ignored_paths",
                return_value=("subsystems/matter/matter_state.json",),
            ):
                inventory = build_inventory(root)

            with self.assertRaises(CleanupError):
                validate_external_recovery(root, inventory, context)

            self.assertTrue(source.exists())

    def test_recording_requires_content_and_mtime_match(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary) / "source"
            data = Path(temporary) / "data"
            source = root / "subsystems/video/videos/camera/clip.mp4"
            destination = data / "media/camera/clip.mp4"
            source.parent.mkdir(parents=True)
            destination.parent.mkdir(parents=True)
            source.write_bytes(b"recording")
            destination.write_bytes(b"recording")
            source_time = source.stat().st_mtime_ns
            os.utime(destination, ns=(source_time, source_time))

            for directory in (
                data / "media",
                data / "media/camera",
            ):
                directory.chmod(0o700)

            destination.chmod(0o600)
            context = _context(root, data)

            with patch(
                "tools.path003_cleanup_source_residue._ignored_paths",
                return_value=(
                    "subsystems/video/videos/camera/clip.mp4",
                ),
            ):
                inventory = build_inventory(root)

            validation = validate_external_recovery(root, inventory, context)
            self.assertEqual(validation.recording_copies, 1)
            destination.write_bytes(b"different")

            with self.assertRaises(CleanupError):
                validate_external_recovery(root, inventory, context)

    def test_legacy_history_must_be_retained_in_external_rotation(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary) / "source"
            data = Path(temporary) / "data"
            source = root / "subsystems/security/security_audit.jsonl"
            source.parent.mkdir(parents=True)
            source.write_bytes(b'{"legacy":true}\n')
            context = _context(root, data)
            destination = context.paths.security_audit_file
            _private_directories(destination.parent)
            destination.write_bytes(b'{"current":true}\n')
            destination.chmod(0o600)
            rotation = destination.with_name(destination.name + ".1")
            rotation.write_bytes(b'{"legacy":true}\n')
            rotation.chmod(0o600)

            with patch(
                "tools.path003_cleanup_source_residue._ignored_paths",
                return_value=(
                    "subsystems/security/security_audit.jsonl",
                ),
            ):
                inventory = build_inventory(root)

            validation = validate_external_recovery(root, inventory, context)
            self.assertEqual(validation.external_histories, 2)


class CleanupMutationTests(unittest.TestCase):
    def test_remove_target_deletes_only_validated_tree(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / ".Trash-1000"
            child = target / "files/obsolete.bin"
            child.parent.mkdir(parents=True)
            child.write_bytes(b"obsolete")
            files, directories, byte_count = _remove_target(root, target)
            self.assertEqual(files, 1)
            self.assertEqual(directories, 2)
            self.assertEqual(byte_count, len(b"obsolete"))
            self.assertFalse(target.exists())

    def test_symlink_blocks_without_touching_target(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            outside = root / "outside.bin"
            outside.write_bytes(b"keep")
            trash = root / ".Trash-1000"
            trash.mkdir()
            (trash / "link").symlink_to(outside)

            with self.assertRaises(CleanupError):
                _remove_target(root, trash)

            self.assertEqual(outside.read_bytes(), b"keep")
            self.assertTrue(trash.exists())

    def test_cleanup_rechecks_fingerprint_and_deletes_state(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary) / "source"
            data = Path(temporary) / "data"
            root.mkdir()
            source = root / "subsystems/matter/matter_state.json"
            _json(source, mode=0o644)
            context = _context(root, data)
            destination = context.paths.matter_state_file
            _private_directories(destination.parent)
            _json(destination)
            _json(json_backup_path(destination))
            handoff_path = Path(temporary) / "handoff.json"

            with patch(
                "tools.path003_cleanup_source_residue._ignored_paths",
                return_value=("subsystems/matter/matter_state.json",),
            ):
                inventory = build_inventory(root)

            handoff = {
                "schema": 1,
                "service": "fixture",
                "source_root": str(root),
                "created_at": __import__("time").time_ns() // 1_000_000_000,
                "service_uid": os.geteuid(),
                "service_gid": os.getegid(),
                "environment": {"KOTIBOT_DATA_DIR": str(data)},
                "state_labels": list(inventory.state_labels),
                "target_count": inventory.target_count,
                "fingerprint": inventory.fingerprint,
                "cleanup_complete": False,
            }
            _write_handoff(handoff_path, handoff)
            args = SimpleNamespace(service="fixture")

            ignored_results = [
                ("subsystems/matter/matter_state.json",),
                (),
            ]

            with (
                patch(
                    "tools.path003_cleanup_source_residue.require_service_inactive",
                ),
                patch(
                    "tools.path003_cleanup_source_residue._ignored_paths",
                    side_effect=ignored_results,
                ),
            ):
                result = run_cleanup(args, root, handoff_path)

            self.assertEqual(result, 0)
            self.assertFalse(source.exists())
            completed = _read_handoff(
                handoff_path,
                root=root,
                service="fixture",
            )
            self.assertTrue(completed["cleanup_complete"])

    def test_authoritative_head_mismatch_stops_before_service_access(self):
        args = SimpleNamespace(
            root=Path.cwd(),
            expected_head="expected",
            action="preflight",
            service="kotibot",
            handoff_file=None,
        )

        with (
            patch(
                "tools.path003_cleanup_source_residue.exact_head",
                return_value="different",
            ),
            patch(
                "tools.path003_cleanup_source_residue.active_service_context",
            ) as service,
        ):
            result = run(args)

        self.assertEqual(result, 2)
        service.assert_not_called()


@unittest.skipIf(os.name != "posix", "POSIX metadata required")
class HandoffTests(unittest.TestCase):
    def test_handoff_is_private_and_round_trips(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary) / "source"
            root.mkdir()
            path = Path(temporary) / "handoff.json"
            document = {
                "schema": 1,
                "service": "fixture",
                "source_root": str(root),
                "created_at": __import__("time").time_ns() // 1_000_000_000,
                "service_uid": os.geteuid(),
                "service_gid": os.getegid(),
            }
            _write_handoff(path, document)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            loaded = _read_handoff(path, root=root, service="fixture")
            self.assertEqual(loaded["schema"], 1)

    def test_service_paths_reject_source_containment(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            environment = {"KOTIBOT_DATA_DIR": str(root / "runtime")}

            with self.assertRaises(RuntimeError):
                runtime_paths_for_service(
                    root,
                    process_user_id=os.geteuid(),
                    environment=environment,
                )


if __name__ == "__main__":
    unittest.main()

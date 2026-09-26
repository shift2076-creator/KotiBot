"""Preservation and failure gates for PATH-003's private history copies."""
import contextlib
import io
import os
from pathlib import Path
import stat
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tests.maintenance.cleanup.test_source_cleanup import _context, _private_directories
from tools import path003_cleanup_source_residue as cleanup
from tools.path003_history_archive import archive_path, create_archive, read_archive


@unittest.skipIf(os.name != 'posix', 'Linux operator tool')
class HistoryArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.options = dict(uid=os.geteuid(), gid=os.getegid(), limit=1024)
        self.target = self.base / 'history.path003-legacy'

    def test_create_private_copy_repeat_noop_and_refuse_replacement(self):
        self.assertTrue(create_archive(self.target, b'legacy\n', **self.options))
        self.assertEqual(stat.S_IMODE(self.target.stat().st_mode), 0o600)
        before = self.target.stat().st_mtime_ns
        self.assertFalse(create_archive(self.target, b'legacy\n', **self.options))
        self.assertEqual(self.target.stat().st_mtime_ns, before)
        with self.assertRaises(ValueError):
            create_archive(self.target, b'different\n', **self.options)
        self.assertEqual(self.target.read_bytes(), b'legacy\n')
        self.assertEqual(list(self.base.iterdir()), [self.target])

    def test_reject_symlink_without_touching_destination(self):
        original = self.base / 'original'
        original.write_bytes(b'keep')
        self.target.symlink_to(original)
        with self.assertRaises(ValueError):
            create_archive(self.target, b'legacy', **self.options)
        self.assertEqual(original.read_bytes(), b'keep')

    def test_reject_symlink_parent(self):
        link = self.base / 'link'
        link.symlink_to(self.base, target_is_directory=True)
        with self.assertRaises(ValueError):
            create_archive(link / self.target.name, b'legacy', **self.options)
        self.assertFalse(self.target.exists())

    def test_reject_bad_permissions_owner_and_size(self):
        create_archive(self.target, b'legacy', **self.options)
        for mode, uid, limit in [(0o644, os.geteuid(), 1024),
                                 (0o600, os.geteuid() + 1, 1024),
                                 (0o600, os.geteuid(), 2)]:
            with self.subTest(mode=mode, uid=uid, limit=limit):
                self.target.chmod(mode)
                with self.assertRaises(ValueError):
                    read_archive(self.target, uid=uid, gid=os.getegid(), limit=limit)
        self.base.chmod(0o755)
        with self.assertRaises(ValueError):
            read_archive(self.target, **self.options)

    def test_reject_fifo_without_waiting_for_writer(self):
        os.mkfifo(self.target, 0o600)
        with self.assertRaises(ValueError):
            read_archive(self.target, **self.options)

    def test_refuse_concurrent_archive_without_overwriting_it(self):
        real_link = os.link
        def concurrent_link(source, destination, **kwargs):
            Path(destination).write_bytes(b'other writer')
            return real_link(source, destination, **kwargs)
        with patch('tools.path003_history_archive.os.link', side_effect=concurrent_link):
            with self.assertRaises(FileExistsError):
                create_archive(self.target, b'legacy', **self.options)
        self.assertEqual(self.target.read_bytes(), b'other writer')
        self.assertEqual(list(self.base.iterdir()), [self.target])


@unittest.skipIf(os.name != 'posix', 'Linux operator tool')
class HistoryCleanupIntegrationTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.root = self.base / 'source'
        self.root.mkdir()
        self.context = _context(self.root, self.base / 'data')
        for name, attribute in [('CACHE', 'cache_root'), ('RUNTIME', 'runtime_root'),
                                ('TEMP', 'temporary_root'), ('PACKAGE', 'package_root'),
                                ('MEDIA', 'media_root')]:
            self.context.environment[f'KOTIBOT_{name}_DIR'] = str(getattr(self.context.paths, attribute))
        self.sources = []
        self.archives = []
        self.live = []
        for label, relative, attribute, rotated in cleanup.HISTORY_TARGETS:
            destination = Path(getattr(self.context.paths, attribute))
            _private_directories(destination.parent)
            destination.write_bytes(b'{"current":true}\n')
            destination.chmod(0o600)
            self.live.append(destination)
            for suffix in (('', '.1') if rotated else ('',)):
                source = self.root / (str(relative) + suffix)
                source.parent.mkdir(parents=True, exist_ok=True)
                source.write_bytes((label + suffix + '\n').encode())
                self.sources.append(source)
                self.archives.append(archive_path(destination.with_name(source.name)))
        self.args = SimpleNamespace(service='fixture', details=False)
        self.handoff = self.base / 'handoff.json'
        self.addCleanup(patch.stopall)
        patch('tools.path003_cleanup_source_residue.active_service_context',
              return_value=self.context).start()
        patch('tools.path003_cleanup_source_residue.require_service_inactive').start()
        patch('tools.path003_cleanup_source_residue._ignored_paths',
              side_effect=lambda root: tuple(str(p.relative_to(root)) for p in self.sources if p.exists())).start()
        self.output = io.StringIO()
        self.capture = contextlib.redirect_stdout(self.output)
        self.capture.__enter__()
        self.addCleanup(self.capture.__exit__, None, None, None)

    def test_three_archives_then_preflight_cleanup_and_post_restart(self):
        source_bytes = [p.read_bytes() for p in self.sources]
        with self.assertRaisesRegex(cleanup.CleanupError, 'does not preserve'):
            cleanup.run_preflight(self.args, self.root, self.handoff)
        self.assertFalse(self.handoff.exists())
        self.assertEqual(cleanup.run_archive_history(self.args, self.root), 0)
        self.assertEqual(cleanup.run_archive_history(self.args, self.root), 0)
        self.assertEqual([p.read_bytes() for p in self.sources], source_bytes)
        self.assertEqual([p.read_bytes() for p in self.archives], source_bytes)
        self.assertEqual(cleanup.run_preflight(self.args, self.root, self.handoff), 0)
        self.assertEqual(cleanup.run_cleanup(self.args, self.root, self.handoff), 0)
        self.assertTrue(all(not p.exists() for p in self.sources))
        self.assertEqual([p.read_bytes() for p in self.archives], source_bytes)
        self.assertTrue(all(p.read_bytes() == b'{"current":true}\n' for p in self.live))
        self.assertEqual(cleanup.run_verify(self.args, self.root, self.handoff), 0)
        self.assertFalse(self.handoff.exists())

    def test_tampered_archive_after_preflight_blocks_every_deletion(self):
        cleanup.run_archive_history(self.args, self.root)
        cleanup.run_preflight(self.args, self.root, self.handoff)
        self.archives[-1].write_bytes(b'changed')
        with self.assertRaisesRegex(cleanup.CleanupError, 'does not preserve'):
            cleanup.run_cleanup(self.args, self.root, self.handoff)
        self.assertTrue(all(p.exists() for p in self.sources))

    def test_archive_survives_live_history_rotation_or_removal(self):
        cleanup.run_archive_history(self.args, self.root)
        for path in self.live:
            path.unlink()
        self.assertEqual(cleanup.run_preflight(self.args, self.root, self.handoff), 0)

    def test_source_change_during_copy_blocks_success(self):
        real_create = create_archive
        def change_source(*args, **kwargs):
            result = real_create(*args, **kwargs)
            self.sources[0].write_bytes(b'changed')
            return result
        with patch('tools.path003_cleanup_source_residue.create_archive', side_effect=change_source):
            with self.assertRaisesRegex(cleanup.CleanupError, 'changed during archiving'):
                cleanup.run_archive_history(self.args, self.root)
        self.assertTrue(all(p.exists() for p in self.sources))

    def test_wrong_source_head_stops_archive_before_service_access(self):
        args = SimpleNamespace(root=self.root, expected_head='expected', action='archive-history')
        with patch('tools.path003_cleanup_source_residue.exact_head', return_value='different'):
            self.assertEqual(cleanup.run(args), 2)
        cleanup.active_service_context.assert_not_called()
        self.assertTrue(all(not p.exists() for p in self.archives))

import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'deploy/installer'))
import install


def make(folder, names):
    for name in names:
        (folder / name).mkdir()
        (folder / name / 'users-data').write_text('x')


class PruneOldBackupsTests(unittest.TestCase):
    def test_keeps_only_the_newest_installer_backups(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            names = [f'202611{day:02d}T120000Z-{day:06x}' for day in range(1, 9)]
            make(folder, names)
            removed = install.prune_old_backups(folder, keep=3)
            self.assertEqual(removed, 5)
            self.assertEqual(sorted(p.name for p in folder.iterdir()), names[-3:])

    def test_leaves_files_links_and_hand_made_backups_alone(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as elsewhere:
            folder = Path(tmp)
            make(folder, ['20261101T120000Z-aaaaaa', '20261102T120000Z-bbbbbb', 'hand-made-backup'])
            (folder / 'users-pre-retire.sqlite3').write_text('db')
            (folder / '20261001T120000Z-cccccc').symlink_to(elsewhere)
            Path(elsewhere, 'precious').write_text('keep me')
            self.assertEqual(install.prune_old_backups(folder, keep=1), 1)
            names = sorted(p.name for p in folder.iterdir())
            self.assertEqual(names, ['20261001T120000Z-cccccc', '20261102T120000Z-bbbbbb',
                                     'hand-made-backup', 'users-pre-retire.sqlite3'])
            self.assertEqual(Path(elsewhere, 'precious').read_text(), 'keep me')

    def test_fewer_backups_than_the_limit_removes_nothing_and_a_missing_folder_is_fine(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            make(folder, ['20261101T120000Z-aaaaaa'])
            self.assertEqual(install.prune_old_backups(folder, keep=5), 0)
            self.assertEqual(install.prune_old_backups(folder / 'missing'), 0)

    def test_the_default_keeps_five(self):
        self.assertEqual(install.BACKUPS_KEPT, 5)


class MigrationStepTests(unittest.TestCase):
    def test_the_migration_has_a_longer_limit_than_the_default_stage_time(self):
        self.assertGreaterEqual(install.MIGRATION_TIMEOUT, 600)
        source = (ROOT / 'deploy/installer/install.py').read_text()
        migrate = source[source.index("'migrate', '--noinput']"):]
        self.assertIn('timeout=MIGRATION_TIMEOUT', migrate[:120])

    def test_the_backup_is_flushed_to_disk_before_the_database_is_touched(self):
        source = (ROOT / 'deploy/installer/install.py').read_text()
        copy = source.index("backup_data(data_dir, backup / 'users-data')")
        flush = source.index('os.sync()')
        migrate = source.index("'migrate', '--noinput']")
        self.assertLess(copy, flush)
        self.assertLess(flush, migrate)


class DataBackupTests(unittest.TestCase):
    def make_data(self, root):
        data = root / 'data'
        (data / 'client-packages').mkdir(parents=True)
        (data / 'client-packages/big.bin').write_text('big')
        (data / 'users.sqlite3').write_text('database')
        (data / 'users.sqlite3-wal').write_text('wal')
        (data / 'sub').mkdir()
        (data / 'sub/note.txt').write_text('note')
        return data

    def test_the_backup_leaves_out_client_packages_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = self.make_data(Path(tmp))
            install.backup_data(data, Path(tmp) / 'copy')
            names = sorted(p.relative_to(Path(tmp) / 'copy').as_posix() for p in (Path(tmp) / 'copy').rglob('*'))
            self.assertEqual(names, ['sub', 'sub/note.txt', 'users.sqlite3', 'users.sqlite3-wal'])

    def test_restore_brings_back_the_saved_files_and_keeps_client_packages(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = self.make_data(Path(tmp))
            install.backup_data(data, Path(tmp) / 'copy')
            (data / 'users.sqlite3').write_text('damaged')
            (data / 'sub/note.txt').write_text('damaged')
            (data / 'sub/extra.txt').write_text('new')
            (data / 'stray.txt').write_text('left alone')
            install.restore_data(Path(tmp) / 'copy', data)
            self.assertEqual((data / 'users.sqlite3').read_text(), 'database')
            self.assertEqual((data / 'sub/note.txt').read_text(), 'note')
            self.assertFalse((data / 'sub/extra.txt').exists())
            self.assertEqual((data / 'client-packages/big.bin').read_text(), 'big')
            self.assertEqual((data / 'stray.txt').read_text(), 'left alone')


class HeartbeatTests(unittest.TestCase):
    def test_a_slow_step_prints_plain_lines_and_a_final_line(self):
        import contextlib
        import io
        import time
        with unittest.mock.patch.object(install, 'HEARTBEAT_SECONDS', 0.05):
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                with install.heartbeat('Backing up'):
                    time.sleep(0.3)
        lines = out.getvalue().splitlines()
        self.assertEqual(lines[0], 'Backing up…')
        self.assertGreaterEqual(sum('still working' in line for line in lines), 2)
        self.assertTrue(lines[-1].startswith('Backing up: done in '))
        self.assertNotIn('\r', out.getvalue())

    def test_the_stage_timer_prints_new_lines_not_carriage_returns(self):
        source = (ROOT / 'deploy/installer/install.py').read_text()
        timer = source[source.index('def show_timer'):source.index('@contextlib.contextmanager')]
        self.assertNotIn("'\\r'", timer)
        self.assertIn('say(', timer)
        self.assertEqual(install.HEARTBEAT_SECONDS, 10)


if __name__ == '__main__':
    unittest.main()

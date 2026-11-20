import sys
import tempfile
import unittest
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


if __name__ == '__main__':
    unittest.main()

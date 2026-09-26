from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from tools.a06_configure_stream_capacity import (
    CONTENTS, NAME, install_dropin, remove_dropin, validate_command,
)


class StreamCapacityDeploymentTests(unittest.TestCase):
    def test_only_verified_worker_count_is_accepted(self):
        validate_command('{ argv[]=/venv/bin/python -m waitress --listen=0.0.0.0:5000 --threads=12 wsgi:application ; }')
        for command in (
            'python -m waitress wsgi:application',
            'python -m waitress --threads=4 wsgi:application',
            'python -m waitress --threads=120 wsgi:application',
            'python -m waitress --threads=12 --threads=4 wsgi:application',
            'python kotibot_server.py --threads=12',
        ):
            with self.subTest(command=command), self.assertRaises(ValueError):
                validate_command(command)

    def test_new_dropin_is_repeatable_and_removable(self):
        with TemporaryDirectory() as temporary:
            directory = Path(temporary) / 'service.d'
            self.assertTrue(install_dropin(directory))
            self.assertEqual((directory / NAME).read_bytes(), CONTENTS)
            self.assertFalse(install_dropin(directory))
            remove_dropin(directory)
            self.assertFalse((directory / NAME).exists())

    def test_unrelated_config_and_modified_dropin_are_preserved(self):
        with TemporaryDirectory() as temporary:
            directory = Path(temporary)
            unrelated = directory / 'credentials.conf'
            unrelated.write_text('fixture')
            target = directory / NAME
            target.write_text('local change')
            with self.assertRaises(ValueError):
                install_dropin(directory)
            with self.assertRaises(ValueError):
                remove_dropin(directory)
            self.assertEqual(target.read_text(), 'local change')
            self.assertEqual(unrelated.read_text(), 'fixture')

    def test_symlink_target_is_refused(self):
        with TemporaryDirectory() as temporary:
            directory = Path(temporary)
            other = directory / 'other'
            other.write_text('fixture')
            (directory / NAME).symlink_to(other)
            with self.assertRaises(ValueError):
                install_dropin(directory)
            with self.assertRaises(ValueError):
                remove_dropin(directory)
            self.assertEqual(other.read_text(), 'fixture')

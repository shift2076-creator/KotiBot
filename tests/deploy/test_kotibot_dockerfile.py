import unittest
from pathlib import Path

STACK = Path(__file__).resolve().parents[2] / 'deploy/stack/kotibot'


class DockerfileCacheTests(unittest.TestCase):
    def test_packages_are_installed_before_the_pinned_source_is_fetched(self):
        text = (STACK / 'Dockerfile').read_text()
        packages = text.index('pip install --no-cache-dir -r /tmp/requirements.txt')
        source = text.index('git clone')
        self.assertLess(packages, source)
        # The package layer must not mention the commit, or every pin reinstalls everything.
        layer = text[text.index('COPY requirements.txt'):text.index('ARG KOTIBOT_REF')]
        self.assertNotIn('KOTIBOT_REF', layer)

    def test_the_commit_argument_is_declared_after_the_slow_layers(self):
        text = (STACK / 'Dockerfile').read_text()
        arg = text.index('ARG KOTIBOT_REF')
        self.assertGreater(arg, text.index('apt-get install'))
        self.assertGreater(arg, text.index('pip install --no-cache-dir -r'))

    def test_source_step_checks_the_requirements_copy(self):
        self.assertIn('cmp /opt/kotibot/requirements.txt /tmp/requirements.txt', (STACK / 'Dockerfile').read_text())

    def test_requirements_copy_exists_and_pins_every_line(self):
        lines = [l for l in (STACK / 'requirements.txt').read_text().splitlines() if l.strip()]
        self.assertTrue(lines)
        self.assertTrue(all('==' in l for l in lines))


if __name__ == '__main__':
    unittest.main()

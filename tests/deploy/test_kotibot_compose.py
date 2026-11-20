import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / 'deploy'
spec = importlib.util.spec_from_file_location('update_compose', ROOT / 'stack/kotibot/update_compose.py')
update_compose = importlib.util.module_from_spec(spec)
spec.loader.exec_module(update_compose)

OLD = """services:
  portal:
    image: x
    volumes:
    - /a:/a
  kotibot:
    image: pivault-kotibot:fae56d35acf3
    environment:
      TZ: America/New_York
      KOTIBOT_JELLYFIN_URL: http://172.18.0.1:8096
    volumes:
    - /srv/pi-server/config/kotibot/data:/data
    - /run/dbus/system_bus_socket:/run/dbus/system_bus_socket
  cloudflared:
    image: c
    environment:
      TZ: x
    volumes:
    - /z:/z
"""


class UpdateComposeTests(unittest.TestCase):
    def test_adds_what_is_missing_to_the_kotibot_service_only(self):
        new = update_compose.update(OLD, '78bd1c602b79')
        block = new[new.index('  kotibot:'):new.index('  cloudflared:')]
        self.assertIn('image: pivault-kotibot:78bd1c602b79', block)
        for key, value in update_compose.ENVIRONMENT:
            self.assertIn('      %s: %s' % (key, value), block)
        for mount in update_compose.VOLUMES:
            self.assertIn('    - ' + mount, block)
        self.assertIn('/run/dbus/system_bus_socket', block)
        self.assertEqual(new[new.index('  cloudflared:'):], OLD[OLD.index('  cloudflared:'):])
        self.assertEqual(new[:new.index('  kotibot:')], OLD[:OLD.index('  kotibot:')])

    def test_the_repo_compose_copy_carries_everything_the_script_adds(self):
        import yaml
        service = yaml.safe_load((ROOT / 'stack/docker-compose.yml').read_text())['services']['kotibot']
        for key, value in update_compose.ENVIRONMENT:
            self.assertEqual(service['environment'].get(key), value, key)
        for mount in update_compose.VOLUMES:
            self.assertIn(mount, service['volumes'])

    def test_running_it_twice_changes_nothing_more(self):
        once = update_compose.update(OLD, '78bd1c602b79')
        self.assertEqual(update_compose.update(once, '78bd1c602b79'), once)

    def test_existing_entries_are_not_duplicated(self):
        partial = OLD.replace('    volumes:\n    - /srv/pi-server/config/kotibot/data:/data',
                              '    volumes:\n    - /srv/pi-server/config/kotibot/data:/data\n    - /srv/pi-server/config/site:/site')
        new = update_compose.update(partial, '78bd1c602b79')
        self.assertEqual(new.count('/srv/pi-server/config/site:/site'), 1)

    def test_bad_tag_or_missing_service_stops(self):
        with self.assertRaises(SystemExit):
            update_compose.update(OLD, 'latest')
        with self.assertRaises(SystemExit):
            update_compose.update('services:\n  a:\n    image: x\n', '78bd1c602b79')

    def test_repo_compose_file_already_matches(self):
        text = (ROOT / 'stack/docker-compose.yml').read_text()
        tag = text[text.index('pivault-kotibot:') + 16:][:12]
        self.assertEqual(update_compose.update(text, tag), text)


if __name__ == '__main__':
    unittest.main()

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'deploy/installer'))
import configuration as config

# The live Caddyfile on the Pi as of 2026-11-20, with the .lan names added by hand.
LIVE = (Path(__file__).parent / 'fixtures/live-caddyfile-20261120.txt').read_text()


def sites(text):
    """Map each top-level site header to its body (a header with names in any order counts once)."""
    found = {}
    for match in re.finditer(r'^(\S[^\n]*?) \{\n(.*?)^\}', text, re.M | re.S):
        header = tuple(sorted(name.strip() for name in match.group(1).split(',')))
        found[header] = match.group(2)
    return found


class AppSiteNameTests(unittest.TestCase):
    def test_rebuilding_the_app_sites_keeps_every_site_and_name_of_the_live_file(self):
        before, after = sites(LIVE), sites(config.apps_caddyfile(LIVE))
        self.assertEqual(set(before), set(after))
        for header, body in before.items():
            self.assertEqual(body, after[header], header)

    def test_every_extra_name_is_for_a_port_the_installer_builds(self):
        self.assertTrue(set(config.APP_EXTRA_NAMES) <= config.APP_PORTS)

    def test_the_tls_check_ignores_the_order_of_names(self):
        def tls(names):
            return {'automation': {'policies': [{'subjects': names, 'issuers': [{'module': 'internal'}]}]}}

        first = tls(['paperless.kotibot.lan', 'kotibot.lan', '192.168.4.90', 'wiki.kotibot.lan'])
        second = tls(['wiki.kotibot.lan', '192.168.4.90', 'paperless.kotibot.lan'])
        self.assertEqual(config._tls_without_names(first, config.NAMED_HOSTS),
                         config._tls_without_names(second, config.NAMED_HOSTS))

    def test_the_tls_check_still_notices_a_missing_name(self):
        def tls(names):
            return {'automation': {'policies': [{'subjects': names}]}}

        self.assertNotEqual(config._tls_without_names(tls(['a.kotibot.lan', 'b.kotibot.lan']), config.NAMED_HOSTS),
                            config._tls_without_names(tls(['a.kotibot.lan']), config.NAMED_HOSTS))


if __name__ == '__main__':
    unittest.main()

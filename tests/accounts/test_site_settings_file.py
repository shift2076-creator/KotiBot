import json
import os
import tempfile
from pathlib import Path
from unittest import mock

from django.test import TestCase

from portal import site_settings_file
from portal.models import SiteSettings


class SiteSettingsFileTests(TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.target = Path(self.folder.name, 'site-settings.json')
        patcher = mock.patch.dict(os.environ, {site_settings_file.ENVIRONMENT: str(self.target)})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_defaults_when_the_file_does_not_exist(self):
        self.assertFalse(SiteSettings.is_offline())
        self.assertEqual(SiteSettings.network_roles(), ('off', 'internet'))
        self.assertFalse(self.target.exists())

    def test_saves_go_to_the_file_and_not_the_database(self):
        SiteSettings.set_offline(True)
        SiteSettings.set_network_roles('local', 'internet')
        self.assertEqual(json.loads(self.target.read_text()),
                         {'ethernet_role': 'local', 'offline_mode': True, 'wifi_role': 'internet'})
        self.assertFalse(SiteSettings.objects.exists())
        self.assertTrue(SiteSettings.is_offline())
        self.assertEqual(SiteSettings.network_roles(), ('local', 'internet'))
        self.assertEqual(self.target.stat().st_mode & 0o777, 0o644)

    def test_a_write_by_kotibot_is_seen_by_the_portal(self):
        self.target.write_text(json.dumps({'offline_mode': True, 'ethernet_role': 'internet', 'wifi_role': 'local'}))
        self.assertTrue(SiteSettings.is_offline())
        self.assertEqual(SiteSettings.network_roles(), ('internet', 'local'))

    def test_a_damaged_file_means_the_defaults(self):
        self.target.write_text('{not json')
        self.assertFalse(SiteSettings.is_offline())
        self.target.write_text(json.dumps({'ethernet_role': 'bogus', 'wifi_role': 'internet'}))
        self.assertEqual(SiteSettings.network_roles(), ('off', 'internet'))

    def test_no_temporary_file_is_left_behind(self):
        SiteSettings.set_offline(True)
        self.assertEqual([p.name for p in Path(self.folder.name).iterdir()], ['site-settings.json'])

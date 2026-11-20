import json
import tempfile
from pathlib import Path
from django.test import TestCase, override_settings
from portal.models import Notification
from portal.notifications import ingest, notify


class OutboxTests(TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        override = override_settings(PIVAULT_NOTIFICATION_ROOT=self.directory.name)
        override.enable(); self.addCleanup(override.disable)

    def test_notify_writes_the_shared_outbox_for_kotibot_and_not_the_portal_database(self):
        notify('users', 'k1', 'Title', 'Body', level='error', details={'accounts': []})
        notify('users', 'k1', 'Title', 'Body', level='error')  # same incident: still one file
        files = list((Path(self.directory.name) / 'inbox').glob('*.json'))
        self.assertEqual(len(files), 1)
        data = json.loads(files[0].read_text())
        self.assertEqual((data['version'], data['source'], data['level'], files[0].name), (1, 'users', 'error', data['id'] + '.json'))
        self.assertEqual(oct(files[0].stat().st_mode & 0o777), '0o644')
        self.assertFalse(Notification.objects.exists())

    def test_the_portal_no_longer_imports_the_inbox(self):
        notify('users', 'k2', 'Title', 'Body')
        ingest()
        self.assertEqual(len(list((Path(self.directory.name) / 'inbox').glob('*.json'))), 1)
        self.assertFalse(Notification.objects.exists())

    def test_an_unwritable_outbox_does_not_break_the_caller(self):
        with override_settings(PIVAULT_NOTIFICATION_ROOT='/proc/not-writable'), self.assertLogs('portal.notifications', level='WARNING'):
            value = notify('clients', 'k3', 'Title', 'Body')
        self.assertEqual(value['source'], 'clients')

import json
import os
import tempfile
from pathlib import Path
from unittest import mock

from django.test import TestCase

from portal import network_requests
from portal.models import SiteSettings, User


class NetworkRequestFilesTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username='admin-id', email='admin@example.com',
            password='Existing-good-password-928!', display_name='Owner', role='admin')
        self.person = User.objects.create_user(username='person', email='person@example.com',
            password='Existing-good-password-928!', display_name='Person', role='user')
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.path = Path(self.dir.name)

    def enabled(self):
        return mock.patch.dict(os.environ, {'PIVAULT_NETWORK_DIR': self.dir.name})

    def test_without_the_folder_nothing_is_written_and_the_page_says_not_applied(self):
        self.client.force_login(self.admin)
        with mock.patch.dict(os.environ, clear=False):
            os.environ.pop('PIVAULT_NETWORK_DIR', None)
            self.client.post('/network', {'ethernet': 'local', 'wifi': 'off', 'internet_jobs': 'running'}, secure=True)
            page = self.client.get('/network?saved=1', secure=True).content.decode()
        self.assertIn('not applied to the network yet', page)
        self.assertEqual(list(self.path.iterdir()), [])

    def test_saving_drops_a_request_for_the_helper(self):
        self.client.force_login(self.admin)
        with self.enabled():
            self.client.post('/network', {'ethernet': 'local', 'wifi': 'off', 'internet_jobs': 'running'}, secure=True)
            page = self.client.get('/network?saved=1', secure=True).content.decode()
        self.assertEqual(json.loads((self.path / 'request.json').read_text()), {'ethernet': 'local', 'wifi': 'off'})
        self.assertIn('being applied', page)

    def test_a_refused_pair_writes_no_request(self):
        self.client.force_login(self.admin)
        with self.enabled():
            self.client.post('/network', {'ethernet': 'internet', 'wifi': 'internet', 'internet_jobs': 'running'}, secure=True)
        self.assertFalse((self.path / 'request.json').exists())

    def test_a_waiting_change_shows_the_countdown_and_a_confirm_button(self):
        (self.path / 'state.json').write_text(json.dumps({'current': ['local', 'off'],
            'change': {'previous': ['off', 'internet'], 'requested': ['local', 'off'], 'deadline': 1100, 'confirmed': False}}))
        self.client.force_login(self.admin)
        with self.enabled(), mock.patch('portal.views.time.time', return_value=1040):
            page = self.client.get('/network', secure=True).content.decode()
        self.assertIn('within 60 seconds', page)
        self.assertIn('action="/network/confirm"', page)

    def test_confirm_writes_the_marker_for_admins_only(self):
        with self.enabled():
            self.client.force_login(self.person)
            self.assertEqual(self.client.post('/network/confirm', secure=True).status_code, 403)
            self.assertFalse((self.path / 'confirm').exists())
            self.client.force_login(self.admin)
            self.client.post('/network/confirm', secure=True)
        self.assertTrue((self.path / 'confirm').exists())

    def test_confirm_needs_a_post_and_a_signed_in_user(self):
        self.client.logout()
        self.assertRedirects(self.client.post('/network/confirm', secure=True), '/users/sign-in', fetch_redirect_response=False)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get('/network/confirm', secure=True).status_code, 405)

    def test_a_reverted_change_puts_the_saved_roles_back_and_says_so(self):
        SiteSettings.set_network_roles('local', 'off')
        (self.path / 'result.json').write_text(json.dumps({'status': 'reverted', 'roles': ['off', 'internet']}))
        (self.path / 'state.json').write_text(json.dumps({'current': ['off', 'internet'], 'change': None}))
        self.client.force_login(self.admin)
        with self.enabled():
            page = self.client.get('/network', secure=True).content.decode()
        self.assertEqual(SiteSettings.network_roles(), ('off', 'internet'))
        self.assertIn('previous setup was restored', page)

    def test_a_failed_change_shows_the_helpers_reason(self):
        (self.path / 'result.json').write_text(json.dumps({'status': 'failed', 'error': 'the new setup did not come up'}))
        self.client.force_login(self.admin)
        with self.enabled():
            page = self.client.get('/network', secure=True).content.decode()
        self.assertIn('the new setup did not come up', page)

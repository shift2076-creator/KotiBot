from django.test import Client, TestCase

from portal.models import SiteSettings, User


class NetworkPageTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username='admin-id', email='admin@example.com',
            password='Existing-good-password-928!', display_name='Owner', role='admin')
        self.person = User.objects.create_user(username='person', email='person@example.com',
            password='Existing-good-password-928!', display_name='Person', role='user')

    def test_anonymous_visitors_are_sent_to_sign_in(self):
        response = self.client.get('/network', secure=True)
        self.assertRedirects(response, '/users/sign-in', fetch_redirect_response=False)

    def test_other_users_cannot_see_the_page_or_change_it(self):
        self.client.force_login(self.person)
        self.assertEqual(self.client.get('/network', secure=True).status_code, 403)
        self.assertEqual(self.client.post('/network', {'ethernet': 'local', 'wifi': 'local'}, secure=True).status_code, 403)
        self.assertEqual(SiteSettings.network_roles(), ('off', 'internet'))

    def test_admin_sees_today_as_the_default_selection(self):
        self.client.force_login(self.admin)
        page = self.client.get('/network', secure=True).content.decode()
        self.assertIn('name="ethernet" value="off" checked', page)
        self.assertIn('name="wifi" value="internet" checked', page)
        self.assertIn('name="internet_jobs" value="running" checked', page)

    def test_saving_records_both_ports_and_the_job_switch_then_says_not_applied(self):
        self.client.force_login(self.admin)
        response = self.client.post('/network', {'ethernet': 'local', 'wifi': 'internet', 'internet_jobs': 'paused'}, secure=True)
        self.assertRedirects(response, '/network?saved=1', fetch_redirect_response=False)
        self.assertEqual(SiteSettings.network_roles(), ('local', 'internet'))
        self.assertTrue(SiteSettings.is_offline())
        page = self.client.get('/network?saved=1', secure=True).content.decode()
        self.assertIn('Saved. Port settings are not applied to the network yet.', page)
        self.assertIn('name="internet_jobs" value="paused" checked', page)

    def test_an_invalid_pair_is_refused_and_nothing_is_saved(self):
        self.client.force_login(self.admin)
        SiteSettings.set_offline(False)
        response = self.client.post('/network', {'ethernet': 'internet', 'wifi': 'internet', 'internet_jobs': 'paused'}, secure=True)
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, 'Only one port can connect to the internet.', status_code=400)
        self.assertEqual(SiteSettings.network_roles(), ('off', 'internet'))
        self.assertFalse(SiteSettings.is_offline())

    def test_wifi_is_never_offered_as_local_and_a_forged_post_is_refused(self):
        self.client.force_login(self.admin)
        page = self.client.get('/network', secure=True).content.decode()
        self.assertIn('name="ethernet" value="local"', page)
        self.assertNotIn('name="wifi" value="local"', page)
        response = self.client.post('/network', {'ethernet': 'internet', 'wifi': 'local', 'internet_jobs': 'running'}, secure=True)
        self.assertContains(response, 'cable only', status_code=400)
        self.assertEqual(SiteSettings.network_roles(), ('off', 'internet'))

    def test_a_post_without_the_csrf_token_is_refused(self):
        guarded = Client(enforce_csrf_checks=True)
        guarded.force_login(self.admin)
        response = guarded.post('/network', {'ethernet': 'local', 'wifi': 'local'}, secure=True)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(SiteSettings.network_roles(), ('off', 'internet'))

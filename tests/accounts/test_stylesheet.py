"""Every portal page uses one shell and one stylesheet, served without a session."""
from pathlib import Path

from django.test import TestCase

def portal_folder():
    # In the image the tests sit in portal/tests; in the repository they are in tests/accounts.
    here = Path(__file__).resolve()
    return here.parents[1] if (here.parents[1] / 'templates').is_dir() else here.parents[2] / 'subsystems/accounts/portal'


TEMPLATES = portal_folder() / 'templates'
LINK = '<link rel="stylesheet" href="/users/pivault.css">'
PAGES = ('users', 'certificate', 'complete', 'devices', 'network', 'notifications', 'vault-repair')


class SharedStylesheetTests(TestCase):
    def test_stylesheet_is_served_publicly_as_css(self):
        response = self.client.get('/users/pivault.css', secure=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/css; charset=utf-8')
        self.assertIn(b'--pv-accent', response.content)

    def test_the_base_template_loads_the_shared_stylesheet_and_brand(self):
        text = (TEMPLATES / 'base.html').read_text()
        self.assertEqual(text.count(LINK), 1)
        self.assertIn('class="pv-brand"', text)
        self.assertIn('class="pv-mark"', text)

    def test_pages_extend_the_base_and_keep_no_styles_of_their_own(self):
        for name in PAGES:
            text = (TEMPLATES / f'{name}.html').read_text()
            self.assertTrue(text.startswith('{% extends "base.html" %}'), name)
            self.assertNotIn('<style', text, name)
            self.assertNotIn('<main', text, name)
            self.assertNotIn(LINK, text, name)

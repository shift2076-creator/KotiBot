import itertools
import unittest

from django.test import TestCase

from portal import network_roles
from portal.models import SiteSettings


class NetworkRoleRuleTests(unittest.TestCase):
    def test_every_pair_of_roles_is_refused_or_accepted_by_the_rule(self):
        refused = {('internet', 'internet'), ('off', 'off'), ('off', 'local'), ('internet', 'local'), ('local', 'local')}
        for ethernet, wifi in itertools.product(network_roles.ROLES, repeat=2):
            reason = network_roles.validate(ethernet, wifi)
            if (ethernet, wifi) in refused:
                self.assertIsNotNone(reason, (ethernet, wifi))
            else:
                self.assertIsNone(reason, (ethernet, wifi))

    def test_only_one_port_may_be_the_internet_uplink(self):
        self.assertIn('Only one port', network_roles.validate('internet', 'internet'))

    def test_the_pi_must_keep_one_port_on_or_it_cannot_be_reached(self):
        self.assertIn('Turn on at least one port', network_roles.validate('off', 'off'))

    def test_unknown_roles_are_refused(self):
        self.assertIsNotNone(network_roles.validate('bridge', 'internet'))
        self.assertIsNotNone(network_roles.validate('off', ''))

    def test_direct_mode_is_cable_only(self):
        self.assertIsNone(network_roles.validate('local', 'off'))
        self.assertIsNone(network_roles.validate('local', 'internet'))
        self.assertIn('cable only', network_roles.validate('internet', 'local'))
        self.assertIsNotNone(network_roles.validate('local', 'local'))


class NetworkRoleStorageTests(TestCase):
    def test_before_anything_is_saved_the_pi_keeps_todays_network(self):
        self.assertEqual(SiteSettings.network_roles(), ('off', 'internet'))

    def test_saved_roles_are_read_back_and_leave_offline_mode_alone(self):
        SiteSettings.set_offline(True)
        SiteSettings.set_network_roles('local', 'local')
        self.assertEqual(SiteSettings.network_roles(), ('local', 'local'))
        self.assertTrue(SiteSettings.is_offline())

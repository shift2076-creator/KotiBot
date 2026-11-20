import itertools
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'subsystems', 'network'))
import network_plan as np


def flat(steps):
    return [' '.join(step.argv) for step in steps]


class SupportedPairTests(unittest.TestCase):
    def test_only_these_pairs_can_be_applied(self):
        applicable = {('off', 'internet'), ('internet', 'off'), ('local', 'internet'), ('local', 'off')}
        for pair in itertools.product(np.ROLES, repeat=2):
            self.assertEqual(np.unsupported(*pair) is None, pair in applicable, pair)

    def test_wifi_never_serves_clients(self):
        for ethernet in np.ROLES:
            self.assertIn('cable only', np.unsupported(ethernet, 'local'))

    def test_unknown_roles_and_both_off_are_refused(self):
        self.assertIsNotNone(np.unsupported('bridge', 'internet'))
        self.assertIn('cannot be reached', np.unsupported('off', 'off'))
        self.assertIn('Only one port', np.unsupported('internet', 'internet'))

    def test_a_refused_pair_produces_no_commands(self):
        result = np.plan('off', 'off')
        self.assertTrue(result.error)
        self.assertEqual((result.up, result.down, result.firewall, result.files), ([], [], [], {}))


class PlanTests(unittest.TestCase):
    def test_todays_network_keeps_wifi_up_and_never_touches_it_down(self):
        result = np.plan('off', 'internet')
        self.assertIsNone(result.error)
        self.assertFalse([c for c in flat(result.up + result.down) if 'device disconnect wlan0' in c])
        self.assertIn('nmcli connection modify id Room 237 connection.autoconnect yes', flat(result.up))
        self.assertIsNone(result.files[np.SHARED_DNSMASQ_FILE])

    def test_the_stock_wired_profile_never_stays_on_autoconnect(self):
        for pair in (('off', 'internet'), ('internet', 'off'), ('local', 'internet'), ('local', 'off')):
            commands = flat(np.plan(*pair).up + np.plan(*pair).down)
            self.assertIn('nmcli connection modify id Wired connection 1 connection.autoconnect no', commands, pair)

    def test_cable_uplink_comes_up_before_wifi_is_dropped(self):
        result = np.plan('internet', 'off')
        self.assertTrue(any('add type ethernet ifname eth0 con-name ' + np.PROFILE_UPLINK in c for c in flat(result.up)))
        self.assertTrue(any('device disconnect wlan0' in c for c in flat(result.down)))
        self.assertFalse(any('device disconnect wlan0' in c for c in flat(result.up)))
        self.assertEqual(result.firewall, [])

    def test_local_cable_with_wifi_uplink_shares_only_dhcp_and_blocks_forwarding(self):
        result = np.plan('local', 'internet')
        added = [c for c in flat(result.up) if 'con-name ' + np.PROFILE_LOCAL in c and ' add ' in c]
        self.assertEqual(len(added), 1)
        self.assertIn('ipv4.method shared', added[0])
        self.assertIn('ipv4.addresses 10.42.0.1/24', added[0])
        content = result.files[np.SHARED_DNSMASQ_FILE]
        self.assertIn('port=0', content)
        self.assertIn('dhcp-option=6,192.168.4.90', content)
        inserted = [c for c in flat(result.firewall) if c.startswith('iptables -I DOCKER-USER')]
        self.assertEqual(sorted(inserted), ['iptables -I DOCKER-USER -i eth0 -o wlan0 -j DROP',
                                            'iptables -I DOCKER-USER -i wlan0 -o eth0 -j DROP'])
        for step in result.firewall:
            self.assertEqual(step.tolerate, step.argv[1] == '-D')

    def test_direct_mode_has_no_uplink_to_block_and_drops_wifi_last(self):
        result = np.plan('local', 'off')
        self.assertEqual(result.firewall, [])
        self.assertTrue(any('device disconnect wlan0' in c for c in flat(result.down)))
        self.assertFalse(any('wlan0' in c for c in flat(result.up)))

    def test_identity_address_is_added_only_when_asked(self):
        self.assertFalse([c for c in flat(np.plan('off', 'internet').up) if np.PROFILE_IDENTITY in c])
        up = flat(np.plan('off', 'internet', identity=True).up)
        added = [c for c in up if ' add type dummy ' in c]
        self.assertEqual(len(added), 1)
        self.assertIn('ifname kb-id0', added[0])
        self.assertIn('ipv4.addresses 192.168.4.90/32', added[0])
        self.assertIn('connection.autoconnect yes', added[0])
        self.assertEqual(up.index(added[0]), 1)  # after the tolerated delete, before everything else

    def test_commands_are_argument_lists_with_no_shell_text(self):
        for pair in (('off', 'internet'), ('internet', 'off'), ('local', 'internet'), ('local', 'off')):
            result = np.plan(*pair, identity=True)
            for step in result.up + result.down + result.firewall:
                self.assertIsInstance(step.argv, tuple)
                self.assertIn(step.argv[0], ('nmcli', 'iptables'))
                for part in step.argv:
                    self.assertNotIn(';', part)
                    self.assertNotIn('|', part)

    def test_plan_does_not_depend_on_profile_names_with_spaces(self):
        result = np.plan('off', 'internet', wired_profile='Wired connection 7', wifi_profile='Home Net')
        self.assertIn('nmcli connection modify id Home Net connection.autoconnect yes', flat(result.up))
        self.assertIn('nmcli connection modify id Wired connection 7 connection.autoconnect no', flat(result.down))


class ConfirmOrRevertTests(unittest.TestCase):
    def test_an_unconfirmed_change_reverts_after_the_grace_period(self):
        change = np.begin_change(('off', 'internet'), ('internet', 'off'), now=1000)
        self.assertEqual(change['deadline'], 1000 + np.GRACE_SECONDS)
        self.assertFalse(np.must_revert(change, 1000 + np.GRACE_SECONDS - 1))
        self.assertTrue(np.must_revert(change, 1000 + np.GRACE_SECONDS))
        self.assertEqual(np.revert_target(change), ('off', 'internet'))

    def test_a_confirmed_change_never_reverts(self):
        change = np.confirm(np.begin_change(('off', 'internet'), ('local', 'internet'), now=0))
        self.assertTrue(change['confirmed'])
        self.assertFalse(np.must_revert(change, 10 ** 9))

    def test_confirm_returns_a_new_record_and_leaves_the_old_one_alone(self):
        change = np.begin_change(('off', 'internet'), ('local', 'off'), now=5)
        np.confirm(change)
        self.assertFalse(change['confirmed'])


if __name__ == '__main__':
    unittest.main()

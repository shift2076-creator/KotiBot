import json
import tempfile
import unittest
from pathlib import Path

import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'subsystems', 'network'))
import network_helper as helper
import network_plan as plan_module


class Fake:
    def __init__(self, fail_on=None, up=True):
        self.commands, self.files, self.removed = [], {}, []
        self.fail_on, self.up = fail_on, up

    def runner(self, argv):
        self.commands.append(tuple(argv))
        return 1 if self.fail_on and self.fail_on in ' '.join(argv) else 0

    def write_file(self, path, content):
        self.files[path] = content

    def remove_file(self, path):
        self.removed.append(path)

    def check(self):
        return self.up

    def kwargs(self):
        return dict(runner=self.runner, write_file=self.write_file, remove_file=self.remove_file, check=self.check)


class HelperTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.path = Path(self.dir.name)

    def request(self, ethernet, wifi):
        (self.path / 'request.json').write_text(json.dumps({'ethernet': ethernet, 'wifi': wifi}))

    def state(self):
        return json.loads((self.path / 'state.json').read_text())

    def test_apply_brings_the_new_setup_up_before_removing_the_old(self):
        fake = Fake()
        helper.apply_roles('local', 'off', **fake.kwargs())
        plan = plan_module.plan('local', 'off')
        expected = [s.argv for s in plan.up + plan.firewall + plan.down]
        self.assertEqual(fake.commands, expected)
        self.assertEqual(fake.files[plan_module.SHARED_DNSMASQ_FILE], plan_module.SHARED_DNSMASQ_CONTENT)

    def test_an_unsupported_pair_runs_nothing(self):
        fake = Fake()
        with self.assertRaises(helper.ApplyError):
            helper.apply_roles('internet', 'local', **fake.kwargs())
        self.assertEqual(fake.commands, [])

    def test_the_old_setup_is_kept_when_the_new_one_does_not_come_up(self):
        fake = Fake(up=False)
        plan = plan_module.plan('local', 'off')
        with self.assertRaises(helper.ApplyError):
            helper.apply_roles('local', 'off', **fake.kwargs())
        for step in plan.down:
            self.assertNotIn(step.argv, fake.commands)

    def test_a_tolerated_failure_is_fine_and_any_other_failure_stops_the_run(self):
        helper.apply_roles('off', 'internet', **Fake(fail_on='connection delete').kwargs())
        with self.assertRaises(helper.ApplyError):
            helper.apply_roles('off', 'internet', **Fake(fail_on='connection modify').kwargs())

    def test_a_request_is_applied_and_waits_for_confirmation(self):
        fake = Fake()
        self.request('local', 'off')
        result = helper.tick(self.path, 1000, **fake.kwargs())
        self.assertEqual(result, {'status': 'waiting', 'deadline': 1000 + plan_module.GRACE_SECONDS})
        self.assertEqual(self.state()['current'], ['local', 'off'])
        self.assertFalse((self.path / 'request.json').exists())

    def test_confirming_in_time_keeps_the_change(self):
        fake = Fake()
        self.request('local', 'off')
        helper.tick(self.path, 1000, **fake.kwargs())
        (self.path / 'confirm').write_text('')
        self.assertEqual(helper.tick(self.path, 1060, **fake.kwargs()), {'status': 'confirmed'})
        self.assertIsNone(self.state()['change'])
        # Long after the deadline nothing is reverted.
        self.assertIsNone(helper.tick(self.path, 5000, **fake.kwargs()))
        self.assertEqual(self.state()['current'], ['local', 'off'])

    def test_an_unconfirmed_change_goes_back_when_time_is_up(self):
        fake = Fake()
        self.request('local', 'off')
        helper.tick(self.path, 1000, **fake.kwargs())
        self.assertIsNone(helper.tick(self.path, 1000 + plan_module.GRACE_SECONDS - 1, **fake.kwargs()))
        fake.commands.clear()
        result = helper.tick(self.path, 1000 + plan_module.GRACE_SECONDS, **fake.kwargs())
        self.assertEqual(result, {'status': 'reverted', 'roles': ['off', 'internet']})
        self.assertEqual(self.state()['current'], ['off', 'internet'])
        self.assertIn(plan_module.plan('off', 'internet').up[-1].argv, fake.commands)

    def test_a_failed_apply_restores_the_previous_setup_and_reports_it(self):
        fake = Fake(up=False)
        self.request('local', 'off')
        result = helper.tick(self.path, 1000, **fake.kwargs())
        self.assertEqual(result['status'], 'failed')
        self.assertIn('did not come up', result['error'])
        self.assertEqual(self.state()['current'], ['off', 'internet'])
        self.assertIsNone(self.state()['change'])

    def test_a_second_request_waits_until_the_first_is_confirmed(self):
        fake = Fake()
        self.request('local', 'off')
        helper.tick(self.path, 1000, **fake.kwargs())
        fake.commands.clear()
        self.request('off', 'internet')
        result = helper.tick(self.path, 1010, **fake.kwargs())
        self.assertEqual(result['status'], 'failed')
        self.assertIn('already waiting', result['error'])
        self.assertEqual(fake.commands, [])

    def test_an_unsupported_request_is_reported_and_changes_nothing(self):
        fake = Fake()
        self.request('internet', 'local')
        result = helper.tick(self.path, 1000, **fake.kwargs())
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(fake.commands, [])
        self.assertEqual(self.state()['current'], ['off', 'internet'])


if __name__ == '__main__':
    unittest.main()

"""Guard against missing discovery, duplicate execution, and false green runs."""
import contextlib
import io
import unittest
from unittest.mock import patch

from tests import runner


class TestRunnerTests(unittest.TestCase):
    def test_full_suite_contains_every_case_once(self):
        suite = runner.load_selection('all')
        ids = [case.id() for case in runner.cases(suite)]
        self.assertEqual(len(ids), len(set(ids)))
        groups = {'.'.join(name.split('.')[1:3]) for name in ids}
        expected = {
            '.'.join(directory.relative_to(runner.TESTS).parts)
            for directory in runner.TESTS.glob('*/*')
            if directory.is_dir() and any(directory.glob('test_*.py'))
        }
        self.assertEqual(groups, expected)

    def test_category_contains_only_its_suites(self):
        category = {case.id() for case in runner.cases(runner.load_selection('devices'))}
        combined = set()
        for directory in (runner.TESTS / 'devices').iterdir():
            if directory.is_dir() and any(directory.glob('test_*.py')):
                combined.update(case.id() for case in runner.cases(
                    runner.load_selection(f'devices.{directory.name}')))
        self.assertEqual(category, combined)
        self.assertTrue(category)
        self.assertTrue(all(name.startswith('tests.devices.') for name in category))

    def test_exact_method_selects_only_one_case(self):
        name = ('devices.matter.test_matter_reliability.MatterColdStartTests.'
                'test_fresh_sibling_does_not_make_unknown_or_unreachable_endpoint_live')
        suite = runner.load_selection(name)
        self.assertEqual([case.id() for case in runner.cases(suite)], [f'tests.{name}'])

    def test_empty_filter_is_an_error(self):
        with self.assertRaisesRegex(ValueError, 'No tests matched'):
            runner.load_selection('devices.matter', 'nonexistent_case_987654321')

    def test_unknown_suite_is_an_error(self):
        with self.assertRaisesRegex(ValueError, 'Test loading failed'):
            runner.load_selection('devices.nonexistent_suite')

    def test_listing_does_not_execute_cases(self):
        with patch.object(unittest.TextTestRunner, 'run') as execute:
            with contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(runner.main(['devices.matter', '--list']), 0)
        execute.assert_not_called()
        self.assertIn('MatterColdStartTests.', output.getvalue())

    def test_missing_dependency_stops_before_discovery(self):
        with patch.object(runner.importlib, 'import_module', side_effect=ImportError):
            with patch.object(runner, 'load_selection') as load:
                with contextlib.redirect_stderr(io.StringIO()) as output:
                    self.assertEqual(runner.main([]), 2)
        load.assert_not_called()
        self.assertIn('tests/requirements.txt', output.getvalue())

    def test_failed_test_sets_failure_exit_code(self):
        class DeliberateFailure(unittest.TestCase):
            def runTest(self):
                self.fail('Synthetic failure used only to check the runner exit code.')
        fixture = unittest.TestSuite([DeliberateFailure()])
        with patch.object(runner, 'check_dependencies'):
            with patch.object(runner, 'load_selection', return_value=fixture):
                with contextlib.redirect_stderr(io.StringIO()):
                    self.assertEqual(runner.main([]), 1)

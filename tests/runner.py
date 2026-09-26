"""Small unittest entry point for categories, suites, modules, and cases."""
import argparse
import importlib
from pathlib import Path
import re
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / 'tests'


def cases(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from cases(item)
        else:
            yield item


def load_selection(selector, pattern=None):
    if selector.startswith('tests.'):
        selector = selector[len('tests.'):]
    if not re.fullmatch(r'[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*', selector):
        raise ValueError('Use dotted names, for example devices.matter.')
    loader = unittest.TestLoader()
    # unittest's -k matching: a substring unless the pattern contains '*'.
    if pattern is not None:
        loader.testNamePatterns = [pattern if '*' in pattern else f'*{pattern}*']
    directory = TESTS if selector == 'all' else TESTS.joinpath(*selector.split('.'))
    if directory.is_dir():
        suite = loader.discover(str(directory), pattern='test_*.py', top_level_dir=str(ROOT))
    else:
        suite = loader.loadTestsFromName(f'tests.{selector}')
    if loader.errors:
        raise ValueError('Test loading failed:\n' + '\n'.join(loader.errors))
    selected = list(cases(suite))
    # loadTestsFromName bypasses testNamePatterns when selecting one method.
    if pattern is not None:
        from fnmatch import fnmatchcase
        match = loader.testNamePatterns[0]
        selected = [case for case in selected if fnmatchcase(case.id(), match)]
    if not selected:
        raise ValueError('No tests matched. Run python -m tests --list to see the suites.')
    return unittest.TestSuite(selected)


def check_dependencies():
    for name in ('flask', 'google.auth.transport.requests'):
        try:
            importlib.import_module(name)
        except ImportError as exc:
            raise ValueError(
                f'Test dependency unavailable: {name}. '
                'Run python -m pip install -r tests/requirements.txt'
            ) from exc


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('selector', nargs='?', default='all',
                        help='all, category, category.suite, or a dotted module/class/test name')
    parser.add_argument('-k', metavar='PATTERN', help='case name substring or wildcard')
    parser.add_argument('-v', '--verbose', action='store_true')
    parser.add_argument('--list', action='store_true',
                        help='list suite counts; with a selector or -k, list matching test IDs')
    parser.add_argument('-f', '--failfast', action='store_true')
    args = parser.parse_args(argv)
    try:
        check_dependencies()
        suite = load_selection(args.selector, args.k)
    except (ValueError, ImportError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if args.list:
        if args.selector == 'all' and args.k is None:
            counts = {}
            for case in cases(suite):
                group = '.'.join(case.id().split('.')[1:3])
                counts[group] = counts.get(group, 0) + 1
            for group, count in sorted(counts.items()):
                print(f'{group:28} {count:3} tests')
            print(f'{sum(counts.values())} tests in {len(counts)} suites')
        else:
            for case in cases(suite):
                print(case.id().removeprefix('tests.'))
        return 0
    result = unittest.TextTestRunner(verbosity=2 if args.verbose else 1,
                                    failfast=args.failfast).run(suite)
    return 0 if result.wasSuccessful() else 1

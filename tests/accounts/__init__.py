"""Tests for the accounts portal (Django), kept here and copied into the portal image by the installer.

Inside the image they run as `portal.tests` under `manage.py test portal`. Under KotiBot's own runner
(`python -m tests accounts`) this file points Django at the portal settings and builds the throwaway test
database, so the same cases run in both places.
"""
if __name__ == 'tests.accounts':
    import atexit
    import os
    import sys
    import tempfile
    from pathlib import Path

    sys.path.append(str(Path(__file__).resolve().parents[2] / 'subsystems' / 'accounts'))
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'settings')
    os.environ.setdefault('PIVAULT_SECRET_KEY', 'test-key-not-a-production-secret')
    os.environ.setdefault('PIVAULT_DATA', tempfile.mkdtemp(prefix='pivault-test-'))

    import django
    django.setup()

    from django.test.runner import DiscoverRunner
    from django.test.utils import setup_test_environment

    setup_test_environment()
    _runner = DiscoverRunner(verbosity=0, interactive=False)
    _databases = _runner.setup_databases()
    atexit.register(_runner.teardown_databases, _databases)

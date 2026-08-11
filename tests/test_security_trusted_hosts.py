import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from flask import Flask


REPO_ROOT = Path(__file__).resolve().parents[1]
SECURITY_MODULE_PATH = (
    REPO_ROOT
    / 'subsystems'
    / 'security'
    / 'kotibot_security.py'
)


def load_security_module():
    spec = importlib.util.spec_from_file_location(
        'test_security_trusted_hosts_module',
        SECURITY_MODULE_PATH,
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class SecurityTrustedHostsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.security_module = load_security_module()

    def test_parser_accepts_exact_ip_and_hostname_values(self):
        parsed = self.security_module._parse_trusted_hosts(
            '192.168.4.45, kotibot, KOTIBOT.local., 192.168.4.45'
        )

        self.assertEqual(
            parsed,
            ('192.168.4.45', 'kotibot', 'kotibot.local'),
        )

    def test_parser_rejects_origins_ports_paths_and_wildcards(self):
        invalid_values = (
            'http://192.168.4.45',
            '192.168.4.45:5000',
            '192.168.4.45/path',
            '*.example.test',
            '.example.test',
        )

        for value in invalid_values:
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    self.security_module._parse_trusted_hosts(value)

    def test_configured_local_host_is_accepted_without_trusting_others(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            security = self.security_module.KotiBotSecurity(
                self.security_module.SecurityConfig(
                    base_dir=Path(temp_dir),
                    allowed_origins=(
                        ('https', 'kotibot.example.test', 443),
                    ),
                    trusted_hosts=('192.168.4.45',),
                )
            )
            app = Flask(__name__)
            security.init_app(app)

            @app.get('/probe')
            def probe():
                return {'ok': True}

            client = app.test_client()

            self.assertEqual(
                client.get(
                    '/probe',
                    headers={'Host': '192.168.4.45:5000'},
                ).status_code,
                200,
            )
            self.assertEqual(
                client.get(
                    '/probe',
                    headers={'Host': 'untrusted.example.test'},
                ).status_code,
                400,
            )

    def test_make_security_loads_trusted_hosts_from_environment(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            env = {
                'KOTIBOT_SECURITY': '1',
                'KOTIBOT_ALLOWED_ORIGINS': 'https://kotibot.example.test',
                'KOTIBOT_TRUSTED_HOSTS': '192.168.4.45,kotibot',
            }

            with patch.dict(os.environ, env, clear=True):
                security = self.security_module.make_security(
                    Path(temp_dir),
                )

            self.assertEqual(
                security.config.trusted_hosts,
                ('192.168.4.45', 'kotibot'),
            )


if __name__ == '__main__':
    unittest.main()

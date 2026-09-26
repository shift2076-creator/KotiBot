"""Exercise Git's ignore rules at the source/runtime boundary."""
from pathlib import Path
import os
import subprocess
from tempfile import TemporaryDirectory
import unittest

ROOT = Path(__file__).resolve().parents[3]


class GitIgnoreBoundaryTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        (self.root / '.gitignore').write_bytes((ROOT / '.gitignore').read_bytes())
        self.environment = {key: value for key, value in os.environ.items()
                            if not key.startswith('GIT_')}
        self.environment['GIT_CONFIG_NOSYSTEM'] = '1'
        self.environment['GIT_CONFIG_GLOBAL'] = os.devnull
        self.git('init', '-q')

    def git(self, *args, input=None):
        result = subprocess.run(['git', '-c', 'core.excludesFile=' + os.devnull,
                                 *args], cwd=self.root, env=self.environment,
                                input=input, capture_output=True, text=True)
        self.assertIn(result.returncode, (0, 1), result.stderr)
        return result

    def assert_ignored(self, paths, expected):
        result = self.git('check-ignore', '--no-index', '--stdin', '-z',
                          input='\0'.join(paths) + '\0')
        self.assertEqual(set(filter(None, result.stdout.split('\0'))),
                         set(paths) if expected else set())

    def test_runtime_residue_and_deliberate_source_are_visible(self):
        self.assert_ignored([
            'server_state.json', 'subsystems/tapo/tapo_device_state.json',
            'subsystems/security/security_audit.jsonl',
            'subsystems/security/security_audit.jsonl.1',
            'subsystems/notifications/notification_queue.jsonl',
            'subsystems/activities/.activity_state.json.12.tmp',
            'state.lkg.json', 'state.json.bak', 'state.bak.1',
            'server.log', 'server.pid', 'logs/server.log', 'runtime/lock',
            'tmp/staging.bin', 'subsystems/temp/recording.part',
            '.Trash-1000/files/old.zip', 'recordings/clip.mp4',
            'static/recordings/clip.mp4', 'subsystems/video/videos/clip.mp4',
            'static/hls/segment.ts', 'static/cache/frame.jpg',
            'static/apks/client.apk', 'client.apk',
            'tests/fixtures/config.json', 'tests/fixtures/events.jsonl',
            '.env.example', 'subsystems/.env.example',
        ], False)

    def test_deliberate_developer_files_remain_ignored(self):
        self.assert_ignored([
            '.venv/lib/package.json', 'venv/bin/python', 'env/package.py',
            'server_core/__pycache__/io.pyc', '.pytest_cache/result.json',
            '.mypy_cache/data.json', '.ruff_cache/hash', 'temp/operator.json',
            '.idea/workspace.xml', '.vscode/settings.json', '.DS_Store',
            'Thumbs.db', 'file.swp', 'file~', '.gradle/cache.bin',
            'android/build/app.apk', 'local.properties',
            'art/font.ufo/glyphs/file.glif', 'art/source.psd',
            'static/img/favicons/FLASK_ROUTES.txt',
            'static/img/favicons/HEAD_SNIPPET.txt',
        ], True)

    def test_explicit_secrets_and_controller_identity_remain_ignored(self):
        self.assert_ignored([
            '.env', '.env.local', 'subsystems/.env.local', 'identity.pem',
            'identity.key', 'identity.p12', 'identity.pfx',
            'credentials-local.json', 'secrets-local.json',
            'subsystems/notifications/firebase-service-account.json',
            'subsystems/security/security_state.json',
            'subsystems/matter/chip_tool_storage/chip.json',
            'subsystems/matter/chip_tool_subscription_storage/node/chip.json',
        ], True)

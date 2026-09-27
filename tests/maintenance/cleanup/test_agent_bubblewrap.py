"""Image replacement must preserve the boundary, gate activation, and recover."""
import contextlib
import copy
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from tools.agent_access import greenie
from tests.maintenance.cleanup.test_agent_selinux import Engine, HEAD, OLD, NEW, IMAGE, LEVEL

UPDATED_IMAGE = 'e' * 64
WORKSPACE_HEAD = 'f' * 40
BINARY = '/home/developer/.vscode-server/extensions/openai.chatgpt-26.917.62051-linux-x64/bin/linux-x86_64/codex'


class BubblewrapEngine(Engine):
    def __init__(self):
        super().__init__()
        self.items[OLD]['ProcessLabel'] = 'system_u:system_r:container_userns_t:' + LEVEL
        self.image_config = {'User': 'developer', 'Cmd': ['sleep', 'infinity'], 'Env': ['HOME=/home/developer']}
        self.candidate_config = copy.deepcopy(self.image_config)
        self.dirty = False

    def __call__(self, *args, **kwargs):
        if args[:2] == ('image', 'inspect'):
            self.calls.append(args)
            return json.dumps([{'Id': args[2], 'Config': self.candidate_config if args[2] == UPDATED_IMAGE else self.image_config}])
        if args[0] == 'exec':
            self.calls.append(args)
            if args[-3:] == ('git', 'rev-parse', 'HEAD'):
                return WORKSPACE_HEAD
            if args[-1] == '--untracked-files=all':
                return ' M user-work.py' if self.dirty else ''
            if args[-2:] == ('/usr/local/bin/bwrap', '--version'):
                return 'bubblewrap 0.13.0'
            if 'shutil.which' in args[-1]:
                return '/usr/local/bin/bwrap'
            raise AssertionError(args)
        result = super().__call__(*args, **kwargs)
        if args[0] == 'create':
            self.items[NEW]['Image'] = args[-1]
        return result


class BubblewrapRepairTests(unittest.TestCase):
    def setUp(self):
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.state = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.engine = BubblewrapEngine()
        self.stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
        self.stack.enter_context(contextlib.redirect_stderr(io.StringIO()))
        self.stack.enter_context(patch.object(greenie, 'STATE', self.state))
        self.stack.enter_context(patch.object(greenie.os, 'geteuid', return_value=1000))
        self.run = self.stack.enter_context(patch.object(greenie, 'run', side_effect=self.host_run))
        self.stack.enter_context(patch.object(greenie, 'podman', side_effect=self.engine))
        self.stack.enter_context(patch.object(greenie.subprocess, 'run', side_effect=self.engine.exists))
        self.proxy = self.stack.enter_context(patch.object(greenie, 'wait_proxy'))
        self.inspection = self.stack.enter_context(patch.object(greenie, 'container_inspection'))
        self.codex = self.stack.enter_context(patch.object(greenie, 'codex_sandbox_check'))

    def host_run(self, *args, **kwargs):
        return 'Enforcing' if args == ('getenforce',) else HEAD

    def repair(self):
        greenie.repair_bubblewrap(Path('/source'), HEAD, UPDATED_IMAGE, IMAGE)

    def assert_original_running(self):
        self.assertEqual(self.engine.item(greenie.NAME)['Id'], OLD)
        self.assertTrue(self.engine.items[OLD]['running'])

    def test_actual_codex_gate_precedes_activation_and_preserves_workspace_head(self):
        def verify(name, *, expected_head):
            self.assertEqual(name, greenie.BUBBLEWRAP_CANDIDATE)
            self.assertEqual(expected_head, WORKSPACE_HEAD)
            self.assertEqual(self.engine.item(greenie.NAME)['Id'], OLD)
            self.assertFalse(self.engine.items[OLD]['running'])
            self.assertTrue(self.engine.items[NEW]['running'])
            self.inspection.assert_called_once_with(codex=True, name=name)
        self.codex.side_effect = verify
        self.repair()
        self.assertEqual(self.engine.item(greenie.NAME)['Id'], NEW)
        self.assertEqual(self.engine.item(greenie.BUBBLEWRAP_BACKUP)['Id'], OLD)
        self.assertFalse(self.engine.items[OLD]['running'])
        record = json.loads((self.state/'bubblewrap-repair.json').read_text())
        self.assertEqual(record['workspace_head'], WORKSPACE_HEAD)
        self.assertEqual(record['original_id'], OLD)
        self.assertEqual(record['candidate_id'], NEW)
        create = next(call for call in self.engine.calls if call[0] == 'create')
        self.assertEqual(create[-1], UPDATED_IMAGE)
        self.assertIn('--security-opt=label=level:' + LEVEL, create)
        self.assertIn('--security-opt=label=type:container_userns_t', create)
        self.assertIn('--cap-drop=all', create)
        self.assertIn('--read-only', create)
        self.assertTrue(all(call[0] not in ('rm', 'build', 'volume', 'tag') for call in self.engine.calls))

    def test_codex_sandbox_failure_restores_original_without_activation(self):
        self.codex.side_effect = subprocess.CalledProcessError(1, ['podman', 'exec'])
        with self.assertRaises(subprocess.CalledProcessError):
            self.repair()
        self.assert_original_running()
        self.assertFalse(self.engine.items[NEW]['running'])
        self.assertFalse(any(call[0] == 'rename' for call in self.engine.calls))

    def test_denial_failure_prevents_codex_execution(self):
        self.inspection.side_effect = ValueError('boundary failed')
        with self.assertRaisesRegex(ValueError, 'boundary failed'):
            self.repair()
        self.codex.assert_not_called()
        self.assert_original_running()

    def test_failed_activation_recovers_original(self):
        self.engine.fail_activation = True
        with self.assertRaises(subprocess.CalledProcessError):
            self.repair()
        self.assert_original_running()
        self.assertFalse(self.engine.items[NEW]['running'])

    def test_wrong_image_is_rejected_before_creation(self):
        with self.assertRaisesRegex(ValueError, 'baseline'):
            greenie.repair_bubblewrap(Path('/source'), HEAD, UPDATED_IMAGE, '1'*64)
        self.assertFalse(any(call[0] in ('create', 'stop') for call in self.engine.calls))

    def test_changed_image_environment_is_rejected(self):
        self.engine.candidate_config['Env'] = ['SSH_AUTH_SOCK=/unsafe']
        with self.assertRaisesRegex(ValueError, 'configuration: Env'):
            self.repair()
        self.assertFalse(any(call[0] in ('create', 'stop') for call in self.engine.calls))

    def test_dirty_checkout_is_preserved_without_interrupting_container(self):
        self.engine.dirty = True
        with self.assertRaisesRegex(ValueError, 'checkout has changes'):
            self.repair()
        self.assert_original_running()
        self.assertFalse(any(call[0] in ('create', 'stop') for call in self.engine.calls))

    def test_permissive_selinux_is_rejected(self):
        self.run.side_effect = lambda *args: 'Permissive' if args == ('getenforce',) else HEAD
        with self.assertRaisesRegex(ValueError, 'Enforcing'):
            self.repair()
        self.assertEqual(self.engine.calls, [])

    def test_existing_recovery_record_is_not_overwritten(self):
        record = self.state/'bubblewrap-repair.json'
        record.write_text('existing recovery information')
        with self.assertRaisesRegex(ValueError, 'recovery record exists'):
            self.repair()
        self.assertEqual(record.read_text(), 'existing recovery information')
        self.assertFalse(any(call[0] in ('create', 'stop') for call in self.engine.calls))

    def test_rollback_restores_original_and_retains_candidate(self):
        self.repair()
        greenie.rollback_bubblewrap()
        self.assert_original_running()
        self.assertEqual(self.engine.item(greenie.BUBBLEWRAP_CANDIDATE)['Id'], NEW)
        self.assertFalse(self.engine.items[NEW]['running'])

    def test_rollback_refuses_unrelated_backup_image(self):
        self.repair()
        self.engine.items[OLD]['Image'] = '2'*64
        self.engine.calls.clear()
        with self.assertRaisesRegex(ValueError, 'recorded image'):
            greenie.rollback_bubblewrap()
        self.assertTrue(self.engine.items[NEW]['running'])
        self.assertFalse(any(call[0] in ('stop', 'rename') for call in self.engine.calls))

    def test_failed_rollback_start_restores_updated_container(self):
        self.repair()
        self.engine.fail_old_start_once = True
        with self.assertRaises(subprocess.CalledProcessError):
            greenie.rollback_bubblewrap()
        self.assertEqual(self.engine.item(greenie.NAME)['Id'], NEW)
        self.assertTrue(self.engine.items[NEW]['running'])
        self.assertFalse(self.engine.items[OLD]['running'])


class CodexInvocationTests(unittest.TestCase):
    def invoke(self, version=greenie.CODEX_VERSION, expected_head=WORKSPACE_HEAD):
        def podman(*args, **kwargs):
            if args[-1] == '--version':
                return version
            if args[-1] == 'HEAD':
                return WORKSPACE_HEAD
            return BINARY
        with (patch.object(greenie, 'podman', side_effect=podman),
              patch.object(greenie.subprocess, 'run') as execute,
              contextlib.redirect_stdout(io.StringIO())):
            greenie.codex_sandbox_check('candidate', expected_head=expected_head)
        return execute

    def test_installed_cli_runs_local_workspace_sandbox_with_no_network(self):
        execute = self.invoke()
        args = execute.call_args.args[0]
        self.assertEqual(args[:7], ['podman', 'exec', '-i', '-w', '/workspace/kotibot', 'candidate', BINARY])
        self.assertEqual(args[7:], ['-c', 'sandbox_mode="workspace-write"', '-c',
                                 'sandbox_workspace_write.network_access=false',
                                 'sandbox', '--', '/opt/tests/bin/python', '-', WORKSPACE_HEAD])
        self.assertTrue(execute.call_args.kwargs['check'])
        self.assertIn('ACTUAL CODEX SANDBOX AND FULL SUITE: PASS', execute.call_args.kwargs['input'])
        self.assertNotIn('SSH_AUTH_SOCK', execute.call_args.kwargs['env'])

    def test_changed_cli_version_stops_before_sandbox_command(self):
        with self.assertRaisesRegex(ValueError, 'version changed'):
            self.invoke(version='codex-cli unknown')

    def test_changed_workspace_head_stops_before_sandbox_command(self):
        with self.assertRaisesRegex(ValueError, 'source commit changed'):
            self.invoke(expected_head=HEAD)

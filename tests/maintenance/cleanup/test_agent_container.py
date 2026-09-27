"""Fail-closed checks for explicitly approved outer-container Codex execution."""
import contextlib
import copy
import io
import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

from tools.agent_access import greenie

IDENTITY = 'b' * 64
HEAD = 'a' * 40
BINARY = ('/home/developer/.vscode-server/extensions/'
          'openai.chatgpt-26.917.62051-linux-x64/bin/linux-x86_64/codex')


def approved_container():
    return {'Id': IDENTITY, 'State': {'Running': True},
            'Mounts': [
                {'Type': 'bind', 'Source': str(greenie.WORKSPACE.resolve()),
                 'Destination': '/workspace/kotibot'},
                {'Type': 'volume', 'Name': 'kotibot-development-home',
                 'Destination': '/home/developer'},
                {'Type': 'tmpfs', 'Destination': '/tmp'}],
            'HostConfig': {'IpcMode': 'private', 'Devices': [], 'VolumesFrom': [], 'PortBindings': {}}}


class OuterBoundaryTests(unittest.TestCase):
    def inspect(self, value=None, *, enforcing='Enforcing', rootless=True, uid=1000):
        with (patch.object(greenie.os, 'geteuid', return_value=uid),
              patch.object(greenie, 'run', return_value=enforcing),
              patch.object(greenie, 'podman', return_value=json.dumps({'host': {'security': {'rootless': rootless}}})),
              patch.object(greenie, 'inspect_configuration', return_value=value or approved_container())):
            return greenie.inspect_container_boundary()

    def test_approved_rootless_boundary(self):
        self.assertEqual(self.inspect()['Id'], IDENTITY)

    def test_rootful_or_permissive_host_is_rejected(self):
        for args in ({'uid': 0}, {'rootless': False}, {'enforcing': 'Permissive'}):
            with self.subTest(args=args), self.assertRaises(ValueError):
                self.inspect(**args)

    def test_changed_mount_destination_and_missing_home_are_rejected(self):
        for alteration in ('destination', 'missing', 'extra', 'tmpfs', 'type'):
            value = approved_container()
            if alteration == 'destination':
                value['Mounts'][0]['Destination'] = '/home/developer/.ssh'
            elif alteration == 'missing':
                del value['Mounts'][1]
            elif alteration == 'extra':
                value['Mounts'].append({'Type': 'bind', 'Source': '/var/mnt/kotibot', 'Destination': '/production'})
            elif alteration == 'tmpfs':
                value['Mounts'][2]['Destination'] = '/etc'
            else:
                value['Mounts'][2]['Type'] = 'image'
            with self.subTest(alteration=alteration), self.assertRaises(ValueError):
                self.inspect(value)

    def test_host_integration_and_unidentified_container_are_rejected(self):
        changes = [('IpcMode', 'host'), ('Devices', [{'PathOnHost': '/dev/snd'}]),
                   ('VolumesFrom', ['another-container']), ('PortBindings', {'1234/tcp': [{}]})]
        for key, setting in changes:
            value = approved_container()
            value['HostConfig'][key] = setting
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.inspect(value)
        for value in (dict(approved_container(), Id='unidentified'),
                      dict(approved_container(), State={'Running': False})):
            with self.assertRaises(ValueError):
                self.inspect(value)

    def test_probe_targets_verified_id_and_explicit_boundary(self):
        with (patch.object(greenie, 'inspect_container_boundary', return_value=approved_container()),
              patch.object(greenie, 'podman', return_value='') as execute,
              contextlib.redirect_stdout(io.StringIO())):
            greenie.container_inspection(codex=True, boundary='container')
        self.assertEqual(execute.call_args.args,
                         ('exec', '-i', IDENTITY, 'python', '-', '--boundary', 'container', '--codex'))
        self.assertIn('container seccomp filter active', execute.call_args.kwargs['input'])


class ContainerCodexTests(unittest.TestCase):
    def setUp(self):
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.output = self.stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
        self.inspection = self.stack.enter_context(patch.object(
            greenie, 'container_inspection', return_value=approved_container()))
        self.binary = self.stack.enter_context(patch.object(greenie, 'installed_codex', return_value=BINARY))
        self.podman = self.stack.enter_context(patch.object(greenie, 'podman', return_value=HEAD))
        self.execute = self.stack.enter_context(patch.object(greenie.subprocess, 'run'))
        self.launch = self.stack.enter_context(patch.object(greenie.os, 'execvpe'))

    def test_actual_codex_runner_uses_approved_mode_and_embeds_denial_checks(self):
        greenie.codex_sandbox_check(expected_head=HEAD, boundary='container')
        args = self.execute.call_args.args[0]
        self.assertEqual(args, ['podman', 'exec', '-i', '-w', '/workspace/kotibot', IDENTITY, BINARY,
                               '-c', 'sandbox_mode="danger-full-access"', '-c', 'approval_policy="on-request"',
                               'sandbox', '--', '/opt/tests/bin/python', '-', HEAD, 'container'])
        script = self.execute.call_args.kwargs['input']
        compile(script, '<actual-codex-probe>', 'exec')
        self.assertIn('_boundary_probe["main"](["--boundary", "container", "--codex"])', script)
        self.assertIn('production/publication proxy route denied', script)
        self.assertIn("subprocess.run(['/opt/tests/bin/python', '-m', 'tests'], check=True)", script)
        self.assertEqual(self.inspection.call_count, 2)
        self.assertIn('CODEX CONTAINER EXECUTION AND FULL SUITE: PASS', self.output.getvalue())

    def test_denied_boundary_never_executes_or_launches_codex(self):
        self.inspection.side_effect = ValueError('boundary denied')
        for action in (lambda: greenie.codex_sandbox_check(boundary='container'), greenie.launch_codex):
            with self.assertRaisesRegex(ValueError, 'boundary denied'):
                action()
        self.binary.assert_not_called()
        self.execute.assert_not_called()
        self.launch.assert_not_called()

    def test_failed_command_does_not_report_success_or_try_another_mode(self):
        self.execute.side_effect = subprocess.CalledProcessError(1, ['podman', 'exec'])
        with self.assertRaises(subprocess.CalledProcessError):
            greenie.codex_sandbox_check(boundary='container')
        self.assertEqual(self.execute.call_count, 1)
        self.assertNotIn('FULL SUITE: PASS', self.output.getvalue())
        self.launch.assert_not_called()

    def test_failed_post_execution_boundary_does_not_report_completion(self):
        self.inspection.side_effect = [approved_container(), ValueError('boundary changed')]
        with self.assertRaisesRegex(ValueError, 'boundary changed'):
            greenie.codex_sandbox_check(boundary='container')
        self.assertNotIn('CODEX CONTAINER EXECUTION AND FULL SUITE: PASS', self.output.getvalue())

    def test_wrong_commit_blocks_the_command(self):
        with self.assertRaisesRegex(ValueError, 'source commit changed'):
            greenie.codex_sandbox_check(expected_head='c' * 40, boundary='container')
        self.execute.assert_not_called()

    def test_launch_is_only_in_verified_container_with_on_request_approval(self):
        greenie.launch_codex()
        program, args, environment = self.launch.call_args.args
        self.assertEqual(program, 'podman')
        self.assertEqual(args, ['podman', 'exec', '-it', '-w', '/workspace/kotibot', IDENTITY, BINARY,
                                '--sandbox', 'danger-full-access', '--ask-for-approval', 'on-request',
                                '--no-alt-screen'])
        self.assertNotIn('SSH_AUTH_SOCK', environment)
        self.assertNotIn('OPENAI_API_KEY', environment)
        self.execute.assert_not_called()

    def test_unreviewed_binary_blocks_launch(self):
        self.binary.side_effect = ValueError('Codex version changed')
        with self.assertRaisesRegex(ValueError, 'version changed'):
            greenie.launch_codex()
        self.launch.assert_not_called()

    def test_unknown_boundary_has_no_side_effect(self):
        with self.assertRaisesRegex(ValueError, 'Unknown development boundary'):
            greenie.codex_sandbox_check(boundary='guess')
        self.inspection.assert_not_called()
        self.execute.assert_not_called()


class CommandRoutingTests(unittest.TestCase):
    def test_normal_cli_verification_selects_container_boundary(self):
        from tools import agent_development as cli
        for arguments, owner, expected in (
            (['verify', '--codex'], 'container_inspection', {'codex': True, 'boundary': 'container'}),
            (['check-codex', '--expected-head', HEAD], 'codex_sandbox_check',
             {'expected_head': HEAD, 'boundary': 'container'}),
            (['codex'], 'launch_codex', {}),
        ):
            with (self.subTest(arguments=arguments), patch.object(cli.sys, 'argv', ['agent_development.py', *arguments]),
                  patch.object(cli, owner) as call, contextlib.redirect_stdout(io.StringIO())):
                cli.main()
            call.assert_called_once_with(**expected)

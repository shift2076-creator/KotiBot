"""Regression checks for nested-container sandbox validation and resumption."""
import contextlib
import importlib.util
import io
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

from tools.agent_access import greenie

ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location('agent_probe', ROOT/'deploy/agent-access/probe.py')
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)
DENIED = "bwrap: Can't mount proc on /newroot/proc: Permission denied"


class NestedSandboxTests(unittest.TestCase):
    def test_recognized_proc_failure_preserves_every_other_restriction(self):
        calls = []
        def execute(args, **kwargs):
            calls.append(list(args))
            return subprocess.CompletedProcess(args, len(calls) == 1, '', DENIED if len(calls) == 1 else '')
        with patch.object(probe.subprocess, 'run', side_effect=execute), contextlib.redirect_stdout(io.StringIO()):
            probe.nested_sandbox(Path('/workspace/kotibot'))
        self.assertEqual(len(calls), 2)
        before = calls[0][:]
        index = before.index('--proc')
        del before[index:index+2]
        self.assertEqual(calls[1], before)
        for option in ('--unshare-user', '--unshare-pid', '--unshare-ipc', '--unshare-net', '--cap-drop', '--ro-bind'):
            self.assertIn(option, calls[1])

    def test_unrelated_error_stops_without_retry(self):
        failure = subprocess.CompletedProcess([], 1, '', 'bwrap: user namespace creation denied')
        with patch.object(probe.subprocess, 'run', return_value=failure) as run:
            with self.assertRaisesRegex(SystemExit, 'user namespace creation denied'):
                probe.nested_sandbox(Path('/workspace/kotibot'))
        self.assertEqual(run.call_count, 1)

    def test_failed_fallback_does_not_report_success(self):
        results = [subprocess.CompletedProcess([], 1, '', DENIED),
                   subprocess.CompletedProcess([], 1, '', 'workspace write failed')]
        output = io.StringIO()
        with patch.object(probe.subprocess, 'run', side_effect=results), contextlib.redirect_stdout(output):
            with self.assertRaisesRegex(SystemExit, 'workspace write failed'):
                probe.nested_sandbox(Path('/workspace/kotibot'))
        self.assertNotIn('PASS', output.getvalue())

    def test_success_needs_no_fallback(self):
        with patch.object(probe.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, '', '')) as run:
            with contextlib.redirect_stdout(io.StringIO()):
                probe.nested_sandbox(Path('/workspace/kotibot'))
        self.assertEqual(run.call_count, 1)

    def test_command_failure_displays_original_diagnostic(self):
        error = subprocess.CalledProcessError(1, ['podman', 'exec'], output='first check passed\n', stderr=DENIED)
        output = io.StringIO()
        with patch.object(greenie.subprocess, 'run', side_effect=error), contextlib.redirect_stderr(output):
            with self.assertRaises(subprocess.CalledProcessError):
                greenie.run('podman', 'exec')
        self.assertIn(DENIED, output.getvalue())
        self.assertIn('first check passed', output.getvalue())

    def test_resume_does_not_build_or_recreate_resources(self):
        calls = []
        def podman(*args, **kwargs):
            calls.append(args)
            if args == ('exec', greenie.NAME, 'git', 'rev-parse', 'HEAD'):
                return 'a'*40
            return ''
        with (patch.object(greenie, 'run', return_value='a'*40),
              patch.object(greenie, 'podman', side_effect=podman),
              patch.object(greenie, 'wait_proxy'), patch.object(greenie, 'container_inspection') as inspection,
              contextlib.redirect_stdout(io.StringIO())):
            greenie.resume(Path('/source'), 'a'*40)
        inspection.assert_called_once_with(name=greenie.NAME)
        self.assertTrue(all(args[0] == 'exec' for args in calls))
        self.assertIn(('exec', greenie.NAME, 'python', '-m', 'tests'), calls)

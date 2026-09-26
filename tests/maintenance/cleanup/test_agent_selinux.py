"""SELinux profile migration must preserve data and fail closed on failed gates."""
import contextlib
import copy
import io
import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

from tools.agent_access import greenie

HEAD = 'a' * 40
OLD = 'b' * 64
NEW = 'c' * 64
IMAGE = 'd' * 64
LEVEL = 's0:c610,c889'


class Engine:
    def __init__(self):
        self.calls = []
        self.items = {OLD: {
            'Id': OLD, 'Image': IMAGE, 'Name': greenie.NAME, 'running': True,
            'ProcessLabel': 'system_u:system_r:container_t:' + LEVEL,
            'Mounts': [
                {'Type': 'bind', 'Source': str(greenie.WORKSPACE.resolve()),
                 'Destination': '/workspace/kotibot'},
                {'Type': 'volume', 'Name': 'kotibot-development-home',
                 'Destination': '/home/developer'}],
            'NetworkSettings': {'Networks': {greenie.NETWORK: {}}},
            'HostConfig': {'Privileged': False, 'PidMode': '', 'ReadonlyRootfs': True,
                           'SecurityOpt': ['no-new-privileges']}}}
        self.rootless = True
        self.fail_create = False
        self.fail_activation = False
        self.fail_old_start_once = False

    def item(self, name):
        return next(item for item in self.items.values()
                    if item['Id'] == name or item['Name'] == name)

    def exists(self, args, **kwargs):
        name = args[-1]
        present = any(item['Name'] == name for item in self.items.values())
        return subprocess.CompletedProcess(args, 0 if present else 1, '', '')

    def __call__(self, *args, **kwargs):
        self.calls.append(args)
        if args[0] == 'inspect':
            return json.dumps([self.item(args[1])])
        if args[:2] == ('network', 'inspect'):
            return json.dumps([{'internal': True}])
        if args[0] == 'info':
            return json.dumps({'host': {'security': {'rootless': self.rootless}}})
        if args[0] == 'exec':
            if args[-3:] == ('git', 'rev-parse', 'HEAD'):
                return HEAD
            return ''
        if args[0] == 'create':
            if self.fail_create:
                raise subprocess.CalledProcessError(1, args)
            value = copy.deepcopy(self.items[OLD])
            value.update(Id=NEW, Name=args[args.index('--name')+1], running=False,
                         ProcessLabel='system_u:system_r:' + greenie.SELINUX_TYPE + ':' + LEVEL)
            self.items[NEW] = value
            return NEW + '\n'
        if args[0] in ('stop', 'start'):
            if args == ('start', OLD) and self.fail_old_start_once:
                self.fail_old_start_once = False
                raise subprocess.CalledProcessError(1, args)
            self.item(args[1])['running'] = args[0] == 'start'
            return args[1]
        if args[0] == 'rename':
            if self.fail_activation and args[1] == NEW and args[2] == greenie.NAME:
                raise subprocess.CalledProcessError(1, args)
            if any(item['Name'] == args[2] for item in self.items.values()):
                raise ValueError('Name already occupied')
            self.item(args[1])['Name'] = args[2]
            return ''
        raise AssertionError(args)


class SelinuxRepairTests(unittest.TestCase):
    def setUp(self):
        self.engine = Engine()
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
        self.stack.enter_context(contextlib.redirect_stderr(io.StringIO()))
        self.stack.enter_context(patch.object(greenie.os, 'geteuid', return_value=1000))
        self.stack.enter_context(patch.object(greenie, 'run', return_value=HEAD))
        self.stack.enter_context(patch.object(greenie, 'podman', side_effect=self.engine))
        self.stack.enter_context(patch.object(greenie.subprocess, 'run', side_effect=self.engine.exists))
        self.resume = self.stack.enter_context(patch.object(greenie, 'resume'))

    def repair(self):
        greenie.repair_selinux(Path('/source'), HEAD)

    def test_verifies_before_activation_and_keeps_original(self):
        def verify(*args, **kwargs):
            self.assertEqual(self.engine.item(greenie.NAME)['Id'], OLD)
            self.assertFalse(self.engine.items[OLD]['running'])
            self.assertTrue(self.engine.items[NEW]['running'])
            self.assertEqual(kwargs['name'], greenie.SELINUX_CANDIDATE)
        self.resume.side_effect = verify
        self.repair()
        self.assertEqual(self.engine.item(greenie.NAME)['Id'], NEW)
        self.assertEqual(self.engine.item(greenie.SELINUX_BACKUP)['Id'], OLD)
        self.assertFalse(self.engine.items[OLD]['running'])
        self.assertTrue(self.engine.items[NEW]['running'])
        create = next(call for call in self.engine.calls if call[0] == 'create')
        self.assertEqual(create[-1], IMAGE)
        self.assertIn('--security-opt=label=type:container_userns_t', create)
        self.assertIn('--security-opt=label=level:' + LEVEL, create)
        self.assertIn('--cap-drop=all', create)
        self.assertIn('--security-opt=no-new-privileges', create)
        self.assertIn('--read-only', create)
        self.assertEqual(create[create.index('--network')+1], greenie.NETWORK)
        self.assertEqual([create[i+1] for i, value in enumerate(create) if value == '-v'],
                         [f'{greenie.WORKSPACE}:/workspace/kotibot:Z',
                          'kotibot-development-home:/home/developer'])
        self.assertTrue(all(call[0] not in ('rm', 'build', 'volume') for call in self.engine.calls))

    def test_failed_denial_or_test_gate_restores_old_and_retains_candidate(self):
        self.resume.side_effect = ValueError('denial/test gate failed')
        with self.assertRaisesRegex(ValueError, 'gate failed'):
            self.repair()
        self.assertEqual(self.engine.item(greenie.NAME)['Id'], OLD)
        self.assertTrue(self.engine.items[OLD]['running'])
        self.assertFalse(self.engine.items[NEW]['running'])
        self.assertEqual(self.engine.item(greenie.SELINUX_CANDIDATE)['Id'], NEW)
        self.assertFalse(any(call[0] == 'rename' for call in self.engine.calls))

    def test_failed_name_activation_restores_old_name_and_service(self):
        self.engine.fail_activation = True
        with self.assertRaises(subprocess.CalledProcessError):
            self.repair()
        self.assertEqual(self.engine.item(greenie.NAME)['Id'], OLD)
        self.assertTrue(self.engine.items[OLD]['running'])
        self.assertFalse(self.engine.items[NEW]['running'])

    def test_failed_create_does_not_stop_original(self):
        self.engine.fail_create = True
        with self.assertRaises(subprocess.CalledProcessError):
            self.repair()
        self.assertTrue(self.engine.items[OLD]['running'])
        self.assertFalse(any(call[0] == 'stop' for call in self.engine.calls))

    def test_existing_recovery_container_blocks_without_mutation(self):
        self.engine.items[NEW] = {'Id': NEW, 'Name': greenie.SELINUX_BACKUP}
        with self.assertRaisesRegex(ValueError, 'already exists'):
            self.repair()
        self.assertFalse(any(call[0] in ('stop', 'create', 'rename') for call in self.engine.calls))

    def test_changed_source_blocks_before_container_changes(self):
        with patch.object(greenie, 'run', return_value='e'*40):
            with self.assertRaisesRegex(ValueError, 'source commit'):
                self.repair()
        self.assertEqual(self.engine.calls, [])

    def test_rootful_engine_is_rejected(self):
        self.engine.rootless = False
        with self.assertRaisesRegex(ValueError, 'Rootless'):
            self.repair()
        self.assertFalse(any(call[0] == 'create' for call in self.engine.calls))

    def test_unexpected_mount_destination_blocks_reconstruction(self):
        self.engine.items[OLD]['Mounts'][0]['Destination'] = '/elsewhere'
        with self.assertRaisesRegex(ValueError, 'mounts differ'):
            self.repair()
        self.assertFalse(any(call[0] == 'create' for call in self.engine.calls))

    def test_unconfined_or_missing_label_cannot_be_repaired(self):
        for label in ('', 'system_u:system_r:spc_t:s0', 'system_u:system_r:container_t:s0'):
            with self.subTest(label=label):
                self.engine.items[OLD]['ProcessLabel'] = label
                with self.assertRaisesRegex(ValueError, 'SELinux'):
                    self.repair()
        self.assertFalse(any(call[0] == 'create' for call in self.engine.calls))

    def test_already_repaired_only_reverifies(self):
        self.engine.items[OLD]['ProcessLabel'] = 'system_u:system_r:container_userns_t:' + LEVEL
        self.repair()
        self.resume.assert_called_once_with(Path('/source'), HEAD)
        self.assertFalse(any(call[0] in ('stop', 'create', 'rename') for call in self.engine.calls))

    def test_rollback_restores_original_without_deleting_new(self):
        self.repair()
        greenie.rollback_selinux()
        self.assertEqual(self.engine.item(greenie.NAME)['Id'], OLD)
        self.assertTrue(self.engine.items[OLD]['running'])
        self.assertEqual(self.engine.item(greenie.SELINUX_CANDIDATE)['Id'], NEW)
        self.assertFalse(self.engine.items[NEW]['running'])
        self.assertFalse(any(call[0] == 'rm' for call in self.engine.calls))

    def test_rollback_rejects_unrelated_backup(self):
        self.repair()
        self.engine.items[OLD]['Image'] = 'f'*64
        self.engine.calls.clear()
        with self.assertRaisesRegex(ValueError, 'does not match'):
            greenie.rollback_selinux()
        self.assertTrue(self.engine.items[NEW]['running'])
        self.assertFalse(any(call[0] in ('stop', 'rename') for call in self.engine.calls))

    def test_inspection_rejects_legacy_profile_and_disabled_seccomp(self):
        with self.assertRaisesRegex(ValueError, 'SELinux'):
            greenie.inspect_configuration()
        self.engine.items[OLD]['ProcessLabel'] = 'system_u:system_r:container_userns_t:' + LEVEL
        self.engine.items[OLD]['HostConfig']['SecurityOpt'].append('seccomp=unconfined')
        with self.assertRaisesRegex(ValueError, 'enforcement is disabled'):
            greenie.inspect_configuration()

    def test_failed_rollback_start_restores_repaired_container(self):
        self.repair()
        self.engine.fail_old_start_once = True
        with self.assertRaises(subprocess.CalledProcessError):
            greenie.rollback_selinux()
        self.assertEqual(self.engine.item(greenie.NAME)['Id'], NEW)
        self.assertTrue(self.engine.items[NEW]['running'])
        self.assertEqual(self.engine.item(greenie.SELINUX_BACKUP)['Id'], OLD)
        self.assertFalse(self.engine.items[OLD]['running'])

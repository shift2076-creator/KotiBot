"""Deployment integrity and development containment failure-path tests."""
import io
import json
import os
from pathlib import Path
import pwd
import subprocess
import tarfile
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tools.agent_access import greenie, releases
from tools import path002_production as production


class ReleaseIntegrityTests(unittest.TestCase):
    def archive(self, entries):
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode='w') as archive:
            for name, content, kind in entries:
                member = tarfile.TarInfo(name)
                member.type = kind
                member.size = len(content) if kind == tarfile.REGTYPE else 0
                archive.addfile(member, io.BytesIO(content))
        return buffer.getvalue()

    def test_export_exact_commit_without_ignored_files(self):
        with TemporaryDirectory() as temp:
            destination = Path(temp)
            payload = self.archive([('app.py', b'print("source")\n', tarfile.REGTYPE)])
            with patch.object(releases, 'git', side_effect=[b'a'*40+b'\n', payload]):
                releases.export_source(Path('/source'), 'a'*40, destination)
            self.assertEqual((destination/'app.py').read_bytes(), b'print("source")\n')
            self.assertEqual(sorted(p.name for p in destination.iterdir()), ['app.py'])

    def test_export_rejects_links_traversal_and_wrong_head_before_writing(self):
        for name, kind in [('../escape', tarfile.REGTYPE), ('/absolute', tarfile.REGTYPE),
                           ('link', tarfile.SYMTYPE), ('device', tarfile.CHRTYPE)]:
            with self.subTest(name=name), TemporaryDirectory() as temp:
                destination = Path(temp)
                payload = self.archive([(name, b'x', kind)])
                with patch.object(releases, 'git', side_effect=[b'a'*40+b'\n', payload]):
                    with self.assertRaises(ValueError):
                        releases.export_source(Path('/source'), 'a'*40, destination)
                self.assertEqual(list(destination.iterdir()), [])
        with patch.object(releases, 'git', return_value=b'b'*40):
            with self.assertRaises(ValueError):
                releases.export_source(Path('/source'), 'a'*40, Path('/unused'))

    def test_environment_copy_detects_changed_original_and_special_files(self):
        with TemporaryDirectory() as temp:
            source = Path(temp)/'old';source.mkdir();(source/'file').write_bytes(b'original')
            target = Path(temp)/'new'
            real_copy = releases.shutil.copytree
            def change(*args, **kwargs):
                value = real_copy(*args, **kwargs)
                (source/'file').write_bytes(b'changed')
                return value
            with patch.object(releases.shutil, 'copytree', side_effect=change):
                with self.assertRaises(ValueError):
                    releases.copy_environment(source, target)
            os.mkfifo(source/'fifo')
            with self.assertRaises(ValueError):
                releases.tree_digest(source)

    @unittest.skipUnless(os.geteuid() == 0, 'Needs an actual alternate UID')
    def test_frozen_release_rejects_real_non_root_writes(self):
        with TemporaryDirectory() as temp:
            root = Path(temp);root.chmod(0o755)
            (root/'source.py').write_bytes(b'keep')
            releases.freeze(root)
            nobody = pwd.getpwnam('nobody')
            probe = 'import os,sys; fd=os.open(sys.argv[1],os.O_WRONLY); os.close(fd)'
            result = subprocess.run(['runuser', '-u', nobody.pw_name, '--', '/usr/bin/python3',
                                     '-I', '-c', probe, str(root/'source.py')], capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual((root/'source.py').read_bytes(), b'keep')


class DeploymentRecoveryTests(unittest.TestCase):
    def test_failed_service_verification_restores_original_dropin_absence(self):
        with TemporaryDirectory() as temp:
            base = Path(temp)/'production';source = Path(temp)/'operator';source.mkdir()
            (source/'requirements.txt').write_text('same dependencies')
            dropin = Path(temp)/'override.conf'
            user = SimpleNamespace(pw_name='fixture', pw_uid=1000)
            def export(_source, _head, destination):
                (destination/'requirements.txt').write_text('same dependencies')
            with (patch.object(production, 'BASE', base), patch.object(production, 'SOURCE', source),
                  patch.object(production, 'DROPIN', dropin),
                  patch.object(production, 'validate_original', return_value=(user, {'state':'/private/state'})),
                  patch.object(production, 'root_owned'), patch.object(production, 'freeze'),
                  patch.object(production, 'copy_environment'),
                  patch.object(production, 'export_source', side_effect=export),
                  patch.object(production, 'audit_virtualenv', return_value=SimpleNamespace(contaminated=False)),
                  patch.object(production, 'command') as command,
                  patch.object(production.time, 'sleep'),
                  patch.object(production, 'verify', side_effect=ValueError('failed startup'))):
                with self.assertRaisesRegex(ValueError, 'failed startup'):
                    production.install('a'*40)
            self.assertFalse(dropin.exists())
            self.assertFalse((base/'deployment.json').exists())
            self.assertTrue((base/'releases'/('a'*40)).is_dir())
            self.assertEqual(sum(call.args == ('systemctl','restart','kotibot.service')
                                 for call in command.call_args_list), 2)

    def test_changed_dropin_blocks_rollback_without_mutation(self):
        with TemporaryDirectory() as temp:
            dropin = Path(temp)/'override';dropin.write_bytes(b'operator edit')
            with patch.object(production, 'DROPIN', dropin), patch.object(production, 'command') as command:
                with self.assertRaises(ValueError):
                    production.rollback({'head': 'a'*40})
            command.assert_not_called()
            self.assertEqual(dropin.read_bytes(), b'operator edit')

    def test_old_interpreter_blocks_verification_even_with_new_working_directory(self):
        release = Path('/opt/kotibot/releases/fixture')
        properties = {'WorkingDirectory':str(release), 'User':'fixture', 'MainPID':'42'}
        with (patch.object(production, 'prop', side_effect=properties.__getitem__),
              patch.object(production.pwd, 'getpwnam', return_value=SimpleNamespace(pw_name='fixture')),
              patch.object(Path, 'read_bytes', side_effect=[production.configuration(release), b'/old/python\0-m\0waitress\0'])):
            with self.assertRaisesRegex(ValueError, 'interpreter'):
                production.verify(release, {'user':'fixture'})

    def test_release_configuration_preserves_existing_restart_privileges(self):
        config = production.configuration(Path('/opt/kotibot/releases/fixture')).decode()
        self.assertIn('--threads=12', config)
        self.assertIn('PYTHONDONTWRITEBYTECODE=1', config)
        self.assertNotIn('NoNewPrivileges', config)
        self.assertNotIn('User=', config)
        self.assertNotIn('LoadCredential', config)


class DevelopmentContainmentTests(unittest.TestCase):
    def container(self):
        return {'Mounts':[{'Type':'bind','Source':str(greenie.WORKSPACE.resolve())}],
                'ProcessLabel':'system_u:system_r:container_userns_t:s0:c610,c889',
                'NetworkSettings':{'Networks':{greenie.NETWORK:{}}},
                'HostConfig':{'Privileged':False,'PidMode':'','ReadonlyRootfs':True,'SecurityOpt':['no-new-privileges']}}

    def test_host_mount_or_network_blocks_agent(self):
        for change in ('mount', 'network', 'privileged', 'hostpid'):
            with self.subTest(change=change):
                value=self.container()
                if change=='mount': value['Mounts'].append({'Type':'bind','Source':'/var/mnt/kotibot'})
                if change=='network': value['NetworkSettings']['Networks']['outside']={}
                if change=='privileged': value['HostConfig']['Privileged']=True
                if change=='hostpid': value['HostConfig']['PidMode']='host'
                with patch.object(greenie, 'podman', side_effect=[json.dumps([value]),json.dumps([{'internal':True}])]):
                    with self.assertRaises(ValueError): greenie.container_inspection()

    def test_proxy_cannot_be_bypassed_by_non_internal_network(self):
        with patch.object(greenie, 'podman', side_effect=[json.dumps([self.container()]),json.dumps([{'internal':False}])]):
            with self.assertRaises(ValueError): greenie.container_inspection()

    def test_desktop_launcher_strips_authority_from_environment(self):
        with patch.dict(os.environ, {'SSH_AUTH_SOCK':'private','GIT_ASKPASS':'private',
                                      'TAPO_PASSWORD':'private','KOTIBOT_DATA_DIR':'private','GH_TOKEN':'private','OPENAI_API_KEY':'private'}, clear=False):
            environment=greenie.clean_environment()
        for key in ('SSH_AUTH_SOCK','GIT_ASKPASS','TAPO_PASSWORD','KOTIBOT_DATA_DIR','GH_TOKEN','OPENAI_API_KEY'):
            self.assertNotIn(key,environment)
        self.assertEqual(environment['GIT_CONFIG_GLOBAL'], os.devnull)

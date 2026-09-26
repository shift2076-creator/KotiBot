"""State failure/recovery regressions using disposable documents and threads."""
import ast
from copy import deepcopy
import json
from pathlib import Path
from queue import Empty, Full, Queue
from tempfile import TemporaryDirectory
from threading import Event, RLock, Thread
import unittest
from unittest.mock import Mock, patch

from flask import Flask
from server_core import io, state
from server_core.routes import register_server_routes

SOURCE_ROOT = Path(__file__).resolve().parents[3]


class StateIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.writer = patch.object(io, 'start_json_writer')
        self.writer.start()
        self.files = {name: self.root / f'{name}.json' for name in
                      ('server', 'actions', 'automations', 'tapo', 'matter', 'android')}
        self.saved_clients = [
            dict(deviceID='tapo:1', clientName='Plug', clientRole='TAPO', source='tapo', provisioned=True),
            dict(deviceID='matter:1', clientName='Sensor', clientRole='DSS', source='matter', provisioned=True),
            dict(deviceID='android:1', clientName='Camera', clientRole='CAM', provisioned=True),
        ]
        self.documents = {
            'server': {'clients': self.saved_clients, 'system': {'armed': True, 'arm_state': 'night'}},
            'actions': {'actions': [{'from_deviceID': 'matter:1', 'action': 'device'}]},
            'automations': {'routes': [{'from_deviceID': 'android:1', 'action': 'device'}]},
            'tapo': {'devices': {'tapo:1': {'tapo_id': '1'}}},
            'matter': {'devices': {'matter:1': {'matter_node_id': '1', 'doorbell_muted': True}}},
            'android': {'clients': {'android:1': {'selected_camera': 'front'}}},
        }
        for name, document in self.documents.items():
            self.write(name, document)
        self.clients = {'existing': dict(deviceID='existing', clientName='Existing', clientRole='KEY', provisioned=True)}
        self.routes = [{'existing': True}]
        self.system = [False, 'day']
        self.lock = RLock()
        self.ctx = dict(
            clients=self.clients, routes=self.routes, state_lock=self.lock,
            state_file=self.files['server'], security_actions_file=self.files['actions'],
            automation_state_file=self.files['automations'], tapo_device_state_file=self.files['tapo'],
            matter_device_state_file=self.files['matter'], android_home_state_file=self.files['android'],
            automation_type_tapo_recharge='recharge', automation_type_device_routes='routes',
            client_role_cam='CAM', client_role_dss='DSS', client_role_key='KEY', client_role_tapo='TAPO',
            open_angle_threshold=15, close_angle_threshold=5,
            client_has_role=lambda c, role: role in (c.get('clientRole') if isinstance(c.get('clientRole'), list) else [c.get('clientRole')]),
            clean_arm_state=lambda value: str(value or 'day'), clean_zone_name=lambda value: str(value or ''),
            init_client=lambda device: {'deviceID': device},
            set_routes=lambda value: self.routes.__setitem__(slice(None), value),
            set_system_arm_state=lambda armed, mode: self.system.__setitem__(slice(None), [armed, mode]),
            system_armed=lambda: self.system[0], system_arm_state=lambda: self.system[1],
            broadcast_state=Mock(),
        )

    def tearDown(self):
        self.writer.stop()
        with io._PENDING_LOCK:
            for mapping in (io._PENDING_WRITES, io._FLUSHING_WRITES, io._FAILED_READS):
                for path in list(mapping):
                    if path.parent == self.root:
                        mapping.pop(path, None)
        self.temp.cleanup()

    def write(self, name, document):
        self.files[name].write_text(json.dumps(document), encoding='utf-8')

    def pending(self):
        with io._PENDING_LOCK:
            return {path: deepcopy(value) for path, value in io._PENDING_WRITES.items()
                    if path.parent == self.root}

    def assert_load_preserves_everything(self, runtime=None):
        runtime = runtime or state.build_state_runtime(self.ctx)
        memory = deepcopy((self.clients, self.routes, self.system))
        disk = {p.name: p.read_bytes() for p in self.root.iterdir() if p.is_file()}
        queued = self.pending()
        with self.assertLogs(state.LOGGER, level='ERROR'):
            self.assertFalse(runtime['load_state']())
        self.assertEqual((self.clients, self.routes, self.system), memory)
        self.assertEqual(self.pending(), queued)
        io.flush_json_writes()
        self.assertEqual({p.name: p.read_bytes() for p in self.root.iterdir() if p.is_file()}, disk)

    def test_corrupt_main_cannot_erase_healthy_subsystems(self):
        self.files['server'].write_text('{broken', encoding='utf-8')
        self.assert_load_preserves_everything()

    def test_corrupt_companion_files_cannot_publish_partial_state(self):
        for name in ('actions', 'automations', 'tapo', 'matter', 'android'):
            with self.subTest(name=name):
                self.files[name].write_text('{broken', encoding='utf-8')
                self.assert_load_preserves_everything()
                self.write(name, self.documents[name])

    def test_unreadable_input_preserves_state(self):
        read = state.read_json_object
        def unreadable(path):
            if path == self.files['matter']:
                raise io.JsonStateUnreadableError(path)
            return read(path)
        with patch.object(state, 'read_json_object', side_effect=unreadable):
            self.assert_load_preserves_everything()

    def test_missing_main_with_existing_subsystems_is_not_a_new_install(self):
        self.files['server'].unlink()
        self.assert_load_preserves_everything()

    def test_missing_primary_with_backup_requires_recovery(self):
        for name in self.files:
            with self.subTest(name=name):
                backup = io.json_backup_path(self.files[name])
                backup.write_bytes(self.files[name].read_bytes())
                self.files[name].unlink()
                self.assert_load_preserves_everything()
                self.write(name, self.documents[name])
                backup.unlink()

    def test_invalid_client_schema_is_rejected_without_writes(self):
        for bad_clients in (42, None, 'invalid', [None], [{'deviceID': 5}],
                            [self.saved_clients[0], self.saved_clients[0]], {'matter': {}},
                            [{**self.saved_clients[0], 'clientRole': {'invalid': True}}]):
            with self.subTest(clients=bad_clients):
                self.write('server', {'clients': bad_clients})
                self.assert_load_preserves_everything()

    def test_missing_client_root_or_invalid_system_is_rejected(self):
        for doc in ({}, {'system': {}}, {'clients': [], 'system': []},
                    {'clients': [], 'system': {'armed': 'false'}},
                    {'clients': [], 'system': {'arm_state': 'invalid'}}):
            with self.subTest(document=doc):
                self.write('server', doc)
                self.assert_load_preserves_everything()

    def test_invalid_subsystem_or_route_schema_is_rejected(self):
        cases = [('matter', {'devices': []}), ('android', {'clients': {'android:1': 42}}),
                 ('tapo', {'wrong_root': {'tapo:1': {}}}), ('actions', {'actions': 'bad'}),
                 ('automations', {'routes': [42]}), ('automations', {'recharge': []})]
        for name, document in cases:
            with self.subTest(name=name, document=document):
                self.write(name, document)
                self.assert_load_preserves_everything()
                self.write(name, self.documents[name])

    def test_orphaned_subsystem_records_are_preserved_for_recovery(self):
        self.write('tapo', {'devices': {'missing-from-main': {'tapo_id': '1'}}})
        self.assert_load_preserves_everything()

    def test_late_client_conversion_failure_cannot_partly_replace_registry(self):
        self.write('matter', {'devices': {'matter:1': {'openness_score': 'invalid'}}})
        self.assert_load_preserves_everything()

    def test_load_can_retry_after_input_is_repaired(self):
        runtime = state.build_state_runtime(self.ctx)
        self.files['server'].write_text('{broken', encoding='utf-8')
        self.assert_load_preserves_everything(runtime)
        self.assert_load_preserves_everything(runtime)
        self.write('server', self.documents['server'])
        self.assertTrue(runtime['load_state']())
        self.assertEqual(set(self.clients), {'tapo:1', 'matter:1', 'android:1'})
        self.assertEqual(self.system, [True, 'night'])
        self.assertEqual(len(self.routes), 2)
        self.assertTrue(self.clients['matter:1']['doorbell_muted'])
        self.assertIsNone(self.clients['matter:1']['matter_reachable'])
        io.flush_json_writes()
        self.assertEqual(json.loads(self.files['matter'].read_text())['devices']['matter:1']['matter_node_id'], '1')

    def test_new_install_with_no_saved_state_initializes_successfully(self):
        for path in self.files.values():
            path.unlink()
        self.clients.clear()
        self.routes.clear()
        self.assertTrue(state.build_state_runtime(self.ctx)['load_state']())
        self.assertEqual(set(self.pending()), set(self.files.values()))
        io.flush_json_writes()
        self.assertTrue(all(path.is_file() for path in self.files.values()))

    def test_rejected_load_batch_rolls_back_published_memory(self):
        with patch.object(state, 'write_json_batch_atomic', side_effect=OSError('fixture failure')):
            self.assert_load_preserves_everything()

    def test_broadcast_failure_does_not_prevent_a_save(self):
        self.ctx['broadcast_state'].side_effect = ValueError('fixture publication failure')
        with self.assertLogs(state.LOGGER, level='ERROR'):
            self.assertTrue(state.build_state_runtime(self.ctx)['save_state']())
        self.assertEqual(len(self.pending()), 6)
        io.flush_json_writes()
        persisted = json.loads(self.files['server'].read_text())
        self.assertEqual(persisted['clients']['android_key'][0]['deviceID'], 'existing')

    def test_rejected_save_is_visible_and_preserves_legacy_migration_input(self):
        self.clients['existing']['tapo_recharge'] = {'enabled': True}
        with patch.object(state, 'write_json_batch_atomic', side_effect=OSError('private fixture value')):
            with self.assertLogs(state.LOGGER, level='ERROR') as captured:
                with self.assertRaises(state.StateSaveError):
                    state.build_state_runtime(self.ctx)['save_state']()
        self.assertIn('tapo_recharge', self.clients['existing'])
        self.ctx['broadcast_state'].assert_not_called()
        self.assertNotIn('private fixture value', '\n'.join(captured.output))

    def test_batch_validation_failure_leaves_existing_queue_unchanged(self):
        io.write_json_batch_atomic({self.files['server']: {'previous': True}})
        previous = self.pending()
        with self.assertRaises(TypeError):
            io.write_json_batch_atomic({self.files['actions']: {'new': True}, self.files['server']: {'bad': object()}})
        self.assertEqual(self.pending(), previous)

    def test_blocked_batch_member_prevents_every_new_queue_update(self):
        io.write_json_batch_atomic({self.files['actions']: {'actions': [{'previous': True}]}})
        previous = self.pending()
        self.files['server'].write_text('{broken', encoding='utf-8')
        with self.assertLogs('kotibot.persistence', level='WARNING'):
            with self.assertRaises(io.JsonStateInvalidError):
                io.read_json_object(self.files['server'])
        with self.assertRaises(io.JsonStateWriteBlockedError):
            io.write_json_batch_atomic({self.files['actions']: {'actions': []}, self.files['server']: {'clients': []}})
        self.assertEqual(self.pending(), previous)

    def test_accepted_batch_is_detached_from_later_caller_mutation(self):
        document = {'clients': [{'deviceID': 'fixture'}]}
        io.write_json_batch_atomic({self.files['server']: document})
        document['clients'].clear()
        self.assertEqual(io.read_json_object(self.files['server'])['clients'], [{'deviceID': 'fixture'}])

    def test_writer_start_failure_cannot_partly_accept_a_batch(self):
        with patch.object(io, 'start_json_writer', side_effect=RuntimeError('fixture writer failure')):
            with self.assertRaises(RuntimeError):
                io.write_json_batch_atomic({self.files['server']: {'clients': []}})
        self.assertEqual(self.pending(), {})

    def test_concurrent_registry_change_waits_for_complete_save_snapshot(self):
        entered, release, mutated = Event(), Event(), Event()
        original_role = self.ctx['client_has_role']
        paused = False
        def role(client, requested):
            nonlocal paused
            if not paused:
                paused = True
                entered.set()
                if not release.wait(2):
                    raise TimeoutError('fixture coordination')
            return original_role(client, requested)
        self.ctx['client_has_role'] = role
        runtime = state.build_state_runtime(self.ctx)
        errors = []
        def save():
            try:
                runtime['save_state']()
            except Exception as error:
                errors.append(error)
        def mutate():
            with self.lock:
                self.clients['new'] = dict(deviceID='new', clientRole='KEY', provisioned=True)
                mutated.set()
        saver = Thread(target=save, daemon=True)
        modifier = Thread(target=mutate, daemon=True)
        saver.start()
        try:
            self.assertTrue(entered.wait(2))
            modifier.start()
            self.assertFalse(mutated.wait(.05))
        finally:
            release.set()
            saver.join(2)
            if modifier.ident is not None:
                modifier.join(2)
        self.assertFalse(saver.is_alive())
        self.assertFalse(modifier.is_alive())
        self.assertEqual(errors, [])
        accepted = io.read_json_object(self.files['server'])
        self.assertEqual([c['deviceID'] for c in accepted['clients']['android_key']], ['existing'])
        with self.lock:
            self.assertTrue(runtime['save_state']())
        self.assertEqual(len(io.read_json_object(self.files['server'])['clients']['android_key']), 2)

    def test_metadata_save_rejection_returns_503_and_restores_metadata(self):
        app = Flask('state-save-fixture')
        runtime = state.build_state_runtime(self.ctx)
        original = deepcopy(self.clients)
        ctx = dict(self.ctx, sse_listeners=[], save_state=runtime['save_state'], current_status_payload=Mock())
        register_server_routes(app, ctx)
        with patch.object(state, 'write_json_batch_atomic', side_effect=OSError('fixture disk failure')):
            with self.assertLogs(state.LOGGER, level='ERROR'):
                response = app.test_client().post('/api/client-metadata', json={'deviceID': 'existing', 'clientName': 'Changed', 'zoneName': 'Changed'})
        self.assertEqual(response.status_code, 503)
        self.assertFalse(response.get_json()['ok'])
        self.assertEqual(self.clients, original)
        ctx['current_status_payload'].assert_not_called()
        ctx['broadcast_state'].assert_not_called()

    def test_failed_startup_never_reaches_subsystem_workers(self):
        tree = ast.parse((SOURCE_ROOT / 'kotibot_server.py').read_text())
        index = next(i for i, node in enumerate(tree.body) if isinstance(node, ast.If)
                     and isinstance(node.test, ast.UnaryOp) and isinstance(node.test.operand, ast.Call)
                     and isinstance(node.test.operand.func, ast.Name) and node.test.operand.func.id == 'load_state')
        end = next(i for i in range(index, len(tree.body)) if isinstance(tree.body[i], ast.FunctionDef))
        startup = compile(ast.Module(body=tree.body[index:end], type_ignores=[]), '<startup fixture>', 'exec')
        workers = {key: Mock() for key in ('normalize_after_state_load', 'start_registered_subsystem_loops', 'start_external_ip_loop')}
        env = dict(load_state=lambda: False, _SUBSYSTEM_RUNTIME=workers, STATE_LOCK=self.lock,
                   prune_invalid_routes_for_clients=lambda: False, save_state=Mock(),
                   sync_arming_motion_detection=Mock(), Thread=Mock(), health_check_loop=Mock())
        with self.assertRaisesRegex(RuntimeError, 'startup stopped'):
            exec(startup, env)
        for worker in workers.values():
            worker.assert_not_called()
        env['load_state'] = lambda: True
        exec(startup, env)
        for worker in workers.values():
            worker.assert_called_once()

    def test_broadcast_waits_for_shared_state_lock(self):
        tree = ast.parse((SOURCE_ROOT / 'kotibot_server.py').read_text())
        function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'broadcast_state')
        entered = Event()
        def payload():
            entered.set()
            return {'clients': []}
        env = dict(STATE_LOCK=self.lock, SSE_LISTENERS=[Queue(1)], current_status_payload=payload,
                   json=json, Empty=Empty, Full=Full)
        exec(compile(ast.Module(body=[function], type_ignores=[]), '<broadcast fixture>', 'exec'), env)
        with self.lock:
            worker = Thread(target=env['broadcast_state'], daemon=True)
            worker.start()
            self.assertFalse(entered.wait(.05))
        worker.join(2)
        self.assertFalse(worker.is_alive())
        self.assertTrue(entered.is_set())
        self.assertEqual(json.loads(env['SSE_LISTENERS'][0].get_nowait()), {'clients': []})

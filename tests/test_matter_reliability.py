"""Behavioral regressions for Matter startup, subscriptions, and delivery.

Uses synthetic device data, real Flask routes, and controlled process output.
It does not commission devices, contact hardware, or read production state.
"""
import inspect
import io
import logging
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event, Lock, Thread
import time
import unittest
from unittest.mock import Mock, patch

from flask import Flask
from server_core import state
from server_core.status import build_status_runtime
from subsystems.matter import matter_routes, matter_runtime


class MatterColdStartTests(unittest.TestCase):
    def test_reload_clears_observations_and_preserves_user_configuration(self):
        clients, routes = {}, []
        stored = {
            'deviceID': 'matter:1:1', 'source': 'matter', 'clientRole': 'DSS',
            'clientName': 'Fixture', 'zone_name': 'Test', 'provisioned': True,
        }
        live = {
            'matter_node_id': '1', 'matter_endpoint': '1',
            'matter_last_sync_at': 999, 'matter_reachable': True,
            'motion_active': True, 'occupancy_state_value': 1,
            'contact_open': True, 'contact_state_value': False,
            'temperature_c': 25, 'humidity_percent': 50,
            'matter_onoff': True, 'door_status': 'open',
            'doorbell_muted': True,
        }
        docs = {'server': {'clients': [stored]},
                'matter': {'devices': {stored['deviceID']: live}}}
        ctx = {
            'clients': clients, 'routes': routes, 'state_file': 'server',
            'security_actions_file': 'security', 'tapo_device_state_file': 'tapo',
            'matter_device_state_file': 'matter', 'android_home_state_file': 'android',
            'automation_state_file': 'automations',
            'automation_type_tapo_recharge': 'recharge',
            'automation_type_device_routes': 'routes',
            'client_role_cam': 'CAM', 'client_role_dss': 'DSS',
            'client_role_key': 'KEY', 'client_role_tapo': 'TAPO',
            'open_angle_threshold': 30, 'close_angle_threshold': 10,
            'client_has_role': lambda c, role: c.get('clientRole') == role,
            'clean_arm_state': lambda value: value,
            'clean_zone_name': lambda value: value or '',
            'init_client': lambda device: {'deviceID': device},
            'set_routes': lambda value: routes.extend(value),
            'set_system_arm_state': Mock(), 'broadcast_state': Mock(),
            'system_armed': False, 'system_arm_state': 'day',
        }
        with patch.object(state, 'read_json_object', side_effect=lambda p: docs.get(p, {})), \
             patch.object(state, 'write_json_atomic'):
            runtime = state.build_state_runtime(ctx)
            self.assertTrue(runtime['load_state']())
        client = clients[stored['deviceID']]
        self.assertEqual(client['matter_last_sync_at'], 0)
        for field in ('motion_active', 'contact_open', 'matter_onoff', 'temperature_c', 'matter_reachable'):
            self.assertIsNone(client[field], field)
        self.assertEqual(client['door_status'], 'unknown')
        self.assertEqual(client['clientName'], 'Fixture')
        self.assertEqual(client['zone_name'], 'Test')
        self.assertTrue(client['doorbell_muted'])
        self.assertEqual(client['matter_node_id'], '1')

    def test_fresh_sibling_does_not_make_unknown_or_unreachable_endpoint_live(self):
        clients = {'a': {'source': 'matter', 'matter_node_id': '1', 'matter_last_sync_at': 999}}
        ctx = dict(clients=clients, preview_viewer_ttl_seconds=30,
                   stale_client_seconds=60, matter_stale_client_seconds=375,
                   server_start_epoch=1000, now_epoch=lambda: 1000,
                   client_has_role=lambda c, r: False)
        for key in ('client_role_cam', 'client_role_dss', 'client_role_key', 'client_role_tapo', 'client_role_unp'):
            ctx[key] = key
        for key in ('age_text', 'clean_filename_part', 'clean_zone_name', 'duration_text', 'now_local', 'voice_talk_active_for_target'):
            ctx[key] = Mock()
        stale = build_status_runtime(ctx)['is_client_stale']
        self.assertTrue(stale({'source': 'matter', 'matter_node_id': '1', 'matter_last_sync_at': 0}))
        self.assertTrue(stale({**clients['a'], 'matter_reachable': False}))
        self.assertFalse(stale(clients['a']))


class MatterRouteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.stop = Event()
        self.clients = {}
        self.clock = 1000
        self.motion, self.door, self.environment = Mock(return_value=False), Mock(return_value=False), Mock(return_value=False)
        self.save, self.broadcast = Mock(), Mock()
        self.runtime = Mock()
        self.runtime.read_state.return_value = {}
        self.runtime.snapshot_all.return_value = {'ok': False, 'snapshots': []}
        self.runtime.matter_node_ids.return_value = ['1', '2']
        self.app = Flask(__name__)
        self.app.logger.setLevel(logging.CRITICAL)
        with patch.object(matter_routes, 'MatterRuntime', return_value=self.runtime):
            matter_routes.register_matter_routes(self.app, {
                'matter_state_file': root / 'state' / 'matter.json',
                'matter_controller_storage_dir': root / 'controller',
                'matter_subscription_storage_dir': root / 'subscriptions',
                'now_epoch': lambda: self.clock, 'clients': self.clients,
                'state_lock': Lock(), 'save_state': self.save, 'broadcast_state': self.broadcast,
                'matter_sync_stop': self.stop, 'fire_camera_motion_routes': self.motion,
                'fire_door_routes': self.door, 'fire_environment_routes': self.environment,
            })
        self.loop = self.app.config['KOTIBOT_MATTER_SENSOR_SUBSCRIBE_LOOP']
        closure = inspect.getclosurevars(self.loop).nonlocals
        self.apply = closure['_apply_matter_sensor_event']
        self.restart = closure['matter_subscription_restart']
        self.addCleanup(self.stop.set)
        self.addCleanup(self.restart.set)

    def client(self, endpoint='1', **values):
        client = dict(deviceID=f'matter:1:{endpoint}', source='matter', matter_node_id='1',
                      matter_endpoint=endpoint, matter_last_sync_at=0, clientName='Fixture')
        client.update(values)
        self.clients[client['deviceID']] = client
        return client

    def event(self, kind, **values):
        return dict(kind=kind, node_id='1', endpoint='1', received_at=self.clock, **values)

    def test_motion_baseline_duplicate_and_real_edges(self):
        c = self.client(motion_active=False)
        self.apply(self.event('motion', occupancy_state_value=1, baseline=True))
        self.assertTrue(c['motion_active'])
        self.motion.assert_not_called()
        self.apply(self.event('motion', occupancy_state_value=1))
        self.motion.assert_not_called()
        self.apply(self.event('motion', occupancy_state_value=0))
        self.apply(self.event('motion', occupancy_state_value=0))
        self.apply(self.event('motion', occupancy_state_value=1))
        self.assertEqual([call.args[1] for call in self.motion.call_args_list], [False, True])
        self.apply(self.event('motion', occupancy_state_value=0, baseline=True))
        self.assertEqual(self.motion.call_count, 2)

    def test_contact_and_environment_reconnect_are_baselines(self):
        self.client(contact_open=False, door_status='closed', temperature_c=20)
        self.apply(self.event('contact', contact_state_value=False, baseline=True))
        self.apply(self.event('temperature', temperature_raw=2200, baseline=True))
        self.door.assert_not_called()
        self.environment.assert_not_called()
        self.apply(self.event('contact', contact_state_value=True))
        self.apply(self.event('temperature', temperature_raw=2300))
        self.door.assert_called_once()
        self.environment.assert_called_once()

    def test_bulb_reports_and_quiet_reports_keep_initialized_devices_current(self):
        bulb = self.client(matter_onoff=None)
        unknown = self.client('2')
        unreachable = self.client('3', matter_last_sync_at=500, matter_reachable=False)
        self.apply(self.event('switch', matter_onoff=True, baseline=True))
        self.assertTrue(bulb['matter_onoff'])
        self.clock += 300
        self.save.reset_mock()
        self.apply(self.event('report'))
        self.assertEqual(bulb['matter_last_sync_at'], self.clock)
        self.assertEqual(unknown['matter_last_sync_at'], 0)
        self.assertEqual(unreachable['matter_last_sync_at'], 500)
        self.save.assert_not_called()
        self.broadcast.assert_called()

    def test_reachability_is_authoritative(self):
        c = self.client(matter_last_sync_at=900)
        self.apply(self.event('reachable', matter_reachable=False))
        self.assertIs(c['matter_reachable'], False)
        self.apply(self.event('reachable', matter_reachable=True))
        self.assertIs(c['matter_reachable'], True)

    def snapshot(self, children):
        self.runtime.snapshot_all.return_value = {'ok': True, 'snapshots': [
            {'ok': True, 'node_id': '1', 'children': children}]}
        return self.app.test_client().post('/api/matter/sync', json={}).get_json()

    def test_failed_endpoint_read_does_not_mark_it_live(self):
        c = self.client()
        result = self.snapshot([{'endpoint': '1', 'kinds': ['switch'],
                                'reads': {'switch': {'ok': False, 'parsed': False}}}])
        self.assertFalse(result['ok'])
        self.assertEqual(c['matter_last_sync_at'], 0)

    def test_partial_contact_read_stays_unknown_and_does_not_fire(self):
        self.client(door_status='open', contact_open=True)
        result = self.snapshot([{'endpoint': '1', 'kinds': ['contact', 'temperature'],
                                'temperature_c': 22, 'contact_state_value': None,
                                'reads': {'contact': {'ok': False, 'parsed': False},
                                          'temperature': {'ok': True, 'parsed': True}}}])
        self.assertTrue(result['ok'])
        self.assertEqual(self.clients['matter:1:1']['door_status'], 'unknown')
        self.assertIsNone(self.clients['matter:1:1']['contact_open'])
        self.door.assert_not_called()

    def test_nodes_run_concurrently_and_sync_drains_them(self):
        started = {node: Event() for node in ('1', '2')}
        active, lock = set(), Lock()
        def subscribe(payload, callback, stop):
            node = payload['node_id']
            with lock:
                active.add(node)
            started[node].set()
            while not stop.is_set():
                self.stop.wait(0.01)
            with lock:
                active.remove(node)
            return {'ok': True, 'event_count': 0}
        self.runtime.subscribe_sensor_states.side_effect = subscribe
        self.app.config['KOTIBOT_MATTER_SYNC_LOOP']()
        thread = Thread(target=self.loop, daemon=True)
        thread.start()
        try:
            self.assertTrue(started['1'].wait(2))
            self.assertTrue(started['2'].wait(2))
            def snapshot(_payload):
                with lock:
                    self.assertEqual(active, set())
                return {'ok': False, 'snapshots': []}
            self.runtime.snapshot_all.side_effect = snapshot
            response = self.app.test_client().post('/api/matter/sync', json={})
            self.assertEqual(response.status_code, 200)
        finally:
            self.stop.set()
            self.restart.set()
            thread.join(3)
        self.assertFalse(thread.is_alive())

    def test_failed_node_recovers_while_other_node_keeps_running(self):
        started, recovered, attempts = Event(), Event(), []
        def subscribe(payload, callback, stop):
            node = payload['node_id']
            if node == '2':
                attempts.append(node)
                if len(attempts) == 1:
                    return {'ok': False, 'event_count': 0}
                recovered.set()
            else:
                started.set()
            while not stop.is_set():
                self.stop.wait(0.01)
            return {'ok': True, 'event_count': 1}
        self.runtime.subscribe_sensor_states.side_effect = subscribe
        self.app.config['KOTIBOT_MATTER_SYNC_LOOP']()
        with patch.dict('os.environ', {'KOTIBOT_MATTER_SENSOR_SUBSCRIBE_RETRY_SECONDS': '5'}):
            thread = Thread(target=self.loop, daemon=True)
            thread.start()
            try:
                self.assertTrue(started.wait(2))
                self.assertTrue(recovered.wait(6))
                self.assertEqual(len(attempts), 2)
            finally:
                self.stop.set()
                self.restart.set()
                thread.join(3)
        self.assertFalse(thread.is_alive())


class FakeProcess:
    def __init__(self, lines):
        self.stdin = io.StringIO()
        self.stdout = lines
        self.returncode = 0
    def poll(self): return self.returncode
    def wait(self, timeout=None): return self.returncode
    def terminate(self): self.returncode = -15
    def kill(self): self.returncode = -9


class MatterProcessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.runtime = matter_runtime.MatterRuntime(root, controller_storage_dir=root/'controller',
            subscription_storage_dir=root/'subscriptions', now_epoch=lambda: 1000)
        self.root = root

    def subscribe(self, children, lines):
        process, events = FakeProcess(lines), []
        with patch.object(self.runtime, '_cached_matter_children', return_value=children), \
             patch.object(self.runtime, 'read_state', return_value={}), \
             patch.object(self.runtime, 'chip_tool_subscription_storage_dir', return_value=self.root), \
             patch.object(matter_runtime.subprocess, 'Popen', return_value=process):
            self.last_result = self.runtime.subscribe_sensor_states({'node_id': '1', 'max_interval': 300}, events.append)
        return process.stdin.getvalue(), events

    def test_bulb_subscription_parses_onoff_and_reachability(self):
        command, events = self.subscribe([{'endpoint': '1', 'kinds': ['switch'],
            'bridged_basic': {'reachable': True}}], [
            'ReportDataMessage =\n', 'Endpoint: 1\n', 'Cluster: 0x0006\n', 'OnOff: TRUE\n',
            'Endpoint: 1\n', 'Cluster: 0x0039\n', 'Reachable: FALSE\n'])
        self.assertIn('0x6,0x39', command)
        self.assertEqual([e['kind'] for e in events], ['report', 'switch', 'reachable'])
        self.assertTrue(events[1]['matter_onoff'])
        self.assertFalse(events[2]['matter_reachable'])

    def test_occupancy_baseline_then_decimal_and_hex_edges(self):
        _, events = self.subscribe([{'endpoint': '1', 'kinds': ['motion']}], [
            'Endpoint: 1\n', 'Cluster: 0x0406\n', 'Occupancy: 0x01\n',
            'Occupancy: 0\n', 'Occupancy: 1\n'])
        self.assertEqual([e['occupancy_state_value'] for e in events], [1, 0, 1])
        self.assertEqual([e['baseline'] for e in events], [True, False, False])

    def test_new_report_does_not_inherit_old_endpoint_context(self):
        _, events = self.subscribe([{'endpoint': '1', 'kinds': ['motion']}], [
            'Endpoint: 1\n', 'Cluster: 0x0406\n', 'Occupancy: 1\n',
            'ReportDataMessage =\n', 'Occupancy: 0\n'])
        self.assertEqual([e['kind'] for e in events], ['motion', 'report'])

    def test_cached_discovery_with_failed_live_reads_is_not_success(self):
        with patch.object(self.runtime, 'discover_endpoints', return_value={
                'ok': True, 'source': 'cache', 'children': [{'endpoint': '1', 'kinds': ['switch']}]}), \
             patch.object(self.runtime, '_run_chip_tool', return_value={'ok': False, 'stdout': 'OnOff: TRUE'}):
            result = self.runtime.snapshot({'node_id': '1'})
        self.assertFalse(result['ok'])
        self.assertIsNone(result['children'][0]['matter_onoff'])

    def test_console_noise_does_not_prevent_subscription_timeout(self):
        with patch.object(matter_runtime.time, 'monotonic', side_effect=[0, 1, 1000]):
            _, events = self.subscribe([{'endpoint': '1', 'kinds': ['motion']}],
                                       ['noise\n', 'more noise\n'])
        self.assertEqual(events, [])
        self.assertIn('inactive', self.last_result['error'])

    def test_quiet_report_frames_refresh_watchdog_without_attribute_changes(self):
        with patch.object(matter_runtime.time, 'monotonic',
                          side_effect=[0, 300, 300, 600, 600, 900, 900, 1000]):
            _, events = self.subscribe([{'endpoint': '1', 'kinds': ['switch']}],
                                       ['ReportDataMessage =\n'] * 3)
        self.assertEqual([event['kind'] for event in events], ['report'] * 3)
        self.assertNotIn('inactive', self.last_result['error'])


if __name__ == '__main__':
    unittest.main()

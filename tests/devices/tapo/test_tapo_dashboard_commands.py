"""Real Flask routes with deterministic device barriers; no hardware or credentials."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import importlib
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import unittest
from unittest.mock import Mock, patch

from flask import Flask
from server_core.io import flush_json_writes
from subsystems.automations import trigger_routes
from subsystems.tapo_commands import TapoCommandQueue
from tests.devices.tapo.test_tapo_command_integrity import load_tapo_control


class TapoCommandQueueTests(unittest.TestCase):
    def test_fifo_reservations_and_aliases(self):
        queue = TapoCommandQueue()
        first, second = queue.reserve('tapo:one'), queue.reserve('one')
        entered = threading.Event()
        with ThreadPoolExecutor() as pool:
            with first:
                task = pool.submit(lambda: self.enter(second, entered))
                self.assertFalse(entered.wait(.03))
                with queue.hold('one'):
                    with queue.hold('two'):
                        pass
            task.result(1)
        self.assertTrue(entered.is_set())
        self.assertEqual(queue._entries, {})

    @staticmethod
    def enter(slot, entered):
        with slot:
            entered.set()

    def test_timeout_and_queue_limit_do_not_strand_following_commands(self):
        queue = TapoCommandQueue(timeout=.02, limit=2)
        first, second = queue.reserve('one'), queue.reserve('one')
        with self.assertRaises(TimeoutError):
            queue.reserve('one')
        with self.assertRaises(TimeoutError):
            with second:
                self.fail('Overtook earlier reservation')
        with first:
            pass
        with queue.hold('one'):
            pass
        self.assertEqual(queue._entries, {})

    def test_observation_catches_complete_command_and_aba(self):
        queue = TapoCommandQueue()
        with queue.observe(['one', 'two']) as unchanged:
            with queue.hold('one'):
                self.assertFalse(unchanged('one'))
            with queue.hold('one'):
                pass
            self.assertFalse(unchanged('one'))
            self.assertTrue(unchanged('two'))
        self.assertEqual(queue._entries, {})

    def test_error_releases_slot(self):
        queue = TapoCommandQueue()
        with self.assertRaises(ValueError):
            with queue.hold('one'):
                raise ValueError('fixture')
        with queue.hold('one'):
            pass
        self.assertEqual(queue._entries, {})


class TapoDashboardCommandTests(unittest.TestCase):
    def setUp(self):
        control = self.control = load_tapo_control()
        self.module = importlib.import_module(control.__package__ + '.tapo_routes')
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        # Complete fixture lighting-state writes before removing their directory.
        self.addCleanup(flush_json_writes)
        self.app = Flask(__name__)
        self.app.testing = True
        self.lock = threading.RLock()
        self.clients = {}
        self.target = self.add_device('plug')
        root = Path(self.temp.name)
        self.save = Mock()
        self.broadcast = Mock()
        self.context = dict(
            tapo_lighting_state_file=root/'lighting.json', automation_state_file=root/'automation.json',
            tapo_camera_hls_dir=root/'hls', recording_dir=root/'recordings', state_lock=self.lock,
            clients=self.clients, client_role_tapo='TAPO',
            client_has_role=lambda c, r: r in ([c.get('clientRole')] if isinstance(c.get('clientRole'), str) else c.get('clientRole', [])),
            init_client=lambda key: dict(deviceID=key), snapshot_client=deepcopy,
            save_state=self.save, broadcast_state=self.broadcast,
            clean_zone_name=lambda v: str(v or '').strip(), safe_int=lambda v: int(v) if v is not None else None,
            now_epoch=lambda: 1000, device_power_changed=Mock(),
        )
        self.executors = []
        def executor(**kwargs):
            instance = ThreadPoolExecutor(**kwargs)
            self.executors.append(instance)
            return instance
        with patch.object(self.module, 'ThreadPoolExecutor', side_effect=executor):
            self.module.register_tapo_routes(self.app, self.context)
        self.addCleanup(lambda: [e.shutdown(wait=True, cancel_futures=True) for e in self.executors])
        self.queue = self.app.extensions['kotibot.tapo_commands']
        self.calls = []
        self.device_effect = None
        async def device(item, action, value=None, **kwargs):
            self.calls.append((item['id'], action, deepcopy(item)))
            if self.device_effect:
                return self.device_effect(item, action, value)
            return dict(ok=True, device={**item, 'is_on': action == 'on', 'control_ready': True})
        self.device_mock = self.patch('set_tapo_device_from_info', side_effect=device)
        for name in ('start_tapo_camera_recording', 'stop_tapo_camera_recording',
                     'start_tapo_camera_stream', 'stop_tapo_camera_stream', 'prune_tapo_camera_streams'):
            self.patch(name, return_value='fixture-media')

    def patch(self, name, **kwargs):
        patcher = patch.object(self.module, name, **kwargs)
        value = patcher.start()
        self.addCleanup(patcher.stop)
        return value

    def add_device(self, name, kind='plug'):
        c = dict(deviceID='tapo:'+name, tapo_id=name, tapo_ip='192.0.2.1', ip='192.0.2.1',
                 tapo_kind=kind, tapo_model='P100' if kind=='plug' else 'C100',
                 clientRole='TAPO', provisioned=True, tapo_is_on=False,
                 tapo_supports_power=True, tapo_control_ready=True, tapo_children=[])
        self.clients[c['deviceID']] = c
        return c

    def post(self, action='on', device='plug', path='/api/tapo/client-command', **data):
        with self.app.test_client() as client:
            return client.post(path, json=dict(deviceID='tapo:'+device, action=action, **data))

    def blocked(self, operation, effect_owner=None, during=None):
        entered, release = threading.Event(), threading.Event()
        def effect(*args, **kwargs):
            entered.set()
            if not release.wait(3):
                raise TimeoutError('Fixture release missing')
            if effect_owner is not None:
                return 'fixture-media'
            return dict(ok=True, device={**args[0], 'is_on': args[1]=='on', 'control_ready': True})
        if effect_owner is None:
            self.device_effect = effect
        else:
            effect_owner.side_effect = effect
        with ThreadPoolExecutor() as pool:
            task = pool.submit(operation)
            try:
                self.assertTrue(entered.wait(1), 'Device operation did not start')
                acquired = self.lock.acquire(timeout=.1)
                self.assertTrue(acquired, 'Device I/O held STATE_LOCK')
                if acquired:
                    self.lock.release()
                if during:
                    during()
            finally:
                release.set()
            result = task.result(2)
        return result

    def test_power_wait_releases_shared_state_lock(self):
        result = self.blocked(self.post)
        self.assertEqual(result.status_code, 200)
        self.assertTrue(self.target['tapo_is_on'])

    def test_camera_start_stop_and_removal_do_not_hold_state_lock(self):
        for action, active, method in (
            ('preview', True, 'start_tapo_camera_stream'),
            ('preview', False, 'stop_tapo_camera_stream'),
            ('record', True, 'start_tapo_camera_recording'),
            ('record', False, 'stop_tapo_camera_recording'),
            ('remove', False, 'stop_tapo_camera_recording'),
        ):
            with self.subTest(action=action, active=active):
                self.add_device('camera', 'camera')
                mock = getattr(self.module, method)
                result = self.blocked(lambda: self.post(action, 'camera', active=active), mock)
                mock.side_effect = None
                self.assertEqual(result.status_code, 200)

    def test_failed_preview_does_not_commit_viewer_or_enabled_state(self):
        camera = self.add_device('camera', 'camera')
        self.module.start_tapo_camera_stream.side_effect = RuntimeError('fixture')
        result = self.post('preview', 'camera', active=True)
        self.assertEqual(result.status_code, 500)
        self.assertFalse(camera.get('preview_viewers'))
        self.assertFalse(camera.get('camera_enabled'))

    def test_multiple_preview_viewers_are_preserved_and_last_viewer_stops(self):
        camera = self.add_device('camera', 'camera')
        for viewer in ('one', 'two'):
            self.assertEqual(self.post('preview', 'camera', active=True, viewerId=viewer).status_code, 200)
        self.post('preview', 'camera', active=False, viewerId='one')
        self.assertEqual(set(camera['preview_viewers']), {'two'})
        self.assertTrue(camera['camera_enabled'])
        self.module.stop_tapo_camera_stream.assert_not_called()
        self.post('preview', 'camera', active=False, viewerId='two')
        self.assertFalse(camera['camera_enabled'])
        self.module.stop_tapo_camera_stream.assert_called_once()

    def test_replaced_client_rejects_old_result(self):
        replacement = deepcopy(self.target)
        result = self.blocked(self.post, during=lambda: self.clients.__setitem__('tapo:plug', replacement))
        self.assertEqual(result.status_code, 409)
        self.assertFalse(replacement['tapo_is_on'])
        self.save.assert_not_called()

    def test_connection_identity_change_rejects_old_result(self):
        result = self.blocked(self.post, during=lambda: self.target.update(tapo_ip='192.0.2.2'))
        self.assertEqual(result.status_code, 409)
        self.assertFalse(self.target['tapo_is_on'])

    def test_camera_removed_during_start_is_stopped_without_resurrection(self):
        self.add_device('camera', 'camera')
        result = self.blocked(lambda: self.post('record', 'camera', active=True),
                              self.module.start_tapo_camera_recording,
                              during=lambda: self.clients.pop('tapo:camera'))
        self.assertEqual(result.status_code, 409)
        self.assertNotIn('tapo:camera', self.clients)
        self.module.stop_tapo_camera_recording.assert_called_once_with('tapo:camera')

    def test_child_command_input_does_not_alias_live_state(self):
        self.target['tapo_children'] = [dict(id='child', is_on=False)]
        def effect(item, action, value):
            item['children'][0]['is_on'] = True
            self.assertFalse(self.target['tapo_children'][0]['is_on'])
            raise ValueError('fixture')
        self.device_effect = effect
        self.assertEqual(self.post('child_on', value=dict(child_id='child')).status_code, 400)
        self.assertFalse(self.target['tapo_children'][0]['is_on'])

    def test_different_devices_progress_while_same_device_commands_wait(self):
        self.add_device('other')
        entered, release, queued = threading.Event(), threading.Event(), threading.Event()
        def effect(item, action, value):
            if item['id']=='plug' and action=='on':
                entered.set()
                if not release.wait(3):
                    raise TimeoutError('fixture')
            return dict(device={**item, 'is_on': action=='on'})
        self.device_effect = effect
        original = self.queue.reserve
        def reserve(key, **kwargs):
            slot = original(key, **kwargs)
            if key=='tapo:plug' and entered.is_set():
                queued.set()
            return slot
        with patch.object(self.queue, 'reserve', side_effect=reserve), ThreadPoolExecutor() as pool:
            first = pool.submit(self.post, 'on')
            try:
                self.assertTrue(entered.wait(1))
                second = pool.submit(self.post, 'off')
                self.assertTrue(queued.wait(1))
                self.assertEqual(self.post('on', 'other').status_code, 200)
                self.assertEqual([x[1] for x in self.calls if x[0]=='plug'], ['on'])
            finally:
                release.set()
            self.assertEqual(first.result(2).status_code, 200)
            self.assertEqual(second.result(2).status_code, 200)
        self.assertFalse(self.target['tapo_is_on'])
        self.assertEqual([x[1] for x in self.calls if x[0]=='plug'], ['on', 'off'])
        self.assertTrue(self.calls[-1][2]['is_on'])

    def test_batch_reserves_all_commands_before_later_direct_command(self):
        entered, release, queued = threading.Event(), threading.Event(), threading.Event()
        def effect(item, action, value):
            if action=='on':
                entered.set()
                if not release.wait(3):
                    raise TimeoutError('fixture')
            return dict(device={**item, 'is_on': action!='off'})
        self.device_effect = effect
        original = self.queue.reserve
        def reserve(key, **kwargs):
            slot = original(key, **kwargs)
            if entered.is_set(): queued.set()
            return slot
        commands=[dict(deviceID='tapo:plug', action='on'), dict(deviceID='tapo:plug', action='brightness_no_power', value=25)]
        with patch.object(self.queue, 'reserve', side_effect=reserve), ThreadPoolExecutor() as pool:
            batch=pool.submit(self.post, path='/api/tapo/client-command-batch', commands=commands, activeHomeMode='day')
            try:
                self.assertTrue(entered.wait(1))
                off=pool.submit(self.post, 'off')
                self.assertTrue(queued.wait(1))
            finally:
                release.set()
            self.assertTrue(batch.result(2).get_json()['ok'])
            self.assertTrue(off.result(2).get_json()['ok'])
        self.assertEqual([x[1] for x in self.calls], ['on','brightness_no_power','off'])
        self.assertTrue(self.calls[1][2]['is_on'])
        self.assertFalse(self.target['tapo_is_on'])

    def test_queue_timeout_is_honest_and_next_command_still_runs(self):
        self.queue.timeout=.02
        reservation=self.queue.reserve('tapo:plug')
        try:
            result=self.post('on')
            self.assertEqual(result.status_code,503)
            self.device_mock.assert_not_awaited()
        finally:
            reservation.cancel()
        self.assertEqual(self.post('on').status_code,200)

    def test_refresh_cannot_overwrite_command_even_after_aba(self):
        entered, release=threading.Event(), threading.Event()
        async def refresh(items, **kwargs):
            entered.set()
            if not release.wait(3): raise TimeoutError('fixture')
            return [{**items[0], 'supported': True, 'is_on': True}]
        with patch.object(self.module,'refresh_tapo_devices',side_effect=refresh), ThreadPoolExecutor() as pool:
            task=pool.submit(self.post, path='/api/tapo/refresh')
            try:
                self.assertTrue(entered.wait(1))
                self.assertEqual(self.post('on').status_code,200)
                self.assertEqual(self.post('off').status_code,200)
            finally:
                release.set()
            self.assertEqual(task.result(2).status_code,200)
        self.assertFalse(self.target['tapo_is_on'])

    def test_automation_uses_same_slot_as_dashboard(self):
        source=dict(deviceID='source', clientRole='DSS', door_status='closed', provisioned=True)
        self.clients['source']=source
        route=dict(from_deviceID='source', trigger='door_open', action_type='device', to_deviceID='tapo:plug', scope='automation')
        context={**self.context, 'get_routes':lambda:[route], 'set_routes':Mock(),
                 'get_clients_for_device':lambda d:[], 'play_wav_file':Mock(),
                 'schedule_door_sound_repeat':Mock(), 'client_role_cam':'CAM', 'client_role_dss':'DSS'}
        runtime=trigger_routes.register_trigger_routes(self.app,context)
        entered,release,queued=threading.Event(),threading.Event(),threading.Event()
        def automation(call):
            entered.set()
            if not release.wait(3): raise TimeoutError('fixture')
            return dict(device={'is_on': True})
        original=self.queue.reserve
        def reserve(key, **kwargs):
            slot=original(key, **kwargs)
            if entered.is_set(): queued.set()
            return slot
        with patch.object(trigger_routes,'_set_tapo_device_from_info',side_effect=lambda *a,**kw:a), \
             patch.object(trigger_routes,'_run_tapo_async',side_effect=automation), \
             patch.object(self.queue,'reserve',side_effect=reserve), ThreadPoolExecutor() as pool:
            task=pool.submit(runtime['fire_door_routes'],source,'open')
            try:
                self.assertTrue(entered.wait(1))
                dashboard=pool.submit(self.post,'off')
                self.assertTrue(queued.wait(1))
                self.device_mock.assert_not_awaited()
            finally:
                release.set()
            task.result(2)
            self.assertEqual(dashboard.result(2).status_code,200)
        self.assertFalse(self.target['tapo_is_on'])

    def test_identity_aliases_share_one_queue(self):
        self.assertEqual(TapoCommandQueue.key('AA-BB:CC'), TapoCommandQueue.key('tapo:aa_bb_cc'))

    def test_prune_skips_camera_with_inflight_command(self):
        from tests.devices.tapo.test_tapo_hls_runtime_path import FakeProcess
        camera = self.add_device('camera', 'camera')
        key = self.control.tapo_stream_key(camera['deviceID'])
        process = FakeProcess()
        self.control.TAPO_CAMERA_STREAMS[key] = dict(
            deviceID=camera['deviceID'], proc=process, last_viewer_at=0)
        def prune():
            self.control.prune_tapo_camera_streams(
                hls_root=Path(self.temp.name)/'hls',
                command_slot=lambda key: self.queue.hold(key, timeout=0))
        with ThreadPoolExecutor() as pool:
            with self.queue.hold(camera['deviceID']):
                pool.submit(prune).result(1)
                self.assertFalse(process.terminated)
            pool.submit(prune).result(1)
        self.assertTrue(process.terminated)
        self.assertEqual(self.queue._entries, {})

    def test_stale_discovery_does_not_recreate_removed_client(self):
        entered, release = threading.Event(), threading.Event()
        async def discovery(**kwargs):
            entered.set()
            if not release.wait(3): raise TimeoutError('fixture')
            return [dict(id='plug', supported=True, kind='plug', ip='192.0.2.1', is_on=True)]
        with patch.object(self.module, 'list_tapo_devices', side_effect=discovery), ThreadPoolExecutor() as pool:
            task = pool.submit(self.post, path='/api/tapo/detect')
            try:
                self.assertTrue(entered.wait(1))
                self.assertEqual(self.post('remove').status_code, 200)
            finally:
                release.set()
            self.assertEqual(task.result(2).status_code, 200)
        self.assertNotIn('tapo:plug', self.clients)

    def test_executor_rejection_cancels_reservation(self):
        with patch.object(self.executors[0], 'submit', side_effect=RuntimeError('executor stopped')):
            result = self.post(path='/api/tapo/client-command-batch', deviceIDs=['tapo:plug'])
        self.assertFalse(result.get_json()['ok'])
        self.assertEqual(self.queue._entries, {})
        self.assertEqual(self.post('on').status_code, 200)

    def test_metadata_only_and_id_alias_remain_supported(self):
        self.assertEqual(self.post('', clientName='New name').status_code, 200)
        self.assertEqual(self.target['clientName'], 'New name')
        self.device_mock.assert_not_awaited()
        with self.app.test_client() as client:
            result = client.post('/api/tapo/client-command', json={'id':'plug','action':'on'})
        self.assertEqual(result.status_code, 200)



if __name__=='__main__':
    unittest.main()

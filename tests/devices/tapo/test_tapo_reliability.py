"""Synthetic regressions: no credentials, SDK, sockets, or real timers."""
import asyncio
from copy import deepcopy
import threading
import types
import unittest
from unittest.mock import AsyncMock, Mock, patch

from flask import Flask

from subsystems.automations import trigger_routes
from tests.devices.android.test_android_frame_upload_context import load_telemetry_module
from tests.devices.tapo.test_tapo_command_integrity import load_tapo_control


def plug(device_id='plug'):
    return dict(id=device_id, ip='192.0.2.1', model='P100',
                device_type='SMART.TAPOPLUG', alias=device_id)


class TapoConnectionReliabilityTests(unittest.TestCase):
    def setUp(self):
        self.control = load_tapo_control()

    def test_cancelled_waiter_releases_slot_before_and_after_handoff(self):
        for during_handoff in (False, True):
            with self.subTest(during_handoff=during_handoff):
                self.control = load_tapo_control()

                async def scenario():
                    entered, release, waiting = asyncio.Event(), asyncio.Event(), asyncio.Event()
                    calls = []
                    cancellations = []

                    async def reachable(host):
                        if host == '192.0.2.2':
                            waiting.set()
                        return True

                    async def connect(item, verify_cached=True):
                        calls.append(item['id'])
                        if item['id'] == 'owner':
                            entered.set()
                            await release.wait()
                        return object()

                    with (patch.object(self.control, '_tapo_host_reachable', side_effect=reachable),
                          patch.object(self.control, '_connect_tapo_device', side_effect=connect)):
                        owner = asyncio.create_task(self.control._get_tapo_device(plug('owner'), False))
                        await asyncio.wait_for(entered.wait(), 1)
                        waiter = asyncio.create_task(self.control._get_tapo_device(
                            {**plug('waiter'), 'ip': '192.0.2.2'}, False))
                        await asyncio.wait_for(waiting.wait(), 1)
                        gate = self.control._tapo_handle_connect_lock
                        self.assertEqual(len(gate._waiters), 1)
                        pending = gate._waiters[0]
                        self.assertFalse(pending.done())
                        if during_handoff:
                            # A concurrent Future's callback runs at the grant,
                            # before the waiting coroutine can resume. An owner
                            # Task callback can run after the waiter has finished.
                            def cancel_at_grant(granted):
                                cancellations.append((granted.done(), granted.cancelled(), waiter.cancel()))

                            pending.add_done_callback(cancel_at_grant)
                        else:
                            self.assertTrue(waiter.cancel())
                        release.set()
                        await owner
                        with self.assertRaises(asyncio.CancelledError):
                            await waiter
                        if during_handoff:
                            self.assertEqual(cancellations, [(True, False, True)])
                        try:
                            await asyncio.wait_for(self.control._get_tapo_device(plug('next'), False), .2)
                        except TimeoutError:
                            self.fail('A cancelled connection waiter stranded the next request')
                        self.assertNotIn('waiter', calls)
                        self.assertIn('next', calls)
                        self.assertFalse(gate._busy)
                        self.assertFalse(gate._waiters)

                asyncio.run(scenario())

    def test_connection_slot_wait_has_a_deadline_and_owner_survives(self):
        async def scenario():
            entered, release = asyncio.Event(), asyncio.Event()

            async def connect(item, verify_cached=True):
                if item['id'] == 'owner':
                    entered.set()
                    await release.wait()
                return object()

            with (patch.object(self.control, '_tapo_host_reachable', AsyncMock(return_value=True)),
                  patch.object(self.control, '_connect_tapo_device', side_effect=connect),
                  patch.object(self.control, 'TAPO_DEVICE_REFRESH_TIMEOUT_SECONDS', .03)):
                owner = asyncio.create_task(self.control._get_tapo_device(plug('owner'), False))
                await entered.wait()
                waiter = asyncio.create_task(self.control._get_tapo_device(plug('waiter'), False))
                try:
                    done, _ = await asyncio.wait({waiter}, timeout=.2)
                    self.assertIn(waiter, done, 'The connection-slot deadline was not enforced')
                    with self.assertRaises(TimeoutError):
                        await waiter
                    self.assertFalse(owner.done())
                finally:
                    release.set()
                    await owner
                    await asyncio.gather(waiter, return_exceptions=True)
                await self.control._get_tapo_device(plug('next'), False)

        asyncio.run(scenario())

    def test_cancelled_owner_allows_next_connection(self):
        async def scenario():
            entered = asyncio.Event()

            async def connect(item, verify_cached=True):
                if item['id'] == 'owner':
                    entered.set()
                    await asyncio.Event().wait()
                return object()

            with (patch.object(self.control, '_tapo_host_reachable', AsyncMock(return_value=True)),
                  patch.object(self.control, '_connect_tapo_device', side_effect=connect)):
                owner = asyncio.create_task(self.control._get_tapo_device(plug('owner'), False))
                await entered.wait()
                owner.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await owner
                await asyncio.wait_for(self.control._get_tapo_device(plug('next'), False), .2)

        asyncio.run(scenario())

    def test_healthy_refresh_reads_info_once_and_skips_reachability_probe(self):
        info = AsyncMock(return_value={'device_on': True})
        self.control._tapo_handles['plug'] = types.SimpleNamespace(get_device_info=info)
        with patch.object(self.control, '_tapo_host_reachable', AsyncMock(return_value=True)) as probe:
            result = asyncio.run(self.control._enrich_control_state(plug()))
        self.assertTrue(result['control_ready'])
        self.assertTrue(result['is_on'])
        self.assertEqual(info.await_count, 1)
        probe.assert_not_awaited()

    def test_discovery_bounds_stalled_reads_and_retains_healthy_devices(self):
        async def scenario():
            async def stalled():
                await asyncio.Event().wait()

            self.control._tapo_handles.update({
                'slow': types.SimpleNamespace(get_device_info=AsyncMock(side_effect=stalled)),
                'healthy': types.SimpleNamespace(get_device_info=AsyncMock(return_value={'device_on': True})),
            })
            with (patch.object(self.control, '_run_discovery_text', return_value='fixture'),
                  patch.object(self.control, '_parse_kasa_discovery', return_value=[plug('slow'), plug('healthy')]),
                  patch.object(self.control, '_tapo_host_reachable', AsyncMock(return_value=True)),
                  patch.object(self.control, 'TAPO_DEVICE_CALL_TIMEOUT_SECONDS', .03),
                  patch.object(self.control, 'TAPO_DEVICE_REFRESH_TIMEOUT_SECONDS', .08)):
                result = await asyncio.wait_for(self.control.list_tapo_devices(force=True), .4)
            devices = {item['id']: item for item in result}
            self.assertFalse(devices['slow']['control_ready'])
            self.assertIn('timed out', devices['slow']['control_error'])
            self.assertTrue(devices['healthy']['is_on'])
            self.assertNotIn('slow', self.control._tapo_handles)

        asyncio.run(scenario())

    def test_expired_cached_session_is_reconnected_once_within_refresh(self):
        expired = types.SimpleNamespace(get_device_info=AsyncMock(side_effect=RuntimeError('expired session')))
        fresh = types.SimpleNamespace(get_device_info=AsyncMock(return_value={'device_on': True}))
        self.control._tapo_handles['plug'] = expired
        with (patch.object(self.control, '_tapo_host_reachable', AsyncMock(return_value=True)),
              patch.object(self.control, '_connect_tapo_device', AsyncMock(return_value=fresh)) as connect):
            result = asyncio.run(self.control._enrich_control_state(plug()))
        self.assertTrue(result['control_ready'])
        self.assertTrue(result['is_on'])
        self.assertEqual(connect.await_count, 1)
        self.assertEqual(fresh.get_device_info.await_count, 1)

    def test_discovery_and_refresh_bound_whole_enrichment_and_preserve_children(self):
        for discover in (False, True):
            with self.subTest(discover=discover):
                child = dict(id='socket', name='Fixture', is_on=True)
                item = {**plug(), 'children': [child]}

                async def stall(_):
                    await asyncio.Event().wait()

                async def scenario():
                    with (patch.object(self.control, '_enrich_control_state', side_effect=stall),
                          patch.object(self.control, '_run_discovery_text', return_value='fixture'),
                          patch.object(self.control, '_parse_kasa_discovery', return_value=[deepcopy(item)]),
                          patch.object(self.control, 'TAPO_DEVICE_REFRESH_TIMEOUT_SECONDS', .03)):
                        call = (self.control.list_tapo_devices(force=True) if discover
                                else self.control.refresh_tapo_devices([item]))
                        task = asyncio.create_task(call)
                        try:
                            done, _ = await asyncio.wait({task}, timeout=.2)
                            self.assertIn(task, done, 'Enrichment exceeded the per-device deadline')
                            result = (await task)[0]
                            self.assertFalse(result['control_ready'])
                            self.assertTrue(result['control_error'])
                            self.assertEqual(result['children'][0]['name'], 'Fixture')
                            self.assertIsNone(result['children'][0]['is_on'])
                        finally:
                            task.cancel()
                            await asyncio.gather(task, return_exceptions=True)

                asyncio.run(scenario())
                self.assertIs(child['is_on'], True)


class FakeTimer:
    def __init__(self, interval, function, args=(), kwargs=None):
        self.interval, self.function = interval, function
        self.args, self.kwargs = args, kwargs or {}
        self.alive = False
        self.cancelled = threading.Event()
    def start(self):
        self.alive = True
    def is_alive(self):
        return self.alive
    def cancel(self):
        self.alive = False
        self.cancelled.set()
    def fire(self):
        try:
            return self.function(*self.args, **self.kwargs)
        finally:
            self.alive = False


class TapoAutomationReliabilityTests(unittest.TestCase):
    def setUp(self):
        self.lock = threading.RLock()
        self.app = Flask(__name__)
        self.source = dict(deviceID='source', clientRole='DSS', door_status='closed', provisioned=True)
        self.target = dict(deviceID='tapo:plug', clientRole='TAPO', tapo_id='plug', tapo_ip='192.0.2.1',
                           tapo_is_on=False, tapo_kind='plug')
        self.clients = {'source': self.source, 'tapo:plug': self.target}
        self.route = dict(from_deviceID='source', trigger='door_open', action_type='device',
                          to_deviceID='tapo:plug', scope='automation')
        self.routes = [self.route]
        self.timers = []
        self.save, self.broadcast = Mock(), Mock()
        self.context = dict(
            state_lock=self.lock, clients=self.clients, get_routes=lambda: self.routes, set_routes=Mock(),
            client_role_cam='CAM', client_role_key='KEY', client_role_dss='DSS', client_role_tapo='TAPO',
            client_has_role=lambda c, r: c.get('clientRole') == r,
            get_clients_for_device=lambda d: [self.clients[d]] if d in self.clients else [],
            play_wav_file=Mock(), schedule_door_sound_repeat=Mock(), cancel_door_sound_repeat=Mock(),
            save_state=self.save, broadcast_state=self.broadcast, now_epoch=lambda: 1000,
        )
        self.runtime = trigger_routes.register_trigger_routes(self.app, self.context)
        self.network = Mock(side_effect=lambda call: {'device': {'is_on': call[1] in ('on', 'child_on')}})
        for patcher in (
            patch.object(trigger_routes, '_set_tapo_device_from_info', side_effect=lambda *a, **kw: a),
            patch.object(trigger_routes, '_run_tapo_async', self.network),
            patch.object(trigger_routes.threading, 'Timer', side_effect=self.make_timer),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.app.config['KOTIBOT_TAPO_RECOVER_DESIRED_LIGHTING'] = Mock(return_value=None)

    def make_timer(self, *args, **kwargs):
        timer = FakeTimer(*args, **kwargs)
        self.timers.append(timer)
        return timer

    def fire(self):
        return self.runtime['fire_door_routes'](self.source, 'open')

    def assert_blocked_network_leaves_state_available(self, operation, network=None, while_blocked=None):
        entered, release = threading.Event(), threading.Event()
        outcomes, errors = [], []
        mock = network if network is not None else self.network

        def blocked(*args, **kwargs):
            entered.set()
            if not release.wait(2):
                raise TimeoutError('test release missing')
            return {'device': {'is_on': True}} if network is None else 'fixture.mp4'

        def worker():
            try:
                outcomes.append(operation())
            except BaseException as error:
                errors.append(error)

        previous_effect = mock.side_effect
        mock.side_effect = blocked
        try:
            thread = threading.Thread(target=worker, daemon=True)
            thread.start()
            acquired = False
            try:
                self.assertTrue(entered.wait(1), 'Device action never started')
                acquired = self.lock.acquire(timeout=.2)
                self.assertTrue(acquired, 'Device I/O held the shared state lock')
                if while_blocked:
                    while_blocked()
            finally:
                if acquired:
                    self.lock.release()
                release.set()
                thread.join(2)
            self.assertFalse(thread.is_alive())
            self.assertEqual(errors, [])
        finally:
            mock.side_effect = previous_effect
        return outcomes

    def register_telemetry(self):
        self.telemetry = load_telemetry_module()
        context = {**self.context, **self.runtime,
                   'normalize_client_roles': lambda r: [r] if r else [],
                   'get_unprovisioned_client': Mock(), 'register_seen_client': Mock(return_value=False),
                   'snapshot_client': lambda c: {'deviceID': c['deviceID']},
                   'preview_requested_for_client': Mock(return_value=False),
                   'handle_key_telemetry': Mock(return_value=False), 'system_armed': Mock(return_value=False),
                   'safe_int': lambda v: int(v) if v is not None else None,
                   'safe_float': lambda v: float(v) if v is not None else None}
        self.telemetry.register_android_home_telemetry(self.app, context)

    def post_telemetry(self, **data):
        with self.app.test_client() as client:
            return client.post('/telemetry', json={'deviceID': 'source', **data})

    def test_android_door_telemetry_keeps_status_available_during_device_call(self):
        self.register_telemetry()
        responses = self.assert_blocked_network_leaves_state_available(
            lambda: self.post_telemetry(type='door_telemetry', openDoor=1))
        self.assertEqual(responses[0].status_code, 200)
        self.assertTrue(self.target['tapo_is_on'])
        self.save.assert_called()

    def test_android_motion_telemetry_keeps_status_available_and_returns_commands(self):
        self.source.update(clientRole='CAM', motion_detection_enabled=True)
        self.route['trigger'] = 'motion'
        self.register_telemetry()
        responses = self.assert_blocked_network_leaves_state_available(
            lambda: self.post_telemetry(type='camera_motion'))
        payload = responses[0].get_json()
        self.assertEqual(payload['recordingEnabled'], 1)
        self.assertTrue(self.target['tapo_is_on'])

    def test_removed_source_never_receives_detached_pending_commands(self):
        self.source['pending_command'] = {'fixtureCommand': 1}
        self.register_telemetry()
        responses = self.assert_blocked_network_leaves_state_available(
            lambda: self.post_telemetry(type='door_telemetry', openDoor=1),
            while_blocked=lambda: self.clients.pop('source'))
        self.assertEqual(responses[0].get_json(), {'ok': True})

    def test_late_power_result_cannot_overwrite_replaced_or_updated_client(self):
        for replace in (False, True):
            with self.subTest(replace=replace):
                self.target['tapo_is_on'] = False
                self.clients['tapo:plug'] = self.target
                def edit():
                    if replace:
                        self.clients['tapo:plug'] = {**self.target, 'tapo_brightness': 17}
                    else:
                        self.target['tapo_brightness'] = 23
                self.assert_blocked_network_leaves_state_available(self.fire, while_blocked=edit)
                self.assertFalse(self.clients['tapo:plug']['tapo_is_on'])

    def test_removed_route_does_not_schedule_new_auto_off(self):
        self.route.update(auto_off=True, auto_off_seconds=30)
        self.assert_blocked_network_leaves_state_available(self.fire, while_blocked=self.routes.clear)
        self.assertEqual(self.timers, [])

    def test_auto_off_runs_outside_state_lock(self):
        self.route.update(auto_off=True, auto_off_seconds=30)
        self.fire()
        self.assertEqual(len(self.timers), 1)
        self.assert_blocked_network_leaves_state_available(self.timers[0].fire)

    def test_replaced_auto_off_callback_does_not_contact_device(self):
        self.route.update(auto_off=True, auto_off_seconds=30)
        self.fire()
        first = self.timers[-1]
        self.fire()
        second = self.timers[-1]
        self.assertIsNot(first, second)
        self.network.reset_mock()
        first.fire()  # A callback already queued when Timer.cancel() ran.
        self.network.assert_not_called()
        second.fire()
        self.assertFalse(self.target['tapo_is_on'])

    def test_motion_during_off_is_followed_by_on_without_global_lock_wait(self):
        self.route.update(trigger='motion', auto_off=True, auto_off_seconds=30)
        self.target['tapo_is_on'] = True
        fire = self.runtime['fire_camera_motion_routes']
        fire(self.source, 'inactive')
        off = self.timers[-1]
        entered, release, on_started = threading.Event(), threading.Event(), threading.Event()
        calls = []

        def network(call):
            calls.append(call[1])
            if call[1] == 'off':
                entered.set()
                self.assertTrue(release.wait(2))
            return {'device': {'is_on': call[1] == 'on'}}

        self.network.side_effect = network
        off_thread = threading.Thread(target=off.fire, daemon=True)
        def on():
            on_started.set()
            fire(self.source, 'motion')
        on_thread = threading.Thread(target=on, daemon=True)
        off_thread.start()
        try:
            self.assertTrue(entered.wait(1))
            on_thread.start()
            self.assertTrue(on_started.wait(1))
            self.assertTrue(off.cancelled.wait(1), 'Motion did not cancel the running OFF timer')
            acquired = self.lock.acquire(timeout=.2)
            self.assertTrue(acquired)
            if acquired:
                self.lock.release()
        finally:
            release.set()
            off_thread.join(2)
            if on_thread.ident:
                on_thread.join(2)
        self.assertEqual(calls, ['off', 'on'])
        self.assertTrue(self.target['tapo_is_on'])
        self.assertFalse(off_thread.is_alive() or on_thread.is_alive())

    def test_failed_cancelled_auto_off_does_not_rearm(self):
        self.route.update(auto_off=True, auto_off_seconds=30)
        self.fire()
        off = self.timers[-1]
        def failure(_):
            self.app.config['KOTIBOT_CANCEL_AUTOMATION_ROUTE_RUNTIME'](self.route)
            raise TimeoutError('fixture')
        self.network.side_effect = failure
        with self.assertLogs(self.app.logger, level='ERROR'):
            off.fire()
        self.assertEqual(self.timers, [off])

    def test_camera_start_and_stop_keep_shared_state_available(self):
        self.target.update(tapo_kind='camera', tapo_is_camera=True)
        self.route.update(action_type='recording', duration_seconds=30)
        with (patch.object(trigger_routes, '_start_tapo_camera_recording') as start,
              patch.object(trigger_routes, '_stop_tapo_camera_recording') as stop):
            self.assert_blocked_network_leaves_state_available(self.fire, network=start)
            self.assertTrue(self.target['tapo_recording'])
            self.assert_blocked_network_leaves_state_available(self.timers[-1].fire, network=stop)
            self.assertFalse(self.target['tapo_recording'])

    def test_child_command_snapshot_does_not_share_live_children(self):
        self.route['targetID'] = 'tapo:plug|child'
        self.target['tapo_children'] = [dict(id='child', is_on=False, name='original')]
        def command(call):
            call[0]['children'][0]['name'] = 'mutated by SDK'
            return {'device': {'is_on': True}}
        self.network.side_effect = command
        self.fire()
        self.assertEqual(self.target['tapo_children'][0]['name'], 'original')
        self.assertEqual(self.network.call_args.args[0][1], 'child_on')

    def test_camera_removed_during_start_is_stopped_without_state_resurrection(self):
        self.target.update(tapo_kind='camera', tapo_is_camera=True)
        self.route.update(action_type='recording', duration_seconds=30)
        with (patch.object(trigger_routes, '_start_tapo_camera_recording') as start,
              patch.object(trigger_routes, '_stop_tapo_camera_recording') as stop):
            self.assert_blocked_network_leaves_state_available(
                self.fire, network=start, while_blocked=lambda: self.clients.pop('tapo:plug'))
            stop.assert_called_once_with('tapo:plug')
        self.assertNotIn('tapo:plug', self.clients)
        self.assertEqual(self.timers, [])

    def test_different_devices_are_not_serialized_with_each_other(self):
        other = {**self.target, 'deviceID': 'tapo:other', 'tapo_id': 'other'}
        self.clients['tapo:other'] = other
        self.routes.append({**self.route, 'from_deviceID': 'other-source', 'to_deviceID': 'tapo:other'})
        entered, release, other_done = threading.Event(), threading.Event(), threading.Event()
        def network(call):
            if call[0]['id'] == 'plug':
                entered.set()
                self.assertTrue(release.wait(2))
            return {'device': {'is_on': True}}
        self.network.side_effect = network
        thread = threading.Thread(target=self.fire, daemon=True)
        def second():
            self.runtime['fire_door_routes']({'deviceID': 'other-source'}, 'open')
            other_done.set()
        second_thread = threading.Thread(target=second, daemon=True)
        thread.start()
        try:
            self.assertTrue(entered.wait(1))
            second_thread.start()
            self.assertTrue(other_done.wait(.5), 'An unrelated device waited behind the slow one')
            self.assertTrue(other['tapo_is_on'])
        finally:
            release.set()
            thread.join(2)
            if second_thread.ident:
                second_thread.join(2)

"""Scene contract tests: final-state writes, independent dispatch, honest failures."""
import asyncio
import importlib
import threading
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from tests.devices.tapo.test_tapo_command_integrity import load_tapo_control


def expired_session(kind='SESSION_TIMEOUT'):
    return Exception(f'Tapo(Unauthorized {{ kind: "{kind}", description: '
                     '"Session has expired. Re-authentication is required." })')


class Builder:
    """Immutable builder matching the pinned SDK's documented public methods."""
    def __init__(self, fields=None):
        self.fields = fields or {}

    def with_fields(self, **fields):
        return Builder({**self.fields, **fields})

    def on(self): return self.with_fields(device_on=True)
    def off(self): return self.with_fields(device_on=False)
    def brightness(self, value): return self.with_fields(brightness=value)
    def hue_saturation(self, hue, saturation):
        return self.with_fields(hue=hue, saturation=saturation, color_temp=0)
    def color_temperature(self, value): return self.with_fields(color_temp=value)

    async def send(self, device):
        device.writes.append(self.fields)
        if device.failure:
            raise device.failure


class SceneTransportTests(unittest.TestCase):
    def setUp(self):
        self.control = load_tapo_control()
        self.scene = importlib.import_module(self.control.__package__ + '.tapo_scenes')
        self.device = SimpleNamespace(set=lambda: Builder(), writes=[], failure=None,
                                      on=AsyncMock(), off=AsyncMock(), get_device_info=AsyncMock(),
                                      refresh_session=AsyncMock())
        self.item = dict(id='bulb', ip='192.0.2.1', kind='bulb', model='L530', is_on=False)
        self.control._tapo_handles['bulb'] = self.device

    def send(self, commands):
        return asyncio.run(self.scene.set_tapo_scene_from_info(self.item, commands))

    def test_power_brightness_and_color_use_one_write_and_no_reads(self):
        with patch.object(self.control, '_tapo_host_reachable', AsyncMock()) as probe:
            result = self.send([dict(action='on'), dict(action='brightness_no_power', value=35),
                                dict(action='color_no_power', value=dict(hue=150, saturation=80))])
        self.assertEqual(self.device.writes, [dict(device_on=True, brightness=35,
                                                  hue=150, saturation=80, color_temp=0)])
        self.assertTrue(result['device']['is_on'])
        self.assertEqual(result['device']['brightness'], 35)
        self.device.on.assert_not_awaited()
        self.device.off.assert_not_awaited()
        self.device.get_device_info.assert_not_awaited()
        probe.assert_not_awaited()
        self.device.refresh_session.assert_not_awaited()

    def test_preset_preserves_off_without_turning_bulb_on_then_off(self):
        self.send([dict(action='brightness_no_power', value=12),
                   dict(action='color_temperature_no_power', value=3100)])
        self.assertEqual(self.device.writes, [dict(device_on=False, brightness=12, color_temp=3100)])
        self.device.on.assert_not_awaited()
        self.device.off.assert_not_awaited()

    def test_final_values_win_within_one_target(self):
        self.send([dict(action='on'), dict(action='brightness_no_power', value=10),
                   dict(action='brightness_no_power', value=40), dict(action='off')])
        self.assertEqual(self.device.writes, [dict(device_on=False, brightness=40)])

    def test_invalid_target_is_rejected_before_any_write(self):
        for command in [dict(action='brightness_no_power', value=0),
                        dict(action='color_no_power', value=dict(hue=400, saturation=20)),
                        dict(action='color_temperature_no_power', value=100),
                        dict(action='unknown')]:
            with self.subTest(command=command), self.assertRaises(ValueError):
                self.send([dict(action='on'), command])
        self.assertEqual(self.device.writes, [])

    def test_transport_failure_is_not_replayed(self):
        self.device.failure = RuntimeError('write failed')
        with self.assertRaisesRegex(RuntimeError, 'write failed'):
            self.send([dict(action='on')])
        self.assertEqual(len(self.device.writes), 1)

    def test_explicit_expiry_renews_session_and_resends_only_rejected_write(self):
        for kind in ('SESSION_TIMEOUT', 'SESSION_EXPIRED'):
            with self.subTest(kind=kind):
                self.device.writes.clear()
                self.device.failure = expired_session(kind)
                async def renew():
                    self.device.failure = None
                self.device.refresh_session = AsyncMock(side_effect=renew)
                result = self.send([dict(action='on'), dict(action='brightness_no_power', value=80)])
                self.assertTrue(result['ok'])
                self.assertEqual(self.device.writes, [dict(device_on=True, brightness=80)] * 2)
                self.device.refresh_session.assert_awaited_once()
                self.device.get_device_info.assert_not_awaited()

    def test_network_and_credentials_errors_never_renew_or_resend(self):
        for error in (TimeoutError('timed out'), RuntimeError('No route to host'),
                      expired_session('LOGIN'), expired_session('HASH_MISMATCH'),
                      RuntimeError('unrelated SESSION_TIMEOUT text')):
            with self.subTest(error=error):
                self.device.writes.clear()
                self.device.failure = error
                with self.assertRaises(type(error)):
                    self.send([dict(action='on')])
                self.assertEqual(len(self.device.writes), 1)
                self.device.refresh_session.assert_not_awaited()
                self.assertNotIn('bulb', self.control._tapo_devices)

    def test_repeated_expiry_stops_after_one_renewal_and_evicts_session(self):
        self.device.failure = expired_session()
        with self.assertRaisesRegex(Exception, 'SESSION_TIMEOUT'):
            self.send([dict(action='on')])
        self.assertEqual(len(self.device.writes), 2)
        self.device.refresh_session.assert_awaited_once()
        self.assertNotIn('bulb', self.control._tapo_handles)
        self.assertNotIn('bulb', self.control._tapo_devices)

    def test_failed_renewal_does_not_resend_or_remove_a_replacement_handle(self):
        for replacement in (None, object()):
            with self.subTest(replacement=bool(replacement)):
                self.control._tapo_handles['bulb'] = self.device
                self.device.writes.clear()
                self.device.failure = expired_session()
                async def renew():
                    if replacement is not None:
                        self.control._tapo_handles['bulb'] = replacement
                    raise RuntimeError('authentication failed')
                self.device.refresh_session = AsyncMock(side_effect=renew)
                with self.assertRaisesRegex(RuntimeError, 'authentication failed'):
                    self.send([dict(action='on')])
                self.assertEqual(len(self.device.writes), 1)
                self.assertIs(self.control._tapo_handles.get('bulb'), replacement)

    def test_dimmable_expiry_does_not_repeat_successful_power_operation(self):
        del self.device.set
        self.device.set_brightness = AsyncMock(side_effect=[expired_session(), None])
        self.send([dict(action='on'), dict(action='brightness_no_power', value=25)])
        self.device.on.assert_awaited_once()
        self.assertEqual(self.device.set_brightness.await_count, 2)
        self.device.refresh_session.assert_awaited_once()

    def test_cancelled_renewal_releases_invalid_session(self):
        self.device.failure = expired_session()
        self.device.refresh_session.side_effect = asyncio.CancelledError()
        with self.assertRaises(asyncio.CancelledError):
            self.send([dict(action='on')])
        self.assertEqual(len(self.device.writes), 1)
        self.assertNotIn('bulb', self.control._tapo_handles)

    def test_scene_preserves_cached_device_metadata(self):
        self.control._tapo_devices['bulb'] = dict(alias='Desk', energy_info={'today': 3})
        self.send([dict(action='on')])
        cached = self.control._tapo_devices['bulb']
        self.assertEqual(cached['alias'], 'Desk')
        self.assertEqual(cached['energy_info'], {'today': 3})
        self.assertFalse(self.item['is_on'])

    def test_cold_login_failure_does_not_try_other_model_handlers(self):
        self.control._tapo_handles.clear()
        api = SimpleNamespace(l530=AsyncMock(side_effect=RuntimeError('login failed')),
                              l535=AsyncMock())
        with patch.object(self.control, '_api_client', AsyncMock(return_value=api)):
            with self.assertRaisesRegex(RuntimeError, 'login failed'):
                self.send([dict(action='on')])
        api.l530.assert_awaited_once()
        api.l535.assert_not_awaited()
        self.assertEqual(self.device.writes, [])

    def test_plug_uses_one_power_write(self):
        self.item['kind'] = 'plug'
        del self.device.set
        self.send([dict(action='off')])
        self.device.off.assert_awaited_once()
        self.device.on.assert_not_awaited()

    def test_dimmable_only_bulb_keeps_supported_power_semantics(self):
        del self.device.set
        self.device.set_brightness = AsyncMock()
        self.send([dict(action='on'), dict(action='brightness_no_power', value=25)])
        self.device.on.assert_awaited_once()
        self.device.set_brightness.assert_awaited_once_with(25)
        self.device.get_device_info.assert_not_awaited()

    def test_cold_scene_has_no_reachability_probe_or_confirmation(self):
        self.control._tapo_handles.clear()
        with patch.object(self.control, '_connect_tapo_device', AsyncMock(return_value=self.device)) as connect, \
             patch.object(self.control, '_tapo_host_reachable', AsyncMock()) as probe:
            self.send([dict(action='on')])
        connect.assert_awaited_once()
        self.assertEqual(connect.await_args.kwargs, {'verify_cached': False, 'single_attempt': True})
        self.assertEqual(connect.await_args.args[0]['id'], self.item['id'])
        probe.assert_not_awaited()
        self.assertEqual(len(self.device.writes), 1)


class SceneDispatchTests(unittest.TestCase):
    def setUp(self):
        # Import the fixture inside setup to avoid duplicate unittest discovery.
        from tests.devices.tapo.test_tapo_dashboard_commands import TapoDashboardCommandTests
        self.fixture = TapoDashboardCommandTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def post(self, mode='day', names=('plug',), action='on'):
        return self.fixture.post(path='/api/tapo/client-command-batch', activeHomeMode=mode,
                                 commands=[dict(deviceID='tapo:'+name, action=action) for name in names])

    def test_twelve_pending_devices_all_dispatch_without_eight_worker_limit(self):
        fixture = self.fixture
        names = ['plug'] + [f'bulb{n}' for n in range(11)]
        for name in names[1:]: fixture.add_device(name)
        started, state, seen = threading.Event(), {}, []
        async def send(item, commands):
            if not state:
                state.update(loop=asyncio.get_running_loop(), release=asyncio.Event())
            seen.append(item['id'])
            if len(seen) == len(names): started.set()
            await state['release'].wait()
            return dict(device={**item, 'is_on': True})
        fixture.scene_mock.side_effect = send
        with ThreadPoolExecutor() as pool:
            request = pool.submit(self.post, names=names)
            try:
                self.assertTrue(started.wait(2), f'Only dispatched {seen}')
                self.assertFalse(request.done())
                fixture.save.assert_not_called()
            finally:
                if state: state['loop'].call_soon_threadsafe(state['release'].set)
            result = request.result(2).get_json()
        self.assertEqual(result['okCount'], 12)
        self.assertEqual(fixture.scene_mock.await_count, 12)
        self.assertEqual(fixture.queue._entries, {})

    def test_busy_bulb_cannot_hold_up_another_device_or_next_scene(self):
        fixture = self.fixture
        fixture.add_device('other')
        busy = fixture.queue.reserve('tapo:plug')
        other_sent = threading.Event()
        async def send(item, commands):
            if item['id'] == 'other': other_sent.set()
            return dict(device={**item, 'is_on': commands[-1]['action'] == 'on'})
        fixture.scene_mock.side_effect = send
        with ThreadPoolExecutor() as pool:
            first = pool.submit(self.post, names=('plug', 'other'))
            try:
                self.assertTrue(other_sent.wait(1))
                self.assertFalse(first.done())
                newer = pool.submit(self.post, 'night', ('other',), 'off')
                self.assertTrue(newer.result(1).get_json()['ok'])
                self.assertFalse(first.done())
            finally:
                busy.cancel()
            older_result = first.result(2).get_json()
        self.assertTrue(older_result['ok'])
        self.assertEqual(older_result['activeSchemes']['home'], 'night')
        self.assertFalse(fixture.clients['tapo:other']['tapo_is_on'])
        self.assertEqual(fixture.queue._entries, {})

    def test_failure_is_reported_once_and_other_targets_still_succeed(self):
        fixture = self.fixture
        fixture.add_device('other')
        async def send(item, commands):
            if item['id'] == 'plug': raise RuntimeError('offline')
            return dict(device={**item, 'is_on': True})
        fixture.scene_mock.side_effect = send
        result = self.post(names=('plug', 'other')).get_json()
        self.assertFalse(result['ok'])
        self.assertEqual((result['okCount'], result['failedCount']), (1, 1))
        self.assertEqual(fixture.scene_mock.await_count, 2)
        self.assertEqual(fixture.queue._entries, {})

    def test_scene_combines_commands_before_transport_and_records_desired_state(self):
        fixture = self.fixture
        result = fixture.post(path='/api/tapo/client-command-batch', activeHomeMode='evening', commands=[
            dict(deviceID='tapo:plug', action='on'),
            dict(deviceID='tapo:plug', action='brightness_no_power', value=30, lightingMode='evening'),
            dict(deviceID='tapo:plug', action='color_no_power', value=dict(hue=50, saturation=20), lightingMode='evening'),
        ]).get_json()
        self.assertTrue(result['ok'])
        fixture.scene_mock.assert_awaited_once()
        self.assertEqual(fixture.target['tapo_desired_brightness'], 30)
        self.assertEqual(fixture.target['tapo_desired_hue'], 50)
        self.assertEqual(fixture.target['tapo_desired_lighting_mode'], 'evening')

    def test_out_of_order_http_delivery_cannot_restore_an_older_scene(self):
        fixture = self.fixture
        def send(sequence, mode, action):
            return fixture.post(path='/api/tapo/client-command-batch', activeHomeMode=mode,
                                sceneSession='fixture-page', sceneSequence=sequence,
                                commands=[dict(deviceID='tapo:plug', action=action)]).get_json()
        self.assertTrue(send(2, 'night', 'off')['ok'])
        self.assertTrue(send(1, 'day', 'on')['superseded'])
        self.assertTrue(send(2, 'night', 'off')['superseded'])
        self.assertEqual(fixture.scene_mock.await_count, 1)
        self.assertFalse(fixture.target['tapo_is_on'])
        self.assertTrue(send(3, 'day', 'on')['ok'])
        self.assertTrue(fixture.target['tapo_is_on'])

    def test_client_replacement_during_send_cannot_receive_old_result(self):
        fixture = self.fixture
        async def send(item, commands):
            fixture.clients['tapo:plug'] = {**fixture.target, 'clientName': 'Replacement'}
            return dict(device={**item, 'is_on': True})
        fixture.scene_mock.side_effect = send
        result = self.post().get_json()
        self.assertFalse(result['ok'])
        self.assertFalse(fixture.clients['tapo:plug']['tapo_is_on'])
        self.assertEqual(fixture.queue._entries, {})

    def test_route_recovers_expired_bulb_without_holding_healthy_bulb(self):
        fixture = self.fixture
        scene = importlib.import_module(fixture.control.__package__ + '.tapo_scenes')
        fixture.scene_mock.side_effect = scene.set_tapo_scene_from_info
        renewing, healthy_sent, state = threading.Event(), threading.Event(), {}
        async def renew():
            state.update(loop=asyncio.get_running_loop(), release=asyncio.Event())
            renewing.set()
            await state['release'].wait()
            expired.failure = None
        class HealthyBuilder(Builder):
            def with_fields(self, **fields):
                return HealthyBuilder({**self.fields, **fields})
            async def send(self, device):
                await super().send(device)
                healthy_sent.set()
        expired = SimpleNamespace(set=lambda: Builder(), writes=[], failure=expired_session(),
                                  refresh_session=AsyncMock(side_effect=renew))
        healthy = SimpleNamespace(set=lambda: HealthyBuilder(), writes=[], failure=None,
                                  refresh_session=AsyncMock())
        for name, device in [('expired', expired), ('healthy', healthy)]:
            fixture.add_device(name, 'bulb').update(tapo_model='L530')
            fixture.control._tapo_handles[name] = device
        with ThreadPoolExecutor() as pool:
            request = pool.submit(self.post, names=('expired', 'healthy'))
            try:
                self.assertTrue(renewing.wait(2))
                self.assertTrue(healthy_sent.wait(2), 'Healthy bulb held behind session renewal')
                self.assertFalse(request.done())
            finally:
                if state: state['loop'].call_soon_threadsafe(state['release'].set)
            result = request.result(2).get_json()
        self.assertTrue(result['ok'], result)
        self.assertEqual(result['okCount'], 2)
        self.assertEqual(len(expired.writes), 2)
        self.assertEqual(len(healthy.writes), 1)
        expired.refresh_session.assert_awaited_once()
        healthy.refresh_session.assert_not_awaited()
        self.assertTrue(fixture.clients['tapo:expired']['tapo_is_on'])
        self.assertEqual(fixture.queue._entries, {})

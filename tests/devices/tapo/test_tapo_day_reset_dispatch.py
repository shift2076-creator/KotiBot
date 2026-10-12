"""Daily presets use the same combined writer and yield to user commands."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import json
from pathlib import Path
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

from subsystems.automations import automations_routes as module


class EndPass(BaseException):
    pass


class DayResetDispatchTests(unittest.TestCase):
    def setUp(self):
        from tests.devices.tapo.test_tapo_dashboard_commands import TapoDashboardCommandTests
        self.fixture = TapoDashboardCommandTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.context = {**self.fixture.context,
                        'client_role_cam': 'CAM', 'client_role_dss': 'DSS', 'client_role_key': 'KEY'}
        self.names = [f'light{n}' for n in range(12)]
        schemes, active = {}, {}
        for name in self.names:
            self.fixture.add_device(name, 'bulb').update(tapo_is_on=True, tapo_supports_brightness=True)
            key = 'device:tapo:' + name
            schemes[key] = [dict(mode='day', preset=dict(brightness=40))]
            active[key] = 'evening'
        Path(self.context['tapo_lighting_state_file']).write_text(json.dumps(dict(schemes=schemes, activeSchemes=active)))
        Path(self.context['automation_state_file']).write_text(json.dumps(dict(tapo_day_reset=dict(enabled=True, resetHour=0))))
        wake = SimpleNamespace(clear=Mock(), set=Mock(), wait=Mock(side_effect=EndPass))
        with patch.object(module, 'Event', return_value=wake):
            module.register_automation_routes(self.fixture.app, self.context)
        self.loop = self.fixture.app.config['KOTIBOT_AUTOMATIONS_LOOP']
        self.clock = SimpleNamespace(now=lambda: datetime(2026, 10, 12, 9))

    def run_pass(self):
        with self.assertRaises(EndPass), patch.object(module, 'datetime', self.clock):
            self.loop()

    def test_all_twelve_devices_start_one_combined_operation_without_worker_limit(self):
        started, state, calls = threading.Event(), {}, []
        async def send(item, commands):
            if not state:
                state.update(loop=asyncio.get_running_loop(), release=asyncio.Event())
            calls.append((item, commands))
            if len(calls) == 12:
                started.set()
            await state['release'].wait()
            return dict(device={**item, 'brightness': 40})
        with patch.object(module, 'set_tapo_scene_from_info', AsyncMock(side_effect=send)), ThreadPoolExecutor() as pool:
            task = pool.submit(self.run_pass)
            try:
                self.assertTrue(started.wait(2), f'Only started {len(calls)}')
                self.assertFalse(task.done())
            finally:
                if state: state['loop'].call_soon_threadsafe(state['release'].set)
            task.result(2)
        self.assertEqual(len(calls), 12)
        self.assertTrue(all([c['action'] for c in commands] == ['brightness_no_power'] for _, commands in calls))
        self.assertTrue(all(self.fixture.clients['tapo:'+name]['tapo_brightness'] == 40 for name in self.names))
        self.assertEqual(self.fixture.queue._entries, {})

    def test_busy_device_is_skipped_and_does_not_block_healthy_devices(self):
        busy = self.fixture.queue.reserve('tapo:light0')
        async def send(item, commands):
            return dict(device={**item, 'brightness': 40})
        try:
            with patch.object(module, 'set_tapo_scene_from_info', AsyncMock(side_effect=send)) as writer:
                self.run_pass()
            self.assertEqual(writer.await_count, 11)
            self.assertNotIn('light0', [call.args[0]['id'] for call in writer.await_args_list])
            config = json.loads(Path(self.context['automation_state_file']).read_text())
            self.assertNotEqual(config['tapo_day_reset'].get('lastRunDate'), '2026-10-12')
        finally:
            busy.cancel()
        self.assertEqual(self.fixture.queue._entries, {})

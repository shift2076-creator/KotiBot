"""Scheduled commands share real dashboard ordering; device I/O is synthetic."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime
import inspect
import threading
import unittest
from unittest.mock import AsyncMock, Mock, patch

from subsystems.automations import automations_routes as automation
from tests.devices.tapo import test_tapo_dashboard_commands as dashboard_tests


class ScheduledTapoCommandTests(unittest.TestCase):
    def setUp(self):
        dashboard = self.dashboard = dashboard_tests.TapoDashboardCommandTests('runTest')
        self.addCleanup(dashboard.doCleanups)
        dashboard.setUp()
        self.clients, self.target = dashboard.clients, dashboard.target
        self.queue, self.lock = dashboard.queue, dashboard.lock
        self.source = self.add_source('phone', 'plug')
        self.activity = Mock()
        self.automation_state = {
            automation.AUTOMATION_TYPE_TAPO_RECHARGE: {'phone': self.rule('phone', 'plug')},
            automation.AUTOMATION_TYPE_TAPO_DAY_RESET: dict(enabled=True, resetHour=6),
        }
        self.lighting_state = {
            'activeSchemes': {'device:tapo:plug': 'night'},
            'schemes': {'device:tapo:plug': [dict(mode='day', preset={
                'colorTemperature': 3700, 'brightness': 45,
            })]},
        }
        context = dict(dashboard.context, client_role_cam='CAM', client_role_dss='DSS',
                       client_role_key='KEY', activity_log=self.activity)
        automation.register_automation_routes(dashboard.app, context)
        closures = inspect.getclosurevars(dashboard.app.config['KOTIBOT_AUTOMATIONS_LOOP']).nonlocals
        self.recharge = closures['run_tapo_recharge_once']
        self.day_reset = closures['run_tapo_day_reset_once']
        self.sent = []
        self.effect = None
        self.patch('run_async', side_effect=asyncio.run)
        self.send = self.patch('set_tapo_device_from_info', new=AsyncMock(side_effect=self.device))
        self.patch('read_json', side_effect=lambda path: deepcopy(
            self.lighting_state if path == context['tapo_lighting_state_file'] else self.automation_state))
        def write(path, data):
            store = self.lighting_state if path == context['tapo_lighting_state_file'] else self.automation_state
            store.clear()
            store.update(deepcopy(data))
        self.patch('write_json_atomic', side_effect=write)
        self.patch('datetime').now.return_value = datetime(2026, 9, 27, 8, 0)

    def patch(self, name, **kwargs):
        patcher = patch.object(automation, name, **kwargs)
        self.addCleanup(patcher.stop)
        return patcher.start()

    def add_source(self, name, target):
        source = dict(deviceID=name, clientName=name, clientRole='KEY', provisioned=True,
                      battery=10, last_seen=1000)
        self.clients[name] = source
        return source

    @staticmethod
    def rule(source, target):
        return dict(enabled=True, clientName=source, targetID='tapo:' + target,
                    targetDeviceID='tapo:' + target, lowBattery=20, fullBattery=100)

    async def device(self, item, action, value):
        self.sent.append((item['id'], action))
        if self.effect:
            return self.effect(item, action, value)
        device = deepcopy(item)
        if action in ('on', 'off'):
            device['is_on'] = action == 'on'
        elif action == 'brightness_no_power':
            device['brightness'] = value
        elif action == 'color_temperature_no_power':
            device['color_temperature'] = value
        return dict(ok=True, device=device)

    def enable_day_reset(self):
        self.target.update(tapo_is_on=True, tapo_kind='bulb', tapo_model='L530',
                           tapo_supports_brightness=True, tapo_supports_color_temp=True,
                           tapo_brightness=10, tapo_color_temperature=2700)

    def while_queued(self, operation, change):
        first = self.queue.reserve('plug')
        reserved = threading.Event()
        original = self.queue.reserve
        def reserve(*args, **kwargs):
            slot = original(*args, **kwargs)
            reserved.set()
            return slot
        with patch.object(self.queue, 'reserve', side_effect=reserve), ThreadPoolExecutor() as pool:
            future = pool.submit(operation)
            try:
                self.assertTrue(reserved.wait(1), 'Scheduled command did not join the shared queue')
                self.send.assert_not_awaited()
                acquired = self.lock.acquire(timeout=.2)
                self.assertTrue(acquired, 'Queue wait held the shared state lock')
                if acquired:
                    try:
                        change()
                    finally:
                        self.lock.release()
            finally:
                first.cancel()
            future.result(2)
        self.assertEqual(self.queue._entries, {})

    def during_send(self, operation, change):
        entered, release = threading.Event(), threading.Event()
        def blocked(item, action, value):
            entered.set()
            self.assertTrue(release.wait(2), 'Test did not release device I/O')
            return dict(ok=True, device=dict(is_on=True, brightness=45))
        self.effect = blocked
        with ThreadPoolExecutor() as pool:
            future = pool.submit(operation)
            try:
                self.assertTrue(entered.wait(1))
                acquired = self.lock.acquire(timeout=.2)
                self.assertTrue(acquired, 'Scheduled device I/O held the shared state lock')
                if acquired:
                    try:
                        change()
                    finally:
                        self.lock.release()
            finally:
                release.set()
            future.result(2)
        self.assertEqual(self.queue._entries, {})

    def test_recharge_rechecks_power_after_waiting_in_dashboard_queue(self):
        self.while_queued(self.recharge, lambda: self.target.update(tapo_is_on=True))
        self.send.assert_not_awaited()
        self.activity.record_event.assert_not_called()

    def test_recharge_rejects_replacement_removal_and_identity_change_while_queued(self):
        for change in ('replace', 'remove', 'readdress'):
            with self.subTest(change=change):
                self.clients['tapo:plug'] = self.target
                self.target['tapo_ip'] = '192.0.2.1'
                def edit():
                    if change == 'replace':
                        self.clients['tapo:plug'] = deepcopy(self.target)
                    elif change == 'remove':
                        self.clients.pop('tapo:plug')
                    else:
                        self.target['tapo_ip'] = '192.0.2.2'
                self.while_queued(self.recharge, edit)
                self.send.assert_not_awaited()
        self.dashboard.save.assert_not_called()

    def test_recharge_rejects_late_result_for_replaced_client(self):
        replacement = deepcopy(self.target)
        self.during_send(self.recharge, lambda: self.clients.update({'tapo:plug': replacement}))
        self.assertFalse(replacement['tapo_is_on'])
        self.assertNotIn('tapo_brightness', replacement)
        self.dashboard.save.assert_not_called()
        self.activity.record_event.assert_not_called()

    def test_recharge_rechecks_battery_freshness_after_queue_wait(self):
        self.while_queued(self.recharge, lambda: self.source.update(last_seen=1))
        self.send.assert_not_awaited()

    def test_recharge_rechecks_battery_value_after_queue_wait(self):
        self.while_queued(self.recharge, lambda: self.source.update(battery=100))
        self.send.assert_not_awaited()

    def test_offline_device_does_not_delay_other_device_or_restore_its_old_result(self):
        fast = self.dashboard.add_device('fast')
        self.add_source('phone2', 'fast')
        self.automation_state[automation.AUTOMATION_TYPE_TAPO_RECHARGE]['phone2'] = self.rule('phone2', 'fast')
        entered, release, fast_sent = threading.Event(), threading.Event(), threading.Event()
        def send(item, action, value):
            if item['id'] == 'plug':
                entered.set()
                self.assertTrue(release.wait(2))
                raise TimeoutError('offline fixture')
            fast_sent.set()
            return dict(ok=True, device=dict(is_on=True))
        self.effect = send
        with ThreadPoolExecutor() as pool:
            future = pool.submit(self.recharge)
            try:
                self.assertTrue(entered.wait(1))
                self.assertTrue(fast_sent.wait(1), 'Healthy charger waited for offline device')
                # The real route waits for fast's scheduled slot and must see
                # its reconciled result before applying the newer manual OFF.
                response = self.dashboard.post('off', device='fast')
                self.assertEqual(response.status_code, 200)
                self.assertFalse(fast['tapo_is_on'])
            finally:
                release.set()
            future.result(2)
        self.assertFalse(fast['tapo_is_on'], 'Late batch reconciliation overwrote manual OFF')
        self.assertEqual(len(self.sent), 2)

    def test_queue_timeout_releases_reservation_without_sending(self):
        self.queue.timeout = .02
        first = self.queue.reserve('plug')
        try:
            self.recharge()
            self.send.assert_not_awaited()
        finally:
            first.cancel()
        self.assertEqual(self.queue._entries, {})
        self.recharge()
        self.assertTrue(self.target['tapo_is_on'])
        self.send.assert_awaited_once()

    def test_child_transport_input_cannot_mutate_registry_on_failure(self):
        self.target['tapo_children'] = [dict(id='socket', is_on=False)]
        self.automation_state[automation.AUTOMATION_TYPE_TAPO_RECHARGE]['phone']['child_id'] = 'socket'
        def fail(item, action, value):
            self.assertEqual(value['child_id'], 'socket')
            item['children'][0]['is_on'] = True
            raise TimeoutError('lost reply')
        self.effect = fail
        self.recharge()
        self.assertFalse(self.target['tapo_children'][0]['is_on'])
        self.send.assert_awaited_once()
        self.dashboard.save.assert_not_called()

    def test_explicit_failure_result_is_not_reconciled_or_logged_as_success(self):
        self.effect = lambda *_: dict(ok=False, error='fixture failure', device=dict(is_on=True))
        self.recharge()
        self.assertFalse(self.target['tapo_is_on'])
        self.dashboard.save.assert_not_called()
        self.activity.record_event.assert_not_called()

    def test_daily_reset_rechecks_power_after_queue_wait(self):
        self.enable_day_reset()
        self.while_queued(self.day_reset, lambda: self.target.update(tapo_is_on=False))
        self.send.assert_not_awaited()
        self.assertFalse(self.target['tapo_is_on'])

    def test_daily_reset_rejects_replacement_and_stops_remaining_commands(self):
        self.enable_day_reset()
        replacement = dict(self.target, tapo_brightness=77)
        self.during_send(self.day_reset, lambda: self.clients.update({'tapo:plug': replacement}))
        self.assertEqual(replacement['tapo_brightness'], 77)
        self.assertEqual(self.lighting_state['activeSchemes']['device:tapo:plug'], 'night')
        self.assertNotIn('lastRunDate', self.automation_state[automation.AUTOMATION_TYPE_TAPO_DAY_RESET])
        self.send.assert_awaited_once()
        self.dashboard.save.assert_not_called()

    def test_daily_sequence_finishes_before_waiting_manual_command(self):
        self.enable_day_reset()
        entered, release, manual_reserved = threading.Event(), threading.Event(), threading.Event()
        original_reserve = self.queue.reserve
        def reserve(*args, **kwargs):
            slot = original_reserve(*args, **kwargs)
            if entered.is_set():
                manual_reserved.set()
            return slot
        def send(item, action, value):
            if action == 'color_temperature_no_power':
                entered.set()
                self.assertTrue(release.wait(2))
                return dict(ok=True, device=dict(color_temperature=value))
            self.assertEqual(item['color_temperature'], 3700, 'Sequence reused stale transport input')
            return dict(ok=True, device=dict(brightness=value))
        self.effect = send
        def manual(item, action, value):
            self.sent.append((item['id'], 'manual:' + action))
            self.assertEqual(item['brightness'], 45, 'Slot released before reconciliation')
            return dict(ok=True, device=dict(is_on=False))
        self.dashboard.device_effect = manual
        with patch.object(self.queue, 'reserve', side_effect=reserve), ThreadPoolExecutor() as pool:
            daily = pool.submit(self.day_reset)
            try:
                self.assertTrue(entered.wait(1))
                user = pool.submit(self.dashboard.post, 'off')
                self.assertTrue(manual_reserved.wait(1))
            finally:
                release.set()
            daily.result(2)
            self.assertEqual(user.result(2).status_code, 200)
        self.assertEqual(self.sent, [('plug', 'color_temperature_no_power'),
                                     ('plug', 'brightness_no_power'), ('plug', 'manual:off')])
        self.assertFalse(self.target['tapo_is_on'])
        self.assertEqual(self.queue._entries, {})

    def test_partial_daily_failure_preserves_success_without_marking_day_complete(self):
        self.enable_day_reset()
        def send(item, action, value):
            if action == 'brightness_no_power':
                raise TimeoutError('lost reply')
            return dict(ok=True, device=dict(color_temperature=value))
        self.effect = send
        self.day_reset()
        self.assertEqual(self.target['tapo_color_temperature'], 3700)
        self.assertEqual(self.target['tapo_brightness'], 10)
        self.dashboard.save.assert_called_once()
        self.assertEqual(self.lighting_state['activeSchemes']['device:tapo:plug'], 'night')
        self.assertNotIn('lastRunDate', self.automation_state[automation.AUTOMATION_TYPE_TAPO_DAY_RESET])
        self.activity.record_event.assert_not_called()
        self.day_reset()
        self.assertEqual(self.send.await_count, 2, 'Failure was retried without the existing backoff')


if __name__ == '__main__':
    unittest.main()

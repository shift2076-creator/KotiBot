"""Audit integration probes using only synthetic clients and local workers."""
import asyncio
import json
from pathlib import Path
import sys
import time
from threading import Event, Lock
from unittest.mock import AsyncMock, patch

from audit_support import source_root
ROOT = source_root()
sys.path.insert(0, str(ROOT))
from flask import Flask
from server_core.routes import register_server_routes
from waitress.adjustments import Adjustments
from waitress.task import ThreadedTaskDispatcher
import importlib.util
import types
from subsystems.automations import trigger_routes

RESULTS = {}


def load_tapo_control():
    package_name = "_kotibot_tapo_command_integrity"
    module_name = f"{package_name}.tapo_control"

    for loaded_name in list(sys.modules):
        if loaded_name == package_name or loaded_name.startswith(f"{package_name}."):
            sys.modules.pop(loaded_name, None)

    package = types.ModuleType(package_name)
    package.__path__ = [str((ROOT / 'subsystems/client-tapo'))]
    sys.modules[package_name] = package

    tapo_stub = types.ModuleType("tapo")
    tapo_stub.ApiClient = object

    spec = importlib.util.spec_from_file_location(
        module_name,
        (ROOT / 'subsystems/client-tapo') / "tapo_control.py",
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module

    with (
        patch.dict(sys.modules, {"tapo": tapo_stub}),
        patch(
            "server_core.credentials.read_text_credential",
            return_value="fixture-credential",
        ),
    ):
        spec.loader.exec_module(module)

    return module



def probe_stream_capacity():
    active = Event()
    active.set()
    class Security:
        def dashboard_token_authorized(self, token):
            return active.is_set()
    listeners = []
    app = Flask('audit-stream-fixture')
    register_server_routes(app, dict(state_lock=Lock(), sse_listeners=listeners,
        clean_zone_name=str, security=Security(), current_status_payload=lambda: {'clients': []}))
    dispatcher = ThreadedTaskDispatcher()
    workers = Adjustments().threads
    dispatcher.set_thread_count(workers)
    class StreamTask:
        def __init__(self):
            self.started = Event()
            self.finished = Event()
        def service(self):
            try:
                with app.test_request_context('/api/status/stream'):
                    response = app.view_functions['status_stream']()
                for _ in response.response:
                    self.started.set()
            finally:
                self.finished.set()
        def cancel(self):
            pass
    class ShortTask:
        def __init__(self):
            self.ran = Event()
        def service(self):
            self.ran.set()
        def cancel(self):
            pass
    streams = [StreamTask() for _ in range(workers)]
    short = ShortTask()
    try:
        for stream in streams:
            dispatcher.add_task(stream)
        assert all(stream.started.wait(2) for stream in streams)
        dispatcher.add_task(short)
        blocked = not short.ran.wait(.2)
        RESULTS['sse-worker-capacity'] = dict(default_workers=workers, open_streams=len(listeners),
            short_request_blocked=blocked)
        assert workers == 4 and blocked
    finally:
        active.clear()
        for queue in list(listeners):
            queue.put_nowait('{}')
        assert all(stream.finished.wait(2) for stream in streams)
        assert short.ran.wait(2)
        dispatcher.shutdown(timeout=2)
    RESULTS['sse-worker-capacity']['short_request_resumed_after_streams_closed'] = True


def probe_cancelled_tapo_connect():
    control = load_tapo_control()
    original_lock = control._tapo_handle_connect_lock
    attempted, acquired = Event(), Event()
    class ObservedLock:
        def acquire(self):
            attempted.set()
            result = original_lock.acquire()
            acquired.set()
            return result
        def release(self):
            original_lock.release()
    async def scenario():
        original_lock.acquire()
        with patch.object(control, '_tapo_handle_connect_lock', ObservedLock()), \
             patch.object(control, '_tapo_host_reachable', new=AsyncMock(return_value=True)), \
             patch.object(control, '_connect_tapo_device', new=AsyncMock()) as connect:
            task = asyncio.create_task(control._get_tapo_device({'id': 'fixture', 'ip': '192.0.2.1'}))
            assert await asyncio.to_thread(attempted.wait, 2)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            original_lock.release()
            assert await asyncio.to_thread(acquired.wait, 2)
            orphaned = original_lock.locked()
            RESULTS['cancelled-tapo-connect'] = dict(task_cancelled=task.cancelled(),
                global_connection_lock_left_held=orphaned, connection_calls=connect.await_count)
            assert orphaned and connect.await_count == 0
            # Release the synthetic orphaned lock so the fixture leaves no workers stuck.
            original_lock.release()
    asyncio.run(scenario())


def probe_tapo_redundant_reads():
    from types import SimpleNamespace
    control = load_tapo_control()
    device = SimpleNamespace(get_device_info=AsyncMock(return_value={'device_on': True}))
    control._tapo_handles['fixture'] = device
    item = dict(id='fixture', ip='192.0.2.1', model='P100', device_type='SMART.TAPOPLUG', alias='Fixture')
    with patch.object(control, '_tapo_host_reachable', new=AsyncMock(return_value=True)) as reachable:
        result = asyncio.run(control._enrich_control_state(item))
    RESULTS['tapo-duplicate-read'] = dict(control_ready=result['control_ready'],
        reachability_probes=reachable.await_count, device_info_reads=device.get_device_info.await_count)
    assert result['control_ready'] and device.get_device_info.await_count == 2


def probe_tapo_discovery_unbounded_read():
    from types import SimpleNamespace
    control = load_tapo_control()
    async def scenario():
        entered = asyncio.Event()
        never = asyncio.Event()
        calls = 0
        async def device_info():
            nonlocal calls
            calls += 1
            if calls == 1:
                return {'device_on': True}
            entered.set()
            await never.wait()
        control._tapo_handles['fixture'] = SimpleNamespace(get_device_info=device_info)
        item = dict(id='fixture', ip='192.0.2.1', model='P100', device_type='SMART.TAPOPLUG', alias='Fixture')
        with patch.object(control, '_tapo_host_reachable', new=AsyncMock(return_value=True)), \
             patch.object(control, '_run_discovery_text', return_value='synthetic discovery'), \
             patch.object(control, '_parse_kasa_discovery', return_value=[item]), \
             patch.object(control, 'TAPO_DEVICE_CALL_TIMEOUT_SECONDS', .01), \
             patch.object(control, 'TAPO_DEVICE_REFRESH_TIMEOUT_SECONDS', .01):
            task = asyncio.create_task(control._discover_tapo(force=True))
            try:
                await asyncio.wait_for(entered.wait(), 1)
                await asyncio.sleep(.05)
                still_waiting = not task.done()
                RESULTS['tapo-discovery-unbounded-read'] = dict(
                    configured_call_timeout_seconds=.01, configured_refresh_timeout_seconds=.01,
                    observed_wait_seconds=.05, still_waiting=still_waiting, device_info_reads=calls)
                assert still_waiting and calls == 2
            finally:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
    asyncio.run(scenario())


def probe_automation_lock():
    from threading import Thread
    from unittest.mock import Mock
    lock = Lock()
    entered, release = Event(), Event()
    clients = {
        'door': {'deviceID': 'door', 'clientRole': 'DSS', 'provisioned': True},
        'tapo:fixture': {'deviceID': 'tapo:fixture', 'clientRole': 'TAPO',
                         'provisioned': True, 'tapo_is_on': False, 'tapo_kind': 'plug'},
    }
    routes = [{'from_deviceID': 'door', 'trigger': 'door_open', 'action': 'device',
               'to_deviceID': 'tapo:fixture', 'scope': 'automation'}]
    runtime = trigger_routes.register_trigger_routes(Flask('audit-trigger-fixture'), dict(
        state_lock=lock, clients=clients, get_routes=lambda: routes, set_routes=Mock(),
        client_role_cam='CAM', client_role_key='KEY',
        client_has_role=lambda c, role: c.get('clientRole') == role,
        get_clients_for_device=lambda d: [clients[d]], play_wav_file=Mock(),
        schedule_door_sound_repeat=Mock(), cancel_door_sound_repeat=Mock(),
        save_state=Mock(), broadcast_state=Mock()))
    observations = []
    def fake_network(_):
        observations.append(lock.locked())
        entered.set()
        assert release.wait(2)
        return {}
    def telemetry_caller():
        # The actual Android telemetry caller holds this same lock before firing routes.
        with lock:
            runtime['fire_door_routes'](clients['door'], 'open')
    with patch.object(trigger_routes, '_set_tapo_device_from_info', return_value=object()), \
         patch.object(trigger_routes, '_run_tapo_async', side_effect=fake_network):
        thread = Thread(target=telemetry_caller)
        thread.start()
        assert entered.wait(2)
        acquired = lock.acquire(timeout=.1)
        if acquired:
            lock.release()
        release.set()
        thread.join(2)
        assert not thread.is_alive()
    RESULTS['automation-network-lock'] = dict(lock_held_during_device_call=observations,
        concurrent_status_lock_available=acquired)
    assert observations == [True] and not acquired


if __name__ == '__main__':
    probe_stream_capacity()
    probe_cancelled_tapo_connect()
    probe_tapo_redundant_reads()
    probe_tapo_discovery_unbounded_read()
    probe_automation_lock()
    print(json.dumps(RESULTS, indent=2))

"""Audit-only fault injection. Imports core helpers, never the live server.

All filesystem writes use disposable fixtures. No real devices or credentials.
"""
import ast
from collections import Counter
import json
import logging
from pathlib import Path
from queue import Queue, Full, Empty
import sys
from tempfile import TemporaryDirectory
from threading import Event, Lock, Thread
from unittest.mock import Mock, patch

from audit_support import source_root
ROOT = source_root()
sys.path.insert(0, str(ROOT))
from flask import Flask
from server_core import io, state
from server_core.device_credentials import DeviceNotificationCredentialStore
from server_core.routes import register_server_routes
from server_core.status import build_status_runtime

logging.disable(logging.CRITICAL)
RESULTS = {}


def main_functions(names, globals_):
    tree = ast.parse((ROOT / 'kotibot_server.py').read_text())
    nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
    assert len(nodes) == len(names)
    for node in nodes:
        node.decorator_list = []
    exec(compile(ast.Module(body=nodes, type_ignores=[]), 'kotibot_server.py [isolated functions]', 'exec'), globals_)
    return globals_


def client(device='fixture', role='CAM', **extra):
    return dict(deviceID=device, clientName='Fixture', clientRole=role,
                provisioned=True, zone_name='Fixture zone', **extra)


def has_role(c, role):
    return role in ([c.get('clientRole')] if isinstance(c.get('clientRole'), str) else c.get('clientRole', []))


def state_context(root, clients=None):
    clients = {} if clients is None else clients
    routes = []
    ctx = dict(clients=clients, routes=routes,
               state_file=root/'server.json', security_actions_file=root/'actions.json',
               tapo_device_state_file=root/'tapo.json', matter_device_state_file=root/'matter.json',
               android_home_state_file=root/'android.json', automation_state_file=root/'automations.json',
               automation_type_tapo_recharge='recharge', automation_type_device_routes='routes',
               client_role_cam='CAM', client_role_dss='DSS', client_role_key='KEY', client_role_tapo='TAPO',
               open_angle_threshold=15, close_angle_threshold=10, client_has_role=has_role,
               clean_arm_state=lambda v: v or 'day', clean_zone_name=lambda v: v or '',
               init_client=lambda device: client(device), set_routes=lambda v: routes.__setitem__(slice(None), v),
               set_system_arm_state=Mock(), broadcast_state=Mock(), system_armed=False, system_arm_state='day')
    return ctx


def reset_io():
    with io._PENDING_LOCK:
        io._PENDING_WRITES.clear()
        io._FLUSHING_WRITES.clear()
        io._FAILED_READS.clear()


def probe_failed_boot():
    for malformed in ('invalid-json', 'wrong-schema'):
        with TemporaryDirectory() as temp, patch.object(io, 'start_json_writer'):
            root = Path(temp)
            ctx = state_context(root)
            (root/'server.json').write_text('{broken' if malformed == 'invalid-json' else '{"clients": 42}')
            for name, key in [('tapo', 'devices'), ('matter', 'devices'), ('android', 'clients')]:
                (root/f'{name}.json').write_text(json.dumps({key: {'fixture': {'clientName': 'Saved settings'}}}))
            (root/'actions.json').write_text('{"actions": []}')
            (root/'automations.json').write_text('{}')
            runtime = state.build_state_runtime(ctx)
            first = runtime['load_state']()
            queued = sorted(p.name for p in io._PENDING_WRITES)
            io.flush_json_writes()
            counts = {name: len(json.loads((root/f'{name}.json').read_text())[key])
                      for name, key in [('tapo', 'devices'), ('matter', 'devices'), ('android', 'clients')]}
            again = runtime['load_state']()
            RESULTS[f'boot-{malformed}'] = dict(first_return=first, second_return=again,
                queued_before_flush=queued, saved_subsystem_records_after_flush=counts)
            assert all(count == 0 for count in counts.values())
            reset_io()


def probe_broadcast_blocks_save():
    ctx = state_context(Path('/unused-fixture'))
    ctx['broadcast_state'] = Mock(side_effect=ValueError('Synthetic status failure'))
    with patch.object(state, 'write_json_atomic') as writer:
        result = state.build_state_runtime(ctx)['save_state']()
    RESULTS['broadcast-blocks-save'] = dict(return_value=result, persistence_calls=writer.call_count)
    assert writer.call_count == 0


def probe_unlocked_save():
    entered, release = Event(), Event()
    paused = [False]
    def pausing_role(c, role):
        if not paused[0]:
            paused[0] = True
            entered.set()
            assert release.wait(2)
        return has_role(c, role)
    ctx = state_context(Path('/unused-fixture'), {'one': client('one', 'KEY')})
    ctx['client_has_role'] = pausing_role
    caught = []
    def record_exception(*args, **kwargs):
        caught.append(type(sys.exc_info()[1]).__name__)
    with patch.object(state, 'read_json_object', return_value={}), \
         patch.object(state, 'write_json_atomic') as writer, \
         patch.object(state.LOGGER, 'exception', side_effect=record_exception):
        runtime = state.build_state_runtime(ctx)
        thread = Thread(target=runtime['save_state'])
        thread.start()
        assert entered.wait(2)
        ctx['clients']['two'] = client('two', 'KEY')
        release.set()
        thread.join(2)
        assert not thread.is_alive()
    RESULTS['concurrent-registry-save'] = dict(swallowed_exceptions=caught,
        partial_writes=writer.call_count, normal_writes=6)
    assert caught == ['RuntimeError'] and writer.call_count == 2


def probe_symlink():
    with TemporaryDirectory() as temp:
        root = Path(temp)
        target = root/'target.json'
        target.write_text('{"fixture": "before"}')
        link = root/'state.json'
        link.symlink_to(target)
        io.write_json_atomic_sync(link, {'fixture': 'after'})
        RESULTS['json-symlink'] = dict(link_still_present=link.is_symlink(),
            redirected_target_changed=json.loads(target.read_text())['fixture'] == 'after',
            redirected_backup_created=(root/'target.lkg.json').exists())
        assert RESULTS['json-symlink']['redirected_target_changed']
        reset_io()


def probe_credential_retry():
    with TemporaryDirectory() as temp:
        store = DeviceNotificationCredentialStore(Path(temp)/'tokens.json')
        with patch.object(store, '_save_unlocked', side_effect=OSError('Synthetic disk failure')) as save:
            try:
                store.set_token('fixture', 'synthetic-token', 1)
            except OSError:
                pass
            store.set_token('fixture', 'synthetic-token', 2)
            set_calls = save.call_count
            token_in_memory = bool(store.credential('fixture'))
        with patch.object(store, '_save_unlocked', side_effect=OSError('Synthetic disk failure')) as save:
            try:
                store.remove('fixture')
            except OSError:
                pass
            retry_result = store.remove('fixture')
            remove_calls = save.call_count
        RESULTS['credential-retry'] = dict(set_attempts=set_calls, token_in_memory=token_in_memory,
            remove_attempts=remove_calls, retry_remove_return=retry_result)
        assert set_calls == remove_calls == 1 and token_in_memory and retry_result is False


def probe_metadata_amplification():
    app = Flask('audit-metadata-fixture')
    payload = Mock(return_value={'clients': []})
    env = main_functions({'broadcast_state'}, dict(json=json, SSE_LISTENERS=[Queue(1)],
        current_status_payload=payload, Full=Full, Empty=Empty))
    broadcast = Mock(wraps=env['broadcast_state'])
    clients = {'fixture': client()}
    ctx = state_context(Path('/unused-fixture'), clients)
    ctx['broadcast_state'] = broadcast
    runtime = state.build_state_runtime(ctx)
    route_ctx = dict(ctx, state_lock=Lock(), sse_listeners=env['SSE_LISTENERS'],
                     current_status_payload=payload, save_state=runtime['save_state'],
                     client_role_dss='DSS', client_role_tapo='TAPO')
    register_server_routes(app, route_ctx)
    with patch.object(state, 'read_json_object', return_value={}), patch.object(state, 'write_json_atomic') as writer:
        response = app.test_client().post('/api/client-metadata', json={'deviceID': 'fixture', 'clientName': 'New fixture name'})
    RESULTS['metadata-amplification'] = dict(status=response.status_code, full_status_builds=payload.call_count,
        broadcasts=broadcast.call_count, state_documents_queued=writer.call_count)
    assert payload.call_count == 3 and broadcast.call_count == 2 and writer.call_count == 6


def status_context(clients):
    return dict(clients=clients, client_role_cam='CAM', client_role_dss='DSS', client_role_key='KEY',
        client_role_tapo='TAPO', client_role_unp='UNP', preview_viewer_ttl_seconds=30,
        stale_client_seconds=65, matter_stale_client_seconds=375, server_start_epoch=0,
        age_text=lambda _: 'fixture', clean_filename_part=str, clean_zone_name=lambda v: v or '',
        client_has_role=has_role, duration_text=str, now_epoch=lambda: 1000, now_local=lambda: 'fixture',
        voice_talk_active_for_target=lambda _: False)


def probe_stale_control():
    runtime = build_status_runtime(status_context({}))
    device = client('control', 'KEY', last_seen=0)
    snap = runtime['snapshot_client'](device)
    RESULTS['offline-control-status'] = dict(last_seen=0, stale=snap['stale'], key_status=snap['key_status'])
    assert snap['stale'] is False and snap['key_status'] == 'Online'


def probe_asset_builds():
    with TemporaryDirectory() as temp:
        root = Path(temp)
        icons = root/'dashboard-icons'
        icons.mkdir()
        (icons/'a.svg').write_text('<svg/>')
        (root/'KotiBot.svg').write_text('<svg/>')
        (icons/'icons.css').write_text('a{background:url("./a.svg")}b{background:url("../KotiBot.svg")}')
        themes, stripes = {}, {}
        for theme in ('dark', 'light'):
            themes[theme] = root/f'{theme}.css'
            stripes[theme] = root/f'{theme}.png'
            themes[theme].write_text('/* fixture */')
            stripes[theme].write_bytes(b'fixture')
        from base64 import b64encode
        env = main_functions({'dashboard_asset_data_uri', 'load_dashboard_icon_stylesheet', 'load_dashboard_theme_stylesheets'},
            dict(b64encode=b64encode, DASHBOARD_ICON_DIR=icons, DASHBOARD_ICON_CSS_FILE=icons/'icons.css',
                 DASHBOARD_THEME_CSS_FILES=themes, DASHBOARD_STRIPE_IMAGE_FILES=stripes))
        reads = []
        actual = Path.read_bytes
        def read(path):
            reads.append(path.name)
            return actual(path)
        with patch.object(Path, 'read_bytes', read):
            env['load_dashboard_theme_stylesheets']().get('dark')
            env['load_dashboard_theme_stylesheets']().get('dark')
        RESULTS['repeated-theme-build'] = dict(two_dark_requests_image_reads=reads)
        assert reads == ['dark.png', 'light.png', 'dark.png', 'light.png']


if __name__ == '__main__':
    for probe in (probe_failed_boot, probe_broadcast_blocks_save, probe_unlocked_save,
                  probe_symlink, probe_credential_retry, probe_metadata_amplification,
                  probe_stale_control, probe_asset_builds):
        probe()
    print(json.dumps(RESULTS, indent=2))

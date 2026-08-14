import ast
from copy import deepcopy
from pathlib import Path
from threading import RLock
import unittest

from server_core.clients import build_client_runtime
from server_core.status import build_status_runtime


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


class RequestStub:
    def __init__(self, payload):
        self.payload = dict(payload)

    def get_json(self, silent=False):
        return dict(self.payload)


class SecurityStub:
    def __init__(self, *, has_key=False, enrollment_pending=False, fail_state=False):
        self.has_key = has_key
        self.enrollment_pending = enrollment_pending
        self.fail_state = fail_state
        self.cancelled = []
        self.audits = []

    @staticmethod
    def normalize_device_id(value):
        value = str(value or '').strip()
        return value if value and ' ' not in value else ''

    def device_has_key(self, device_id):
        if self.fail_state:
            raise RuntimeError('protected state unavailable')
        return self.has_key

    def device_enrollment_pending(self, device_id):
        if self.fail_state:
            raise RuntimeError('protected state unavailable')
        return self.enrollment_pending

    def cancel_device_enrollment(self, device_id):
        self.cancelled.append(device_id)

    def audit(self, event, **fields):
        self.audits.append((event, dict(fields)))


def load_server_functions(namespace, *names):
    path = REPOSITORY_ROOT / 'kotibot_server.py'
    tree = ast.parse(
        path.read_text(encoding='utf-8'),
        filename=str(path),
    )
    functions = []

    for name in names:
        function = next(
            node
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == name
        )
        function.decorator_list = []
        functions.append(function)

    module = ast.Module(body=functions, type_ignores=[])
    ast.fix_missing_locations(module)
    exec(compile(module, str(path), 'exec'), namespace)
    return tuple(namespace[name] for name in names)


def load_request_policy():
    path = REPOSITORY_ROOT / 'subsystems' / 'security' / 'security_routes.py'
    tree = ast.parse(
        path.read_text(encoding='utf-8'),
        filename=str(path),
    )
    allowed_names = {
        'PUBLIC_LOGIN_ASSETS',
        'PUBLIC_LOGIN_ASSET_PREFIXES',
        'ENROLLMENT_PATHS',
        'DEVICE_SIGNED_PATHS',
        'DEVICE_SIGNED_PREFIXES',
    }
    body = [
        node
        for node in tree.body
        if (
            isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name)
                and target.id in allowed_names
                for target in node.targets
            )
        ) or (
            isinstance(node, ast.FunctionDef)
            and node.name in ('normalized_method', 'request_policy')
        )
    ]
    module = ast.Module(body=body, type_ignores=[])
    ast.fix_missing_locations(module)
    namespace = {}
    exec(compile(module, str(path), 'exec'), namespace)
    return namespace['request_policy']


class ControlReenrollmentRouteTests(unittest.TestCase):
    def setUp(self):
        self.clients = {}
        self.saved = []
        self.runtime = build_client_runtime({
            'clients': self.clients,
            'request_json': lambda: {},
            'request_ip': lambda: '127.0.0.1',
            'request_header': lambda name: '',
            'now_epoch': lambda: 1000.0,
            'clean_zone_name': lambda value: str(value or '').strip(),
            'cancel_door_sound_repeat': lambda device_id: None,
            'prune_routes_for_client_change': lambda *args, **kwargs: None,
            'system_armed': lambda: False,
            'android_home_apply_seen_client': lambda: None,
            'client_role_cam': 'CAM',
            'client_role_dss': 'DSS',
            'client_role_key': 'KEY',
            'client_role_tapo': 'TAPO',
            'client_role_unp': 'UNP',
            'door_recalibration_command_timeout_seconds': 30,
        })

    def call_route(self, payload, security):
        namespace = {
            'request': RequestStub(payload),
            'jsonify': lambda value: value,
            'SECURITY': security,
            'STATE_LOCK': RLock(),
            'CLIENTS': self.clients,
            'client_has_role': self.runtime['client_has_role'],
            'android_client_profile': self.runtime['android_client_profile'],
            'CLIENT_ROLE_CAM': 'CAM',
            'CLIENT_ROLE_DSS': 'DSS',
            'CLIENT_ROLE_KEY': 'KEY',
            'CLIENT_ROLE_TAPO': 'TAPO',
            'CLIENT_ROLE_UNP': 'UNP',
            'save_state': lambda: self.saved.append(deepcopy(self.clients)),
        }
        _, route = load_server_functions(
            namespace,
            'client_allows_device_key_handoff',
            're_enroll_client',
        )
        return route()

    @staticmethod
    def provisioned_client(role, **fields):
        client = {
            'deviceID': 'android-test',
            'clientName': 'Pocket Control',
            'clientRole': list(role),
            'provisioned': True,
            'source': 'android',
            'zone_name': '',
            'pending_command': {'unchanged': 1},
            'notification_settings': {'unchanged': True},
        }
        client.update(fields)
        return client

    def test_keyless_control_is_prepared_without_deleting_saved_state(self):
        client = self.provisioned_client(['KEY'])
        before = deepcopy(client)
        self.clients['android-test'] = client
        security = SecurityStub()

        response = self.call_route(
            {'deviceID': 'android-test'},
            security,
        )

        self.assertEqual(response, {
            'ok': True,
            'state': 'awaiting_device_handshake',
        })
        self.assertEqual(client['detectedRole'], 'KEY')
        self.assertEqual(client['clientRole'], 'UNP')
        self.assertIs(client['provisioned'], False)
        for field in (
            'deviceID',
            'clientName',
            'source',
            'zone_name',
            'pending_command',
            'notification_settings',
        ):
            self.assertEqual(client[field], before[field], field)
        self.assertEqual(security.cancelled, ['android-test'])
        self.assertEqual(len(self.saved), 1)
        self.assertEqual(
            security.audits,
            [(
                'device_reenrollment_prepared',
                {'status': 200, 'client_class': 'control'},
            )],
        )
        response_text = repr(response).lower()
        self.assertNotIn('token', response_text)
        self.assertNotIn('secret', response_text)
        self.assertNotIn('deviceid', response_text)

    def test_keyless_monitor_keeps_its_canonical_capabilities(self):
        client = self.provisioned_client(
            ['CAM', 'DSS'],
            clientName='Entry Monitor',
            zone_name='Entry',
        )
        self.clients['android-test'] = client

        response = self.call_route(
            {'deviceId': 'android-test'},
            SecurityStub(),
        )

        self.assertIs(response['ok'], True)
        self.assertEqual(client['detectedRole'], 'CAM,DSS')
        self.assertEqual(client['clientRole'], 'UNP')
        self.assertEqual(client['clientName'], 'Entry Monitor')
        self.assertEqual(client['zone_name'], 'Entry')

    def test_existing_key_fails_closed_without_mutation(self):
        client = self.provisioned_client(['KEY'])
        before = deepcopy(client)
        self.clients['android-test'] = client
        security = SecurityStub(has_key=True)

        payload, status = self.call_route(
            {'deviceID': 'android-test'},
            security,
        )

        self.assertEqual(status, 409)
        self.assertEqual(payload['error'], 'device_key_present')
        self.assertEqual(client, before)
        self.assertEqual(security.cancelled, [])
        self.assertEqual(self.saved, [])

    def test_pending_enrollment_is_not_invalidated(self):
        client = self.provisioned_client(['KEY'])
        before = deepcopy(client)
        self.clients['android-test'] = client
        security = SecurityStub(enrollment_pending=True)

        payload, status = self.call_route(
            {'deviceID': 'android-test'},
            security,
        )

        self.assertEqual(status, 409)
        self.assertEqual(
            payload['error'],
            'device_enrollment_in_progress',
        )
        self.assertEqual(client, before)
        self.assertEqual(security.cancelled, [])
        self.assertEqual(self.saved, [])

    def test_non_first_party_and_non_provisioned_clients_are_rejected(self):
        cases = (
            (
                self.provisioned_client(
                    ['TAPO'],
                    source='tapo',
                ),
                'client_not_reenrollable',
            ),
            (
                self.provisioned_client(
                    ['KEY'],
                    provisioned=False,
                ),
                'client_already_unprovisioned',
            ),
        )

        for client, expected_error in cases:
            with self.subTest(expected_error=expected_error):
                self.clients = {'android-test': client}
                self.saved = []
                before = deepcopy(client)
                payload, status = self.call_route(
                    {'deviceID': 'android-test'},
                    SecurityStub(),
                )
                self.assertEqual(status, 409)
                self.assertEqual(payload['error'], expected_error)
                self.assertEqual(client, before)
                self.assertEqual(self.saved, [])

    def test_invalid_unknown_and_unavailable_security_state_fail_closed(self):
        payload, status = self.call_route(
            {'deviceID': 'bad id'},
            SecurityStub(),
        )
        self.assertEqual(status, 400)
        self.assertEqual(payload['error'], 'invalid_deviceID')

        payload, status = self.call_route(
            {'deviceID': 'missing'},
            SecurityStub(),
        )
        self.assertEqual(status, 404)
        self.assertEqual(payload['error'], 'client_not_found')

        client = self.provisioned_client(['KEY'])
        before = deepcopy(client)
        self.clients['android-test'] = client
        security = SecurityStub(fail_state=True)
        payload, status = self.call_route(
            {'deviceID': 'android-test'},
            security,
        )
        self.assertEqual(status, 503)
        self.assertEqual(payload['error'], 'security_state_unavailable')
        self.assertEqual(client, before)
        self.assertEqual(self.saved, [])
        self.assertEqual(
            security.audits,
            [(
                'device_reenrollment_blocked',
                {
                    'status': 503,
                    'reason': 'security_state_unavailable',
                },
            )],
        )


class DeviceKeyStatusTests(unittest.TestCase):
    @staticmethod
    def has_role(client, role):
        roles = client.get('clientRole', [])
        return role in (roles if isinstance(roles, list) else [roles])

    @classmethod
    def android_profile(cls, client):
        roles = client.get('clientRole', [])
        roles = roles if isinstance(roles, list) else [roles]
        source = str(client.get('source') or '').lower()

        if source in ('tapo', 'matter') or 'TAPO' in roles:
            return {'clientClass': 'non_android', 'capabilities': []}
        if 'KEY' in roles:
            return {'clientClass': 'control', 'capabilities': ['KEY']}
        if 'CAM' in roles and 'DSS' in roles:
            return {
                'clientClass': 'monitor',
                'capabilities': ['CAM', 'DSS'],
            }
        return {'clientClass': 'unclassified', 'capabilities': []}

    def snapshot(self, client, key_callback):
        runtime = build_status_runtime({
            'clients': {client['deviceID']: client},
            'client_role_cam': 'CAM',
            'client_role_dss': 'DSS',
            'client_role_key': 'KEY',
            'client_role_tapo': 'TAPO',
            'client_role_unp': 'UNP',
            'preview_viewer_ttl_seconds': 5,
            'stale_client_seconds': 60,
            'matter_stale_client_seconds': 60,
            'server_start_epoch': 1,
            'age_text': lambda value: 'now',
            'clean_filename_part': lambda value: str(value or ''),
            'clean_zone_name': lambda value: str(value or '').strip(),
            'client_has_role': self.has_role,
            'android_client_profile': self.android_profile,
            'device_has_key': key_callback,
            'duration_text': lambda value: str(value),
            'now_epoch': lambda: 1000.0,
            'now_local': lambda: None,
            'voice_talk_active_for_target': lambda device_id: False,
        })
        return runtime['snapshot_client'](client)

    @staticmethod
    def client(role, **fields):
        client = {
            'deviceID': 'android-status',
            'clientName': 'Status Client',
            'clientRole': list(role),
            'provisioned': True,
            'source': 'android',
            'zone_name': '',
            'last_seen': 999.0,
        }
        client.update(fields)
        return client

    def test_dashboard_receives_only_a_boolean_key_presence_signal(self):
        for has_key in (False, True):
            with self.subTest(has_key=has_key):
                result = self.snapshot(
                    self.client(['KEY']),
                    lambda device_id, value=has_key: value,
                )
                self.assertIs(
                    result['deviceKeyProvisioned'],
                    has_key,
                )
                self.assertNotIn('kotiKeyID', result)
                self.assertNotIn('kotiKeySecret', result)
                self.assertNotIn('enrollmentToken', result)

    def test_uncertain_or_non_first_party_state_never_enables_recovery(self):
        def unavailable(device_id):
            raise RuntimeError('protected state unavailable')

        uncertain = self.snapshot(
            self.client(['KEY']),
            unavailable,
        )
        external = self.snapshot(
            self.client(['TAPO'], source='tapo'),
            lambda device_id: False,
        )

        self.assertNotIn('deviceKeyProvisioned', uncertain)
        self.assertNotIn('deviceKeyProvisioned', external)


class ControlReenrollmentContractTests(unittest.TestCase):
    @staticmethod
    def source(relative_path):
        return (REPOSITORY_ROOT / relative_path).read_text(encoding='utf-8')

    @staticmethod
    def source_block(source, start_marker, end_marker):
        start = source.index(start_marker)
        end = source.index(end_marker, start)
        return source[start:end]

    def test_route_defaults_to_authenticated_same_origin_dashboard_policy(self):
        self.assertEqual(
            load_request_policy()('POST', '/api/re-enroll-client'),
            'dashboard',
        )

    def test_production_route_preserves_client_and_never_returns_credentials(self):
        source = self.source('kotibot_server.py')
        route = self.source_block(
            source,
            "@app.post('/api/re-enroll-client')",
            "@app.route('/api/remove-client'",
        )

        self.assertIn('client_allows_device_key_handoff(client)', route)
        self.assertIn("SECURITY.device_has_key(deviceID)", route)
        self.assertIn(
            "SECURITY.device_enrollment_pending(deviceID)",
            route,
        )
        self.assertIn("client['detectedRole']", route)
        self.assertIn("client['clientRole'] = CLIENT_ROLE_UNP", route)
        self.assertIn("client['provisioned'] = False", route)
        self.assertIn('SECURITY.cancel_device_enrollment(deviceID)', route)
        self.assertNotIn('revoke_device_key', route)
        self.assertNotIn('issue_device_key', route)
        self.assertNotIn('begin_device_enrollment', route)
        self.assertNotIn('CLIENTS.pop', route)
        self.assertNotIn('prune_routes_for_client_change', route)
        self.assertNotIn('DEVICE_NOTIFICATION_CREDENTIALS', route)
        self.assertNotIn('enrollmentToken', route)
        self.assertNotIn('kotiKeySecret', route)

    def test_status_wiring_and_dashboard_action_are_fail_closed(self):
        server_source = self.source('kotibot_server.py')
        actions_source = self.source('static/js/dashboard-actions.js')
        events_source = self.source('static/js/dashboard-events.js')
        action = self.source_block(
            actions_source,
            'window.reenrollClient = async function',
            'window.removeClient = async function',
        )
        menu = self.source_block(
            actions_source,
            'window.renderDashboardClientMenu = function',
            'window.hideAudioModal = function',
        )

        self.assertIn("'device_has_key': SECURITY.device_has_key,", server_source)
        self.assertIn('client.deviceKeyProvisioned === false', menu)
        self.assertIn('["control", "monitor"]', menu)
        self.assertIn('data-dashboard-action="re-enroll-client"', menu)
        self.assertIn('postJson("/api/re-enroll-client"', action)
        self.assertIn('refreshStatusData({ forceNetwork: true })', action)
        self.assertNotIn('setInterval', action)
        self.assertNotIn('enrollmentToken', action)
        self.assertNotIn('kotiKeySecret', action)
        self.assertIn('"re-enroll-client": async (el)', events_source)
        self.assertIn('window.reenrollClient?.(el.dataset.deviceId)', events_source)


if __name__ == '__main__':
    unittest.main()

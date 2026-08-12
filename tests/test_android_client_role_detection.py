import ast
import re
import unittest
from pathlib import Path
from threading import RLock

from server_core.clients import build_client_runtime


REPO_ROOT = Path(__file__).resolve().parents[1]


class ProvisionRequest:
    def __init__(self, payload):
        self.payload = dict(payload)

    def get_json(self):
        return dict(self.payload)


class ProvisionSecurity:
    def __init__(self, enrollment_pending):
        self.enrollment_pending = enrollment_pending
        self.checked_device_ids = []

    def device_enrollment_pending(self, device_id):
        self.checked_device_ids.append(device_id)
        return self.enrollment_pending


def load_server_provision_function(namespace):
    path = REPO_ROOT / 'kotibot_server.py'
    tree = ast.parse(
        path.read_text(encoding='utf-8'),
        filename=str(path),
    )
    provision = next(
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == 'provision'
    )
    provision.decorator_list = []
    module = ast.Module(body=[provision], type_ignores=[])
    ast.fix_missing_locations(module)
    exec(compile(module, str(path), 'exec'), namespace)
    return namespace['provision']


class AndroidClientRoleDetectionTests(unittest.TestCase):
    @staticmethod
    def source_block(source, start_marker, end_marker):
        start = source.index(start_marker)
        end = source.index(end_marker, start)
        return source[start:end]

    def setUp(self):
        self.clients = {}
        self.request_data = {}
        self.request_headers = {}

        self.runtime = build_client_runtime({
            'clients': self.clients,
            'request_json': lambda: dict(self.request_data),
            'request_ip': lambda: '127.0.0.1',
            'request_header': lambda name: self.request_headers.get(name, ''),
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

    def new_client(self, device_id='android-1'):
        return self.runtime['get_unprovisioned_client'](device_id)

    def server_provision(self, payload, enrollment_pending):
        self.request_data = dict(payload)
        security = ProvisionSecurity(enrollment_pending)
        saved_states = []
        namespace = {
            'request': ProvisionRequest(payload),
            'jsonify': lambda value: value,
            'SECURITY': security,
            'STATE_LOCK': RLock(),
            'get_unprovisioned_client': self.runtime['get_unprovisioned_client'],
            'clean_zone_name': lambda value: str(value or '').strip(),
            'normalize_client_roles': self.runtime['normalize_client_roles'],
            'android_client_profile': self.runtime['android_client_profile'],
            'CLIENT_ROLE_KEY': 'KEY',
            'CLIENT_ROLE_CAM': 'CAM',
            'save_state': lambda: saved_states.append(dict(self.clients)),
        }
        provision = load_server_provision_function(namespace)
        return provision(), security, saved_states

    def test_key_telemetry_overrides_conflicting_reported_camera_role(self):
        client = self.new_client()

        changed = self.runtime['register_seen_client'](
            client,
            {
                'clientRole': 'CAM',
                'type': 'key_telemetry',
            },
            '/telemetry',
            'key_telemetry',
        )

        self.assertTrue(changed)
        self.assertEqual(client['clientRole'], 'UNP')
        self.assertEqual(client['detectedRole'], 'KEY')

    def test_monitor_camera_and_door_roles_are_merged(self):
        client = self.new_client()

        self.runtime['register_seen_client'](
            client,
            {'type': 'camera_ping'},
            '/telemetry',
            'camera_ping',
        )
        self.runtime['register_seen_client'](
            client,
            {'type': 'door_telemetry'},
            '/telemetry',
            'door_telemetry',
        )

        self.assertEqual(client['clientRole'], 'UNP')
        self.assertEqual(client['detectedRole'], 'CAM,DSS')

    def test_client_role_header_is_used_when_body_has_no_role(self):
        client = self.new_client()
        self.request_headers['X-Client-Role'] = 'controller'

        self.runtime['register_seen_client'](
            client,
            {'type': 'telemetry'},
            '/telemetry',
            'telemetry',
        )

        self.assertEqual(client['detectedRole'], 'KEY')

    def test_detected_role_does_not_reclassify_provisioned_client(self):
        client = self.new_client()
        client['clientRole'] = ['CAM']
        client['detectedRole'] = 'CAM'
        client['provisioned'] = True

        self.runtime['register_seen_client'](
            client,
            {'type': 'key_telemetry'},
            '/telemetry',
            'key_telemetry',
        )

        self.assertEqual(client['clientRole'], ['CAM'])
        self.assertEqual(client['detectedRole'], 'CAM')

    def test_canonical_android_profile_covers_each_client_class(self):
        profile = self.runtime['android_client_profile']
        cases = (
            (
                {'provisioned': False, 'detectedRole': 'KEY'},
                {'clientClass': 'control', 'capabilities': ['KEY']},
            ),
            (
                {'provisioned': False, 'detectedRole': 'CAM'},
                {'clientClass': 'monitor', 'capabilities': ['CAM', 'DSS']},
            ),
            (
                {'provisioned': False, 'detectedRole': 'DSS'},
                {'clientClass': 'monitor', 'capabilities': ['CAM', 'DSS']},
            ),
            (
                {'provisioned': True, 'clientRole': ['CAM', 'DSS']},
                {'clientClass': 'monitor', 'capabilities': ['CAM', 'DSS']},
            ),
            (
                {'provisioned': True, 'clientRole': ['CAM']},
                {'clientClass': 'camera', 'capabilities': ['CAM']},
            ),
            (
                {'provisioned': True, 'clientRole': ['DSS']},
                {'clientClass': 'door', 'capabilities': ['DSS']},
            ),
            (
                {'provisioned': True, 'clientRole': ['KEY']},
                {'clientClass': 'control', 'capabilities': ['KEY']},
            ),
        )

        for client, expected in cases:
            with self.subTest(client=client):
                self.assertEqual(profile(client), expected)

    def test_monitor_role_cannot_be_split_after_provisioning(self):
        client = {
            'deviceID': 'android-monitor',
            'provisioned': True,
            'clientRole': ['CAM', 'DSS'],
            'pending_command': {},
        }

        ok, error = self.runtime['apply_enabled_roles'](client, ['CAM'])

        self.assertTrue(ok)
        self.assertEqual(error, '')
        self.assertEqual(client['clientRole'], ['CAM', 'DSS'])

    def test_profile_reaches_status_and_metadata_edits_do_not_change_roles(self):
        status_source = (
            REPO_ROOT / 'server_core' / 'status.py'
        ).read_text(encoding='utf-8')
        actions_source = (
            REPO_ROOT / 'static' / 'js' / 'dashboard-actions.js'
        ).read_text(encoding='utf-8')
        save_source = self.source_block(
            actions_source,
            'window.saveClientMenuMeta = async function',
            'window.cameraVideoModalRefreshTimer',
        )
        cancel_source = self.source_block(
            actions_source,
            'window.hideClientMetaModal = function',
            'window.removeClientMetaDevice = async function',
        )

        self.assertIn(
            "'androidClientClass': android_profile['clientClass']",
            status_source,
        )
        self.assertIn(
            "'androidCapabilities': list(android_profile['capabilities'])",
            status_source,
        )
        self.assertNotIn('enabledRoles', save_source)
        self.assertNotIn('enabled_roles', save_source)
        self.assertNotIn('postJson(', cancel_source)

    def test_provisioned_role_is_part_of_the_restart_contract(self):
        state_source = (
            REPO_ROOT / 'server_core' / 'state.py'
        ).read_text(encoding='utf-8')
        common_keys = self.source_block(
            state_source,
            'COMMON_CLIENT_STATE_KEYS = (',
            'TAPO_SERVER_STATE_KEYS =',
        )
        load_source = self.source_block(
            state_source,
            '    def load_state():',
            "    return {\n        'save_state': save_state,",
        )

        self.assertIn("'clientRole',", common_keys)
        self.assertIn("'provisioned',", common_keys)
        self.assertIn("'zone_name',", common_keys)
        self.assertIn('c.update(item)', load_source)
        self.assertIn("c['pending_command'] = {}", load_source)

    def test_successful_control_provisioning_collapses_to_key_role(self):
        payload = {
            'deviceID': 'android-control',
            'clientName': 'Pocket Control',
            'clientRole': ['CAM', 'KEY', 'DSS'],
            'zoneName': 'Ignored Zone',
        }

        response, security, saved_states = self.server_provision(
            payload,
            enrollment_pending=True,
        )

        client = self.clients['android-control']
        self.assertEqual(response, {'ok': True})
        self.assertEqual(
            security.checked_device_ids,
            ['android-control'],
        )
        self.assertEqual(client['clientRole'], ['KEY'])
        self.assertEqual(client['zone_name'], '')
        self.assertIs(client['provisioned'], True)
        self.assertNotIn('motion_detection_enabled', client)
        self.assertEqual(len(saved_states), 1)

    def test_new_device_ui_uses_detected_role_for_label_and_defaults(self):
        utils_source = (
            REPO_ROOT / 'static' / 'js' / 'dashboard-utils.js'
        ).read_text(encoding='utf-8')
        actions_source = (
            REPO_ROOT / 'static' / 'js' / 'dashboard-actions.js'
        ).read_text(encoding='utf-8')
        events_source = (
            REPO_ROOT / 'static' / 'js' / 'dashboard-events.js'
        ).read_text(encoding='utf-8')
        modals_source = (
            REPO_ROOT / 'static' / 'css' / 'modals.css'
        ).read_text(encoding='utf-8')
        style_source = (
            REPO_ROOT / 'static' / 'css' / 'style.css'
        ).read_text(encoding='utf-8')
        matter_render_source = (
            REPO_ROOT / 'subsystems' / 'matter' / 'static' / 'js'
            / 'matter-render.js'
        ).read_text(encoding='utf-8')
        menu_source = self.source_block(
            actions_source,
            'window.renderDashboardClientMenu = function',
            'window.hideAudioModal = function',
        )
        provision_source = self.source_block(
            menu_source,
            '    ${!isProvisioned ? `',
            '    ${isProvisioned && hasCam ? `',
        )

        self.assertIn('return "KotiBot Control Client";', utils_source)
        self.assertIn('return "KotiBot Monitor Client";', utils_source)
        self.assertIn('window.dashboardAndroidClientProfile = function', utils_source)
        self.assertIn('client?.detectedRole || client?.detected_role', utils_source)
        self.assertIn(
            'return { clientClass: "monitor", capabilities: new Set(["CAM", "DSS"]) };',
            utils_source,
        )
        self.assertIn(
            'window.dashboardAndroidClientProfile(client)',
            menu_source,
        )
        self.assertIn('"New KotiBot Control Client"', menu_source)
        self.assertIn('"New KotiBot Monitor Client"', menu_source)
        self.assertIn(
            'manufacturer ? `Android - ${manufacturer}` : "Android"',
            menu_source,
        )
        self.assertIn('"Android - Security Camera"', menu_source)
        self.assertIn('"Android - Door Swing Sensor"', menu_source)
        self.assertIn('.modal-close[hidden],', modals_source)
        self.assertIn(
            'return window.dashboardDeviceTypeName(c);',
            matter_render_source,
        )
        self.assertIn(
            'manufacturer ? `Android - ${manufacturer}` : "Android"',
            matter_render_source,
        )
        self.assertIn(
            'window.dashboardDeviceIconName(c)',
            matter_render_source,
        )
        self.assertIn(
            'window.dashboardIconHtml("koti-fa-triangle-exclamation"',
            matter_render_source,
        )
        self.assertIn(
            '.dashboard-home-matter-found-section,',
            style_source,
        )
        self.assertRegex(
            menu_source,
            re.compile(
                r'\$\{\s*isControlProvisionClient\s*\?\s*""\s*:\s*`',
                re.DOTALL,
            ),
        )
        self.assertRegex(
            menu_source,
            re.compile(
                r'id="p_role_\$\{escAttr\(deviceID\)\}"\s*'
                r'value="\$\{provisionRoleValue\}"',
                re.DOTALL,
            ),
        )
        self.assertNotIn('p_btn_cam_', provision_source)
        self.assertNotIn('p_btn_door_', provision_source)
        self.assertNotIn('toggle-provision', provision_source)
        self.assertNotIn('Security Camera', provision_source)
        self.assertNotIn('Door Swing Sensor', provision_source)
        self.assertIn('Video &amp; Motion', menu_source)
        self.assertIn('Contact Events', menu_source)
        self.assertIn(
            'isProvisioned && androidProfile.clientClass === "monitor"',
            menu_source,
        )
        self.assertIn('isProvisioned && hasCam', menu_source)
        self.assertIn('isProvisioned && hasDss', menu_source)
        self.assertIn(
            'class="modal-head-actions client-menu-lens-actions" '
            'role="group" aria-label="Camera lens"',
            menu_source,
        )
        self.assertNotIn('data-dashboard-change="toggle-client-role"', menu_source)
        self.assertNotIn('"toggle-client-role"', events_source)
        self.assertNotIn('window.setClientEnabledRoles', actions_source)
        self.assertNotIn('window.toggleClientServiceRole', actions_source)
        self.assertNotIn('id="p_btn_key_', menu_source)
        self.assertNotIn(
            '<div class="modal-section-title">${isTapoProvisionClient',
            menu_source,
        )
        self.assertNotIn('window.toggleProvisionFunction', actions_source)

    def test_provisioning_uses_shared_transient_modal(self):
        actions_source = (
            REPO_ROOT / 'static' / 'js' / 'dashboard-actions.js'
        ).read_text(encoding='utf-8')
        modals_source = (
            REPO_ROOT / 'static' / 'css' / 'modals.css'
        ).read_text(encoding='utf-8')
        provision_source = self.source_block(
            actions_source,
            'window.provisionClient = async function',
            'window.unlockDashboardSecurity = async function',
        )
        transient_source = self.source_block(
            actions_source,
            'let clientTransientHoldTimer = 0;',
            'window.saveClientMenuMeta = async function',
        )

        self.assertIn(
            'String(err?.message || "").trim() '
            '=== "device_enrollment_not_pending"',
            provision_source,
        )
        self.assertIn('showClientTransientModal({', provision_source)
        self.assertIn('heading: "Device Offline"', provision_source)
        self.assertIn(
            'message: "Device must be online to provision."',
            provision_source,
        )
        self.assertIn(
            'window.showClientSaveSuccessModal('
            '\n    getClientByDeviceId(deviceID),'
            '\n    clientName,'
            '\n    zoneName'
            '\n  );'
            '\n\n  try {\n    const data = await refreshStatusData();',
            provision_source,
        )
        self.assertIn('function showClientTransientModal({', transient_source)
        self.assertIn('dismissClientMenu = false', transient_source)
        self.assertIn('}, 300);', transient_source)
        self.assertIn('}, 3000);', transient_source)
        self.assertIn('transientModal.hidden = true;', transient_source)
        self.assertIn(
            'transientModal.classList.remove("is-fading");',
            transient_source,
        )
        self.assertIn(
            'document.body.classList.remove("modal-open");',
            transient_source,
        )
        self.assertIn(
            'window.showClientSaveSuccessModal = function',
            transient_source,
        )
        self.assertIn('.client-transient-shell {', modals_source)
        self.assertIn(
            '.client-transient-modal.is-fading .client-transient-shell {',
            modals_source,
        )

    def test_offline_provisioning_fails_closed_without_mutating_client_state(self):
        payload = {
            'deviceID': 'android-offline',
            'clientName': 'Offline Monitor',
            'clientRole': ['CAM', 'DSS'],
            'zoneName': 'Entry',
        }

        response, security, saved_states = self.server_provision(
            payload,
            enrollment_pending=False,
        )

        self.assertEqual(response, ({
            'ok': False,
            'error': 'device_enrollment_not_pending',
        }, 409))
        self.assertEqual(
            security.checked_device_ids,
            ['android-offline'],
        )
        self.assertEqual(self.clients, {})
        self.assertEqual(saved_states, [])

    def test_successful_provisioning_persists_the_final_monitor_state(self):
        client = self.new_client('android-monitor')
        client['detectedRole'] = 'CAM'
        payload = {
            'deviceID': 'android-monitor',
            'clientName': ' Rear Monitor ',
            'clientRole': ['CAM'],
            'zoneName': ' Rear Entry ',
        }

        response, security, saved_states = self.server_provision(
            payload,
            enrollment_pending=True,
        )

        client = self.clients['android-monitor']
        self.assertEqual(response, {'ok': True})
        self.assertEqual(
            security.checked_device_ids,
            ['android-monitor'],
        )
        self.assertEqual(client['clientName'], 'Rear Monitor')
        self.assertEqual(client['clientRole'], ['CAM', 'DSS'])
        self.assertEqual(client['zone_name'], 'Rear Entry')
        self.assertIs(client['provisioned'], True)
        self.assertIs(client['motion_detection_enabled'], False)
        self.assertEqual(
            client['pending_command']['motionDetectionEnabled'],
            0,
        )
        self.assertEqual(
            client['pending_command']['motion_detection_enabled'],
            0,
        )
        self.assertEqual(len(saved_states), 1)


if __name__ == '__main__':
    unittest.main()

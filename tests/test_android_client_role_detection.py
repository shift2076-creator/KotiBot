import unittest
from pathlib import Path

from server_core.clients import build_client_runtime


REPO_ROOT = Path(__file__).resolve().parents[1]


class AndroidClientRoleDetectionTests(unittest.TestCase):
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

    def test_new_device_ui_uses_detected_role_for_label_and_defaults(self):
        utils_source = (
            REPO_ROOT / 'static' / 'js' / 'dashboard-utils.js'
        ).read_text(encoding='utf-8')
        actions_source = (
            REPO_ROOT / 'static' / 'js' / 'dashboard-actions.js'
        ).read_text(encoding='utf-8')

        self.assertIn('return "KotiBot-Control Client";', utils_source)
        self.assertIn('return "KotiBot-Monitor Client";', utils_source)
        self.assertIn('function detectedRoleSetOfClient(c)', actions_source)
        self.assertIn('value="${provisionRoleValue}"', actions_source)
        self.assertIn('provisionRoles.has("KEY") ? "active"', actions_source)


if __name__ == '__main__':
    unittest.main()

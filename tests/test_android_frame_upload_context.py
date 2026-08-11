import importlib.util
import sys
import unittest
from pathlib import Path
from threading import RLock

from flask import Flask, g


REPO_ROOT = Path(__file__).resolve().parents[1]
TELEMETRY_MODULE_PATH = (
    REPO_ROOT
    / 'subsystems'
    / 'client-android-home'
    / 'client_android_home_telemetry.py'
)


def load_telemetry_module():
    spec = importlib.util.spec_from_file_location(
        'test_android_frame_upload_context_module',
        TELEMETRY_MODULE_PATH,
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class AndroidFrameUploadContextTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.telemetry_module = load_telemetry_module()

    def test_signed_request_context_identity_reaches_upload_handler(self):
        app = Flask(__name__)
        camera = {
            'deviceID': 'camera-1',
            'clientRole': 'cam',
            'provisioned': True,
            'pending_command': {},
        }

        def client_has_role(client, role):
            return client.get('clientRole') == role

        context = {
            'state_lock': RLock(),
            'client_role_cam': 'cam',
            'client_role_dss': 'dss',
            'client_role_key': 'key',
            'client_role_tapo': 'tapo',
            'client_has_role': client_has_role,
            'normalize_client_roles': lambda value: [value] if value else [],
            'get_unprovisioned_client': lambda device_id: None,
            'get_clients_for_device': lambda device_id: [camera],
            'register_seen_client': lambda client, data, path, kind: False,
            'snapshot_client': lambda client: {'deviceID': client['deviceID']},
            'preview_requested_for_client': lambda client: True,
            'handle_key_telemetry': lambda client, data: False,
            'fire_door_routes': lambda client, state: False,
            'fire_camera_motion_routes': lambda client, output='motion': False,
            'cancel_door_sound_repeat': lambda device_id: None,
            'system_armed': lambda: False,
            'save_state': lambda: None,
            'broadcast_state': lambda: None,
            'safe_int': lambda value: int(value) if value is not None else None,
            'safe_float': lambda value: float(value) if value is not None else None,
            'now_epoch': lambda: 1234.0,
        }

        self.telemetry_module.register_android_home_telemetry(
            app,
            context,
        )

        @app.before_request
        def establish_signed_device_identity():
            g.kotibot_device_id = 'camera-1'

        frame = b'\xff\xd8\xfftest-frame'
        response = app.test_client().post(
            '/upload_frame',
            data=frame,
            content_type='image/jpeg',
            headers={
                'X-Koti-Frame-Captured-Ms': '1234000',
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(camera['frame'], frame)
        self.assertEqual(camera['frame_captured_ms'], 1234000)
        self.assertEqual(camera['frame_seq'], 1)
        self.assertEqual(camera['frame_last_seen'], 1234.0)


if __name__ == '__main__':
    unittest.main()

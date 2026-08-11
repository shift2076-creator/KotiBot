import base64
import hashlib
import hmac
import importlib.util
import sys
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import RLock

from flask import Flask

from subsystems.security.kotibot_security import (
    KotiBotSecurity,
    SecurityConfig,
)
from subsystems.security.security_routes import register_security_routes


REPO_ROOT = Path(__file__).resolve().parents[1]
TELEMETRY_MODULE_PATH = (
    REPO_ROOT
    / 'subsystems'
    / 'client-android-home'
    / 'client_android_home_telemetry.py'
)
FRAME = b'\xff\xd8\xfftest-frame'


def load_telemetry_module():
    spec = importlib.util.spec_from_file_location(
        'test_android_frame_upload_context_module',
        TELEMETRY_MODULE_PATH,
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def encode_signature(value):
    return base64.urlsafe_b64encode(value).decode('ascii').rstrip('=')


class AndroidFrameUploadContextTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.telemetry_module = load_telemetry_module()

    def make_security(self, base_dir):
        return KotiBotSecurity(SecurityConfig(
            base_dir=Path(base_dir),
            allowed_origins=(
                ('https', 'kotibot.example', 443),
            ),
        ))

    def make_app(self, security, clients):
        app = Flask(__name__)

        def client_has_role(client, role):
            client_roles = client.get('clientRole')

            if isinstance(client_roles, list):
                return role in client_roles

            return client_roles == role

        context = {
            'state_lock': RLock(),
            'client_role_cam': 'cam',
            'client_role_dss': 'dss',
            'client_role_key': 'key',
            'client_role_tapo': 'tapo',
            'client_has_role': client_has_role,
            'normalize_client_roles': lambda value: [value] if value else [],
            'get_unprovisioned_client': lambda device_id: None,
            'get_clients_for_device': lambda device_id: [
                client
                for client in clients
                if client.get('deviceID') == device_id
            ],
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

        register_security_routes(app, {
            'security': security,
        })
        self.telemetry_module.register_android_home_telemetry(
            app,
            context,
        )
        return app

    def signed_headers(self, credentials, device_id, nonce):
        timestamp = str(int(time.time()))
        body_sha = hashlib.sha256(FRAME).hexdigest()
        canonical = '\n'.join((
            'POST',
            '/upload_frame',
            timestamp,
            nonce,
            body_sha,
        )).encode('utf-8')
        signature = encode_signature(hmac.new(
            credentials['secret'].encode('utf-8'),
            canonical,
            hashlib.sha256,
        ).digest())

        return {
            'X-Device-ID': device_id,
            'X-Koti-Key-ID': credentials['keyID'],
            'X-Koti-Timestamp': timestamp,
            'X-Koti-Nonce': nonce,
            'X-Koti-Body-SHA256': body_sha,
            'X-Koti-Signature': signature,
            'X-Koti-Frame-Captured-Ms': '1234000',
        }

    def post_frame(self, app, headers):
        return app.test_client().post(
            '/upload_frame',
            data=FRAME,
            content_type='image/jpeg',
            headers=headers,
        )

    def assert_camera_frame(self, camera):
        self.assertEqual(camera['frame'], FRAME)
        self.assertEqual(camera['frame_captured_ms'], 1234000)
        self.assertEqual(camera['frame_seq'], 1)
        self.assertEqual(camera['frame_last_seen'], 1234.0)

    def test_signed_camera_upload_reaches_handler_before_and_after_restart(self):
        with TemporaryDirectory() as temp_dir:
            security = self.make_security(temp_dir)
            credentials = security.issue_device_key('camera-1')
            camera = {
                'deviceID': 'camera-1',
                'clientRole': 'cam',
                'provisioned': True,
                'pending_command': {},
            }
            app = self.make_app(security, [camera])

            response = self.post_frame(
                app,
                self.signed_headers(
                    credentials,
                    'camera-1',
                    'frame-before-restart',
                ),
            )

            self.assertEqual(response.status_code, 200)
            self.assert_camera_frame(camera)

            restarted_security = self.make_security(temp_dir)
            restarted_camera = {
                'deviceID': 'camera-1',
                'clientRole': 'cam',
                'provisioned': True,
                'pending_command': {},
            }
            restarted_app = self.make_app(
                restarted_security,
                [restarted_camera],
            )

            restarted_response = self.post_frame(
                restarted_app,
                self.signed_headers(
                    credentials,
                    'camera-1',
                    'frame-after-restart',
                ),
            )

            self.assertEqual(restarted_response.status_code, 200)
            self.assert_camera_frame(restarted_camera)

    def test_unsigned_upload_is_rejected_before_and_after_restart(self):
        with TemporaryDirectory() as temp_dir:
            security = self.make_security(temp_dir)
            security.issue_device_key('camera-1')
            camera = {
                'deviceID': 'camera-1',
                'clientRole': 'cam',
                'provisioned': True,
                'pending_command': {},
            }

            for app in (
                self.make_app(security, [camera]),
                self.make_app(self.make_security(temp_dir), [camera]),
            ):
                with self.subTest(app=app.name):
                    response = self.post_frame(app, {
                        'X-Device-ID': 'camera-1',
                    })

                    self.assertEqual(response.status_code, 401)
                    self.assertEqual(
                        response.get_json()['error'],
                        'missing_signature_headers',
                    )

            self.assertNotIn('frame', camera)

    def test_signed_non_camera_upload_is_rejected_before_and_after_restart(self):
        with TemporaryDirectory() as temp_dir:
            security = self.make_security(temp_dir)
            credentials = security.issue_device_key('control-1')
            control = {
                'deviceID': 'control-1',
                'clientRole': 'dss',
                'provisioned': True,
                'pending_command': {},
            }
            apps = (
                self.make_app(security, [control]),
                self.make_app(self.make_security(temp_dir), [control]),
            )

            for index, app in enumerate(apps):
                with self.subTest(restarted=bool(index)):
                    response = self.post_frame(
                        app,
                        self.signed_headers(
                            credentials,
                            'control-1',
                            f'non-camera-{index}',
                        ),
                    )

                    self.assertEqual(response.status_code, 403)
                    self.assertEqual(
                        response.get_json()['error'],
                        'camera_role_required',
                    )

            self.assertNotIn('frame', control)


if __name__ == '__main__':
    unittest.main()

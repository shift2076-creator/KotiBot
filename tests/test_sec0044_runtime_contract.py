import ast
import json
import os
from pathlib import Path
from threading import RLock
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

try:
    from flask import Flask
    from subsystems.voice import voice_routes
except ModuleNotFoundError as exc:
    if exc.name != "flask":
        raise

    Flask = None
    voice_routes = None

from server_core.integration_credentials import IntegrationCredentials
from subsystems.network import external_ip


SOURCE_ROOT = Path(__file__).resolve().parents[1]
SECRET_ENVIRONMENT_NAMES = {
    "KOTIBOT_CLOUDFLARE_API_TOKEN",
    "KOTIBOT_CAMERA_TALK_TURN_USERNAME",
    "KOTIBOT_CAMERA_TALK_TURN_CREDENTIAL",
    "KOTIBOT_CAMERA_TALK_ICE_SERVERS",
}


class _Response:
    def __init__(self, payload: bytes):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def read(self):
        return self.payload


def _direct_environment_reads(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not node.args:
            continue

        function = node.func

        if (
            not isinstance(function, ast.Attribute)
            or function.attr != "get"
            or not isinstance(function.value, ast.Attribute)
            or function.value.attr != "environ"
            or not isinstance(function.value.value, ast.Name)
            or function.value.value.id != "os"
            or not isinstance(node.args[0], ast.Constant)
            or not isinstance(node.args[0].value, str)
        ):
            continue

        names.add(node.args[0].value)

    return names


class Sec0044RuntimeContractTests(unittest.TestCase):
    def setUp(self):
        if voice_routes is not None:
            voice_routes.VOICE_TALK_SESSIONS.clear()

    def tearDown(self):
        if voice_routes is not None:
            voice_routes.VOICE_TALK_SESSIONS.clear()

    def test_runtime_consumers_do_not_read_legacy_secret_environment(self):
        consumer_paths = (
            SOURCE_ROOT / "subsystems" / "network" / "external_ip.py",
            SOURCE_ROOT / "subsystems" / "voice" / "voice_routes.py",
        )

        for path in consumer_paths:
            with self.subTest(path=path.relative_to(SOURCE_ROOT)):
                self.assertEqual(
                    _direct_environment_reads(path)
                    & SECRET_ENVIRONMENT_NAMES,
                    set(),
                )

    def test_server_loads_once_and_passes_one_credential_owner(self):
        server_source = (SOURCE_ROOT / "kotibot_server.py").read_text(
            encoding="utf-8"
        )
        subsystem_source = (
            SOURCE_ROOT / "server_core" / "subsystems.py"
        ).read_text(encoding="utf-8")

        self.assertEqual(
            server_source.count(
                "INTEGRATION_CREDENTIALS = load_integration_credentials()"
            ),
            1,
        )
        self.assertIn(
            "'integration_credentials': INTEGRATION_CREDENTIALS,",
            server_source,
        )
        self.assertEqual(
            subsystem_source.count(
                "'integration_credentials': ctx['integration_credentials']"
            ),
            1,
        )
        self.assertIn(
            "'integration_credentials': ctx[\n"
            "                    'integration_credentials'\n"
            "                ],",
            subsystem_source,
        )

    def test_systemd_loads_closed_integration_document(self):
        drop_in = (
            SOURCE_ROOT
            / "deploy"
            / "systemd"
            / "kotibot.service.d"
            / "credentials.conf"
        ).read_text(encoding="utf-8")

        self.assertEqual(
            drop_in.count(
                "LoadCredential=integration-credentials.json:"
                "/etc/kotibot/credentials.d/"
                "integration-credentials.json"
            ),
            1,
        )

    def test_cloudflare_request_uses_protected_token(self):
        app = SimpleNamespace(config={}, logger=Mock())
        credentials = IntegrationCredentials.from_document({
            "version": 1,
            "cloudflare_api_token": "protected-cloudflare-token",
        })
        requests = []

        external_ip.register_external_ip_checker(
            app,
            {"integration_credentials": credentials},
        )

        def open_url(request, timeout):
            requests.append(request)

            if len(requests) == 1:
                return _Response(b"198.51.100.42\n")

            app.config["KOTIBOT_EXTERNAL_IP_STOP"].set()
            return _Response(json.dumps({
                "result": {
                    "id": "record-id",
                    "type": "A",
                    "name": "home.example.invalid",
                    "content": "198.51.100.42",
                    "ttl": 1,
                    "proxied": True,
                },
            }).encode("utf-8"))

        environment = {
            "KOTIBOT_EXTERNAL_IP_ENABLED": "1",
            "KOTIBOT_CLOUDFLARE_ZONE_ID": "zone-id",
            "KOTIBOT_CLOUDFLARE_RECORD_ID": "record-id",
            "KOTIBOT_PUBLIC_HOSTNAME": "home.example.invalid",
        }

        with patch.dict(os.environ, environment, clear=True):
            with patch.object(
                external_ip.urlrequest,
                "urlopen",
                side_effect=open_url,
            ):
                app.config["KOTIBOT_EXTERNAL_IP_CHECK_LOOP"]()

        self.assertEqual(len(requests), 2)
        self.assertEqual(
            requests[1].get_header("Authorization"),
            "Bearer protected-cloudflare-token",
        )
        self.assertNotIn(
            "KOTIBOT_CLOUDFLARE_API_TOKEN",
            environment,
        )

    @unittest.skipIf(Flask is None, "Flask is not installed")
    def test_camera_talk_returns_protected_composite_ice_servers(self):
        credentials = IntegrationCredentials.from_document({
            "version": 1,
            "camera_talk_ice_servers": [{
                "urls": ["turn:relay.example.invalid:3478"],
                "username": "protected-user",
                "credential": "protected-password",
            }],
        })
        app = self._voice_app(credentials)

        with patch.dict(os.environ, {}, clear=True):
            response = app.test_client().post(
                "/api/voice/session",
                json={"targetDeviceID": "camera-1"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.get_json()["iceServers"],
            [{
                "urls": ["turn:relay.example.invalid:3478"],
                "username": "protected-user",
                "credential": "protected-password",
            }],
        )

    @unittest.skipIf(Flask is None, "Flask is not installed")
    def test_camera_talk_combines_nonsecret_urls_with_protected_pair(self):
        credentials = IntegrationCredentials.from_document({
            "version": 1,
            "camera_talk_turn_username": "protected-user",
            "camera_talk_turn_credential": "protected-password",
        })
        app = self._voice_app(credentials)
        environment = {
            "KOTIBOT_CAMERA_TALK_DISABLE_DEFAULT_STUN": "1",
            "KOTIBOT_CAMERA_TALK_TURN_URLS": (
                "turn:relay.example.invalid:3478"
            ),
        }

        with patch.dict(os.environ, environment, clear=True):
            response = app.test_client().post(
                "/api/voice/session",
                json={"targetDeviceID": "camera-1"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.get_json()["iceServers"],
            [{
                "urls": "turn:relay.example.invalid:3478",
                "username": "protected-user",
                "credential": "protected-password",
            }],
        )

    @staticmethod
    def _voice_app(credentials):
        app = Flask(__name__)
        clients = {
            "camera-1": {
                "provisioned": True,
                "roles": {"camera"},
            },
        }
        context = {
            "state_lock": RLock(),
            "clients": clients,
            "client_role_cam": "camera",
            "client_role_key": "key",
            "client_role_tapo": "tapo",
            "client_has_role": (
                lambda client, role: role in client.get("roles", set())
            ),
            "is_client_stale": lambda client: False,
            "now_epoch": lambda: 1000.0,
            "push_queue": None,
            "integration_credentials": credentials,
        }
        voice_routes.register_voice_routes(app, context)
        return app


if __name__ == "__main__":
    unittest.main()

"""Real Scene HTTP route under the deployed stream/worker budget; fake devices."""
import http.client
import json
import threading
import unittest
from unittest.mock import Mock, patch

from waitress import create_server
from server_core.routes import register_server_routes


class SceneHttpCapacityTests(unittest.TestCase):
    def test_fifteen_scenes_reach_devices_with_eight_status_streams_open(self):
        # Reuse the device fixture, but exercise its route through actual HTTP.
        from tests.devices.tapo.test_tapo_dashboard_commands import TapoDashboardCommandTests
        fixture = TapoDashboardCommandTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.add_device('other')
        security = Mock()
        security.dashboard_token_authorized.return_value = True
        listeners = []
        with patch.dict('os.environ', {'KOTIBOT_STATUS_STREAM_LIMIT': '8'}):
            register_server_routes(fixture.app, dict(
                fixture.context, sse_listeners=listeners,
                security=security, current_status_payload=lambda: {'ok': True},
            ))
        socket_map = {}
        server = create_server(fixture.app, host='127.0.0.1', port=0, threads=12, map=socket_map)
        runner = threading.Thread(target=server.run, daemon=True)
        runner.start()
        port = int(server.effective_port)
        connections, responses = [], []
        try:
            for _ in range(8):
                connection = http.client.HTTPConnection('127.0.0.1', port, timeout=3)
                connections.append(connection)
                connection.request('GET', '/api/status/stream')
                response = connection.getresponse()
                responses.append(response)
                self.assertEqual(response.status, 200)
                self.assertTrue(response.readline().startswith(b'data:'))
            self.assertEqual(len(listeners), 8)
            for n in range(15):
                action = 'on' if n % 2 == 0 else 'off'
                connection = http.client.HTTPConnection('127.0.0.1', port, timeout=3)
                try:
                    connection.request('POST', '/api/tapo/client-command-batch',
                        body=json.dumps({'activeHomeMode': 'day' if n % 2 == 0 else 'night',
                                         'commands': [dict(deviceID='tapo:'+name, action=action)
                                                      for name in ('plug', 'other')]}),
                        headers={'Content-Type': 'application/json'})
                    response = connection.getresponse()
                    data = json.loads(response.read())
                    self.assertEqual(response.status, 200)
                    self.assertTrue(data['ok'], data)
                    self.assertEqual(data['okCount'], 2)
                finally:
                    connection.close()
            for name in ('plug', 'other'):
                self.assertEqual([call[1] for call in fixture.calls if call[0] == name],
                                 ['on' if n % 2 == 0 else 'off' for n in range(15)])
            self.assertEqual(fixture.queue._entries, {})
        finally:
            security.dashboard_token_authorized.return_value = False
            for listener in list(listeners):
                listener.put_nowait('{}')
            for response in responses:
                response.close()
            for connection in connections:
                connection.close()
            server.task_dispatcher.shutdown(timeout=3)
            for channel in list(socket_map.values()):
                channel.close()
            runner.join(timeout=3)
        self.assertFalse(runner.is_alive())
        self.assertEqual(listeners, [])

import http.client
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock, patch

from flask import Flask
from waitress import create_server

from server_core.routes import register_server_routes
from server_core.streaming import StatusStreamSlots


class StatusStreamCapacityTests(unittest.TestCase):
    def build_app(self, limit=2):
        app = Flask(__name__)
        app.testing = True
        security = Mock()
        security.dashboard_token_authorized.return_value = True
        listeners = []
        payload = Mock(return_value={'ok': True})
        with patch.dict('os.environ', {'KOTIBOT_STATUS_STREAM_LIMIT': str(limit)}):
            register_server_routes(app, {
                'state_lock': threading.RLock(),
                'sse_listeners': listeners,
                'security': security,
                'current_status_payload': payload,
                'clean_zone_name': str,
            })
        return app, security, listeners, payload

    def test_limit_rejects_without_building_status_and_close_releases(self):
        app, _, listeners, payload = self.build_app()
        client = app.test_client()
        streams = [client.get('/api/status/stream', buffered=False) for _ in range(2)]
        try:
            self.assertEqual(len(listeners), 2)
            rejected = client.get('/api/status/stream')
            self.assertEqual(rejected.status_code, 503)
            self.assertEqual(rejected.headers['Retry-After'], '15')
            self.assertEqual(payload.call_count, 2)
            self.assertEqual(client.get('/api/status').status_code, 200)
            streams[0].close()
            replacement = client.get('/api/status/stream', buffered=False)
            self.assertEqual(replacement.status_code, 200)
            replacement.close()
        finally:
            for stream in streams:
                stream.close()
        self.assertEqual(listeners, [])

    def test_unconsumed_response_close_releases_once(self):
        app, _, listeners, _ = self.build_app(1)
        with app.test_request_context('/api/status/stream'):
            response = app.full_dispatch_request()
        self.assertEqual(listeners, [])
        response.close()
        response.close()
        with app.test_client().get('/api/status/stream', buffered=False) as stream:
            self.assertEqual(stream.status_code, 200)

    def test_initial_snapshot_exception_releases(self):
        app, _, listeners, payload = self.build_app(1)
        payload.side_effect = RuntimeError('snapshot failed')
        with self.assertRaisesRegex(RuntimeError, 'snapshot failed'):
            app.test_client().get('/api/status/stream', buffered=False)
        self.assertEqual(listeners, [])
        payload.side_effect = None
        with app.test_client().get('/api/status/stream', buffered=False) as response:
            self.assertEqual(response.status_code, 200)

    def test_revocation_stops_publication_and_releases(self):
        app, security, listeners, _ = self.build_app(1)
        response = app.test_client().get('/api/status/stream', buffered=False)
        iterator = iter(response.response)
        next(iterator)  # Initial payload buffered by the test client.
        security.dashboard_token_authorized.return_value = False
        with self.assertRaises(StopIteration):
            next(iterator)
        self.assertEqual(listeners, [])
        response.close()
        security.dashboard_token_authorized.return_value = True
        with app.test_client().get('/api/status/stream', buffered=False) as replacement:
            self.assertEqual(replacement.status_code, 200)

    def test_authorization_checked_before_admission(self):
        app, security, listeners, payload = self.build_app(1)
        security.dashboard_token_authorized.return_value = False
        self.assertEqual(app.test_client().get('/api/status/stream').status_code, 401)
        payload.assert_not_called()
        self.assertEqual(listeners, [])
        security.dashboard_token_authorized.return_value = True
        with app.test_client().get('/api/status/stream', buffered=False) as response:
            self.assertEqual(response.status_code, 200)

    def test_slots_are_per_application(self):
        first, *_ = self.build_app(1)
        second, *_ = self.build_app(1)
        with first.test_client().get('/api/status/stream', buffered=False) as a:
            with second.test_client().get('/api/status/stream', buffered=False) as b:
                self.assertEqual((a.status_code, b.status_code), (200, 200))

    def test_concurrent_admission_and_idempotent_release(self):
        slots = StatusStreamSlots(8)
        barrier = threading.Barrier(24)
        def acquire():
            barrier.wait(timeout=3)
            return slots.acquire()
        with ThreadPoolExecutor(max_workers=24) as pool:
            leases = list(pool.map(lambda _: acquire(), range(24)))
        leases = [lease for lease in leases if lease is not None]
        self.assertEqual(len(leases), 8)
        for release in leases:
            release()
            release()
        replacements = [slots.acquire() for _ in range(9)]
        self.assertEqual(sum(item is not None for item in replacements), 8)
        for release in replacements:
            if release:
                release()

    def test_invalid_limits_fail_explicitly(self):
        for value in (0, -1, 'bad', '', '1.5', 1.5, True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                StatusStreamSlots(value)

    def test_default_leaves_capacity_in_four_worker_deployment(self):
        with patch.dict('os.environ', {}, clear=True):
            slots = StatusStreamSlots()
        leases = [slots.acquire() for _ in range(3)]
        self.assertEqual(sum(item is not None for item in leases), 2)
        for release in leases:
            if release:
                release()

    def test_real_waitress_reserves_workers_during_reconnect_burst(self):
        app, security, listeners, _ = self.build_app(8)
        socket_map = {}
        server = create_server(app, host='127.0.0.1', port=0, threads=12, map=socket_map)
        runner = threading.Thread(target=server.run, daemon=True)
        runner.start()
        connections = []
        responses = []
        port = int(server.effective_port)

        def request(path):
            connection = http.client.HTTPConnection('127.0.0.1', port, timeout=3)
            try:
                connection.request('GET', path)
                response = connection.getresponse()
                body = response.read()
                return response.status, body
            finally:
                connection.close()

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
            with ThreadPoolExecutor(max_workers=12) as pool:
                paths = ['/api/status/stream', '/api/status'] * 12
                results = list(pool.map(request, paths))
            self.assertEqual([status for status, _ in results], [503, 200] * 12)
            self.assertEqual(len(listeners), 8)
        finally:
            # Wake every generator without waiting for the heartbeat timeout.
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

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import unittest

from flask import Flask

from subsystems.notifications.kotibot_push import KotiBotPushQueue
from subsystems.voice.voice_routes import register_voice_routes
from tools.sec005_sanitize_notification_history import sanitize_payload
from tools.sec005_verify_output_sanitization import (
    _scan_notification_record,
)


class _FakeIntegrationCredentials:
    camera_talk_turn_username = ""
    camera_talk_turn_credential = ""

    def camera_talk_ice_servers(self):
        return []


class _FakePushQueue:
    def __init__(self):
        self.calls = []

    def enqueue_data(self, **kwargs):
        self.calls.append(dict(kwargs))
        return {
            "event_type": kwargs.get("event_type", ""),
            "status": "queued_data_fcm_pending",
        }


class Sec005NotificationHistoryPrivacyTests(unittest.TestCase):
    def test_queue_can_dispatch_data_without_persisting_history(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            queue_file = root / "notification_queue.jsonl"
            queue = KotiBotPushQueue(
                root,
                queue_file=queue_file,
                service_account_file=root / "missing.json",
            )

            queue.enqueue_data(
                event_type="camera_talk_candidate",
                deviceID="device-1",
                data={
                    "candidate": (
                        "candidate:1 1 UDP 1 192.0.2.10 50000 typ host"
                    ),
                },
                persist_history=False,
            )

            self.assertFalse(queue_file.exists())

    def test_queue_still_persists_normal_notification_history(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            queue_file = root / "notification_queue.jsonl"
            queue = KotiBotPushQueue(
                root,
                queue_file=queue_file,
                service_account_file=root / "missing.json",
            )

            queue.enqueue_data(
                event_type="fcm_test",
                deviceID="device-1",
                data={"message": "synthetic"},
            )

            records = [
                json.loads(line)
                for line in queue_file.read_text(
                    encoding="utf-8"
                ).splitlines()
                if line
            ]
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["event_type"], "fcm_test")

    def test_camera_talk_candidate_uses_ephemeral_notification_delivery(self):
        app = Flask(__name__)
        clients = {
            "camera-1": {
                "deviceID": "camera-1",
                "provisioned": True,
                "clientRole": ["CAM"],
                "fcm_token": "synthetic-fcm-token",
            },
        }
        push_queue = _FakePushQueue()

        register_voice_routes(app, {
            "state_lock": threading.Lock(),
            "clients": clients,
            "client_role_cam": "CAM",
            "client_role_key": "KEY",
            "client_role_tapo": "TAPO",
            "client_has_role": (
                lambda client, role:
                role in (
                    client.get("clientRole")
                    if isinstance(client.get("clientRole"), list)
                    else [client.get("clientRole")]
                )
            ),
            "is_client_stale": lambda client: False,
            "now_epoch": lambda: 1000.0,
            "push_queue": push_queue,
            "integration_credentials": _FakeIntegrationCredentials(),
        })

        client = app.test_client()

        created = client.post(
            "/api/voice/session",
            json={"targetDeviceID": "camera-1"},
        ).get_json()
        session_id = created["sessionID"]

        offer_response = client.post(
            f"/api/voice/session/{session_id}/offer",
            json={
                "offer": {
                    "type": "offer",
                    "sdp": "v=0\r\nm=audio 9 RTP/AVP 0\r\n",
                },
            },
        )
        self.assertEqual(offer_response.status_code, 200)

        candidate_response = client.post(
            f"/api/voice/session/{session_id}/candidate",
            json={
                "candidate": {
                    "candidate": (
                        "candidate:1 1 UDP 1 192.0.2.10 "
                        "50000 typ host"
                    ),
                },
            },
        )
        self.assertEqual(candidate_response.status_code, 200)

        candidate_calls = [
            call
            for call in push_queue.calls
            if call.get("event_type") == "camera_talk_candidate"
        ]
        self.assertEqual(len(candidate_calls), 1)
        self.assertIs(
            candidate_calls[0].get("persist_history"),
            False,
        )

        response = candidate_response.get_json()
        self.assertTrue(response["fcm"]["queued"])
        self.assertFalse(response["fcm"]["historyPersisted"])
        self.assertNotIn(
            "192.0.2.10",
            json.dumps(response, sort_keys=True),
        )

    def test_verifier_rejects_persisted_signaling(self):
        with self.assertRaises(RuntimeError):
            _scan_notification_record({
                "event_type": "camera_talk_candidate",
                "data": {
                    "candidate": (
                        "candidate:1 1 UDP 1 192.0.2.10 "
                        "50000 typ host"
                    ),
                },
            })

    def test_sanitizer_removes_signaling_and_malformed_records(self):
        normal = json.dumps({
            "event_type": "fcm_test",
            "data": {"message": "synthetic"},
        }).encode("utf-8")
        signaling = json.dumps({
            "event_type": "camera_talk_candidate",
            "data": {
                "candidate": (
                    "candidate:1 1 UDP 1 192.0.2.10 "
                    "50000 typ host"
                ),
            },
        }).encode("utf-8")
        malformed = b"not-json}"

        sanitized, summary = sanitize_payload(
            b"\n".join([
                normal,
                signaling,
                malformed,
                b"",
            ])
        )

        self.assertEqual(summary["total"], 3)
        self.assertEqual(summary["retained"], 1)
        self.assertEqual(summary["private_signaling"], 1)
        self.assertEqual(summary["malformed"], 1)
        self.assertNotIn(b"192.0.2.10", sanitized)

        records = [
            json.loads(line)
            for line in sanitized.splitlines()
            if line
        ]
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["event_type"], "fcm_test")


if __name__ == "__main__":
    unittest.main()

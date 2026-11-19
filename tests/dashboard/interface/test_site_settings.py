import json
import tempfile
import unittest
from pathlib import Path

from flask import Flask

from subsystems.network.site_settings import ROUTE, register_site_settings_routes, validate
from subsystems.security.security_routes import request_policy


def client_for(path):
    app = Flask(__name__)
    register_site_settings_routes(app, {"path": path})
    return app.test_client()


class SiteSettingsTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = str(Path(self.folder.name, "site-settings.json"))

    def post(self, client, **body):
        return client.post(ROUTE, json=body)

    def test_validation_matches_the_portal_rules(self):
        self.assertIsNone(validate("off", "internet"))
        self.assertIsNone(validate("local", "internet"))
        self.assertIn("Choose", validate("x", "internet"))
        self.assertIn("Only one port", validate("internet", "internet"))
        self.assertIn("at least one port", validate("off", "off"))

    def test_defaults_then_save_then_read_back(self):
        client = client_for(self.path)
        self.assertEqual(client.get(ROUTE).get_json(),
                         {"ok": True, "available": True, "ethernet": "off", "wifi": "internet", "jobs": "running"})
        reply = self.post(client, ethernet="local", wifi="internet", jobs="paused")
        self.assertEqual(reply.status_code, 200)
        self.assertEqual(json.loads(Path(self.path).read_text()),
                         {"ethernet_role": "local", "offline_mode": True, "wifi_role": "internet"})
        self.assertEqual(client.get(ROUTE).get_json()["jobs"], "paused")
        self.assertEqual(Path(self.path).stat().st_mode & 0o777, 0o644)
        self.assertEqual([p.name for p in Path(self.folder.name).iterdir()], ["site-settings.json"])

    def test_a_bad_pair_or_switch_is_refused_and_nothing_is_written(self):
        client = client_for(self.path)
        for body in ({"ethernet": "internet", "wifi": "internet", "jobs": "running"},
                     {"ethernet": "off", "wifi": "off", "jobs": "running"},
                     {"ethernet": "off", "wifi": "internet", "jobs": "maybe"}):
            self.assertEqual(self.post(client, **body).status_code, 400, body)
        self.assertFalse(Path(self.path).exists())

    def test_unknown_fields_in_the_file_are_kept(self):
        Path(self.path).write_text(json.dumps({"other": 1}))
        client = client_for(self.path)
        self.post(client, ethernet="off", wifi="internet", jobs="running")
        self.assertEqual(json.loads(Path(self.path).read_text())["other"], 1)

    def test_off_when_no_file_is_configured(self):
        client = client_for("")
        self.assertEqual(client.get(ROUTE).get_json(), {"ok": True, "available": False})
        self.assertEqual(self.post(client, ethernet="off", wifi="internet", jobs="running").status_code, 503)

    def test_needs_the_dashboard_login(self):
        self.assertEqual(request_policy("GET", ROUTE), "dashboard")
        self.assertEqual(request_policy("POST", ROUTE), "dashboard")


if __name__ == "__main__":
    unittest.main()

import hashlib
import json
import os
import tempfile
import unittest
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from flask import Flask

from subsystems.pivault_admin import client_packages as cp
from subsystems.pivault_admin import devices, notifications, store
from subsystems.pivault_admin.routes import register_pivault_admin_routes
from subsystems.security.security_routes import request_policy

CINEMA = {"movie_key": "nosferatu", "source_url": "https://archive.org/details/x", "source_md5": "a" * 32,
          "actual_bytes": 5, "estimated_bytes": 4, "maximum_bytes": 9, "minimum_bytes": 1, "height": 720,
          "tolerance_percent": 20, "reference_minutes": 90}


class Base(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        base = Path(self.folder.name)
        patcher = mock.patch.dict(os.environ, {
            "KOTIBOT_PIVAULT_ADMIN_DIR": str(base / "admin"),
            "KOTIBOT_PIVAULT_NOTIFICATIONS": str(base / "notes"),
            "KOTIBOT_PIVAULT_CLIENTS": str(base / "clients"),
        })
        patcher.start()
        self.addCleanup(patcher.stop)
        self.notes = base / "notes"
        (self.notes / "inbox").mkdir(parents=True)

    def drop(self, event, name=None):
        (self.notes / "inbox" / ((name or event["id"]) + ".json")).write_text(json.dumps(event))


def cinema_event():
    details = dict(CINEMA)
    event_id = hashlib.sha256(json.dumps(details, sort_keys=True).encode()).hexdigest()
    return {"version": 1, "id": event_id, "source": "cinema", "kind": "cinema.filesize", "level": "warning",
            "title": "Filesize", "message": "check", "details": details,
            "created_at": datetime.now(timezone.utc).isoformat()}


class NotificationTests(Base):
    def test_valid_outbox_file_is_imported_and_removed(self):
        event = cinema_event()
        self.drop(event)
        feed = notifications.feed("a@b.c")
        self.assertEqual(feed["open_count"], 1)
        self.assertEqual(feed["unread_count"], 1)
        self.assertEqual(list((self.notes / "inbox").iterdir()), [])

    def test_tampered_or_misnamed_files_are_kept_and_ignored(self):
        event = cinema_event()
        event["details"]["actual_bytes"] = 6
        self.drop(event)
        self.drop(cinema_event(), name="wrong")
        self.assertEqual(notifications.feed("a")["open_count"], 0)
        self.assertEqual(len(list((self.notes / "inbox").iterdir())), 2)

    def test_cinema_approval_writes_decision_and_closes(self):
        event = cinema_event()
        self.drop(event)
        notifications.feed("a")
        self.assertEqual(notifications.resolve("a@b.c", event["id"], "approve"), "resolved")
        decision = json.loads((self.notes / "decisions" / (event["id"] + ".json")).read_text())
        self.assertEqual((decision["action"], decision["id"]), ("approve", event["id"]))
        with self.assertRaises(PermissionError):
            notifications.resolve("a", event["id"], "skip")

    def test_plain_notice_resolves_only_with_resolve(self):
        key = notifications.notify("maintenance", "k", "Title", "Body")
        with self.assertRaises(notifications.NotificationError):
            notifications.resolve("a", key, "approve")
        self.assertEqual(notifications.resolve("a", key, "resolve"), "resolved")

    def test_notify_deduplicates_and_cinema_cannot_be_forged(self):
        first = notifications.notify("clients", "same", "T", "M")
        self.assertEqual(first, notifications.notify("clients", "same", "T", "M"))
        self.assertEqual(notifications.feed("a")["open_count"], 1)
        with self.assertRaises(notifications.NotificationError):
            notifications.notify("cinema", "k", "T", "M", kind="cinema.filesize")

    def test_seen_clears_unread_and_clear_failures_leaves_cinema(self):
        notifications.notify("clients", "w", "T", "M", level="warning")
        self.drop(cinema_event())
        feed = notifications.feed("a")
        notifications.mark_seen("a", [item["id"] for item in feed["items"]])
        self.assertEqual(notifications.feed("a")["unread_count"], 0)
        self.assertEqual(notifications.clear_failures(), 1)
        self.assertEqual(notifications.feed("a")["open_count"], 1)


def apk_bytes():
    path = Path(tempfile.mkdtemp()) / "x.apk"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("AndroidManifest.xml", "x")
    return path.read_bytes()


def release_for(client, data, version="1.0.0"):
    return {"version": version, "sha256": hashlib.sha256(data).hexdigest(), "size": len(data),
            "url": "https://f-droid.org/repo/org.adaway_1.apk", "release_url": "https://f-droid.org/packages/org.adaway/"}


class ClientPackageTests(Base):
    def test_release_validation_rules(self):
        good = release_for("adaway", b"x")
        self.assertEqual(cp.validate_release("adaway", good), good)
        for change in ({"version": "1.0.0rc1"}, {"sha256": "zz"}, {"size": 0},
                       {"url": "https://evil.example/repo/org.adaway_1.apk"},
                       {"url": "http://f-droid.org/repo/org.adaway_1.apk"}):
            with self.assertRaises(cp.ValidationError):
                cp.validate_release("adaway", {**good, **change})

    def test_package_checks_reject_wrong_hash_and_non_apk(self):
        data = apk_bytes()
        release = {**release_for("adaway", data), "client": "adaway"}
        target = Path(self.folder.name) / "p.apk"
        target.write_bytes(data)
        cp.verify_package(target, release)
        with self.assertRaises(cp.ValidationError):
            cp.verify_package(target, {**release, "sha256": "0" * 64})
        junk = Path(self.folder.name) / "j.apk"
        junk.write_bytes(b"not a zip")
        with self.assertRaises(cp.ValidationError):
            cp.verify_package(junk, {**release, "sha256": hashlib.sha256(b"not a zip").hexdigest(), "size": 9})

    def run_night(self, data, version="1.0.0"):
        release = release_for("adaway", data, version)

        def fake_discover(client):
            if client == "adaway":
                return release
            raise cp.ValidationError("offline")

        def fake_fetch(row, progress=None):
            target = cp.release_path(row)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            return target

        with mock.patch.object(cp, "discover", fake_discover), mock.patch.object(cp, "fetch", fake_fetch):
            return cp.maintain()

    def test_night_publishes_newest_and_reports_failed_checks_once(self):
        data = apk_bytes()
        errors = self.run_night(data)
        self.assertIn("firefox", errors)
        self.assertNotIn("adaway", errors)
        row = {r["key"]: r for r in cp.client_rows()}["adaway"]
        self.assertEqual((row["current"], row["available"], row["status"]), ("1.0.0", True, "Up to date"))
        self.run_night(data)
        warnings = [i for i in notifications.feed("a")["items"] if i["source"] == "clients"]
        self.assertEqual(len(warnings), len(errors))

    def test_older_release_never_replaces_a_newer_current(self):
        self.run_night(apk_bytes(), "2.0.0")
        self.run_night(apk_bytes() + b"", "1.0.0")
        self.assertEqual({r["key"]: r for r in cp.client_rows()}["adaway"]["current"], "2.0.0")

    def test_offline_mode_pauses_everything(self):
        settings = Path(self.folder.name) / "site.json"
        settings.write_text(json.dumps({"offline_mode": True}))
        with mock.patch.dict(os.environ, {"KOTIBOT_SITE_SETTINGS": str(settings)}):
            with mock.patch.object(cp, "discover", side_effect=AssertionError("must not run")):
                self.assertEqual(cp.maintain(), [])


class DeviceTests(Base):
    def setUp(self):
        super().setUp()
        self.data = apk_bytes()
        release = release_for("adaway", self.data)
        cp.record_release("adaway", release)
        self.row = {**release, "client": "adaway"}
        target = cp.release_path(self.row)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(self.data)
        with store.connect() as db:
            self.release_id = db.execute("SELECT id FROM client_releases").fetchone()[0]
        devices.set_version("adaway", self.release_id)

    def test_identify_is_stable_and_report_validates(self):
        first = devices.identify({"android_id": "a" * 16, "model": "Pixel"})
        again = devices.identify({"android_id": "a" * 16, "model": "Pixel 9"})
        self.assertEqual(first["id"], again["id"])
        self.assertEqual(set(first["apps"]), set(devices.DEVICE_PACKAGES))
        with self.assertRaises(devices.DeviceError):
            devices.identify({"android_id": "../x"})
        devices.report(first["id"], {"apps": {"adaway": {"state": "enabled", "version": "1.0.0"}}})
        app = [a for a in devices.overview()["devices"][0]["apps"] if a["client"] == "adaway"][0]
        self.assertEqual((app["state"], app["on_phone"]), ("enabled", "1.0.0"))
        with self.assertRaises(devices.DeviceError):
            devices.report(first["id"], {"apps": {"firefox": {"state": "enabled"}}})
        with self.assertRaises(devices.DeviceError):
            devices.report(first["id"], {"apps": {"adaway": {"state": "weird"}}})

    def test_manifest_and_apk_only_for_current_local_copy(self):
        self.assertEqual(devices.manifest()["apps"]["adaway"]["url"], "/api/pivault/devices/helper/apk/adaway")
        path, name, _ = devices.apk("adaway")
        self.assertEqual(name, "AdAway-1.0.0.apk")
        self.assertIsNone(devices.apk("firefox"))
        path.unlink()
        self.assertEqual(devices.manifest()["apps"], {})

    def test_rename_toggle_and_revert(self):
        device = devices.identify({"android_id": "b" * 16})
        devices.rename(device["id"], "Kitchen phone")
        devices.set_app(device["id"], "adaway", False)
        info = devices.overview()["devices"][0]
        self.assertEqual(info["name"], "Kitchen phone")
        self.assertFalse([a for a in info["apps"] if a["client"] == "adaway"][0]["enabled"])
        with self.assertRaises(devices.DeviceError):
            devices.rename(device["id"], " ")
        with self.assertRaises(devices.DeviceError):
            devices.set_app(device["id"], "firefox", True)
        with self.assertRaises(LookupError):
            devices.set_version("adaway", "0" * 64)

    def test_tokens_expire_and_cannot_be_forged(self):
        token = devices.issue_token(now=1000)
        self.assertTrue(devices.token_valid(token, now=1000 + 60))
        self.assertFalse(devices.token_valid(token, now=1000 + devices.TOKEN_SECONDS + 5))
        self.assertFalse(devices.token_valid(token[:-4] + "AAAA"))
        self.assertFalse(devices.token_valid("garbage"))

    def test_helper_script_gets_origin_and_token_but_source_keeps_placeholders(self):
        text = devices.helper_script("https://192.168.4.90:8449")
        self.assertIn("https://192.168.4.90:8449", text)
        self.assertNotIn("__PIVAULT_TOKEN__", text)
        self.assertIn("__PIVAULT_TOKEN__", devices.HELPER.read_text())


class RouteTests(Base):
    def setUp(self):
        super().setUp()
        app = Flask(__name__)
        security = mock.Mock()
        security.dashboard_session_email.return_value = "me@home.lan"
        register_pivault_admin_routes(app, {"security": security})
        self.client = app.test_client()

    def test_helper_routes_need_a_token_and_use_helper_policy(self):
        self.assertEqual(request_policy("POST", "/api/pivault/devices/helper/identify"), "helper")
        self.assertEqual(request_policy("GET", "/api/pivault/devices"), "dashboard")
        self.assertEqual(request_policy("GET", "/api/pivault/devices/sync.py"), "dashboard")
        self.assertEqual(self.client.get("/api/pivault/devices/helper/manifest").status_code, 401)
        header = {"Authorization": "Bearer " + devices.issue_token()}
        self.assertEqual(self.client.get("/api/pivault/devices/helper/manifest", headers=header).status_code, 200)
        reply = self.client.post("/api/pivault/devices/helper/identify", headers=header, json={"android_id": "c" * 16})
        self.assertEqual(reply.status_code, 200)

    def test_inbox_round_trip_over_http(self):
        event = cinema_event()
        (self.notes / "inbox" / (event["id"] + ".json")).write_text(json.dumps(event))
        feed = self.client.get("/api/pivault/notifications").get_json()
        self.assertEqual(feed["open_count"], 1)
        reply = self.client.post("/api/pivault/notifications/%s/resolve" % event["id"], json={"action": "skip"})
        self.assertEqual(reply.status_code, 200)
        again = self.client.post("/api/pivault/notifications/%s/resolve" % event["id"], json={"action": "skip"})
        self.assertEqual(again.status_code, 409)
        bad = self.client.post("/api/pivault/notifications/%s/resolve" % ("0" * 64), json={"action": "resolve"})
        self.assertEqual(bad.status_code, 404)

    def test_unconfigured_returns_503(self):
        with mock.patch.dict(os.environ, {"KOTIBOT_PIVAULT_ADMIN_DIR": ""}):
            self.assertEqual(self.client.get("/api/pivault/notifications").status_code, 503)


if __name__ == "__main__":
    unittest.main()

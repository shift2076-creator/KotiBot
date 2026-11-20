import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from flask import Flask

from subsystems.jobs.jobs import MAX_FILE_BYTES, ROUTE, list_jobs, register_jobs_routes
from subsystems.network import site_settings
from subsystems.security.security_routes import request_policy


def client_for(path=None):
    app = Flask(__name__)
    register_jobs_routes(app, {"path": path} if path is not None else {})
    return app.test_client()


class JobsListTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)

    def job(self, name, definition=None, last=None):
        folder = self.root / name
        folder.mkdir()
        if definition is not None:
            (folder / "job.json").write_text(json.dumps(definition))
        if last is not None:
            (folder / "last-run.json").write_text(json.dumps(last))
        return folder

    def test_lists_each_job_with_its_last_run(self):
        self.job("music", {"name": "Music", "description": "One recording per genre.",
                           "schedule": "Daily 03:00 America/New_York"},
                 {"started": "2026-11-20T03:00:00-05:00", "finished": "2026-11-20T03:09:00-05:00",
                  "result": "ok", "summary": "10 new"})
        self.job("cinema", {"name": "Cinema"}, {"result": "failed", "summary": "disk cap"})
        jobs = list_jobs(self.root)
        self.assertEqual([job["id"] for job in jobs], ["cinema", "music"])
        self.assertEqual(jobs[1]["schedule"], "Daily 03:00 America/New_York")
        self.assertEqual(jobs[1]["last_run"]["result"], "ok")
        self.assertEqual(jobs[0]["last_run"]["result"], "failed")

    def test_a_job_that_has_never_run_still_appears(self):
        self.job("news", {"name": "News"})
        [job] = list_jobs(self.root)
        self.assertEqual(job["last_run"], {"started": "", "finished": "", "result": "unknown", "summary": ""})

    def test_unreadable_files_hide_their_field_not_the_list(self):
        folder = self.job("broken")
        (folder / "job.json").write_text("{not json")
        (folder / "last-run.json").write_text(json.dumps(["not", "an", "object"]))
        self.job("fine", {"name": "Fine"}, {"result": "ok"})
        jobs = {job["id"]: job for job in list_jobs(self.root)}
        self.assertEqual(jobs["broken"]["name"], "broken")
        self.assertEqual(jobs["broken"]["last_run"]["result"], "unknown")
        self.assertEqual(jobs["fine"]["last_run"]["result"], "ok")

    def test_an_unknown_result_word_is_not_passed_through(self):
        self.job("odd", {"name": "Odd"}, {"result": "<script>"})
        self.assertEqual(list_jobs(self.root)[0]["last_run"]["result"], "unknown")

    def test_long_text_is_cut_and_oversized_files_are_ignored(self):
        self.job("long", {"name": "N" * 500, "description": "D" * 5000}, {"summary": "S" * 5000})
        big = self.job("big")
        (big / "job.json").write_text(json.dumps({"name": "x", "pad": "p" * MAX_FILE_BYTES}))
        jobs = {job["id"]: job for job in list_jobs(self.root)}
        self.assertEqual(len(jobs["long"]["name"]), 80)
        self.assertEqual(len(jobs["long"]["description"]), 300)
        self.assertEqual(len(jobs["long"]["last_run"]["summary"]), 300)
        self.assertEqual(jobs["big"]["name"], "big")

    def test_symlinks_and_odd_names_are_skipped(self):
        outside = tempfile.TemporaryDirectory()
        self.addCleanup(outside.cleanup)
        (Path(outside.name) / "job.json").write_text(json.dumps({"name": "Outside"}))
        (self.root / "linked").symlink_to(outside.name)
        real = self.job("real", {"name": "Real"})
        (real / "last-run.json").symlink_to(Path(outside.name) / "job.json")
        (self.root / "Bad Name").mkdir()
        (self.root / "file.txt").write_text("x")
        jobs = list_jobs(self.root)
        self.assertEqual([job["id"] for job in jobs], ["real"])
        self.assertEqual(jobs[0]["last_run"]["result"], "unknown")

    def test_a_missing_directory_is_unavailable(self):
        self.assertIsNone(list_jobs(self.root / "nope"))


class JobsRouteTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)

    def test_unavailable_without_a_directory(self):
        with mock.patch.dict(os.environ, {"KOTIBOT_JOBS_DIR": ""}):
            reply = client_for().get(ROUTE)
        self.assertEqual(reply.get_json(), {"ok": True, "available": False})
        self.assertEqual(client_for(str(self.root / "nope")).get(ROUTE).get_json(),
                         {"ok": True, "available": False})

    def test_lists_jobs_and_reports_the_internet_jobs_switch(self):
        (self.root / "music").mkdir()
        (self.root / "music" / "job.json").write_text(json.dumps({"name": "Music"}))
        settings = self.root.parent / (self.root.name + "-settings.json")
        settings.write_text(json.dumps({"offline_mode": True}))
        self.addCleanup(settings.unlink)
        with mock.patch.dict(os.environ, {site_settings.PATH_ENVIRONMENT: str(settings)}):
            body = client_for(str(self.root)).get(ROUTE).get_json()
        self.assertTrue(body["available"])
        self.assertEqual(body["internet_jobs"], "paused")
        self.assertEqual(body["jobs"][0]["name"], "Music")

    def test_internet_jobs_is_unknown_when_no_settings_file_is_named(self):
        with mock.patch.dict(os.environ, {site_settings.PATH_ENVIRONMENT: ""}):
            body = client_for(str(self.root)).get(ROUTE).get_json()
        self.assertEqual(body["internet_jobs"], "unknown")

    def test_read_only_and_behind_the_dashboard_session(self):
        self.assertEqual(client_for(str(self.root)).post(ROUTE, json={}).status_code, 405)
        self.assertEqual(request_policy("GET", ROUTE), "dashboard")


if __name__ == "__main__":
    unittest.main()

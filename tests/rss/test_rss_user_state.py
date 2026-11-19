import json
import stat
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from flask import Flask

from subsystems.rss import rss_feeds as rss
from subsystems.rss import rss_user_state as state
from subsystems.security.security_routes import request_policy


def feed_xml(count):
    now = datetime.now(timezone.utc)
    items = "".join(
        f"<item><title>Story {i} {'rocket' if i % 5 == 0 else 'budget'}</title>"
        f"<link>https://e.test/s{i}</link>"
        f"<pubDate>{(now - timedelta(minutes=i)).strftime('%a, %d %b %Y %H:%M:%S GMT')}</pubDate></item>"
        for i in range(count)
    )

    return f'<?xml version="1.0"?><rss version="2.0"><channel><title>Wire</title>{items}</channel></rss>'.encode()


def number(item):
    return int(item["title"].split()[1])


class Base(unittest.TestCase):
    count = 18

    def setUp(self):
        rss._CACHE.clear()
        self.addCleanup(rss._CACHE.clear)
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.path = Path(folder.name) / "rss" / "feeds.json"
        self.email = "ann@home.lan"
        security = mock.Mock()
        security.dashboard_session_email.side_effect = lambda: self.email
        app = Flask(__name__)
        rss.register_rss_routes(app, {"path": self.path, "security": security})
        self.client = app.test_client()
        patch = mock.patch.object(rss, "_get", lambda url, deadline: feed_xml(self.count))
        patch.start()
        self.addCleanup(patch.stop)
        self.client.post("/api/rss/feeds", json={"url": "https://e.test/feed.xml"})

    def items(self, query=""):
        return self.client.get("/api/rss/items" + query).get_json()


class PagingTests(Base):
    def test_items_come_in_small_batches_newest_first_with_a_has_more_flag(self):
        first = self.items()
        self.assertEqual([number(i) for i in first["items"]][:3], [0, 1, 2])
        self.assertEqual((len(first["items"]), first["has_more"]), (10, True))
        second = self.items("?limit=10&offset=10")
        self.assertEqual((len(second["items"]), second["has_more"]), (8, False))
        self.assertEqual(number(second["items"][0]), 10)
        self.assertEqual(self.items("?limit=10&offset=500")["items"], [])

    def test_there_is_no_per_feed_cap_so_every_recent_item_can_be_reached(self):
        ids = set()
        for offset in range(0, 40, 10):
            ids |= {i["id"] for i in self.items(f"?limit=10&offset={offset}")["items"]}
        self.assertEqual(len(ids), self.count)

    def test_bad_paging_values_fall_back_or_clamp(self):
        self.assertEqual(len(self.items("?limit=abc&offset=x")["items"]), 10)
        self.assertEqual(len(self.items("?limit=0")["items"]), 1)
        self.assertEqual(len(self.items("?limit=99999")["items"]), self.count)
        self.assertEqual(len(self.items("?limit=5&offset=-3")["items"]), 5)

    def test_search_covers_the_whole_stream_and_pages_its_own_results(self):
        found = self.items("?q=ROCKET&limit=2")
        self.assertEqual([number(i) for i in found["items"]], [0, 5])
        self.assertTrue(found["has_more"])
        rest = self.items("?q=rocket&limit=2&offset=2")
        self.assertEqual([number(i) for i in rest["items"]], [10, 15])
        self.assertFalse(rest["has_more"])
        self.assertEqual(self.items("?q=%20%20Wire%20")["items"][0]["feed"], "Wire")
        self.assertEqual(self.items("?q=nothing-matches")["items"], [])
        self.assertEqual(len(self.items("?q=" + "x" * 5000)["items"]), 0)


class HideTests(Base):
    def test_hiding_removes_an_item_pulls_the_next_one_in_and_can_be_undone(self):
        top = self.items()["items"]
        gone = top[0]["id"]
        self.assertEqual(self.client.post(f"/api/rss/items/{gone}/hide").get_json(), {"ok": True})
        after = self.items()
        self.assertEqual(len(after["items"]), 10)
        self.assertNotIn(gone, [i["id"] for i in after["items"]])
        self.assertEqual([number(i) for i in after["items"]], list(range(1, 11)))
        self.assertEqual(after["hidden_count"], 1)
        shown = self.items("?view=hidden")["items"]
        self.assertEqual([i["id"] for i in shown], [gone])
        self.assertEqual(self.client.post(f"/api/rss/items/{gone}/unhide").get_json(), {"ok": True})
        self.assertEqual(self.items()["items"][0]["id"], gone)
        self.assertEqual(self.items()["hidden_count"], 0)

    def test_hiding_twice_is_harmless_and_odd_ids_are_refused(self):
        ident = self.items()["items"][0]["id"]
        for _ in range(2):
            self.assertEqual(self.client.post(f"/api/rss/items/{ident}/hide").status_code, 200)
        self.assertEqual(self.items()["hidden_count"], 1)
        for bad in ("nope", "../../etc", "G" * 16, "a" * 15):
            self.assertEqual(self.client.post(f"/api/rss/items/{bad}/hide").status_code, 404, bad)

    def test_each_user_has_their_own_hidden_list(self):
        ident = self.items()["items"][0]["id"]
        self.client.post(f"/api/rss/items/{ident}/hide")
        self.email = "bo@home.lan"
        self.assertEqual(self.items()["items"][0]["id"], ident)
        self.assertEqual(self.items()["hidden_count"], 0)
        self.email = "ANN@home.lan "
        self.assertEqual(self.items()["hidden_count"], 1, "the same person, however the email is cased")

    def test_a_session_with_no_email_uses_one_shared_bucket(self):
        ident = self.items()["items"][0]["id"]
        self.email = ""
        self.client.post(f"/api/rss/items/{ident}/hide")
        self.assertEqual(self.items()["hidden_count"], 1)
        self.email = "ann@home.lan"
        self.assertEqual(self.items()["hidden_count"], 0)


class SaveTests(Base):
    def test_saving_copies_the_item_from_the_feed_into_a_folder_and_tags_it(self):
        item = self.items()["items"][3]
        reply = self.client.post(f"/api/rss/saved/{item['id']}", json={"folder": "Climate", "title": "Forged", "link": "https://evil.test/"})
        self.assertEqual(reply.get_json(), {"ok": True})
        saved = self.client.get("/api/rss/saved").get_json()
        self.assertEqual(saved["folders"], ["Read later", "Climate"])
        row = saved["items"][0]
        self.assertEqual((row["title"], row["link"], row["folder"], row["feed"]), (item["title"], item["link"], "Climate", "Wire"))
        tagged = [i for i in self.items()["items"] if i["id"] == item["id"]][0]
        self.assertEqual(tagged["folder"], "Climate")
        self.assertEqual(self.items()["saved_count"], 1)

    def test_saving_again_moves_it_and_removing_takes_it_out(self):
        ident = self.items()["items"][0]["id"]
        self.client.post(f"/api/rss/saved/{ident}", json={"folder": "Read later"})
        self.client.post(f"/api/rss/saved/{ident}", json={"folder": "Work"})
        saved = self.client.get("/api/rss/saved").get_json()
        self.assertEqual([(r["id"], r["folder"]) for r in saved["items"]], [(ident, "Work")])
        self.assertEqual(self.client.post(f"/api/rss/saved/{ident}/remove").get_json(), {"ok": True})
        self.assertEqual(self.client.post(f"/api/rss/saved/{ident}/remove").status_code, 404)
        self.assertEqual(self.client.get("/api/rss/saved").get_json()["items"], [])

    def test_unknown_items_and_bad_folder_names_are_refused(self):
        ident = self.items()["items"][0]["id"]
        self.assertEqual(self.client.post("/api/rss/saved/" + "0" * 16, json={"folder": "X"}).status_code, 404)
        self.assertEqual(self.client.post("/api/rss/saved/nope", json={"folder": "X"}).status_code, 404)
        for body in ({}, {"folder": ""}, {"folder": "   "}, {"folder": "\x00\x01"}):
            self.assertEqual(self.client.post(f"/api/rss/saved/{ident}", json=body).status_code, 400, body)
        long_name = self.client.post(f"/api/rss/saved/{ident}", json={"folder": "n" * 300})
        self.assertEqual(long_name.status_code, 200)
        self.assertEqual(len(self.client.get("/api/rss/saved").get_json()["items"][0]["folder"]), state.MAX_FOLDER_NAME)

    def test_saved_articles_are_per_user_and_survive_the_feed_moving_on(self):
        ident = self.items()["items"][0]["id"]
        self.client.post(f"/api/rss/saved/{ident}", json={"folder": "Keep"})
        self.email = "bo@home.lan"
        self.assertEqual(self.client.get("/api/rss/saved").get_json()["items"], [])
        self.email = "ann@home.lan"
        rss._CACHE.clear()
        with mock.patch.object(rss, "_get", lambda url, deadline: feed_xml(1).replace(b"Story 0", b"Other")):
            self.assertEqual(self.client.get("/api/rss/saved").get_json()["items"][0]["id"], ident)

    def test_the_search_also_finds_by_folder_name(self):
        ident = self.items()["items"][0]["id"]
        self.client.post(f"/api/rss/saved/{ident}", json={"folder": "Garden"})
        self.assertEqual([i["id"] for i in self.items("?q=garden")["items"]], [ident])


class StoredFileTests(Base):
    def test_the_file_holds_no_email_and_is_private(self):
        ident = self.items()["items"][0]["id"]
        self.client.post(f"/api/rss/items/{ident}/hide")
        file = self.path.with_name("user-state.json")
        text = file.read_text()
        self.assertNotIn("ann", text)
        self.assertNotIn("home.lan", text)
        self.assertEqual(stat.S_IMODE(file.stat().st_mode) & 0o077, 0)
        self.assertEqual(list(json.loads(text)["users"]), [state.user_key("ann@home.lan")])

    def test_user_keys_are_stable_distinct_and_never_the_email(self):
        self.assertEqual(state.user_key("A@b.c"), state.user_key(" a@B.c "))
        self.assertNotEqual(state.user_key("a@b.c"), state.user_key("d@b.c"))
        self.assertEqual(state.user_key(""), "dashboard")
        self.assertRegex(state.user_key("a@b.c"), r"^[0-9a-f]{16}$")

    def test_a_damaged_file_is_cleaned_when_read_and_state_survives_a_restart(self):
        file = self.path.with_name("user-state.json")
        file.parent.mkdir(parents=True, exist_ok=True)
        good = "a" * 16
        file.write_text(json.dumps({"users": {
            state.user_key("x@y.z"): {"hidden": [good, good, "bad", 7, "../x"], "saved": [
                {"id": good, "title": "Ok", "link": "javascript:1", "feed": "F", "kind": "weird", "folder": ""},
                {"id": "bad", "title": "x"}, "junk", {"id": "b" * 16, "title": ""}]},
            "not-a-user": {"hidden": [good]}, "dashboard": "text"}}))
        view = state.UserState(file).view(state.user_key("x@y.z"))
        self.assertEqual(view["hidden"], [good])
        self.assertEqual(len(view["saved"]), 1)
        row = view["saved"][0]
        self.assertEqual((row["link"], row["kind"], row["folder"]), ("", "article", state.DEFAULT_FOLDER))
        self.assertEqual(state.UserState(file).view("not-a-user"), {"hidden": [], "saved": []})
        file.write_text("not json")
        self.assertEqual(state.UserState(file).view(state.user_key("x@y.z")), {"hidden": [], "saved": []})


class LimitTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.store = state.UserState(Path(folder.name) / "s.json")

    def item(self, n):
        return {"id": f"{n:016x}", "title": f"T{n}", "link": f"https://e.test/{n}", "feed": "F", "kind": "article"}

    def test_hidden_list_keeps_only_the_newest_entries(self):
        with mock.patch.object(state, "MAX_HIDDEN", 3):
            for n in range(5):
                self.store.hide("dashboard", f"{n:016x}")
        self.assertEqual(self.store.view("dashboard")["hidden"], [f"{n:016x}" for n in (2, 3, 4)])

    def test_saved_articles_and_folders_are_bounded_with_a_readable_message(self):
        with mock.patch.object(state, "MAX_SAVED", 2), mock.patch.object(state, "MAX_FOLDERS", 1):
            self.store.save("dashboard", self.item(1), "A")
            with self.assertRaisesRegex(state.StateError, "up to 1 folders"):
                self.store.save("dashboard", self.item(2), "B")
            self.store.save("dashboard", self.item(2), "A")
            with self.assertRaisesRegex(state.StateError, "up to 2 articles"):
                self.store.save("dashboard", self.item(3), "A")
            self.store.save("dashboard", self.item(2), "A")


class PolicyTests(unittest.TestCase):
    def test_every_new_route_needs_the_dashboard_login(self):
        for method, path in (
            ("GET", "/api/rss/items"), ("GET", "/api/rss/saved"),
            ("POST", "/api/rss/items/" + "a" * 16 + "/hide"), ("POST", "/api/rss/items/" + "a" * 16 + "/unhide"),
            ("POST", "/api/rss/saved/" + "a" * 16), ("POST", "/api/rss/saved/" + "a" * 16 + "/remove"),
        ):
            self.assertEqual(request_policy(method, path), "dashboard", path)


if __name__ == "__main__":
    unittest.main()

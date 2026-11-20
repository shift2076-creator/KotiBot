import json
import time
import unittest
from unittest import mock

from flask import Flask

from subsystems.documents import paperless_shelf as module
from subsystems.documents.paperless_shelf import PaperlessShelf, Unavailable, parse_tokens, register_paperless_routes
from subsystems.security.security_routes import request_policy

OWNER_TOKEN = "a" * 40
GUEST_TOKEN = "b" * 40


def doc(ident, title, **over):
    return {"id": ident, "title": title, "correspondent": 1, "document_type": 2, "added": "2026-11-20T09:00:00Z",
            "modified": "2026-11-20T10:00:00Z", "tags": [], **over}


class Paperless:
    """A fake Paperless: every token sees only its own documents, like the real one."""

    def __init__(self):
        self.calls = []
        self.docs = {
            OWNER_TOKEN: [doc(1, "Electric bill"), doc(2, "Lease agreement", tags=[7]), doc(3, "Dentist receipt")],
            GUEST_TOKEN: [doc(9, "Guest document")],
        }
        self.fail = False

    def __call__(self, path, token):
        self.calls.append((path, token))

        if self.fail:
            raise Unavailable("network")

        if token not in self.docs:
            raise Unavailable("http_401")

        if path.startswith("/api/correspondents/"):
            return {"results": [{"id": 1, "name": "Utility Co"}]}

        if path.startswith("/api/document_types/"):
            return {"results": [{"id": 2, "name": "Bill"}]}

        if path.startswith("/api/tags/"):
            return {"results": [{"id": 7}]}

        if "is_in_inbox" in path:
            return {"count": 4, "results": []}

        rows = self.docs[token]

        if "tags__id__all=7" in path:
            rows = [row for row in rows if 7 in row["tags"]]

        if "title_content=lease" in path:
            rows = [row for row in rows if "lease" in row["title"].lower()]

        return {"count": len(rows), "next": None, "results": rows}


class ShelfTests(unittest.TestCase):
    def setUp(self):
        self.paperless = Paperless()
        self.tokens = {"owner@example.test": OWNER_TOKEN, "guest@example.test": GUEST_TOKEN}
        self.shelf = PaperlessShelf("http://p.test", tokens=lambda: self.tokens, fetch=self.paperless)

    def test_each_person_sees_only_their_own_documents(self):
        mine = self.shelf.documents("owner@example.test")
        theirs = self.shelf.documents("guest@example.test")

        self.assertEqual([i["title"] for i in mine["items"]], ["Electric bill", "Lease agreement", "Dentist receipt"])
        self.assertEqual([i["title"] for i in theirs["items"]], ["Guest document"])
        self.assertTrue(all(token == OWNER_TOKEN for path, token in self.paperless.calls[:1]))

    def test_the_cache_never_mixes_people(self):
        self.shelf.documents("owner@example.test")
        self.assertEqual([i["title"] for i in self.shelf.documents("guest@example.test")["items"]], ["Guest document"])

    def test_someone_without_a_token_gets_no_card_and_no_fallback(self):
        reply = self.shelf.documents("nobody@example.test")

        self.assertEqual(reply, {"ok": True, "available": False})
        self.assertEqual(self.shelf.documents("")["available"], False)
        self.assertEqual(self.paperless.calls, [])

    def test_email_matching_ignores_case(self):
        self.assertTrue(self.shelf.documents("Owner@Example.TEST")["available"])

    def test_items_carry_names_age_fields_and_favorite_flag(self):
        item = self.shelf.documents("owner@example.test")["items"][1]

        self.assertEqual((item["correspondent"], item["type"], item["favorite"]), ("Utility Co", "Bill", True))
        self.assertEqual(item["modified"], "2026-11-20T10:00:00Z")
        self.assertFalse(self.shelf.documents("owner@example.test")["items"][0]["favorite"])

    def test_tabs_choose_the_ordering_and_favs_filters_by_the_favorite_tag(self):
        self.shelf.documents("owner@example.test", "added")
        self.shelf.documents("owner@example.test", "edited")
        favs = self.shelf.documents("owner@example.test", "favs")
        paths = [path for path, _ in self.paperless.calls if path.startswith("/api/documents/?") and "is_in_inbox" not in path]

        self.assertIn("ordering=-added", paths[0])
        self.assertIn("ordering=-modified", paths[1])
        self.assertIn("tags__id__all=7", paths[2])
        self.assertEqual([i["title"] for i in favs["items"]], ["Lease agreement"])

    def test_favs_is_empty_when_the_tag_does_not_exist(self):
        original = self.paperless.__call__

        def none(path, token):
            return {"results": []} if path.startswith("/api/tags/") else original(path, token)

        shelf = PaperlessShelf("http://p.test", tokens=lambda: self.tokens, fetch=none)

        self.assertEqual(shelf.documents("owner@example.test", "favs")["items"], [])

    def test_search_goes_to_paperless_and_inbox_count_comes_with_the_page(self):
        reply = self.shelf.documents("owner@example.test", "added", "  Lease ")

        self.assertEqual([i["title"] for i in reply["items"]], ["Lease agreement"])
        self.assertEqual(reply["inbox_count"], 4)

    def test_paging_uses_whole_pages(self):
        self.shelf.documents("owner@example.test", "added", "", 25, 10)
        path = [p for p, _ in self.paperless.calls if p.startswith("/api/documents/?") and "is_in_inbox" not in p][0]

        self.assertIn("page=3", path)
        self.assertIn("page_size=10", path)

    def test_text_is_reduced_and_bad_rows_are_dropped(self):
        self.paperless.docs[OWNER_TOKEN] = [doc(1, "  <b>x</b>\n\n y  "), {"id": "bad"}, "nope", doc(2, "")]
        titles = [i["title"] for i in self.shelf.documents("owner@example.test")["items"]]

        self.assertEqual(titles, ["<b>x</b> y", "Document 2"])

    def test_a_failure_gives_unavailable_or_the_last_good_page(self):
        self.paperless.fail = True
        self.assertEqual(self.shelf.documents("owner@example.test")["available"], False)
        self.paperless.fail = False
        good = self.shelf.documents("owner@example.test")
        self.paperless.fail = True

        with mock.patch.object(module, "CACHE_SECONDS", 0):
            self.assertEqual(self.shelf.documents("owner@example.test"), good)

    def test_pages_carry_the_public_link_base_when_configured(self):
        shelf = PaperlessShelf("http://p.test", tokens=lambda: self.tokens, fetch=self.paperless, link_base="https://paperless.kotibot.lan")

        self.assertEqual(shelf.documents("owner@example.test")["link_base"], "https://paperless.kotibot.lan")
        self.assertEqual(self.shelf.documents("owner@example.test")["link_base"], "")

    def test_the_card_is_off_without_a_url(self):
        self.assertEqual(PaperlessShelf("", tokens=lambda: self.tokens, fetch=self.paperless).documents("owner@example.test"), {"ok": True, "available": False})


class TokenFileTests(unittest.TestCase):
    def test_only_well_formed_entries_are_kept(self):
        raw = json.dumps({"A@x.test": OWNER_TOKEN, "b@x.test": "short", "c@x.test": 5, "": OWNER_TOKEN})

        self.assertEqual(parse_tokens(raw), {"a@x.test": OWNER_TOKEN})

    def test_bad_json_and_wrong_shapes_give_nothing(self):
        for raw in ("", "not json", "[]", "null"):
            self.assertEqual(parse_tokens(raw), {})


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.paperless = Paperless()
        self.shelf = PaperlessShelf("http://p.test", tokens=lambda: {"owner@example.test": OWNER_TOKEN}, fetch=self.paperless)

    def wait(self, check):
        deadline = time.monotonic() + 3

        while time.monotonic() < deadline and not check():
            time.sleep(0.01)

        self.assertTrue(check())

    def test_a_cold_cache_is_not_ready_and_never_waited_for(self):
        self.assertEqual(self.shelf.bootstrap("owner@example.test"), {"ready": False})
        self.wait(lambda: bool(self.shelf._pages))
        boot = self.shelf.bootstrap("owner@example.test")

        self.assertTrue(boot["ready"] and boot["items"])

    def test_someone_without_a_token_is_ready_and_unavailable_at_once(self):
        self.assertEqual(self.shelf.bootstrap("nobody@example.test"), {"ready": True, "available": False})
        self.assertEqual(self.paperless.calls, [])

    def test_stale_data_is_served_at_once_and_refreshed_in_the_background(self):
        self.shelf.documents("owner@example.test")
        asked = len(self.paperless.calls)

        with mock.patch.object(module, "CACHE_SECONDS", 0):
            boot = self.shelf.bootstrap("owner@example.test")
            self.assertTrue(boot["ready"] and boot["items"])
            self.wait(lambda: len(self.paperless.calls) > asked)


class RouteTests(unittest.TestCase):
    def setUp(self):
        self.paperless = Paperless()
        self.email = "owner@example.test"
        security = mock.Mock()
        security.dashboard_session_email = lambda: self.email
        shelf = PaperlessShelf("http://p.test", tokens=lambda: {"owner@example.test": OWNER_TOKEN, "guest@example.test": GUEST_TOKEN}, fetch=self.paperless)
        app = Flask(__name__)
        register_paperless_routes(app, {"security": security, "shelf": shelf})
        self.app = app
        self.client = app.test_client()

    def test_the_route_answers_for_the_signed_in_person_only(self):
        mine = self.client.get("/api/shelves/paperless/documents?tab=added").get_json()
        self.email = "guest@example.test"
        theirs = self.client.get("/api/shelves/paperless/documents").get_json()
        self.email = "stranger@example.test"
        stranger = self.client.get("/api/shelves/paperless/documents").get_json()

        self.assertEqual(len(mine["items"]), 3)
        self.assertEqual([i["title"] for i in theirs["items"]], ["Guest document"])
        self.assertEqual(stranger, {"ok": True, "available": False})

    def test_bad_arguments_fall_back_to_defaults_and_replies_are_not_cached(self):
        reply = self.client.get("/api/shelves/paperless/documents?tab=zzz&limit=x&offset=-5")

        self.assertEqual(reply.status_code, 200)
        self.assertEqual(reply.headers["Cache-Control"], "no-store")
        self.assertEqual(reply.get_json()["tab"], "added")

    def test_the_bootstrap_hook_is_registered_for_the_index_page(self):
        with self.app.test_request_context("/"):
            self.assertIn("kotibot_paperless_bootstrap", self.app.extensions)
            self.assertEqual(self.app.extensions["kotibot_paperless_bootstrap"]()["ready"], False)

    def test_the_route_is_behind_the_dashboard_login(self):
        self.assertEqual(request_policy("GET", "/api/shelves/paperless/documents"), "dashboard")


if __name__ == "__main__":
    unittest.main()

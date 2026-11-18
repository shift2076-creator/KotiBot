import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
import unittest

from flask import Flask

from server_core.credentials import CredentialMissingError
from subsystems.media import jellyfin_shelf as shelf_module
from subsystems.media.jellyfin_shelf import (
    JellyfinShelf,
    clean_item_id,
    map_resume_item,
    normalize_base_url,
    register_jellyfin_shelf_routes,
)
from subsystems.security.security_routes import request_policy

MOVIE_ID = "a" * 32
EPISODE_ID = "b" * 32
SERIES_ID = "c" * 32
USER_ID = "d" * 32
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 32
PASSWORD = "correct horse battery staple"

RESUME = {
    "Items": [
        {
            "Id": MOVIE_ID,
            "Name": "Nosferatu",
            "Type": "Movie",
            "ProductionYear": 1922,
            "ImageTags": {"Primary": "tagmovie"},
            "RunTimeTicks": 100 * 600_000_000,
            "UserData": {"PlaybackPositionTicks": 25 * 600_000_000},
        },
        {
            "Id": EPISODE_ID,
            "Name": "The Pilot",
            "Type": "Episode",
            "SeriesName": "Some Series",
            "SeriesId": SERIES_ID,
            "SeriesPrimaryImageTag": "tagseries",
            "ParentIndexNumber": 2,
            "IndexNumber": 5,
            "RunTimeTicks": 50 * 600_000_000,
            "UserData": {
                "PlaybackPositionTicks": 10 * 600_000_000,
                "PlayedPercentage": 20.0,
            },
        },
        {"Id": "not-an-id", "Name": "Bad", "Type": "Movie"},
        "not a dict",
    ]
}


class FakeJellyfin:
    def __init__(self):
        self.requests = []
        self.reject_next_token = False
        self.redirect = False
        self.image_type = "image/png"
        self.auth_headers = []
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def _send(self, status, body=b"", content_type="application/json", headers=None):
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))

                for key, value in (headers or {}).items():
                    self.send_header(key, value)

                self.end_headers()
                self.wfile.write(body)

            def do_POST(self):
                length = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(length) or b"{}")
                owner.requests.append(("POST", self.path))
                owner.auth_headers.append(self.headers.get("Authorization"))

                if owner.redirect:
                    return self._send(302, headers={"Location": "http://127.0.0.1:9/x"})

                if body.get("Pw") != PASSWORD:
                    return self._send(401)

                self._send(200, json.dumps({
                    "AccessToken": "token-%d" % len(owner.requests),
                    "User": {"Id": USER_ID},
                }).encode())

            def do_GET(self):
                owner.requests.append(("GET", self.path))
                owner.auth_headers.append(self.headers.get("Authorization"))

                if owner.reject_next_token:
                    owner.reject_next_token = False
                    return self._send(401)

                if self.path.startswith("/Users/%s/Items/Resume" % USER_ID):
                    return self._send(200, json.dumps(RESUME).encode())

                if "/Images/Primary" in self.path:
                    return self._send(200, PNG, owner.image_type)

                self._send(404)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = "http://127.0.0.1:%d" % self.server.server_address[1]

    def count(self, method, needle=""):
        return sum(1 for m, p in self.requests if m == method and needle in p)

    def close(self):
        self.server.shutdown()
        self.server.server_close()


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def credentials(name):
    return {"jellyfin-username": "household", "jellyfin-password": PASSWORD}[name]


class ShelfTestCase(unittest.TestCase):
    def setUp(self):
        self.fake = FakeJellyfin()
        self.addCleanup(self.fake.close)
        self.clock = Clock()

    def shelf(self, read_credentials=credentials, url=None):
        return JellyfinShelf(
            self.fake.url if url is None else url,
            read_credentials=read_credentials,
            clock=self.clock,
        )


class ContinueWatchingTests(ShelfTestCase):
    def test_maps_movies_and_episodes_and_drops_bad_items(self):
        result = self.shelf().continue_watching()

        self.assertTrue(result["available"])
        self.assertEqual(len(result["items"]), 2)
        movie, episode = result["items"]
        self.assertEqual(movie["title"], "Nosferatu")
        self.assertEqual(movie["subtitle"], "1922")
        self.assertEqual(movie["percent"], 25)
        self.assertEqual(movie["minutes_left"], 75)
        self.assertEqual(
            movie["image"],
            "/api/shelves/jellyfin/image/%s?tag=tagmovie" % MOVIE_ID,
        )
        self.assertEqual(episode["title"], "Some Series")
        self.assertEqual(episode["subtitle"], "S2E5 · The Pilot")
        self.assertEqual(episode["percent"], 20)
        self.assertIn(SERIES_ID, episode["image"])

    def test_results_are_cached_for_thirty_seconds(self):
        shelf = self.shelf()
        shelf.continue_watching()
        self.clock.now += 29
        shelf.continue_watching()
        self.assertEqual(self.fake.count("GET", "/Items/Resume"), 1)
        self.clock.now += 2
        shelf.continue_watching()
        self.assertEqual(self.fake.count("GET", "/Items/Resume"), 2)
        self.assertEqual(self.fake.count("POST"), 1)

    def test_expired_token_signs_in_again_once(self):
        shelf = self.shelf()
        shelf.continue_watching()
        self.clock.now += 40
        self.fake.reject_next_token = True
        result = shelf.continue_watching()
        self.assertTrue(result["available"])
        self.assertEqual(self.fake.count("POST"), 2)

    def test_wrong_password_is_unavailable_without_leaking_it(self):
        shelf = self.shelf(
            read_credentials=lambda name: "x" if name.endswith("username") else "wrong-password"
        )
        result = shelf.continue_watching()
        self.assertFalse(result["available"])
        self.assertNotIn("wrong-password", json.dumps(result))
        self.assertEqual(self.fake.count("GET"), 0)

    def test_missing_credentials_never_touch_the_network(self):
        def missing(name):
            raise CredentialMissingError("Credential is missing")

        result = self.shelf(read_credentials=missing).continue_watching()
        self.assertEqual(result["reason"], "credentials_missing")
        self.assertEqual(self.fake.requests, [])

    def test_not_configured_makes_no_requests(self):
        result = self.shelf(url="").continue_watching()
        self.assertEqual(result["reason"], "not_configured")
        self.assertEqual(self.fake.requests, [])

    def test_unreachable_server_is_unavailable(self):
        self.fake.close()
        result = self.shelf().continue_watching()
        self.assertFalse(result["available"])
        self.assertEqual(result["reason"], "unavailable")

    def test_failure_is_cached_so_a_down_server_is_not_hammered(self):
        self.fake.close()
        shelf = self.shelf()
        shelf.continue_watching()
        calls = []
        shelf._opener = type("O", (), {"open": lambda *a, **k: calls.append(1)})()
        shelf.continue_watching()
        self.assertEqual(calls, [])

    def test_redirects_are_not_followed(self):
        self.fake.redirect = True
        result = self.shelf().continue_watching()
        self.assertFalse(result["available"])
        self.assertEqual(self.fake.count("POST"), 1)


class ImageTests(ShelfTestCase):
    def test_poster_is_proxied_with_token_and_cached(self):
        shelf = self.shelf()
        shelf.continue_watching()
        first = shelf.image(MOVIE_ID, "tagmovie")
        second = shelf.image(MOVIE_ID, "tagmovie")
        self.assertEqual(first, (PNG, "image/png"))
        self.assertEqual(first, second)
        self.assertEqual(self.fake.count("GET", "/Images/Primary"), 1)
        self.assertIn('Token="token-', self.fake.auth_headers[-1] or "")

    def test_invalid_id_or_tag_makes_no_request(self):
        shelf = self.shelf()
        for item_id, tag in (("../x", "t"), (MOVIE_ID, "a/b"), (MOVIE_ID, ""), ("", "t")):
            self.assertIsNone(shelf.image(item_id, tag))
        self.assertEqual(self.fake.requests, [])

    def test_non_image_content_type_is_refused(self):
        self.fake.image_type = "text/html"
        self.assertIsNone(self.shelf().image(MOVIE_ID, "tagmovie"))

    def test_image_cache_is_bounded(self):
        shelf = self.shelf()
        for index in range(shelf_module.IMAGE_CACHE_ENTRIES + 5):
            shelf.image("%032x" % index, "t")
        self.assertEqual(len(shelf._images), shelf_module.IMAGE_CACHE_ENTRIES)


class HelperTests(unittest.TestCase):
    def test_base_url_accepts_only_plain_origins(self):
        self.assertEqual(normalize_base_url("http://127.0.0.1:8096/"), "http://127.0.0.1:8096")
        self.assertEqual(normalize_base_url("https://jf.lan"), "https://jf.lan")
        for bad in ("", "ftp://x", "http://u:p@x", "http://x/web", "http://x?a=1", "http://x#f", "x", "http://x:notaport"):
            self.assertEqual(normalize_base_url(bad), "", bad)

    def test_item_ids_are_32_hex(self):
        self.assertEqual(clean_item_id("A" * 8 + "-" + "b" * 24), "a" * 8 + "b" * 24)
        self.assertEqual(clean_item_id("nope"), "")
        self.assertEqual(clean_item_id(None), "")

    def test_percent_is_clamped_and_computed_from_ticks(self):
        item = map_resume_item({
            "Id": MOVIE_ID, "Name": "X", "Type": "Movie",
            "RunTimeTicks": 100, "UserData": {"PlaybackPositionTicks": 500},
        })
        self.assertEqual(item["percent"], 100)
        self.assertIsNone(item["minutes_left"])


class RouteTests(ShelfTestCase):
    def client(self):
        app = Flask(__name__)
        register_jellyfin_shelf_routes(app, {"shelf": self.shelf()})
        return app.test_client()

    def test_routes_require_dashboard_authentication(self):
        for path in (
            "/api/shelves/jellyfin/continue",
            "/api/shelves/jellyfin/image/" + MOVIE_ID,
        ):
            self.assertEqual(request_policy("GET", path), "dashboard", path)

    def test_continue_route_returns_items(self):
        response = self.client().get("/api/shelves/jellyfin/continue")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["available"])

    def test_image_route_serves_image_and_404s_bad_input(self):
        client = self.client()
        client.get("/api/shelves/jellyfin/continue")
        good = client.get("/api/shelves/jellyfin/image/%s?tag=tagmovie" % MOVIE_ID)
        self.assertEqual((good.status_code, good.mimetype), (200, "image/png"))
        self.assertEqual(client.get("/api/shelves/jellyfin/image/%s?tag=" % MOVIE_ID).status_code, 404)
        self.assertEqual(client.get("/api/shelves/jellyfin/image/zzz?tag=t").status_code, 404)


if __name__ == "__main__":
    unittest.main()

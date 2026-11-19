import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from flask import Flask

from subsystems.rss import rss_feeds as rss
from subsystems.security.security_routes import request_policy

RSS = b"""<?xml version="1.0"?><rss version="2.0"><channel><title>Example &amp; Co</title>
<item><title>First &lt;b&gt;story&lt;/b&gt;</title><link>https://e.test/1</link><pubDate>{new}</pubDate></item>
<item><title>Old story</title><link>https://e.test/2</link><pubDate>Mon, 01 Jan 2024 00:00:00 GMT</pubDate></item>
<item><title>Bad link</title><link>javascript:alert(1)</link></item></channel></rss>"""
ATOM = b"""<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"><title>Atom Blog</title>
<entry><title>Atom one</title><link rel="alternate" href="https://a.test/1"/><updated>{new}</updated></entry></feed>"""


def now_rfc():
    return datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")


class ParseTests(unittest.TestCase):
    def test_rss_is_reduced_to_plain_text_and_safe_links(self):
        title, items = rss.parse(RSS.replace(b"{new}", now_rfc().encode()))
        self.assertEqual(title, "Example & Co")
        self.assertEqual(items[0]["title"], "First story")
        self.assertEqual(items[0]["link"], "https://e.test/1")
        self.assertEqual(items[2]["link"], "")

    def test_atom_is_read(self):
        stamp = datetime.now(timezone.utc).isoformat().encode()
        title, items = rss.parse(ATOM.replace(b"{new}", stamp))
        self.assertEqual((title, items[0]["link"]), ("Atom Blog", "https://a.test/1"))

    def test_entity_declarations_and_non_feeds_are_refused(self):
        bomb = b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa">]><rss><channel><title>&a;</title></channel></rss>'
        with self.assertRaises(rss.FeedError):
            rss.parse(bomb)
        with self.assertRaises(rss.FeedError):
            rss.parse(b"<html><body>hi</body></html>")
        with self.assertRaises(rss.FeedError):
            rss.parse(b"not xml")

    def test_url_rules(self):
        self.assertEqual(rss.clean_url(" https://e.test/feed "), "https://e.test/feed")
        for bad in ("", "ftp://e.test/x", "javascript:1", "https://u:p@e.test/", "https://e.test:99999/", "x" * 600):
            self.assertEqual(rss.clean_url(bad), "", bad)


class AddressTests(unittest.TestCase):
    def test_private_and_loopback_addresses_are_refused(self):
        for address in ("127.0.0.1", "10.0.0.5", "192.168.4.90", "169.254.1.1", "::1", "fd00::1"):
            info = [(0, 0, 0, "", (address, 80))]
            with mock.patch("socket.getaddrinfo", return_value=info):
                with self.assertRaises(rss.FeedError, msg=address):
                    rss._public_address("h.test", 80)

    def test_mixed_answers_are_refused_and_public_is_accepted(self):
        mixed = [(0, 0, 0, "", ("93.184.216.34", 80)), (0, 0, 0, "", ("10.0.0.5", 80))]
        with mock.patch("socket.getaddrinfo", return_value=mixed):
            with self.assertRaises(rss.FeedError):
                rss._public_address("h.test", 80)
        with mock.patch("socket.getaddrinfo", return_value=[(0, 0, 0, "", ("93.184.216.34", 80))]):
            self.assertEqual(rss._public_address("h.test", 80), "93.184.216.34")


class GroupTests(unittest.TestCase):
    def setUp(self):
        rss._CACHE.clear()
        self.addCleanup(rss._CACHE.clear)

    def feed(self, n, enabled=True):
        return {"id": f"{n:012x}", "title": f"Feed {n}", "url": f"https://f{n}.test/x", "enabled": enabled}

    def put(self, feed, items):
        rss._CACHE[feed["url"]] = {"items": items, "at": 0, "ok": True}

    def test_groups_are_newest_first_recent_deduplicated_and_capped(self):
        now = datetime.now(timezone.utc)
        a, b = self.feed(1), self.feed(2)
        stamp = lambda h: (now - timedelta(hours=h)).isoformat()
        self.put(a, [{"title": f"A{i}", "link": f"https://e.test/{i}", "published": stamp(i)} for i in range(9)]
                 + [{"title": "Ancient", "link": "https://e.test/old", "published": stamp(24 * 30)}])
        self.put(b, [{"title": "Same story", "link": "https://e.test/0", "published": stamp(0)},
                     {"title": "B1", "link": "https://e.test/b1", "published": stamp(1)}])
        groups = rss.build_groups([a, b], now)
        self.assertEqual([g["title"] for g in groups], ["Feed 1", "Feed 2"])
        self.assertEqual([i["title"] for i in groups[0]["items"]], ["A0", "A1", "A2", "A3", "A4"])
        self.assertEqual([i["title"] for i in groups[1]["items"]], ["B1"])

    def test_disabled_and_empty_feeds_are_left_out(self):
        a, b = self.feed(1, enabled=False), self.feed(2)
        self.put(a, [{"title": "x", "link": "https://e.test/x", "published": datetime.now(timezone.utc).isoformat()}])
        self.put(b, [])
        self.assertEqual(rss.build_groups([a, b]), [])


class RouteTests(unittest.TestCase):
    def setUp(self):
        rss._CACHE.clear()
        self.addCleanup(rss._CACHE.clear)
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.path = Path(folder.name) / "rss" / "feeds.json"
        app = Flask(__name__)
        rss.register_rss_routes(app, {"path": self.path})
        self.client = app.test_client()
        patch = mock.patch.object(rss, "_get", lambda url, deadline: RSS.replace(b"{new}", now_rfc().encode()))
        patch.start()
        self.addCleanup(patch.stop)

    def test_add_update_remove_and_items(self):
        reply = self.client.post("/api/rss/feeds", json={"url": "https://e.test/feed.xml"}).get_json()
        feed = reply["feeds"][0]
        self.assertEqual((feed["title"], feed["enabled"]), ("Example & Co", True))
        self.assertEqual(self.client.post("/api/rss/feeds", json={"url": "https://e.test/feed.xml"}).status_code, 400)
        items = self.client.get("/api/rss/items").get_json()
        self.assertEqual(items["groups"][0]["items"][0]["title"], "First story")
        hidden = self.client.post(f"/api/rss/feeds/{feed['id']}", json={"enabled": False}).get_json()
        self.assertFalse(hidden["feeds"][0]["enabled"])
        self.assertEqual(self.client.get("/api/rss/items").get_json()["groups"], [])
        self.assertEqual(self.client.post(f"/api/rss/feeds/{feed['id']}/remove", json={}).get_json()["feeds"], [])
        self.assertEqual(self.client.post("/api/rss/feeds/aaaaaaaaaaaa/remove", json={}).status_code, 404)

    def test_bad_input_is_rejected_with_a_readable_message(self):
        for body in ({}, {"url": "ftp://x"}, {"url": "javascript:1"}):
            reply = self.client.post("/api/rss/feeds", json=body)
            self.assertEqual(reply.status_code, 400)
            self.assertIn("http", reply.get_json()["error"])

    def test_unreachable_feed_is_not_saved(self):
        with mock.patch.object(rss, "_get", side_effect=rss.FeedError("The feed could not be reached.")):
            reply = self.client.post("/api/rss/feeds", json={"url": "https://e.test/x"})
        self.assertEqual(reply.status_code, 400)
        self.assertFalse(self.path.exists())

    def test_stored_file_is_revalidated_when_read(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text(json.dumps({"feeds": [
            {"id": "0123456789ab", "title": "ok", "url": "https://e.test/x", "enabled": True},
            {"id": "bad", "title": "x", "url": "https://e.test/y"},
            {"id": "0123456789ac", "title": "x", "url": "file:///etc/passwd"}]}))
        self.assertEqual([f["id"] for f in rss._read(self.path)], ["0123456789ab"])

    def test_feed_limit(self):
        for n in range(rss.MAX_FEEDS):
            self.assertTrue(self.client.post("/api/rss/feeds", json={"url": f"https://e{n}.test/f"}).get_json()["ok"])
        self.assertEqual(self.client.post("/api/rss/feeds", json={"url": "https://extra.test/f"}).status_code, 400)

    def test_routes_need_the_dashboard_login(self):
        for method, path in (("GET", "/api/rss/feeds"), ("POST", "/api/rss/feeds"), ("GET", "/api/rss/items"),
                             ("POST", "/api/rss/feeds/0123456789ab"), ("POST", "/api/rss/feeds/0123456789ab/remove")):
            self.assertEqual(request_policy(method, path), "dashboard")


if __name__ == "__main__":
    unittest.main()

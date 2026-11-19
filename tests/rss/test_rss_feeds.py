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


PODCAST = b"""<?xml version="1.0"?><rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd"><channel><title>Show</title>
<item><title>November 18, 2026 - Full episode</title><pubDate>{new}</pubDate>
<guid>https://www.pbs.org/newshour/show/november-18-2026</guid><itunes:duration>53:14</itunes:duration>
<enclosure url="https://cdn.test/ep.mp3" length="1" type="audio/mpeg"/></item></channel></rss>"""
VIDEO_RSS = b"""<?xml version="1.0"?><rss version="2.0" xmlns:media="http://search.yahoo.com/mrss/"><channel><title>V</title>
<item><title>Clip</title><link>https://v.test/clip</link><media:content url="https://cdn.test/c.mp4" type="video/mp4"/></item>
<item><title>On YouTube</title><link>https://www.youtube.com/watch?v=abc</link></item>
<item><title>Plain</title><link>https://v.test/plain</link></item></channel></rss>"""


class KindTests(unittest.TestCase):
    def test_episode_without_link_uses_its_guid_page_and_is_audio_with_minutes(self):
        _title, items = rss.parse(PODCAST.replace(b"{new}", now_rfc().encode()))
        self.assertEqual(items[0]["link"], "https://www.pbs.org/newshour/show/november-18-2026")
        self.assertEqual((items[0]["kind"], items[0]["minutes"]), ("audio", 53))

    def test_the_audio_file_is_never_used_as_the_link(self):
        _title, items = rss.parse(PODCAST.replace(b"{new}", b"").replace(b"<guid>https://www.pbs.org/newshour/show/november-18-2026</guid>", b""))
        self.assertEqual(items[0]["link"], "")

    def test_video_is_recognised_from_media_or_known_video_sites(self):
        _title, items = rss.parse(VIDEO_RSS)
        self.assertEqual([i["kind"] for i in items], ["video", "video", "article"])

    def test_plain_rss_and_atom_items_are_articles(self):
        _t, rss_items = rss.parse(RSS.replace(b"{new}", now_rfc().encode()))
        self.assertEqual({i["kind"] for i in rss_items}, {"article"})
        stamp = datetime.now(timezone.utc).isoformat().encode()
        _t, atom_items = rss.parse(ATOM.replace(b"{new}", stamp))
        self.assertEqual(atom_items[0]["kind"], "article")

    def test_duration_forms(self):
        self.assertEqual([rss._minutes(v) for v in ("53:14", "1:02:03", "600", "", "x", "99999999")], [53, 62, 10, 0, 0, 0])


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


class StreamTests(unittest.TestCase):
    def setUp(self):
        rss._CACHE.clear()
        self.addCleanup(rss._CACHE.clear)

    def feed(self, n, enabled=True):
        return {"id": f"{n:012x}", "title": f"Feed {n}", "url": f"https://f{n}.test/x", "enabled": enabled}

    def put(self, feed, items):
        rss._CACHE[feed["url"]] = {"items": items, "at": 0, "ok": True}

    def item(self, title, link, moment, kind="article"):
        return {"title": title, "link": link, "published": moment.isoformat(), "kind": kind, "minutes": 0}

    def test_one_newest_first_stream_that_is_recent_deduplicated_and_capped_per_feed(self):
        now = datetime.now(timezone.utc)
        a, b = self.feed(1), self.feed(2)
        ago = lambda h: now - timedelta(hours=h)
        self.put(a, [self.item(f"A{i}", f"https://e.test/{i}", ago(i * 2)) for i in range(9)]
                 + [self.item("Ancient", "https://e.test/old", ago(24 * 30))])
        self.put(b, [self.item("Same story", "https://e.test/0", ago(0)), self.item("B1", "https://e.test/b1", ago(1))])
        stream = rss.build_items([a, b], now)
        self.assertEqual([i["title"] for i in stream], ["A0", "B1", "A1", "A2", "A3", "A4"])
        self.assertEqual({i["feed"] for i in stream}, {"Feed 1", "Feed 2"})
        self.assertEqual(stream[1]["feed_id"], b["id"])

    def test_kind_and_minutes_travel_with_each_item(self):
        feed = self.feed(1)
        self.put(feed, [self.item("Ep", "https://e.test/ep", datetime.now(timezone.utc), "audio")])
        self.assertEqual(rss.build_items([feed])[0]["kind"], "audio")

    def test_a_feed_kind_overrides_what_its_items_declare_and_auto_keeps_it(self):
        pinned, auto = {**self.feed(1), "kind": "video"}, {**self.feed(2), "kind": "auto"}
        self.put(pinned, [self.item("Ep", "https://e.test/ep", datetime.now(timezone.utc), "audio")])
        self.put(auto, [self.item("Ep2", "https://e.test/ep2", datetime.now(timezone.utc), "audio")])
        kinds = {i["title"]: i["kind"] for i in rss.build_items([pinned, auto])}
        self.assertEqual(kinds, {"Ep": "video", "Ep2": "audio"})

    def test_disabled_feeds_are_left_out(self):
        a = self.feed(1, enabled=False)
        self.put(a, [self.item("x", "https://e.test/x", datetime.now(timezone.utc))])
        self.assertEqual(rss.build_items([a]), [])


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
        self.assertEqual(items["items"][0]["title"], "First story")
        self.assertEqual((items["items"][0]["feed"], items["items"][0]["kind"]), ("Example & Co", "article"))
        hidden = self.client.post(f"/api/rss/feeds/{feed['id']}", json={"enabled": False}).get_json()
        self.assertFalse(hidden["feeds"][0]["enabled"])
        self.assertEqual(self.client.get("/api/rss/items").get_json()["items"], [])
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

    def test_feed_kind_can_be_set_and_rejects_nonsense(self):
        feed = self.client.post("/api/rss/feeds", json={"url": "https://e.test/feed.xml"}).get_json()["feeds"][0]
        self.assertEqual(feed["kind"], "auto")
        set_video = self.client.post(f"/api/rss/feeds/{feed['id']}", json={"kind": "video"}).get_json()
        self.assertEqual(set_video["feeds"][0]["kind"], "video")
        self.assertEqual(self.client.get("/api/rss/items").get_json()["items"][0]["kind"], "video")
        self.assertEqual(self.client.post(f"/api/rss/feeds/{feed['id']}", json={"kind": "podcast"}).status_code, 400)

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


PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 20


class IconTests(unittest.TestCase):
    def setUp(self):
        rss._CACHE.clear()
        rss._ICONS.clear()
        self.addCleanup(rss._CACHE.clear)
        self.addCleanup(rss._ICONS.clear)
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        app = Flask(__name__)
        rss.register_rss_routes(app, {"path": Path(folder.name) / "rss" / "feeds.json"})
        self.client = app.test_client()
        self.asked = []

    def serve(self, pages):
        def fake(url, deadline, accept=None, limit=rss.MAX_BYTES):
            self.asked.append(url)
            if url.endswith("feed.xml"):
                return RSS.replace(b"{new}", now_rfc().encode())
            if url in pages:
                return pages[url]
            raise rss.FeedError("nope")
        patch = mock.patch.object(rss, "_get", fake)
        patch.start()
        self.addCleanup(patch.stop)

    def feed(self):
        self.client.post("/api/rss/feeds", json={"url": "https://e.test/feed.xml"})
        return self.client.get("/api/rss/items").get_json()["items"]

    def test_items_carry_the_icon_route_for_their_site(self):
        self.serve({})
        items = self.feed()
        linked = [i for i in items if i["link"]]
        self.assertTrue(linked and all(i["icon"] == "/api/rss/icon/e.test" for i in linked))
        self.assertTrue(all(i["icon"] == "" for i in items if not i["link"]))

    def test_host_of_accepts_only_plain_public_looking_names(self):
        self.assertEqual(rss.host_of("https://WWW.PBS.org/a"), "www.pbs.org")
        for bad in ("", "javascript:1", "https://localhost/", "https://10.0.0.1/", "ftp://a.b/", "https://a_b.c/"):
            self.assertEqual(rss.host_of(bad), "", bad)

    def test_serves_favicon_ico_with_locked_down_headers(self):
        self.serve({"https://e.test/favicon.ico": PNG})
        self.feed()
        reply = self.client.get("/api/rss/icon/e.test")
        self.assertEqual((reply.status_code, reply.mimetype, reply.data), (200, "image/png", PNG))
        self.assertEqual(reply.headers["X-Content-Type-Options"], "nosniff")
        self.assertIn("default-src 'none'", reply.headers["Content-Security-Policy"])

    def test_falls_back_to_the_icon_link_in_the_page(self):
        self.serve({"https://e.test/": b'<html><link rel="stylesheet" href="/s.css"><link rel="shortcut icon" href="/i/fav.png">',
                    "https://e.test/i/fav.png": PNG})
        self.feed()
        self.assertEqual(self.client.get("/api/rss/icon/e.test").data, PNG)

    def test_refuses_svg_html_and_unknown_hosts_and_remembers_misses(self):
        self.serve({"https://e.test/favicon.ico": b"<svg onload=alert(1)>"})
        self.feed()
        self.assertEqual(self.client.get("/api/rss/icon/e.test").status_code, 404)
        count = len(self.asked)
        self.assertEqual(self.client.get("/api/rss/icon/e.test").status_code, 404)
        self.assertEqual(len(self.asked), count)
        self.assertEqual(self.client.get("/api/rss/icon/other.test").status_code, 404)
        self.assertEqual(self.client.get("/api/rss/icon/127.0.0.1").status_code, 404)

    def test_icon_route_is_behind_the_dashboard_login(self):
        self.assertEqual(request_policy("GET", "/api/rss/icon/e.test"), "dashboard")

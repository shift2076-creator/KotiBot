"""RSS and Atom news feeds for the dashboard Home page.

The Admin keeps a short list of feeds in Settings. KotiBot fetches them, never
the browser, so no page script talks to a feed host and every request stays
behind the dashboard login. Feed text is untrusted: it is reduced to plain text,
links are limited to http(s), and the browser builds the cards with textContent.

Fetching is deliberately conservative: public addresses only (checked on the
address the connection really uses, after every redirect), small size cap, short
timeout, no compressed bodies, and XML that declares a DTD or entities is
refused, which closes the entity-expansion attacks the standard library parser
does not guard against.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import hashlib
import html
import http.client
import ipaddress
import json
import logging
import os
from pathlib import Path
import re
import socket
import ssl
import tempfile
import time
from threading import Lock
from urllib import parse as urlparse
from xml.etree import ElementTree

from flask import jsonify, request


LOGGER = logging.getLogger(__name__)

MAX_FEEDS = 12
MAX_URL_LENGTH = 500
MAX_TITLE_LENGTH = 60
ITEMS_PER_FEED = 5
KEEP_PER_FEED = 20
MAX_AGE_DAYS = 14
CACHE_SECONDS = 15 * 60
RETRY_SECONDS = 60
TIMEOUT_SECONDS = 6
MAX_BYTES = 1024 * 1024
MAX_REDIRECTS = 3
USER_AGENT = "KotiBot-RSS/1"

_LOCK = Lock()
_CACHE = {}
_DOCTYPE = re.compile(rb"<!\s*(DOCTYPE|ENTITY)", re.IGNORECASE)
_TAGS = re.compile(r"<[^>]*>")
_SPACE = re.compile(r"\s+")
_ATOM = "{http://www.w3.org/2005/Atom}"
_MEDIA = "{http://search.yahoo.com/mrss/}"
_ITUNES = "{http://www.itunes.com/dtds/podcast-1.0.dtd}"
_YOUTUBE = "{http://www.youtube.com/xml/schemas/2015}"
_VIDEO_HOSTS = ("youtube.com", "youtu.be", "vimeo.com")

ARTICLE, VIDEO, AUDIO = "article", "video", "audio"
KINDS = (ARTICLE, VIDEO, AUDIO)


class FeedError(Exception):
    """A feed could not be added or read. The text is safe to show the Admin."""


# --- addresses and fetching -------------------------------------------------

def clean_url(value):
    """Return the URL if it is a plain http(s) address, else ''."""
    text = str(value or "").strip()

    if not text or len(text) > MAX_URL_LENGTH:
        return ""

    try:
        parsed = urlparse.urlsplit(text)
        port = parsed.port
    except ValueError:
        return ""

    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return ""

    if parsed.username or parsed.password:
        return ""

    if port is not None and not 1 <= port <= 65535:
        return ""

    return text


def _public_address(host, port):
    """Return one public IP for host, or raise FeedError."""
    try:
        found = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError:
        raise FeedError("That address could not be found.")

    addresses = []

    for item in found:
        address = ipaddress.ip_address(item[4][0].split("%", 1)[0])

        if not address.is_global:
            raise FeedError("Only public internet addresses are allowed.")

        addresses.append(address)

    if not addresses:
        raise FeedError("That address could not be found.")

    return str(addresses[0])


class _Pinned(http.client.HTTPConnection):
    """Connects to an address that was already checked, not a fresh lookup."""

    def __init__(self, host, port, address, **kwargs):
        super().__init__(host, port, **kwargs)
        self._address = address

    def connect(self):
        self.sock = socket.create_connection(
            (self._address, self.port), self.timeout
        )


class _PinnedTls(http.client.HTTPSConnection):
    def __init__(self, host, port, address, **kwargs):
        super().__init__(host, port, context=ssl.create_default_context(), **kwargs)
        self._address = address

    def connect(self):
        raw = socket.create_connection((self._address, self.port), self.timeout)
        self.sock = self._context.wrap_socket(raw, server_hostname=self.host)


def _get(url, deadline):
    """Fetch url, following a few redirects, and return the body bytes."""
    for _ in range(MAX_REDIRECTS + 1):
        parts = urlparse.urlsplit(url)
        secure = parts.scheme == "https"
        port = parts.port or (443 if secure else 80)
        address = _public_address(parts.hostname, port)
        remaining = deadline - time.monotonic()

        if remaining <= 0:
            raise FeedError("The feed took too long to answer.")

        timeout = min(TIMEOUT_SECONDS, remaining)
        connection = (_PinnedTls if secure else _Pinned)(
            parts.hostname, port, address, timeout=timeout
        )

        try:
            path = urlparse.urlunsplit(("", "", parts.path or "/", parts.query, ""))
            connection.request("GET", path, headers={
                "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml",
                "Accept-Encoding": "identity",
                "User-Agent": USER_AGENT,
            })
            response = connection.getresponse()

            if response.status in (301, 302, 303, 307, 308):
                target = response.getheader("Location") or ""
                url = clean_url(urlparse.urljoin(url, target))

                if not url:
                    raise FeedError("The feed redirected somewhere that is not allowed.")

                continue

            if response.status != 200:
                raise FeedError(f"The feed answered with an error ({response.status}).")

            body = response.read(MAX_BYTES + 1)
        except FeedError:
            raise
        except (OSError, http.client.HTTPException):
            raise FeedError("The feed could not be reached.")
        finally:
            connection.close()

        if len(body) > MAX_BYTES:
            raise FeedError("The feed is too large.")

        return body

    raise FeedError("The feed redirected too many times.")


# --- parsing ----------------------------------------------------------------

def _text(value, limit):
    text = html.unescape(_TAGS.sub(" ", str(value or "")))
    text = _SPACE.sub(" ", text).strip()

    return text if len(text) <= limit else text[:limit - 1].rstrip() + "…"


def _when(value):
    text = str(value or "").strip()

    if not text:
        return None

    try:
        moment = parsedate_to_datetime(text)
    except (TypeError, ValueError, IndexError):
        try:
            moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None

    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)

    return moment.astimezone(timezone.utc)


def _child(node, *names):
    for name in names:
        found = node.find(name)

        if found is not None and found.text:
            return found.text

    return ""


def _atom_link(entry):
    best = ""

    for link in entry.findall(f"{_ATOM}link"):
        href = link.get("href") or ""

        if link.get("rel") in (None, "", "alternate"):
            return href

        best = best or href

    return best


def _minutes(value):
    """Minutes from an iTunes duration: seconds, mm:ss or hh:mm:ss."""
    text = str(value or "").strip()

    if not re.fullmatch(r"\d{1,5}(:\d{1,2}){0,2}", text):
        return 0

    seconds = 0

    for part in text.split(":"):
        seconds = seconds * 60 + int(part)

    return seconds // 60


def _kind(item, link):
    """article, video or audio, from the media the item itself declares."""
    types = []

    for node in item.iter():
        if node.tag in ("enclosure", f"{_MEDIA}content"):
            types.append(str(node.get("type") or "").lower())
            types.append(str(node.get("medium") or "").lower() + "/")

        if node.tag == f"{_YOUTUBE}videoId":
            return VIDEO

    if any(value.startswith("video/") for value in types):
        return VIDEO

    if any(value.startswith("audio/") for value in types):
        return AUDIO

    host = (urlparse.urlsplit(link).hostname or "").lower()

    if any(host == name or host.endswith("." + name) for name in _VIDEO_HOSTS):
        return VIDEO

    return ARTICLE


def _make_item(item, title, link, guid, date, duration):
    item_title = _text(title, 160)
    # Podcast feeds often have no <link>; their <guid> is the episode page.
    address = clean_url(str(link or "").strip()) or clean_url(str(guid or "").strip())

    if not item_title:
        return None

    moment = _when(date)

    return {
        "title": item_title,
        "link": address,
        "published": moment.isoformat() if moment else "",
        "kind": _kind(item, address),
        "minutes": _minutes(duration),
    }


def parse(body):
    """Return (feed_title, items) from RSS 2.0 or Atom bytes."""
    if _DOCTYPE.search(body):
        raise FeedError("That feed uses XML features that are not allowed.")

    try:
        root = ElementTree.fromstring(body)
    except ElementTree.ParseError:
        raise FeedError("That address is not an RSS or Atom feed.")

    items = []

    if root.tag == f"{_ATOM}feed":
        title = _text(_child(root, f"{_ATOM}title"), MAX_TITLE_LENGTH)

        for entry in root.findall(f"{_ATOM}entry"):
            made = _make_item(
                entry,
                _child(entry, f"{_ATOM}title"),
                _atom_link(entry),
                "",
                _child(entry, f"{_ATOM}updated", f"{_ATOM}published"),
                "",
            )

            if made:
                items.append(made)
    elif root.tag in ("rss", "{http://www.w3.org/1999/02/22-rdf-syntax-ns#}RDF"):
        channel = root.find("channel")
        channel = channel if channel is not None else root
        title = _text(_child(channel, "title"), MAX_TITLE_LENGTH)

        for node in list(channel.iter("item")):
            made = _make_item(
                node,
                _child(node, "title"),
                _child(node, "link"),
                _child(node, "guid"),
                _child(node, "pubDate", "{http://purl.org/dc/elements/1.1/}date"),
                _child(node, f"{_ITUNES}duration"),
            )

            if made:
                items.append(made)
    else:
        raise FeedError("That address is not an RSS or Atom feed.")

    return title, items[:KEEP_PER_FEED]


# --- stored feed list -------------------------------------------------------

def _read(path):
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []

    rows = value.get("feeds") if isinstance(value, dict) else None
    clean = []

    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue

        url = clean_url(row.get("url"))
        feed_id = str(row.get("id") or "")

        if url and re.fullmatch(r"[0-9a-f]{12}", feed_id):
            clean.append({
                "id": feed_id,
                "title": _text(row.get("title"), MAX_TITLE_LENGTH) or url,
                "url": url,
                "enabled": row.get("enabled") is not False,
            })

    return clean[:MAX_FEEDS]


def _write(path, feeds):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    handle, name = tempfile.mkstemp(dir=target.parent, prefix=".feeds-")

    try:
        with os.fdopen(handle, "w", encoding="utf-8") as out:
            json.dump({"feeds": feeds}, out, indent=2)
            out.write("\n")

        os.replace(name, target)
    except BaseException:
        try:
            os.unlink(name)
        except OSError:
            pass

        raise


def _feed_id(url):
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:12]


# --- building the Home shelf ------------------------------------------------

def _refresh(feed):
    """Fetch one feed into the cache. Keeps the old items when a fetch fails."""
    deadline = time.monotonic() + TIMEOUT_SECONDS * 2
    previous = _CACHE.get(feed["url"], {})

    try:
        _title, items = parse(_get(feed["url"], deadline))
        _CACHE[feed["url"]] = {"items": items, "at": time.monotonic(), "ok": True}
    except FeedError:
        _CACHE[feed["url"]] = {
            "items": previous.get("items", []),
            "at": time.monotonic() - CACHE_SECONDS + RETRY_SECONDS,
            "ok": False,
        }


def _stale(feed):
    cached = _CACHE.get(feed["url"])

    return not cached or time.monotonic() - cached["at"] >= CACHE_SECONDS


def _norm(text):
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def build_items(feeds, now=None):
    """One newest-first stream: recent only, no repeats, a few per feed."""
    now = now or datetime.now(timezone.utc)
    seen = set()
    stream = []
    oldest = datetime.min.replace(tzinfo=timezone.utc)

    for feed in feeds:
        if not feed["enabled"]:
            continue

        rows = []

        for item in _CACHE.get(feed["url"], {}).get("items", []):
            moment = _when(item["published"])

            if moment and (now - moment).days > MAX_AGE_DAYS:
                continue

            key = item["link"] or _norm(item["title"])

            if key in seen:
                continue

            seen.add(key)
            rows.append((moment or oldest, item))

        rows.sort(key=lambda pair: pair[0], reverse=True)

        for moment, item in rows[:ITEMS_PER_FEED]:
            stream.append((moment, {**item, "feed": feed["title"], "feed_id": feed["id"]}))

    stream.sort(key=lambda pair: pair[0], reverse=True)

    return [item for _moment, item in stream]


def register_rss_routes(app, context):
    path = context["path"]

    def listing():
        return jsonify({"ok": True, "feeds": _read(path)})

    @app.route("/api/rss/feeds", methods=["GET"])
    def api_rss_feeds_get():
        return listing()

    @app.route("/api/rss/feeds", methods=["POST"])
    def api_rss_feeds_add():
        data = request.get_json(silent=True) or {}
        url = clean_url(data.get("url"))

        if not url:
            return jsonify({"ok": False, "error": "Enter a full web address that starts with http:// or https://."}), 400

        with _LOCK:
            feeds = _read(path)

            if len(feeds) >= MAX_FEEDS:
                return jsonify({"ok": False, "error": f"You can add up to {MAX_FEEDS} feeds."}), 400

            if any(feed["url"] == url for feed in feeds):
                return jsonify({"ok": False, "error": "That feed is already in the list."}), 400

            try:
                found_title, items = parse(_get(url, time.monotonic() + TIMEOUT_SECONDS * 2))
            except FeedError as problem:
                return jsonify({"ok": False, "error": str(problem)}), 400

            title = _text(data.get("title"), MAX_TITLE_LENGTH) or found_title or urlparse.urlsplit(url).hostname
            feeds.append({"id": _feed_id(url), "title": title, "url": url, "enabled": True})
            _write(path, feeds)
            _CACHE[url] = {"items": items, "at": time.monotonic(), "ok": True}

        return listing()

    @app.route("/api/rss/feeds/<feed_id>", methods=["POST"])
    def api_rss_feeds_update(feed_id):
        data = request.get_json(silent=True) or {}

        with _LOCK:
            feeds = _read(path)
            feed = next((row for row in feeds if row["id"] == feed_id), None)

            if feed is None:
                return jsonify({"ok": False, "error": "That feed is not in the list."}), 404

            if "title" in data:
                title = _text(data.get("title"), MAX_TITLE_LENGTH)

                if not title:
                    return jsonify({"ok": False, "error": "Give the feed a name."}), 400

                feed["title"] = title

            if "enabled" in data:
                feed["enabled"] = data.get("enabled") is True

            _write(path, feeds)

        return listing()

    @app.route("/api/rss/feeds/<feed_id>/remove", methods=["POST"])
    def api_rss_feeds_remove(feed_id):
        with _LOCK:
            feeds = _read(path)
            kept = [row for row in feeds if row["id"] != feed_id]

            if len(kept) == len(feeds):
                return jsonify({"ok": False, "error": "That feed is not in the list."}), 404

            _write(path, kept)

        return listing()

    @app.route("/api/rss/items", methods=["GET"])
    def api_rss_items():
        feeds = [feed for feed in _read(path) if feed["enabled"]]
        stale = [feed for feed in feeds if _stale(feed)]

        if stale:
            with ThreadPoolExecutor(max_workers=min(4, len(stale))) as pool:
                list(pool.map(_refresh, stale))

        response = jsonify({"ok": True, "items": build_items(feeds)})
        response.headers["Cache-Control"] = "no-store"

        return response

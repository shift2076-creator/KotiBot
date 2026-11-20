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
from threading import BoundedSemaphore, Lock, Thread
from urllib import parse as urlparse
from xml.etree import ElementTree

from flask import Response, abort, jsonify, request

from . import rss_user_state as user_state


LOGGER = logging.getLogger(__name__)

MAX_FEEDS = 12
MAX_URL_LENGTH = 500
MAX_TITLE_LENGTH = 60
PAGE_DEFAULT = 10
PAGE_MAX = 300
QUERY_MAX = 100
KEEP_PER_FEED = 20
MAX_AGE_DAYS = 14
CACHE_SECONDS = 15 * 60
RETRY_SECONDS = 60
TIMEOUT_SECONDS = 6
# Podcast feeds list their whole back catalogue (NPR Up First is about 2 MB).
MAX_BYTES = 4 * 1024 * 1024
MAX_REDIRECTS = 3
USER_AGENT = "KotiBot-RSS/1"
ICON_BYTES = 64 * 1024
PAGE_BYTES = 256 * 1024
ICON_SECONDS = 24 * 60 * 60
ICON_MISS_SECONDS = 60 * 60
MAX_ICONS = 64
# An icon request never holds a server thread for long: the site is fetched by a
# small background pool, and a request waits only this long (and only while fewer
# than ICON_WAITERS requests are already waiting) before answering "not yet".
ICON_WAIT_SECONDS = 1.5
ICON_WAITERS = 2
ICON_WORKERS = 3

_LOCK = Lock()
_CACHE = {}
_ICONS = {}
_ICON_JOBS = {}
_ICON_POOL = ThreadPoolExecutor(max_workers=ICON_WORKERS, thread_name_prefix="rss-icon")
_ICON_WAITING = BoundedSemaphore(ICON_WAITERS)
_PREFETCH = {"started": False}
_REFRESHING = Lock()
PREFETCH_SECONDS = 60
_HOST = re.compile(r"[a-z0-9]([a-z0-9.-]{0,251}[a-z0-9])?")
_LINK_TAG = re.compile(r"<link\b[^>]*>", re.IGNORECASE)
_REL = re.compile(r"""\brel\s*=\s*["']([^"']*)["']""", re.IGNORECASE)
_HREF = re.compile(r"""\bhref\s*=\s*["']([^"']*)["']""", re.IGNORECASE)
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
# A feed's own data cannot always say what its items are (PBS tags a video
# show as an audio podcast), so the Admin can fix the kind per feed.
AUTO = "auto"
FEED_KINDS = (AUTO,) + KINDS


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


def _get(url, deadline, accept=None, limit=MAX_BYTES):
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
                "Accept": accept or "application/rss+xml, application/atom+xml, application/xml, text/xml",
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

            body = response.read(limit + 1)
        except FeedError:
            raise
        except (OSError, http.client.HTTPException):
            raise FeedError("The feed could not be reached.")
        finally:
            connection.close()

        if len(body) > limit:
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
                "kind": row.get("kind") if row.get("kind") in FEED_KINDS else AUTO,
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


def item_ident(item):
    """The stable id of a cached item, shared by hide and save."""
    return user_state.item_id(item["link"], _norm(item["title"]))


def build_items(feeds, now=None, skip=(), only=None):
    """One newest-first stream: recent only, no repeats.

    The caller pages through it (the Home card loads a few rows at a time as it
    scrolls), so there is no per-feed cap; each feed already keeps only its newest
    KEEP_PER_FEED items. skip holds ids the caller has hidden; only keeps just
    those ids (the Hidden view).
    """
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
            ident = item_ident(item)

            if key in seen or ident in skip or (only is not None and ident not in only):
                continue

            seen.add(key)
            rows.append((moment or oldest, item, ident))

        rows.sort(key=lambda row: row[0], reverse=True)

        for moment, item, ident in rows:
            kind = item["kind"] if feed.get("kind", AUTO) == AUTO else feed["kind"]
            host = host_of(item["link"])
            stream.append((moment, {
                **item, "id": ident, "kind": kind, "feed": feed["title"], "feed_id": feed["id"],
                "icon": f"/api/rss/icon/{host}" if host else "",
            }))

    stream.sort(key=lambda pair: pair[0], reverse=True)

    return [item for _moment, item in stream]


# --- site icons ---------------------------------------------------------------
# The favicon of the site an item links to is fetched here, once, and served from
# KotiBot, so the browser never contacts the news sites. Only raster images are
# accepted (an SVG can carry script), and only for hosts that appear in the feeds.

def host_of(link):
    """The lower-case host of an http(s) link, or "" when it is not a usable name."""
    try:
        parts = urlparse.urlsplit(link or "")
        host = (parts.hostname or "").lower()
    except ValueError:
        return ""

    if parts.scheme not in ("http", "https") or "." not in host:
        return ""

    if not _HOST.fullmatch(host) or re.fullmatch(r"[0-9.]+", host):
        return ""

    return host


def _sniff(body):
    if body.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"

    if body.startswith(b"GIF8"):
        return "image/gif"

    if body.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"

    if body.startswith(b"\x00\x00\x01\x00"):
        return "image/x-icon"

    if body[:4] == b"RIFF" and body[8:12] == b"WEBP":
        return "image/webp"

    return ""


def _page_icon(page, base):
    """The first icon link in an HTML page, as an absolute http(s) URL, or ""."""
    for tag in _LINK_TAG.findall(page.decode("latin-1")):
        rel = _REL.search(tag)
        href = _HREF.search(tag)

        if rel and href and "icon" in rel.group(1).lower().split() and href.group(1).strip():
            return clean_url(urlparse.urljoin(base, html.unescape(href.group(1).strip()))) or ""

    return ""


def _icon_cached(host):
    """(True, icon or None) while host's answer is still fresh, else (False, None)."""
    with _LOCK:
        cached = _ICONS.get(host)

    if cached and time.monotonic() - cached["at"] < (ICON_SECONDS if cached["found"] else ICON_MISS_SECONDS):
        return True, cached["found"]

    return False, None


def icon_job(host):
    """Start fetching host's favicon in the background; None when it is already cached."""
    if _icon_cached(host)[0]:
        return None

    with _LOCK:
        job = _ICON_JOBS.get(host)

        if job is None:
            job = _ICON_JOBS[host] = _ICON_POOL.submit(_icon_task, host)

    return job


def _icon_task(host):
    try:
        return fetch_icon(host)
    finally:
        with _LOCK:
            _ICON_JOBS.pop(host, None)


def warm_icons(feeds):
    """Fetch the icons for every site in the cached feeds, without waiting for them."""
    hosts = []

    for feed in feeds:
        for item in _CACHE.get(feed["url"], {}).get("items", []):
            host = host_of(item["link"])

            if host and host not in hosts:
                hosts.append(host)

    for host in hosts[:MAX_ICONS]:
        icon_job(host)


def fetch_icon(host):
    """Return (bytes, content_type) for host's favicon, or None. Cached."""
    now = time.monotonic()
    hit, cached = _icon_cached(host)

    if hit:
        return cached

    found = None
    deadline = now + 2 * TIMEOUT_SECONDS
    image = "image/png, image/x-icon, image/gif, image/jpeg, image/webp"
    candidates = [f"https://{host}/favicon.ico", None]

    for url in candidates:
        try:
            if url is None:
                url = _page_icon(_get(f"https://{host}/", deadline, "text/html", PAGE_BYTES), f"https://{host}/")

                if not url:
                    break

            body = _get(url, deadline, image, ICON_BYTES)
        except FeedError:
            continue

        kind = _sniff(body)

        if kind:
            found = (body, kind)
            break

    with _LOCK:
        if len(_ICONS) >= MAX_ICONS:
            _ICONS.pop(next(iter(_ICONS)))

        _ICONS[host] = {"found": found, "at": time.monotonic()}

    return found


def register_rss_routes(app, context):
    path = context["path"]
    security = context.get("security")
    state = user_state.UserState(context.get("user_state_path") or Path(path).with_name("user-state.json"))

    def current_user():
        email = security.dashboard_session_email() if security else ""

        return user_state.user_key(email)

    def refresh_stale(feeds):
        stale = [feed for feed in feeds if _stale(feed)]

        if stale:
            with ThreadPoolExecutor(max_workers=min(4, len(stale))) as pool:
                list(pool.map(_refresh, stale))

    def no_store(payload):
        response = jsonify(payload)
        response.headers["Cache-Control"] = "no-store"

        return response

    def with_saved(items, saved):
        folders = {row["id"]: row["folder"] for row in saved}

        return [{**item, "folder": folders.get(item["id"], "")} for item in items]

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
            kind = data.get("kind") if data.get("kind") in FEED_KINDS else AUTO
            feeds.append({"id": _feed_id(url), "title": title, "url": url, "enabled": True, "kind": kind})
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

            if "kind" in data:
                if data.get("kind") not in FEED_KINDS:
                    return jsonify({"ok": False, "error": "Choose Auto, Article, Video or Audio."}), 400

                feed["kind"] = data["kind"]

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

    def page_arguments():
        def number(name, default, low, high):
            try:
                return max(low, min(high, int(request.args.get(name, default))))
            except (TypeError, ValueError):
                return default

        needle = _SPACE.sub(" ", request.args.get("q", "")[:QUERY_MAX]).strip().lower()

        return number("limit", PAGE_DEFAULT, 1, PAGE_MAX), number("offset", 0, 0, 100000), needle

    def page(feeds, mine, limit, offset, needle):
        """One page of the signed-in user's stream, with the counts the card shows."""
        hidden = set(mine["hidden"])
        stream = with_saved(build_items(feeds, skip=hidden), mine["saved"])

        if needle:
            stream = [
                item for item in stream
                if needle in f'{item["title"]} {item["feed"]} {item["folder"]}'.lower()
            ]

        return {
            "ok": True,
            "items": stream[offset:offset + limit],
            "has_more": offset + limit < len(stream),
            "hidden_count": len(build_items(feeds, only=hidden)),
            "saved_count": len(mine["saved"]),
            "folders": user_state.folder_names(mine["saved"]),
        }

    def refresh_quietly():
        # One refresh at a time, however many page loads ask for one.
        if not _REFRESHING.acquire(blocking=False):
            return

        try:
            refresh_stale([feed for feed in _read(path) if feed["enabled"]])
        finally:
            _REFRESHING.release()

    def bootstrap():
        """The first page for the Home HTML, from the cache only: it never waits on a feed.

        Whatever is cached is used, stale or not, and a stale feed is refreshed in the
        background. {"ready": False} means a feed has never been fetched, so the browser
        asks for the page itself.
        """
        feeds = [feed for feed in _read(path) if feed["enabled"]]

        if any(_stale(feed) for feed in feeds):
            Thread(target=refresh_quietly, name="rss-refresh", daemon=True).start()

        if any(feed["url"] not in _CACHE for feed in feeds):
            return {"ready": False}

        warm_icons(feeds)

        return {"ready": True, **page(feeds, state.view(current_user()), PAGE_DEFAULT, 0, "")}

    app.extensions["kotibot_rss_bootstrap"] = bootstrap

    if context.get("prefetch") and not _PREFETCH["started"]:
        # Keep the cache warm, so the first page after a restart or a quiet hour
        # already has news and the Home HTML never has to wait for it.
        _PREFETCH["started"] = True

        def keep_warm():
            while True:
                try:
                    refresh_quietly()
                except Exception:
                    LOGGER.exception("RSS background refresh failed")

                time.sleep(PREFETCH_SECONDS)

        Thread(target=keep_warm, name="rss-prefetch", daemon=True).start()

    @app.route("/api/rss/items", methods=["GET"])
    def api_rss_items():
        feeds = [feed for feed in _read(path) if feed["enabled"]]
        refresh_stale(feeds)
        warm_icons(feeds)
        mine = state.view(current_user())

        if request.args.get("view") == "hidden":
            hidden_items = with_saved(build_items(feeds, only=set(mine["hidden"])), mine["saved"])

            return no_store({"ok": True, "items": hidden_items})

        return no_store(page(feeds, mine, *page_arguments()))

    def state_reply(action):
        try:
            action()
        except user_state.StateError as problem:
            return jsonify({"ok": False, "error": str(problem)}), 400
        except LookupError as problem:
            return jsonify({"ok": False, "error": str(problem)}), 404

        return jsonify({"ok": True})

    @app.route("/api/rss/items/<item_id>/hide", methods=["POST"])
    def api_rss_item_hide(item_id):
        return state_reply(lambda: state.hide(current_user(), item_id))

    @app.route("/api/rss/items/<item_id>/unhide", methods=["POST"])
    def api_rss_item_unhide(item_id):
        return state_reply(lambda: state.unhide(current_user(), item_id))

    @app.route("/api/rss/saved", methods=["GET"])
    def api_rss_saved():
        mine = state.view(current_user())

        return no_store({"ok": True, "items": mine["saved"], "folders": user_state.folder_names(mine["saved"])})

    @app.route("/api/rss/saved/<item_id>", methods=["POST"])
    def api_rss_saved_add(item_id):
        data = request.get_json(silent=True) or {}
        found = next((
            {**item, "id": item_id, "feed": feed["title"]}
            for feed in _read(path) if feed["enabled"]
            for item in _CACHE.get(feed["url"], {}).get("items", [])
            if re.fullmatch(r"[0-9a-f]{16}", item_id) and item_ident(item) == item_id
        ), None)

        if found is None:
            return jsonify({"ok": False, "error": "That article is no longer in the feed."}), 404

        return state_reply(lambda: state.save(current_user(), found, data.get("folder")))

    @app.route("/api/rss/saved/<item_id>/remove", methods=["POST"])
    def api_rss_saved_remove(item_id):
        return state_reply(lambda: state.unsave(current_user(), item_id))

    @app.route("/api/rss/icon/<host>", methods=["GET"])
    def api_rss_icon(host):
        host = host.lower()
        known = {
            host_of(item["link"])
            for feed in _read(path) if feed["enabled"]
            for item in _CACHE.get(feed["url"], {}).get("items", [])
        }

        if host not in known:
            abort(404)

        hit, found = _icon_cached(host)

        if not hit:
            found = None
            job = icon_job(host)

            # Wait briefly for a cold site, but never tie up more than ICON_WAITERS
            # server threads; the page shows a placeholder and asks again later.
            if job is not None and _ICON_WAITING.acquire(blocking=False):
                try:
                    found = job.result(timeout=ICON_WAIT_SECONDS)
                except Exception:
                    found = None
                finally:
                    _ICON_WAITING.release()

        if not found:
            response = Response(status=404)
            response.headers["Cache-Control"] = "no-store"

            return response

        response = Response(found[0], mimetype=found[1])
        response.headers["Cache-Control"] = "private, max-age=86400"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Content-Security-Policy"] = "default-src 'none'; sandbox"

        return response

"""Paperless-ngx "Documents" card for the dashboard Home page.

Each KotiBot user sees only their own documents. KotiBot holds one Paperless API
token per signed-in user (a protected credential, never in the browser, the repo
or the log) and calls Paperless as that user, so Paperless itself decides what
each person may see. A user with no token gets no card; there is no fallback to
anyone else's token.

The card is off unless ``KOTIBOT_PAPERLESS_URL`` is set. Every failure yields an
"unavailable" answer; no failure detail, URL or token reaches the browser or the
log.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
from threading import Lock, Thread
from urllib import error as urlerror
from urllib import parse as urlparse
from urllib import request as urlrequest

from flask import jsonify, request

from server_core.credentials import CredentialMissingError, read_text_credential
from subsystems.media.jellyfin_shelf import normalize_base_url


LOGGER = logging.getLogger(__name__)

URL_ENVIRONMENT = "KOTIBOT_PAPERLESS_URL"
PUBLIC_URL_ENVIRONMENT = "KOTIBOT_PAPERLESS_PUBLIC_URL"
FAVORITE_TAG_ENVIRONMENT = "KOTIBOT_PAPERLESS_FAVORITE_TAG"
TOKENS_CREDENTIAL = "paperless-tokens"

DEFAULT_FAVORITE_TAG = "Favorite"
TABS = ("added", "edited", "favs")
ORDERING = {"added": "-added", "edited": "-modified", "favs": "-modified"}
PAGE_DEFAULT = 10
PAGE_MAX = 50
QUERY_MAX = 100
TITLE_MAX = 200
CACHE_SECONDS = 30
STALE_SECONDS = 6 * 60 * 60
NAMES_SECONDS = 5 * 60
TIMEOUT_SECONDS = 6
MAX_JSON_BYTES = 2 * 1024 * 1024
MAX_CACHE_ENTRIES = 64

_TOKEN = re.compile(r"[0-9A-Za-z]{16,128}")
_SPACE = re.compile(r"\s+")


class Unavailable(Exception):
    """A Paperless request failed. Carries only a short reason code."""

    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


class _NoRedirect(urlrequest.HTTPRedirectHandler):
    """Never follow a redirect, so a token cannot be sent elsewhere."""

    def redirect_request(self, *args, **kwargs):
        return None


def _text(value, limit):
    return _SPACE.sub(" ", str(value or "")).strip()[:limit]


def parse_tokens(raw):
    """{"email": "token"} from the credential text; bad entries are dropped."""
    try:
        data = json.loads(raw or "{}")
    except ValueError:
        return {}

    if not isinstance(data, dict):
        return {}

    tokens = {}

    for email, token in data.items():
        key = str(email or "").strip().lower()

        if key and isinstance(token, str) and _TOKEN.fullmatch(token.strip()):
            tokens[key] = token.strip()

    return tokens


def _http_get(base_url, path, token):
    """GET one Paperless JSON page as the token's user."""
    req = urlrequest.Request(
        base_url + path,
        headers={"Authorization": f"Token {token}", "Accept": "application/json"},
    )
    opener = urlrequest.build_opener(_NoRedirect)

    try:
        with opener.open(req, timeout=TIMEOUT_SECONDS) as response:
            body = response.read(MAX_JSON_BYTES + 1)
    except urlerror.HTTPError as problem:
        raise Unavailable(f"http_{problem.code}") from None
    except (urlerror.URLError, OSError, ValueError):
        raise Unavailable("network") from None

    if len(body) > MAX_JSON_BYTES:
        raise Unavailable("too_large")

    try:
        data = json.loads(body)
    except ValueError:
        raise Unavailable("bad_json") from None

    if not isinstance(data, dict):
        raise Unavailable("bad_json")

    return data


class PaperlessShelf:
    def __init__(self, base_url, *, tokens=None, fetch=None, favorite_tag=DEFAULT_FAVORITE_TAG, link_base=""):
        self.base_url = base_url
        self.link_base = link_base
        self.favorite_tag = favorite_tag
        self._tokens = tokens
        self._fetch = fetch or (lambda path, token: _http_get(self.base_url, path, token))
        self._lock = Lock()
        self._pages = {}
        self._names = {}
        self._warming = set()

    @property
    def enabled(self):
        return bool(self.base_url)

    def token_for(self, email):
        key = str(email or "").strip().lower()

        if not key or not self.enabled:
            return ""

        if self._tokens is not None:
            return self._tokens().get(key, "")

        try:
            return parse_tokens(read_text_credential(TOKENS_CREDENTIAL)).get(key, "")
        except (CredentialMissingError, RuntimeError):
            return ""

    # -- Paperless calls ---------------------------------------------------

    def _lookup(self, token, name, path):
        """{id: name} for correspondents or document types, cached per user."""
        slot = (hashlib.sha256(token.encode()).hexdigest(), name)
        now = time.monotonic()

        with self._lock:
            hit = self._names.get(slot)

        if hit and now - hit[0] < NAMES_SECONDS:
            return hit[1]

        try:
            data = self._fetch(f"{path}?page_size=1000&fields=id,name", token)
        except Unavailable:
            return hit[1] if hit else {}

        found = {
            row["id"]: _text(row.get("name"), 80)
            for row in data.get("results", [])
            if isinstance(row, dict) and isinstance(row.get("id"), int)
        }

        with self._lock:
            self._names[slot] = (now, found)

        return found

    def _favorite_id(self, token):
        slot = (hashlib.sha256(token.encode()).hexdigest(), "favorite")
        now = time.monotonic()

        with self._lock:
            hit = self._names.get(slot)

        if hit and now - hit[0] < NAMES_SECONDS:
            return hit[1]

        query = urlparse.urlencode({"name__iexact": self.favorite_tag, "page_size": 1, "fields": "id"})
        data = self._fetch(f"/api/tags/?{query}", token)
        rows = [row for row in data.get("results", []) if isinstance(row, dict) and isinstance(row.get("id"), int)]
        found = rows[0]["id"] if rows else 0

        with self._lock:
            self._names[slot] = (now, found)

        return found

    def _fresh(self, token, tab, needle, limit, offset):
        favorite = self._favorite_id(token)
        arguments = {
            "ordering": ORDERING[tab],
            "page_size": limit,
            "page": offset // limit + 1,
            "fields": "id,title,correspondent,document_type,added,modified,tags",
        }

        if needle:
            arguments["title_content"] = needle

        if tab == "favs":
            if not favorite:
                return {"items": [], "has_more": False}

            arguments["tags__id__all"] = favorite

        data = self._fetch("/api/documents/?" + urlparse.urlencode(arguments), token)
        people = self._lookup(token, "correspondents", "/api/correspondents/")
        kinds = self._lookup(token, "types", "/api/document_types/")
        items = []

        for row in data.get("results", []):
            if not isinstance(row, dict) or not isinstance(row.get("id"), int):
                continue

            tags = row.get("tags") if isinstance(row.get("tags"), list) else []
            items.append({
                "id": row["id"],
                "title": _text(row.get("title"), TITLE_MAX) or f"Document {row['id']}",
                "correspondent": people.get(row.get("correspondent"), ""),
                "type": kinds.get(row.get("document_type"), ""),
                "added": _text(row.get("added"), 40),
                "modified": _text(row.get("modified"), 40),
                "favorite": bool(favorite) and favorite in tags,
            })

        return {"items": items, "has_more": bool(data.get("next"))}

    def _inbox(self, token):
        query = urlparse.urlencode({"is_in_inbox": "true", "page_size": 1, "fields": "id"})
        count = self._fetch(f"/api/documents/?{query}", token).get("count")

        return count if isinstance(count, int) and count >= 0 else 0

    # -- public ------------------------------------------------------------

    def documents(self, email, tab="added", query="", offset=0, limit=PAGE_DEFAULT):
        token = self.token_for(email)

        if not token:
            return {"ok": True, "available": False}

        tab = tab if tab in TABS else "added"
        limit = max(1, min(PAGE_MAX, int(limit)))
        offset = max(0, int(offset)) // limit * limit
        needle = _text(query, QUERY_MAX).lower()
        key = (hashlib.sha256(token.encode()).hexdigest(), tab, needle, limit, offset)
        now = time.monotonic()

        with self._lock:
            hit = self._pages.get(key)

        if hit and now - hit[0] < CACHE_SECONDS:
            return hit[1]

        try:
            payload = {"ok": True, "available": True, "tab": tab, **self._fresh(token, tab, needle, limit, offset)}
            payload["inbox_count"] = self._inbox(token)
            payload["link_base"] = self.link_base
        except Unavailable as problem:
            LOGGER.warning("Paperless request failed: %s", problem.reason)

            return hit[1] if hit else {"ok": True, "available": False, "reason": "unavailable"}

        with self._lock:
            if len(self._pages) >= MAX_CACHE_ENTRIES:
                self._pages.pop(next(iter(self._pages)))

            self._pages[key] = (now, payload)

        return payload

    def bootstrap(self, email):
        """The first page for the Home HTML, from the cache only; never waits on Paperless.

        Stale data is served as is and refreshed in the background. {"ready": False}
        means this user's first page has not been fetched yet.
        """
        token = self.token_for(email)

        if not token:
            return {"ready": True, "available": False}

        key = (hashlib.sha256(token.encode()).hexdigest(), "added", "", PAGE_DEFAULT, 0)

        with self._lock:
            hit = self._pages.get(key)
            running = key in self._warming

            if not running and (not hit or time.monotonic() - hit[0] >= CACHE_SECONDS):
                self._warming.add(key)
                Thread(target=self._warm, args=(email, key), name="paperless-warm", daemon=True).start()

        if hit and time.monotonic() - hit[0] < STALE_SECONDS:
            return {"ready": True, **hit[1]}

        return {"ready": False}

    def _warm(self, email, key):
        try:
            self.documents(email, "added", "", 0, PAGE_DEFAULT)
        except Exception:
            LOGGER.exception("Paperless warm-up failed")
        finally:
            with self._lock:
                self._warming.discard(key)


def register_paperless_routes(app, context=None):
    context = context or {}
    security = context.get("security")
    base_url = normalize_base_url(os.environ.get(URL_ENVIRONMENT, ""))

    if os.environ.get(URL_ENVIRONMENT, "").strip() and not base_url:
        LOGGER.warning("%s is not a plain http(s) address; the Documents card is off", URL_ENVIRONMENT)

    shelf = context.get("shelf") or PaperlessShelf(
        base_url,
        favorite_tag=os.environ.get(FAVORITE_TAG_ENVIRONMENT, "").strip() or DEFAULT_FAVORITE_TAG,
        link_base=normalize_base_url(os.environ.get(PUBLIC_URL_ENVIRONMENT, "")),
    )
    app.config["KOTIBOT_PAPERLESS_SHELF"] = shelf

    def current_email():
        return security.dashboard_session_email() if security else ""

    def number(name, default):
        try:
            return int(request.args.get(name, default))
        except (TypeError, ValueError):
            return default

    @app.route("/api/shelves/paperless/documents", methods=["GET"])
    def api_paperless_documents():
        payload = shelf.documents(
            current_email(),
            request.args.get("tab", "added"),
            request.args.get("q", ""),
            number("offset", 0),
            number("limit", PAGE_DEFAULT),
        )
        response = jsonify(payload)
        response.headers["Cache-Control"] = "no-store"

        return response

    app.extensions["kotibot_paperless_bootstrap"] = lambda: shelf.bootstrap(current_email())

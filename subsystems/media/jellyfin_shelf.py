"""Jellyfin "Continue watching" shelf for the dashboard Home page.

KotiBot signs in to Jellyfin as one non-administrator account, reads that
account's resume list, and proxies the poster images, so the browser never
holds a Jellyfin token and every request stays behind the dashboard login.

The shelf is off unless ``KOTIBOT_JELLYFIN_URL`` is set. The account name and
password come from protected credential files, never from the environment.
Every failure yields an "unavailable" answer; no failure detail, URL or
credential reaches the browser or the log.
"""

from __future__ import annotations

from collections import OrderedDict
import json
import logging
import os
import re
import time
from threading import Lock
from urllib import error as urlerror
from urllib import parse as urlparse
from urllib import request as urlrequest

from flask import Response, jsonify, request

from server_core.credentials import CredentialMissingError, read_text_credential


LOGGER = logging.getLogger(__name__)

URL_ENVIRONMENT = "KOTIBOT_JELLYFIN_URL"
USERNAME_CREDENTIAL = "jellyfin-username"
PASSWORD_CREDENTIAL = "jellyfin-password"

CACHE_SECONDS = 30
TIMEOUT_SECONDS = 6
ITEM_LIMIT = 12
OVERVIEW_MAX_CHARS = 400
IMAGE_MAX_WIDTH = 320
IMAGE_CACHE_ENTRIES = 24
MAX_JSON_BYTES = 2 * 1024 * 1024
MAX_IMAGE_BYTES = 2 * 1024 * 1024
TICKS_PER_MINUTE = 600_000_000

ALLOWED_IMAGE_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})
_ITEM_ID_RE = re.compile(r"^[0-9a-f]{32}$")
_TAG_RE = re.compile(r"^[0-9A-Za-z_-]{1,64}$")
_CLIENT = (
    'Client="KotiBot", Device="KotiBot", '
    'DeviceId="kotibot-dashboard-shelf", Version="1"'
)

IMAGE_ROUTE = "/api/shelves/jellyfin/image/"
PROGRESS_ROUTE = "/api/shelves/jellyfin/progress/"


class ShelfUnavailable(Exception):
    """A shelf request failed. Carries only a short reason code."""

    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


class _NoRedirect(urlrequest.HTTPRedirectHandler):
    """Never follow a redirect, so the token cannot be sent elsewhere."""

    def redirect_request(self, *args, **kwargs):
        return None


def normalize_base_url(value):
    """Return ``scheme://host[:port]`` for a valid configured URL, else ''."""
    text = str(value or "").strip()

    if not text:
        return ""

    try:
        parsed = urlparse.urlsplit(text)
        port = parsed.port
    except ValueError:
        return ""

    if (
        parsed.scheme not in ("http", "https")
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
    ):
        return ""

    host = parsed.hostname

    if ":" in host:
        host = f"[{host}]"

    return f"{parsed.scheme}://{host}" + (f":{port}" if port else "")


def clean_item_id(value):
    text = str(value or "").replace("-", "").lower()
    return text if _ITEM_ID_RE.match(text) else ""


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None

    return value


def map_resume_item(raw):
    """Reduce one Jellyfin item to the few fields the shelf shows."""
    if not isinstance(raw, dict):
        return None

    kind = str(raw.get("Type") or "")
    item_id = clean_item_id(raw.get("Id"))
    name = str(raw.get("Name") or "").strip()

    if not item_id or not name:
        return None

    release_year = None

    if kind == "Episode":
        image_id = clean_item_id(raw.get("SeriesId"))
        image_tag = str(raw.get("SeriesPrimaryImageTag") or "")
        title = str(raw.get("SeriesName") or "").strip() or name
        season = raw.get("ParentIndexNumber")
        episode = raw.get("IndexNumber")
        marker = (
            f"S{int(season)}E{int(episode)}"
            if _number(season) is not None and _number(episode) is not None
            else ""
        )
        subtitle = " · ".join(part for part in (marker, name) if part)
    else:
        image_id = item_id
        tags = raw.get("ImageTags")
        image_tag = str(
            tags.get("Primary") if isinstance(tags, dict) else ""
        )
        title = name
        year = _number(raw.get("ProductionYear"))
        subtitle = str(int(year)) if year else ""
        release_year = int(year) if year else None

    data = raw.get("UserData")
    data = data if isinstance(data, dict) else {}
    total = _number(raw.get("RunTimeTicks"))
    position = _number(data.get("PlaybackPositionTicks"))
    percent = _number(data.get("PlayedPercentage"))

    if percent is None and total and position is not None:
        percent = position / total * 100

    percent = max(0, min(100, int(round(percent or 0))))
    minutes_left = None
    runtime_minutes = int(total // TICKS_PER_MINUTE) if total else None

    if total and position is not None and total > position:
        minutes_left = int((total - position) // TICKS_PER_MINUTE)

    image_url = ""

    if image_id and _TAG_RE.match(image_tag):
        image_url = (
            f"{IMAGE_ROUTE}{image_id}?"
            + urlparse.urlencode({"tag": image_tag})
        )

    return {
        "id": item_id,
        "title": title,
        "subtitle": subtitle,
        "year": release_year,
        "overview": str(raw.get("Overview") or "").strip()[:OVERVIEW_MAX_CHARS],
        "percent": percent,
        "minutes_left": minutes_left,
        "runtime_minutes": runtime_minutes,
        "image": image_url,
    }


class JellyfinShelf:
    def __init__(
        self,
        base_url,
        *,
        read_credentials=None,
        clock=time.monotonic,
        opener=None,
    ):
        self.base_url = normalize_base_url(base_url)
        self._read_credentials = read_credentials or _read_account
        self._clock = clock
        self._opener = opener or urlrequest.build_opener(_NoRedirect)
        self._state_lock = Lock()
        self._refresh_lock = Lock()
        self._token = ""
        self._user_id = ""
        self._cache = None
        self._cache_at = 0.0
        self._images = OrderedDict()
        self._last_reason = ""

    # -- Jellyfin transport -------------------------------------------------

    def _request(self, method, path, *, body=None, token="", max_bytes):
        authorization = f"MediaBrowser {_CLIENT}"

        if token:
            authorization += f', Token="{token}"'

        headers = {
            "Authorization": authorization,
            "Accept": "application/json, image/*",
            "User-Agent": "KotiBot/1.0",
        }
        data = None

        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"

        request = urlrequest.Request(
            self.base_url + path,
            data=data,
            headers=headers,
            method=method,
        )

        try:
            with self._opener.open(request, timeout=TIMEOUT_SECONDS) as response:
                payload = response.read(max_bytes + 1)
                content_type = str(
                    response.headers.get("Content-Type") or ""
                ).split(";")[0].strip().lower()
        except urlerror.HTTPError as exc:
            exc.close()
            reason = "unauthorized" if exc.code == 401 else "unavailable"
            raise ShelfUnavailable(reason) from None
        except (urlerror.URLError, OSError, ValueError):
            raise ShelfUnavailable("unavailable") from None

        if len(payload) > max_bytes:
            raise ShelfUnavailable("unavailable")

        return payload, content_type

    def _authenticate(self):
        try:
            username = self._read_credentials(USERNAME_CREDENTIAL)
            password = self._read_credentials(PASSWORD_CREDENTIAL)
        except (CredentialMissingError, RuntimeError):
            raise ShelfUnavailable("credentials_missing") from None

        if not username or not password:
            raise ShelfUnavailable("credentials_missing")

        payload, _ = self._request(
            "POST",
            "/Users/AuthenticateByName",
            body={"Username": username, "Pw": password},
            max_bytes=MAX_JSON_BYTES,
        )

        try:
            document = json.loads(payload.decode("utf-8"))
            token = str(document["AccessToken"])
            user_id = clean_item_id(document["User"]["Id"])
        except (ValueError, KeyError, TypeError, AttributeError):
            raise ShelfUnavailable("unavailable") from None

        if not token or not user_id:
            raise ShelfUnavailable("unavailable")

        with self._state_lock:
            self._token = token
            self._user_id = user_id

    def _session(self):
        with self._state_lock:
            return self._token, self._user_id

    def _authorized_get(self, build_path, max_bytes):
        """GET with the session token, signing in once more on a 401."""
        return self._authorized("GET", build_path, max_bytes)

    def _authorized(self, method, build_path, max_bytes, body=None):
        for attempt in (0, 1):
            token, user_id = self._session()

            if not token:
                self._authenticate()
                token, user_id = self._session()

            try:
                return self._request(
                    method,
                    build_path(user_id),
                    body=body,
                    token=token,
                    max_bytes=max_bytes,
                )
            except ShelfUnavailable as exc:
                if exc.reason != "unauthorized" or attempt:
                    raise

                with self._state_lock:
                    self._token = ""
                    self._user_id = ""

        raise ShelfUnavailable("unavailable")

    # -- shelf --------------------------------------------------------------

    def _fresh_cache(self):
        with self._state_lock:
            if (
                self._cache is not None
                and self._clock() - self._cache_at < CACHE_SECONDS
            ):
                return self._cache

        return None

    def _fetch_resume(self):
        query = urlparse.urlencode({
            "Limit": ITEM_LIMIT,
            "MediaTypes": "Video",
            "Fields": "ProductionYear,Overview",
            "EnableTotalRecordCount": "false",
        })
        payload, _ = self._authorized_get(
            lambda user_id: f"/Users/{user_id}/Items/Resume?{query}",
            MAX_JSON_BYTES,
        )

        try:
            items = json.loads(payload.decode("utf-8")).get("Items")
        except (ValueError, AttributeError):
            raise ShelfUnavailable("unavailable") from None

        if not isinstance(items, list):
            raise ShelfUnavailable("unavailable")

        mapped = [map_resume_item(item) for item in items]
        return {"available": True, "items": [m for m in mapped if m]}

    def _note_reason(self, reason):
        # Log only transitions, never details.
        if reason == self._last_reason:
            return

        self._last_reason = reason

        if reason:
            LOGGER.warning("Jellyfin shelf unavailable: %s", reason)
        else:
            LOGGER.info("Jellyfin shelf available again")

    def continue_watching(self):
        if not self.base_url:
            return {"available": False, "reason": "not_configured", "items": []}

        cached = self._fresh_cache()

        if cached is not None:
            return cached

        with self._refresh_lock:
            cached = self._fresh_cache()

            if cached is not None:
                return cached

            try:
                result = self._fetch_resume()
                self._note_reason("")
            except ShelfUnavailable as exc:
                result = {
                    "available": False,
                    "reason": exc.reason,
                    "items": [],
                }
                self._note_reason(exc.reason)

            with self._state_lock:
                self._cache = result
                self._cache_at = self._clock()

            return result

    def reset_progress(self, item_id):
        """Set one resume-list title back to the start (position 0).

        Jellyfin drops a title with no position from Continue watching, so
        this is both Restart and Remove. Only titles that are in the current
        resume list can be changed, and only this account's own watch data is
        written. Returns "ok", "not_found" or "unavailable".
        """
        item_id = clean_item_id(item_id)

        if not self.base_url or not item_id:
            return "not_found"

        shelf = self.continue_watching()

        if not shelf.get("available"):
            return "unavailable"

        if item_id not in {item["id"] for item in shelf["items"]}:
            return "not_found"

        try:
            self._authorized(
                "POST",
                lambda user_id: (
                    f"/UserItems/{item_id}/UserData?"
                    + urlparse.urlencode({"userId": user_id})
                ),
                MAX_JSON_BYTES,
                body={"PlaybackPositionTicks": 0},
            )
        except ShelfUnavailable:
            return "unavailable"

        with self._state_lock:
            self._cache = None

        return "ok"

    def image(self, item_id, tag):
        """Return ``(bytes, content_type)`` for one poster, or None."""
        item_id = clean_item_id(item_id)
        tag = str(tag or "")

        if not self.base_url or not item_id or not _TAG_RE.match(tag):
            return None

        key = (item_id, tag)

        with self._state_lock:
            hit = self._images.get(key)

            if hit is not None:
                self._images.move_to_end(key)
                return hit

        query = urlparse.urlencode({
            "maxWidth": IMAGE_MAX_WIDTH,
            "quality": 80,
            "tag": tag,
        })

        try:
            payload, content_type = self._authorized_get(
                lambda _user_id: f"/Items/{item_id}/Images/Primary?{query}",
                MAX_IMAGE_BYTES,
            )
        except ShelfUnavailable:
            return None

        if content_type not in ALLOWED_IMAGE_TYPES or not payload:
            return None

        with self._state_lock:
            self._images[key] = (payload, content_type)
            self._images.move_to_end(key)

            while len(self._images) > IMAGE_CACHE_ENTRIES:
                self._images.popitem(last=False)

        return payload, content_type


def _read_account(credential_name):
    return read_text_credential(credential_name, required=True)


def register_jellyfin_shelf_routes(app, context=None):
    context = context or {}
    base_url = normalize_base_url(os.environ.get(URL_ENVIRONMENT, ""))

    if os.environ.get(URL_ENVIRONMENT, "").strip() and not base_url:
        LOGGER.warning(
            "%s is not a plain http(s) address; the Jellyfin shelf is off",
            URL_ENVIRONMENT,
        )

    shelf = context.get("shelf") or JellyfinShelf(base_url)
    app.config["KOTIBOT_JELLYFIN_SHELF"] = shelf

    @app.route("/api/shelves/jellyfin/continue", methods=["GET"])
    def api_jellyfin_continue():
        return jsonify(shelf.continue_watching())

    @app.route(PROGRESS_ROUTE + "<item_id>/reset", methods=["POST"])
    def api_jellyfin_progress_reset(item_id):
        outcome = shelf.reset_progress(item_id)

        if outcome == "ok":
            return jsonify({"ok": True})

        if outcome == "not_found":
            return jsonify({"ok": False, "error": "not_found"}), 404

        return jsonify({"ok": False, "error": "unavailable"}), 502

    @app.route(IMAGE_ROUTE + "<item_id>", methods=["GET"])
    def api_jellyfin_image(item_id):
        found = shelf.image(item_id, request.args.get("tag", ""))

        if found is None:
            return jsonify({"ok": False, "error": "not_found"}), 404

        payload, content_type = found
        return Response(payload, mimetype=content_type)

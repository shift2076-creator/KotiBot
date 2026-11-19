"""Per-user state for the Home News card: hidden articles and saved folders.

Each signed-in dashboard user has their own hidden list and saved folders. The
user is keyed by a salted hash of the dashboard email, so the file carries no
addresses. Sessions without an email (a paired Control device) share one
"dashboard" bucket, the same fallback the Admin inbox uses.

Everything read back from disk is revalidated, every list is bounded, and a saved
article is always copied from KotiBot's own feed cache, never from request text,
so a caller cannot store a title or link a feed did not publish.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from threading import Lock

MAX_HIDDEN = 500
MAX_SAVED = 200
MAX_FOLDERS = 20
MAX_FOLDER_NAME = 40
MAX_USERS = 64
DEFAULT_FOLDER = "Read later"
SHARED_USER = "dashboard"

_LOCK = Lock()
_ID = re.compile(r"[0-9a-f]{16}")
_USER = re.compile(r"[0-9a-f]{16}")
_SPACE = re.compile(r"\s+")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_KINDS = ("article", "video", "audio")


class StateError(Exception):
    """A change was refused. The text is safe to show the user."""


def user_key(email):
    """A stable, non-reversible bucket name for a dashboard email."""
    text = str(email or "").strip().lower()

    if not text:
        return SHARED_USER

    return hashlib.sha256(("kotibot-rss-user:" + text).encode("utf-8")).hexdigest()[:16]


def item_id(link, title_key):
    """The id of a feed item: its link, or its normalised title when it has none."""
    return hashlib.sha256((link or title_key).encode("utf-8")).hexdigest()[:16]


def clean_folder(value):
    name = _SPACE.sub(" ", _CONTROL.sub(" ", str(value or ""))).strip()

    if not name:
        raise StateError("Give the folder a name.")

    return name[:MAX_FOLDER_NAME].rstrip()


def _text(value, limit):
    text = _SPACE.sub(" ", _CONTROL.sub(" ", str(value or ""))).strip()

    return text[:limit]


def _link(value):
    text = str(value or "").strip()

    return text if re.match(r"https?://", text, re.IGNORECASE) and len(text) <= 500 else ""


def _clean_saved(row):
    if not isinstance(row, dict) or not _ID.fullmatch(str(row.get("id") or "")):
        return None

    title = _text(row.get("title"), 160)

    if not title:
        return None

    try:
        folder = clean_folder(row.get("folder") or DEFAULT_FOLDER)
    except StateError:
        return None

    return {
        "id": row["id"],
        "title": title,
        "link": _link(row.get("link")),
        "feed": _text(row.get("feed"), 60),
        "kind": row.get("kind") if row.get("kind") in _KINDS else "article",
        "folder": folder,
        "saved_at": _text(row.get("saved_at"), 40),
    }


def _empty():
    return {"hidden": [], "saved": []}


def _read(path):
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}

    users = value.get("users") if isinstance(value, dict) else None
    clean = {}

    for key, record in (users.items() if isinstance(users, dict) else []):
        if key != SHARED_USER and not _USER.fullmatch(str(key)) or not isinstance(record, dict):
            continue

        hidden = []

        for entry in record.get("hidden") if isinstance(record.get("hidden"), list) else []:
            if isinstance(entry, str) and _ID.fullmatch(entry) and entry not in hidden:
                hidden.append(entry)

        saved = []

        for row in record.get("saved") if isinstance(record.get("saved"), list) else []:
            made = _clean_saved(row)

            if made and all(other["id"] != made["id"] for other in saved):
                saved.append(made)

        clean[key] = {"hidden": hidden[-MAX_HIDDEN:], "saved": saved[:MAX_SAVED]}

    return dict(list(clean.items())[:MAX_USERS])


def _write(path, users):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    handle, name = tempfile.mkstemp(dir=target.parent, prefix=".user-state-")

    try:
        with os.fdopen(handle, "w", encoding="utf-8") as out:
            json.dump({"users": users}, out, indent=2)
            out.write("\n")

        os.replace(name, target)
    except BaseException:
        try:
            os.unlink(name)
        except OSError:
            pass

        raise


class UserState:
    """Reads and changes one state file. Every change is one locked read-modify-write."""

    def __init__(self, path):
        self.path = Path(path)

    def _change(self, user, apply):
        with _LOCK:
            users = _read(self.path)
            record = users.setdefault(user, _empty())
            result = apply(record)

            if len(users) > MAX_USERS:
                raise StateError("Too many users are stored.")

            _write(self.path, users)

            return result

    def view(self, user):
        """A copy of the user's record (empty when they have none)."""
        with _LOCK:
            record = _read(self.path).get(user) or _empty()

        return {"hidden": list(record["hidden"]), "saved": [dict(row) for row in record["saved"]]}

    def hide(self, user, ident):
        self._require_id(ident)

        def apply(record):
            if ident not in record["hidden"]:
                record["hidden"].append(ident)
                del record["hidden"][:-MAX_HIDDEN]

        self._change(user, apply)

    def unhide(self, user, ident):
        self._require_id(ident)

        def apply(record):
            if ident in record["hidden"]:
                record["hidden"].remove(ident)

        self._change(user, apply)

    def save(self, user, item, folder):
        """Save a feed item (taken from the cache) into a folder, moving it if already saved."""
        name = clean_folder(folder)
        self._require_id(item.get("id"))

        def apply(record):
            others = [row for row in record["saved"] if row["id"] != item["id"]]
            folders = {row["folder"] for row in others}

            if name not in folders and name != DEFAULT_FOLDER and len(folders - {DEFAULT_FOLDER}) >= MAX_FOLDERS:
                raise StateError(f"You can have up to {MAX_FOLDERS} folders.")

            if len(others) >= MAX_SAVED:
                raise StateError(f"You can save up to {MAX_SAVED} articles.")

            made = _clean_saved({
                "id": item["id"], "title": item.get("title"), "link": item.get("link"),
                "feed": item.get("feed"), "kind": item.get("kind"), "folder": name,
                "saved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            })

            if not made:
                raise StateError("That article cannot be saved.")

            record["saved"] = [made] + others

        self._change(user, apply)

    def unsave(self, user, ident):
        self._require_id(ident)
        found = []

        def apply(record):
            kept = [row for row in record["saved"] if row["id"] != ident]
            found.append(len(kept) != len(record["saved"]))
            record["saved"] = kept

        self._change(user, apply)

        if not found[0]:
            raise LookupError("That article is not saved.")

    @staticmethod
    def _require_id(ident):
        if not _ID.fullmatch(str(ident or "")):
            raise LookupError("That article is not in the feed.")


def folder_names(saved):
    """Folder names for the picker: the default first, then the user's own, A to Z."""
    own = sorted({row["folder"] for row in saved} - {DEFAULT_FOLDER}, key=str.lower)

    return [DEFAULT_FOLDER] + own

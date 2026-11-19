"""Admin inbox: the PiVault notification store, ported from the portal.

Producers are unchanged: local services drop JSON files into
``<notification root>/inbox``; this module validates and ingests them, and
writes cinema approvals back to ``<root>/decisions``. Nothing in the portal
creates ``clients.update`` approvals any more (client downloads are
automatic), so that kind is not ported.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from . import store

LOGGER = logging.getLogger(__name__)
ROOT_ENVIRONMENT = "KOTIBOT_PIVAULT_NOTIFICATIONS"
IDENTIFIER = re.compile(r"^[a-f0-9]{64}$")
NAME = re.compile(r"^[a-zA-Z0-9_.-]{1,64}$")
LEVELS = ("info", "warning", "error")
CINEMA = "cinema.filesize"


class NotificationError(ValueError):
    pass


def now():
    return datetime.now(timezone.utc).isoformat()


def root():
    value = os.environ.get(ROOT_ENVIRONMENT, "").strip()
    return Path(value) if value else None


def validate_details(details):
    if not isinstance(details, dict):
        raise NotificationError("Notification details must be an object.")

    if not re.fullmatch(r"[a-z0-9-]{1,150}", str(details.get("movie_key", ""))):
        raise NotificationError("Invalid movie key.")

    parsed = urlsplit(str(details.get("source_url", "")))
    host = parsed.hostname or ""

    if (
        parsed.scheme != "https"
        or parsed.username
        or parsed.password
        or parsed.port not in (None, 443)
        or not (host == "archive.org" or host == "loc.gov" or host.endswith(".loc.gov"))
    ):
        raise NotificationError("Invalid movie source.")

    if not re.fullmatch(r"(?:[a-f0-9]{32}|-)", str(details.get("source_md5", ""))):
        raise NotificationError("Invalid source checksum.")

    for field in ("actual_bytes", "estimated_bytes", "maximum_bytes", "height"):
        if type(details.get(field)) is not int or details[field] <= 0:
            raise NotificationError("Invalid filesize details.")

    if type(details.get("minimum_bytes")) is not int or details["minimum_bytes"] < 0:
        raise NotificationError("Invalid minimum filesize.")

    if type(details.get("tolerance_percent")) is not int or not 0 < details["tolerance_percent"] < 100:
        raise NotificationError("Invalid tolerance.")

    minutes = details.get("reference_minutes")

    if isinstance(minutes, bool) or not isinstance(minutes, (int, float)) or not 0 < minutes <= 600:
        raise NotificationError("Invalid runtime.")


def _timestamp(value):
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        raise NotificationError("Invalid event timestamp.") from None

    if parsed.tzinfo is None:
        raise NotificationError("Invalid event timestamp.")

    return parsed.astimezone(timezone.utc).isoformat()


def _insert(connection, event_id, source, kind, level, title, message, details, created):
    connection.execute(
        "INSERT OR IGNORE INTO notifications "
        "(id, source, kind, level, title, message, details, created_at) VALUES (?,?,?,?,?,?,?,?)",
        (event_id, source, kind, level, title, message, json.dumps(details, sort_keys=True), created),
    )


def ingest(path=None):
    """Import outbox files. A file is removed only after its row is committed."""
    folder = root()
    inbox = folder / "inbox" if folder else None

    if inbox is None or not inbox.is_dir():
        return 0

    imported = 0

    for item in sorted(inbox.glob("*.json")):
        try:
            if item.is_symlink() or item.stat().st_size > 65536:
                continue

            data = json.loads(item.read_text())
            event_id = data["id"]

            if (
                not IDENTIFIER.fullmatch(event_id)
                or item.name != event_id + ".json"
                or data.get("version") != 1
            ):
                raise NotificationError("Invalid notification identity.")

            if not NAME.fullmatch(data["source"]) or not NAME.fullmatch(data["kind"]):
                raise NotificationError("Invalid notification source.")

            if data["level"] not in LEVELS:
                raise NotificationError("Invalid notification severity.")

            if not isinstance(data["title"], str) or not 0 < len(data["title"]) <= 200:
                raise NotificationError("Invalid notification title.")

            if not isinstance(data["message"], str) or len(data["message"]) > 8000:
                raise NotificationError("Invalid notification message.")

            details = data.get("details", {})

            if not isinstance(details, dict):
                raise NotificationError("Invalid notification details.")

            if data["kind"] == CINEMA:
                if data["source"] != "cinema":
                    raise NotificationError("Invalid cinema producer.")

                validate_details(details)
                fingerprint = hashlib.sha256(json.dumps(details, sort_keys=True).encode()).hexdigest()

                if fingerprint != event_id:
                    raise NotificationError("Movie event fingerprint does not match its source.")

            created = _timestamp(data.get("created_at", ""))

            with store.connect(path) as connection:
                _insert(connection, event_id, data["source"], data["kind"], data["level"],
                        data["title"], data["message"], details, created)

            item.unlink(missing_ok=True)
            imported += 1
        except (OSError, ValueError, KeyError, TypeError):
            LOGGER.warning("Could not import notification file %s", item.name)

    return imported


def notify(source, key, title, message, *, kind="service.notice", level="warning", path=None):
    """Record one incident; the key deduplicates repeats."""
    if not NAME.fullmatch(source) or not NAME.fullmatch(kind) or level not in LEVELS:
        raise NotificationError("Invalid notification producer or severity.")

    if not 0 < len(title) <= 200 or len(message) > 8000 or not 0 < len(key) <= 256:
        raise NotificationError("Invalid notification content.")

    if kind == CINEMA:
        raise NotificationError("Cinema review events must come from the outbox.")

    event_id = hashlib.sha256((source + ":" + kind + ":" + key).encode()).hexdigest()

    with store.connect(path) as connection:
        _insert(connection, event_id, source, kind, level, title, message, {}, now())

    return event_id


def _row(item):
    return {
        "id": item["id"],
        "source": item["source"],
        "kind": item["kind"],
        "level": item["level"],
        "title": item["title"],
        "message": item["message"],
        "created_at": item["created_at"],
        "status": item["status"],
        "resolution": item["resolution"],
        "pending_delivery": bool(item["resolution"]) and item["status"] == "open",
    }


def feed(user, path=None):
    ingest(path)
    publish_decisions(path)

    with store.connect(path) as connection:
        items = connection.execute(
            "SELECT * FROM notifications WHERE status='open' ORDER BY created_at DESC LIMIT 50"
        ).fetchall()
        unread = connection.execute(
            "SELECT COUNT(*) FROM notifications n WHERE n.status='open' AND NOT EXISTS "
            "(SELECT 1 FROM notification_receipts r WHERE r.notification_id=n.id AND r.user=?)",
            (user,),
        ).fetchone()[0]
        total = connection.execute("SELECT COUNT(*) FROM notifications WHERE status='open'").fetchone()[0]
        resolved = connection.execute(
            "SELECT * FROM notifications WHERE status='resolved' ORDER BY resolved_at DESC LIMIT 20"
        ).fetchall()

    return {
        "open_count": total,
        "unread_count": unread,
        "items": [_row(item) for item in items],
        "resolved": [_row(item) for item in resolved],
    }


def mark_seen(user, ids, path=None):
    if len(ids) > 100 or any(not IDENTIFIER.fullmatch(str(value)) for value in ids):
        raise NotificationError("Invalid notification list.")

    with store.connect(path) as connection:
        for value in ids:
            connection.execute(
                "INSERT OR IGNORE INTO notification_receipts (notification_id, user, seen_at) "
                "SELECT id, ?, ? FROM notifications WHERE id=?",
                (user, now(), value),
            )


def resolve(user, event_id, action, path=None):
    """Returns the new status. Cinema events take approve/skip; the rest take resolve."""
    if not IDENTIFIER.fullmatch(str(event_id)):
        raise NotificationError("Invalid notification.")

    with store.connect(path) as connection:
        item = connection.execute("SELECT * FROM notifications WHERE id=?", (event_id,)).fetchone()

        if item is None:
            raise LookupError("No such notification.")

        allowed = ("approve", "skip") if item["kind"] == CINEMA else ("resolve",)

        if action not in allowed:
            raise NotificationError("Invalid resolution.")

        if item["status"] == "resolved" or item["resolution"]:
            raise PermissionError("Another admin has already handled this notification.")

        resolved = item["kind"] != CINEMA
        connection.execute(
            "UPDATE notifications SET resolution=?, resolved_by=?, status=?, resolved_at=? WHERE id=?",
            (action, user, "resolved" if resolved else "open", now() if resolved else None, event_id),
        )
        connection.execute(
            "INSERT OR IGNORE INTO notification_receipts (notification_id, user, seen_at) VALUES (?,?,?)",
            (event_id, user, now()),
        )

    publish_decisions(path)

    with store.connect(path) as connection:
        return connection.execute("SELECT status FROM notifications WHERE id=?", (event_id,)).fetchone()[0]


def clear_failures(path=None):
    """Resolve open client and maintenance warnings; cinema approvals are left for review."""
    with store.connect(path) as connection:
        return connection.execute(
            "UPDATE notifications SET status='resolved', resolution='resolve', resolved_at=? "
            "WHERE source IN ('clients','maintenance') AND status='open' AND level='warning'",
            (now(),),
        ).rowcount


def resolve_matching(where, params=(), path=None):
    with store.connect(path) as connection:
        connection.execute(
            "UPDATE notifications SET status='resolved', resolution='resolve', resolved_at=? "
            "WHERE status='open' AND " + where,
            (now(), *params),
        )


def publish_decisions(path=None):
    """Write each approve/skip decision to the outbox; retry if the disk was unavailable."""
    folder = root()

    if folder is None:
        return

    with store.connect(path) as connection:
        events = connection.execute(
            "SELECT * FROM notifications WHERE kind=? AND status='open' AND resolution IN ('approve','skip')",
            (CINEMA,),
        ).fetchall()

    for event in events:
        temporary = None

        try:
            validate_details(json.loads(event["details"]))
            destination = folder / "decisions"
            destination.mkdir(mode=0o750, parents=True, exist_ok=True)
            descriptor, temporary = tempfile.mkstemp(prefix=".decision-", dir=destination)

            with os.fdopen(descriptor, "w") as stream:
                json.dump({"version": 1, "id": event["id"], "action": event["resolution"],
                           "admin_id": event["resolved_by"], "at": now()}, stream)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())

            os.replace(temporary, destination / (event["id"] + ".json"))
            temporary = None

            with store.connect(path) as connection:
                connection.execute(
                    "UPDATE notifications SET status='resolved', resolved_at=? "
                    "WHERE id=? AND status='open' AND resolution=?",
                    (now(), event["id"], event["resolution"]),
                )
        except (OSError, ValueError):
            LOGGER.warning("Notification decision is awaiting delivery: %s", event["id"])
        finally:
            if temporary and os.path.exists(temporary):
                os.unlink(temporary)

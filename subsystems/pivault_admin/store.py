"""SQLite store for the Admin inbox, client packages and Android devices.

These replace the PiVault portal's notification, client-release and device
tables. One small database file in KotiBot's own data folder; every call opens
its own short-lived connection, so threads (web requests and the nightly job)
never share one.
"""

from __future__ import annotations

import os
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path

ROOT_ENVIRONMENT = "KOTIBOT_PIVAULT_ADMIN_DIR"
SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS notifications (
    id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    kind TEXT NOT NULL,
    level TEXT NOT NULL,
    title TEXT NOT NULL,
    message TEXT NOT NULL,
    details TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    resolution TEXT NOT NULL DEFAULT '',
    resolved_by TEXT NOT NULL DEFAULT '',
    resolved_at TEXT
);
CREATE INDEX IF NOT EXISTS notifications_status ON notifications (status, created_at);
CREATE TABLE IF NOT EXISTS notification_receipts (
    notification_id TEXT NOT NULL REFERENCES notifications (id) ON DELETE CASCADE,
    user TEXT NOT NULL,
    seen_at TEXT NOT NULL,
    PRIMARY KEY (notification_id, user)
);
CREATE TABLE IF NOT EXISTS client_releases (
    id TEXT PRIMARY KEY,
    client TEXT NOT NULL,
    version TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    size INTEGER NOT NULL,
    url TEXT NOT NULL,
    release_url TEXT NOT NULL,
    discovered_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS client_packages (
    client TEXT PRIMARY KEY,
    current_id TEXT REFERENCES client_releases (id),
    previous_id TEXT REFERENCES client_releases (id),
    latest_id TEXT REFERENCES client_releases (id),
    checked_at TEXT,
    last_error TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS devices (
    id TEXT PRIMARY KEY,
    identity TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    model TEXT NOT NULL DEFAULT '',
    android_release TEXT NOT NULL DEFAULT '',
    first_seen TEXT NOT NULL,
    last_seen TEXT
);
CREATE TABLE IF NOT EXISTS device_apps (
    device_id TEXT NOT NULL REFERENCES devices (id) ON DELETE CASCADE,
    client TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    observed_state TEXT NOT NULL DEFAULT 'unknown',
    observed_version TEXT NOT NULL DEFAULT '',
    observed_at TEXT,
    PRIMARY KEY (device_id, client)
);
"""

_INIT_LOCK = threading.Lock()
_READY = set()


def root(path=None):
    value = path or os.environ.get(ROOT_ENVIRONMENT, "").strip()
    return Path(value) if value else None


def database_path(path=None):
    folder = root(path)
    return None if folder is None else folder / "admin.sqlite3"


@contextmanager
def connect(path=None):
    """Yield a connection; commit on success, roll back on error."""
    target = database_path(path)

    if target is None:
        raise RuntimeError("The PiVault admin folder is not configured")

    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)

    with _INIT_LOCK:
        if str(target) not in _READY:
            boot = sqlite3.connect(target)
            try:
                boot.executescript(SCHEMA)
                boot.commit()
            finally:
                boot.close()

            os.chmod(target, 0o600)
            _READY.add(str(target))

    connection = sqlite3.connect(target, timeout=15, isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("BEGIN IMMEDIATE")

    try:
        yield connection
        connection.execute("COMMIT")
    except BaseException:
        connection.execute("ROLLBACK")
        raise
    finally:
        connection.close()

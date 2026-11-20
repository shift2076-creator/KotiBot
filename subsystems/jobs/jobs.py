"""Read-only list of KotiBot's scheduled jobs, shown in Settings, System.

Each job keeps a folder under the directory named by ``KOTIBOT_JOBS_DIR``:

``job.json``       name, description and a human-readable schedule.
``last-run.json``  started, finished, result and a short summary of the last run.

This module only reads. It never starts, stops or reschedules anything and never
touches the machine's timers. A missing directory means the list is unavailable;
a missing or malformed file hides that field, never the rest of the list.

The Internet jobs switch that Settings, Network already owns is reported beside
the list so both read from the same place.
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path

from flask import jsonify

from subsystems.network import site_settings


LOGGER = logging.getLogger(__name__)

PATH_ENVIRONMENT = "KOTIBOT_JOBS_DIR"
ROUTE = "/api/jobs"

RESULTS = ("ok", "failed", "running")
MAX_JOBS = 64
MAX_FILE_BYTES = 16 * 1024
MAX_TEXT = 300
JOB_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")


def _text(value, limit=MAX_TEXT):
    return value.strip()[:limit] if isinstance(value, str) else ""


def _read_object(path):
    """Return the JSON object in ``path``, or {} for anything unusable."""
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_FILE_BYTES:
            return {}

        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}

    return value if isinstance(value, dict) else {}


def describe_job(folder):
    definition = _read_object(folder / "job.json")
    last = _read_object(folder / "last-run.json")
    result = last.get("result")

    return {
        "id": folder.name,
        "name": _text(definition.get("name"), 80) or folder.name,
        "description": _text(definition.get("description")),
        "schedule": _text(definition.get("schedule"), 120),
        "last_run": {
            "started": _text(last.get("started"), 40),
            "finished": _text(last.get("finished"), 40),
            "result": result if result in RESULTS else "unknown",
            "summary": _text(last.get("summary")),
        },
    }


def list_jobs(root):
    try:
        folders = sorted(
            entry for entry in Path(root).iterdir()
            if JOB_ID.match(entry.name) and entry.is_dir() and not entry.is_symlink()
        )
    except OSError:
        return None

    return [describe_job(folder) for folder in folders[:MAX_JOBS]]


def internet_jobs_state():
    path = os.environ.get(site_settings.PATH_ENVIRONMENT, "").strip()
    return site_settings.load(path)["jobs"] if path else "unknown"


def register_jobs_routes(app, context=None):
    context = context or {}

    def jobs_root():
        return context.get("path") or os.environ.get(PATH_ENVIRONMENT, "").strip()

    @app.route(ROUTE, methods=["GET"])
    def api_jobs_get():
        root = jobs_root()
        jobs = list_jobs(root) if root else None

        if jobs is None:
            return jsonify({"ok": True, "available": False})

        return jsonify({
            "ok": True,
            "available": True,
            "internet_jobs": internet_jobs_state(),
            "jobs": jobs,
        })

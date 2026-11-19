"""Network port roles and the Internet jobs switch, owned by KotiBot Settings.

Replaces the PiVault portal's Network page. The values live in a small JSON
file that the portal mounts too, so the portal's nightly jobs honour what the
Admin sets here. Nothing in this module touches the machine's network: saving
roles only records the choice, exactly as the portal page did.

Off unless ``KOTIBOT_SITE_SETTINGS`` names the file. A missing or unreadable
file means the defaults (Ethernet off, Wi-Fi internet, jobs running).
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path
from threading import Lock

from flask import jsonify, request


LOGGER = logging.getLogger(__name__)

PATH_ENVIRONMENT = "KOTIBOT_SITE_SETTINGS"
ROUTE = "/api/pivault/network"

OFF = "off"
INTERNET = "internet"
LOCAL = "local"
ROLES = (OFF, INTERNET, LOCAL)
DEFAULT_ETHERNET = OFF
DEFAULT_WIFI = INTERNET

_LOCK = Lock()


def validate(ethernet, wifi):
    """Return why this pair of roles cannot be saved, or None."""
    if ethernet not in ROLES or wifi not in ROLES:
        return "Choose Off, Internet or Local for each port."

    if ethernet == INTERNET and wifi == INTERNET:
        return "Only one port can connect to the internet."

    if ethernet == OFF and wifi == OFF:
        return "Turn on at least one port, or the Pi cannot be reached."

    return None


def _read(path):
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}

    return value if isinstance(value, dict) else {}


def load(path):
    stored = _read(path)
    ethernet = stored.get("ethernet_role")
    wifi = stored.get("wifi_role")

    if ethernet not in ROLES or wifi not in ROLES:
        ethernet, wifi = DEFAULT_ETHERNET, DEFAULT_WIFI

    return {
        "ethernet": ethernet,
        "wifi": wifi,
        "jobs": "paused" if stored.get("offline_mode") is True else "running",
    }


def save(path, ethernet, wifi, jobs):
    target = Path(path)
    merged = _read(target)
    merged.update({
        "ethernet_role": ethernet,
        "wifi_role": wifi,
        "offline_mode": jobs == "paused",
    })
    handle, name = tempfile.mkstemp(dir=target.parent, prefix=".site-settings-")

    try:
        with os.fdopen(handle, "w", encoding="utf-8") as out:
            json.dump(merged, out, indent=2, sort_keys=True)
            out.write("\n")

        os.chmod(name, 0o644)
        os.replace(name, target)
    except BaseException:
        try:
            os.unlink(name)
        except OSError:
            pass

        raise


def register_site_settings_routes(app, context=None):
    context = context or {}

    def settings_path():
        return context.get("path") or os.environ.get(PATH_ENVIRONMENT, "").strip()

    @app.route(ROUTE, methods=["GET"])
    def api_pivault_network_get():
        path = settings_path()

        if not path:
            return jsonify({"ok": True, "available": False})

        return jsonify({"ok": True, "available": True, **load(path)})

    @app.route(ROUTE, methods=["POST"])
    def api_pivault_network_post():
        path = settings_path()

        if not path:
            return jsonify({"ok": False, "error": "unavailable"}), 503

        data = request.get_json(silent=True) or {}
        ethernet = str(data.get("ethernet", ""))
        wifi = str(data.get("wifi", ""))
        jobs = str(data.get("jobs", ""))

        if jobs not in ("running", "paused"):
            return jsonify({
                "ok": False,
                "error": "Choose Running or Paused for the Internet jobs.",
            }), 400

        problem = validate(ethernet, wifi)

        if problem:
            return jsonify({"ok": False, "error": problem}), 400

        with _LOCK:
            try:
                save(path, ethernet, wifi, jobs)
            except OSError:
                LOGGER.warning("The site settings file could not be written")
                return jsonify({"ok": False, "error": "Could not save the settings."}), 500

        return jsonify({"ok": True, **load(path)})

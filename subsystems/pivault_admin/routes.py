"""HTTP routes for the Admin inbox and Android devices (dashboard session or helper token)."""

from __future__ import annotations

import os
from functools import wraps

from flask import jsonify, request, send_file

from . import client_packages, devices, notifications, store

PREFIX = "/api/pivault"


def register_pivault_admin_routes(app, context=None):
    security = (context or {}).get("security")

    def available():
        return store.root() is not None

    def unavailable():
        return jsonify({"ok": False, "error": "pivault_admin_unavailable"}), 503

    def user():
        email = security.dashboard_session_email() if security else ""
        return email or "dashboard"

    def json_body():
        data = request.get_json(silent=True)
        return data if isinstance(data, dict) else {}

    def guarded(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not available():
                return unavailable()

            try:
                return view(*args, **kwargs)
            except LookupError as error:
                return jsonify({"ok": False, "error": str(error)}), 404
            except PermissionError as error:
                return jsonify({"ok": False, "error": str(error)}), 409
            except (notifications.NotificationError, devices.DeviceError) as error:
                return jsonify({"ok": False, "error": str(error)}), 400

        return wrapped

    def helper_only(view):
        @wraps(view)
        @guarded
        def wrapped(*args, **kwargs):
            header = request.headers.get("Authorization", "")

            if not header.startswith("Bearer ") or not devices.token_valid(header[7:]):
                return jsonify({"error": "Device sync token required."}), 401

            return view(*args, **kwargs)

        return wrapped

    @app.get(PREFIX + "/notifications")
    @guarded
    def pivault_notifications():
        return jsonify({"ok": True, **notifications.feed(user())})

    @app.post(PREFIX + "/notifications/seen")
    @guarded
    def pivault_notifications_seen():
        notifications.mark_seen(user(), json_body().get("ids") or [])
        return jsonify({"ok": True})

    @app.post(PREFIX + "/notifications/clear-failures")
    @guarded
    def pivault_notifications_clear():
        return jsonify({"ok": True, "cleared": notifications.clear_failures()})

    @app.post(PREFIX + "/notifications/<event_id>/resolve")
    @guarded
    def pivault_notification_resolve(event_id):
        status = notifications.resolve(user(), event_id, json_body().get("action", ""))
        return jsonify({"ok": True, "status": status}), (202 if status == "open" else 200)

    @app.get(PREFIX + "/devices")
    @guarded
    def pivault_devices():
        return jsonify({"ok": True, **devices.overview(), "clients": client_packages.client_rows()})

    @app.post(PREFIX + "/devices/<device_id>/rename")
    @guarded
    def pivault_device_rename(device_id):
        devices.rename(device_id, json_body().get("name"))
        return jsonify({"ok": True})

    @app.post(PREFIX + "/devices/<device_id>/apps/<client>")
    @guarded
    def pivault_device_app(device_id, client):
        devices.set_app(device_id, client, json_body().get("enabled"))
        return jsonify({"ok": True})

    @app.post(PREFIX + "/devices/apps/<client>/version")
    @guarded
    def pivault_device_version(client):
        devices.set_version(client, json_body().get("release", ""))
        return jsonify({"ok": True})

    @app.get(PREFIX + "/devices/sync.py")
    @guarded
    def pivault_device_helper_script():
        script = devices.helper_script(request.host_url.rstrip("/"))
        return script, 200, {
            "Content-Type": "text/x-python; charset=utf-8",
            "Content-Disposition": 'attachment; filename="pivault-android-sync.py"',
        }

    @app.post(PREFIX + "/devices/helper/identify")
    @helper_only
    def pivault_helper_identify():
        return jsonify(devices.identify(json_body()))

    @app.post(PREFIX + "/devices/helper/<device_id>/report")
    @helper_only
    def pivault_helper_report(device_id):
        devices.report(device_id, json_body())
        return jsonify({"ok": True})

    @app.get(PREFIX + "/devices/helper/manifest")
    @helper_only
    def pivault_helper_manifest():
        return jsonify(devices.manifest())

    @app.get(PREFIX + "/devices/helper/apk/<client>")
    @helper_only
    def pivault_helper_apk(client):
        found = devices.apk(client)

        if found is None:
            return jsonify({"error": "No local download is available."}), 404

        target, name, mimetype = found
        return send_file(target, as_attachment=True, download_name=name, mimetype=mimetype)

"""PiVault root certificate: status and download for the Settings page.

PiVault's Caddy serves every local HTTPS address with its own certificate
authority, so each browser and phone must trust that authority once. The
installer publishes the public root certificate (never the key) as a
read-only file for KotiBot. This module reports whether it is there, shows
its SHA-256 fingerprint and serves it as a download.

Off unless ``KOTIBOT_PIVAULT_ROOT_CERT`` names the file. Both routes fall
under the dashboard login like every route that is not listed as public.
"""

from __future__ import annotations

import hashlib
import logging
import os
import ssl
from pathlib import Path

from flask import Response, jsonify


LOGGER = logging.getLogger(__name__)

PATH_ENVIRONMENT = "KOTIBOT_PIVAULT_ROOT_CERT"
STATUS_ROUTE = "/api/pivault/certificate"
DOWNLOAD_ROUTE = "/api/pivault/certificate/ca.crt"
DOWNLOAD_NAME = "pivault-root.crt"
MAX_BYTES = 64 * 1024


def read_certificate(path_text):
    """Return ``(pem_bytes, fingerprint)`` or ``None`` when unusable."""
    if not path_text:
        return None

    path = Path(path_text)

    try:
        if path.is_symlink() or not path.is_file():
            return None

        if path.stat().st_size > MAX_BYTES:
            return None

        raw = path.read_bytes()
        der = ssl.PEM_cert_to_DER_cert(raw.decode("ascii"))
    except (OSError, ValueError, UnicodeDecodeError):
        return None

    digest = hashlib.sha256(der).hexdigest().upper()
    fingerprint = ":".join(digest[i:i + 2] for i in range(0, len(digest), 2))
    return raw, fingerprint


def register_pivault_certificate_routes(app, context=None):
    context = context or {}

    def certificate():
        return read_certificate(
            context.get("path") or os.environ.get(PATH_ENVIRONMENT, "").strip()
        )

    @app.route(STATUS_ROUTE, methods=["GET"])
    def api_pivault_certificate():
        found = certificate()

        if found is None:
            return jsonify({"ok": True, "ready": False, "fingerprint": ""})

        return jsonify({"ok": True, "ready": True, "fingerprint": found[1]})

    @app.route(DOWNLOAD_ROUTE, methods=["GET"])
    def api_pivault_certificate_download():
        found = certificate()

        if found is None:
            return jsonify({"ok": False, "error": "not_found"}), 404

        response = Response(found[0], mimetype="application/x-x509-ca-cert")
        response.headers["Content-Disposition"] = (
            f'attachment; filename="{DOWNLOAD_NAME}"'
        )
        return response

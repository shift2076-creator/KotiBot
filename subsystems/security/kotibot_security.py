from __future__ import annotations

import base64
import copy
import hashlib
import hmac
import ipaddress
import json
import logging
import os
import secrets
import time
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from typing import Any, Optional
from urllib.parse import urlsplit

from flask import (
    g,
    has_request_context,
    jsonify,
    redirect,
    request,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

from server_core.io import (
    JsonStateMissingError,
    JsonStateReadError,
    json_backup_path,
    read_json_object,
    write_json_atomic_sync,
)
from server_core.paths import (
    build_runtime_paths,
    prepare_runtime_directories,
)

DASHBOARD_COOKIE = "kotibot_session"
MAX_CLOCK_SKEW_SECONDS = 300

# An authenticated browser remains signed in for 90 days. Opening the
# authenticated dashboard renews that server-side session.
SESSION_SECONDS = 90 * 24 * 60 * 60
MAX_SESSIONS_PER_USER = 10
DASHBOARD_SESSION_ROTATION_RECOVERY_KEY = (
    "dashboard_session_rotation_recovery"
)

NONCE_RETENTION_SECONDS = 10 * 60
MAX_NONCE_CACHE_ENTRIES = 50_000

PREVIOUS_DEVICE_KEY_GRACE_SECONDS = 5 * 60
DEVICE_ENROLLMENT_SECONDS = 15 * 60

LOGIN_ATTEMPT_LIMIT = 5
LOGIN_ATTEMPT_WINDOW_SECONDS = 15 * 60
ENROLLMENT_ATTEMPT_LIMIT = 12
ENROLLMENT_ATTEMPT_WINDOW_SECONDS = 60

# Keep attacker-controlled rate-limit keys and audit storage bounded.
MAX_RATE_LIMIT_KEYS = 10_000
AUDIT_FILE_MAX_BYTES = 5 * 1024 * 1024

AUDITED_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
HIGH_FREQUENCY_AUDIT_PATHS = {
    "/telemetry",
    "/upload_frame",
}


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _unb64(value: str) -> bytes:
    pad = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + pad).encode("ascii"))


def _now() -> int:
    return int(time.time())


def _json_dumps(data: Any) -> str:
    return json.dumps(data, separators=(",", ":"), sort_keys=True)


def _safe_eq(a: str, b: str) -> bool:
    return hmac.compare_digest(str(a or "").encode("utf-8"), str(b or "").encode("utf-8"))


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)

    if value is None:
        return default

    return value.strip().lower() in ("1", "true", "yes", "on")


def _dashboard_cookie_secure() -> bool:
    # Secure is the safe production default. Local HTTP development must opt
    # out explicitly; forwarding headers never decide cookie security.
    return _env_bool("KOTIBOT_COOKIE_SECURE", True)


def _parse_proxy_networks(value: str) -> tuple:
    networks = []

    for item in str(value or "").split(","):
        item = item.strip()

        if not item:
            continue

        networks.append(ipaddress.ip_network(item, strict=False))

    return tuple(networks)


def _origin_tuple(value: str):
    """Return a normalized (scheme, host, port) origin tuple."""
    try:
        parsed = urlsplit(str(value or "").strip())
        scheme = parsed.scheme.lower()
        hostname = str(parsed.hostname or "").lower()
        port = parsed.port
    except ValueError:
        return None

    if (
        scheme not in ("http", "https")
        or not hostname
        or parsed.username
        or parsed.password
    ):
        return None

    if port is None:
        port = 443 if scheme == "https" else 80

    return scheme, hostname, port


def _parse_allowed_origins(value: str) -> tuple:
    origins = []

    for item in str(value or "").split(","):
        item = item.strip()

        if not item:
            continue

        parsed = urlsplit(item)

        # Configured origins must not contain a path, query, or fragment.
        if parsed.path not in ("", "/") or parsed.query or parsed.fragment:
            raise ValueError(
                f"KOTIBOT_ALLOWED_ORIGINS contains an invalid origin: {item}"
            )

        origin = _origin_tuple(item)

        if origin is None:
            raise ValueError(
                f"KOTIBOT_ALLOWED_ORIGINS contains an invalid origin: {item}"
            )

        if origin not in origins:
            origins.append(origin)

    return tuple(origins)


def _parse_trusted_hosts(value: str) -> tuple:
    hosts = []

    for item in str(value or "").split(","):
        item = item.strip()

        if not item:
            continue

        try:
            parsed = urlsplit(f"//{item}")
            port = parsed.port
        except ValueError:
            parsed = None
            port = None

        hostname = (
            str(parsed.hostname or "").lower().rstrip(".")
            if parsed is not None
            else ""
        )

        if (
            not hostname
            or parsed.username
            or parsed.password
            or port is not None
            or parsed.path
            or parsed.query
            or parsed.fragment
            or "*" in item
            or item.startswith(".")
        ):
            raise ValueError(
                f"KOTIBOT_TRUSTED_HOSTS contains an invalid host: {item}"
            )

        try:
            hostname = ipaddress.ip_address(hostname).compressed
        except ValueError:
            labels = hostname.split(".")

            if (
                len(hostname) > 253
                or any(
                    not label
                    or len(label) > 63
                    or label.startswith("-")
                    or label.endswith("-")
                    or any(
                        not (
                            character.isascii()
                            and (
                                character.isalnum()
                                or character == "-"
                            )
                        )
                        for character in label
                    )
                    for label in labels
                )
            ):
                raise ValueError(
                    f"KOTIBOT_TRUSTED_HOSTS contains an invalid host: {item}"
                )

        if hostname not in hosts:
            hosts.append(hostname)

    return tuple(hosts)


def _request_ip(trusted_proxy_networks: tuple) -> str:
    remote_text = str(request.remote_addr or "").strip()

    try:
        remote_ip = ipaddress.ip_address(remote_text)
    except ValueError:
        return remote_text

    if not any(remote_ip in network for network in trusted_proxy_networks):
        return remote_ip.compressed

    # A trusted reverse proxy must append or replace X-Forwarded-For.
    # Do not let an unrelated trusted proxy promote an attacker-supplied
    # CF-Connecting-IP header.
    forwarded = [
        item.strip()
        for item in str(request.headers.get("X-Forwarded-For") or "").split(",")
        if item.strip()
    ]

    # Walk from the trusted proxy back toward the originating caller. An
    # attacker-controlled value prepended to X-Forwarded-For cannot win.
    for item in reversed(forwarded):
        try:
            candidate = ipaddress.ip_address(item)
        except ValueError:
            continue

        if any(candidate in network for network in trusted_proxy_networks):
            continue

        return candidate.compressed

    return remote_ip.compressed

@dataclass
class SecurityConfig:
    base_dir: Path
    legacy_state_path: Path | None = None
    audit_path: Path | None = None
    enabled: bool = True
    trusted_proxy_networks: tuple = ()
    allowed_origins: tuple = ()
    trusted_hosts: tuple = ()
    state_filename: str = "security_state.json"
    audit_filename: str = "security_audit.jsonl"

    @property
    def state_file(self) -> Path:
        return self.base_dir / self.state_filename

    @property
    def audit_file(self) -> Path:
        if self.audit_path is not None:
            return Path(self.audit_path)

        return self.base_dir / self.audit_filename

    @property
    def legacy_state_file(self) -> Path | None:
        if self.legacy_state_path is None:
            return None

        return Path(self.legacy_state_path)

class KotiBotSecurity:
    """
    Server-issued key starter module.

    Dashboard:
      - no username/password
      - paste server dashboard key once
      - server returns HttpOnly session cookie

    Provisioned device clients:
      - each device gets a server-issued HMAC secret
      - request body + path + timestamp + nonce are signed
      - replayed requests are rejected

    Required device headers:
      X-Device-ID
      X-Koti-Key-ID
      X-Koti-Timestamp
      X-Koti-Nonce
      X-Koti-Body-SHA256
      X-Koti-Signature

    Canonical string:
      METHOD + "\n" + PATH + "\n" + TIMESTAMP + "\n" + NONCE + "\n" + BODY_SHA256_HEX
    """

    def __init__(self, config: SecurityConfig):
        self.config = config
        self._state_lock = RLock()
        self._audit_lock = RLock()
        self._nonces = {}
        self._rate_limits = {}
        self.state = self._load_state()
        self._ensure_state()

    def client_ip(self) -> str:
        """Return the direct IP or the first untrusted proxy-chain address."""
        return _request_ip(self.config.trusted_proxy_networks)

    def require_same_origin(self):
        """Reject browser state changes not originating from this dashboard."""
        source = str(
            request.headers.get("Origin")
            or request.headers.get("Referer")
            or ""
        ).strip()
        fetch_site = str(
            request.headers.get("Sec-Fetch-Site")
            or ""
        ).strip().lower()

        if source and source.lower() != "null":
            # A concrete source must match the configured HTTPS dashboard.
            source_allowed = (
                _origin_tuple(source)
                in self.config.allowed_origins
            )
        else:
            # Firefox may use the opaque Origin value "null". Accept an absent
            # or opaque source only when browser-controlled Fetch Metadata
            # independently confirms that the form is same-origin.
            source_allowed = fetch_site == "same-origin"

        if not source_allowed:
            self.audit(
                "cross_origin_request_blocked",
                status=403,
                supplied_origin=source[:256],
                fetch_site=fetch_site[:32],
            )
            return self.error("same_origin_required", 403)

        return None

    def _rate_limit(
        self,
        key: str,
        limit: int,
        window_seconds: int,
    ) -> int:
        """Record one attempt and return a Retry-After value when blocked."""
        now = time.monotonic()
        cutoff = now - window_seconds

        with self._state_lock:
            bucket = [
                seen_at
                for seen_at in self._rate_limits.get(key, ())
                if seen_at > cutoff
            ]

            if len(bucket) >= limit:
                self._rate_limits[key] = bucket
                remaining = window_seconds - (now - bucket[0])
                return max(1, int(remaining + 0.999))

            # Prevent attackers from growing the key map without bound.
            if (
                key not in self._rate_limits
                and len(self._rate_limits) >= MAX_RATE_LIMIT_KEYS
            ):
                self._rate_limits.pop(
                    next(iter(self._rate_limits)),
                    None,
                )

            bucket.append(now)
            self._rate_limits[key] = bucket
            return 0

    def login_rate_limit(self) -> int:
        return self._rate_limit(
            f"login:{self.client_ip()}",
            LOGIN_ATTEMPT_LIMIT,
            LOGIN_ATTEMPT_WINDOW_SECONDS,
        )

    def clear_login_rate_limit(self) -> None:
        with self._state_lock:
            self._rate_limits.pop(
                f"login:{self.client_ip()}",
                None,
            )

    def enrollment_rate_limit(self, device_id: str) -> int:
        device_id = self.normalize_device_id(device_id) or "invalid"
        client_ip = self.client_ip()

        # Limit both the source IP and the specific source/device pair so
        # changing device IDs cannot bypass the enrollment throttle.
        for key in (
            f"enrollment-ip:{client_ip}",
            f"enrollment-device:{client_ip}:{device_id}",
        ):
            retry_after = self._rate_limit(
                key,
                ENROLLMENT_ATTEMPT_LIMIT,
                ENROLLMENT_ATTEMPT_WINDOW_SECONDS,
            )

            if retry_after:
                return retry_after

        return 0

    def _audit_value(self, name: str, value):
        lowered = str(name or "").lower()

        if any(
            marker in lowered
            for marker in (
                "password",
                "secret",
                "token",
                "signature",
                "authorization",
                "cookie",
                "nonce",
            )
        ):
            return "[redacted]"

        compact_name = "".join(
            ch for ch in lowered
            if ch.isalnum()
        )

        if (
            compact_name in {
                "ip",
                "mac",
                "host",
            }
            or any(
                marker in compact_name
                for marker in (
                    "email",
                    "username",
                    "userid",
                    "identifier",
                    "deviceid",
                    "clientid",
                    "keyid",
                    "projectid",
                    "sessionid",
                    "ipaddress",
                    "clientip",
                    "sourceip",
                    "remoteip",
                    "macaddress",
                    "hostname",
                    "origin",
                    "referer",
                    "uuid",
                    "serial",
                    "imei",
                    "ssid",
                    "bssid",
                    "address",
                )
            )
        ):
            return "[private]"

        if value is None or isinstance(value, (bool, int, float)):
            return value

        return str(value)[:512]

    def audit(self, event: str, status: int = 0, **fields) -> bool:
        """Append a bounded, permission-restricted JSON security event."""
        record = {
            "ts": _now(),
            "event": str(event or "security_event")[:128],
            "status": int(status or 0),
        }

        if has_request_context():
            route_rule = getattr(request, "url_rule", None)
            route_path = str(
                getattr(route_rule, "rule", "")
                or "[unmatched]"
            )

            record.update({
                "method": request.method,
                "path": route_path[:256],
            })

            dashboard_email = self.dashboard_session_email()
            dashboard_principal = (
                self.dashboard_session_principal_type()
            )
            authenticated_device_id = str(
                getattr(g, "kotibot_device_id", "")
                or ""
            ).strip()
            claimed_device_id = str(
                request.headers.get("X-Device-ID")
                or ""
            ).strip()

            if dashboard_email:
                record["actor"] = "dashboard"
            elif dashboard_principal == "key_client":
                record["actor"] = "key-client-dashboard"
            elif authenticated_device_id:
                record["actor"] = "device"
            elif claimed_device_id:
                record["actor"] = "device-claim"
            else:
                record["actor"] = "anonymous"

        for name, value in fields.items():
            record[str(name)[:64]] = self._audit_value(
                name,
                value,
            )

        encoded = _json_dumps(record) + "\n"
        audit_file = self.config.audit_file
        backup_file = audit_file.with_name(
            f"{audit_file.name}.1"
        )

        try:
            with self._audit_lock:
                audit_file.parent.mkdir(
                    parents=True,
                    exist_ok=True,
                )

                if (
                    audit_file.exists()
                    and audit_file.stat().st_size
                    >= AUDIT_FILE_MAX_BYTES
                ):
                    if backup_file.exists():
                        backup_file.unlink()

                    audit_file.replace(backup_file)
                    os.chmod(backup_file, 0o600)

                flags = (
                    os.O_WRONLY
                    | os.O_CREAT
                    | os.O_APPEND
                    | getattr(os, "O_CLOEXEC", 0)
                )
                fd = os.open(audit_file, flags, 0o600)

                with os.fdopen(fd, "a", encoding="utf-8") as stream:
                    stream.write(encoded)
                    stream.flush()

                os.chmod(audit_file, 0o600)

            return True
        except OSError:
            logging.getLogger(__name__).exception(
                "Security audit event could not be written"
            )
            return False

    def audit_request(self, response) -> None:
        """Audit mutations and rejected reads without logging camera traffic."""
        status = int(response.status_code or 0)

        if (
            request.path in HIGH_FREQUENCY_AUDIT_PATHS
            and status < 400
        ):
            return

        if (
            request.method not in AUDITED_METHODS
            and status < 400
        ):
            return

        self.audit(
            "http_request",
            status=status,
        )

    def init_app(self, app):
        # Reject Host-header values outside the configured dashboard origins
        # and explicit non-browser device endpoints.
        app.config["TRUSTED_HOSTS"] = sorted({
            hostname
            for _, hostname, _ in self.config.allowed_origins
        } | set(self.config.trusted_hosts))

        @app.after_request
        def finish_security_response(response):
            if (
                request.method == "GET"
                and request.path == "/"
                and request.cookies.get(DASHBOARD_COOKIE)
                and self.dashboard_authorized()
            ):
                self.refresh_dashboard_cookie(response)

            # A staged replacement may be returned only on a successful JSON
            # response to a device request that already passed HMAC
            # authentication with its current key. Previous/grace keys cannot
            # retrieve the replacement. A request signed by the staged key
            # promotes it before this hook runs, so no secret is re-issued.
            authenticated_device_id = str(
                getattr(g, "kotibot_device_id", "")
                or ""
            ).strip()
            request_key_id = str(
                request.headers.get("X-Koti-Key-ID")
                or ""
            ).strip()

            if (
                authenticated_device_id
                and 200 <= int(response.status_code or 0) < 300
                and response.is_json
                and self.device_key_is_current(
                    authenticated_device_id,
                    request_key_id,
                )
            ):
                handoff = self.device_key_handoff_payload(
                    authenticated_device_id
                )

                if handoff:
                    try:
                        payload = response.get_json()
                    except Exception:
                        payload = None

                    if isinstance(payload, dict):
                        payload.update(handoff)
                        response.set_data(_json_dumps(payload))

            self.audit_request(response)
            return response

        @app.get("/api/security/status")
        def security_status():
            blocked = self.require_dashboard()
            if blocked:
                return blocked

            return jsonify({
                "ok": True,
                "enabled": True,
                "dashboard_authenticated": True,
                "dashboard_user_email": self.dashboard_session_email(),
                "dashboard_session_type": (
                    self.dashboard_session_principal_type()
                ),
                "device_key_count": len(self.state.get("device_keys", {})),
                "dashboard_user_count": len(self.dashboard_users()),
                "dashboard_login_mode": "email_password",
                "dashboard_session_rotation_recovery": (
                    self.dashboard_session_rotation_recovery_status()
                ),
            })

        @app.post("/api/security/keyclient-session")
        def key_client_dashboard_session():
            device_id = self.normalize_device_id(
                getattr(g, "kotibot_device_id", "")
            )
            key_id = str(
                request.headers.get("X-Koti-Key-ID") or ""
            ).strip()

            if (
                not device_id
                or not self.device_key_is_current(
                    device_id,
                    key_id,
                )
            ):
                self.audit(
                    "key_client_dashboard_session_rejected",
                    status=403,
                    reason="current_device_key_required",
                )
                return self.error(
                    "current_device_key_required",
                    403,
                )

            authorizer = app.config.get(
                "KOTIBOT_KEY_CLIENT_SESSION_AUTHORIZER"
            )

            if not callable(authorizer):
                self.audit(
                    "key_client_dashboard_session_unavailable",
                    status=503,
                )
                return self.error(
                    "key_client_session_unavailable",
                    503,
                )

            try:
                authorized = bool(authorizer(device_id))
            except Exception:
                logging.getLogger(__name__).exception(
                    "Key-client dashboard authorization failed"
                )
                authorized = False

            if not authorized:
                self.audit(
                    "key_client_dashboard_session_rejected",
                    status=403,
                    reason="key_client_not_authorized",
                )
                return self.error(
                    "key_client_not_authorized",
                    403,
                )

            response = jsonify({"ok": True})

            try:
                self.set_key_client_dashboard_cookie(
                    response,
                    device_id,
                    key_id,
                )
            except ValueError:
                self.audit(
                    "key_client_dashboard_session_rejected",
                    status=403,
                    reason="current_device_key_required",
                )
                return self.error(
                    "current_device_key_required",
                    403,
                )

            self.audit(
                "key_client_dashboard_session_issued",
                status=200,
            )
            return response

        @app.get("/api/security/dashboard-sessions")
        def security_list_dashboard_sessions():
            blocked = self.require_dashboard()
            if blocked:
                return blocked

            sessions = self.list_dashboard_sessions()

            return jsonify({
                "ok": True,
                "dashboard_sessions": sessions,
                "dashboard_session_count": len(sessions),
            })

        @app.delete("/api/security/dashboard-sessions")
        def security_revoke_dashboard_sessions():
            blocked = self.require_dashboard()
            if blocked:
                return blocked

            data = request.get_json(silent=True) or {}
            scope = str(data.get("scope") or "").strip().lower()

            if scope:
                if scope != "others":
                    return self.error(
                        "invalid_session_scope",
                        400,
                    )

                revoked_count = (
                    self.revoke_other_dashboard_sessions()
                )

                self.audit(
                    "dashboard_other_sessions_revoked",
                    status=200,
                    revoked_count=revoked_count,
                )

                return jsonify({
                    "ok": True,
                    "revoked_count": revoked_count,
                })

            session_ref = str(
                data.get("session_ref") or ""
            ).strip()

            if not session_ref or len(session_ref) > 128:
                return self.error(
                    "invalid_session_ref",
                    400,
                )

            result = self.revoke_dashboard_session_ref(
                session_ref
            )

            if result == "current":
                return self.error(
                    "current_session_requires_logout",
                    409,
                )

            if result == "not_found":
                return self.error(
                    "session_not_found",
                    404,
                )

            self.audit(
                "dashboard_session_revoked",
                status=200,
                revoked_count=1,
            )

            return jsonify({
                "ok": True,
                "revoked_count": 1,
            })

        @app.post(
            "/api/security/dashboard-session-credential/rotate"
        )
        def security_rotate_dashboard_session_credential():
            blocked = self.require_dashboard()
            if blocked:
                return blocked

            data = request.get_json(silent=True) or {}

            if data.get("confirmation") != (
                "rotate-dashboard-session-credential"
            ):
                return self.error(
                    "rotation_confirmation_required",
                    400,
                )

            try:
                result = self.rotate_dashboard_session_credential()
            except RuntimeError as exc:
                error = str(exc)

                if error not in {
                    "dashboard_session_rotation_recovery_exists",
                    "dashboard_session_credential_malformed",
                    "dashboard_session_registry_malformed",
                }:
                    error = "dashboard_session_rotation_failed"

                self.audit(
                    "dashboard_session_credential_rotation_rejected",
                    status=409,
                    reason=error,
                )
                return self.error(error, 409)

            response = jsonify({"ok": True, **result})
            self.revoke_current_dashboard_session(response)
            self.audit(
                "dashboard_session_credential_rotated",
                status=200,
                revoked_session_count=(
                    result["revoked_session_count"]
                ),
                recovery_preserved=True,
            )
            return response

        @app.post(
            "/api/security/dashboard-session-credential/rollback"
        )
        def security_rollback_dashboard_session_credential():
            blocked = self.require_dashboard()
            if blocked:
                return blocked

            data = request.get_json(silent=True) or {}

            if data.get("confirmation") != (
                "rollback-dashboard-session-credential"
            ):
                return self.error(
                    "rollback_confirmation_required",
                    400,
                )

            try:
                result = (
                    self.rollback_dashboard_session_credential()
                )
            except RuntimeError as exc:
                error = str(exc)

                if error not in {
                    "dashboard_session_rotation_recovery_missing",
                    "dashboard_session_rotation_recovery_malformed",
                    "dashboard_session_credential_malformed",
                    "dashboard_session_registry_malformed",
                }:
                    error = "dashboard_session_rotation_rollback_failed"

                self.audit(
                    "dashboard_session_credential_rollback_rejected",
                    status=409,
                    reason=error,
                )
                return self.error(error, 409)

            response = jsonify({"ok": True, **result})
            self.revoke_current_dashboard_session(response)
            self.audit(
                "dashboard_session_credential_rolled_back",
                status=200,
                invalidated_session_count=(
                    result["invalidated_session_count"]
                ),
                restored_session_count=(
                    result["restored_session_count"]
                ),
            )
            return response

        @app.post("/login")
        def dashboard_login():
            blocked = self.require_same_origin()
            if blocked:
                return blocked

            rate_block = self.login_rate_limit()
            if rate_block:
                response = redirect(
                    url_for("dashboard", login_error="rate"),
                    code=303,
                )
                response.headers["Retry-After"] = str(rate_block)
                self.audit("dashboard_login_rate_limited", status=429)
                return response

            email = str(request.form.get("email") or "").strip()
            password = str(request.form.get("password") or "")

            if not self.dashboard_login_configured():
                self.audit("dashboard_login_unconfigured", status=503)
                return redirect(
                    url_for("dashboard", login_error="setup"),
                    code=303,
                )

            if not self.verify_dashboard_login(email, password):
                self.audit(
                    "dashboard_login_failed",
                    status=401,
                    email=self._normalize_dashboard_email(email),
                )
                return redirect(
                    url_for("dashboard", login_error="bad"),
                    code=303,
                )

            self.clear_login_rate_limit()

            response = redirect(url_for("dashboard"), code=303)
            self.set_dashboard_cookie(
                response,
                self._normalize_dashboard_email(email),
            )
            self.audit(
                "dashboard_login_succeeded",
                status=200,
                email=self._normalize_dashboard_email(email),
            )
            return response

        @app.post("/api/security/dashboard-logout")
        def dashboard_logout():
            response = jsonify({"ok": True})
            self.revoke_current_dashboard_session(response)
            self.audit("dashboard_logout", status=200)
            return response

        @app.route("/api/security/device-key", methods=["POST"])
        def security_issue_device_key():
            blocked = self.require_dashboard()
            if blocked:
                return blocked

            data = request.get_json(silent=True) or {}
            device_id = str(data.get("deviceID") or data.get("deviceId") or "").strip()

            if not device_id:
                return self.error("missing_deviceID", 400)

            issued = self.issue_device_key(device_id, rotate=bool(data.get("rotate", False)))
            return jsonify({"ok": True, **issued})

        @app.route("/api/security/revoke-device-key", methods=["POST"])
        def security_revoke_device_key():
            blocked = self.require_dashboard()
            if blocked:
                return blocked

            data = request.get_json(silent=True) or {}
            device_id = str(data.get("deviceID") or data.get("deviceId") or "").strip()
            key_id = str(data.get("keyID") or data.get("keyId") or data.get("kid") or "").strip()

            if not device_id:
                return self.error("missing_deviceID", 400)

            self.revoke_device_key(device_id, key_id=key_id or None)
            return jsonify({"ok": True})

        @app.post("/api/security/device-enrollment")
        def security_reset_device_enrollment():
            blocked = self.require_dashboard()
            if blocked:
                return blocked

            data = request.get_json(silent=True) or {}
            device_id = self.normalize_device_id(
                data.get("deviceID") or data.get("deviceId")
            )

            if not device_id:
                return self.error("missing_deviceID", 400)

            # Resetting enrollment is an explicit administrator action. Existing
            # device credentials are revoked before the one-time claim is issued.
            self.revoke_device_key(device_id)
            enrollment = self.begin_device_enrollment(
                device_id,
                rotate=True,
            )

            self.audit(
                "device_enrollment_reset",
                status=200,
                deviceID=device_id,
            )

            return jsonify({
                "ok": True,
                "deviceID": device_id,
                **enrollment,
            })
        
        @app.route("/api/security/dashboard-users", methods=["GET"])
        def security_list_dashboard_users():
            blocked = self.require_dashboard()
            if blocked:
                return blocked

            return jsonify({
                "ok": True,
                "dashboard_users": self.list_dashboard_users(),
                "dashboard_user_count": len(self.dashboard_users()),
            })

        @app.route("/api/security/dashboard-users", methods=["POST"])
        def security_add_dashboard_user():
            blocked = self.require_dashboard()
            if blocked:
                return blocked

            data = request.get_json(silent=True) or {}
            email = str(data.get("email") or "").strip()
            password = str(data.get("password") or "")

            try:
                user = self.add_dashboard_user(email, password)
            except Exception as e:
                return jsonify({"ok": False, "error": str(e)}), 400

            return jsonify({
                "ok": True,
                "dashboard_user": user,
                "dashboard_users": self.list_dashboard_users(),
                "dashboard_user_count": len(self.dashboard_users()),
            })

        @app.route("/api/security/dashboard-users", methods=["DELETE"])
        def security_remove_dashboard_user():
            blocked = self.require_dashboard()
            if blocked:
                return blocked

            data = request.get_json(silent=True) or {}
            email = str(data.get("email") or "").strip().lower()

            if not email:
                return jsonify({"ok": False, "error": "email required"}), 400

            try:
                removed = self.remove_dashboard_user(email)
            except Exception as e:
                return jsonify({"ok": False, "error": str(e)}), 400

            return jsonify({
                "ok": True,
                "removed": removed,
                "dashboard_email": email,
                "dashboard_users": self.list_dashboard_users(),
                "dashboard_user_count": len(self.dashboard_users()),
            })


    def _migrate_legacy_state(self) -> None:
        state_file = self.config.state_file
        backup_file = json_backup_path(state_file)
        legacy_state_file = self.config.legacy_state_file

        if state_file.is_symlink():
            raise RuntimeError(
                "Security state must not be a symbolic link"
            )

        if state_file.exists() or backup_file.exists():
            return

        if legacy_state_file is None:
            return

        if legacy_state_file.is_symlink():
            raise RuntimeError(
                "Legacy security state must not be a symbolic link"
            )

        legacy_backup_file = json_backup_path(legacy_state_file)

        if not legacy_state_file.exists():
            if legacy_backup_file.exists():
                raise RuntimeError(
                    "Legacy security state primary is missing while "
                    "a recovery copy exists"
                )

            return

        try:
            legacy_state = read_json_object(legacy_state_file)
        except JsonStateReadError as exc:
            raise RuntimeError(
                "Legacy security state could not be read: "
                f"file={exc.filename} reason={exc.reason}"
            ) from None

        write_json_atomic_sync(state_file, legacy_state)

    def _load_state(self) -> dict:
        state_file = self.config.state_file

        self._migrate_legacy_state()

        if state_file.is_symlink():
            raise RuntimeError(
                "Security state must not be a symbolic link"
            )

        try:
            state = read_json_object(state_file)
        except JsonStateMissingError:
            if json_backup_path(state_file).exists():
                raise RuntimeError(
                    "Security state primary is missing while a recovery "
                    "copy exists"
                ) from None

            return {}
        except JsonStateReadError as exc:
            # Resetting corrupted authentication state silently could destroy
            # all users, sessions, and device credentials.
            raise RuntimeError(
                "Security state could not be read: "
                f"file={exc.filename} reason={exc.reason}"
            ) from None

        os.chmod(state_file, 0o600)
        return state

    def _save_state(self) -> None:
        with self._state_lock:
            state_file = self.config.state_file

            if state_file.is_symlink():
                raise RuntimeError(
                    "Security state must not be a symbolic link"
                )

            write_json_atomic_sync(state_file, self.state)

    def _ensure_state(self) -> None:
        changed = False

        saved_nonces = self.state.pop("nonces", None)

        if isinstance(saved_nonces, dict):
            now = _now()

            for key, seen_at in saved_nonces.items():
                try:
                    seen_at = int(seen_at)
                except Exception:
                    continue

                if now - seen_at <= NONCE_RETENTION_SECONDS:
                    self._nonces[str(key)] = seen_at

            changed = True
        elif saved_nonces is not None:
            changed = True

        # Static dashboard keys were a permanent authentication bypass.
        for key in (
            "dashboard_key_hash",
            "dashboard_key_hint",
            "_first_dashboard_key",
        ):
            if key in self.state:
                self.state.pop(key, None)
                changed = True

        if "session_secret" not in self.state:
            self.state["session_secret"] = _b64(secrets.token_bytes(32))
            changed = True

        if "device_keys" not in self.state or not isinstance(self.state.get("device_keys"), dict):
            self.state["device_keys"] = {}
            changed = True

        for key in (
            "dashboard_sessions",
            "device_enrollments",
        ):
            if not isinstance(self.state.get(key), dict):
                self.state[key] = {}
                changed = True

        legacy_email = str(self.state.get("dashboard_email") or "").strip().lower()
        legacy_hash = str(self.state.get("dashboard_password_hash") or "").strip()

        if legacy_email and legacy_hash:
            users = self.state.setdefault("dashboard_users", {})

            if not isinstance(users, dict):
                users = {}
                self.state["dashboard_users"] = users

            users.setdefault(legacy_email, {
                "password_hash": legacy_hash,
                "created_at": _now(),
                "updated_at": _now(),
                "status": "active",
            })
            self.state.pop("dashboard_email", None)
            self.state.pop("dashboard_password_hash", None)
            changed = True

        if "dashboard_users" in self.state and not isinstance(self.state.get("dashboard_users"), dict):
            self.state["dashboard_users"] = {}
            changed = True

        if changed:
            self._save_state()

    def _hash_secret(self, value: str) -> str:
        # Retained for high-entropy dashboard and device keys.
        return hashlib.sha256(str(value).encode("utf-8")).hexdigest()

    def _hash_password(self, password: str) -> str:
        return generate_password_hash(str(password or ""), method="scrypt")

    def _verify_password_hash(self, password: str, expected_hash: str) -> bool:
        expected_hash = str(expected_hash or "")

        # Werkzeug password hashes contain separators. Existing KotiBot
        # SHA-256 hashes do not, so they remain verifiable during migration.
        if "$" in expected_hash:
            try:
                return check_password_hash(expected_hash, str(password or ""))
            except (TypeError, ValueError):
                return False

        return _safe_eq(self._hash_secret(password), expected_hash)

    def _normalize_dashboard_email(self, email: str) -> str:
        return str(email or "").strip().lower()

    def _validate_dashboard_user(self, email: str, password: str) -> tuple[str, str]:
        email = self._normalize_dashboard_email(email)
        password = str(password or "")

        if not email or "@" not in email:
            raise ValueError("valid email required")

        if len(password) < 10:
            raise ValueError("password must be at least 10 characters")

        if not any(ch.isupper() for ch in password):
            raise ValueError("password must include an uppercase letter")

        if not any(ch.islower() for ch in password):
            raise ValueError("password must include a lowercase letter")

        if not any(ch.isdigit() for ch in password):
            raise ValueError("password must include a number")

        if not any(not ch.isalnum() for ch in password):
            raise ValueError("password must include a special character")

        return email, password

    def dashboard_users(self, include_disabled: bool = False) -> dict:
        users = self.state.get("dashboard_users")

        if not isinstance(users, dict):
            return {}

        cleaned = {}

        for email, record in users.items():
            email = self._normalize_dashboard_email(email)

            if not email or not isinstance(record, dict):
                continue

            if not include_disabled and str(record.get("status") or "active").lower() != "active":
                continue

            if not str(record.get("password_hash") or "").strip():
                continue

            cleaned[email] = record

        return cleaned

    def dashboard_login_configured(self) -> bool:
        if self.dashboard_users():
            return True

        return bool(
            str(self.state.get("dashboard_email") or "").strip()
            and str(self.state.get("dashboard_password_hash") or "").strip()
        )

    def set_dashboard_login(self, email: str, password: str) -> None:
        email, password = self._validate_dashboard_user(email, password)
        now = _now()

        with self._state_lock:
            self.state["dashboard_users"] = {
                email: {
                    "password_hash": self._hash_password(password),
                    "created_at": now,
                    "updated_at": now,
                    "status": "active",
                    "session_version": 1,
                }
            }
            self.state["dashboard_sessions"] = {}
            self.state.pop("dashboard_email", None)
            self.state.pop("dashboard_password_hash", None)
            self._save_state()

    def add_dashboard_user(self, email: str, password: str) -> dict:
        email, password = self._validate_dashboard_user(email, password)
        now = _now()

        with self._state_lock:
            users = self.state.setdefault("dashboard_users", {})

            if not isinstance(users, dict):
                users = {}
                self.state["dashboard_users"] = users

            existing = users.get(email) if isinstance(users.get(email), dict) else {}
            created_at = int(existing.get("created_at") or now)

            session_version = int(
                existing.get("session_version", 0) or 0
            ) + 1

            users[email] = {
                "password_hash": self._hash_password(password),
                "created_at": created_at,
                "updated_at": now,
                "status": "active",
                "session_version": session_version,
            }

            self._revoke_user_sessions_unlocked(email)
            self.state.pop("dashboard_email", None)
            self.state.pop("dashboard_password_hash", None)
            self._save_state()

        return {
            "email": email,
            "created_at": created_at,
            "updated_at": now,
            "status": "active",
        }

    def remove_dashboard_user(self, email: str) -> bool:
        email = self._normalize_dashboard_email(email)

        if not email:
            raise ValueError("email required")

        with self._state_lock:
            users = self.state.get("dashboard_users")

            if not isinstance(users, dict) or email not in users:
                return False

            active_users = self.dashboard_users()

            if email in active_users and len(active_users) <= 1:
                raise ValueError(
                    "cannot remove the last dashboard user"
                )

            users.pop(email, None)
            self._revoke_user_sessions_unlocked(email)
            self._save_state()

        return True

    def list_dashboard_users(self) -> list[dict]:
        users = self.dashboard_users(include_disabled=True)
        output = []

        for email in sorted(users.keys()):
            record = users[email]
            output.append({
                "email": email,
                "created_at": record.get("created_at"),
                "updated_at": record.get("updated_at"),
                "status": record.get("status", "active"),
            })

        legacy_email = self._normalize_dashboard_email(self.state.get("dashboard_email"))
        legacy_hash = str(self.state.get("dashboard_password_hash") or "").strip()

        if legacy_email and legacy_hash and legacy_email not in users:
            output.append({
                "email": legacy_email,
                "created_at": None,
                "updated_at": None,
                "status": "legacy",
            })

        return output

    def verify_dashboard_login(self, email: str, password: str) -> bool:
        email = self._normalize_dashboard_email(email)
        password = str(password or "")

        if not email or not password:
            return False

        record = self.dashboard_users().get(email)

        if record:
            expected_hash = str(record.get("password_hash") or "")
            verified = self._verify_password_hash(password, expected_hash)

            # Transparently replace an existing unsalted SHA-256 password
            # hash after the user successfully proves the password.
            if verified and not expected_hash.startswith("scrypt:"):
                with self._state_lock:
                    record["password_hash"] = self._hash_password(password)
                    record["updated_at"] = _now()
                    self._save_state()

            return verified

        expected_email = self._normalize_dashboard_email(self.state.get("dashboard_email"))
        expected_hash = str(self.state.get("dashboard_password_hash") or "")

        return (
            _safe_eq(email, expected_email)
            and self._verify_password_hash(password, expected_hash)
        )


    def _session_signature(self, session_id: str) -> str:
        secret = _unb64(self.state["session_secret"])
        return _b64(
            hmac.new(
                secret,
                session_id.encode("utf-8"),
                hashlib.sha256,
            ).digest()
        )

    def _session_key(self, session_id: str) -> str:
        return self._hash_secret(session_id)

    def _dashboard_session_principal_type(self, record: dict) -> str:
        principal_type = str(
            record.get("principal_type") or ""
        ).strip().lower()

        if not principal_type and self._normalize_dashboard_email(
            record.get("email")
        ):
            # Sessions created before principal typing are dashboard-user
            # sessions. Preserve them without weakening validation.
            return "dashboard_user"

        return principal_type

    def _key_client_dashboard_session_valid(
        self,
        record: dict,
    ) -> bool:
        device_id = self.normalize_device_id(
            record.get("device_id")
        )
        key_id = str(record.get("key_id") or "").strip()

        return bool(
            device_id
            and key_id
            and self.device_key_is_current(device_id, key_id)
        )

    def _session_from_token(self, token: str):
        token = str(token or "")

        if token.count(".") != 1:
            return None

        session_id, signature = token.split(".", 1)

        if (
            not session_id
            or len(session_id) > 128
            or not _safe_eq(signature, self._session_signature(session_id))
        ):
            return None

        with self._state_lock:
            sessions = self.state.get("dashboard_sessions", {})
            record = sessions.get(self._session_key(session_id))

            if not isinstance(record, dict):
                return None

            if int(record.get("expires_at", 0) or 0) < _now():
                return None

            principal_type = self._dashboard_session_principal_type(
                record
            )

            if principal_type == "key_client":
                if not self._key_client_dashboard_session_valid(record):
                    return None
            elif principal_type == "dashboard_user":
                email = self._normalize_dashboard_email(
                    record.get("email")
                )
                user = self.dashboard_users().get(email)

                if not user:
                    return None

                if int(record.get("user_version", 0) or 0) != int(
                    user.get("session_version", 1) or 1
                ):
                    return None
            else:
                return None

            return session_id, dict(record)

    def current_dashboard_session(self):
        return self._session_from_token(
            request.cookies.get(DASHBOARD_COOKIE, "")
        )

    def dashboard_session_email(self) -> str:
        session = self.current_dashboard_session()
        return str(session[1].get("email") or "") if session else ""

    def dashboard_session_principal_type(self) -> str:
        session = self.current_dashboard_session()

        if not session:
            return ""

        return self._dashboard_session_principal_type(session[1])

    def _dashboard_request_client_metadata(self) -> dict:
        user_agent = str(
            request.headers.get("User-Agent") or ""
        )[:512]
        lowered = user_agent.lower()

        if "android" in lowered:
            os_name = "Android"
        elif any(
            value in lowered
            for value in ("iphone", "ipad", "ipod")
        ):
            os_name = "iOS"
        elif "windows" in lowered:
            os_name = "Windows"
        elif "cros" in lowered:
            os_name = "ChromeOS"
        elif "mac os x" in lowered or "macintosh" in lowered:
            os_name = "macOS"
        elif "linux" in lowered:
            os_name = "Linux"
        else:
            os_name = "Other"

        is_android_webview = (
            "android" in lowered
            and (
                "; wv)" in lowered
                or " version/4.0 " in lowered
            )
            and "chrome/" in lowered
        )

        if is_android_webview:
            browser = "Android WebView"
            client_kind = "android_webview"
        elif any(
            value in lowered
            for value in ("edg/", "edgios/", "edga/")
        ):
            browser = "Edge"
            client_kind = "browser"
        elif "opr/" in lowered or "opera" in lowered:
            browser = "Opera"
            client_kind = "browser"
        elif "firefox/" in lowered or "fxios/" in lowered:
            browser = "Firefox"
            client_kind = "browser"
        elif "crios/" in lowered or "chrome/" in lowered:
            browser = "Chrome"
            client_kind = "browser"
        elif "safari/" in lowered and "version/" in lowered:
            browser = "Safari"
            client_kind = "browser"
        elif any(
            value in lowered
            for value in ("curl/", "wget/", "httpie/")
        ):
            browser = "CLI"
            client_kind = "cli"
        else:
            browser = "Other"
            client_kind = "unknown"

        if "ipad" in lowered:
            device = "tablet"
        elif any(
            value in lowered
            for value in ("iphone", "ipod")
        ):
            device = "phone"
        elif "android" in lowered:
            device = (
                "phone"
                if "mobile" in lowered
                else "tablet"
            )
        elif client_kind == "browser":
            device = "desktop"
        else:
            device = "unknown"

        return {
            "ip": str(self.client_ip() or "")[:64],
            "browser": browser,
            "os": os_name,
            "device": device,
            "client_kind": client_kind,
        }

    def _dashboard_session_ref(
        self,
        session_key: str,
    ) -> str:
        secret = _unb64(self.state["session_secret"])

        return _b64(
            hmac.new(
                secret,
                (
                    "dashboard-session-ref:"
                    + str(session_key or "")
                ).encode("utf-8"),
                hashlib.sha256,
            ).digest()
        )

    def list_dashboard_sessions(self) -> list[dict]:
        current = self.current_dashboard_session()
        current_key = (
            self._session_key(current[0])
            if current
            else ""
        )
        current_client = (
            self._dashboard_request_client_metadata()
            if current_key
            else {}
        )
        users = self.dashboard_users()
        now = _now()
        output = []

        with self._state_lock:
            sessions = self.state.get(
                "dashboard_sessions",
                {},
            )

            if not isinstance(sessions, dict):
                return []

            for session_key, record in sessions.items():
                if not isinstance(record, dict):
                    continue

                principal_type = (
                    self._dashboard_session_principal_type(record)
                )

                try:
                    created_at = int(
                        record.get("created_at", 0) or 0
                    )
                    last_seen_at = int(
                        record.get("last_seen_at", 0) or 0
                    )
                    expires_at = int(
                        record.get("expires_at", 0) or 0
                    )
                except (TypeError, ValueError):
                    continue

                if expires_at < now:
                    continue

                if principal_type == "key_client":
                    if not self._key_client_dashboard_session_valid(
                        record
                    ):
                        continue

                    username = "KotiBot Control"
                elif principal_type == "dashboard_user":
                    email = self._normalize_dashboard_email(
                        record.get("email")
                    )
                    user = users.get(email)

                    if not user:
                        continue

                    try:
                        user_version = int(
                            record.get("user_version", 0) or 0
                        )
                        current_version = int(
                            user.get("session_version", 1) or 1
                        )
                    except (TypeError, ValueError):
                        continue

                    if user_version != current_version:
                        continue

                    username = email
                else:
                    continue

                is_current = session_key == current_key

                last_seen_ip = str(
                    record.get("last_seen_ip") or ""
                )[:64]
                browser = str(
                    record.get("browser") or "Unknown"
                )[:64]
                os_name = str(
                    record.get("os") or "Unknown"
                )[:64]
                device = str(
                    record.get("device") or "unknown"
                )[:32]
                client_kind = str(
                    record.get("client_kind") or "unknown"
                )[:32]

                if is_current:
                    last_seen_at = now
                    last_seen_ip = str(
                        current_client.get("ip") or ""
                    )[:64]
                    browser = str(
                        current_client.get("browser")
                        or "Unknown"
                    )[:64]
                    os_name = str(
                        current_client.get("os")
                        or "Unknown"
                    )[:64]
                    device = str(
                        current_client.get("device")
                        or "unknown"
                    )[:32]
                    client_kind = str(
                        current_client.get("client_kind")
                        or "unknown"
                    )[:32]

                output.append({
                    "session_ref":
                        self._dashboard_session_ref(
                            session_key
                        ),
                    "username": username,
                    "created_at": created_at,
                    "last_seen_at": last_seen_at,
                    "expires_at": expires_at,
                    "created_ip": str(
                        record.get("created_ip") or ""
                    )[:64],
                    "last_seen_ip": last_seen_ip,
                    "browser": browser,
                    "os": os_name,
                    "device": device,
                    "client_kind": client_kind,
                    "current": is_current,
                })

        output.sort(
            key=lambda item: (
                0 if item["current"] else 1,
                -int(item["last_seen_at"] or 0),
                -int(item["created_at"] or 0),
            )
        )
        return output

    def _write_dashboard_cookie(self, response, token: str) -> None:
        response.set_cookie(
            DASHBOARD_COOKIE,
            token,
            max_age=SESSION_SECONDS,
            httponly=True,
            secure=_dashboard_cookie_secure(),
            samesite="Strict",
            path="/",
        )

    def set_dashboard_cookie(self, response, email: str) -> None:
        email = self._normalize_dashboard_email(email)
        user = self.dashboard_users().get(email)

        if not user:
            raise ValueError("dashboard user is not active")

        now = _now()
        session_id = secrets.token_urlsafe(32)
        session_key = self._session_key(session_id)
        client = self._dashboard_request_client_metadata()

        with self._state_lock:
            sessions = self.state.setdefault("dashboard_sessions", {})
            self._prune_sessions_unlocked()

            existing = sorted(
                (
                    (key, record)
                    for key, record in sessions.items()
                    if isinstance(record, dict)
                    and self._normalize_dashboard_email(
                        record.get("email")
                    ) == email
                ),
                key=lambda item: int(
                    item[1].get("created_at", 0) or 0
                ),
            )

            while len(existing) >= MAX_SESSIONS_PER_USER:
                old_key, _ = existing.pop(0)
                sessions.pop(old_key, None)

            sessions[session_key] = {
                "email": email,
                "created_at": now,
                "last_seen_at": now,
                "expires_at": now + SESSION_SECONDS,
                "user_version": int(
                    user.get("session_version", 1) or 1
                ),
                "created_ip": client["ip"],
                "last_seen_ip": client["ip"],
                "browser": client["browser"],
                "os": client["os"],
                "device": client["device"],
                "client_kind": client["client_kind"],
            }
            self._save_state()

        token = f"{session_id}.{self._session_signature(session_id)}"
        self._write_dashboard_cookie(response, token)

    def set_key_client_dashboard_cookie(
        self,
        response,
        device_id: str,
        key_id: str,
    ) -> None:
        device_id = self.normalize_device_id(device_id)
        key_id = str(key_id or "").strip()
        now = _now()
        session_id = secrets.token_urlsafe(32)
        session_key = self._session_key(session_id)
        client = self._dashboard_request_client_metadata()

        with self._state_lock:
            if not self.device_key_is_current(device_id, key_id):
                raise ValueError("current device key is required")

            sessions = self.state.setdefault("dashboard_sessions", {})
            self._prune_sessions_unlocked()

            # The native Control app exchanges on startup. Keep one bounded
            # dashboard session for this authenticated device instead of
            # accumulating a new server-side session on every launch.
            for existing_key, record in list(sessions.items()):
                if (
                    isinstance(record, dict)
                    and self._dashboard_session_principal_type(record)
                    == "key_client"
                    and _safe_eq(
                        self.normalize_device_id(
                            record.get("device_id")
                        ),
                        device_id,
                    )
                ):
                    sessions.pop(existing_key, None)

            sessions[session_key] = {
                "principal_type": "key_client",
                "device_id": device_id,
                "key_id": key_id,
                "created_at": now,
                "last_seen_at": now,
                "expires_at": now + SESSION_SECONDS,
                "created_ip": client["ip"],
                "last_seen_ip": client["ip"],
                "browser": client["browser"],
                "os": client["os"],
                "device": client["device"],
                "client_kind": client["client_kind"],
            }
            self._save_state()

        token = f"{session_id}.{self._session_signature(session_id)}"
        self._write_dashboard_cookie(response, token)

    def refresh_dashboard_cookie(self, response) -> bool:
        current = self.current_dashboard_session()

        if not current:
            return False

        session_id, _ = current
        session_key = self._session_key(session_id)
        now = _now()
        client = self._dashboard_request_client_metadata()

        with self._state_lock:
            record = self.state.get(
                "dashboard_sessions",
                {},
            ).get(session_key)

            if not isinstance(record, dict):
                return False

            record["last_seen_at"] = now
            record["expires_at"] = now + SESSION_SECONDS
            record["last_seen_ip"] = client["ip"]
            record["browser"] = client["browser"]
            record["os"] = client["os"]
            record["device"] = client["device"]
            record["client_kind"] = client["client_kind"]
            self._save_state()

        token = f"{session_id}.{self._session_signature(session_id)}"
        self._write_dashboard_cookie(response, token)
        return True

    def revoke_current_dashboard_session(self, response) -> None:
        current = self.current_dashboard_session()

        if current:
            session_id, _ = current

            with self._state_lock:
                self.state.get(
                    "dashboard_sessions",
                    {},
                ).pop(self._session_key(session_id), None)
                self._save_state()

        response.delete_cookie(
            DASHBOARD_COOKIE,
            path="/",
            secure=_dashboard_cookie_secure(),
            samesite="Strict",
        )

    def revoke_other_dashboard_sessions(self) -> int:
        current = self.current_dashboard_session()

        if not current:
            return 0

        current_key = self._session_key(current[0])

        with self._state_lock:
            sessions = self.state.get(
                "dashboard_sessions",
                {},
            )

            if not isinstance(sessions, dict):
                return 0

            revoked_keys = [
                session_key
                for session_key in sessions
                if session_key != current_key
            ]

            for session_key in revoked_keys:
                sessions.pop(session_key, None)

            if revoked_keys:
                self._save_state()

        return len(revoked_keys)

    def revoke_dashboard_session_ref(
        self,
        session_ref: str,
    ) -> str:
        session_ref = str(session_ref or "").strip()

        if not session_ref or len(session_ref) > 128:
            return "not_found"

        current = self.current_dashboard_session()
        current_key = (
            self._session_key(current[0])
            if current
            else ""
        )

        with self._state_lock:
            sessions = self.state.get(
                "dashboard_sessions",
                {},
            )

            if not isinstance(sessions, dict):
                return "not_found"

            for session_key in list(sessions):
                if not _safe_eq(
                    session_ref,
                    self._dashboard_session_ref(
                        session_key
                    ),
                ):
                    continue

                if session_key == current_key:
                    return "current"

                sessions.pop(session_key, None)
                self._save_state()
                return "revoked"

        return "not_found"

    def _revoke_user_sessions_unlocked(self, email: str) -> None:
        email = self._normalize_dashboard_email(email)
        sessions = self.state.setdefault("dashboard_sessions", {})

        for key, record in list(sessions.items()):
            if (
                isinstance(record, dict)
                and self._normalize_dashboard_email(
                    record.get("email")
                ) == email
            ):
                sessions.pop(key, None)

    def revoke_user_sessions(self, email: str) -> None:
        with self._state_lock:
            self._revoke_user_sessions_unlocked(email)
            self._save_state()

    def revoke_all_dashboard_sessions(self) -> None:
        with self._state_lock:
            self.state["dashboard_sessions"] = {}
            self._save_state()

    @staticmethod
    def _validated_dashboard_session_credential(value) -> str:
        value = str(value or "").strip()

        try:
            decoded = _unb64(value)
        except Exception:
            decoded = b""

        if len(decoded) < 32:
            raise RuntimeError(
                "dashboard_session_credential_malformed"
            )

        return value

    def _dashboard_session_rotation_recovery_unlocked(
        self,
    ) -> dict:
        recovery = self.state.get(
            DASHBOARD_SESSION_ROTATION_RECOVERY_KEY
        )

        if recovery is None:
            raise RuntimeError(
                "dashboard_session_rotation_recovery_missing"
            )

        if (
            not isinstance(recovery, dict)
            or recovery.get("version") != 1
            or recovery.get("status") != "retired"
        ):
            raise RuntimeError(
                "dashboard_session_rotation_recovery_malformed"
            )

        try:
            retired_at = int(recovery.get("retired_at", 0) or 0)
        except (TypeError, ValueError):
            retired_at = 0

        sessions = recovery.get("dashboard_sessions")

        if retired_at <= 0 or not isinstance(sessions, dict):
            raise RuntimeError(
                "dashboard_session_rotation_recovery_malformed"
            )

        self._validated_dashboard_session_credential(
            recovery.get("session_secret")
        )
        return recovery

    def dashboard_session_rotation_recovery_status(self) -> str:
        with self._state_lock:
            if (
                DASHBOARD_SESSION_ROTATION_RECOVERY_KEY
                not in self.state
            ):
                return "none"

            try:
                self._dashboard_session_rotation_recovery_unlocked()
            except RuntimeError:
                return "malformed"

            return "available"

    def rotate_dashboard_session_credential(self) -> dict:
        with self._state_lock:
            if (
                DASHBOARD_SESSION_ROTATION_RECOVERY_KEY
                in self.state
            ):
                raise RuntimeError(
                    "dashboard_session_rotation_recovery_exists"
                )

            current_secret = (
                self._validated_dashboard_session_credential(
                    self.state.get("session_secret")
                )
            )
            current_sessions = self.state.get(
                "dashboard_sessions"
            )

            if not isinstance(current_sessions, dict):
                raise RuntimeError(
                    "dashboard_session_registry_malformed"
                )

            replacement_secret = _b64(secrets.token_bytes(32))

            while _safe_eq(replacement_secret, current_secret):
                replacement_secret = _b64(secrets.token_bytes(32))

            recovery = {
                "version": 1,
                "status": "retired",
                "retired_at": _now(),
                "session_secret": current_secret,
                "dashboard_sessions": copy.deepcopy(
                    current_sessions
                ),
            }

            self.state[
                DASHBOARD_SESSION_ROTATION_RECOVERY_KEY
            ] = recovery
            self.state["session_secret"] = replacement_secret
            self.state["dashboard_sessions"] = {}

            try:
                self._save_state()
            except Exception:
                self.state["session_secret"] = current_secret
                self.state["dashboard_sessions"] = current_sessions
                self.state.pop(
                    DASHBOARD_SESSION_ROTATION_RECOVERY_KEY,
                    None,
                )
                raise

        return {
            "revoked_session_count": len(current_sessions),
            "recovery_preserved": True,
        }

    def rollback_dashboard_session_credential(self) -> dict:
        with self._state_lock:
            recovery = (
                self._dashboard_session_rotation_recovery_unlocked()
            )
            recovery_secret = (
                self._validated_dashboard_session_credential(
                    recovery.get("session_secret")
                )
            )
            recovery_sessions = recovery.get(
                "dashboard_sessions"
            )
            current_secret = (
                self._validated_dashboard_session_credential(
                    self.state.get("session_secret")
                )
            )
            current_sessions = self.state.get(
                "dashboard_sessions"
            )

            if (
                not isinstance(recovery_sessions, dict)
                or not isinstance(current_sessions, dict)
            ):
                raise RuntimeError(
                    "dashboard_session_registry_malformed"
                )

            restored_sessions = copy.deepcopy(recovery_sessions)
            self.state["session_secret"] = recovery_secret
            self.state["dashboard_sessions"] = restored_sessions
            self.state.pop(
                DASHBOARD_SESSION_ROTATION_RECOVERY_KEY,
                None,
            )

            try:
                self._save_state()
            except Exception:
                self.state["session_secret"] = current_secret
                self.state["dashboard_sessions"] = current_sessions
                self.state[
                    DASHBOARD_SESSION_ROTATION_RECOVERY_KEY
                ] = recovery
                raise

        return {
            "invalidated_session_count": len(current_sessions),
            "restored_session_count": len(restored_sessions),
            "recovery_preserved": False,
        }

    def _prune_sessions_unlocked(self) -> None:
        now = _now()
        users = self.dashboard_users()
        sessions = self.state.setdefault("dashboard_sessions", {})

        for key, record in list(sessions.items()):
            if not isinstance(record, dict):
                sessions.pop(key, None)
                continue

            if int(record.get("expires_at", 0) or 0) < now:
                sessions.pop(key, None)
                continue

            principal_type = self._dashboard_session_principal_type(
                record
            )

            if principal_type == "key_client":
                if not self._key_client_dashboard_session_valid(record):
                    sessions.pop(key, None)
                continue

            email = self._normalize_dashboard_email(
                record.get("email")
            )
            user = users.get(email)

            if (
                principal_type != "dashboard_user"
                or not user
                or int(record.get("user_version", 0) or 0)
                != int(user.get("session_version", 1) or 1)
            ):
                sessions.pop(key, None)

    def dashboard_token_authorized(self, token: str) -> bool:
        """Validate a captured token without requiring a request context."""
        return self._session_from_token(token) is not None

    def dashboard_authorized(self) -> bool:
        return self.current_dashboard_session() is not None

    def require_dashboard(self):
        if self.dashboard_authorized():
            return None

        return self.error("dashboard_auth_required", 401)

    def normalize_device_id(self, device_id) -> str:
        device_id = str(device_id or "").strip()

        if (
            not device_id
            or len(device_id) > 128
            or any(
                not (
                    ch.isascii()
                    and (
                        ch.isalnum()
                        or ch in "._:-"
                    )
                )
                for ch in device_id
            )
        ):
            return ""

        return device_id

    def begin_device_enrollment(
        self,
        device_id: str,
        rotate: bool = False,
    ) -> dict:
        device_id = self.normalize_device_id(device_id)

        if not device_id:
            raise ValueError("invalid deviceID")

        now = _now()

        with self._state_lock:
            enrollments = self.state.setdefault(
                "device_enrollments",
                {},
            )
            existing = enrollments.get(device_id)

            if (
                not rotate
                and isinstance(existing, dict)
                and int(existing.get("expires_at", 0) or 0) >= now
            ):
                return {
                    "enrollmentPending": True,
                    "enrollmentExpiresAt": existing["expires_at"],
                }

            token = "koti_enroll_" + secrets.token_urlsafe(32)
            expires_at = now + DEVICE_ENROLLMENT_SECONDS

            enrollments[device_id] = {
                "token_hash": self._hash_secret(token),
                "issued_at": now,
                "expires_at": expires_at,
            }
            self._save_state()

        return {
            "enrollmentPending": True,
            "enrollmentToken": token,
            "enrollmentExpiresAt": expires_at,
        }

    def device_enrollment_pending(self, device_id: str) -> bool:
        device_id = self.normalize_device_id(device_id)
        record = self.state.get(
            "device_enrollments",
            {},
        ).get(device_id)

        return bool(
            isinstance(record, dict)
            and int(record.get("expires_at", 0) or 0) >= _now()
        )

    def verify_device_enrollment(
        self,
        device_id: str,
        token: str,
    ) -> bool:
        device_id = self.normalize_device_id(device_id)
        token = str(token or "")
        record = self.state.get(
            "device_enrollments",
            {},
        ).get(device_id)

        return bool(
            token
            and isinstance(record, dict)
            and int(record.get("expires_at", 0) or 0) >= _now()
            and _safe_eq(
                self._hash_secret(token),
                record.get("token_hash", ""),
            )
        )

    def consume_device_enrollment(
        self,
        device_id: str,
        token: str,
    ) -> bool:
        if not self.verify_device_enrollment(device_id, token):
            return False

        device_id = self.normalize_device_id(device_id)

        with self._state_lock:
            self.state.setdefault(
                "device_enrollments",
                {},
            ).pop(device_id, None)
            self._save_state()

        return True

    def cancel_device_enrollment(self, device_id: str) -> None:
        device_id = self.normalize_device_id(device_id)

        with self._state_lock:
            self.state.setdefault(
                "device_enrollments",
                {},
            ).pop(device_id, None)
            self._save_state()

    def _new_device_key_record(
        self,
        now: int,
        *,
        status: str = "active",
    ) -> dict:
        return {
            "key_id": "nb_dev_" + secrets.token_urlsafe(12),
            "secret": "nb_secret_" + secrets.token_urlsafe(32),
            "issued_at": now,
            "status": status,
        }

    def _staged_device_key_state(self, item) -> str:
        if item is None:
            return "missing"

        if not isinstance(item, dict):
            return "malformed"

        if str(item.get("status") or "").strip().lower() != "staged":
            return "retired"

        if (
            not str(item.get("key_id") or "").strip()
            or not str(item.get("secret") or "").strip()
        ):
            return "malformed"

        return "staged"

    def stage_device_key_handoffs(
        self,
        device_ids,
    ) -> dict[str, int]:
        clean_ids = []
        seen = set()
        skipped_invalid = 0

        for raw_device_id in device_ids:
            device_id = self.normalize_device_id(raw_device_id)

            if not device_id:
                skipped_invalid += 1
                continue

            if device_id in seen:
                continue

            seen.add(device_id)
            clean_ids.append(device_id)

        result = {
            "requested": len(clean_ids),
            "staged": 0,
            "already_staged": 0,
            "skipped_no_active_key": 0,
            "skipped_previous_grace": 0,
            "skipped_ambiguous_pending": 0,
            "skipped_invalid": skipped_invalid,
        }
        now = _now()
        changed = False

        with self._state_lock:
            device_keys = self.state.setdefault(
                "device_keys",
                {},
            )

            for device_id in clean_ids:
                record = device_keys.get(device_id)

                if not isinstance(record, dict):
                    result["skipped_no_active_key"] += 1
                    continue

                current = record.get("current")

                if (
                    not isinstance(current, dict)
                    or current.get("status") != "active"
                    or not str(current.get("key_id") or "").strip()
                    or not str(current.get("secret") or "").strip()
                ):
                    result["skipped_no_active_key"] += 1
                    continue

                previous = record.get("previous")

                if (
                    isinstance(previous, dict)
                    and previous.get("status") == "active"
                ):
                    try:
                        previous_expires_at = int(
                            previous.get("expires_at") or 0
                        )
                    except (TypeError, ValueError):
                        result["skipped_previous_grace"] += 1
                        continue

                    if previous_expires_at >= now:
                        result["skipped_previous_grace"] += 1
                        continue

                pending = record.get("pending")

                if pending is not None:
                    pending_state = self._staged_device_key_state(
                        pending
                    )

                    if pending_state == "staged":
                        result["already_staged"] += 1
                    else:
                        result["skipped_ambiguous_pending"] += 1

                    continue

                pending = self._new_device_key_record(
                    now,
                    status="staged",
                )
                pending["staged_at"] = now
                record["pending"] = pending
                result["staged"] += 1
                changed = True

            if changed:
                self._save_state()

        return result

    def device_key_handoff_payload(
        self,
        device_id: str,
    ) -> Optional[dict]:
        device_id = self.normalize_device_id(device_id)

        if not device_id:
            return None

        with self._state_lock:
            record = self.state.get(
                "device_keys",
                {},
            ).get(device_id, {})

            if not isinstance(record, dict):
                return None

            current = record.get("current")
            pending = record.get("pending")

            if (
                not isinstance(current, dict)
                or current.get("status") != "active"
                or self._staged_device_key_state(pending)
                != "staged"
            ):
                return None

            return {
                "kotiKeyID": pending["key_id"],
                "kotiKeySecret": pending["secret"],
            }

    def device_key_is_current(
        self,
        device_id: str,
        key_id: str,
    ) -> bool:
        device_id = self.normalize_device_id(device_id)
        key_id = str(key_id or "").strip()

        if not device_id or not key_id:
            return False

        record = self.state.get(
            "device_keys",
            {},
        ).get(device_id, {})
        current = (
            record.get("current")
            if isinstance(record, dict)
            else None
        )

        return bool(
            isinstance(current, dict)
            and current.get("status") == "active"
            and _safe_eq(current.get("key_id", ""), key_id)
        )

    def _mark_current_device_key_handoff_verified(
        self,
        device_id: str,
        key_id: str,
    ) -> bool:
        device_id = self.normalize_device_id(device_id)
        key_id = str(key_id or "").strip()

        if not device_id or not key_id:
            return False

        with self._state_lock:
            record = self.state.get(
                "device_keys",
                {},
            ).get(device_id)

            if not isinstance(record, dict):
                return False

            current = record.get("current")

            if (
                not isinstance(current, dict)
                or current.get("status") != "active"
                or not _safe_eq(
                    current.get("key_id", ""),
                    key_id,
                )
            ):
                return False

            # The first successfully signed request proves that a directly
            # issued or re-enrolled credential reached the live client. Keep
            # subsequent requests read-only instead of rewriting protected
            # security state on every heartbeat or telemetry update.
            if record.get("handoff_verified_at"):
                return True

            record["handoff_verified_at"] = _now()
            self._save_state()

        return True

    def _promote_staged_device_key(
        self,
        device_id: str,
        key_id: str,
    ) -> bool:
        device_id = self.normalize_device_id(device_id)
        key_id = str(key_id or "").strip()

        if not device_id or not key_id:
            return False

        now = _now()

        with self._state_lock:
            record = self.state.get(
                "device_keys",
                {},
            ).get(device_id)

            if not isinstance(record, dict):
                return False

            current = record.get("current")

            # Another concurrent request may already have promoted this exact
            # staged key. Treat that as success instead of failing a valid
            # second request.
            if (
                isinstance(current, dict)
                and current.get("status") == "active"
                and _safe_eq(
                    current.get("key_id", ""),
                    key_id,
                )
            ):
                return True

            pending = record.get("pending")

            if (
                self._staged_device_key_state(pending)
                != "staged"
                or not _safe_eq(
                    pending.get("key_id", ""),
                    key_id,
                )
            ):
                return False

            if (
                not isinstance(current, dict)
                or current.get("status") != "active"
                or not str(current.get("key_id") or "").strip()
                or not str(current.get("secret") or "").strip()
            ):
                return False

            new_current = dict(pending)
            new_current["status"] = "active"
            new_current["activated_at"] = now

            record["previous"] = {
                **current,
                "expires_at": (
                    now + PREVIOUS_DEVICE_KEY_GRACE_SECONDS
                ),
            }
            record["current"] = new_current
            record.pop("pending", None)
            record["rotated_at"] = now
            record["handoff_verified_at"] = now
            self._save_state()

        return True

    def issue_device_key(
        self,
        device_id: str,
        rotate: bool = False,
    ) -> dict:
        device_id = self.normalize_device_id(device_id)

        if not device_id:
            raise ValueError("invalid deviceID")

        now = _now()

        with self._state_lock:
            record = self.state.setdefault(
                "device_keys",
                {},
            ).setdefault(device_id, {})
            old_current = record.get("current")

            if old_current and not rotate:
                return {
                    "deviceID": device_id,
                    "keyID": old_current.get("key_id"),
                    "alreadyIssued": True,
                    "message": "An active key already exists.",
                }

            new_current = self._new_device_key_record(now)

            if old_current:
                record["previous"] = {
                    **old_current,
                    "expires_at": (
                        now + PREVIOUS_DEVICE_KEY_GRACE_SECONDS
                    ),
                }

            # Explicit issuance/rotation supersedes any incomplete staged
            # handoff so a third usable credential cannot linger.
            record.pop("pending", None)
            record["current"] = new_current
            record["rotated_at"] = now if old_current else None
            # Issuance proves only that the server created a replacement.
            # The replacement becomes verified after the live client signs
            # its first request with this exact current key.
            record.pop("handoff_verified_at", None)
            self._save_state()

        return {
            "deviceID": device_id,
            "keyID": new_current["key_id"],
            "secret": new_current["secret"],
            "alreadyIssued": False,
            "storeThisOnClient": True,
        }

    def revoke_device_key(
        self,
        device_id: str,
        key_id: Optional[str] = None,
    ) -> None:
        device_id = self.normalize_device_id(device_id)

        with self._state_lock:
            record = self.state.setdefault(
                "device_keys",
                {},
            ).get(device_id)

            if not record:
                return

            pending = record.get("pending")

            if (
                isinstance(pending, dict)
                and (
                    not key_id
                    or pending.get("key_id") == key_id
                )
            ):
                # A staged key has not become authoritative yet. Remove it
                # rather than preserving another revoked secret-bearing slot.
                record.pop("pending", None)

            for slot in ("current", "previous"):
                item = record.get(slot)

                if not item:
                    continue

                if key_id and item.get("key_id") != key_id:
                    continue

                item["status"] = "revoked"
                item["revoked_at"] = _now()

            self._save_state()

    def _device_key_candidate_slots(
        self,
        device_id: str,
    ) -> list[tuple[str, dict]]:
        device_id = self.normalize_device_id(device_id)
        record = self.state.get(
            "device_keys",
            {},
        ).get(device_id, {})
        now = _now()
        items = []

        for slot in ("current", "previous"):
            item = record.get(slot)

            if not item or item.get("status") != "active":
                continue

            if (
                slot == "previous"
                and int(item.get("expires_at", 0) or 0) < now
            ):
                continue

            items.append((slot, item))

        pending = record.get("pending")

        if self._staged_device_key_state(pending) == "staged":
            items.append(("pending", pending))

        return items

    def _device_key_candidates(self, device_id: str) -> list[dict]:
        return [
            item
            for _, item in self._device_key_candidate_slots(
                device_id
            )
        ]

    def device_has_key(self, device_id: str) -> bool:
        return bool(self._device_key_candidates(device_id))

    def require_device_signature(self, device_id: str):
        device_id = self.normalize_device_id(
            device_id
            or request.headers.get("X-Device-ID")
        )

        if not device_id:
            return self.error("missing_deviceID", 400)

        candidates = self._device_key_candidate_slots(device_id)

        if not candidates:
            return self.error("device_key_required", 401)

        key_id = str(
            request.headers.get("X-Koti-Key-ID") or ""
        ).strip()
        timestamp = str(
            request.headers.get("X-Koti-Timestamp") or ""
        ).strip()
        nonce = str(
            request.headers.get("X-Koti-Nonce") or ""
        ).strip()
        body_sha = str(
            request.headers.get("X-Koti-Body-SHA256") or ""
        ).strip()
        signature = str(
            request.headers.get("X-Koti-Signature") or ""
        ).strip()

        if not all((
            key_id,
            timestamp,
            nonce,
            body_sha,
            signature,
        )):
            return self.error("missing_signature_headers", 401)

        if len(nonce) > 128 or len(signature) > 256:
            return self.error("invalid_signature_headers", 401)

        matching = next(
            (
                (slot, item)
                for slot, item in candidates
                if item.get("key_id") == key_id
            ),
            None,
        )

        if not matching:
            return self.error("unknown_device_key", 401)

        matching_slot, matching = matching

        try:
            ts = int(timestamp)
        except ValueError:
            return self.error("bad_timestamp", 401)

        if abs(_now() - ts) > MAX_CLOCK_SKEW_SECONDS:
            return self.error("timestamp_out_of_range", 401)

        raw_body = request.get_data(cache=True) or b""
        expected_body_sha = hashlib.sha256(raw_body).hexdigest()

        if not _safe_eq(body_sha, expected_body_sha):
            return self.error("body_hash_mismatch", 401)

        canonical = "\n".join([
            request.method.upper(),
            request.path,
            timestamp,
            nonce,
            body_sha,
        ]).encode("utf-8")

        expected = _b64(
            hmac.new(
                matching["secret"].encode("utf-8"),
                canonical,
                hashlib.sha256,
            ).digest()
        )

        if not _safe_eq(signature, expected):
            return self.error("bad_signature", 401)

        # Invalid signatures never enter the replay cache.
        nonce_key = f"{device_id}:{key_id}:{nonce}"

        if self._nonce_seen(nonce_key):
            return self.error("replay_detected", 409)

        # HMAC, body hash, timestamp, and replay validation all succeed
        # before a staged credential can become authoritative.
        if (
            matching_slot == "pending"
            and not self._promote_staged_device_key(
                device_id,
                key_id,
            )
        ):
            return self.error(
                "staged_key_promotion_failed",
                409,
            )

        if (
            matching_slot == "current"
            and not self._mark_current_device_key_handoff_verified(
                device_id,
                key_id,
            )
        ):
            return self.error(
                "current_key_verification_failed",
                409,
            )

        return None

    def _nonce_seen(self, nonce_key: str) -> bool:
        with self._state_lock:
            now = _now()

            for key, seen_at in list(self._nonces.items()):
                if now - int(seen_at or 0) > NONCE_RETENTION_SECONDS:
                    self._nonces.pop(key, None)

            if nonce_key in self._nonces:
                return True

            while len(self._nonces) >= MAX_NONCE_CACHE_ENTRIES:
                self._nonces.pop(next(iter(self._nonces)), None)

            self._nonces[nonce_key] = now
            return False

    def error(self, code: str, status: int):
        return jsonify({"ok": False, "error": code}), status

def make_security(
    base_dir: Path,
    *,
    legacy_state_file: Path | None = None,
    audit_file: Path | None = None,
) -> KotiBotSecurity:
    if not _env_bool("KOTIBOT_SECURITY", True):
        raise RuntimeError(
            "KOTIBOT_SECURITY cannot be disabled"
        )

    trusted_proxy_networks = _parse_proxy_networks(
        os.environ.get("KOTIBOT_TRUSTED_PROXY_CIDRS", "")
    )
    allowed_origins = _parse_allowed_origins(
        os.environ.get("KOTIBOT_ALLOWED_ORIGINS", "")
    )
    trusted_hosts = _parse_trusted_hosts(
        os.environ.get("KOTIBOT_TRUSTED_HOSTS", "")
    )

    if (
        not allowed_origins
        or any(
            scheme != "https"
            for scheme, _, _ in allowed_origins
        )
    ):
        raise RuntimeError(
            "KOTIBOT_ALLOWED_ORIGINS must contain only exact HTTPS "
            "dashboard origins"
        )

    # A production HTTPS dashboard must never issue an insecure session cookie.
    if not _dashboard_cookie_secure():
        raise RuntimeError(
            "KOTIBOT_COOKIE_SECURE must remain enabled"
        )

    return KotiBotSecurity(SecurityConfig(
        base_dir=Path(base_dir),
        legacy_state_path=(
            Path(legacy_state_file)
            if legacy_state_file is not None
            else None
        ),
        audit_path=(
            Path(audit_file)
            if audit_file is not None
            else None
        ),
        enabled=True,
        trusted_proxy_networks=trusted_proxy_networks,
        allowed_origins=allowed_origins,
        trusted_hosts=trusted_hosts,
    ))

def _cli() -> int:
    source_root = Path(__file__).resolve().parents[2]
    runtime_paths = build_runtime_paths(source_root)
    prepare_runtime_directories(runtime_paths)
    security = make_security(
        runtime_paths.security_state_dir,
        legacy_state_file=(
            source_root
            / "subsystems"
            / "security"
            / "security_state.json"
        ),
        audit_file=runtime_paths.security_audit_file,
    )

    import getpass
    import sys

    cmd = (
        sys.argv[1] if len(sys.argv) > 1 else "status"
    ).strip().lower()

    def dashboard_password():
        password = os.environ.get(
            "KOTIBOT_DASHBOARD_PASSWORD",
            "",
        )

        if password:
            return password

        # Never place a dashboard password in the process argument list.
        return getpass.getpass("Dashboard password: ")

    if cmd == "status":
        print(json.dumps({
            "enabled": security.config.enabled,
            "state_file": str(security.config.state_file),
            "audit_file": str(security.config.audit_file),
            "allowed_origins": [
                {
                    "scheme": scheme,
                    "host": host,
                    "port": port,
                }
                for scheme, host, port
                in security.config.allowed_origins
            ],
            "trusted_hosts": list(
                security.config.trusted_hosts
            ),
            "trusted_proxy_networks": [
                str(network)
                for network
                in security.config.trusted_proxy_networks
            ],
            "dashboard_login_mode": (
                "email_password"
                if security.dashboard_login_configured()
                else "unconfigured"
            ),
            "dashboard_user_count": len(
                security.dashboard_users()
            ),
            "dashboard_session_count": len(
                security.state.get("dashboard_sessions", {})
            ),
            "device_key_count": len(
                security.state.get("device_keys", {})
            ),
        }, indent=2))
        return 0

    if cmd == "issue-device-key":
        if len(sys.argv) < 3:
            print("Usage: python kotibot_security.py issue-device-key DEVICE_ID [--rotate]")
            return 2
        print(json.dumps(security.issue_device_key(sys.argv[2], rotate="--rotate" in sys.argv[3:]), indent=2))
        return 0

    if cmd == "set-dashboard-login":
        email = os.environ.get("KOTIBOT_DASHBOARD_EMAIL") or (sys.argv[2] if len(sys.argv) > 2 else "")
        password = dashboard_password()

        try:
            security.set_dashboard_login(email, password)
        except Exception as e:
            print(f"Failed: {e}")
            return 1

        print(json.dumps({
            "ok": True,
            "dashboard_email": email.strip().lower(),
            "dashboard_login_mode": "email_password",
            "dashboard_user_count": len(security.dashboard_users()),
            "replaced_existing_dashboard_users": True,
        }, indent=2))
        return 0

    if cmd == "add-dashboard-user":
        email = (
            os.environ.get("KOTIBOT_DASHBOARD_EMAIL")
            or (sys.argv[2] if len(sys.argv) > 2 else "")
        )
        # Reuse the protected environment/getpass path. Passwords never
        # belong in argv, shell history, or process listings.
        password = dashboard_password()

        try:
            user = security.add_dashboard_user(email, password)
        except Exception as e:
            print(f"Failed: {e}")
            return 1

        print(json.dumps({
            "ok": True,
            "dashboard_user": user,
            "dashboard_user_count": len(security.dashboard_users()),
            "dashboard_login_mode": "email_password",
        }, indent=2))
        return 0

    if cmd == "list-dashboard-users":
        print(json.dumps({
            "ok": True,
            "dashboard_users": security.list_dashboard_users(),
            "dashboard_user_count": len(security.dashboard_users()),
        }, indent=2))
        return 0

    if cmd == "remove-dashboard-user":
        email = sys.argv[2] if len(sys.argv) > 2 else ""

        try:
            removed = security.remove_dashboard_user(email)
        except Exception as e:
            print(f"Failed: {e}")
            return 1

        print(json.dumps({
            "ok": True,
            "removed": removed,
            "dashboard_email": email.strip().lower(),
            "dashboard_user_count": len(security.dashboard_users()),
        }, indent=2))
        return 0

    print(
        "Commands: status | "
        "issue-device-key DEVICE_ID [--rotate] | "
        "set-dashboard-login EMAIL | "
        "add-dashboard-user EMAIL | "
        "list-dashboard-users | "
        "remove-dashboard-user EMAIL"
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(_cli())

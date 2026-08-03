from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from typing import Any, Optional

from flask import jsonify, request


DASHBOARD_COOKIE = "kotibot_session"
MAX_CLOCK_SKEW_SECONDS = 300
SESSION_SECONDS = 12 * 60 * 60
NONCE_RETENTION_SECONDS = 10 * 60


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


def _came_through_cloudflare() -> bool:
    return bool(
        request.headers.get("CF-Ray")
        or request.headers.get("CF-Connecting-IP")
        or request.headers.get("Cf-Connecting-Ip")
    )


def _client_ip() -> str:
    cf_ip = request.headers.get("CF-Connecting-IP") or request.headers.get("Cf-Connecting-Ip")
    if cf_ip:
        return cf_ip.strip()

    forwarded = request.headers.get("X-Forwarded-For", "")
    return (forwarded.split(",", 1)[0].strip() or request.remote_addr or "")


def _is_local_request() -> bool:
    if _came_through_cloudflare():
        return False

    ip = _client_ip()
    return (
        ip in ("127.0.0.1", "::1")
        or ip.startswith("192.168.")
        or ip.startswith("10.")
        or ip.startswith("172.16.")
    )


@dataclass
class SecurityConfig:
    base_dir: Path
    enabled: bool = False
    trust_local: bool = True
    state_filename: str = "security_state.json"

    @property
    def state_file(self) -> Path:
        return self.base_dir / self.state_filename


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
        self._nonces = {}
        self.state = self._load_state()
        self._ensure_state()

    def init_app(self, app):
        @app.route("/api/security/status", methods=["GET"])
        def security_status():
            ok = self.dashboard_authorized()
            payload = {
                "ok": True,
                "enabled": self.config.enabled,
                "dashboard_authenticated": ok,
                "device_key_count": len(self.state.get("device_keys", {})),
                "dashboard_user_count": len(self.dashboard_users()),
                "trust_local": self.config.trust_local,
                "dashboard_login_mode": "email_password" if self.dashboard_login_configured() else "dashboard_key",
            }
            return jsonify(payload)

        @app.route("/api/security/dashboard-login", methods=["POST"])
        def dashboard_login():
            data = request.get_json(silent=True) or {}

            if self.dashboard_login_configured():
                email = str(data.get("email") or "").strip()
                password = str(data.get("password") or "")

                if not self.verify_dashboard_login(email, password):
                    return self.error("bad_dashboard_login", 401)
            else:
                supplied = str(data.get("key") or request.headers.get("X-Dashboard-Key") or "")

                if not self.verify_dashboard_key(supplied):
                    return self.error("bad_dashboard_key", 401)

            response = jsonify({"ok": True})
            self.set_dashboard_cookie(response)
            return response

        @app.route("/api/security/dashboard-logout", methods=["POST"])
        def dashboard_logout():
            response = jsonify({"ok": True})
            response.delete_cookie(DASHBOARD_COOKIE, path="/")
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

            active_users = self.dashboard_users()
            if email in active_users and len(active_users) <= 1:
                return jsonify({"ok": False, "error": "cannot remove the last dashboard user"}), 400

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


    def _load_state(self) -> dict:
        if not self.config.state_file.exists():
            return {}

        try:
            return json.loads(self.config.state_file.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save_state(self) -> None:
        with self._state_lock:
            self.config.state_file.parent.mkdir(parents=True, exist_ok=True)

            tmp = self.config.state_file.with_name(
                f"{self.config.state_file.name}.{os.getpid()}.{time.time_ns()}.tmp"
            )

            tmp.write_text(json.dumps(self.state, indent=2, sort_keys=True), encoding="utf-8")
            tmp.replace(self.config.state_file)

            try:
                os.chmod(self.config.state_file, 0o600)
            except Exception:
                pass

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

        if "dashboard_key_hash" not in self.state:
            dashboard_key = "nb_dash_" + secrets.token_urlsafe(32)
            self.state["dashboard_key_hash"] = self._hash_secret(dashboard_key)
            self.state["dashboard_key_hint"] = dashboard_key[:14] + "..."
            self.state["_first_dashboard_key"] = dashboard_key
            changed = True

        if "session_secret" not in self.state:
            self.state["session_secret"] = _b64(secrets.token_bytes(32))
            changed = True

        if "device_keys" not in self.state or not isinstance(self.state.get("device_keys"), dict):
            self.state["device_keys"] = {}
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

    def first_dashboard_key(self) -> Optional[str]:
        return self.state.get("_first_dashboard_key")

    def consume_first_dashboard_key(self) -> Optional[str]:
        key = self.state.pop("_first_dashboard_key", None)
        self._save_state()
        return key

    def _hash_secret(self, value: str) -> str:
        return hashlib.sha256(str(value).encode("utf-8")).hexdigest()

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
                    "password_hash": self._hash_secret(password),
                    "created_at": now,
                    "updated_at": now,
                    "status": "active",
                }
            }
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

            users[email] = {
                "password_hash": self._hash_secret(password),
                "created_at": created_at,
                "updated_at": now,
                "status": "active",
            }
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

            users.pop(email, None)
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
            return _safe_eq(self._hash_secret(password), expected_hash)

        expected_email = self._normalize_dashboard_email(self.state.get("dashboard_email"))
        expected_hash = str(self.state.get("dashboard_password_hash") or "")

        return _safe_eq(email, expected_email) and _safe_eq(self._hash_secret(password), expected_hash)


    def verify_dashboard_key(self, supplied: str) -> bool:
        if not supplied:
            return False
        return _safe_eq(self._hash_secret(supplied), self.state.get("dashboard_key_hash", ""))

    def _sign_session_payload(self, payload_b64: str) -> str:
        secret = _unb64(self.state["session_secret"])
        return _b64(hmac.new(secret, payload_b64.encode("utf-8"), hashlib.sha256).digest())

    def set_dashboard_cookie(self, response) -> None:
        payload = {
            "iat": _now(),
            "exp": _now() + SESSION_SECONDS,
            "sid": secrets.token_urlsafe(18),
        }
        payload_b64 = _b64(_json_dumps(payload).encode("utf-8"))
        sig = self._sign_session_payload(payload_b64)
        response.set_cookie(
            DASHBOARD_COOKIE,
            f"{payload_b64}.{sig}",
            max_age=SESSION_SECONDS,
            httponly=True,
            secure=bool(os.environ.get("KOTIBOT_COOKIE_SECURE", "")),
            samesite="Strict",
            path="/",
        )

    def dashboard_authorized(self) -> bool:
        if not self.config.enabled:
            return True

        if self.config.trust_local and _is_local_request():
            return True

        supplied = str(request.headers.get("X-Dashboard-Key") or "")
        if supplied and self.verify_dashboard_key(supplied):
            return True

        token = request.cookies.get(DASHBOARD_COOKIE, "")
        if "." not in token:
            return False

        payload_b64, sig = token.rsplit(".", 1)
        if not _safe_eq(sig, self._sign_session_payload(payload_b64)):
            return False

        try:
            payload = json.loads(_unb64(payload_b64).decode("utf-8"))
        except Exception:
            return False

        return int(payload.get("exp", 0) or 0) >= _now()

    def require_dashboard(self):
        if self.dashboard_authorized():
            return None
        return self.error("dashboard_auth_required", 401)

    def issue_device_key(self, device_id: str, rotate: bool = False) -> dict:
        device_id = str(device_id or "").strip()
        key_id = "nb_dev_" + secrets.token_urlsafe(12)
        secret = "nb_secret_" + secrets.token_urlsafe(32)

        record = self.state.setdefault("device_keys", {}).setdefault(device_id, {})
        old_current = record.get("current")

        if old_current and not rotate:
            return {
                "deviceID": device_id,
                "keyID": old_current.get("key_id"),
                "alreadyIssued": True,
                "message": "Key already exists. Send rotate=true to issue a replacement.",
            }

        if old_current:
            record["previous"] = old_current

        record["current"] = {
            "key_id": key_id,
            "secret": secret,
            "issued_at": _now(),
            "status": "active",
        }
        record["rotated_at"] = _now() if old_current else None

        self._save_state()

        return {
            "deviceID": device_id,
            "keyID": key_id,
            "secret": secret,
            "alreadyIssued": False,
            "storeThisOnClient": True,
        }

    def revoke_device_key(self, device_id: str, key_id: Optional[str] = None) -> None:
        record = self.state.setdefault("device_keys", {}).get(device_id)
        if not record:
            return

        for slot in ("current", "previous"):
            item = record.get(slot)
            if not item:
                continue
            if key_id and item.get("key_id") != key_id:
                continue
            item["status"] = "revoked"
            item["revoked_at"] = _now()

        self._save_state()

    def _device_key_candidates(self, device_id: str) -> list[dict]:
        record = self.state.get("device_keys", {}).get(str(device_id or "").strip(), {})
        items = []
        for slot in ("current", "previous"):
            item = record.get(slot)
            if item and item.get("status") == "active":
                items.append(item)
        return items

    def device_has_key(self, device_id: str) -> bool:
        return bool(self._device_key_candidates(device_id))

    def require_device_signature(self, device_id: str):
        if not self.config.enabled:
            return None

        device_id = str(device_id or request.headers.get("X-Device-ID") or "").strip()
        if not device_id:
            return self.error("missing_deviceID", 400)

        candidates = self._device_key_candidates(device_id)
        if not candidates:
            return self.error("device_key_required", 401)

        key_id = str(
            request.headers.get("X-Koti-Key-ID")
            or request.headers.get("X-Koti-Key-ID")
            or ""
        ).strip()

        timestamp = str(
            request.headers.get("X-Koti-Timestamp")
            or request.headers.get("X-Koti-Timestamp")
            or ""
        ).strip()

        nonce = str(
            request.headers.get("X-Koti-Nonce")
            or request.headers.get("X-Koti-Nonce")
            or ""
        ).strip()

        body_sha = str(
            request.headers.get("X-Koti-Body-SHA256")
            or request.headers.get("X-Koti-Body-SHA256")
            or ""
        ).strip()

        signature = str(
            request.headers.get("X-Koti-Signature")
            or request.headers.get("X-Koti-Signature")
            or ""
        ).strip()

        if not all((key_id, timestamp, nonce, body_sha, signature)):
            return self.error("missing_signature_headers", 401)

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

        nonce_key = f"{device_id}:{key_id}:{nonce}"
        if self._nonce_seen(nonce_key, ts):
            return self.error("replay_detected", 409)

        canonical = "\n".join([
            request.method.upper(),
            request.path,
            timestamp,
            nonce,
            body_sha,
        ]).encode("utf-8")

        matching = [x for x in candidates if x.get("key_id") == key_id]
        if not matching:
            return self.error("unknown_device_key", 401)

        expected = _b64(hmac.new(matching[0]["secret"].encode("utf-8"), canonical, hashlib.sha256).digest())
        if not _safe_eq(signature, expected):
            return self.error("bad_signature", 401)

        return None

    def _nonce_seen(self, nonce_key: str, ts: int) -> bool:
        with self._state_lock:
            now = _now()

            for key, seen_at in list(self._nonces.items()):
                try:
                    if now - int(seen_at) > NONCE_RETENTION_SECONDS:
                        self._nonces.pop(key, None)
                except Exception:
                    self._nonces.pop(key, None)

            if nonce_key in self._nonces:
                return True

            self._nonces[nonce_key] = ts
            return False

    def error(self, code: str, status: int):
        return jsonify({"ok": False, "error": code}), status


def make_security(base_dir: Path) -> KotiBotSecurity:
    enabled = str(os.environ.get("KOTIBOT_SECURITY", "0")).strip().lower() in ("1", "true", "yes", "on")
    trust_local = str(os.environ.get("KOTIBOT_TRUST_LOCAL", "1")).strip().lower() not in ("0", "false", "no", "off")
    return KotiBotSecurity(SecurityConfig(base_dir=Path(base_dir), enabled=enabled, trust_local=trust_local))


def _cli() -> int:
    base_dir = Path(__file__).resolve().parent
    security = make_security(base_dir)

    import sys
    cmd = (sys.argv[1] if len(sys.argv) > 1 else "status").strip().lower()

    if cmd == "status":
        print(json.dumps({
            "enabled_by_env": security.config.enabled,
            "trust_local": security.config.trust_local,
            "state_file": str(security.config.state_file),
            "dashboard_key_hint": security.state.get("dashboard_key_hint"),
            "dashboard_login_mode": "email_password" if security.dashboard_login_configured() else "dashboard_key",
            "dashboard_user_count": len(security.dashboard_users()),
            "device_key_count": len(security.state.get("device_keys", {})),
        }, indent=2))
        return 0

    if cmd == "dashboard-key":
        key = security.first_dashboard_key()
        if not key:
            print("Dashboard key was already displayed/consumed. Rotate by deleting dashboard_key_hash from security_state.json while local-only.")
            return 1
        print(key)
        security.consume_first_dashboard_key()
        return 0

    if cmd == "issue-device-key":
        if len(sys.argv) < 3:
            print("Usage: python kotibot_security.py issue-device-key DEVICE_ID [--rotate]")
            return 2
        print(json.dumps(security.issue_device_key(sys.argv[2], rotate="--rotate" in sys.argv[3:]), indent=2))
        return 0

    if cmd == "set-dashboard-login":
        email = os.environ.get("KOTIBOT_DASHBOARD_EMAIL") or (sys.argv[2] if len(sys.argv) > 2 else "")
        password = os.environ.get("KOTIBOT_DASHBOARD_PASSWORD") or (sys.argv[3] if len(sys.argv) > 3 else "")

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
        email = os.environ.get("KOTIBOT_DASHBOARD_EMAIL") or (sys.argv[2] if len(sys.argv) > 2 else "")
        password = os.environ.get("KOTIBOT_DASHBOARD_PASSWORD") or (sys.argv[3] if len(sys.argv) > 3 else "")

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

    print("Commands: status | dashboard-key | issue-device-key DEVICE_ID [--rotate] | set-dashboard-login EMAIL PASSWORD | add-dashboard-user EMAIL PASSWORD | list-dashboard-users | remove-dashboard-user EMAIL")
    return 2


if __name__ == "__main__":
    raise SystemExit(_cli())

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from threading import Lock, Thread
from typing import Any
from urllib import error as urlerror
from urllib import request as urlrequest
import os

from google.auth.transport.requests import Request
from google.oauth2 import service_account

from server_core.credentials import (
    CredentialMissingError,
    read_json_credential_file,
)

class KotiBotPushQueue:
    """
    Starter queue for notification events.

    Phase 1:
      - server records notification intent locally
      - dashboard/SSE can still show live events

    Phase 2:
      - worker reads queue and sends Android FCM
      - later add APNs/Web Push without changing door/key/camera logic
    """

    def __init__(
        self,
        base_dir: Path,
        filename: str = "notification_queue.jsonl",
        *,
        queue_file: Path | None = None,
        legacy_queue_file: Path | None = None,
        service_account_file: Path | None = None,
    ):
        self.base_dir = Path(base_dir)
        self.queue_file = (
            Path(queue_file)
            if queue_file is not None
            else self.base_dir / filename
        )
        self.legacy_queue_file = (
            Path(legacy_queue_file)
            if legacy_queue_file is not None
            else None
        )
        self.service_account_file = (
            Path(service_account_file)
            if service_account_file is not None
            else self.base_dir / "firebase-service-account.json"
        )
        self._credentials = None
        self._project_id = ""
        self._credential_lock = Lock()
        self._queue_lock = Lock()
        self._migrate_legacy_queue()

    def _prepare_queue_directory(self) -> None:
        self.queue_file.parent.mkdir(
            parents=True,
            exist_ok=True,
            mode=0o700,
        )

        if os.name != "nt":
            os.chmod(self.queue_file.parent, 0o700)

    def _migrate_legacy_queue(self) -> None:
        queue_file = self.queue_file
        legacy_file = self.legacy_queue_file

        if queue_file.is_symlink():
            raise RuntimeError(
                "Notification history must not be a symbolic link"
            )

        if queue_file.exists():
            if not queue_file.is_file():
                raise RuntimeError(
                    "Notification history path must be a regular file"
                )

            if os.name != "nt":
                os.chmod(queue_file, 0o600)
            return

        if legacy_file is None:
            return

        if legacy_file.is_symlink():
            raise RuntimeError(
                "Legacy notification history must not be a symbolic link"
            )

        source_flags = (
            os.O_RDONLY
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0)
        )

        try:
            source_fd = os.open(legacy_file, source_flags)
        except FileNotFoundError:
            return
        except OSError:
            raise RuntimeError(
                "Legacy notification history could not be opened"
            ) from None

        source = os.fdopen(source_fd, "rb")

        self._prepare_queue_directory()
        temporary_file = queue_file.with_name(
            f".{queue_file.name}.{os.getpid()}.{time.time_ns()}.tmp"
        )
        flags = (
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0)
        )

        try:
            with source:
                fd = os.open(temporary_file, flags, 0o600)

                with os.fdopen(fd, "wb") as destination:
                    shutil.copyfileobj(source, destination)
                    destination.flush()
                    os.fsync(destination.fileno())

            if queue_file.exists():
                return

            temporary_file.replace(queue_file)

            if os.name != "nt":
                os.chmod(queue_file, 0o600)
        except OSError:
            raise RuntimeError(
                "Legacy notification history could not be migrated"
            ) from None
        finally:
            try:
                temporary_file.unlink(missing_ok=True)
            except OSError:
                pass

    def _append_queue_item(self, item: dict) -> None:
        encoded = (
            json.dumps(
                item,
                separators=(",", ":"),
                sort_keys=True,
            )
            + "\n"
        )

        if self.queue_file.is_symlink():
            raise RuntimeError(
                "Notification history must not be a symbolic link"
            )

        self._prepare_queue_directory()

        with self._queue_lock:
            fd = os.open(
                self.queue_file,
                os.O_WRONLY
                | os.O_CREAT
                | os.O_APPEND
                | getattr(os, "O_CLOEXEC", 0)
                | getattr(os, "O_NOFOLLOW", 0),
                0o600,
            )

            with os.fdopen(fd, "a", encoding="utf-8") as stream:
                stream.write(encoded)
                stream.flush()

            os.chmod(self.queue_file, 0o600)

    def enqueue(
        self,
        event_type: str,
        title: str,
        body: str,
        deviceID: str = "",
        data: dict[str, Any] | None = None,
        fcm_token: str = "",
    ) -> dict:
        item = {
            "ts": int(time.time()),
            "event_type": str(event_type or ""),
            "deviceID": str(deviceID or ""),
            "title": str(title or ""),
            "body": str(body or ""),
            "data": data or {},
            "status": "queued_fcm_pending" if str(fcm_token or "").strip() else "queued_no_fcm_token",
        }

        self._append_queue_item(item)

        if str(fcm_token or "").strip():
            Thread(
                target=self._send_fcm_background,
                args=(item, fcm_token),
                daemon=True,
            ).start()

        return item

    def _send_fcm_background(self, item: dict, fcm_token: str):
        self.send_fcm(
            token=fcm_token,
            title=item.get("title", ""),
            body=item.get("body", ""),
            data={
                **{
                    "event_type": item.get("event_type", ""),
                    "deviceID": item.get("deviceID", ""),
                    "title": item.get("title", ""),
                    "body": item.get("body", ""),
                },
                **{
                    str(k): "" if v is None else str(v)
                    for k, v in (item.get("data") or {}).items()
                },
            },
        )

    def enqueue_data(
        self,
        event_type: str,
        deviceID: str = "",
        data: dict[str, Any] | None = None,
        fcm_token: str = "",
    ) -> dict:
        item = {
            "ts": int(time.time()),
            "event_type": str(event_type or ""),
            "deviceID": str(deviceID or ""),
            "title": "",
            "body": "",
            "data": data or {},
            "status": "queued_data_fcm_pending" if str(fcm_token or "").strip() else "queued_no_fcm_token",
        }

        self._append_queue_item(item)

        if str(fcm_token or "").strip():
            Thread(
                target=self._send_fcm_data_background,
                args=(item, fcm_token),
                daemon=True,
            ).start()

        return item

    def _send_fcm_data_background(self, item: dict, fcm_token: str):
        self.send_fcm_data(
            token=fcm_token,
            data={
                **{
                    "event_type": item.get("event_type", ""),
                    "deviceID": item.get("deviceID", ""),
                },
                **{
                    str(k): "" if v is None else str(v)
                    for k, v in (item.get("data") or {}).items()
                },
            },
        )

    def _fcm_credentials(self):
        with self._credential_lock:
            if self._credentials is None:
                try:
                    credential_info = read_json_credential_file(
                        self.service_account_file,
                        credential_name="firebase-service-account.json",
                    )
                except CredentialMissingError:
                    return None

                credentials = service_account.Credentials.from_service_account_info(
                    credential_info,
                    scopes=["https://www.googleapis.com/auth/firebase.messaging"],
                )
                self._credentials = credentials
                self._project_id = credentials.project_id or ""

            if not self._credentials.valid:
                self._credentials.refresh(Request())

            return self._credentials

    def send_fcm(self, token: str, title: str, body: str, data: dict[str, str] | None = None) -> dict:
        token = str(token or "").strip()

        if not token:
            return {"ok": False, "skipped": True, "reason": "missing_fcm_token"}

        credentials = self._fcm_credentials()

        if credentials is None:
            return {"ok": False, "skipped": True, "reason": "missing_service_account"}

        project_id = self._project_id

        if not project_id:
            return {"ok": False, "error": "missing_project_id"}

        payload = {
            "message": {
                "token": token,
                "notification": {
                    "title": str(title or "KotiBot Alert"),
                    "body": str(body or title or "KotiBot Alert"),
                },
                "data": {
                    str(k): str(v)
                    for k, v in (data or {}).items()
                    if v is not None
                },
                "android": {
                    "priority": "high",
                    "notification": {
                        "channel_id": "key_client_alerts_v3",
                        "sound": "bell",
                    },
                },
            }
        }

        body_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        req = urlrequest.Request(
            f"https://fcm.googleapis.com/v1/projects/{project_id}/messages:send",
            data=body_bytes,
            method="POST",
            headers={
                "Authorization": f"Bearer {credentials.token}",
                "Content-Type": "application/json; charset=utf-8",
            },
        )

        try:
            with urlrequest.urlopen(req, timeout=8) as response:
                return {
                    "ok": True,
                    "status": response.status,
                    "response": json.loads(response.read().decode("utf-8", errors="replace") or "{}"),
                }
        except urlerror.HTTPError as e:
            return {
                "ok": False,
                "status": e.code,
                "error": e.read().decode("utf-8", errors="replace"),
            }
        except Exception as e:
            return {
                "ok": False,
                "error": str(e),
            }

    def send_fcm_data(self, token: str, data: dict[str, str] | None = None) -> dict:
        token = str(token or "").strip()

        if not token:
            return {"ok": False, "skipped": True, "reason": "missing_fcm_token"}

        credentials = self._fcm_credentials()

        if credentials is None:
            return {"ok": False, "skipped": True, "reason": "missing_service_account"}

        project_id = self._project_id

        if not project_id:
            return {"ok": False, "error": "missing_project_id"}

        payload = {
            "message": {
                "token": token,
                "data": {
                    str(k): str(v)
                    for k, v in (data or {}).items()
                    if v is not None
                },
                "android": {
                    "priority": "high",
                },
            }
        }

        body_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        req = urlrequest.Request(
            f"https://fcm.googleapis.com/v1/projects/{project_id}/messages:send",
            data=body_bytes,
            method="POST",
            headers={
                "Authorization": f"Bearer {credentials.token}",
                "Content-Type": "application/json; charset=utf-8",
            },
        )

        try:
            with urlrequest.urlopen(req, timeout=8) as response:
                return {
                    "ok": True,
                    "status": response.status,
                    "response": json.loads(response.read().decode("utf-8", errors="replace") or "{}"),
                }
        except urlerror.HTTPError as e:
            return {
                "ok": False,
                "status": e.code,
                "error": e.read().decode("utf-8", errors="replace"),
            }
        except Exception as e:
            return {
                "ok": False,
                "error": str(e),
            }

    def recent(self, limit: int = 50) -> list[dict]:
        if self.queue_file.is_symlink():
            raise RuntimeError(
                "Notification history must not be a symbolic link"
            )

        if not self.queue_file.exists():
            return []

        max_bytes = 64 * 1024

        with self.queue_file.open("rb") as f:
            try:
                f.seek(0, 2)
                size = f.tell()
                f.seek(max(0, size - max_bytes))
            except Exception:
                f.seek(0)

            lines = f.read().decode("utf-8", errors="replace").splitlines()[-limit:]

        out = []
        for line in lines:
            try:
                out.append(json.loads(line))
            except Exception:
                pass
        return out

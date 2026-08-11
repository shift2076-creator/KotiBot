"""Protected dynamic credentials associated with KotiBot device identities."""

from __future__ import annotations

from copy import deepcopy
import math
import os
from pathlib import Path
from threading import RLock

from server_core.io import (
    JsonStateMissingError,
    JsonStateReadError,
    json_backup_path,
    read_json_object,
    write_json_atomic_sync,
)


DEVICE_CREDENTIAL_SCHEMA_VERSION = 1
MAX_NOTIFICATION_TOKEN_LENGTH = 8192


def _normalized_device_id(value) -> str:
    device_id = str(value or "").strip()

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
        raise ValueError("invalid deviceID")

    return device_id


def _normalized_token(value) -> str:
    token = str(value or "").strip()

    if (
        not token
        or len(token) > MAX_NOTIFICATION_TOKEN_LENGTH
        or "\x00" in token
        or any(ch.isspace() for ch in token)
    ):
        raise ValueError("invalid notification credential")

    return token


def _normalized_updated_at(value) -> float:
    try:
        updated_at = float(value or 0)
    except (TypeError, ValueError):
        raise ValueError("invalid credential timestamp") from None

    if updated_at < 0 or not math.isfinite(updated_at):
        raise ValueError("invalid credential timestamp")

    return updated_at


def _server_client_items(data: dict) -> list[dict]:
    stored_clients = data.get("clients", [])

    if isinstance(stored_clients, list):
        return [
            dict(item)
            for item in stored_clients
            if isinstance(item, dict)
        ]

    if not isinstance(stored_clients, dict):
        return []

    items: list[dict] = []
    seen_device_ids: set[str] = set()

    for group_items in stored_clients.values():
        if not isinstance(group_items, list):
            continue

        for raw_item in group_items:
            if not isinstance(raw_item, dict):
                continue

            item = dict(raw_item)
            device_id = str(item.get("deviceID") or "").strip()

            if not device_id or device_id in seen_device_ids:
                continue

            seen_device_ids.add(device_id)
            items.append(item)

    return items


class DeviceNotificationCredentialStore:
    """Own protected FCM tokens without exposing them to ordinary state."""

    def __init__(self, state_file: Path):
        self.state_file = Path(state_file)

        if not self.state_file.is_absolute():
            raise RuntimeError(
                "Device notification credential path must be absolute"
            )

        self._lock = RLock()
        self._tokens = self._load()

    def _load(self) -> dict[str, dict]:
        if self.state_file.parent.is_symlink():
            raise RuntimeError(
                "Device notification credential directory must not be a "
                "symbolic link"
            )

        if self.state_file.is_symlink():
            raise RuntimeError(
                "Device notification credential state must not be a "
                "symbolic link"
            )

        try:
            state = read_json_object(self.state_file)
        except JsonStateMissingError:
            if json_backup_path(self.state_file).exists():
                raise RuntimeError(
                    "Device notification credential primary is missing "
                    "while a recovery copy exists"
                ) from None

            return {}
        except JsonStateReadError as exc:
            raise RuntimeError(
                "Device notification credential state could not be read: "
                f"file={exc.filename} reason={exc.reason}"
            ) from None

        if state.get("version") != DEVICE_CREDENTIAL_SCHEMA_VERSION:
            raise RuntimeError(
                "Device notification credential schema is unsupported"
            )

        raw_tokens = state.get("tokens")

        if not isinstance(raw_tokens, dict):
            raise RuntimeError(
                "Device notification credential token map is invalid"
            )

        tokens: dict[str, dict] = {}

        try:
            for device_id, raw_record in raw_tokens.items():
                clean_id = _normalized_device_id(device_id)

                if not isinstance(raw_record, dict):
                    raise ValueError("invalid notification credential record")

                tokens[clean_id] = {
                    "token": _normalized_token(raw_record.get("token")),
                    "updated_at": _normalized_updated_at(
                        raw_record.get("updated_at")
                    ),
                }
        except ValueError as exc:
            raise RuntimeError(
                "Device notification credential state is invalid"
            ) from exc

        if os.name != "nt":
            os.chmod(self.state_file, 0o600)

        return tokens

    def _save_unlocked(self) -> None:
        if self.state_file.parent.is_symlink():
            raise RuntimeError(
                "Device notification credential directory must not be a "
                "symbolic link"
            )

        self.state_file.parent.mkdir(
            mode=0o700,
            parents=True,
            exist_ok=True,
        )

        if os.name != "nt":
            os.chmod(self.state_file.parent, 0o700)

        if self.state_file.is_symlink():
            raise RuntimeError(
                "Device notification credential state must not be a "
                "symbolic link"
            )

        write_json_atomic_sync(
            self.state_file,
            {
                "version": DEVICE_CREDENTIAL_SCHEMA_VERSION,
                "tokens": self._tokens,
            },
        )

    def credential(self, device_id) -> dict:
        try:
            clean_id = _normalized_device_id(device_id)
        except ValueError:
            return {}

        with self._lock:
            record = self._tokens.get(clean_id)
            return deepcopy(record) if isinstance(record, dict) else {}

    def set_token(
        self,
        device_id,
        token,
        updated_at=0,
    ) -> dict:
        clean_id = _normalized_device_id(device_id)
        clean_token = _normalized_token(token)
        clean_updated_at = _normalized_updated_at(updated_at)

        with self._lock:
            current = self._tokens.get(clean_id)

            if (
                isinstance(current, dict)
                and current.get("token") == clean_token
            ):
                return deepcopy(current)

            record = {
                "token": clean_token,
                "updated_at": clean_updated_at,
            }
            self._tokens[clean_id] = record
            self._save_unlocked()
            return deepcopy(record)

    def remove(self, device_id) -> bool:
        try:
            clean_id = _normalized_device_id(device_id)
        except ValueError:
            return False

        with self._lock:
            if clean_id not in self._tokens:
                return False

            self._tokens.pop(clean_id, None)
            self._save_unlocked()
            return True

    def migrate_legacy_server_state(self, server_state_file: Path) -> int:
        """Copy legacy FCM fields and return how many source records exist."""
        source = Path(server_state_file)

        if source.is_symlink():
            raise RuntimeError(
                "Legacy server state must not be a symbolic link"
            )

        try:
            data = read_json_object(source)
        except JsonStateMissingError:
            if json_backup_path(source).exists():
                raise RuntimeError(
                    "Legacy server state primary is missing while a "
                    "recovery copy exists"
                ) from None

            return 0
        except JsonStateReadError as exc:
            raise RuntimeError(
                "Legacy server state could not be read during credential "
                f"migration: file={exc.filename} reason={exc.reason}"
            ) from None

        candidates: dict[str, dict] = {}

        try:
            for item in _server_client_items(data):
                raw_token = item.get("fcm_token")

                if raw_token in (None, ""):
                    continue

                device_id = _normalized_device_id(item.get("deviceID"))
                candidate = {
                    "token": _normalized_token(raw_token),
                    "updated_at": _normalized_updated_at(
                        item.get("fcm_token_at")
                    ),
                }
                previous = candidates.get(device_id)

                if (
                    not isinstance(previous, dict)
                    or candidate["updated_at"] > previous["updated_at"]
                ):
                    candidates[device_id] = candidate
        except ValueError as exc:
            raise RuntimeError(
                "Legacy server notification credential is invalid"
            ) from exc

        changed = 0

        with self._lock:
            for device_id, candidate in candidates.items():
                current = self._tokens.get(device_id)

                if isinstance(current, dict):
                    current_updated_at = _normalized_updated_at(
                        current.get("updated_at")
                    )

                    if current_updated_at >= candidate["updated_at"]:
                        continue

                self._tokens[device_id] = candidate
                changed += 1

            if changed:
                self._save_unlocked()

        return len(candidates)

    def count(self) -> int:
        with self._lock:
            return len(self._tokens)

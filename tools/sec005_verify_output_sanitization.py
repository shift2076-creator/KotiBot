#!/usr/bin/env python3
"""Value-free live verifier for current SEC-005 durable/log sanitization."""

from __future__ import annotations

import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from server_core.paths import build_runtime_paths  # noqa: E402
from tools.sec0045_verify_complete_credential_cutover import (  # noqa: E402
    FORBIDDEN_ORDINARY_STATE_KEYS,
)
from tools.sec005_verify_audit_privacy import (  # noqa: E402
    ALLOWED_ACTORS,
    expected_placeholder,
)


SECRET_LOG_MARKERS = (
    "password",
    "secret",
    "token",
    "credential",
    "authorization",
    "privatekey",
)
MAX_JSONL_BYTES = 16 * 1024 * 1024
MAX_JSONL_RECORDS = 100_000


def _compact_key(name: object) -> str:
    return "".join(
        ch
        for ch in str(name or "").lower()
        if ch.isalnum()
    )


def _scan_forbidden_state_keys(value) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key).strip().lower() in FORBIDDEN_ORDINARY_STATE_KEYS:
                raise RuntimeError(
                    "ordinary state contains a forbidden credential field"
                )

            _scan_forbidden_state_keys(child)
        return

    if isinstance(value, list):
        for child in value:
            _scan_forbidden_state_keys(child)


def verify_ordinary_state(state_root: Path) -> int:
    documents = sorted(state_root.rglob("*.json"))

    for path in documents:
        if path.is_symlink() or not path.is_file():
            raise RuntimeError(
                "ordinary state contains an invalid JSON path"
            )

        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise RuntimeError(
                "ordinary state contains an unreadable JSON document"
            ) from exc

        _scan_forbidden_state_keys(document)

    return len(documents)


def _iter_jsonl(path: Path):
    if path.stat().st_size > MAX_JSONL_BYTES:
        raise RuntimeError("log file is unexpectedly large")

    count = 0

    with path.open("r", encoding="utf-8") as stream:
        for line in stream:
            line = line.strip()

            if not line:
                continue

            count += 1

            if count > MAX_JSONL_RECORDS:
                raise RuntimeError("log file contains too many records")

            try:
                yield json.loads(line)
            except json.JSONDecodeError as exc:
                raise RuntimeError(
                    "log file contains invalid JSON"
                ) from exc


def _scan_notification_record(value) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            compact = _compact_key(key)

            if any(marker in compact for marker in SECRET_LOG_MARKERS):
                raise RuntimeError(
                    "notification history contains a secret-bearing field"
                )

            _scan_notification_record(child)
        return

    if isinstance(value, list):
        for child in value:
            _scan_notification_record(child)


def verify_notification_history(path: Path) -> int:
    if not path.exists():
        return 0

    if path.is_symlink() or not path.is_file():
        raise RuntimeError(
            "notification history path is invalid"
        )

    checked = 0

    for record in _iter_jsonl(path):
        _scan_notification_record(record)
        checked += 1

    return checked


def verify_security_audit(path: Path) -> int:
    candidates = (
        path,
        path.with_name(f"{path.name}.1"),
    )
    checked = 0

    for candidate in candidates:
        if not candidate.exists():
            continue

        if candidate.is_symlink() or not candidate.is_file():
            raise RuntimeError("security audit path is invalid")

        for record in _iter_jsonl(candidate):
            # SEC-006 owns historical pre-sanitization records. SEC-005
            # verifies the current-format writer identified by its actor field.
            if "actor" not in record:
                continue

            if record.get("actor") not in ALLOWED_ACTORS:
                raise RuntimeError(
                    "security audit contains an invalid actor class"
                )

            if "ip" in record or "dashboard_email" in record:
                raise RuntimeError(
                    "security audit contains a legacy identity field"
                )

            for name, value in record.items():
                placeholder = expected_placeholder(name)

                if placeholder is not None and value != placeholder:
                    raise RuntimeError(
                        "security audit contains an unsanitized field"
                    )

            checked += 1

    return checked


def main() -> int:
    paths = build_runtime_paths(REPO_ROOT)

    try:
        ordinary_documents = verify_ordinary_state(
            paths.state_root
        )
        notification_records = verify_notification_history(
            paths.notification_queue_file
        )
        audit_records = verify_security_audit(
            paths.security_audit_file
        )
    except RuntimeError:
        print(
            "SEC-005 output sanitization verification failed; "
            "no values displayed."
        )
        return 1

    if audit_records == 0:
        print(
            "SEC-005 output sanitization verification stopped: "
            "no current-format audit records; no values displayed."
        )
        return 2

    print(
        "SEC-005 output sanitization verification passed: "
        f"ordinary-documents={ordinary_documents}; "
        f"notification-records={notification_records}; "
        f"audit-records={audit_records}; "
        "no values displayed."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Value-free live verifier for SEC-005 security-audit privacy."""

from __future__ import annotations

import json
import os
from pathlib import Path
import stat
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from server_core.paths import build_runtime_paths


SECRET_MARKERS = (
    "password",
    "secret",
    "token",
    "signature",
    "authorization",
    "cookie",
    "nonce",
)

PRIVATE_MARKERS = (
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

PRIVATE_EXACT = {
    "ip",
    "mac",
    "host",
}

ALLOWED_ACTORS = {
    "anonymous",
    "dashboard",
    "device",
    "device-claim",
}


def compact_field_name(name: object) -> str:
    return "".join(
        ch
        for ch in str(name or "").lower()
        if ch.isalnum()
    )


def expected_placeholder(name: object) -> str | None:
    lowered = str(name or "").lower()

    if any(marker in lowered for marker in SECRET_MARKERS):
        return "[redacted]"

    compact = compact_field_name(name)

    if (
        compact in PRIVATE_EXACT
        or any(marker in compact for marker in PRIVATE_MARKERS)
    ):
        return "[private]"

    return None


def iter_records(path: Path):
    with path.open("r", encoding="utf-8") as stream:
        for line in stream:
            line = line.strip()

            if not line:
                continue

            yield json.loads(line)


def main() -> int:
    paths = build_runtime_paths(REPO_ROOT)
    audit_file = paths.security_audit_file
    candidates = (
        audit_file,
        audit_file.with_name(f"{audit_file.name}.1"),
    )

    existing = tuple(
        path
        for path in candidates
        if path.is_file()
    )

    if not existing:
        print("SEC-005 audit privacy verification stopped: no audit file.")
        return 2

    if os.name != "nt":
        for path in existing:
            mode = stat.S_IMODE(path.stat().st_mode)

            if mode != 0o600:
                print(
                    "SEC-005 audit privacy verification failed: "
                    "audit permissions are not private."
                )
                return 1

    checked = 0

    try:
        for path in existing:
            for record in iter_records(path):
                # Old records predate this privacy contract and are intentionally
                # left for SEC-006/history cleanup. New-format records carry
                # only a coarse actor class.
                if "actor" not in record:
                    continue

                checked += 1

                if record.get("actor") not in ALLOWED_ACTORS:
                    print(
                        "SEC-005 audit privacy verification failed: "
                        "unexpected actor class."
                    )
                    return 1

                if "ip" in record or "dashboard_email" in record:
                    print(
                        "SEC-005 audit privacy verification failed: "
                        "legacy raw-identity field present in new-format record."
                    )
                    return 1

                for name, value in record.items():
                    placeholder = expected_placeholder(name)

                    if (
                        placeholder is not None
                        and value != placeholder
                    ):
                        print(
                            "SEC-005 audit privacy verification failed: "
                            "private or secret field was not sanitized."
                        )
                        return 1
    except (OSError, UnicodeError, json.JSONDecodeError):
        print(
            "SEC-005 audit privacy verification failed: "
            "audit file could not be validated."
        )
        return 1

    if checked == 0:
        print(
            "SEC-005 audit privacy verification stopped: "
            "no new-format audit records yet."
        )
        return 2

    print(
        "SEC-005 audit privacy verification passed: "
        f"{checked} new-format record(s) checked; no values displayed."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

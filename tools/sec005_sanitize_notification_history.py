#!/usr/bin/env python3
"""Remove malformed/private WebRTC records from notification history safely."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import time


REPO_ROOT = Path(__file__).resolve().parents[1]

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from server_core.paths import build_runtime_paths  # noqa: E402


MAX_HISTORY_BYTES = 16 * 1024 * 1024
PRIVATE_SIGNALING_KEYS = frozenset({
    "candidate",
    "sdp",
})
PRIVATE_SIGNALING_EVENT_TYPES = frozenset({
    "camera_talk_candidate",
})


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description=(
            "Sanitize KotiBot notification history without displaying "
            "record values."
        ),
    )
    result.add_argument(
        "--apply",
        action="store_true",
        help="create a private rollback copy and atomically rewrite history",
    )
    result.add_argument(
        "--service",
        default="kotibot",
        help="systemd service that must be inactive before --apply",
    )
    return result


def contains_private_signaling(value) -> bool:
    if isinstance(value, dict):
        event_type = str(
            value.get("event_type") or ""
        ).strip().lower()

        if event_type in PRIVATE_SIGNALING_EVENT_TYPES:
            return True

        for key, child in value.items():
            if str(key).strip().lower() in PRIVATE_SIGNALING_KEYS:
                return True

            if contains_private_signaling(child):
                return True

        return False

    if isinstance(value, list):
        return any(
            contains_private_signaling(child)
            for child in value
        )

    return False


def sanitize_payload(payload: bytes):
    retained = []
    total = 0
    malformed = 0
    private_signaling = 0

    for raw_line in payload.splitlines():
        stripped = raw_line.strip()

        if not stripped:
            continue

        total += 1

        try:
            record = json.loads(stripped.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            malformed += 1
            continue

        if contains_private_signaling(record):
            private_signaling += 1
            continue

        retained.append(raw_line + b"\n")

    return (
        b"".join(retained),
        {
            "total": total,
            "retained": len(retained),
            "malformed": malformed,
            "private_signaling": private_signaling,
        },
    )


def require_private_regular_file(path: Path) -> None:
    metadata = path.lstat()

    if stat.S_ISLNK(metadata.st_mode):
        raise RuntimeError(
            "notification history must not be a symbolic link"
        )

    if not stat.S_ISREG(metadata.st_mode):
        raise RuntimeError(
            "notification history must be a regular file"
        )

    if os.name != "nt":
        mode = stat.S_IMODE(metadata.st_mode)

        if mode != 0o600:
            raise RuntimeError(
                "notification history permissions must be 0600"
            )


def service_is_active(service: str) -> bool:
    name = str(service or "").strip()
    allowed = (
        "abcdefghijklmnopqrstuvwxyz"
        "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        "0123456789@_.-"
    )

    if not name or any(ch not in allowed for ch in name):
        raise RuntimeError("systemd service name is invalid")

    try:
        completed = subprocess.run(
            ["systemctl", "is-active", "--quiet", name],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError(
            "could not inspect KotiBot service state"
        ) from exc

    return completed.returncode == 0


def write_private_copy(path: Path, payload: bytes) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
        mode=0o700,
    )

    if os.name != "nt":
        os.chmod(path.parent, 0o700)

    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    fd = os.open(path, flags, 0o600)

    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except Exception:
        path.unlink(missing_ok=True)
        raise

    if os.name != "nt":
        os.chmod(path, 0o600)


def replace_history(path: Path, payload: bytes) -> None:
    temporary = path.with_name(
        f".{path.name}.sec005.{os.getpid()}.{time.time_ns()}.tmp"
    )
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    fd = os.open(temporary, flags, 0o600)

    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())

        os.replace(temporary, path)

        if os.name != "nt":
            os.chmod(path, 0o600)
    finally:
        temporary.unlink(missing_ok=True)


def main(argv=None) -> int:
    args = parser().parse_args(argv)
    paths = build_runtime_paths(REPO_ROOT)
    history = paths.notification_queue_file

    try:
        require_private_regular_file(history)
        payload = history.read_bytes()

        if len(payload) > MAX_HISTORY_BYTES:
            raise RuntimeError(
                "notification history is unexpectedly large"
            )

        sanitized, summary = sanitize_payload(payload)

        print(
            "SEC-005 notification-history preflight: "
            f"records={summary['total']} "
            f"retained={summary['retained']} "
            f"private-signaling={summary['private_signaling']} "
            f"malformed={summary['malformed']}; "
            "no values displayed."
        )

        changes = (
            summary["private_signaling"]
            + summary["malformed"]
        )

        if changes == 0:
            print(
                "SEC-005 notification history already sanitized; "
                "no changes required."
            )
            return 0

        if not args.apply:
            print(
                "SEC-005 notification history requires sanitization; "
                "rerun with --apply while the service is stopped."
            )
            return 2

        if service_is_active(args.service):
            raise RuntimeError(
                "KotiBot service must be stopped before sanitization"
            )

        recovery = (
            paths.data_root
            / "recovery"
            / "sec005"
            / "notification_queue.pre-sec005.jsonl"
        )

        if recovery.exists():
            raise RuntimeError(
                "SEC-005 notification-history rollback copy already exists"
            )

        write_private_copy(recovery, payload)

        if recovery.read_bytes() != payload:
            raise RuntimeError(
                "SEC-005 rollback-copy validation failed"
            )

        replace_history(history, sanitized)
        require_private_regular_file(history)

        rewritten = history.read_bytes()
        validated, post_summary = sanitize_payload(rewritten)

        if (
            rewritten != validated
            or post_summary["malformed"] != 0
            or post_summary["private_signaling"] != 0
        ):
            raise RuntimeError(
                "SEC-005 rewritten notification history failed validation"
            )

        print(
            "SEC-005 notification-history sanitization passed: "
            f"retained={post_summary['retained']} "
            f"removed-private-signaling={summary['private_signaling']} "
            f"removed-malformed={summary['malformed']}; "
            "private rollback copy retained; no values displayed."
        )
        return 0
    except (OSError, RuntimeError) as exc:
        print(
            "SEC-005 notification-history sanitization stopped: "
            f"{exc}; no values displayed."
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

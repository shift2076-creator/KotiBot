#!/usr/bin/env python3
"""Verify SEC-004.3 storage ownership without displaying credentials."""

from __future__ import annotations

import argparse
import math
import os
from pathlib import Path
import stat
import sys


SOURCE_ROOT = Path(__file__).resolve().parents[1]

if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from server_core.io import (  # noqa: E402
    JsonStateReadError,
    read_json_object,
)
from server_core.paths import build_runtime_paths  # noqa: E402


FORBIDDEN_ORDINARY_STATE_KEYS = frozenset({
    "fcm_token",
    "fcm_token_at",
})
SECURITY_DICTIONARY_KEYS = (
    "dashboard_sessions",
    "device_keys",
    "device_enrollments",
)


def _parser() -> argparse.ArgumentParser:
    paths = build_runtime_paths(SOURCE_ROOT)
    parser = argparse.ArgumentParser(
        description=(
            "Verify that dashboard/device authentication state and FCM "
            "tokens are protected without printing their values."
        ),
    )
    parser.add_argument(
        "--security-state",
        type=Path,
        default=paths.security_state_file,
    )
    parser.add_argument(
        "--notification-credentials",
        type=Path,
        default=paths.device_notification_credentials_file,
    )
    parser.add_argument(
        "--server-state",
        type=Path,
        default=paths.server_state_file,
    )
    parser.add_argument(
        "--minimum-tokens",
        type=int,
        default=0,
        help="require at least this many protected FCM token records",
    )
    return parser


def _read_required_object(path: Path, label: str) -> dict:
    path = Path(path)

    if path.is_symlink():
        raise RuntimeError(f"{label} must not be a symbolic link")

    try:
        return read_json_object(path)
    except JsonStateReadError as exc:
        raise RuntimeError(
            f"{label} could not be read: reason={exc.reason}"
        ) from None


def _require_private(path: Path, *, directory: bool, label: str) -> None:
    path = Path(path)

    if path.is_symlink():
        raise RuntimeError(f"{label} must not be a symbolic link")

    expected = 0o700 if directory else 0o600

    if directory:
        valid_kind = path.is_dir()
    else:
        valid_kind = path.is_file()

    if not valid_kind:
        raise RuntimeError(f"{label} is missing")

    if os.name != "nt":
        actual = stat.S_IMODE(path.stat().st_mode)

        if actual != expected:
            raise RuntimeError(
                f"{label} permissions must be {expected:o}, found {actual:o}"
            )


def _contains_forbidden_key(value) -> bool:
    if isinstance(value, dict):
        return any(
            key in FORBIDDEN_ORDINARY_STATE_KEYS
            or _contains_forbidden_key(item)
            for key, item in value.items()
        )

    if isinstance(value, list):
        return any(_contains_forbidden_key(item) for item in value)

    return False


def _require_external(path: Path, label: str) -> None:
    resolved = Path(path).resolve(strict=False)
    source = SOURCE_ROOT.resolve(strict=False)

    if resolved == source or source in resolved.parents:
        raise RuntimeError(f"{label} must be outside the source tree")


def _notification_token_count(path: Path) -> int:
    path = Path(path)
    _require_private(
        path.parent,
        directory=True,
        label="notification credential directory",
    )

    if path.is_symlink():
        raise RuntimeError(
            "notification credential state must not be a symbolic link"
        )

    if not path.exists():
        return 0

    _require_private(
        path,
        directory=False,
        label="notification credential state",
    )
    state = _read_required_object(path, "notification credential state")

    if state.get("version") != 1 or not isinstance(state.get("tokens"), dict):
        raise RuntimeError("notification credential schema is invalid")

    for record in state["tokens"].values():
        if not isinstance(record, dict):
            raise RuntimeError("notification credential record is invalid")

        token = record.get("token")

        if (
            not isinstance(token, str)
            or not token.strip()
            or any(character.isspace() for character in token)
        ):
            raise RuntimeError("notification credential record is invalid")

        try:
            updated_at = float(record.get("updated_at") or 0)
        except (TypeError, ValueError):
            raise RuntimeError(
                "notification credential timestamp is invalid"
            ) from None

        if updated_at < 0 or not math.isfinite(updated_at):
            raise RuntimeError("notification credential timestamp is invalid")

    return len(state["tokens"])


def verify_cutover(
    *,
    security_state_file: Path,
    notification_credentials_file: Path,
    server_state_file: Path,
    minimum_tokens: int = 0,
) -> dict[str, int]:
    if minimum_tokens < 0:
        raise RuntimeError("minimum token count must not be negative")

    for path, label in (
        (security_state_file, "security state"),
        (notification_credentials_file, "notification credential state"),
        (server_state_file, "server state"),
    ):
        _require_external(path, label)

    _require_private(
        Path(security_state_file).parent,
        directory=True,
        label="security state directory",
    )
    _require_private(
        security_state_file,
        directory=False,
        label="security state",
    )
    security_state = _read_required_object(
        security_state_file,
        "security state",
    )

    if (
        not isinstance(security_state.get("session_secret"), str)
        or not security_state["session_secret"].strip()
    ):
        raise RuntimeError("security session secret is missing")

    for key in SECURITY_DICTIONARY_KEYS:
        if not isinstance(security_state.get(key), dict):
            raise RuntimeError(f"security state field is invalid: {key}")

    dashboard_users = security_state.get("dashboard_users", {})

    if not isinstance(dashboard_users, dict):
        raise RuntimeError(
            "security state field is invalid: dashboard_users"
        )

    token_count = _notification_token_count(
        notification_credentials_file
    )

    if token_count < minimum_tokens:
        raise RuntimeError(
            "protected notification credential count is below the minimum"
        )

    server_state = _read_required_object(server_state_file, "server state")

    if _contains_forbidden_key(server_state):
        raise RuntimeError(
            "ordinary server state still contains notification credentials"
        )

    return {
        "dashboard_users": len(dashboard_users),
        "dashboard_sessions": len(security_state["dashboard_sessions"]),
        "device_keys": len(security_state["device_keys"]),
        "device_enrollments": len(security_state["device_enrollments"]),
        "notification_tokens": token_count,
    }


def main(argv=None) -> int:
    args = _parser().parse_args(argv)

    try:
        counts = verify_cutover(
            security_state_file=args.security_state,
            notification_credentials_file=args.notification_credentials,
            server_state_file=args.server_state,
            minimum_tokens=args.minimum_tokens,
        )
    except RuntimeError as exc:
        print(f"SEC-004.3 cutover verification failed: {exc}")
        return 1

    print("SEC-004.3 cutover verification passed.")
    print(
        "protected-auth-state: ready "
        f"(users={counts['dashboard_users']} "
        f"sessions={counts['dashboard_sessions']} "
        f"device-keys={counts['device_keys']} "
        f"enrollments={counts['device_enrollments']})"
    )
    print(
        "protected-notification-credentials: ready "
        f"(tokens={counts['notification_tokens']})"
    )
    print("ordinary-server-state: sanitized")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

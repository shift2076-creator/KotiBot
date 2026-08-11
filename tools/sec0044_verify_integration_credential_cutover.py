#!/usr/bin/env python3
"""Verify SEC-004.4 integration credential storage without printing values."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import stat
import sys


SOURCE_ROOT = Path(__file__).resolve().parents[1]

if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from server_core.credentials import (  # noqa: E402
    default_credential_directory,
    read_json_credential_file,
)
from server_core.integration_credentials import (  # noqa: E402
    INTEGRATION_CREDENTIAL_NAME,
    validate_integration_credential_document,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Verify protected SEC-004.4 integration credentials without "
            "displaying credential values."
        ),
    )
    parser.add_argument(
        "--credential-file",
        type=Path,
        default=(
            default_credential_directory()
            / INTEGRATION_CREDENTIAL_NAME
        ),
        help="protected integration credential document",
    )
    parser.add_argument(
        "--require-cloudflare",
        action="store_true",
        help="fail unless a protected Cloudflare API token is configured",
    )
    parser.add_argument(
        "--require-camera-talk",
        action="store_true",
        help=(
            "fail unless a complete protected TURN pair or composite ICE "
            "server document is configured"
        ),
    )
    return parser


def _validate_private_parent(path: Path) -> None:
    parent = path.parent

    try:
        metadata = parent.lstat()
    except OSError as exc:
        raise RuntimeError(
            "Integration credential directory could not be inspected"
        ) from exc

    if stat.S_ISLNK(metadata.st_mode):
        raise RuntimeError(
            "Integration credential directory must not be a symbolic link"
        )

    if not stat.S_ISDIR(metadata.st_mode):
        raise RuntimeError(
            "Integration credential parent must be a directory"
        )

    if os.name != "nt" and stat.S_IMODE(metadata.st_mode) & 0o027:
        raise RuntimeError(
            "Integration credential directory permissions are not private"
        )


def verify_integration_credential_cutover(
    path: Path,
    *,
    require_cloudflare: bool = False,
    require_camera_talk: bool = False,
) -> tuple[str, ...]:
    path = Path(path).expanduser()

    if not path.is_absolute():
        raise RuntimeError(
            "Integration credential path must be absolute"
        )

    _validate_private_parent(path)
    document = read_json_credential_file(
        path,
        credential_name=INTEGRATION_CREDENTIAL_NAME,
    )
    normalized = validate_integration_credential_document(document)
    has_cloudflare = bool(normalized.get("cloudflare_api_token"))
    has_turn_username = bool(
        normalized.get("camera_talk_turn_username")
    )
    has_turn_credential = bool(
        normalized.get("camera_talk_turn_credential")
    )
    has_turn_pair = has_turn_username and has_turn_credential
    ice_server_count = len(
        normalized.get("camera_talk_ice_servers", [])
    )
    has_camera_talk = has_turn_pair or ice_server_count > 0

    if has_turn_username != has_turn_credential:
        raise RuntimeError(
            "Protected camera-talk TURN credential pair is incomplete"
        )

    if require_cloudflare and not has_cloudflare:
        raise RuntimeError(
            "Protected Cloudflare API token is not configured"
        )

    if require_camera_talk and not has_camera_talk:
        raise RuntimeError(
            "Protected camera-talk credentials are not configured"
        )

    return (
        "protected-integration-document: ready",
        "cloudflare-api-token: "
        + ("ready" if has_cloudflare else "not-configured"),
        "camera-talk-turn-pair: "
        + ("ready" if has_turn_pair else "not-configured"),
        "camera-talk-composite-ice: "
        + (
            f"ready (servers={ice_server_count})"
            if ice_server_count
            else "not-configured"
        ),
    )


def main() -> int:
    args = _parser().parse_args()

    try:
        statuses = verify_integration_credential_cutover(
            args.credential_file,
            require_cloudflare=args.require_cloudflare,
            require_camera_talk=args.require_camera_talk,
        )
    except RuntimeError as exc:
        print(f"SEC-004.4 cutover verification stopped: {exc}")
        return 1

    print("SEC-004.4 cutover verification passed.")

    for status in statuses:
        print(status)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

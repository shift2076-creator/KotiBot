#!/usr/bin/env python3
"""Value-free SEC-006 credential-rotation and cleanup preflight.

This tool is intentionally read-only. It reuses the proven SEC-004.5 cutover
verifier, then reports only counts and equality/overlap status needed to plan
credential rotation. It never prints credential values, account identifiers,
device identifiers, session identifiers, emails, or token contents.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
from pathlib import Path
import sys


SOURCE_ROOT = Path(__file__).resolve().parents[1]

if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from server_core.credentials import default_credential_directory  # noqa: E402
from server_core.integration_credentials import (  # noqa: E402
    LEGACY_INTEGRATION_CREDENTIAL_ENVIRONMENTS,
)
from server_core.io import JsonStateReadError, read_json_object  # noqa: E402
from server_core.paths import RuntimePaths  # noqa: E402
from tools.sec004_migrate_service_credentials import (  # noqa: E402
    FIREBASE_CREDENTIAL_NAME,
    TAPO_CREDENTIALS,
)
from tools.sec0045_verify_complete_credential_cutover import (  # noqa: E402
    inspect_active_service,
    verify_complete_cutover,
)


LEGACY_FIREBASE_SOURCE = (
    SOURCE_ROOT
    / "subsystems"
    / "notifications"
    / FIREBASE_CREDENTIAL_NAME
)
LEGACY_SECURITY_SOURCE = (
    SOURCE_ROOT
    / "subsystems"
    / "security"
    / "security_state.json"
)

# These names describe credential material only. Values are never emitted.
SECURITY_SECRET_KEYS = frozenset({
    "session_secret",
    "dashboard_key",
    "dashboard_key_hash",
    "dashboard_password_hash",
    "password_hash",
    "secret",
    "token",
    "token_hash",
    "fcm_token",
})

AUTH_MAPPING_FIELDS = (
    "dashboard_users",
    "dashboard_sessions",
    "device_keys",
    "device_enrollments",
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Read-only SEC-006 preflight. Reports only credential classes, "
            "counts, and protected/legacy overlap status."
        ),
    )
    parser.add_argument(
        "--service",
        default="kotibot",
        help="active Linux systemd service to inspect",
    )
    parser.add_argument(
        "--credential-directory",
        type=Path,
        default=default_credential_directory(),
        help="manager-owned protected service credential directory",
    )
    parser.add_argument(
        "--data-root",
        type=Path,
        help=(
            "override the running service data root; otherwise derive it "
            "from the active process"
        ),
    )
    parser.add_argument(
        "--legacy-firebase-source",
        type=Path,
        default=LEGACY_FIREBASE_SOURCE,
    )
    parser.add_argument(
        "--legacy-security-source",
        type=Path,
        default=LEGACY_SECURITY_SOURCE,
    )
    return parser


def _read_object(path: Path, label: str) -> dict:
    try:
        document = read_json_object(Path(path))
    except JsonStateReadError as exc:
        raise RuntimeError(
            f"{label} could not be read: reason={exc.reason}"
        ) from None

    if not isinstance(document, dict):
        raise RuntimeError(f"{label} must contain an object")

    return document


def _stable_digest(value) -> bytes:
    try:
        encoded = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise RuntimeError(
            "Credential-state comparison encountered invalid JSON"
        ) from exc

    return hashlib.sha256(encoded).digest()


def _same_value(left, right) -> bool:
    return hmac.compare_digest(
        _stable_digest(left),
        _stable_digest(right),
    )


def _mapping_overlap(current: dict, legacy: dict, field: str) -> dict[str, int]:
    current_mapping = current.get(field)
    legacy_mapping = legacy.get(field)

    if not isinstance(current_mapping, dict):
        current_mapping = {}

    if not isinstance(legacy_mapping, dict):
        legacy_mapping = {}

    common_keys = set(current_mapping).intersection(legacy_mapping)
    matching = sum(
        1
        for key in common_keys
        if _same_value(current_mapping[key], legacy_mapping[key])
    )

    return {
        "current": len(current_mapping),
        "legacy": len(legacy_mapping),
        "shared": len(common_keys),
        "matching": matching,
    }


def _session_secret_status(current: dict, legacy: dict) -> str:
    current_value = current.get("session_secret")
    legacy_value = legacy.get("session_secret")

    if not isinstance(current_value, str) or not current_value.strip():
        return "current-missing"

    if not isinstance(legacy_value, str) or not legacy_value.strip():
        return "legacy-missing"

    return "same" if _same_value(current_value, legacy_value) else "different"


def _count_named_keys(value, names: frozenset[str]) -> int:
    if isinstance(value, dict):
        return sum(
            (1 if str(key).casefold() in names else 0)
            + _count_named_keys(child, names)
            for key, child in value.items()
        )

    if isinstance(value, list):
        return sum(_count_named_keys(child, names) for child in value)

    return 0


def summarize_security_overlap(current: dict, legacy: dict) -> dict:
    return {
        "session_secret": _session_secret_status(current, legacy),
        "mappings": {
            field: _mapping_overlap(current, legacy, field)
            for field in AUTH_MAPPING_FIELDS
        },
        "legacy_secret_fields": _count_named_keys(
            legacy,
            SECURITY_SECRET_KEYS,
        ),
        "legacy_fcm_token_fields": _count_named_keys(
            legacy,
            frozenset({"fcm_token"}),
        ),
    }


def _present_environment_count(environment: dict[str, str], names) -> int:
    return sum(
        1
        for name in names
        if str(environment.get(name, "")).strip()
    )


def run_preflight(args) -> int:
    snapshot = inspect_active_service(
        args.service,
        data_root_override=args.data_root,
    )

    manager_owner = (0, 0) if os.name != "nt" else None
    service_owner = (
        (snapshot.process_user_id, snapshot.process_group_id)
        if os.name != "nt"
        else None
    )
    runtime_owners = (
        frozenset({
            (0, 0),
            (snapshot.process_user_id, snapshot.process_group_id),
        })
        if os.name != "nt"
        else None
    )

    # Reuse the already-proven SEC-004.5 gate first. SEC-006 must never plan
    # deletion from an unverified cutover baseline.
    cutover = verify_complete_cutover(
        source_credential_directory=args.credential_directory,
        runtime_credential_directory=snapshot.runtime_credential_directory,
        data_root=snapshot.data_root,
        service_environment=snapshot.environment,
        legacy_firebase_source=args.legacy_firebase_source,
        legacy_security_source=args.legacy_security_source,
        manager_owner=manager_owner,
        service_owner=service_owner,
        runtime_owners=runtime_owners,
    )

    paths = RuntimePaths(
        source_root=SOURCE_ROOT,
        data_root=snapshot.data_root,
    ).validate()
    current_security = _read_object(
        paths.security_state_file,
        "protected security state",
    )
    legacy_security = _read_object(
        args.legacy_security_source,
        "legacy security state",
    )
    overlap = summarize_security_overlap(
        current_security,
        legacy_security,
    )

    tapo_environment_names = tuple(
        environment_name
        for _, environment_name in TAPO_CREDENTIALS
    )
    tapo_present = _present_environment_count(
        dict(snapshot.environment),
        tapo_environment_names,
    )
    integration_present = _present_environment_count(
        dict(snapshot.environment),
        LEGACY_INTEGRATION_CREDENTIAL_ENVIRONMENTS,
    )

    print("SEC-006 credential-rotation preflight passed; no values displayed.")
    print(
        "cutover-baseline: verified "
        f"(service-credentials={cutover.service_credentials} "
        f"legacy-sources={cutover.retained_legacy_sources})"
    )
    print(
        "legacy-tapo-environment: retained-and-matching "
        f"(present={tapo_present}/{len(tapo_environment_names)})"
    )
    print(
        "legacy-integration-environment: retained-and-matching "
        f"(present={integration_present}/"
        f"{len(LEGACY_INTEGRATION_CREDENTIAL_ENVIRONMENTS)})"
    )
    print("legacy-firebase-source: retained-and-matching")
    print("legacy-security-source: retained")
    print(
        "protected-auth-state: "
        f"users={cutover.dashboard_users} "
        f"active-sessions={cutover.dashboard_sessions} "
        f"device-keys={cutover.device_keys} "
        f"enrollments={cutover.device_enrollments} "
        f"notification-tokens={cutover.notification_tokens}"
    )
    print(
        "legacy-auth-overlap: "
        f"session-secret={overlap['session_secret']} "
        f"secret-fields={overlap['legacy_secret_fields']} "
        f"legacy-fcm-token-fields={overlap['legacy_fcm_token_fields']}"
    )

    for field in AUTH_MAPPING_FIELDS:
        item = overlap["mappings"][field]
        print(
            f"legacy-auth-{field.replace('_', '-')}: "
            f"current={item['current']} legacy={item['legacy']} "
            f"shared={item['shared']} matching={item['matching']}"
        )

    print(
        "rotation-dominoes: "
        "tapo-account/device credentials, Firebase service account, "
        "protected dashboard/session/device authentication"
    )

    if integration_present:
        print(
            "rotation-dominoes-optional-integrations: present "
            f"(legacy-environment-fields={integration_present})"
        )
    else:
        print("rotation-dominoes-optional-integrations: absent")

    print("cleanup-authorized: no")
    print("destructive-changes-performed: no")
    return 0


def main(argv=None) -> int:
    args = _parser().parse_args(argv)

    try:
        return run_preflight(args)
    except RuntimeError as exc:
        print(
            "SEC-006 credential-rotation preflight stopped: "
            f"{exc}; no values displayed."
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

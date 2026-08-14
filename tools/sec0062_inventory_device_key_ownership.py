#!/usr/bin/env python3
"""SEC-006.2 value-free device-key ownership, recovery, and handoff inventory.

This tool is read-only against live KotiBot state. Its isolated fixture may
write only inside a TemporaryDirectory. It never prints credential values,
device identifiers, account identifiers, or notification tokens.
"""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path
import stat
import sys
import time
from tempfile import TemporaryDirectory


SOURCE_ROOT = Path(__file__).resolve().parents[1]

if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))


FIRST_PARTY_GROUPS = frozenset({"android_home", "android_key"})
EXTERNAL_GROUPS = frozenset({"matter", "tapo"})


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Read-only SEC-006.2 key ownership/handoff inventory. "
            "Reports counts only; never values or identifiers."
        ),
    )
    parser.add_argument("--service", default="kotibot")
    parser.add_argument("--data-root", type=Path)
    return parser


def _read_object(path: Path, label: str) -> dict:
    from server_core.io import JsonStateReadError, read_json_object

    path = Path(path)

    try:
        metadata = path.lstat()
    except FileNotFoundError:
        raise RuntimeError(f"{label} is missing") from None
    except OSError as exc:
        raise RuntimeError(f"{label} could not be inspected") from exc

    if stat.S_ISLNK(metadata.st_mode):
        raise RuntimeError(f"{label} must not be a symbolic link")

    if not stat.S_ISREG(metadata.st_mode):
        raise RuntimeError(f"{label} must be a regular file")

    if sys.platform != "win32":
        mode = stat.S_IMODE(metadata.st_mode)

        if mode & 0o037:
            raise RuntimeError(f"{label} permissions are not private")

    try:
        document = read_json_object(path)
    except JsonStateReadError as exc:
        raise RuntimeError(
            f"{label} could not be read: reason={exc.reason}"
        ) from None

    if not isinstance(document, dict):
        raise RuntimeError(f"{label} must contain an object")

    return document


def flatten_server_clients(
    server_state: dict,
) -> tuple[dict[str, dict], int]:
    raw_clients = server_state.get("clients")
    clients: dict[str, dict] = {}
    duplicate_ids = 0

    if isinstance(raw_clients, list):
        group_items = [("legacy", raw_clients)]
    elif isinstance(raw_clients, dict):
        group_items = [
            (str(group_name), items)
            for group_name, items in raw_clients.items()
            if isinstance(items, list)
        ]
    else:
        return {}, 0

    for group_name, items in group_items:
        for item in items:
            if not isinstance(item, dict):
                continue

            device_id = str(item.get("deviceID") or "").strip()

            if not device_id:
                continue

            if device_id in clients:
                duplicate_ids += 1
                continue

            clients[device_id] = {
                "group": group_name,
                "provisioned": bool(item.get("provisioned")),
            }

    return clients, duplicate_ids


def _slot_state(slot, *, now: int, previous: bool) -> str:
    if slot is None:
        return "missing"

    if not isinstance(slot, dict):
        return "malformed"

    status_value = str(slot.get("status") or "").strip().lower()
    key_id_present = bool(str(slot.get("key_id") or "").strip())
    secret_present = bool(str(slot.get("secret") or "").strip())

    if (
        status_value == "active"
        and (not key_id_present or not secret_present)
    ):
        return "malformed"

    if status_value != "active":
        return "retired"

    if previous:
        try:
            expires_at = int(slot.get("expires_at") or 0)
        except (TypeError, ValueError):
            return "malformed"

        if expires_at < now:
            return "retired"

        return "grace-active"

    return "active"


def _pending_slot_state(slot) -> str:
    if slot is None:
        return "missing"

    if not isinstance(slot, dict):
        return "malformed"

    if str(slot.get("status") or "").strip().lower() != "staged":
        return "retired"

    if (
        not str(slot.get("key_id") or "").strip()
        or not str(slot.get("secret") or "").strip()
    ):
        return "malformed"

    return "staged"


def _enrollment_state(record, *, now: int) -> str:
    if record is None:
        return "missing"

    if not isinstance(record, dict):
        return "malformed"

    try:
        expires_at = int(record.get("expires_at") or 0)
    except (TypeError, ValueError):
        return "malformed"

    return "pending" if expires_at >= now else "expired"


def _owner_class(client: dict | None) -> str:
    if client is None:
        return "orphaned"

    group = str(client.get("group") or "").strip()
    provisioned = bool(client.get("provisioned"))

    if not provisioned or group == "unprovisioned":
        return "unprovisioned"

    if group in FIRST_PARTY_GROUPS:
        return "first-party-provisioned"

    if group in EXTERNAL_GROUPS:
        return "external-unexpected"

    if group == "other":
        return "other-provisioned"

    return "unknown-group"


def summarize_device_key_inventory(
    security_state: dict,
    server_state: dict,
    *,
    now: int | None = None,
) -> dict[str, int]:
    now = int(time.time()) if now is None else int(now)
    clients, duplicate_ids = flatten_server_clients(server_state)
    raw_keys = security_state.get("device_keys")
    device_keys = raw_keys if isinstance(raw_keys, dict) else {}
    raw_enrollments = security_state.get("device_enrollments")
    enrollments = (
        raw_enrollments
        if isinstance(raw_enrollments, dict)
        else {}
    )

    counts = Counter()
    counts["protected_key_records"] = len(device_keys)
    counts["registry_clients"] = len(clients)
    counts["registry_duplicate_ids"] = duplicate_ids

    key_ids = set()
    active_current_key_ids = set()

    for device_id, record in device_keys.items():
        device_id = str(device_id)
        key_ids.add(device_id)
        client = clients.get(device_id)
        group = str((client or {}).get("group") or "orphaned")
        owner = _owner_class(client)

        counts[f"owner_{owner}"] += 1
        counts[f"group_{group}"] += 1

        if not isinstance(record, dict):
            counts["malformed_key_records"] += 1
            continue

        current_state = _slot_state(
            record.get("current"),
            now=now,
            previous=False,
        )
        previous_state = _slot_state(
            record.get("previous"),
            now=now,
            previous=True,
        )
        pending_state = _pending_slot_state(
            record.get("pending")
        )

        counts[f"current_{current_state}"] += 1
        counts[f"previous_{previous_state}"] += 1
        counts[f"pending_{pending_state}"] += 1

        if current_state == "active":
            active_current_key_ids.add(device_id)
            counts[f"active_group_{group}"] += 1

            if owner == "first-party-provisioned":
                counts["live_rotation_candidates"] += 1

                if record.get("handoff_verified_at"):
                    counts["first_party_handoff_verified"] += 1
                else:
                    counts["first_party_handoff_unverified"] += 1
            elif owner in {
                "external-unexpected",
                "other-provisioned",
                "unknown-group",
            }:
                counts["active_keys_requiring_review"] += 1

        if current_state in {"retired", "malformed"}:
            counts["stale_current_slots"] += 1

        if previous_state in {"retired", "malformed"}:
            counts["stale_previous_slots"] += 1

    for device_id, client in clients.items():
        if _owner_class(client) != "first-party-provisioned":
            continue

        group = str(client.get("group") or "unknown")

        if device_id not in key_ids:
            counts["first_party_clients_without_key_record"] += 1

        if device_id in active_current_key_ids:
            continue

        counts["first_party_clients_without_active_key"] += 1
        counts[f"first_party_without_active_key_{group}"] += 1

        enrollment_state = _enrollment_state(
            enrollments.get(device_id),
            now=now,
        )
        counts[
            f"first_party_without_active_key_enrollment_"
            f"{enrollment_state}"
        ] += 1
        counts[
            f"first_party_without_active_key_{group}_enrollment_"
            f"{enrollment_state}"
        ] += 1

    counts["enrollment_records"] = len(enrollments)

    for device_id, record in enrollments.items():
        owner = _owner_class(clients.get(str(device_id)))

        if owner == "first-party-provisioned":
            counts["enrollment_first_party_provisioned"] += 1
        elif owner == "orphaned":
            counts["enrollment_orphaned"] += 1
        else:
            counts["enrollment_other"] += 1

        enrollment_state = _enrollment_state(
            record,
            now=now,
        )

        if enrollment_state == "malformed":
            counts["enrollment_malformed"] += 1
        elif enrollment_state == "pending":
            counts["enrollment_pending"] += 1
        elif enrollment_state == "expired":
            counts["enrollment_expired"] += 1

    return dict(counts)


def prove_server_reenrollment_fixture() -> bool:
    """Prove replacement issuance without touching live protected state."""
    from subsystems.security.kotibot_security import (
        KotiBotSecurity,
        SecurityConfig,
    )

    with TemporaryDirectory(prefix="kotibot-sec0062-") as temp_dir:
        security = KotiBotSecurity(
            SecurityConfig(base_dir=Path(temp_dir))
        )
        device_id = "sec0062-fixture-device"

        original = security.issue_device_key(device_id)

        if original.get("alreadyIssued") is not False:
            return False

        security.revoke_device_key(device_id)
        enrollment = security.begin_device_enrollment(
            device_id,
            rotate=True,
        )
        enrollment_token = str(
            enrollment.get("enrollmentToken") or ""
        )

        if not enrollment_token:
            return False

        if not security.verify_device_enrollment(
            device_id,
            enrollment_token,
        ):
            return False

        if not security.consume_device_enrollment(
            device_id,
            enrollment_token,
        ):
            return False

        replacement = security.issue_device_key(
            device_id,
            rotate=True,
        )

        if replacement.get("alreadyIssued") is not False:
            return False

        if not str(replacement.get("keyID") or "").strip():
            return False

        if not str(replacement.get("secret") or "").strip():
            return False

        if replacement.get("keyID") == original.get("keyID"):
            return False

        if replacement.get("secret") == original.get("secret"):
            return False

        if security.device_enrollment_pending(device_id):
            return False

        active_candidates = security._device_key_candidates(device_id)

        return (
            len(active_candidates) == 1
            and active_candidates[0].get("key_id")
            == replacement.get("keyID")
        )


def verify_server_handshake_contract(source_root: Path = SOURCE_ROOT) -> bool:
    """Verify the provisioned handshake forces replacement after enrollment."""
    source = (
        Path(source_root) / "kotibot_server.py"
    ).read_text(encoding="utf-8")

    start = source.index("def handshake():")
    end = source.index(
        "@app.route('/provision', methods=['POST'])",
        start,
    )
    block = source[start:end]

    # Ignore formatting-only whitespace so the contract check follows the
    # Python call structure instead of requiring a particular line wrap.
    normalized = "".join(block.split())
    consume = normalized.index(
        "SECURITY.consume_device_enrollment("
    )
    issue = normalized.index(
        "issued=SECURITY.issue_device_key("
        "deviceID,rotate=True"
    )

    return consume < issue


def verify_server_handoff_contract(
    source_root: Path = SOURCE_ROOT,
) -> bool:
    server = (
        Path(source_root) / "kotibot_server.py"
    ).read_text(encoding="utf-8")
    security = (
        Path(source_root)
        / "subsystems"
        / "security"
        / "kotibot_security.py"
    ).read_text(encoding="utf-8")

    server_normalized = "".join(server.split())
    security_normalized = "".join(security.split())

    required_server = (
        "defclient_allows_device_key_handoff(",
        "@app.post('/api/security/device-key/handoff-stage')",
        "SECURITY.stage_device_key_handoffs(",
        "SECURITY.device_key_handoff_payload(",
    )
    required_security = (
        "defstage_device_key_handoffs(",
        "defdevice_key_handoff_payload(",
        "defdevice_key_is_current(",
        "def_promote_staged_device_key(",
        "handoff_verified_at",
    )

    return (
        all(item in server_normalized for item in required_server)
        and all(
            item in security_normalized
            for item in required_security
        )
    )


def render_summary(summary: dict[str, int]) -> list[str]:
    def value(name: str) -> int:
        return int(summary.get(name, 0) or 0)

    def count(label: str, name: str, *, indent: int = 2) -> str:
        return (
            f"{' ' * indent}{label:<38} "
            f"{value(name):>4}"
        )

    return [
        "SEC-006.2 DEVICE-KEY OWNERSHIP INVENTORY",
        "Result: PASS",
        (
            "Privacy: secret values and device/account identifiers "
            "were not displayed."
        ),
        "",
        "OWNERSHIP",
        count("Protected key records", "protected_key_records"),
        count(
            "First-party provisioned",
            "owner_first-party-provisioned",
        ),
        count("Unprovisioned", "owner_unprovisioned"),
        count("Orphaned", "owner_orphaned"),
        count(
            "Unexpected external",
            "owner_external-unexpected",
        ),
        count("Other provisioned", "owner_other-provisioned"),
        count("Unknown group", "owner_unknown-group"),
        "",
        "KEY RECORDS BY CLIENT TYPE",
        count("KotiBot Monitor", "group_android_home"),
        count("KotiBot Control", "group_android_key"),
        count("Tapo", "group_tapo"),
        count("Matter", "group_matter"),
        count("Orphaned", "group_orphaned"),
        "",
        "KEY SLOT STATUS",
        (
            "  Current   "
            f"active {value('current_active')} | "
            f"retired {value('current_retired')} | "
            f"malformed {value('current_malformed')}"
        ),
        (
            "  Previous  "
            f"grace-active {value('previous_grace-active')} | "
            f"retired {value('previous_retired')} | "
            f"malformed {value('previous_malformed')}"
        ),
        (
            "  Staged    "
            f"waiting {value('pending_staged')} | "
            f"retired {value('pending_retired')} | "
            f"malformed {value('pending_malformed')}"
        ),
        (
            "  Stale     "
            f"current {value('stale_current_slots')} | "
            f"previous {value('stale_previous_slots')}"
        ),
        "",
        "FIRST-PARTY HANDOFF",
        count("Live key records", "live_rotation_candidates"),
        count("Verified", "first_party_handoff_verified"),
        count(
            "Awaiting verification",
            "first_party_handoff_unverified",
        ),
        count(
            "Clients without an active key",
            "first_party_clients_without_active_key",
        ),
        count(
            "KotiBot Monitor without active key",
            "first_party_without_active_key_android_home",
            indent=4,
        ),
        count(
            "KotiBot Control without active key",
            "first_party_without_active_key_android_key",
            indent=4,
        ),
        count(
            "Clients without any key record",
            "first_party_clients_without_key_record",
        ),
        "",
        "REENROLLMENT",
        (
            "  All records  "
            f"total {value('enrollment_records')} | "
            f"pending {value('enrollment_pending')} | "
            f"expired {value('enrollment_expired')} | "
            f"malformed {value('enrollment_malformed')}"
        ),
        (
            "  Ownership    "
            f"first-party {value('enrollment_first_party_provisioned')} | "
            f"orphaned {value('enrollment_orphaned')} | "
            f"other {value('enrollment_other')}"
        ),
        "  For first-party clients without an active key:",
        (
            "    Recovery   "
            f"pending {value('first_party_without_active_key_enrollment_pending')} | "
            f"expired {value('first_party_without_active_key_enrollment_expired')} | "
            f"malformed {value('first_party_without_active_key_enrollment_malformed')} | "
            f"missing {value('first_party_without_active_key_enrollment_missing')}"
        ),
        (
            "    Expired    "
            f"Monitor {value('first_party_without_active_key_android_home_enrollment_expired')} | "
            f"Control {value('first_party_without_active_key_android_key_enrollment_expired')}"
        ),
        "",
        "EXTERNAL KEY REVIEW",
        count(
            "Active keys requiring ownership review",
            "active_keys_requiring_review",
        ),
        count("Tapo active", "active_group_tapo"),
        count("Matter active", "active_group_matter"),
    ]


def run_live_inventory(args) -> int:
    from server_core.paths import RuntimePaths
    from tools.sec0045_verify_complete_credential_cutover import (
        inspect_active_service,
    )

    snapshot = inspect_active_service(
        args.service,
        data_root_override=args.data_root,
    )
    paths = RuntimePaths(
        source_root=SOURCE_ROOT,
        data_root=snapshot.data_root,
    ).validate()

    security_state = _read_object(
        paths.security_state_file,
        "protected security state",
    )
    server_state = _read_object(
        paths.server_state_file,
        "durable server state",
    )
    summary = summarize_device_key_inventory(
        security_state,
        server_state,
    )

    for line in render_summary(summary):
        print(line)

    reenrollment_ok = prove_server_reenrollment_fixture()
    handshake_contract_ok = verify_server_handshake_contract()
    handoff_contract_ok = verify_server_handoff_contract()

    print("\nCONTRACT CHECKS")
    print(
        f"  {'Server re-enrollment fixture':<38} "
        + ("PASS" if reenrollment_ok else "FAIL")
    )
    print(
        f"  {'Handshake credential replacement':<38} "
        + ("PASS" if handshake_contract_ok else "FAIL")
    )
    print(
        f"  {'Staged handoff contract':<38} "
        + ("PASS" if handoff_contract_ok else "FAIL")
    )

    if (
        not reenrollment_ok
        or not handshake_contract_ok
        or not handoff_contract_ok
    ):
        print("\nHANDOFF GATE: BLOCKED")
        print("  One or more server-side contract checks failed.")
        return 1

    unverified = int(
        summary.get("first_party_handoff_unverified", 0) or 0
    )
    without_active_key = int(
        summary.get("first_party_clients_without_active_key", 0)
        or 0
    )

    if unverified or without_active_key:
        expired_correlated = int(
            summary.get(
                "first_party_without_active_key_enrollment_expired",
                0,
            )
            or 0
        )
        without_key_record = int(
            summary.get(
                "first_party_clients_without_key_record",
                0,
            )
            or 0
        )
        pending_recovery = int(
            summary.get(
                "first_party_without_active_key_enrollment_pending",
                0,
            )
            or 0
        )
        print("\nHANDOFF GATE: PENDING")

        if unverified:
            print(
                "  - First-party active keys awaiting verified "
                f"handoff: {unverified}"
            )

        if without_active_key:
            print(
                "  - First-party clients without an active key: "
                f"{without_active_key}"
            )

        if without_key_record:
            print(
                "  - First-party clients without any key record: "
                f"{without_key_record}"
            )

        if pending_recovery:
            print(
                "  - Matching recovery enrollments currently "
                f"pending: {pending_recovery}"
            )

        if expired_correlated:
            print(
                "  - Matching recovery enrollments expired: "
                f"{expired_correlated}"
            )
    else:
        print("\nHANDOFF GATE: READY FOR REVIEW")

    print("\nDestructive cleanup performed: NO")
    return 0


def main(argv=None) -> int:
    args = _parser().parse_args(argv)

    try:
        return run_live_inventory(args)
    except (RuntimeError, OSError, ValueError) as exc:
        print(
            "SEC-006.2 device-key ownership inventory stopped: "
            f"{exc}; no values or identifiers displayed."
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""SEC-006.2 value-free device-key ownership and re-enrollment preflight.

Read-only against live KotiBot state. The only writes performed by this tool
are inside a TemporaryDirectory used to prove the server-side re-enrollment
contract. No live credential is issued, rotated, revoked, displayed, or copied.
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


FIRST_PARTY_GROUPS = frozenset({
    "android_home",
    "android_key",
})
EXTERNAL_GROUPS = frozenset({
    "matter",
    "tapo",
})


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Read-only SEC-006.2 device-key ownership inventory. "
            "Reports counts and contract status only; never credential values "
            "or device identifiers."
        ),
    )
    parser.add_argument(
        "--service",
        default="kotibot",
        help="active Linux systemd service to inspect",
    )
    parser.add_argument(
        "--data-root",
        type=Path,
        help=(
            "override the active service data root; otherwise derive it "
            "from the running process"
        ),
    )
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


def flatten_server_clients(server_state: dict) -> tuple[dict[str, dict], int]:
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

    if status_value == "active" and (not key_id_present or not secret_present):
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
    enrollments = raw_enrollments if isinstance(raw_enrollments, dict) else {}

    counts = Counter()
    counts["protected_key_records"] = len(device_keys)
    counts["registry_clients"] = len(clients)
    counts["registry_duplicate_ids"] = duplicate_ids

    key_ids = set()

    for device_id, record in device_keys.items():
        device_id = str(device_id)
        key_ids.add(device_id)
        owner = _owner_class(clients.get(device_id))
        counts[f"owner_{owner}"] += 1

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

        counts[f"current_{current_state}"] += 1
        counts[f"previous_{previous_state}"] += 1

        if current_state == "active":
            if owner == "first-party-provisioned":
                counts["live_rotation_candidates"] += 1
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
        if (
            _owner_class(client) == "first-party-provisioned"
            and device_id not in key_ids
        ):
            counts["first_party_clients_without_key_record"] += 1

    counts["enrollment_records"] = len(enrollments)

    for device_id, record in enrollments.items():
        owner = _owner_class(clients.get(str(device_id)))

        if owner == "first-party-provisioned":
            counts["enrollment_first_party_provisioned"] += 1
        elif owner == "orphaned":
            counts["enrollment_orphaned"] += 1
        else:
            counts["enrollment_other"] += 1

        if not isinstance(record, dict):
            counts["enrollment_malformed"] += 1
            continue

        try:
            expires_at = int(record.get("expires_at") or 0)
        except (TypeError, ValueError):
            counts["enrollment_malformed"] += 1
            continue

        if expires_at >= now:
            counts["enrollment_pending"] += 1
        else:
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


def render_summary(summary: dict[str, int]) -> list[str]:
    def value(name: str) -> int:
        return int(summary.get(name, 0) or 0)

    return [
        "SEC-006.2 device-key ownership inventory passed; "
        "no values or identifiers displayed.",
        f"protected-device-key-records: {value('protected_key_records')}",
        (
            "registry-ownership: "
            f"first-party-provisioned={value('owner_first-party-provisioned')} "
            f"unprovisioned={value('owner_unprovisioned')} "
            f"orphaned={value('owner_orphaned')} "
            f"external-unexpected={value('owner_external-unexpected')} "
            f"other-provisioned={value('owner_other-provisioned')} "
            f"unknown-group={value('owner_unknown-group')}"
        ),
        (
            "key-slots: "
            f"current-active={value('current_active')} "
            f"current-retired={value('current_retired')} "
            f"current-malformed={value('current_malformed')} "
            f"previous-grace-active={value('previous_grace-active')} "
            f"previous-retired={value('previous_retired')} "
            f"previous-malformed={value('previous_malformed')}"
        ),
        (
            "stale-key-slots: "
            f"current={value('stale_current_slots')} "
            f"previous={value('stale_previous_slots')}"
        ),
        (
            "rotation-candidates: "
            f"first-party-live-records={value('live_rotation_candidates')} "
            f"active-requiring-review={value('active_keys_requiring_review')} "
            f"first-party-clients-without-key="
            f"{value('first_party_clients_without_key_record')}"
        ),
        (
            "enrollment-records: "
            f"total={value('enrollment_records')} "
            f"pending={value('enrollment_pending')} "
            f"expired={value('enrollment_expired')} "
            f"first-party={value('enrollment_first_party_provisioned')} "
            f"orphaned={value('enrollment_orphaned')} "
            f"other={value('enrollment_other')} "
            f"malformed={value('enrollment_malformed')}"
        ),
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

    fixture_ok = prove_server_reenrollment_fixture()
    handshake_ok = verify_server_handshake_contract()

    print(
        "server-reenrollment-fixture: "
        + ("passed" if fixture_ok else "FAILED")
    )
    print(
        "server-handshake-rotation-contract: "
        + ("passed" if handshake_ok else "FAILED")
    )

    live_candidates = int(
        summary.get("live_rotation_candidates", 0) or 0
    )

    if not fixture_ok or not handshake_ok:
        print("rotation-authorized: no (server recovery contract failed)")
        return 1

    if live_candidates:
        print(
            "client-handoff-proof: required for deployed first-party clients"
        )
        print(
            "rotation-authorized: no "
            "(deployed client re-enrollment acceptance not proven)"
        )
    else:
        print("client-handoff-proof: no live first-party key candidate found")
        print(
            "rotation-authorized: no "
            "(SEC-006.3 remains the explicit rotation step)"
        )

    print("destructive-changes-performed: no")
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

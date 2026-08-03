from __future__ import annotations

import re
from typing import Any

P306_VISIBLE_OUTLET_POSITIONS = {4}
P306_NIGHTLIGHT_POSITIONS = {5}
P306_FORCED_NAMES = {
    4: "Coffee Maker",
    5: "Nightlight",
}

def _clean_text(value: Any, limit: int = 80) -> str:
    return " ".join(str(value or "").replace("\r", " ").replace("\n", " ").split())[:limit]

def _normalize_model(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().upper().replace("TAPO ", ""))

def _compact_model(value: Any) -> str:
    clean = str(value or "").strip().lower().split("(", 1)[0]
    return "".join(ch for ch in clean if ch.isalnum())

def _bool_value(value: Any):
    if value is True or value is False:
        return value

    if isinstance(value, (int, float)):
        return value != 0

    text = str(value or "").strip().lower()

    if text in {"1", "true", "yes", "on", "enabled"}:
        return True

    if text in {"0", "false", "no", "off", "disabled"}:
        return False

    return None

def outlet_extender_control_methods(model: str) -> list[str]:
    methods: list[str] = []
    clean = _compact_model(model)

    for value in (clean, "p316", "p306", "p304", "p300"):
        if value and value not in methods:
            methods.append(value)

    return methods

def default_outlet_count(model: str, device_type: str) -> int:
    m = _normalize_model(model)
    t = str(device_type or "").strip().upper()
    blob = f"{m} {t}"

    if m.startswith(("P316", "EP316")):
        return 6
    if m.startswith(("P306", "EP306")):
        return 5
    if m.startswith(("P304", "EP304")):
        return 4
    if m.startswith(("P300", "EP300")):
        return 3
    if "POWER STRIP" in blob or "POWERSTRIP" in blob:
        return 3

    return 0

def outlet_extender_child_position(child: dict[str, Any], index: int = 0) -> int:
    for key in ("position", "slot_number"):
        try:
            value = int(child.get(key))
            if value > 0:
                return value
        except (TypeError, ValueError):
            pass

    try:
        value = int(child.get("index"))
        if value >= 0:
            return value + 1
    except (TypeError, ValueError):
        pass

    return index + 1

def outlet_extender_child_name_is_default(value: Any) -> bool:
    text = _clean_text(value).strip()

    return bool(
        not text
        or re.match(r"^(tapo\s*)?p\d+[_\s-]*\d+$", text, re.I)
        or re.match(r"^outlet\s+\d+$", text, re.I)
        or re.match(r"^extender\s+.+\s+\d+$", text, re.I)
    )

def outlet_extender_child_display_name(parent_name: str, child: dict[str, Any], index: int = 0, model: str = "") -> str:
    position = outlet_extender_child_position(child, index)
    m = _normalize_model(model)

    if m.startswith(("P306", "EP306")) and position in P306_FORCED_NAMES:
        return P306_FORCED_NAMES[position]

    raw_name = _clean_text(child.get("alias") or child.get("name") or child.get("nickname"))

    if raw_name and not outlet_extender_child_name_is_default(raw_name):
        return raw_name

    base_name = _clean_text(parent_name) or "Tapo Extender"
    return _clean_text(f"Extender {base_name} {position}")

def _child_looks_like_light(child: dict[str, Any], alias: str = "") -> bool:
    tokens = []

    for key in ("type", "kind", "category", "component", "device_type", "deviceType", "name", "alias", "nickname", "avatar", "model"):
        value = str(child.get(key) or "").strip().lower()
        if value:
            tokens.append(value)

    if alias:
        tokens.append(str(alias).strip().lower())

    text = " ".join(tokens)
    return any(token in text for token in ("nightlight", "night light", "light", "led"))

def _default_child_hidden(model: str, position: int) -> bool:
    m = _normalize_model(model)

    if m.startswith(("P306", "EP306")):
        return position not in P306_VISIBLE_OUTLET_POSITIONS

    return False

def apply_outlet_extender_child_defaults(
    child: dict[str, Any],
    model: str,
    device_type: str = "",
    index: int = 0,
    parent_name: str = "",
) -> dict[str, Any]:
    if not isinstance(child, dict):
        child = {}

    next_child = dict(child)
    position = outlet_extender_child_position(next_child, index)
    m = _normalize_model(model)

    raw_id = str(
        next_child.get("id")
        or next_child.get("device_id")
        or next_child.get("deviceId")
        or next_child.get("child_id")
        or next_child.get("childId")
        or next_child.get("original_device_id")
        or next_child.get("originalDeviceId")
        or position
    ).strip()

    alias = _clean_text(
        next_child.get("alias")
        or next_child.get("name")
        or next_child.get("nickname")
        or ""
    )

    is_light = _child_looks_like_light(next_child, alias)

    if m.startswith(("P306", "EP306")) and position in P306_NIGHTLIGHT_POSITIONS:
        is_light = True

    if outlet_extender_child_name_is_default(alias) or (m.startswith(("P306", "EP306")) and position in P306_FORCED_NAMES):
        alias = outlet_extender_child_display_name(parent_name, next_child, index, model)

    child_kind = "nightlight" if is_light else "plug"

    next_child.update({
        "id": raw_id,
        "index": max(0, position - 1),
        "position": position,
        "alias": alias,
        "name": alias,
        "clientName": alias,
        "is_usb": bool(next_child.get("is_usb")),
        "is_light": is_light,
        "is_outlet": not is_light,
        "kind": child_kind,
        "tapo_kind": child_kind,
        "tapo_alias": alias,
        "tapo_child_id": raw_id,
        "tapo_child_name": alias,
        "tapo_child_position": position,
        "tapo_child_index": max(0, position - 1),
        "tapo_child_kind": child_kind,
        "tapo_is_outlet_child": True,
        "tapo_is_plug": not is_light,
        "tapo_is_bulb": False,
        "tapo_supports_power": True,
        "supports_power": True,
        "supports_brightness": bool(next_child.get("supports_brightness")),
        "supports_color_temp": bool(next_child.get("supports_color_temp")),
        "supports_color": bool(next_child.get("supports_color")),
    })

    # Apply the model’s hide default only when this child has never received a
    # saved choice. Normal refreshes must not overwrite an explicit false/true.
    if next_child.get("tapo_hide_dashboard") in (None, ""):
        next_child["tapo_hide_dashboard"] = _default_child_hidden(model, position)
    else:
        next_child["tapo_hide_dashboard"] = _bool_value(
            next_child.get("tapo_hide_dashboard")
        ) is True

    if "cli_index" not in next_child or next_child.get("cli_index") in (None, ""):
        next_child["cli_index"] = index

    if "tapo_room_power" not in next_child or next_child.get("tapo_room_power") is None:
        next_child["tapo_room_power"] = False

    return next_child

def default_outlet_children(model: str, device_type: str, parent_name: str = "") -> list[dict[str, Any]]:
    children = []

    for index in range(default_outlet_count(model, device_type)):
        position = index + 1
        child = {
            "id": str(position),
            "index": index,
            "cli_index": index,
            "position": position,
            "alias": f"Outlet {position}",
            "is_usb": False,
            "is_light": False,
            "supports_brightness": False,
            "supports_color_temp": False,
            "supports_color": False,
            "is_on": None,
            "raw": {},
        }
        children.append(apply_outlet_extender_child_defaults(child, model, device_type, index, parent_name))

    return children

def _repair_p306_legacy_child_assignment(
    children: list[dict[str, Any]],
    model: str,
    device_type: str = "",
    parent_name: str = "",
) -> list[dict[str, Any]]:
    if not _normalize_model(model).startswith(
        ("P306", "EP306")
    ):
        return children

    forced_names = {
        _clean_text(name).lower()
        for name in P306_FORCED_NAMES.values()
    }
    forced_name_positions = {}

    for index, child in enumerate(children):
        if not isinstance(child, dict):
            continue

        child_name = _clean_text(
            child.get("alias")
            or child.get("name")
            or child.get("nickname")
        ).lower()

        if child_name not in forced_names:
            continue

        forced_name_positions.setdefault(
            child_name,
            set(),
        ).add(
            outlet_extender_child_position(
                child,
                index,
            )
        )

    duplicated_names = {
        name
        for name, positions in forced_name_positions.items()
        if len(positions) > 1
    }

    if not duplicated_names:
        return children

    base_name = _clean_text(parent_name) or "Tapo Extender"
    repaired = []

    for index, child in enumerate(children):
        if not isinstance(child, dict):
            continue

        next_child = dict(child)
        position = outlet_extender_child_position(
            next_child,
            index,
        )
        current_name = _clean_text(
            next_child.get("alias")
            or next_child.get("name")
            or next_child.get("nickname")
        )
        forced_name = P306_FORCED_NAMES.get(position)

        if forced_name:
            display_name = forced_name
        elif current_name.lower() in duplicated_names:
            display_name = _clean_text(
                f"Extender {base_name} {position}"
            )
        else:
            display_name = current_name

        if display_name:
            next_child.update({
                "alias": display_name,
                "name": display_name,
                "clientName": display_name,
                "tapo_alias": display_name,
                "tapo_child_name": display_name,
            })

        # A duplicated P306 forced name identifies the legacy crossed
        # assignment. Restore the model layout once; later explicit choices
        # remain untouched because the duplicate no longer exists.
        next_child["tapo_hide_dashboard"] = (
            _default_child_hidden(
                model,
                position,
            )
        )

        repaired.append(
            apply_outlet_extender_child_defaults(
                next_child,
                model,
                device_type,
                index,
                parent_name,
            )
        )

    return sorted(
        repaired,
        key=lambda child: outlet_extender_child_position(
            child
        ),
    )
        
def normalize_outlet_extender_children(
    children: list[dict[str, Any]],
    model: str,
    device_type: str = "",
    parent_name: str = "",
) -> list[dict[str, Any]]:
    normalized = []

    for index, child in enumerate(children if isinstance(children, list) else []):
        if isinstance(child, dict):
            normalized.append(apply_outlet_extender_child_defaults(child, model, device_type, index, parent_name))

    return _repair_p306_legacy_child_assignment(
        sorted(
            normalized,
            key=lambda child: (
                outlet_extender_child_position(child)
            ),
        ),
        model,
        device_type,
        parent_name,
    )

def _identity_keys(child: dict[str, Any]) -> list[str]:
    keys = []

    for field in (
        "id",
        "device_id",
        "deviceId",
        "child_id",
        "childId",
        "original_device_id",
        "originalDeviceId",
    ):
        value = str(child.get(field) or "").strip()

        if value and value not in keys:
            keys.append(value)

    return keys

def _fallback_keys(
    child: dict[str, Any],
    index: int = 0,
) -> list[str]:
    keys = []

    # Physical position is the strongest fallback. slot_number must remain
    # last because the P306 reports the same slot_number for every child.
    for field in (
        "position",
        "index",
        "cli_index",
        "slot_number",
    ):
        value = str(child.get(field) or "").strip()

        if value:
            keys.append(f"{field}:{value}")

    if not keys:
        keys.append(f"ordinal:{index + 1}")

    return keys

def _has_power_value(child: dict[str, Any]) -> bool:
    return isinstance(child, dict) and any(
        child.get(field) is not None and child.get(field) != ""
        for field in ("is_on", "device_on", "on", "state")
    )

def merge_outlet_extender_child_metadata(
    old_children: list[dict[str, Any]],
    new_children: list[dict[str, Any]],
    model: str,
    device_type: str = "",
    parent_name: str = "",
) -> list[dict[str, Any]]:
    if not isinstance(new_children, list):
        return []

    old_identity_map = {}
    old_fallback_map = {}

    if isinstance(old_children, list):
        for index, child in enumerate(old_children):
            if not isinstance(child, dict):
                continue

            old_child = apply_outlet_extender_child_defaults(child, model, device_type, index, parent_name)

            for key in _identity_keys(old_child):
                old_identity_map[key] = old_child

            for key in _fallback_keys(old_child, index):
                old_fallback_map[key] = old_child

    merged = []

    for index, child in enumerate(new_children):
        if not isinstance(child, dict):
            continue

        normalized_child = apply_outlet_extender_child_defaults(child, model, device_type, index, parent_name)
        old = next((old_identity_map.get(key) for key in _identity_keys(normalized_child) if isinstance(old_identity_map.get(key), dict)), {})

        if not old:
            old = next((old_fallback_map.get(key) for key in _fallback_keys(normalized_child, index) if isinstance(old_fallback_map.get(key), dict)), {})

        next_child = {
            child_key: child_value
            for child_key, child_value in normalized_child.items()
            if child_key != "raw"
        }

        for field in ("alias", "name", "zone_name", "room", "room_name", "zone"):
            if field in old and old.get(field) not in (None, ""):
                next_child[field] = old.get(field)

        if "tapo_room_power" in old and old.get("tapo_room_power") is not None:
            next_child["tapo_room_power"] = _bool_value(old.get("tapo_room_power"))

        # The persisted child hide choice owns dashboard membership after first
        # detection; refreshed extender metadata must never restore its default.
        if "tapo_hide_dashboard" in old and old.get("tapo_hide_dashboard") is not None:
            next_child["tapo_hide_dashboard"] = (
                _bool_value(old.get("tapo_hide_dashboard")) is True
            )

        if not _has_power_value(next_child) and _has_power_value(old):
            for field in ("is_on", "device_on", "on", "state"):
                if old.get(field) is not None and old.get(field) != "":
                    next_child[field] = old.get(field)

        if not str(next_child.get("status") or "").strip() and str(old.get("status") or "").strip():
            next_child["status"] = old.get("status")

        merged.append(apply_outlet_extender_child_defaults(next_child, model, device_type, index, parent_name))

    return _repair_p306_legacy_child_assignment(
        sorted(
            merged,
            key=lambda child: (
                outlet_extender_child_position(child)
            ),
        ),
        model,
        device_type,
        parent_name,
    )
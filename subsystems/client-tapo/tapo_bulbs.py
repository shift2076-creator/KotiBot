from __future__ import annotations

import re
from typing import Any

from .tapo_types import classify_bulb_capabilities

BULB_FALLBACK_METHODS = (
    "l535",
    "l530",
    "l520",
    "l510",
    "l630",
    "l610",
    "l930",
    "l920",
    "l900",
)


def append_unique(items: list[str], *values: str) -> None:
    for value in values:
        clean = str(value or "").strip().lower()
        if clean and clean not in items:
            items.append(clean)


def model_method_candidates(model: str) -> list[str]:
    raw = str(model or "").strip().lower()
    base = raw.split("(", 1)[0].strip()
    clean = re.sub(r"[^a-z0-9]+", "", base)
    candidates: list[str] = []

    if clean:
        append_unique(candidates, clean)
        family = re.match(r"^([a-z]+\d+)", clean)
        if family:
            append_unique(candidates, family.group(1))

    return candidates


def bulb_control_methods(model: str) -> list[str]:
    methods = model_method_candidates(model)
    append_unique(methods, *BULB_FALLBACK_METHODS)
    return methods


def apply_bulb_capability_defaults(item: dict[str, Any]) -> dict[str, Any]:
    caps = classify_bulb_capabilities(item.get("model", ""), item.get("device_type", ""))
    item["supports_power"] = bool(item.get("supports_power", caps.supports_power))
    item["supports_brightness"] = bool(item.get("supports_brightness", caps.supports_brightness))
    item["supports_color_temp"] = bool(item.get("supports_color_temp", caps.supports_color_temp))
    item["supports_color"] = bool(item.get("supports_color", caps.supports_color))
    item["dimmable"] = bool(item.get("dimmable", caps.supports_brightness))
    return item


def update_bulb_capabilities_from_device(item: dict[str, Any], dev: Any, has_any_method) -> dict[str, Any]:
    item["supports_power"] = True
    item["supports_brightness"] = bool(
        has_any_method(dev, ("set_brightness",))
        or item.get("supports_brightness")
    )
    item["supports_color_temp"] = bool(
        has_any_method(dev, ("set_color_temperature", "set_colour_temperature", "set_color_temp"))
        or item.get("supports_color_temp")
    )
    item["supports_color"] = bool(
        has_any_method(dev, ("set_hue_saturation", "set_hsv", "set_color"))
        or item.get("supports_color")
    )
    item["dimmable"] = bool(item.get("supports_brightness"))
    return item

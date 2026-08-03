from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

@dataclass
class TapoCapabilitySet:
    supports_power: bool = False
    supports_brightness: bool = False
    supports_color_temp: bool = False
    supports_color: bool = False
    supports_energy: bool = False
    supports_children: bool = False
    supports_rtsp: bool = False
    supports_onvif: bool = False

@dataclass
class DashboardCardState:
    device_id: str
    kind: str
    title: str
    model: str = ""
    ip: str = ""
    control_ready: bool = False
    control_error: str = ""
    fields: dict[str, Any] = field(default_factory=dict)

FULL_COLOR_BULB_PREFIXES = (
    "L530",
    "L535",
    "L630",
    "L900",
    "L920",
    "L930",
)

WHITE_TUNABLE_BULB_PREFIXES = (
    "L520",
    "L530",
    "L535",
    "L610",
    "L630",
    "L900",
    "L920",
    "L930",
)

DIMMABLE_BULB_PREFIXES = (
    "L510",
    "L520",
    "L530",
    "L535",
    "L610",
    "L630",
    "L900",
    "L920",
    "L930",
)

OUTLET_EXTENDER_PREFIXES = (
    "P300",
    "P304",
    "P306",
    "P316",
    "EP300",
    "EP304",
    "EP306",
    "EP316",
)

PLUG_PREFIXES = (
    "P100",
    "P105",
    "P110",
    "P115",
    "P125",
    "EP10",
    "EP25",
)

ENERGY_MONITORING_PLUG_PREFIXES = (
    "P110",
    "P115",
)

ENERGY_MONITORING_EXTENDER_PREFIXES = (
    "P304M",
    "P316M",
)

HUB_PREFIXES = (
    "H100",
    "H110",
    "H200",
)

def normalize_model(value: str | None) -> str:
    text = str(value or "").strip().upper()
    text = text.replace("TAPO ", "")
    return re.sub(r"\s+", " ", text)

def model_has_prefix(model: str, prefixes: tuple[str, ...]) -> bool:
    clean = normalize_model(model)
    return any(clean.startswith(prefix) for prefix in prefixes)

def model_supports_energy(model: str, kind: str = "") -> bool:
    clean_kind = str(kind or "").strip().lower()

    if clean_kind == "plug":
        return model_has_prefix(model, ENERGY_MONITORING_PLUG_PREFIXES)

    if clean_kind == "outlet_extender":
        return model_has_prefix(model, ENERGY_MONITORING_EXTENDER_PREFIXES)

    return model_has_prefix(
        model,
        ENERGY_MONITORING_PLUG_PREFIXES + ENERGY_MONITORING_EXTENDER_PREFIXES,
    )

def classify_bulb_capabilities(model: str, device_type: str = "") -> TapoCapabilitySet:
    m = normalize_model(model)
    blob = f"{m} {str(device_type or '').upper()}"

    supports_power = True
    supports_brightness = (
        model_has_prefix(m, DIMMABLE_BULB_PREFIXES)
        or "DIMM" in blob
        or "BULB" in blob
        or "LIGHT" in blob
    )
    supports_color_temp = (
        model_has_prefix(m, WHITE_TUNABLE_BULB_PREFIXES)
        or "COLOR TEMP" in blob
        or "COLOUR TEMP" in blob
        or "TUNABLE" in blob
        or "WHITE" in blob
    )
    supports_color = (
        model_has_prefix(m, FULL_COLOR_BULB_PREFIXES)
        or "COLOR" in blob
        or "COLOUR" in blob
        or "RGB" in blob
        or "MULTICOLOR" in blob
        or "MULTI-COLOR" in blob
    )

    if supports_color:
        supports_brightness = True

    return TapoCapabilitySet(
        supports_power=supports_power,
        supports_brightness=supports_brightness,
        supports_color_temp=supports_color_temp,
        supports_color=supports_color,
    )

def classify_tapo_device(model: str, device_type: str) -> dict[str, Any]:
    m = normalize_model(model)
    t = str(device_type or "").strip().upper()
    blob = f"{m} {t}"

    is_camera = (
        m.startswith(("C", "TC"))
        or "CAMERA" in blob
        or "IPC" in blob
    )

    is_lightstrip = (
        m.startswith("L9")
        or "LIGHT STRIP" in blob
        or "LIGHTSTRIP" in blob
    )

    is_hub = (
        model_has_prefix(m, HUB_PREFIXES)
        or "TAPOHUB" in blob
        or "TAPO HUB" in blob
        or "SMART.TAPOHUB" in blob
    )

    is_outlet_extender = (
        not is_hub
        and (
            model_has_prefix(m, OUTLET_EXTENDER_PREFIXES)
            or "POWER STRIP" in blob
            or "POWERSTRIP" in blob
            or "EXTENDER" in blob
        )
    )

    is_bulb = (
        not is_camera
        and not is_outlet_extender
        and (
            m.startswith("L")
            or "BULB" in blob
            or is_lightstrip
        )
    )

    is_plug = (
        not is_camera
        and not is_outlet_extender
        and (
            model_has_prefix(m, PLUG_PREFIXES)
            or m.startswith(("P", "EP"))
            or "PLUG" in blob
        )
    )

    if is_camera:
        kind = "camera"
        dashboard_section = "camera"
    elif is_hub:
        kind = "hub"
        dashboard_section = "hub"
    elif is_outlet_extender:
        kind = "outlet_extender"
        dashboard_section = "control"
    elif is_lightstrip:
        kind = "lightstrip"
        dashboard_section = "control"
    elif is_bulb:
        kind = "bulb"
        dashboard_section = "control"
    elif is_plug:
        kind = "plug"
        dashboard_section = "control"
    else:
        kind = "unknown"
        dashboard_section = "control"

    if kind in {"bulb", "lightstrip"}:
        capabilities = classify_bulb_capabilities(m, t)
    else:
        capabilities = TapoCapabilitySet(
            supports_power=kind in {"plug", "outlet_extender"},
            supports_energy=model_supports_energy(m, kind),
            supports_children=kind == "outlet_extender",
            supports_rtsp=kind == "camera",
            supports_onvif=kind == "camera",
        )

    return {
        "kind": kind,
        "dashboard_section": dashboard_section,
        "is_bulb": kind in {"bulb", "lightstrip"},
        "is_plug": kind == "plug",
        "is_outlet_extender": kind == "outlet_extender",
        "is_hub": kind == "hub",
        "is_camera": kind == "camera",
        "supports_power": capabilities.supports_power,
        "supports_brightness": capabilities.supports_brightness,
        "supports_color_temp": capabilities.supports_color_temp,
        "supports_color": capabilities.supports_color,
        "supports_energy": capabilities.supports_energy,
        "supports_children": capabilities.supports_children,
        "supports_rtsp": capabilities.supports_rtsp,
        "supports_onvif": capabilities.supports_onvif,
        "rtsp_url": "",
        "onvif_port": 2020,
        "children": [],
        "supported": kind != "unknown",
    }
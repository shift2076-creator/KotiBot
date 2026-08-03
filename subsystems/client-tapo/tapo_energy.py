from __future__ import annotations

import asyncio
import inspect
import os
import time
from threading import Lock
from typing import Any

from .tapo_types import model_supports_energy


TAPO_ENERGY_REFRESH_SECONDS = max(
    10.0,
    float(os.environ.get("KOTIBOT_TAPO_ENERGY_SECONDS", "60") or 60),
)
TAPO_ENERGY_CALL_TIMEOUT_SECONDS = max(
    1.0,
    float(os.environ.get("KOTIBOT_TAPO_ENERGY_TIMEOUT_SECONDS", "5") or 5),
)

_ENERGY_CACHE: dict[str, dict[str, Any]] = {}
_ENERGY_ATTEMPTED_AT: dict[str, float] = {}
_ENERGY_CACHE_LOCK = Lock()

_ENERGY_FIELDS = (
    "energy_available",
    "energy_error",
    "energy_updated_at",
    "current_power_w",
    "today_energy_kwh",
    "month_energy_kwh",
    "today_runtime_minutes",
    "month_runtime_minutes",
)


def _clean_number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _clean_int(value: Any) -> int | None:
    number = _clean_number(value)
    return int(number) if number is not None else None


def _first_value(data: dict[str, Any], *keys: str):
    for key in keys:
        if key in data and data.get(key) is not None:
            return data.get(key)

    return None


def _response_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}

    if isinstance(value, dict):
        return dict(value)

    to_dict = getattr(value, "to_dict", None)

    if callable(to_dict):
        result = to_dict()
        return dict(result) if isinstance(result, dict) else {}

    try:
        return {
            key: item
            for key, item in vars(value).items()
            if not key.startswith("_")
        }
    except TypeError:
        return {}


async def _maybe_await(value):
    return await value if inspect.isawaitable(value) else value


async def _call_energy_method(handler, method_name: str):
    method = getattr(handler, method_name, None)

    if not callable(method):
        raise AttributeError(f"{method_name} is not supported")

    return await asyncio.wait_for(
        _maybe_await(method()),
        timeout=TAPO_ENERGY_CALL_TIMEOUT_SECONDS,
    )


def _snapshot_from_payloads(
    usage: dict[str, Any],
    power: dict[str, Any],
    errors: list[str],
) -> dict[str, Any]:
    current_power_mw = _clean_number(
        _first_value(power, "current_power", "currentPower", "power")
    )

    if current_power_mw is None:
        current_power_mw = _clean_number(
            _first_value(usage, "current_power", "currentPower")
        )

    current_power_w = (
        current_power_mw / 1000.0
        if current_power_mw is not None
        else None
    )

    today_energy_wh = _clean_number(
        _first_value(usage, "today_energy", "todayEnergy")
    )
    month_energy_wh = _clean_number(
        _first_value(usage, "month_energy", "monthEnergy")
    )

    return {
        "energy_available": bool(usage or power),
        "energy_error": "; ".join(errors),
        "energy_updated_at": int(time.time()),
        "current_power_w": (
            round(current_power_w, 3)
            if current_power_w is not None
            else None
        ),
        "today_energy_kwh": (
            round(today_energy_wh / 1000.0, 6)
            if today_energy_wh is not None
            else None
        ),
        "month_energy_kwh": (
            round(month_energy_wh / 1000.0, 6)
            if month_energy_wh is not None
            else None
        ),
        "today_runtime_minutes": _clean_int(
            _first_value(usage, "today_runtime", "todayRuntime")
        ),
        "month_runtime_minutes": _clean_int(
            _first_value(usage, "month_runtime", "monthRuntime")
        ),
    }


def _cache_read(cache_key: str) -> dict[str, Any]:
    with _ENERGY_CACHE_LOCK:
        return dict(_ENERGY_CACHE.get(cache_key) or {})


def _cache_write(cache_key: str, snapshot: dict[str, Any]):
    with _ENERGY_CACHE_LOCK:
        _ENERGY_CACHE[cache_key] = dict(snapshot)


def _query_due(cache_key: str, force: bool) -> bool:
    now = time.monotonic()

    with _ENERGY_CACHE_LOCK:
        if not force:
            attempted_at = _ENERGY_ATTEMPTED_AT.get(cache_key, 0.0)

            if now - attempted_at < TAPO_ENERGY_REFRESH_SECONDS:
                return False

        _ENERGY_ATTEMPTED_AT[cache_key] = now
        return True


def _merge_with_cached(
    snapshot: dict[str, Any],
    cached: dict[str, Any],
) -> dict[str, Any]:
    merged = dict(snapshot)

    for key in _ENERGY_FIELDS:
        if key in {"energy_available", "energy_error", "energy_updated_at"}:
            continue

        if merged.get(key) is None and cached.get(key) is not None:
            merged[key] = cached.get(key)

    return merged


async def _read_handler_energy(
    handler,
    cache_key: str,
    force: bool = False,
) -> dict[str, Any]:
    cached = _cache_read(cache_key)

    if not _query_due(cache_key, force):
        return cached

    calls = []

    for method_name in ("get_energy_usage", "get_current_power"):
        if callable(getattr(handler, method_name, None)):
            calls.append((method_name, _call_energy_method(handler, method_name)))

    if not calls:
        snapshot = {
            **cached,
            "energy_available": False,
            "energy_error": "Energy monitoring is not supported by this device handler",
        }
        _cache_write(cache_key, snapshot)
        return snapshot

    results = await asyncio.gather(
        *(call for _, call in calls),
        return_exceptions=True,
    )
    payloads = {}
    errors = []

    for (method_name, _), result in zip(calls, results):
        if isinstance(result, Exception):
            errors.append(f"{method_name}: {result}")
        else:
            payloads[method_name] = _response_dict(result)

    usage = payloads.get("get_energy_usage", {})
    power = payloads.get("get_current_power", {})

    if not usage and not power:
        snapshot = {
            **cached,
            "energy_available": False,
            "energy_error": "; ".join(errors) or "Energy data unavailable",
        }
        _cache_write(cache_key, snapshot)
        return snapshot

    snapshot = _merge_with_cached(
        _snapshot_from_payloads(usage, power, errors),
        cached,
    )
    _cache_write(cache_key, snapshot)
    return snapshot


def _apply_snapshot(
    target: dict[str, Any],
    snapshot: dict[str, Any],
    supported: bool = True,
):
    target["supports_energy"] = supported

    if not supported:
        return

    for key in _ENERGY_FIELDS:
        if key in snapshot:
            target[key] = snapshot.get(key)


def _device_cache_key(item: dict[str, Any]) -> str:
    device_id = str(
        item.get("id")
        or item.get("device_id")
        or item.get("deviceID")
        or item.get("ip")
        or ""
    ).strip()
    return f"device:{device_id}" if device_id else ""


def _child_identity(child: dict[str, Any], index: int) -> str:
    return str(
        child.get("id")
        or child.get("device_id")
        or child.get("deviceId")
        or child.get("child_id")
        or child.get("childId")
        or child.get("original_device_id")
        or child.get("originalDeviceId")
        or child.get("position")
        or index + 1
    ).strip()


async def _energy_child_handler(parent_handler, child: dict[str, Any], index: int):
    plug = getattr(parent_handler, "plug", None)

    if not callable(plug):
        raise AttributeError("Power strip child energy handler is unavailable")

    child_id = _child_identity(child, index)
    nickname = str(
        child.get("nickname")
        or child.get("alias")
        or child.get("name")
        or ""
    ).strip()
    position = _clean_int(child.get("position"))
    attempts = []

    if child_id:
        attempts.append({"device_id": child_id})
    if position is not None and position > 0:
        attempts.append({"position": position})
    if nickname:
        attempts.append({"nickname": nickname})

    errors = []

    for kwargs in attempts:
        try:
            return await asyncio.wait_for(
                _maybe_await(plug(**kwargs)),
                timeout=TAPO_ENERGY_CALL_TIMEOUT_SECONDS,
            )
        except Exception as error:
            errors.append(f"plug({kwargs}): {error}")

    raise RuntimeError(
        "; ".join(errors)
        or f"Unable to resolve power strip outlet {index + 1}"
    )


async def _enrich_energy_child(
    parent_handler,
    parent_cache_key: str,
    child: dict[str, Any],
    index: int,
    force: bool,
) -> dict[str, Any]:
    next_child = dict(child)

    if next_child.get("is_usb"):
        _apply_snapshot(next_child, {}, supported=False)
        return next_child

    child_id = _child_identity(next_child, index)
    cache_key = f"{parent_cache_key}|{child_id or index + 1}"
    cached = _cache_read(cache_key)

    if not force and not _query_due(cache_key, False):
        _apply_snapshot(next_child, cached)
        return next_child

    try:
        handler = await _energy_child_handler(parent_handler, next_child, index)

        with _ENERGY_CACHE_LOCK:
            _ENERGY_ATTEMPTED_AT.pop(cache_key, None)

        snapshot = await _read_handler_energy(handler, cache_key, force=True)
    except Exception as error:
        snapshot = {
            **cached,
            "energy_available": False,
            "energy_error": str(error),
        }
        _cache_write(cache_key, snapshot)

    _apply_snapshot(next_child, snapshot)
    return next_child


async def _enrich_device_energy(
    item: dict[str, Any],
    device_getter,
    force: bool,
) -> dict[str, Any]:
    next_item = dict(item)
    model = str(next_item.get("model") or "")
    kind = str(next_item.get("kind") or "")
    supported = model_supports_energy(model, kind)
    cache_key = _device_cache_key(next_item)

    _apply_snapshot(next_item, {}, supported=supported)

    if not supported or not cache_key:
        return next_item

    if next_item.get("control_ready") is False:
        cached = _cache_read(cache_key)
        snapshot = {
            **cached,
            "energy_available": False,
            "energy_error": str(
                next_item.get("control_error")
                or "Tapo device is unavailable"
            ),
        }
        _apply_snapshot(next_item, snapshot)
        return next_item

    try:
        handler = await _maybe_await(
            device_getter(next_item, verify_cached=False)
        )
    except Exception as error:
        cached = _cache_read(cache_key)
        snapshot = {
            **cached,
            "energy_available": False,
            "energy_error": str(error),
        }
        _apply_snapshot(next_item, snapshot)
        return next_item

    if kind == "outlet_extender":
        children = (
            next_item.get("children")
            if isinstance(next_item.get("children"), list)
            else []
        )
        next_item["children"] = await asyncio.gather(*[
            _enrich_energy_child(
                handler,
                cache_key,
                child,
                index,
                force,
            )
            for index, child in enumerate(children)
            if isinstance(child, dict)
        ])
        return next_item

    snapshot = await _read_handler_energy(handler, cache_key, force=force)
    _apply_snapshot(next_item, snapshot)
    return next_item


async def enrich_tapo_energy_devices(
    devices: list[dict[str, Any]],
    device_getter,
    force: bool = False,
) -> list[dict[str, Any]]:
    if not devices:
        return []

    async def enrich_one(item: dict[str, Any]) -> dict[str, Any]:
        try:
            return await _enrich_device_energy(item, device_getter, force)
        except Exception as error:
            next_item = dict(item)
            supported = model_supports_energy(
                str(next_item.get("model") or ""),
                str(next_item.get("kind") or ""),
            )
            snapshot = {
                **_cache_read(_device_cache_key(next_item)),
                "energy_available": False,
                "energy_error": str(error),
            }
            _apply_snapshot(next_item, snapshot, supported=supported)
            return next_item

    return list(await asyncio.gather(*[
        enrich_one(item)
        for item in devices
    ]))


def _energy_fields(source: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    def field(name: str):
        return source.get(f"{prefix}{name}")

    return {
        "supported": field("supports_energy") is True,
        "available": field("energy_available") is True,
        "error": str(field("energy_error") or ""),
        "updatedAt": _clean_int(field("energy_updated_at")),
        "currentPowerW": _clean_number(field("current_power_w")),
        "todayEnergyKWh": _clean_number(field("today_energy_kwh")),
        "monthEnergyKWh": _clean_number(field("month_energy_kwh")),
        "todayRuntimeMinutes": _clean_int(field("today_runtime_minutes")),
        "monthRuntimeMinutes": _clean_int(field("month_runtime_minutes")),
    }


def tapo_energy_snapshot(clients: dict[str, dict[str, Any]]) -> dict[str, Any]:
    devices = []
    total_current_power_w = 0.0
    total_today_energy_kwh = 0.0
    total_month_energy_kwh = 0.0
    latest_update = None

    for device_id, client in clients.items():
        if not isinstance(client, dict):
            continue

        energy = _energy_fields(client, "tapo_")
        energy["supported"] = energy["supported"] or model_supports_energy(
            str(client.get("tapo_model") or client.get("model") or ""),
            str(client.get("tapo_kind") or client.get("kind") or ""),
        )
        children = []

        for index, child in enumerate(
            client.get("tapo_children")
            if isinstance(client.get("tapo_children"), list)
            else []
        ):
            if not isinstance(child, dict):
                continue

            child_energy = _energy_fields(child)

            if not child_energy["supported"]:
                continue

            child_id = _child_identity(child, index)
            children.append({
                "targetID": f"{device_id}|{child_id}",
                "id": child_id,
                "name": str(
                    child.get("clientName")
                    or child.get("alias")
                    or child.get("name")
                    or f"Outlet {index + 1}"
                ),
                **child_energy,
            })

        if not energy["supported"] and not children:
            continue

        readings = children if children else [energy]

        for reading in readings:
            total_current_power_w += reading.get("currentPowerW") or 0.0
            total_today_energy_kwh += reading.get("todayEnergyKWh") or 0.0
            total_month_energy_kwh += reading.get("monthEnergyKWh") or 0.0

            updated_at = reading.get("updatedAt")

            if updated_at is not None:
                latest_update = max(latest_update or updated_at, updated_at)

        devices.append({
            "deviceID": str(client.get("deviceID") or device_id),
            "clientName": str(
                client.get("clientName")
                or client.get("tapo_alias")
                or client.get("tapo_model")
                or device_id
            ),
            "zoneName": str(
                client.get("zone_name")
                or client.get("room")
                or client.get("room_name")
                or ""
            ),
            "model": str(client.get("tapo_model") or client.get("model") or ""),
            **energy,
            "children": children,
        })

    devices.sort(key=lambda item: (
        item.get("zoneName", "").lower(),
        item.get("clientName", "").lower(),
    ))

    return {
        "ok": True,
        "count": len(devices),
        "updatedAt": latest_update,
        "totals": {
            "currentPowerW": round(total_current_power_w, 3),
            "todayEnergyKWh": round(total_today_energy_kwh, 6),
            "monthEnergyKWh": round(total_month_energy_kwh, 6),
        },
        "devices": devices,
    }


def register_tapo_energy_routes(app, ctx):
    from flask import jsonify

    state_lock = ctx["state_lock"]
    clients = ctx["clients"]
    refresh_clients = ctx["refresh_clients"]

    def snapshot():
        with state_lock:
            return tapo_energy_snapshot(clients)

    app.config["KOTIBOT_TAPO_ENERGY_SNAPSHOT"] = snapshot

    @app.get("/api/tapo/energy")
    def api_tapo_energy():
        return jsonify(snapshot())

    @app.post("/api/tapo/energy/refresh")
    def api_tapo_energy_refresh():
        result = refresh_clients(
            persist=True,
            broadcast=True,
            skip_if_busy=True,
            energy_force=True,
        )

        if result.get("busy"):
            return jsonify({
                **snapshot(),
                "busy": True,
            })

        if not result.get("ok"):
            return jsonify(result), 500

        return jsonify(snapshot())

    return {
        "snapshot": snapshot,
    }

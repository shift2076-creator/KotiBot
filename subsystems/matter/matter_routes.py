from __future__ import annotations

import math
import os
from pathlib import Path
from threading import Event, Lock

from flask import jsonify, request

from .matter_runtime import MatterRuntime


def _json_payload():
    return request.get_json(silent=True) or {}


def _error_response(error, status=400):
    return jsonify({
        "ok": False,
        "error": str(error),
    }), status


def register_matter_routes(app, context):
    matter_dir = Path(context["matter_dir"])
    controller_storage_dir = Path(
        context["matter_controller_storage_dir"]
    )
    subscription_storage_dir = Path(
        context["matter_subscription_storage_dir"]
    )
    matter_dir.mkdir(parents=True, exist_ok=True)

    runtime = MatterRuntime(
        matter_dir,
        controller_storage_dir=controller_storage_dir,
        subscription_storage_dir=subscription_storage_dir,
        now_epoch=context["now_epoch"],
    )
    runtime_state = runtime.read_state()
    matter_settings = dict(
        runtime_state.get("settings")
        if isinstance(runtime_state.get("settings"), dict)
        else {}
    )

    def _matter_settings_snapshot():
        return dict(matter_settings)

    app.config["KOTIBOT_MATTER_SETTINGS_SNAPSHOT"] = _matter_settings_snapshot

    state_lock = context.get("state_lock")
    clients = context.get("clients", {})
    save_state = context.get("save_state")
    broadcast_state = context.get("broadcast_state")
    now_epoch = context["now_epoch"]
    client_role_dss = context.get("client_role_dss", "DSS")
    fire_door_routes = context.get("fire_door_routes", lambda door_client, output: False)
    fire_camera_motion_routes = context.get("fire_camera_motion_routes", lambda motion_client, output="motion": False)
    fire_environment_routes = context.get("fire_environment_routes", lambda sensor_client, kind, value, previous_value: False)
    activity_log = context.get("activity_log")
    activity_log_can_record = activity_log is not None and hasattr(activity_log, "record_state_change")
    activity_log_can_reset = activity_log is not None and hasattr(activity_log, "reset_state_signature")
    matter_sync_stop = context.get("matter_sync_stop") or Event()
    matter_sync_lock = Lock()
    matter_subscription_lock = Lock()
    matter_startup_sync_complete = Event()
    matter_subscription_restart = Event()
    matter_sync_active = Event()
    matter_maintenance_lock = Lock()
    matter_maintenance = Event()

    def _matter_device_id(node_id, endpoint):
        return f"matter:{node_id}:{endpoint}"

    def _upsert_matter_client(device_id, defaults, values):
        existing = clients.get(device_id)

        if not isinstance(existing, dict):
            existing = {}

        client = dict(existing)
        client.update(defaults)
        client.update(values)

        if existing.get("clientName"):
            client["clientName"] = existing["clientName"]

        if existing.get("zone_name"):
            client["zone_name"] = existing["zone_name"]
        clients[device_id] = client

        return device_id

    def _matter_kind_label(kinds):
        clean_kinds = [str(kind or "").strip().lower() for kind in kinds if kind]

        if "contact" in clean_kinds:
            return "contact"

        if "motion" in clean_kinds:
            return "motion"

        if "switch" in clean_kinds:
            return "switch"

        if "button" in clean_kinds:
            return "button"

        if "battery" in clean_kinds and len(clean_kinds) == 1:
            return "battery"

        if "temperature" in clean_kinds and "humidity" in clean_kinds:
            return "environment"

        if "temperature" in clean_kinds:
            return "temperature"

        if "humidity" in clean_kinds:
            return "humidity"

        return "matter"

    def _matter_kind_name(kind_label):
        return {
            "temperature": "Temperature Sensor",
            "humidity": "Humidity Sensor",
            "environment": "Temperature/Humidity Sensor",
            "contact": "Contact Sensor",
            "motion": "Motion Sensor",
            "switch": "Switch",
            "button": "Button",
            "battery": "Battery",
        }.get(kind_label, "Matter Device")

    def _matter_client_name(kind_label):
        return f"Matter {_matter_kind_name(kind_label)}"

    def _matter_battery_state(child):
        child = child if isinstance(child, dict) else {}

        low = child.get("matter_battery_low")

        if low is None:
            low = child.get("battery_low")

        low_bool = _matter_bool(low)

        if low_bool is None:
            return None

        return "low" if low_bool else "ok"

    def _matter_model_name(kind_label):
        return f"Matter {_matter_kind_name(kind_label)}"

    def _matter_bool(value):
        if value is True or value == 1:
            return True

        if value is False or value == 0:
            return False

        clean = str(value or "").strip().lower()

        if clean in ("true", "1", "yes", "on", "open"):
            return True

        if clean in ("false", "0", "no", "off", "closed", "close"):
            return False

        return None

    def _matter_int(value):
        try:
            return int(value)
        except Exception:
            return None

    def _matter_float(value):
        try:
            number = float(value)
        except Exception:
            return None

        return number if math.isfinite(number) else None

    def _matter_kinds_with(client, *new_kinds):
        raw_kinds = client.get("matter_kinds") if isinstance(client.get("matter_kinds"), list) else [client.get("matter_kind")]
        kinds = []

        for kind in [*raw_kinds, *new_kinds]:
            clean_kind = str(kind or "").strip().lower()

            if clean_kind and clean_kind != "matter" and clean_kind not in kinds:
                kinds.append(clean_kind)

        return kinds

    def _recommission_matter_connection():
        payload = _json_payload()

        with matter_maintenance_lock:
            matter_maintenance.set()
            matter_subscription_restart.set()
            runtime.stop_subscription()

            try:
                with matter_subscription_lock, matter_sync_lock:
                    result = runtime.recommission_node(payload)

                    if not result.get("ok"):
                        return result

                    sync_result = _sync_matter_clients_locked({
                        "force_discovery": True,
                    })

                    return {
                        "ok": True,
                        "status": (
                            "connected"
                            if sync_result.get("ok")
                            else "sync_failed"
                        ),
                        "node_id": result.get("node_id"),
                        "backup": result.get("backup"),
                        "device_count": len(
                            sync_result.get("devices") or []
                        ),
                        "sync_ok": bool(sync_result.get("ok")),
                    }
            finally:
                matter_maintenance.clear()

    def _record_matter_activity_state(client, *, kind, state, status, icon, accent, detail="", category="", source="matter"):
        if not activity_log_can_record:
            return None

        client = client if isinstance(client, dict) else {}
        device_id = str(client.get("deviceID") or "").strip()

        if not device_id:
            return None

        try:
            return activity_log.record_state_change(
                deviceID=device_id,
                name=client.get("clientName") or client.get("matter_node_label") or client.get("model") or "Matter Device",
                kind=kind,
                state=state,
                status=status,
                icon=icon,
                accent=accent,
                source=source,
                detail=detail,
                category=category,
                record_initial=True,
            )
        except Exception:
            app.logger.exception("Matter activity recording failed")
            return None

    def _reset_matter_activity_signature(client, kind):
        if not activity_log_can_reset:
            return False

        client = client if isinstance(client, dict) else {}
        device_id = str(client.get("deviceID") or "").strip()

        if not device_id:
            return False

        try:
            return bool(activity_log.reset_state_signature(
                deviceID=device_id,
                kind=kind,
                source="matter",
            ))
        except Exception:
            app.logger.exception("Matter activity signature reset failed")
            return False

    def _record_matter_contact_activity(client, door_status):
        state = str(door_status or "").strip().lower()

        if state not in ("open", "closed"):
            return None

        return _record_matter_activity_state(
            client,
            kind="matter_contact",
            state=state,
            status="Opened" if state == "open" else "Closed",
            icon="sensor_door",
            accent="green" if state == "open" else "red",
            category="system",
        )

    def _record_matter_motion_activity(client, active):
        motion_active = _matter_bool(active)

        if motion_active is not True:
            _reset_matter_activity_signature(client, "matter_motion")
            return None

        return _record_matter_activity_state(
            client,
            kind="matter_motion",
            state="detected",
            status="Motion detected",
            icon="motion_sensor_active",
            accent="orange",
            category="system",
        )

    def _record_matter_switch_activity(client, enabled):
        power_state = _matter_bool(enabled)

        if power_state is None:
            return None

        return _record_matter_activity_state(
            client,
            kind="matter_switch_power",
            state="on" if power_state else "off",
            status="On" if power_state else "Off",
            icon="toggle_on",
            accent="purple",
            category="users",
        )

    def _record_matter_button_activity(client, position):
        pos = _matter_int(position)

        if pos is None:
            return None

        if pos <= 0:
            _reset_matter_activity_signature(client, "matter_button_press")
            return None

        return _record_matter_activity_state(
            client,
            kind="matter_button_press",
            state=f"position:{pos}",
            status="Pressed",
            icon="radio_button_checked",
            accent="gold",
            detail=f"position {pos}",
            category="users",
        )

    def _matter_contact_open_when(client, child=None):
        # Matter BooleanState StateValue is not an arbitrary polarity for a
        # Contact Sensor: FALSE means open/no contact and TRUE means closed/contact.
        # Do not relearn this value from persisted client state. A recommissioned
        # endpoint can otherwise retain the old inferred polarity and swap
        # door_open with door_close for every automation using that sensor.
        return False

    def _matter_contact_open(child, client=None):
        raw_contact = _matter_bool(child.get("contact_state_value"))

        if raw_contact is None:
            raw_contact = _matter_bool(child.get("contact_open"))

        if raw_contact is None:
            return None

        return raw_contact == _matter_contact_open_when(client, child)

    def _existing_contact_open(client):
        status = str(client.get("door_status") or "").strip().lower()

        if status == "open":
            return True

        if status in ("closed", "close"):
            return False

        return _matter_bool(client.get("contact_open"))

    def _matter_cluster_names(child):
        clusters = []

        for cluster in child.get("clusters", []):
            if not isinstance(cluster, dict):
                continue

            name = str(cluster.get("name") or "").strip()
            value = str(cluster.get("value") or "").strip()
            label = name or value

            if label and label not in clusters:
                clusters.append(label)

        if clusters:
            return ",".join(clusters)

        kinds = child.get("kinds") if isinstance(child.get("kinds"), list) else []
        fallback = []

        for kind in kinds:
            if kind == "temperature":
                fallback.append("TemperatureMeasurement")
            elif kind == "humidity":
                fallback.append("RelativeHumidityMeasurement")
            elif kind == "contact":
                fallback.append("BooleanState")
            elif kind == "motion":
                fallback.append("OccupancySensing")
            elif kind == "switch":
                fallback.append("OnOff")
            elif kind == "button":
                fallback.append("Switch")
            elif kind == "battery":
                fallback.append("PowerSource")

        return ",".join(fallback)

    def _sync_matter_clients_locked(payload):
        payload = dict(payload or {})

        snapshot_result = runtime.snapshot_all(payload)
        snapshots = snapshot_result.get("snapshots") if isinstance(snapshot_result.get("snapshots"), list) else []
        synced_at = now_epoch()
        devices = []
        door_transition_events = []
        motion_transition_events = []
        environment_transition_events = []
        matter_activity_events = []

        defaults = {
            "ip": "matter",
            "last_seen": synced_at,
            "needs_heartbeat": False,
            "heartbeat_requested_at": 0,
            "heartbeat_pending": False,
            "provisioned": True,
            "battery": None,
            "armed": 0,
            "brand": "Matter",
            "androidVersion": "",
            "telemetry_count": 0,
            "pending_command": {},
            "version": "matter",
            "fcm_token": "",
            "fcm_token_at": 0,
            "detectedRole": "",
            "source": "matter",
            "manufacturer": "Matter",
            "matter_last_sync_at": synced_at,
            "zone_name": "",
        }

        def apply_snapshot(snapshot):
            if not isinstance(snapshot, dict) or not snapshot.get("ok"):
                return

            node_id = str(snapshot.get("node_id") or "").strip()
            snapshot_children = snapshot.get("children") if isinstance(snapshot.get("children"), list) else []

            if not node_id:
                return

            for child in snapshot_children:
                if not isinstance(child, dict):
                    continue

                reads = child.get("reads") if isinstance(child.get("reads"), dict) else {}
                primary_kinds = child.get("kinds") if isinstance(child.get("kinds"), list) else []

                if not primary_kinds:
                    continue

                endpoint = str(child.get("endpoint") or "").strip()

                if not endpoint:
                    continue

                kinds = child.get("kinds") if isinstance(child.get("kinds"), list) else []
                kind_label = _matter_kind_label(kinds)
                device_id = _matter_device_id(node_id, endpoint)
                existing_client = clients.get(device_id) if isinstance(clients.get(device_id), dict) else {}
                old_contact_open = _existing_contact_open(existing_client)
                old_motion_active = _matter_bool(existing_client.get("motion_active"))
                old_temperature_c = _matter_float(existing_client.get("temperature_c"))
                old_humidity_percent = _matter_float(existing_client.get("humidity_percent"))
                old_matter_onoff = _matter_bool(existing_client.get("matter_onoff"))
                old_button_position = _matter_int(existing_client.get("matter_button_position") if existing_client.get("matter_button_position") is not None else existing_client.get("matter_switch_position"))
                bridged_basic = child.get("bridged_basic") if isinstance(child.get("bridged_basic"), dict) else {}
                vendor_name = str(child.get("matter_vendor_name") or bridged_basic.get("vendor_name") or "").strip()
                product_name = str(child.get("matter_product_name") or bridged_basic.get("product_name") or "").strip()
                node_label = str(child.get("matter_node_label") or bridged_basic.get("node_label") or "").strip()
                hardware_version = str(
                    child.get("matter_hardware_version")
                    or bridged_basic.get("hardware_version_string")
                    or ""
                ).strip()
                software_version = str(
                    child.get("matter_software_version")
                    or bridged_basic.get("software_version_string")
                    or ""
                ).strip()
                serial_number = str(child.get("matter_serial_number") or bridged_basic.get("serial_number") or "").strip()
                matter_reachable = child.get("matter_reachable")

                if matter_reachable is None:
                    matter_reachable = bridged_basic.get("reachable")

                occupancy_state_value = child.get("occupancy_state_value")
                next_motion_active = _matter_bool(child.get("motion_active"))

                if occupancy_state_value is None:
                    occupancy_state_value = existing_client.get("occupancy_state_value")

                if next_motion_active is None:
                    next_motion_active = old_motion_active

                values = {
                    "deviceID": device_id,
                    "clientName": node_label or _matter_client_name(kind_label),
                    "clientRole": client_role_dss if kind_label in ("contact", "button") else "TLM",
                    "brand": vendor_name or "Matter",
                    "manufacturer": vendor_name or "Matter",
                    "model": product_name or _matter_model_name(kind_label),
                    "matter_endpoint": endpoint,
                    "matter_kind": kind_label,
                    "matter_kinds": kinds,
                    "matter_device_type": _matter_kind_name(kind_label),
                    "matter_cluster": _matter_cluster_names(child),
                    "matter_vendor_name": vendor_name,
                    "matter_product_name": product_name,
                    "matter_node_label": node_label,
                    "matter_hardware_version": hardware_version,
                    "matter_software_version": software_version,
                    "matter_serial_number": serial_number,
                    "matter_reachable": matter_reachable,
                    "matter_node_id": node_id,
                    "temperature_raw": child.get("temperature_raw"),
                    "temperature_c": child.get("temperature_c"),
                    "humidity_raw": child.get("humidity_raw"),
                    "humidity_percent": child.get("humidity_percent"),
                    "contact_state_value": child.get("contact_state_value"),
                    "contact_open": child.get("contact_open"),
                    "occupancy_state_value": occupancy_state_value,
                    "motion_active": next_motion_active,
                    "last_motion_at": existing_client.get("last_motion_at", 0),
                    "matter_onoff": child.get("matter_onoff"),
                    "matter_switch_position": child.get("matter_switch_position"),
                    "matter_switch_positions": child.get("matter_switch_positions"),
                    "matter_switch_multipress_max": child.get("matter_switch_multipress_max"),
                    "matter_button_position": child.get("matter_button_position") if child.get("matter_button_position") is not None else child.get("matter_switch_position"),
                    "matter_button_event": existing_client.get("matter_button_event", ""),
                    "matter_button_event_at": existing_client.get("matter_button_event_at", 0),
                    "matter_button_press_count": existing_client.get("matter_button_press_count"),
                    "matter_battery_percent_remaining_raw": child.get("matter_battery_percent_remaining_raw"),
                    "matter_battery_percent": child.get("matter_battery_percent"),
                    "matter_battery_charge_level": child.get("matter_battery_charge_level"),
                    "matter_battery_charge_state": child.get("matter_battery_charge_state"),
                    "matter_battery_replacement_needed": child.get("matter_battery_replacement_needed"),
                    "matter_battery_low": child.get("matter_battery_low"),
                    "battery_low": child.get("matter_battery_low"),
                    "battery_state": _matter_battery_state(child),
                    "matter_reads": reads,
                    "matter_battery_attr_reads": child.get("battery_attr_reads") if isinstance(child.get("battery_attr_reads"), dict) else {},
                    "matter_bridged_basic_reads": child.get("bridged_basic_reads") if isinstance(child.get("bridged_basic_reads"), dict) else {},
                    "battery": child.get("matter_battery_percent"),
                }

                door_status = ""

                if kind_label == "contact":
                    contact_open = _matter_contact_open(child, existing_client)
                    contact_open_when = _matter_contact_open_when(existing_client, child)

                    if contact_open is None:
                        contact_open = False

                    door_status = "open" if contact_open else "closed"
                    values.update({
                        "hasDSSHW": True,
                        "matter_contact_open_when": contact_open_when,
                        "contact_open": contact_open,
                        "door_status": door_status,
                        "openness_score": 1.0 if contact_open else 0.0,
                        "door_angle": 90.0 if contact_open else 0.0,
                        "door_event_ms": int(synced_at * 1000),
                        "last_transition_at": synced_at,
                        "calibrating": 0,
                    })

                    if "doorbell_muted" not in existing_client:
                        values["doorbell_muted"] = False

                elif kind_label == "motion" and old_motion_active is False and next_motion_active is True:
                    values["last_motion_at"] = synced_at

                devices.append(_upsert_matter_client(device_id, defaults, values))
                updated_client = clients.get(device_id)

                if isinstance(updated_client, dict):
                    next_temperature_c = _matter_float(updated_client.get("temperature_c"))
                    next_humidity_percent = _matter_float(updated_client.get("humidity_percent"))

                    if old_temperature_c is not None and next_temperature_c is not None and old_temperature_c != next_temperature_c:
                        environment_transition_events.append({
                            "client": dict(updated_client),
                            "kind": "temperature",
                            "value": next_temperature_c,
                            "previous_value": old_temperature_c,
                        })

                    if old_humidity_percent is not None and next_humidity_percent is not None and old_humidity_percent != next_humidity_percent:
                        environment_transition_events.append({
                            "client": dict(updated_client),
                            "kind": "humidity",
                            "value": next_humidity_percent,
                            "previous_value": old_humidity_percent,
                        })

                if kind_label == "contact" and old_contact_open is not None and old_contact_open != contact_open:
                    if isinstance(updated_client, dict):
                        event = {
                            "client": dict(updated_client),
                            "output": door_status,
                        }
                        door_transition_events.append(event)
                        matter_activity_events.append({
                            "client": event["client"],
                            "kind": "contact",
                            "output": door_status,
                        })

                elif kind_label == "motion" and old_motion_active is not None and next_motion_active is not None and old_motion_active != next_motion_active:
                    if isinstance(updated_client, dict):
                        event = {
                            "client": dict(updated_client),
                            "active": next_motion_active,
                        }
                        matter_activity_events.append({
                            "client": event["client"],
                            "kind": "motion",
                            "active": next_motion_active,
                        })

                        motion_transition_events.append(event)

                elif kind_label == "switch":
                    next_onoff = _matter_bool(child.get("matter_onoff"))

                    if old_matter_onoff is not None and next_onoff is not None and old_matter_onoff != next_onoff and isinstance(updated_client, dict):
                        matter_activity_events.append({
                            "client": dict(updated_client),
                            "kind": "switch",
                            "state": next_onoff,
                        })

                elif kind_label == "button":
                    next_position = _matter_int(child.get("matter_button_position") if child.get("matter_button_position") is not None else child.get("matter_switch_position"))

                    if old_button_position is not None and next_position is not None and old_button_position != next_position and isinstance(updated_client, dict):
                        matter_activity_events.append({
                            "client": dict(updated_client),
                            "kind": "button",
                            "position": next_position,
                        })

        def apply_updates():
            for snapshot in snapshots:
                apply_snapshot(snapshot)

        if state_lock is not None:
            with state_lock:
                apply_updates()
        else:
            apply_updates()

        if devices:
            if callable(save_state):
                save_state()
            elif callable(broadcast_state):
                broadcast_state()

        for event in matter_activity_events:
            kind = event.get("kind")

            if kind == "contact":
                _record_matter_contact_activity(event.get("client") or {}, event.get("output"))
            elif kind == "motion":
                _record_matter_motion_activity(event.get("client") or {}, event.get("active"))
            elif kind == "switch":
                _record_matter_switch_activity(event.get("client") or {}, event.get("state"))
            elif kind == "button":
                _record_matter_button_activity(event.get("client") or {}, event.get("position"))

        routes_changed = False

        for event in door_transition_events:
            routes_changed = bool(fire_door_routes(event.get("client") or {}, event.get("output"))) or routes_changed


        for event in motion_transition_events:
            routes_changed = bool(fire_camera_motion_routes(
                event.get("client") or {},
                event.get("active", False),
            )) or routes_changed

        for event in environment_transition_events:
            routes_changed = bool(fire_environment_routes(
                event.get("client") or {},
                event.get("kind"),
                event.get("value"),
                event.get("previous_value"),
            )) or routes_changed

        if routes_changed and callable(save_state):
            save_state()

        return {
            "ok": bool(snapshot_result.get("ok") and devices),
            "snapshot": snapshot_result,
            "devices": devices,
            "updated_at": synced_at,
        }

    def _try_sync_matter_clients(payload):
        if not matter_sync_lock.acquire(blocking=False):
            return {
                "ok": False,
                "busy": True,
                "error": "Matter sync is already running.",
            }

        matter_sync_active.set()
        runtime.stop_subscription()

        try:
            with matter_subscription_lock:
                return _sync_matter_clients_locked(payload)
        finally:
            matter_sync_active.clear()
            matter_subscription_restart.set()
            matter_sync_lock.release()

    def _apply_matter_contact_event(event):
        node_id = str(event.get("node_id") or "").strip()
        endpoint = str(event.get("endpoint") or "").strip()
        raw_contact = _matter_bool(event.get("contact_state_value"))

        if not endpoint or raw_contact is None:
            return False

        device_id = _matter_device_id(node_id, endpoint)
        synced_at = float(event.get("received_at") or now_epoch())
        route_event = None

        def apply_event_locked():
            nonlocal route_event

            client = clients.get(device_id)

            if not isinstance(client, dict):
                return False

            old_contact_open = _existing_contact_open(client)
            contact_open = _matter_contact_open({"contact_state_value": raw_contact}, client)
            contact_open_when = _matter_contact_open_when(client)

            if contact_open is None:
                return False

            door_status = "open" if contact_open else "closed"
            client.update({
                "last_seen": synced_at,
                "matter_last_sync_at": synced_at,
                "matter_kind": "contact",
                "matter_kinds": _matter_kinds_with(client, "contact"),
                "matter_device_type": "Contact Sensor",
                "matter_contact_open_when": contact_open_when,
                "contact_state_value": raw_contact,
                "contact_open": contact_open,
                "door_status": door_status,
                "openness_score": 1.0 if contact_open else 0.0,
                "door_angle": 90.0 if contact_open else 0.0,
                "door_event_ms": int(synced_at * 1000),
                "last_transition_at": synced_at,
                "stale": False,
            })

            if old_contact_open is not None and old_contact_open != contact_open:
                route_event = {
                    "client": dict(client),
                    "output": door_status,
                }

            return True

        if state_lock is not None:
            with state_lock:
                changed = apply_event_locked()
        else:
            changed = apply_event_locked()

        if not changed:
            return False

        if callable(save_state):
            save_state()
        elif callable(broadcast_state):
            broadcast_state()

        if route_event:
            _record_matter_contact_activity(route_event.get("client") or {}, route_event.get("output"))

        routes_changed = False

        if route_event:
            routes_changed = bool(fire_door_routes(route_event.get("client") or {}, route_event.get("output")))

        if routes_changed and callable(save_state):
            save_state()

        return True

    def _apply_matter_motion_event(event):
        node_id = str(event.get("node_id") or "").strip()
        endpoint = str(event.get("endpoint") or "").strip()
        occupancy_state_value = _matter_int(event.get("occupancy_state_value"))

        if not endpoint or occupancy_state_value is None:
            return False

        device_id = _matter_device_id(node_id, endpoint)
        synced_at = float(event.get("received_at") or now_epoch())
        motion_active = bool(occupancy_state_value & 1)
        route_event = None
        activity_event = None

        def apply_event_locked():
            nonlocal route_event, activity_event

            client = clients.get(device_id)

            if not isinstance(client, dict):
                return False

            old_motion_active = _matter_bool(client.get("motion_active"))
            client.update({
                "last_seen": synced_at,
                "matter_last_sync_at": synced_at,
                "matter_kind": "motion",
                "matter_kinds": _matter_kinds_with(client, "motion"),
                "matter_device_type": "Motion Sensor",
                "occupancy_state_value": occupancy_state_value,
                "motion_active": motion_active,
                "stale": False,
            })

            if motion_active:
                client["last_motion_at"] = synced_at

            if old_motion_active is not None and old_motion_active != motion_active:
                activity_event = {
                    "client": dict(client),
                    "active": motion_active,
                }
                route_event = dict(activity_event)

            return True

        if state_lock is not None:
            with state_lock:
                changed = apply_event_locked()
        else:
            changed = apply_event_locked()

        if not changed:
            return False

        if callable(save_state):
            save_state()
        elif callable(broadcast_state):
            broadcast_state()

        if activity_event:
            _record_matter_motion_activity(activity_event.get("client") or {}, activity_event.get("active"))

        routes_changed = False

        if route_event:
            routes_changed = bool(fire_camera_motion_routes(
                route_event.get("client") or {},
                route_event.get("active", False),
            ))

        if routes_changed and callable(save_state):
            save_state()

        return True

    def _apply_matter_environment_event(event):
        kind = str(event.get("kind") or "").strip().lower()
        node_id = str(event.get("node_id") or "").strip()
        endpoint = str(event.get("endpoint") or "").strip()

        if kind not in ("temperature", "humidity") or not node_id or not endpoint:
            return False

        raw_key = "temperature_raw" if kind == "temperature" else "humidity_raw"
        value_key = "temperature_c" if kind == "temperature" else "humidity_percent"
        raw_value = _matter_int(event.get(raw_key))

        if raw_value is None:
            return False

        device_id = _matter_device_id(node_id, endpoint)
        synced_at = float(event.get("received_at") or now_epoch())
        route_event = None

        def apply_event_locked():
            nonlocal route_event

            client = clients.get(device_id)

            if not isinstance(client, dict):
                return False

            previous_value = _matter_float(client.get(value_key))
            next_value = round(raw_value / 100.0, 2)

            client.update({
                "last_seen": synced_at,
                "matter_last_sync_at": synced_at,
                "matter_kinds": _matter_kinds_with(client, kind),
                raw_key: raw_value,
                value_key: next_value,
                "stale": False,
            })

            if previous_value is not None and previous_value != next_value:
                route_event = {
                    "client": dict(client),
                    "kind": kind,
                    "value": next_value,
                    "previous_value": previous_value,
                }

            return True

        if state_lock is not None:
            with state_lock:
                changed = apply_event_locked()
        else:
            changed = apply_event_locked()

        if not changed:
            return False

        if callable(save_state):
            save_state()
        elif callable(broadcast_state):
            broadcast_state()

        routes_changed = False

        if route_event:
            routes_changed = bool(fire_environment_routes(
                route_event.get("client") or {},
                route_event.get("kind"),
                route_event.get("value"),
                route_event.get("previous_value"),
            ))

        if routes_changed and callable(save_state):
            save_state()

        return True

    def _matter_env_bool(name, default=True):
        raw = os.environ.get(name)

        if raw is None:
            return bool(default)

        return str(raw).strip().lower() not in ("0", "false", "no", "off")

    def _matter_env_seconds(name, default, minimum=0.0):
        raw = str(os.environ.get(name, default)).strip()

        try:
            value = float(raw)
        except Exception:
            value = float(default)

        return max(float(minimum), value)

    def _apply_matter_sensor_event(event):
        kind = str((event or {}).get("kind") or "").strip().lower()

        if kind in ("temperature", "humidity"):
            return _apply_matter_environment_event(event)

        if kind == "contact":
            return _apply_matter_contact_event(event)

        if kind == "motion":
            return _apply_matter_motion_event(event)

        return False

    def _matter_sensor_subscribe_loop():
        env_prefix = "KOTIBOT_MATTER_SENSOR_SUBSCRIBE"

        if not _matter_env_bool(f"{env_prefix}_ENABLED", True):
            return

        initial_delay = _matter_env_seconds(f"{env_prefix}_INITIAL_DELAY_SECONDS", 0.0, 0.0)
        retry_delay = _matter_env_seconds(f"{env_prefix}_RETRY_SECONDS", 15.0, 5.0)
        min_interval = int(_matter_env_seconds(f"{env_prefix}_MIN_SECONDS", 0.0, 0.0))
        max_interval = int(_matter_env_seconds(f"{env_prefix}_MAX_SECONDS", 300.0, 1.0))
        last_error_at = {}

        if matter_sync_stop.wait(initial_delay):
            return

        while not matter_startup_sync_complete.is_set():
            if matter_sync_stop.wait(0.25):
                return

        while not matter_sync_stop.is_set():
            if matter_maintenance.is_set() or matter_sync_active.is_set():
                if matter_sync_stop.wait(1.0):
                    return

                continue

            try:
                node_ids = runtime.matter_node_ids({})

                for node_id in node_ids:
                    if matter_sync_stop.is_set():
                        return

                    with matter_subscription_lock:
                        if matter_maintenance.is_set() or matter_sync_active.is_set():
                            break

                        result = runtime.subscribe_sensor_states(
                            {
                                "node_id": node_id,
                                "min_interval": min_interval,
                                "max_interval": max_interval,
                            },
                            _apply_matter_sensor_event,
                            matter_sync_stop,
                        )

                    if matter_sync_stop.is_set():
                        return

                    if matter_maintenance.is_set() or matter_sync_active.is_set():
                        break

                    if not result.get("ok"):
                        current_time = now_epoch()

                        if current_time - last_error_at.get(node_id, 0) >= 60:
                            last_error_at[node_id] = current_time
                            app.logger.warning(
                                "Matter sensor subscription failed for node %s: %s",
                                node_id,
                                result.get("error")
                                or f"process exited with {result.get('returncode')}",
                            )
            except Exception:
                current_time = now_epoch()

                if current_time - last_error_at.get("__loop__", 0) >= 60:
                    last_error_at["__loop__"] = current_time
                    app.logger.exception("Matter sensor subscription loop failed")

            if matter_subscription_restart.wait(retry_delay):
                matter_subscription_restart.clear()

            if matter_sync_stop.is_set():
                return

    def _matter_sync_loop():
        if not _matter_env_bool("KOTIBOT_MATTER_SYNC_ENABLED", True):
            matter_startup_sync_complete.set()
            return

        initial_delay = _matter_env_seconds(
            "KOTIBOT_MATTER_SYNC_INITIAL_DELAY_SECONDS",
            0.0,
            0.0,
        )

        if matter_sync_stop.wait(initial_delay):
            return

        while matter_maintenance.is_set():
            if matter_sync_stop.wait(1.0):
                return

        try:
            result = _try_sync_matter_clients({
                "auto": True,
            })

            if (
                not result.get("ok")
                and result.get("error")
            ):
                app.logger.warning(
                    "Matter startup sync failed: %s",
                    result.get("error"),
                )
        except Exception:
            app.logger.exception(
                "Matter startup sync failed"
            )
        finally:
            matter_startup_sync_complete.set()

    def run(handler):
        try:
            return jsonify(handler())
        except ValueError as e:
            return _error_response(e, 400)

    def _save_matter_settings():
        nonlocal matter_settings

        result = runtime.save_settings(_json_payload())
        saved_settings = result.get("settings") if isinstance(result.get("settings"), dict) else {}
        matter_settings = dict(saved_settings)

        return result

    @app.post("/api/matter/recommission")
    def matter_recommission():
        return run(_recommission_matter_connection)

    @app.get("/api/matter/status")
    def matter_status():
        return run(runtime.status)

    @app.post("/api/matter/settings")
    def matter_save_settings():
        return run(_save_matter_settings)

    @app.post("/api/matter/node")
    def matter_save_node():
        return run(lambda: runtime.save_node(_json_payload()))

    @app.post("/api/matter/remove-node")
    def matter_remove_node():
        return run(lambda: runtime.remove_node(_json_payload()))

    @app.post("/api/matter/commission-code")
    def matter_commission_code():
        return run(lambda: runtime.commission_code(_json_payload()))

    @app.post("/api/matter/inspect")
    def matter_inspect():
        return run(lambda: runtime.inspect_node(_json_payload()))

    @app.post("/api/matter/read")
    def matter_read():
        return run(lambda: runtime.read_attribute(_json_payload()))

    @app.get("/api/matter/snapshot")
    def matter_snapshot():
        return run(lambda: runtime.snapshot_all({}))

    @app.post("/api/matter/snapshot")
    def matter_snapshot_post():
        return run(lambda: runtime.snapshot_all(_json_payload()))

    @app.get("/api/matter/sync")
    def matter_sync():
        return run(lambda: _try_sync_matter_clients({}))

    @app.post("/api/matter/sync")
    def matter_sync_post():
        return run(lambda: _try_sync_matter_clients(_json_payload()))

    @app.post("/api/matter/on")
    def matter_on():
        return run(lambda: runtime.onoff(_json_payload(), True))

    @app.post("/api/matter/off")
    def matter_off():
        return run(lambda: runtime.onoff(_json_payload(), False))

    @app.post("/api/matter/level")
    def matter_level():
        return run(lambda: runtime.level(_json_payload()))

    @app.post("/api/matter/color-temperature")
    def matter_color_temperature():
        return run(lambda: runtime.color_temperature(_json_payload()))

    app.config["KOTIBOT_MATTER_RUNTIME"] = runtime
    app.config["KOTIBOT_MATTER_SYNC_LOOP"] = _matter_sync_loop
    app.config["KOTIBOT_MATTER_SENSOR_SUBSCRIBE_LOOP"] = _matter_sensor_subscribe_loop

    return {
        "runtime": runtime,
    }

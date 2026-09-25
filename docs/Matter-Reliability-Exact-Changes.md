# KotiBot Matter reliability changes

Authoritative PRE: `7f43621c11b90dc1cce9ecd9e374b9a2a3b5f332`.

Apply each exact PRE → POST replacement in order. Each PRE was checked to occur once in the authoritative source. No production files are included in the support ZIP.

## server_core/state.py

### Change 1

PRE

```python
                    c['tapo_recording'] = False
                    c['tapo_recording_enabled'] = False

                clients[deviceID] = c

            _write_current_state_files()
```

POST

```python
                    c['tapo_recording'] = False
                    c['tapo_recording_enabled'] = False

                if str(c.get('source') or '').strip().lower() == 'matter':
                    # Restored observations are not evidence of a live device.
                    # Unknown values also make the first report a baseline,
                    # rather than an automation/security transition.
                    for field in (
                        'matter_reachable', 'temperature_raw', 'temperature_c',
                        'humidity_raw', 'humidity_percent', 'contact_state_value',
                        'contact_open', 'occupancy_state_value', 'motion_active',
                        'matter_onoff', 'matter_switch_position',
                        'matter_button_position', 'matter_button_press_count',
                        'battery', 'battery_low', 'battery_state',
                        'matter_battery_percent_remaining_raw',
                        'matter_battery_percent', 'matter_battery_charge_level',
                        'matter_battery_charge_state',
                        'matter_battery_replacement_needed', 'matter_battery_low',
                    ):
                        c[field] = None
                    for field in (
                        'matter_last_sync_at', 'last_motion_at', 'door_event_ms',
                        'last_transition_at', 'matter_button_event_at',
                    ):
                        c[field] = 0
                    c['door_status'] = 'unknown'
                    c['matter_button_event'] = ''

                clients[deviceID] = c

            _write_current_state_files()
```

## server_core/status.py

### Change 1

PRE

```python
        current_time = now_epoch() if now is None else now

        if str(c.get('source') or '').strip().lower() == 'matter':
            last_seen = float(c.get('matter_last_sync_at', 0) or c.get('last_seen', 0) or 0)
            node_id = str(c.get('matter_node_id') or '').strip()

            if node_id:
                last_seen = max(
                    [last_seen] + [
                        float(peer.get('matter_last_sync_at', 0) or peer.get('last_seen', 0) or 0)
                        for peer in CLIENTS.values()
                        if isinstance(peer, dict)
                        and str(peer.get('source') or '').strip().lower() == 'matter'
                        and str(peer.get('matter_node_id') or '').strip() == node_id
                    ]
                )

            return last_seen == 0 or (current_time - last_seen) > MATTER_STALE_CLIENT_SECONDS

```

POST

```python
        current_time = now_epoch() if now is None else now

        if str(c.get('source') or '').strip().lower() == 'matter':
            if c.get('matter_reachable') is False:
                return True
            last_seen = float(c.get('matter_last_sync_at', 0) or c.get('last_seen', 0) or 0)

            return last_seen == 0 or (current_time - last_seen) > MATTER_STALE_CLIENT_SECONDS

```

## subsystems/matter/matter_routes.py

### Change 1

PRE

```python
import math
import os
from pathlib import Path
from threading import Event, Lock

from flask import jsonify, request

```

POST

```python
import math
import os
from pathlib import Path
from threading import Event, Lock, Thread

from flask import jsonify, request

```

### Change 2

PRE

```python
            runtime.stop_subscription()

            try:
                with matter_subscription_lock, matter_sync_lock:
                    result = runtime.recommission_node(payload)

                    if not result.get("ok"):
```

POST

```python
            runtime.stop_subscription()

            try:
                with matter_sync_lock, matter_subscription_lock:
                    result = runtime.recommission_node(payload)

                    if not result.get("ok"):
```

### Change 3

PRE

```python
                if not primary_kinds:
                    continue

                endpoint = str(child.get("endpoint") or "").strip()

                if not endpoint:
```

POST

```python
                if not primary_kinds:
                    continue

                # Cached discovery identifies an endpoint; only a successful
                # live attribute read establishes its current state.
                if not any(
                    isinstance(reads.get(kind), dict)
                    and reads[kind].get("ok")
                    and reads[kind].get("parsed")
                    for kind in primary_kinds
                    if kind != "battery" or primary_kinds == ["battery"]
                ):
                    continue

                endpoint = str(child.get("endpoint") or "").strip()

                if not endpoint:
```

### Change 4

PRE

```python
                    contact_open = _matter_contact_open(child, existing_client)
                    contact_open_when = _matter_contact_open_when(existing_client, child)

                    if contact_open is None:
                        contact_open = False

                    door_status = "open" if contact_open else "closed"
                    values.update({
                        "hasDSSHW": True,
                        "matter_contact_open_when": contact_open_when,
```

POST

```python
                    contact_open = _matter_contact_open(child, existing_client)
                    contact_open_when = _matter_contact_open_when(existing_client, child)

                    door_status = (
                        "unknown" if contact_open is None
                        else "open" if contact_open else "closed"
                    )
                    values.update({
                        "hasDSSHW": True,
                        "matter_contact_open_when": contact_open_when,
```

### Change 5

PRE

```python
                            "previous_value": old_humidity_percent,
                        })

                if kind_label == "contact" and old_contact_open is not None and old_contact_open != contact_open:
                    if isinstance(updated_client, dict):
                        event = {
                            "client": dict(updated_client),
```

POST

```python
                            "previous_value": old_humidity_percent,
                        })

                if kind_label == "contact" and old_contact_open is not None and contact_open is not None and old_contact_open != contact_open:
                    if isinstance(updated_client, dict):
                        event = {
                            "client": dict(updated_client),
```

### Change 6

PRE

```python
            }

        matter_sync_active.set()
        runtime.stop_subscription()

        try:
            with matter_subscription_lock:
                return _sync_matter_clients_locked(payload)
        finally:
```

POST

```python
            }

        matter_sync_active.set()
        matter_subscription_restart.set()

        try:
            runtime.stop_subscription()
            with matter_subscription_lock:
                return _sync_matter_clients_locked(payload)
        finally:
```

### Change 7

PRE

```python
                "stale": False,
            })

            if old_contact_open is not None and old_contact_open != contact_open:
                route_event = {
                    "client": dict(client),
                    "output": door_status,
```

POST

```python
                "stale": False,
            })

            if not event.get("baseline") and old_contact_open is not None and old_contact_open != contact_open:
                route_event = {
                    "client": dict(client),
                    "output": door_status,
```

### Change 8

PRE

```python
            if motion_active:
                client["last_motion_at"] = synced_at

            if old_motion_active is not None and old_motion_active != motion_active:
                activity_event = {
                    "client": dict(client),
                    "active": motion_active,
```

POST

```python
            if motion_active:
                client["last_motion_at"] = synced_at

            if not event.get("baseline") and old_motion_active is not None and old_motion_active != motion_active:
                activity_event = {
                    "client": dict(client),
                    "active": motion_active,
```

### Change 9

PRE

```python
                "stale": False,
            })

            if previous_value is not None and previous_value != next_value:
                route_event = {
                    "client": dict(client),
                    "kind": kind,
```

POST

```python
                "stale": False,
            })

            if not event.get("baseline") and previous_value is not None and previous_value != next_value:
                route_event = {
                    "client": dict(client),
                    "kind": kind,
```

### Change 10

PRE

```python
    def _apply_matter_sensor_event(event):
        kind = str((event or {}).get("kind") or "").strip().lower()

        if kind in ("temperature", "humidity"):
            return _apply_matter_environment_event(event)

```

POST

```python
    def _apply_matter_sensor_event(event):
        kind = str((event or {}).get("kind") or "").strip().lower()

        if kind in ("report", "switch", "reachable"):
            return _apply_matter_device_event(event)

        if kind in ("temperature", "humidity"):
            return _apply_matter_environment_event(event)

```

### Change 11

PRE

```python
            return _apply_matter_motion_event(event)

        return False

    def _matter_sensor_subscribe_loop():
        env_prefix = "KOTIBOT_MATTER_SENSOR_SUBSCRIBE"
```

POST

```python
            return _apply_matter_motion_event(event)

        return False

    def _apply_matter_device_event(event):
        kind = event.get("kind")
        node_id = str(event.get("node_id") or "").strip()
        endpoint = str(event.get("endpoint") or "").strip()
        received_at = float(event.get("received_at") or now_epoch())
        changed = False
        updated = False
        activity = None

        def apply_locked():
            nonlocal changed, updated, activity
            if kind == "report":
                for client in clients.values():
                    if (
                        str(client.get("source") or "").lower() == "matter"
                        and str(client.get("matter_node_id") or "") == node_id
                        and client.get("matter_last_sync_at", 0)
                        and client.get("matter_reachable") is not False
                    ):
                        client["last_seen"] = received_at
                        client["matter_last_sync_at"] = received_at
                        updated = True
                return

            client = clients.get(_matter_device_id(node_id, endpoint))
            if not isinstance(client, dict):
                return
            key = "matter_onoff" if kind == "switch" else "matter_reachable"
            value = _matter_bool(event.get(key))
            if value is None:
                return
            previous = _matter_bool(client.get(key))
            client[key] = value
            client["last_seen"] = received_at
            client["matter_last_sync_at"] = received_at
            changed = previous != value
            updated = True
            if kind == "switch" and not event.get("baseline") and previous is not None and changed:
                activity = dict(client)

        if state_lock is not None:
            with state_lock:
                apply_locked()
        else:
            apply_locked()
        if changed and callable(save_state):
            save_state()
        elif updated and callable(broadcast_state):
            broadcast_state()
        if activity:
            _record_matter_switch_activity(activity, activity["matter_onoff"])
        return updated

    def _matter_sensor_subscribe_loop():
        env_prefix = "KOTIBOT_MATTER_SENSOR_SUBSCRIBE"
```

### Change 12

PRE

```python
        min_interval = int(_matter_env_seconds(f"{env_prefix}_MIN_SECONDS", 0.0, 0.0))
        max_interval = int(_matter_env_seconds(f"{env_prefix}_MAX_SECONDS", 300.0, 1.0))
        last_error_at = {}

        if matter_sync_stop.wait(initial_delay):
            return
```

POST

```python
        min_interval = int(_matter_env_seconds(f"{env_prefix}_MIN_SECONDS", 0.0, 0.0))
        max_interval = int(_matter_env_seconds(f"{env_prefix}_MAX_SECONDS", 300.0, 1.0))
        last_error_at = {}

        class SubscriptionStop:
            def is_set(self):
                return (
                    matter_sync_stop.is_set()
                    or matter_maintenance.is_set()
                    or matter_sync_active.is_set()
                    or matter_subscription_restart.is_set()
                )

        subscription_stop = SubscriptionStop()

        def monitor_node(node_id):
            # One persistent subscription per node. A quiet or unreachable
            # node must never monopolize the other nodes' report delivery.
            delay = retry_delay
            while not subscription_stop.is_set():
                try:
                    result = runtime.subscribe_sensor_states(
                        {
                            "node_id": node_id,
                            "min_interval": min_interval,
                            "max_interval": max_interval,
                        },
                        _apply_matter_sensor_event,
                        subscription_stop,
                    )
                    if subscription_stop.is_set():
                        return
                    current_time = now_epoch()
                    if current_time - last_error_at.get(node_id, 0) >= 60:
                        last_error_at[node_id] = current_time
                        app.logger.warning("Matter subscription ended; recovery scheduled")
                    if result.get("event_count", 0):
                        delay = retry_delay
                except Exception:
                    if subscription_stop.is_set():
                        return
                    app.logger.warning("Matter subscription unavailable; recovery scheduled")
                if matter_subscription_restart.wait(delay):
                    return
                delay = min(delay * 2, max(300.0, retry_delay))

        if matter_sync_stop.wait(initial_delay):
            return
```

### Change 13

PRE

```python
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

```

POST

```python
            try:
                node_ids = runtime.matter_node_ids({})

                with matter_subscription_lock:
                    if matter_maintenance.is_set() or matter_sync_active.is_set():
                        continue
                    matter_subscription_restart.clear()
                    workers = [
                        Thread(target=monitor_node, args=(node_id,), daemon=True)
                        for node_id in node_ids
                    ]
                    for worker in workers:
                        worker.start()
                    for worker in workers:
                        worker.join()
            except Exception:
                current_time = now_epoch()

```

## subsystems/matter/matter_runtime.py

### Change 1

PRE

```python

def _parse_occupancy_value(stdout: str) -> int | None:
    text = _strip_ansi(stdout)
    match = re.search(r"\bOccupancy:\s*(\d+)\b", text or "", re.IGNORECASE)

    return int(match.group(1)) if match else None

def _parse_report_endpoint(stdout: str) -> str:
    text = _strip_ansi(stdout)
```

POST

```python

def _parse_occupancy_value(stdout: str) -> int | None:
    text = _strip_ansi(stdout)
    match = re.search(r"\bOccupancy:\s*(0x[0-9a-f]+|\d+)\b", text or "", re.IGNORECASE)

    if not match:
        return None
    value = match.group(1)
    return int(value, 16 if value.lower().startswith("0x") else 10)

def _parse_report_endpoint(stdout: str) -> str:
    text = _strip_ansi(stdout)
```

### Change 2

PRE

```python

                child_snapshot["reads"][kind] = _matter_read_debug(read, parsed_value=raw_value, parsed_ok=parsed_ok)

                if kind == "temperature":
                    child_snapshot["temperature_raw"] = raw_value

```

POST

```python

                child_snapshot["reads"][kind] = _matter_read_debug(read, parsed_value=raw_value, parsed_ok=parsed_ok)

                if not read_ok:
                    continue

                if kind == "temperature":
                    child_snapshot["temperature_raw"] = raw_value

```

### Change 3

PRE

```python

        ok = bool(
            snapshot_children
            and (valid_read_count > 0 or discovery.get("ok"))
        )

        return {
```

POST

```python

        ok = bool(
            snapshot_children
            and valid_read_count > 0
        )

        return {
```

### Change 4

PRE

```python
            "humidity": "0x405",
            "contact": "0x45",
            "motion": "0x406",
        }
        subscription_paths = []
        seen_paths = set()
```

POST

```python
            "humidity": "0x405",
            "contact": "0x45",
            "motion": "0x406",
            "switch": "0x6",
        }
        subscription_paths = []
        seen_paths = set()
```

### Change 5

PRE

```python
                path = (cluster_id, "0x0", endpoint)

                if cluster_id and path not in seen_paths:
                    seen_paths.add(path)
                    subscription_paths.append(path)

```

POST

```python
                path = (cluster_id, "0x0", endpoint)

                if cluster_id and path not in seen_paths:
                    seen_paths.add(path)
                    subscription_paths.append(path)

            if child.get("bridged_basic"):
                path = ("0x39", "0x11", endpoint)
                if path not in seen_paths:
                    seen_paths.add(path)
                    subscription_paths.append(path)

```

### Change 6

PRE

```python
            "true",
        ]
        event_count = 0
        proc = None
        output_queue = Queue()
        reported_endpoint = ""
        reported_cluster = None
        last_event_at = started_at
        watchdog_seconds = max_interval + 15
        watchdog_expired = False

```

POST

```python
            "true",
        ]
        event_count = 0
        reported_values = set()
        proc = None
        output_queue = Queue()
        reported_endpoint = ""
        reported_cluster = None
        last_event_at = time.monotonic()
        watchdog_seconds = max_interval + 15
        watchdog_expired = False

```

### Change 7

PRE

```python

                while True:
                    if stop_event is not None and stop_event.is_set():
                        break

                    try:
```

POST

```python

                while True:
                    if stop_event is not None and stop_event.is_set():
                        proc.terminate()
                        break

                    if time.monotonic() - last_event_at > watchdog_seconds:
                        watchdog_expired = True
                        proc.terminate()
                        break

                    try:
```

### Change 8

PRE

```python
                        if proc.poll() is not None:
                            break

                        if self.now_epoch() - last_event_at > watchdog_seconds:
                            watchdog_expired = True
                            proc.terminate()
                            break

                        continue

                    if raw_line is None:
                        break

                    next_endpoint = _parse_report_endpoint(raw_line)

```

POST

```python
                        if proc.poll() is not None:
                            break

                        continue

                    if raw_line is None:
                        break

                    # A valid subscription can report no changed attributes.
                    # Count received ReportData frames, not console noise or
                    # only changes, when checking the subscription's liveness.
                    if "ReportDataMessage =" in _strip_ansi(raw_line):
                        last_event_at = time.monotonic()
                        reported_endpoint = ""
                        reported_cluster = None
                        on_value({
                            "kind": "report",
                            "node_id": node_id,
                            "received_at": self.now_epoch(),
                        })
                        continue

                    next_endpoint = _parse_report_endpoint(raw_line)

```

### Change 9

PRE

```python
                            "contact_state_value": raw_value,
                            "received_at": self.now_epoch(),
                        }
                    elif reported_cluster == 1030:
                        raw_value = _parse_occupancy_value(raw_line)

```

POST

```python
                            "contact_state_value": raw_value,
                            "received_at": self.now_epoch(),
                        }
                    elif reported_cluster in (6, 57):
                        label = "OnOff" if reported_cluster == 6 else "Reachable"
                        match = re.search(
                            rf"\b{label}:\s*(TRUE|FALSE)\b",
                            _strip_ansi(raw_line), re.IGNORECASE,
                        )
                        if match is None or not reported_endpoint:
                            continue
                        event = {
                            "kind": "switch" if reported_cluster == 6 else "reachable",
                            "node_id": node_id,
                            "endpoint": reported_endpoint,
                            "matter_onoff" if reported_cluster == 6 else "matter_reachable":
                                match.group(1).upper() == "TRUE",
                            "received_at": self.now_epoch(),
                        }
                    elif reported_cluster == 1030:
                        raw_value = _parse_occupancy_value(raw_line)

```

### Change 10

PRE

```python
                        continue

                    event_count += 1
                    last_event_at = self.now_epoch()
                    on_value(event)

            returncode = proc.wait(timeout=2) if proc.poll() is None else proc.returncode
```

POST

```python
                        continue

                    event_count += 1
                    report_key = (reported_endpoint, reported_cluster)
                    event["baseline"] = report_key not in reported_values
                    reported_values.add(report_key)
                    last_event_at = time.monotonic()
                    on_value(event)

            returncode = proc.wait(timeout=2) if proc.poll() is None else proc.returncode
```

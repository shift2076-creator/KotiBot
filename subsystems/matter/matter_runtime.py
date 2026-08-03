from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from queue import Empty, Queue
from threading import Lock, Thread
from typing import Any

from server_core.io import read_json, write_json_atomic

_ALLOWED_TOKEN_RE = re.compile(r"^[A-Za-z0-9_.:-]+$")
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
_MATTER_DEBUG_TEXT_LIMIT = 24000

_MATTER_CAPABILITY_DEFINITIONS = {
    "temperature": {
        "cluster_id": "1026",
        "cluster_name": "TemperatureMeasurement",
        "chip_cluster": "temperaturemeasurement",
        "attribute": "measured-value",
        "value_kind": "measured",
    },
    "humidity": {
        "cluster_id": "1029",
        "cluster_name": "RelativeHumidityMeasurement",
        "chip_cluster": "relativehumiditymeasurement",
        "attribute": "measured-value",
        "value_kind": "measured",
    },
    "contact": {
        "cluster_id": "69",
        "cluster_name": "BooleanState",
        "chip_cluster": "booleanstate",
        "attribute": "state-value",
        "value_kind": "bool",
    },
    "motion": {
        "cluster_id": "1030",
        "cluster_name": "OccupancySensing",
        "chip_cluster": "occupancysensing",
        "attribute": "occupancy",
        "value_kind": "bitmap",
    },
    "switch": {
        "cluster_id": "6",
        "cluster_name": "OnOff",
        "chip_cluster": "onoff",
        "attribute": "on-off",
        "value_kind": "bool",
    },
    "button": {
        "cluster_id": "59",
        "cluster_name": "Switch",
        "chip_cluster": "switch",
        "attribute": "current-position",
        "value_kind": "int",
    },
    "battery": {
        "cluster_id": "47",
        "cluster_name": "PowerSource",
        "chip_cluster": "powersource",
        "attribute": "bat-charge-level",
        "value_kind": "int",
    },
}

_MATTER_BRIDGED_BASIC_CLUSTER_ID = "57"
_MATTER_BRIDGED_BASIC_CLUSTER_NAME = "BridgedDeviceBasicInformation"
_MATTER_BRIDGED_BASIC_ATTRIBUTES = {
    "vendor_name": {
        "attribute": "vendor-name",
        "label": "VendorName",
        "kind": "string",
    },
    "product_name": {
        "attribute": "product-name",
        "label": "ProductName",
        "kind": "string",
    },
    "node_label": {
        "attribute": "node-label",
        "label": "NodeLabel",
        "kind": "string",
    },
    "hardware_version_string": {
        "attribute": "hardware-version-string",
        "label": "HardwareVersionString",
        "kind": "string",
    },
    "software_version_string": {
        "attribute": "software-version-string",
        "label": "SoftwareVersionString",
        "kind": "string",
    },
    "serial_number": {
        "attribute": "serial-number",
        "label": "SerialNumber",
        "kind": "string",
    },
    "reachable": {
        "attribute": "reachable",
        "label": "Reachable",
        "kind": "bool",
    },
}

def _strip_ansi(value: Any) -> str:
    return _ANSI_RE.sub("", _to_text(value))

def _parse_descriptor_entries(stdout: str, list_name: str) -> list[dict[str, str]]:
    entries = []
    in_list = False

    for raw_line in _to_text(stdout).splitlines():
        line = _strip_ansi(raw_line)

        if f"{list_name}:" in line:
            in_list = True
            continue

        if not in_list:
            continue

        match = re.search(r"\[\d+\]:\s*(\d+)(?:\s*\(([^)]+)\))?", line)

        if match:
            entries.append({
                "value": match.group(1),
                "name": (match.group(2) or "").strip(),
            })
            continue

        if entries and re.search(r"\[(EM|CTL|DL|IN|FP|TS|SC)\]", line):
            break

    return entries

def _cluster_entry_matches(entry: dict[str, str], definition: dict[str, str]) -> bool:
    value = str(entry.get("value") or "").strip()
    name = str(entry.get("name") or "").strip().lower().replace(" ", "")
    cluster_id = str(definition.get("cluster_id") or "").strip()
    cluster_name = str(definition.get("cluster_name") or "").strip().lower().replace(" ", "")

    return value == cluster_id or bool(name and name == cluster_name)

def _cluster_list_has(cluster_entries: Any, cluster_id: str, cluster_name: str) -> bool:
    if not isinstance(cluster_entries, list):
        return False

    clean_cluster_id = str(cluster_id or "").strip()
    clean_cluster_name = str(cluster_name or "").strip().lower().replace(" ", "")

    for entry in cluster_entries:
        if not isinstance(entry, dict):
            continue

        value = str(entry.get("value") or "").strip()
        name = str(entry.get("name") or "").strip().lower().replace(" ", "")

        if value == clean_cluster_id or bool(name and name == clean_cluster_name):
            return True

    return False

def _matter_kind_sort_key(kind: str) -> int:
    order = {
        "temperature": 10,
        "humidity": 20,
        "contact": 30,
        "motion": 40,
        "switch": 50,
        "button": 60,
        "battery": 90,
    }
    return order.get(kind, 100)

def _clean_token(value: Any, *, field_name: str) -> str:
    token = str(value or "").strip()

    if not token:
        raise ValueError(f"Missing {field_name}")

    if not _ALLOWED_TOKEN_RE.match(token):
        raise ValueError(f"Invalid {field_name}")

    return token

def _clean_node_id(value: Any) -> str:
    token = _clean_token(value, field_name="node_id")
    return token

def _clean_endpoint(value: Any) -> str:
    token = _clean_token(value, field_name="endpoint")
    return token

def _clean_cluster(value: Any) -> str:
    token = _clean_token(value, field_name="cluster").lower()
    aliases = {
        "on_off": "onoff",
        "on-off": "onoff",
        "level_control": "levelcontrol",
        "level-control": "levelcontrol",
        "color_control": "colorcontrol",
        "color-control": "colorcontrol",
        "temperature": "temperaturemeasurement",
        "temperature_measurement": "temperaturemeasurement",
        "humidity": "relativehumiditymeasurement",
        "relative_humidity": "relativehumiditymeasurement",
        "occupancy": "occupancysensing",
        "occupancy_sensing": "occupancysensing",
        "boolean_state": "booleanstate",
        "boolean-state": "booleanstate",
        "generic_switch": "switch",
        "generic-switch": "switch",
        "momentary_switch": "switch",
        "momentary-switch": "switch",
        "button": "switch",
    }
    return aliases.get(token, token)

def _clean_attribute(value: Any) -> str:
    token = _clean_token(value, field_name="attribute")
    return token

def _clean_temperature_unit(value: Any) -> str:
    return "f" if str(value or "").strip().lower() == "f" else "c"

def _load_json_object(path: Path) -> dict[str, Any]:
    try:
        data = read_json(path)
    except FileNotFoundError:
        return {}
    except Exception:
        return {}

    return data if isinstance(data, dict) else {}

def _write_json_object(path: Path, data: dict[str, Any]) -> None:
    write_json_atomic(path, data)

_MATTER_LIST_VALUE_RE = re.compile(r"\[\s*\d+\s*\]\s*:\s*(\d+)(?:\s*\(([^)]+)\))?", re.I)
_MATTER_ATTR_VALUE_RE = re.compile(r"^\s*(?:\[\s*\d+\s*\]\s*:)?\s*([A-Za-z][A-Za-z0-9_ -]*)\s*[:=]\s*(.+?)\s*$")

def _chip_stdout(result: dict[str, Any]) -> str:
    return str((result or {}).get("stdout") or "")

def _chip_success(result: dict[str, Any]) -> bool:
    return bool(isinstance(result, dict) and result.get("ok"))

def _matter_list_values(result: dict[str, Any]) -> list[tuple[int, str]]:
    values: list[tuple[int, str]] = []

    for match in _MATTER_LIST_VALUE_RE.finditer(_chip_stdout(result)):
        try:
            item_id = int(match.group(1))
        except Exception:
            continue

        values.append((item_id, str(match.group(2) or "").strip()))

    return values

def _matter_endpoint_ids_from_parts(result: dict[str, Any]) -> list[str]:
    endpoints: list[str] = []

    for item_id, _label in _matter_list_values(result):
        endpoint = str(item_id)

        if endpoint != "0" and endpoint not in endpoints:
            endpoints.append(endpoint)

    return endpoints

def _matter_server_cluster_ids(result: dict[str, Any]) -> set[int]:
    return {cluster_id for cluster_id, _label in _matter_list_values(result)}

def _matter_has_cluster(result: dict[str, Any], cluster_id: int, cluster_name: str = "") -> bool:
    if cluster_id in _matter_server_cluster_ids(result):
        return True

    if cluster_name:
        return cluster_name.lower() in _chip_stdout(result).lower()

    return False

def _matter_clean_attr_text(value: Any) -> str:
    text = str(value or "").strip().strip(",")

    if text.startswith('"') and text.endswith('"'):
        text = text[1:-1]

    return text.strip()

def _matter_attr_value(result: dict[str, Any], *names: str) -> str:
    wanted = {
        str(name or "").strip().lower().replace("_", "").replace("-", "").replace(" ", "")
        for name in names
        if str(name or "").strip()
    }

    if not wanted:
        return ""

    for raw_line in _chip_stdout(result).splitlines():
        line = _strip_ansi(raw_line)
        match = _MATTER_ATTR_VALUE_RE.match(line)

        if match:
            key = match.group(1).strip().lower().replace("_", "").replace("-", "").replace(" ", "")

            if key in wanted:
                return _matter_clean_attr_text(match.group(2))

        for name in names:
            clean_name = str(name or "").strip()

            if not clean_name:
                continue

            match = re.search(rf"\b{re.escape(clean_name)}\b\s*[:=]\s*(.+?)\s*$", line, re.I)

            if match:
                return _matter_clean_attr_text(match.group(1))

    return ""

def _matter_data_value(result: dict[str, Any]) -> str:
    for line in _chip_stdout(result).splitlines():
        match = re.search(r"\bData\s*=\s*(.+?)\s*$", _strip_ansi(line), re.I)

        if match:
            return _matter_clean_attr_text(match.group(1))

    return ""

def _matter_attr_or_data_value(result: dict[str, Any], *names: str) -> str:
    return _matter_attr_value(result, *names) or _matter_data_value(result)

def _matter_bool_value(value: Any):
    clean = str(value if value is not None else "").strip().lower()

    if clean in ("true", "1", "yes", "on", "enabled"):
        return True

    if clean in ("false", "0", "no", "off", "disabled"):
        return False

    return None

def _matter_bool_result_value(result: dict[str, Any], *names: str):
    return _matter_bool_value(_matter_attr_or_data_value(result, *names))

def _matter_int_value(value: Any):
    text = str(value if value is not None else "").strip()

    if not text:
        return None

    try:
        return int(text)
    except Exception:
        match = re.search(r"-?\d+", text)

        if not match:
            return None

        try:
            return int(match.group(0))
        except Exception:
            return None

def _matter_int_result_value(result: dict[str, Any], *names: str):
    return _matter_int_value(_matter_attr_or_data_value(result, *names))

def _matter_debug_text(value: Any) -> str:
    text = _to_text(value)

    if len(text) <= _MATTER_DEBUG_TEXT_LIMIT:
        return text

    return text[-_MATTER_DEBUG_TEXT_LIMIT:]

def _matter_read_debug(read: dict[str, Any], *, parsed_value: Any = None, parsed_ok: bool | None = None) -> dict[str, Any]:
    debug = {
        "ok": read.get("ok"),
        "returncode": read.get("returncode"),
        "command": read.get("command"),
        "stdout": _matter_debug_text(read.get("stdout", "")),
        "stderr": _matter_debug_text(read.get("stderr", "")),
        "started_at": read.get("started_at"),
        "finished_at": read.get("finished_at"),
    }

    if parsed_ok is not None:
        debug["parsed"] = parsed_ok

    if parsed_value is not None:
        debug["value"] = parsed_value

    return debug

def _matter_battery_low_value(charge_level: Any = None, replacement_needed: Any = None):
    replacement_bool = _matter_bool_value(replacement_needed)

    if replacement_bool is not None:
        return replacement_bool

    charge_number = _matter_int_value(charge_level)

    if charge_number is not None:
        return charge_number > 0

    charge_text = str(charge_level or "").strip().lower()

    if charge_text in ("warning", "critical", "low", "replace", "replacement_needed", "replacement-needed"):
        return True

    if charge_text in ("ok", "okay", "normal", "good", "nominal", "healthy"):
        return False

    return None

def _matter_apply_battery_status(attrs: dict[str, Any]) -> None:
    battery_low = _matter_battery_low_value(
        attrs.get("matter_battery_charge_level"),
        attrs.get("matter_battery_replacement_needed"),
    )

    if battery_low is None:
        return

    attrs["matter_battery_low"] = battery_low
    attrs["battery_low"] = battery_low
    attrs["battery_state"] = "low" if battery_low else "ok"

def _matter_endpoint_kinds(server_list: dict[str, Any]) -> list[str]:
    kinds: list[str] = []

    if _matter_has_cluster(server_list, 1026, "TemperatureMeasurement"):
        kinds.append("temperature")

    if _matter_has_cluster(server_list, 1029, "RelativeHumidityMeasurement"):
        kinds.append("humidity")

    if _matter_has_cluster(server_list, 69, "BooleanState"):
        kinds.append("contact")

    if _matter_has_cluster(server_list, 1030, "OccupancySensing"):
        kinds.append("motion")

    if _matter_has_cluster(server_list, 6, "OnOff"):
        kinds.append("switch")

    if _matter_has_cluster(server_list, 59, "Switch"):
        kinds.append("button")

    if _matter_has_cluster(server_list, 47, "PowerSource"):
        kinds.append("battery")

    return kinds

def _to_text(value: Any) -> str:
    if value is None:
        return ""

    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")

    return str(value)

def _redact_command(command: list[str]) -> list[str]:
    redacted = list(command)

    for index, part in enumerate(redacted):
        if part == "code" and index > 0 and redacted[index - 1] == "pairing":
            setup_code_index = index + 2

            if setup_code_index < len(redacted):
                redacted[setup_code_index] = "[REDACTED_SETUP_CODE]"

    return redacted

def _parse_measured_value(stdout: str) -> int | None:
    text = _strip_ansi(stdout)
    match = re.search(r"\bMeasuredValue:\s*(-?\d+)\b", text or "")

    if not match:
        return None

    return int(match.group(1))

def _parse_state_value(stdout: str) -> bool | None:
    text = _strip_ansi(stdout)
    match = re.search(r"\bStateValue:\s*(TRUE|FALSE)\b", text or "", re.IGNORECASE)

    return match.group(1).upper() == "TRUE" if match else None

def _parse_occupancy_value(stdout: str) -> int | None:
    text = _strip_ansi(stdout)
    match = re.search(r"\bOccupancy:\s*(\d+)\b", text or "", re.IGNORECASE)

    return int(match.group(1)) if match else None

def _parse_report_endpoint(stdout: str) -> str:
    text = _strip_ansi(stdout)
    match = re.search(r"\bEndpoint:\s*(0x[0-9A-Fa-f]+|\d+)\b", text or "")

    if not match:
        return ""

    try:
        return str(int(match.group(1), 0))
    except ValueError:
        return ""

def _parse_report_cluster(stdout: str) -> int | None:
    text = _strip_ansi(stdout)
    match = re.search(r"\bCluster:\s*(0x[0-9A-Fa-f_]+|\d+)\b", text or "")

    if not match:
        return None

    try:
        return int(match.group(1).replace("_", ""), 0)
    except ValueError:
        return None

def _parse_matter_string_value(stdout: str, label: str) -> str | None:
    text = _strip_ansi(stdout)
    match = re.search(rf"\b{re.escape(label)}:\s*(.*?)\s*$", text, re.MULTILINE)

    if match:
        return match.group(1).strip()

    match = re.search(r'\bData\s*=\s*"([^"]*)"', text)

    if match:
        return match.group(1)

    return None

def _parse_matter_bool_value(stdout: str, label: str) -> bool | None:
    text = _strip_ansi(stdout)
    match = re.search(rf"\b{re.escape(label)}:\s*(TRUE|FALSE)\b", text, re.IGNORECASE)

    if match:
        return match.group(1).upper() == "TRUE"

    match = re.search(r"\bData\s*=\s*(true|false)\b", text, re.IGNORECASE)

    if match:
        return match.group(1).lower() == "true"

    return None

class MatterRuntime:
    def __init__(
        self,
        matter_dir: Path,
        *,
        now_epoch,
    ):
        self.matter_dir = Path(matter_dir)
        self.state_file = self.matter_dir / "matter_state.json"
        self.now_epoch = now_epoch
        self._subscription_lock = Lock()
        self._subscription_processes = set()

    def chip_tool_path(self) -> str:
        configured = str(os.environ.get("KOTIBOT_MATTER_CHIP_TOOL", "")).strip()

        if configured:
            return configured

        found = shutil.which("chip-tool")

        if found:
            return found

        return "chip-tool"

    def chip_tool_storage_dir(self) -> Path:
        storage_dir = self.matter_dir / "chip_tool_storage"
        storage_dir.mkdir(parents=True, exist_ok=True)
        return storage_dir

    def chip_tool_subscription_storage_dir(self, subscription_id: str) -> Path:
        storage_root = self.matter_dir / "chip_tool_subscription_storage"
        storage_root.mkdir(parents=True, exist_ok=True)
        clean_id = re.sub(r"[^A-Za-z0-9_.-]+", "_", subscription_id).strip("_") or "default"
        storage_dir = storage_root / clean_id

        if not storage_dir.exists():
            shutil.copytree(self.chip_tool_storage_dir(), storage_dir)

        return storage_dir

    def stop_subscription(self) -> bool:
        with self._subscription_lock:
            processes = [proc for proc in self._subscription_processes if proc.poll() is None]

        if not processes:
            return False

        for proc in processes:
            proc.terminate()

        for proc in processes:
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=3)

        return True

    def bypass_attestation(self) -> bool:
        raw = str(os.environ.get("KOTIBOT_MATTER_BYPASS_ATTESTATION", "1")).strip().lower()
        return raw not in ("0", "false", "no", "off")

    def default_state(self) -> dict[str, Any]:
        return {
            "enabled": True,
            "chip_tool": self.chip_tool_path(),
            "chip_tool_storage": str(self.chip_tool_storage_dir()),
            "bypass_attestation": self.bypass_attestation(),
            "nodes": {},
            "last_command": {},
            "settings": {
                "temperature_unit": "c",
            },
        }

    def read_state(self) -> dict[str, Any]:
        state = self.default_state()
        loaded = _load_json_object(self.state_file)

        if isinstance(loaded.get("nodes"), dict):
            state["nodes"] = loaded["nodes"]

        if isinstance(loaded.get("last_command"), dict):
            state["last_command"] = loaded["last_command"]

        default_settings = state.get("settings") if isinstance(state.get("settings"), dict) else {}
        loaded_settings = loaded.get("settings") if isinstance(loaded.get("settings"), dict) else {}

        settings = dict(default_settings)
        settings.update(loaded_settings)
        settings["temperature_unit"] = _clean_temperature_unit(
            loaded_settings.get("temperature_unit", loaded.get("temperature_unit", settings.get("temperature_unit")))
        )
        state["settings"] = settings

        if "enabled" in loaded:
            state["enabled"] = bool(loaded.get("enabled"))

        configured_chip_tool = str(os.environ.get("KOTIBOT_MATTER_CHIP_TOOL", "")).strip()

        if configured_chip_tool:
            state["chip_tool"] = configured_chip_tool
        elif isinstance(loaded.get("chip_tool"), str) and loaded.get("chip_tool").strip():
            state["chip_tool"] = loaded["chip_tool"].strip()

        return state

    def write_state(self, state: dict[str, Any]) -> None:
        _write_json_object(self.state_file, state)

    def _run_chip_tool(
        self,
        args: list[str],
        *,
        timeout: float = 20.0,
        storage_dir: Path | None = None,
    ) -> dict[str, Any]:
        state = self.read_state()
        chip_tool = str(state.get("chip_tool") or self.chip_tool_path()).strip() or "chip-tool"
        selected_storage_dir = Path(storage_dir) if storage_dir is not None else self.chip_tool_storage_dir()
        selected_storage_dir.mkdir(parents=True, exist_ok=True)

        command = [
            chip_tool,
            *args,
            "--storage-directory",
            str(selected_storage_dir),
        ]

        started_at = self.now_epoch()

        try:
            proc = subprocess.run(
                command,
                cwd=str(self.matter_dir),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=timeout,
                check=False,
            )

            result = {
                "ok": proc.returncode == 0,
                "returncode": proc.returncode,
                "command": _redact_command(command),
                "stdout": proc.stdout,
                "stderr": proc.stderr,
                "started_at": started_at,
                "finished_at": self.now_epoch(),
            }

        except subprocess.TimeoutExpired as e:
            result = {
                "ok": False,
                "returncode": None,
                "command": _redact_command(command),
                "stdout": _to_text(e.stdout),
                "stderr": _to_text(e.stderr) or "chip-tool timed out",
                "started_at": started_at,
                "finished_at": self.now_epoch(),
            }

        state["last_command"] = result
        self.write_state(state)

        return result

    def status(self) -> dict[str, Any]:
        state = self.read_state()
        chip_tool = str(state.get("chip_tool") or "").strip()

        if "/" in chip_tool:
            chip_tool_found = os.path.isfile(chip_tool) and os.access(chip_tool, os.X_OK)
        else:
            chip_tool_found = bool(shutil.which(chip_tool))

        return {
            "ok": True,
            "enabled": bool(state.get("enabled")),
            "chip_tool": chip_tool,
            "chip_tool_found": chip_tool_found,
            "chip_tool_storage": str(self.chip_tool_storage_dir()),
            "bypass_attestation": self.bypass_attestation(),
            "nodes": state.get("nodes", {}),
            "last_command": state.get("last_command", {}),
            "settings": state.get("settings") if isinstance(state.get("settings"), dict) else {},
        }

    def save_settings(self, payload: dict[str, Any]) -> dict[str, Any]:
        state = self.read_state()
        settings = state.get("settings") if isinstance(state.get("settings"), dict) else {}

        settings["temperature_unit"] = _clean_temperature_unit(
            payload.get("temperature_unit", payload.get("temperatureUnit", settings.get("temperature_unit")))
        )

        state["settings"] = settings
        self.write_state(state)

        return {
            "ok": True,
            "settings": settings,
        }

    def save_node(self, payload: dict[str, Any]) -> dict[str, Any]:
        node_id = _clean_node_id(payload.get("node_id") or payload.get("nodeID"))

        state = self.read_state()
        nodes = state.setdefault("nodes", {})

        existing = nodes.get(node_id)
        node = dict(existing) if isinstance(existing, dict) else {}

        node["node_id"] = node_id
        node["alias"] = str(payload.get("alias", node.get("alias", "")) or "").strip()
        node["manufacturer"] = str(payload.get("manufacturer", node.get("manufacturer", "")) or "").strip()
        node["model"] = str(payload.get("model", node.get("model", "")) or "").strip()
        node["source"] = str(payload.get("source", node.get("source", "matter")) or "matter").strip()
        node["notes"] = str(payload.get("notes", node.get("notes", "")) or "").strip()
        node["updated_at"] = self.now_epoch()

        endpoints = payload.get("endpoints")

        if isinstance(endpoints, list):
            node["endpoints"] = endpoints

        nodes[node_id] = node
        self.write_state(state)

        return {
            "ok": True,
            "node": node,
        }

    def remove_node(self, payload: dict[str, Any]) -> dict[str, Any]:
        node_id = _clean_node_id(payload.get("node_id") or payload.get("nodeID"))

        state = self.read_state()
        state.setdefault("nodes", {}).pop(node_id, None)
        self.write_state(state)

        return {"ok": True}

    def matter_node_ids(self, payload: dict[str, Any] | None = None) -> list[str]:
        payload = payload or {}
        raw_nodes = payload.get("node_ids", payload.get("nodeIDs"))

        if raw_nodes is None:
            single_node = payload.get("node_id") or payload.get("nodeID")

            if single_node:
                raw_nodes = [single_node]

        if isinstance(raw_nodes, str):
            raw_nodes = [part.strip() for part in raw_nodes.replace(";", ",").split(",")]

        node_ids = []

        if isinstance(raw_nodes, list):
            for raw_node in raw_nodes:
                try:
                    node_id = _clean_node_id(raw_node)
                except ValueError:
                    continue

                if node_id not in node_ids:
                    node_ids.append(node_id)

            return node_ids

        state = self.read_state()
        nodes = state.get("nodes") if isinstance(state.get("nodes"), dict) else {}

        for raw_node_id in nodes:
            try:
                node_id = _clean_node_id(raw_node_id)
            except ValueError:
                continue

            if node_id not in node_ids:
                node_ids.append(node_id)

        return node_ids

    def commission_code(self, payload: dict[str, Any]) -> dict[str, Any]:
        node_id = _clean_node_id(payload.get("node_id") or payload.get("nodeID"))
        setup_code = _clean_token(payload.get("setup_code") or payload.get("setupCode"), field_name="setup_code")

        args = ["pairing", "code", node_id, setup_code]

        if self.bypass_attestation():
            args.extend(["--bypass-attestation-verifier", "true"])

        return self._run_chip_tool(args, timeout=120.0)

    def recommission_node(self, payload: dict[str, Any]) -> dict[str, Any]:
        node_id = _clean_node_id(payload.get("node_id") or payload.get("nodeID"))
        setup_code = _clean_token(payload.get("setup_code") or payload.get("setupCode"), field_name="setup_code")
        storage_dir = self.chip_tool_storage_dir()
        stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(self.now_epoch()))
        backup_dir = self.matter_dir / f"chip_tool_storage.bad-{stamp}"
        repair_dir = self.matter_dir / f".chip_tool_storage.repair-{time.time_ns()}"

        suffix = 1

        while backup_dir.exists():
            backup_dir = self.matter_dir / f"chip_tool_storage.bad-{stamp}-{suffix}"
            suffix += 1

        self.stop_subscription()
        shutil.rmtree(repair_dir, ignore_errors=True)
        storage_dir.rename(backup_dir)
        repair_dir.mkdir(parents=True, exist_ok=True)

        args = ["pairing", "code", node_id, setup_code]

        if self.bypass_attestation():
            args.extend(["--bypass-attestation-verifier", "true"])

        try:
            result = self._run_chip_tool(
                args,
                timeout=120.0,
                storage_dir=repair_dir,
            )
        except Exception:
            shutil.rmtree(repair_dir, ignore_errors=True)

            if not storage_dir.exists() and backup_dir.exists():
                backup_dir.rename(storage_dir)

            raise

        if not result.get("ok"):
            shutil.rmtree(repair_dir, ignore_errors=True)
            backup_dir.rename(storage_dir)

            return {
                "ok": False,
                "error": "Matter commissioning failed; previous controller storage was restored.",
                "returncode": result.get("returncode"),
                "rolled_back": True,
            }

        repair_dir.rename(storage_dir)
        shutil.rmtree(
            self.matter_dir / "chip_tool_subscription_storage",
            ignore_errors=True,
        )

        state = self.read_state()
        node = state.setdefault("nodes", {}).setdefault(node_id, {})
        node["node_id"] = node_id
        node["recommissioned_at"] = self.now_epoch()
        self.write_state(state)

        return {
            "ok": True,
            "node_id": node_id,
            "backup": backup_dir.name,
            "returncode": result.get("returncode"),
        }

    def inspect_node(self, payload: dict[str, Any]) -> dict[str, Any]:
        node_id = _clean_node_id(payload.get("node_id") or payload.get("nodeID"))

        parts_list = self._run_chip_tool(["descriptor", "read", "parts-list", node_id, "0"])

        results = {
            "parts_list": parts_list,
            "endpoints": {},
        }

        endpoints = payload.get("endpoints")

        if not isinstance(endpoints, list) or not endpoints:
            endpoints = _matter_endpoint_ids_from_parts(parts_list)

        endpoint_summaries: list[dict[str, Any]] = []

        for endpoint in endpoints:
            clean_endpoint = _clean_endpoint(endpoint)
            device_type_list = self._run_chip_tool(
                ["descriptor", "read", "device-type-list", node_id, clean_endpoint]
            )
            server_list = self._run_chip_tool(
                ["descriptor", "read", "server-list", node_id, clean_endpoint]
            )
            kinds = _matter_endpoint_kinds(server_list)
            values: dict[str, Any] = {}

            if "switch" in kinds:
                onoff_result = self._run_chip_tool(
                    ["onoff", "read", "on-off", node_id, clean_endpoint],
                    timeout=8.0,
                )
                onoff_value = _matter_bool_result_value(onoff_result, "OnOff", "On Off", "on-off", "on_off")

                values["onoff"] = onoff_result
                values["matter_onoff"] = onoff_value

            if "button" in kinds:
                number_of_positions = self._run_chip_tool(
                    ["switch", "read", "number-of-positions", node_id, clean_endpoint],
                    timeout=8.0,
                )
                current_position = self._run_chip_tool(
                    ["switch", "read", "current-position", node_id, clean_endpoint],
                    timeout=8.0,
                )
                multi_press_max = self._run_chip_tool(
                    ["switch", "read", "multi-press-max", node_id, clean_endpoint],
                    timeout=8.0,
                )

                values["number_of_positions"] = number_of_positions
                values["current_position"] = current_position
                values["multi_press_max"] = multi_press_max
                values["matter_switch_positions"] = _matter_int_result_value(number_of_positions, "NumberOfPositions", "Number Of Positions", "number-of-positions")
                values["matter_switch_position"] = _matter_int_result_value(current_position, "CurrentPosition", "Current Position", "current-position")
                values["matter_switch_multipress_max"] = _matter_int_result_value(multi_press_max, "MultiPressMax", "Multi Press Max", "multi-press-max")

            results["endpoints"][clean_endpoint] = {
                "device_type_list": device_type_list,
                "server_list": server_list,
                "matter_kinds": kinds,
                "values": values,
            }

            endpoint_summaries.append({
                "endpoint": clean_endpoint,
                "matter_kind": kinds[0] if len(kinds) == 1 else ("multi" if kinds else "matter"),
                "matter_kinds": kinds,
                "matter_onoff": values.get("matter_onoff"),
                "matter_switch_position": values.get("matter_switch_position"),
                "matter_switch_positions": values.get("matter_switch_positions"),
                "matter_switch_multipress_max": values.get("matter_switch_multipress_max"),
            })

        state = self.read_state()
        node = state.setdefault("nodes", {}).setdefault(node_id, {"node_id": node_id})
        node["endpoints"] = endpoint_summaries
        node["last_inspection"] = results
        node["last_inspection_at"] = self.now_epoch()
        self.write_state(state)

        return {
            "ok": True,
            "node_id": node_id,
            "endpoints": endpoint_summaries,
            "inspection": results,
        }

    def read_attribute(self, payload: dict[str, Any]) -> dict[str, Any]:
        node_id = _clean_node_id(payload.get("node_id") or payload.get("nodeID"))
        endpoint = _clean_endpoint(payload.get("endpoint"))
        cluster = _clean_cluster(payload.get("cluster"))
        attribute = _clean_attribute(payload.get("attribute"))

        return self._run_chip_tool([cluster, "read", attribute, node_id, endpoint])

    def matter_discovery_ttl_seconds(self) -> float:
        raw = str(os.environ.get("KOTIBOT_MATTER_DISCOVERY_TTL_SECONDS", "300")).strip()

        try:
            return max(0.0, float(raw))
        except Exception:
            return 300.0

    def _matter_payload_children(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        children_by_endpoint: dict[str, dict[str, Any]] = {}
        endpoints_payload = payload.get("endpoints") if isinstance(payload.get("endpoints"), dict) else {}

        for kind in _MATTER_CAPABILITY_DEFINITIONS:
            endpoint_value = (
                payload.get(f"{kind}_endpoint")
                or payload.get(f"{kind}Endpoint")
                or endpoints_payload.get(kind)
            )

            if endpoint_value in (None, ""):
                continue

            endpoint = _clean_endpoint(endpoint_value)
            child = children_by_endpoint.setdefault(endpoint, {
                "endpoint": endpoint,
                "kinds": [],
                "clusters": [],
                "source": "payload",
            })

            if kind not in child["kinds"]:
                child["kinds"].append(kind)
                child["clusters"].append({
                    "value": _MATTER_CAPABILITY_DEFINITIONS[kind]["cluster_id"],
                    "name": _MATTER_CAPABILITY_DEFINITIONS[kind]["cluster_name"],
                })

        return list(children_by_endpoint.values())

    def _normalize_matter_children(self, children: Any) -> list[dict[str, Any]]:
        normalized = []

        if not isinstance(children, list):
            return normalized

        for child in children:
            if not isinstance(child, dict):
                continue

            try:
                endpoint = _clean_endpoint(child.get("endpoint"))
            except ValueError:
                continue

            raw_kinds = child.get("kinds")

            if isinstance(raw_kinds, str):
                raw_kinds = [raw_kinds]

            if not isinstance(raw_kinds, list):
                raw_kinds = [child.get("kind")]

            kinds = []

            for kind in raw_kinds:
                clean_kind = str(kind or "").strip().lower()

                if clean_kind in _MATTER_CAPABILITY_DEFINITIONS and clean_kind not in kinds:
                    kinds.append(clean_kind)

            cluster_entries = child.get("clusters") if isinstance(child.get("clusters"), list) else []

            for kind, definition in _MATTER_CAPABILITY_DEFINITIONS.items():
                if kind not in kinds and any(_cluster_entry_matches(entry, definition) for entry in cluster_entries if isinstance(entry, dict)):
                    kinds.append(kind)

            if not kinds:
                kinds = ["matter"]

            normalized_child = dict(child)
            normalized_child["endpoint"] = endpoint
            normalized_child["kinds"] = sorted(kinds, key=_matter_kind_sort_key)
            normalized.append(normalized_child)

        return normalized

    def _cached_matter_children(self, node_id: str, *, max_age_seconds: float | None) -> list[dict[str, Any]]:
        state = self.read_state()
        node = state.get("nodes", {}).get(node_id)

        if not isinstance(node, dict):
            return []

        children = self._normalize_matter_children(node.get("matter_children"))

        if not children:
            return []

        if max_age_seconds is not None:
            try:
                discovered_at = float(node.get("matter_discovered_at") or 0)
            except Exception:
                discovered_at = 0.0

            if max_age_seconds <= 0 or self.now_epoch() - discovered_at > max_age_seconds:
                return []

        return children

    def _read_matter_bridged_basic_info(self, node_id: str, endpoint: str) -> dict[str, Any]:
        values = {}
        reads = {}

        for field, definition in _MATTER_BRIDGED_BASIC_ATTRIBUTES.items():
            read = self._run_chip_tool([
                "bridgeddevicebasicinformation",
                "read",
                definition["attribute"],
                node_id,
                endpoint,
            ], timeout=5.0)

            if definition.get("kind") == "bool":
                parsed_value = _parse_matter_bool_value(read.get("stdout", ""), definition["label"])
            else:
                parsed_value = _parse_matter_string_value(read.get("stdout", ""), definition["label"])

            parsed_ok = parsed_value is not None

            if parsed_ok:
                values[field] = parsed_value

            reads[field] = _matter_read_debug(read, parsed_value=parsed_value, parsed_ok=parsed_ok)

        return {
            "values": values,
            "reads": reads,
        }

    def discover_endpoints(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = payload or {}
        node_id = _clean_node_id(payload.get("node_id") or payload.get("nodeID"))
        payload_children = self._matter_payload_children(payload)

        if payload_children:
            return {
                "ok": True,
                "node_id": node_id,
                "source": "payload",
                "children": payload_children,
                "updated_at": self.now_epoch(),
            }

        force_discovery = str(
            payload.get("force_discovery", payload.get("forceDiscovery", ""))
        ).strip().lower() in ("1", "true", "yes", "on")

        automatic = str(payload.get("auto") or "").strip().lower() in (
            "1",
            "true",
            "yes",
            "on",
        )
        cached_children = [] if force_discovery else self._cached_matter_children(
            node_id,
            max_age_seconds=None if automatic else self.matter_discovery_ttl_seconds(),
        )

        if cached_children:
            return {
                "ok": True,
                "node_id": node_id,
                "source": "cache",
                "children": cached_children,
                "updated_at": self.now_epoch(),
            }

        stale_children = self._cached_matter_children(node_id, max_age_seconds=None)
        stale_children_by_endpoint = {
            str(child.get("endpoint") or "").strip(): child
            for child in stale_children
            if isinstance(child, dict) and child.get("endpoint")
        }
        endpoints_to_scan = ["0"]
        scanned_parts_endpoints = set()
        part_endpoints = []
        parts_reads = {}
        endpoint_details = {}
        children = []

        while endpoints_to_scan:
            parent_endpoint = endpoints_to_scan.pop(0)

            if parent_endpoint in scanned_parts_endpoints:
                continue

            scanned_parts_endpoints.add(parent_endpoint)
            parts_read = self._run_chip_tool([
                "descriptor",
                "read",
                "parts-list",
                node_id,
                parent_endpoint,
            ], timeout=5.0)
            parts_reads[parent_endpoint] = _matter_read_debug(parts_read)

            if not parts_read.get("ok"):
                continue

            part_entries = _parse_descriptor_entries(parts_read.get("stdout", ""), "PartsList")

            for entry in part_entries:
                endpoint = str(entry.get("value") or "").strip()

                if not endpoint or endpoint == "0":
                    continue

                if endpoint not in part_endpoints:
                    part_endpoints.append(endpoint)

                if endpoint not in scanned_parts_endpoints and endpoint not in endpoints_to_scan:
                    endpoints_to_scan.append(endpoint)

        for endpoint in part_endpoints:
            server_read = self._run_chip_tool([
                "descriptor",
                "read",
                "server-list",
                node_id,
                endpoint,
            ], timeout=5.0)
            cluster_entries = _parse_descriptor_entries(server_read.get("stdout", ""), "ServerList")
            kinds = []

            for kind, definition in _MATTER_CAPABILITY_DEFINITIONS.items():
                if any(_cluster_entry_matches(entry, definition) for entry in cluster_entries):
                    kinds.append(kind)

            bridged_basic = {}
            bridged_basic_reads = {}
            stale_child = stale_children_by_endpoint.get(endpoint)

            if (
                isinstance(stale_child, dict)
                and isinstance(stale_child.get("bridged_basic"), dict)
                and stale_child.get("bridged_basic")
            ):
                bridged_basic = dict(stale_child.get("bridged_basic") or {})
            elif _cluster_list_has(
                cluster_entries,
                _MATTER_BRIDGED_BASIC_CLUSTER_ID,
                _MATTER_BRIDGED_BASIC_CLUSTER_NAME,
            ):
                bridged_basic_result = self._read_matter_bridged_basic_info(node_id, endpoint)
                bridged_basic = bridged_basic_result.get("values", {})
                bridged_basic_reads = bridged_basic_result.get("reads", {})

            button_attrs = {}
            button_attr_reads = {}
            battery_attrs = {}
            battery_attr_reads = {}

            if "button" in kinds:
                button_attr_definitions = {
                    "matter_switch_positions": {
                        "attribute": "number-of-positions",
                        "labels": ("NumberOfPositions", "Number Of Positions", "number-of-positions"),
                    },
                    "matter_switch_multipress_max": {
                        "attribute": "multi-press-max",
                        "labels": ("MultiPressMax", "Multi Press Max", "multi-press-max"),
                    },
                }

                for field, attr_definition in button_attr_definitions.items():
                    read = self._run_chip_tool([
                        "switch",
                        "read",
                        attr_definition["attribute"],
                        node_id,
                        endpoint,
                    ], timeout=8.0)
                    parsed_value = _matter_int_result_value(read, *attr_definition["labels"])

                    if parsed_value is not None:
                        button_attrs[field] = parsed_value

                    button_attr_reads[field] = {
                        "ok": read.get("ok"),
                        "returncode": read.get("returncode"),
                        "parsed": parsed_value is not None,
                    }

            if "battery" in kinds:
                battery_attr_definitions = {
                    "matter_battery_charge_level": {
                        "attribute": "bat-charge-level",
                        "labels": ("BatChargeLevel", "Bat Charge Level", "bat-charge-level"),
                        "kind": "int",
                    },
                    "matter_battery_replacement_needed": {
                        "attribute": "bat-replacement-needed",
                        "labels": ("BatReplacementNeeded", "Bat Replacement Needed", "bat-replacement-needed"),
                        "kind": "bool",
                    },
                    "matter_battery_charge_state": {
                        "attribute": "bat-charge-state",
                        "labels": ("BatChargeState", "Bat Charge State", "bat-charge-state"),
                        "kind": "int",
                    },
                }

                for field, attr_definition in battery_attr_definitions.items():
                    read = self._run_chip_tool([
                        "powersource",
                        "read",
                        attr_definition["attribute"],
                        node_id,
                        endpoint,
                    ], timeout=8.0)

                    if attr_definition.get("kind") == "bool":
                        parsed_value = _matter_bool_result_value(read, *attr_definition["labels"])
                    else:
                        parsed_value = _matter_int_result_value(read, *attr_definition["labels"])

                    parsed_ok = parsed_value is not None

                    if parsed_ok:
                        battery_attrs[field] = parsed_value

                    battery_attr_reads[field] = _matter_read_debug(read, parsed_value=parsed_value, parsed_ok=parsed_ok)

                _matter_apply_battery_status(battery_attrs)

            endpoint_details[endpoint] = {
                "endpoint": endpoint,
                "kinds": sorted(kinds, key=_matter_kind_sort_key),
                "clusters": cluster_entries,
                "bridged_basic": bridged_basic,
                "bridged_basic_reads": bridged_basic_reads,
                "button_attr_reads": button_attr_reads,
                "battery_attr_reads": battery_attr_reads,
                **button_attrs,
                **battery_attrs,
                "server_list": _matter_read_debug(server_read),
            }

            if kinds or _cluster_list_has(
                cluster_entries,
                _MATTER_BRIDGED_BASIC_CLUSTER_ID,
                _MATTER_BRIDGED_BASIC_CLUSTER_NAME,
            ):
                children.append(endpoint_details[endpoint])

        discovered_at = self.now_epoch()
        normalized_children = self._normalize_matter_children(children)

        if normalized_children:
            state = self.read_state()
            node = state.setdefault("nodes", {}).setdefault(node_id, {"node_id": node_id})
            node["matter_children"] = normalized_children
            node["matter_discovered_at"] = discovered_at
            node["matter_discovery"] = {
                "ok": True,
                "source": "descriptor",
                "parts": part_endpoints,
                "parts_reads": parts_reads,
                "endpoints": endpoint_details,
                "updated_at": discovered_at,
            }
            self.write_state(state)

            return {
                "ok": True,
                "node_id": node_id,
                "source": "descriptor",
                "children": normalized_children,
                "parts": part_endpoints,
                "parts_reads": parts_reads,
                "updated_at": discovered_at,
            }

        if stale_children:
            return {
                "ok": True,
                "node_id": node_id,
                "source": "stale_cache",
                "children": stale_children,
                "parts": part_endpoints,
                "parts_reads": parts_reads,
                "updated_at": discovered_at,
            }

        return {
            "ok": False,
            "node_id": node_id,
            "source": "descriptor",
            "children": [],
            "parts": part_endpoints,
            "parts_reads": parts_reads,
            "updated_at": discovered_at,
        }
    
    def snapshot(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = payload or {}

        node_id = _clean_node_id(payload.get("node_id") or payload.get("nodeID"))
        discovery = self.discover_endpoints(payload)
        children = self._normalize_matter_children(discovery.get("children"))
        endpoints = {}
        snapshot_children = []
        first_temperature_raw = None
        first_temperature_c = None
        first_humidity_raw = None
        first_humidity_percent = None
        first_contact_state_value = None
        first_contact_open = None
        first_occupancy_state_value = None
        first_motion_active = None
        valid_read_count = 0
        attempted_read_count = 0

        for child in children:
            endpoint = child["endpoint"]
            bridged_basic = child.get("bridged_basic") if isinstance(child.get("bridged_basic"), dict) else {}
            child_snapshot = {
                "endpoint": endpoint,
                "kinds": child.get("kinds", []),
                "clusters": child.get("clusters", []),
                "bridged_basic": bridged_basic,
                "bridged_basic_reads": child.get("bridged_basic_reads", {}),
                "battery_attr_reads": dict(child.get("battery_attr_reads") or {}),
                "matter_vendor_name": bridged_basic.get("vendor_name"),
                "matter_product_name": bridged_basic.get("product_name"),
                "matter_node_label": bridged_basic.get("node_label"),
                "matter_hardware_version": bridged_basic.get("hardware_version_string"),
                "matter_software_version": bridged_basic.get("software_version_string"),
                "matter_serial_number": bridged_basic.get("serial_number"),
                "matter_reachable": bridged_basic.get("reachable"),
                "reads": {},
                "temperature_raw": None,
                "temperature_c": None,
                "humidity_raw": None,
                "humidity_percent": None,
                "contact_state_value": None,
                "contact_open": None,
                "occupancy_state_value": None,
                "motion_active": None,
                "matter_onoff": None,
                "matter_switch_position": None,
                "matter_switch_positions": child.get("matter_switch_positions"),
                "matter_switch_multipress_max": child.get("matter_switch_multipress_max"),
                "matter_button_position": None,
                "matter_battery_percent_remaining_raw": None,
                "matter_battery_percent": None,
                "matter_battery_charge_level": child.get("matter_battery_charge_level"),
                "matter_battery_charge_state": child.get("matter_battery_charge_state"),
                "matter_battery_replacement_needed": child.get("matter_battery_replacement_needed"),
                "matter_battery_low": child.get("matter_battery_low"),
                "battery_low": child.get("battery_low"),
                "battery_state": child.get("battery_state"),
            }
            read_kinds = list(child.get("kinds", []))

            for kind in read_kinds:
                definition = _MATTER_CAPABILITY_DEFINITIONS.get(kind)

                if not definition:
                    continue

                endpoints.setdefault(kind, endpoint)
                attempted_read_count += 1
                read = self._run_chip_tool([
                    definition["chip_cluster"],
                    "read",
                    definition["attribute"],
                    node_id,
                    endpoint,
                ], timeout=5.0)

                if kind in ("temperature", "humidity"):
                    raw_value = _parse_measured_value(read.get("stdout", ""))
                elif kind in ("contact", "switch"):
                    raw_value = _matter_bool_result_value(read, "StateValue", "State Value", "OnOff", "On Off", definition["attribute"])
                elif kind == "motion":
                    raw_value = _matter_int_result_value(read, "Occupancy", definition["attribute"])
                elif kind == "button":
                    raw_value = _matter_int_result_value(read, "CurrentPosition", "Current Position", "current-position")
                elif kind == "battery":
                    raw_value = _matter_int_result_value(read, "BatChargeLevel", "Bat Charge Level", "bat-charge-level")
                else:
                    raw_value = None

                parsed_ok = raw_value is not None
                read_ok = bool(read.get("ok") and parsed_ok)

                child_kinds = child.get("kinds", [])

                if read_ok and kind in child_kinds and (kind != "battery" or child_kinds == ["battery"]):
                    valid_read_count += 1

                child_snapshot["reads"][kind] = _matter_read_debug(read, parsed_value=raw_value, parsed_ok=parsed_ok)

                if kind == "temperature":
                    child_snapshot["temperature_raw"] = raw_value

                    if raw_value is not None:
                        child_snapshot["temperature_c"] = round(raw_value / 100.0, 2)

                    if first_temperature_raw is None and raw_value is not None:
                        first_temperature_raw = child_snapshot["temperature_raw"]
                        first_temperature_c = child_snapshot["temperature_c"]

                elif kind == "humidity":
                    child_snapshot["humidity_raw"] = raw_value

                    if raw_value is not None:
                        child_snapshot["humidity_percent"] = round(raw_value / 100.0, 2)

                    if first_humidity_raw is None and raw_value is not None:
                        first_humidity_raw = child_snapshot["humidity_raw"]
                        first_humidity_percent = child_snapshot["humidity_percent"]

                elif kind == "contact":
                    child_snapshot["contact_state_value"] = raw_value
                    # Matter Contact Sensor semantics are fixed by the device type:
                    # FALSE means open/no contact; TRUE means closed/contact.
                    # Keep the raw value separate from KotiBot's physical open state.
                    child_snapshot["contact_open"] = (
                        None if raw_value is None else not raw_value
                    )

                    if first_contact_state_value is None and raw_value is not None:
                        first_contact_state_value = child_snapshot["contact_state_value"]
                        first_contact_open = child_snapshot["contact_open"]

                elif kind == "motion":
                    child_snapshot["occupancy_state_value"] = raw_value
                    child_snapshot["motion_active"] = None if raw_value is None else bool(raw_value & 1)

                    if first_occupancy_state_value is None and raw_value is not None:
                        first_occupancy_state_value = child_snapshot["occupancy_state_value"]
                        first_motion_active = child_snapshot["motion_active"]

                elif kind == "switch":
                    child_snapshot["matter_onoff"] = raw_value

                elif kind == "button":
                    child_snapshot["matter_switch_position"] = raw_value
                    child_snapshot["matter_button_position"] = raw_value

                elif kind == "battery":
                    child_snapshot["matter_battery_charge_level"] = raw_value
                    child_snapshot["battery_attr_reads"]["matter_battery_charge_level"] = child_snapshot["reads"][kind]
                    _matter_apply_battery_status(child_snapshot)

            snapshot_children.append(child_snapshot)

        ok = bool(
            snapshot_children
            and (valid_read_count > 0 or discovery.get("ok"))
        )

        return {
            "ok": ok,
            "node_id": node_id,
            "endpoints": endpoints,
            "children": snapshot_children,
            "discovery": {
                "ok": discovery.get("ok"),
                "source": discovery.get("source"),
                "parts": discovery.get("parts", []),
                "updated_at": discovery.get("updated_at"),
            },
            "temperature_raw": first_temperature_raw,
            "temperature_c": first_temperature_c,
            "humidity_raw": first_humidity_raw,
            "humidity_percent": first_humidity_percent,
            "contact_state_value": first_contact_state_value,
            "contact_open": first_contact_open,
            "occupancy_state_value": first_occupancy_state_value,
            "motion_active": first_motion_active,
            "reads": {
                "attempted": attempted_read_count,
                "valid": valid_read_count,
            },
            "updated_at": self.now_epoch(),
        }

    def snapshot_all(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = payload or {}
        node_ids = self.matter_node_ids(payload)

        if not node_ids:
            return {
                "ok": False,
                "error": "no_matter_nodes_configured",
                "snapshots": [],
                "updated_at": self.now_epoch(),
            }

        snapshots = []

        for node_id in node_ids:
            node_payload = dict(payload)
            node_payload["node_id"] = node_id

            try:
                snapshots.append(self.snapshot(node_payload))
            except Exception as e:
                snapshots.append({
                    "ok": False,
                    "node_id": node_id,
                    "error": str(e),
                    "children": [],
                    "updated_at": self.now_epoch(),
                })

        return {
            "ok": any(snapshot.get("ok") for snapshot in snapshots if isinstance(snapshot, dict)),
            "snapshots": snapshots,
            "updated_at": self.now_epoch(),
        }

    def subscribe_sensor_states(self, payload: dict[str, Any], on_value, stop_event=None) -> dict[str, Any]:
        payload = payload or {}
        node_id = _clean_node_id(payload.get("node_id") or payload.get("nodeID"))

        try:
            min_interval = max(0, int(payload.get("min_interval", payload.get("minInterval", 0)) or 0))
        except Exception:
            min_interval = 0

        try:
            max_interval = max(1, int(payload.get("max_interval", payload.get("maxInterval", 60)) or 60))
        except Exception:
            max_interval = 60

        started_at = self.now_epoch()
        sensor_clusters = {
            "temperature": "0x402",
            "humidity": "0x405",
            "contact": "0x45",
            "motion": "0x406",
        }
        subscription_paths = []
        seen_paths = set()

        for child in self._cached_matter_children(node_id, max_age_seconds=None):
            endpoint = str(child.get("endpoint") or "").strip()
            kinds = child.get("kinds") if isinstance(child.get("kinds"), list) else []

            if not endpoint:
                continue

            for kind in kinds:
                cluster_id = sensor_clusters.get(str(kind or "").strip().lower())
                path = (cluster_id, "0x0", endpoint)

                if cluster_id and path not in seen_paths:
                    seen_paths.add(path)
                    subscription_paths.append(path)

        if not subscription_paths:
            return {
                "ok": False,
                "returncode": None,
                "command": [],
                "event_count": 0,
                "error": f"No cached Matter sensor endpoints found for node {node_id}",
                "started_at": started_at,
                "finished_at": self.now_epoch(),
            }

        state = self.read_state()
        chip_tool = str(state.get("chip_tool") or self.chip_tool_path()).strip() or "chip-tool"
        process_command = [
            chip_tool,
            "interactive",
            "start",
            "--storage-directory",
            str(self.chip_tool_subscription_storage_dir(f"sensors_{node_id}")),
        ]
        subscription_command = [
            "any",
            "subscribe-by-id",
            ",".join(path[0] for path in subscription_paths),
            ",".join(path[1] for path in subscription_paths),
            str(min_interval),
            str(max_interval),
            node_id,
            ",".join(path[2] for path in subscription_paths),
            "--keepSubscriptions",
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

        try:
            proc = subprocess.Popen(
                process_command,
                cwd=str(self.matter_dir),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )

            with self._subscription_lock:
                self._subscription_processes.add(proc)

            if proc.stdin is None:
                raise RuntimeError("Matter interactive subscription stdin unavailable")

            proc.stdin.write(" ".join(subscription_command) + "\n")
            proc.stdin.flush()

            if proc.stdout is not None:
                def read_output():
                    try:
                        for raw_line in proc.stdout:
                            output_queue.put(raw_line)
                    finally:
                        output_queue.put(None)

                Thread(target=read_output, daemon=True).start()

                while True:
                    if stop_event is not None and stop_event.is_set():
                        break

                    try:
                        raw_line = output_queue.get(timeout=1.0)
                    except Empty:
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

                    if next_endpoint:
                        reported_endpoint = next_endpoint

                    next_cluster = _parse_report_cluster(raw_line)

                    if next_cluster is not None:
                        reported_cluster = next_cluster

                    if reported_cluster in (1026, 1029):
                        raw_value = _parse_measured_value(raw_line)

                        if raw_value is None or not reported_endpoint:
                            continue

                        event = {
                            "kind": "temperature" if reported_cluster == 1026 else "humidity",
                            "node_id": node_id,
                            "endpoint": reported_endpoint,
                            "received_at": self.now_epoch(),
                        }

                        if reported_cluster == 1026:
                            event["temperature_raw"] = raw_value
                        else:
                            event["humidity_raw"] = raw_value
                    elif reported_cluster == 69:
                        raw_value = _parse_state_value(raw_line)

                        if raw_value is None or not reported_endpoint:
                            continue

                        event = {
                            "kind": "contact",
                            "node_id": node_id,
                            "endpoint": reported_endpoint,
                            "contact_state_value": raw_value,
                            "received_at": self.now_epoch(),
                        }
                    elif reported_cluster == 1030:
                        raw_value = _parse_occupancy_value(raw_line)

                        if raw_value is None or not reported_endpoint:
                            continue

                        event = {
                            "kind": "motion",
                            "node_id": node_id,
                            "endpoint": reported_endpoint,
                            "occupancy_state_value": raw_value,
                            "motion_active": bool(raw_value & 1),
                            "received_at": self.now_epoch(),
                        }
                    else:
                        continue

                    event_count += 1
                    last_event_at = self.now_epoch()
                    on_value(event)

            returncode = proc.wait(timeout=2) if proc.poll() is None else proc.returncode
            stopped = stop_event is not None and stop_event.is_set()

            return {
                "ok": stopped,
                "returncode": returncode,
                "command": _redact_command(process_command),
                "subscription_command": _redact_command(subscription_command),
                "event_count": event_count,
                "error": (
                    None
                    if stopped
                    else (
                        f"Matter sensor subscription inactive for {watchdog_seconds}s"
                        if watchdog_expired
                        else f"Matter sensor subscription exited rc={returncode} events={event_count}"
                    )
                ),
                "started_at": started_at,
                "finished_at": self.now_epoch(),
            }

        except Exception as e:
            return {
                "ok": False,
                "returncode": getattr(proc, "returncode", None),
                "command": _redact_command(process_command),
                "subscription_command": _redact_command(subscription_command),
                "event_count": event_count,
                "error": str(e),
                "started_at": started_at,
                "finished_at": self.now_epoch(),
            }

        finally:
            if proc is not None and proc.poll() is None:
                proc.terminate()

                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=3)

            with self._subscription_lock:
                self._subscription_processes.discard(proc)
                
    def onoff(self, payload: dict[str, Any], enabled: bool) -> dict[str, Any]:
        node_id = _clean_node_id(payload.get("node_id") or payload.get("nodeID"))
        endpoint = _clean_endpoint(payload.get("endpoint"))

        return self._run_chip_tool(["onoff", "on" if enabled else "off", node_id, endpoint])

    def level(self, payload: dict[str, Any]) -> dict[str, Any]:
        node_id = _clean_node_id(payload.get("node_id") or payload.get("nodeID"))
        endpoint = _clean_endpoint(payload.get("endpoint"))

        raw_level = payload.get("level", payload.get("current_level"))

        try:
            level = max(0, min(254, int(raw_level)))
        except Exception:
            raise ValueError("Invalid level")

        transition_time = payload.get("transition_time", payload.get("transitionTime", 0))

        try:
            transition_time = max(0, int(transition_time))
        except Exception:
            transition_time = 0

        return self._run_chip_tool([
            "levelcontrol",
            "move-to-level",
            str(level),
            str(transition_time),
            node_id,
            endpoint,
        ])

    def color_temperature(self, payload: dict[str, Any]) -> dict[str, Any]:
        node_id = _clean_node_id(payload.get("node_id") or payload.get("nodeID"))
        endpoint = _clean_endpoint(payload.get("endpoint"))

        raw_mireds = payload.get("mireds", payload.get("color_temperature_mireds"))

        try:
            mireds = max(1, int(raw_mireds))
        except Exception:
            raise ValueError("Invalid color temperature mireds")

        transition_time = payload.get("transition_time", payload.get("transitionTime", 0))

        try:
            transition_time = max(0, int(transition_time))
        except Exception:
            transition_time = 0

        return self._run_chip_tool([
            "colorcontrol",
            "move-to-color-temperature",
            str(mireds),
            str(transition_time),
            node_id,
            endpoint,
        ])

import asyncio
import base64
import inspect
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote
from datetime import datetime
from tapo import ApiClient

from .tapo_bulbs import bulb_control_methods, update_bulb_capabilities_from_device
from .tapo_extenders import (
    default_outlet_children,
    default_outlet_count,
    merge_outlet_extender_child_metadata,
    normalize_outlet_extender_children,
    outlet_extender_control_methods,
)
from .tapo_energy import enrich_tapo_energy_devices
from .tapo_plugs import plug_control_methods
from .tapo_types import classify_tapo_device

TAPO_USERNAME = os.environ.get("TAPO_USERNAME", "").strip()
TAPO_PASSWORD = os.environ.get("TAPO_PASSWORD", "").strip()
TAPO_CACHE_SECONDS = float(os.environ.get("TAPO_CACHE_SECONDS", "10") or 10)
TAPO_DEVICE_CONNECT_TIMEOUT_SECONDS = float(os.environ.get("TAPO_DEVICE_CONNECT_TIMEOUT_SECONDS", "1.25") or 1.25)
TAPO_DEVICE_CALL_TIMEOUT_SECONDS = float(os.environ.get("TAPO_DEVICE_CALL_TIMEOUT_SECONDS", "4") or 4)
TAPO_DEVICE_REFRESH_TIMEOUT_SECONDS = float(os.environ.get("TAPO_DEVICE_REFRESH_TIMEOUT_SECONDS", "6") or 6)

TAPO_CAMERA_STREAMS = {}
TAPO_CAMERA_RECORDINGS = {}
TAPO_CAMERA_STREAM_TTL_SECONDS = 45.0
TAPO_CAMERA_RUNTIME_ROOT = Path(__file__).resolve().parent / "runtime"
TAPO_CAMERA_HLS_ROOT = TAPO_CAMERA_RUNTIME_ROOT / "camera_hls"
TAPO_CAMERA_RECORDING_ROOT = Path(os.environ.get(
    "KOTIBOT_TAPO_RECORDING_DIR",
    str(Path(__file__).resolve().parents[2] / "subsystems" / "video" / "videos")
))

TAPO_CAMERA_HLS_ROOT.mkdir(
    parents=True,
    exist_ok=True,
    mode=0o700,
)
TAPO_CAMERA_RECORDING_ROOT.mkdir(
    parents=True,
    exist_ok=True,
    mode=0o700,
)

os.chmod(TAPO_CAMERA_HLS_ROOT, 0o700)
os.chmod(TAPO_CAMERA_RECORDING_ROOT, 0o700)

_tapo_devices: dict[str, dict[str, Any]] = {}
_tapo_handles: dict[str, Any] = {}
_tapo_last_scan = 0.0

# Native bulb fade durations, in seconds. Valid range: 0-60.
# Set either value to 0 to disable that transition.
TAPO_NATIVE_FADE_ON_SECONDS = 2
TAPO_NATIVE_FADE_OFF_SECONDS = 2

TAPO_NATIVE_FADE_COMMAND_TIMEOUT_SECONDS = 8.0

_tapo_native_fade_ready: dict[str, tuple[int, int]] = {}
_tapo_native_fade_errors: dict[str, str] = {}

_LOGGER = logging.getLogger(__name__)

def run_async(coro):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    raise RuntimeError("run_async cannot be used from inside an already-running event loop")

def _redact_command_for_log(cmd) -> list[str]:
    redacted = []
    redact_next = False

    for part in cmd or []:
        text = str(part)

        if redact_next:
            redacted.append("***")
            redact_next = False
            continue

        redacted.append(text)

        if text in {"--password", "--username"}:
            redact_next = True

    return redacted

def _command_timeout_message(cmd, timeout_seconds: float) -> str:
    return f"Command {_redact_command_for_log(cmd)!r} timed out after {timeout_seconds:g} seconds"

def _kasa_cli_environment():
    _require_credentials()
    environment = os.environ.copy()
    environment["KASA_USERNAME"] = TAPO_USERNAME
    environment["KASA_PASSWORD"] = TAPO_PASSWORD
    return environment

def _require_credentials():
    if not TAPO_USERNAME or not TAPO_PASSWORD:
        raise RuntimeError("Missing TAPO_USERNAME or TAPO_PASSWORD environment variables")

def _device_id(mac: str, ip: str) -> str:
    clean = re.sub(r"[^a-zA-Z0-9]+", "_", mac or "").strip("_").lower()
    return clean or ip.replace(".", "_")

def tapo_stream_key(deviceID):
    return "".join(
        ch for ch in str(deviceID or "")
        if ch.isalnum() or ch in ("-", "_", ".")
    ).strip("._")[:80] or "unknown"

def tapo_camera_rtsp_url(c):
    # The credential-bearing URL is constructed only when opening the camera.
    # It must never enter CLIENTS, JSON state, status payloads, or logs.
    ip = str(c.get("tapo_ip") or c.get("ip") or "").strip()
    user = os.environ.get("TAPO_CAMERA_USERNAME", "").strip()
    password = os.environ.get("TAPO_CAMERA_PASSWORD", "").strip()
    path = os.environ.get("TAPO_CAMERA_RTSP_PATH", "/stream1").strip() or "/stream1"

    if not path.startswith("/"):
        path = f"/{path}"

    if not ip:
        raise RuntimeError("Missing Tapo camera IP")

    if not user or not password:
        raise RuntimeError("Missing TAPO_CAMERA_USERNAME or TAPO_CAMERA_PASSWORD")

    return f"rtsp://{quote(user, safe='')}:{quote(password, safe='')}@{ip}:554{path}"


def ffmpeg_rtsp_input(rtsp_url):
    """
    Put the credential-bearing URL in an anonymous memory file.

    FFmpeg receives only /proc/self/fd/<n> in argv. The descriptor contains
    an ffconcat document that opens the RTSP source using TCP.
    """
    if not hasattr(os, "memfd_create"):
        raise RuntimeError(
            "Secure RTSP launch requires Linux memfd_create"
        )

    payload = (
        "ffconcat version 1.0\n"
        f"file '{rtsp_url}'\n"
        "option rtsp_transport tcp\n"
    ).encode("utf-8")

    fd = os.memfd_create(
        "kotibot-rtsp",
        flags=getattr(os, "MFD_CLOEXEC", 0),
    )

    try:
        remaining = memoryview(payload)

        while remaining:
            written = os.write(fd, remaining)

            if written <= 0:
                raise OSError(
                    "Could not write the FFmpeg RTSP descriptor"
                )

            remaining = remaining[written:]

        os.lseek(fd, 0, os.SEEK_SET)
        return fd, f"/proc/self/fd/{fd}"
    except Exception:
        os.close(fd)
        raise


def stop_tapo_camera_stream(deviceID):
    key = tapo_stream_key(deviceID)
    entry = TAPO_CAMERA_STREAMS.pop(key, None)

    if not entry:
        return

    proc = entry.get("proc")

    if proc and proc.poll() is None:
        proc.terminate()

        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()

def touch_tapo_camera_stream(stream_key):
    key = tapo_stream_key(stream_key)
    entry = TAPO_CAMERA_STREAMS.get(key)

    if entry:
        entry["last_viewer_at"] = time.time()

def clean_tapo_recording_label(value):
    raw = " ".join(str(value or "").replace("\r", " ").replace("\n", " ").split())
    safe = ''.join(ch for ch in raw if ch.isalnum() or ch in (' ', '-', '_', '.', '(', ')'))
    return " ".join(safe.split()).strip(' ._')[:80] or 'unknown'

def tapo_camera_recording_path(c):
    now = datetime.now()
    day_label = now.strftime("%Y-%m-%d")
    date_label = now.strftime("%Y-%m-%d %H-%M-%S")
    recording_dir = TAPO_CAMERA_RECORDING_ROOT / day_label
    recording_dir.mkdir(
        parents=True,
        exist_ok=True,
        mode=0o700,
    )
    os.chmod(recording_dir, 0o700)

    zone_name = clean_tapo_recording_label(c.get("zone_name") or "Unknown Zone")
    client_name = clean_tapo_recording_label(
        c.get("clientName")
        or c.get("tapo_alias")
        or c.get("tapo_model")
        or c.get("deviceID")
        or "Tapo Camera"
    )

    stem = clean_tapo_recording_label(f"{date_label} {zone_name} {client_name}")
    path = recording_dir / f"{stem}.mp4"

    if not path.exists():
        return path

    index = 1

    while True:
        path = recording_dir / f"{stem} {index:06d}.mp4"

        if not path.exists():
            return path

        index += 1

def start_tapo_camera_recording(c):
    deviceID = c.get("deviceID")
    key = tapo_stream_key(deviceID)
    entry = TAPO_CAMERA_RECORDINGS.get(key)

    if entry and entry.get("proc") and entry["proc"].poll() is None:
        return entry.get("path")

    ffmpeg = shutil.which("ffmpeg")

    if not ffmpeg:
        raise RuntimeError("ffmpeg not found")

    rtsp_url = tapo_camera_rtsp_url(c)
    rtsp_fd, rtsp_input = ffmpeg_rtsp_input(rtsp_url)
    path = tapo_camera_recording_path(c)

    # Reserve the output securely before FFmpeg opens it.
    path.touch(mode=0o600, exist_ok=False)

    cmd = [
        ffmpeg,
        "-hide_banner",
        "-loglevel", "error",
        "-y",
        "-f", "concat",
        "-safe", "0",
        "-protocol_whitelist",
        "file,crypto,http,https,tcp,tls,udp,rtp,rtsp",
        "-i", rtsp_input,
        "-map", "0:v:0",
        "-map", "0:a?",
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "64k",
        "-movflags", "+frag_keyframe+empty_moov",
        "-f", "mp4",
        str(path),
    ]

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            pass_fds=(rtsp_fd,),
        )
    except Exception:
        path.unlink(missing_ok=True)
        raise
    finally:
        os.close(rtsp_fd)

    time.sleep(.35)

    if proc.poll() is not None:
        error_text = ""

        try:
            error_text = proc.stderr.read().strip()
        except Exception:
            error_text = ""

        raise RuntimeError(error_text or "Tapo camera recording stopped immediately")

    TAPO_CAMERA_RECORDINGS[key] = {
        "proc": proc,
        "path": str(path),
        "started_at": time.time(),
    }

    return str(path)

def stop_tapo_camera_recording(deviceID):
    key = tapo_stream_key(deviceID)
    entry = TAPO_CAMERA_RECORDINGS.pop(key, None)

    if not entry:
        return ""

    proc = entry.get("proc")

    if proc and proc.poll() is None:
        proc.terminate()

        try:
            proc.wait(timeout=4)
        except subprocess.TimeoutExpired:
            proc.kill()

    return str(entry.get("path") or "")

def start_tapo_camera_stream(c):
    deviceID = c.get("deviceID")
    key = tapo_stream_key(deviceID)
    now = time.time()
    entry = TAPO_CAMERA_STREAMS.get(key)

    if entry and entry.get("proc") and entry["proc"].poll() is None:
        entry["last_viewer_at"] = now
        return f"/api/tapo/camera-hls/{key}/index.m3u8"

    ffmpeg = shutil.which("ffmpeg")

    if not ffmpeg:
        raise RuntimeError("ffmpeg not found")

    stream_dir = TAPO_CAMERA_HLS_ROOT / key

    if stream_dir.exists():
        shutil.rmtree(stream_dir, ignore_errors=True)

    stream_dir.mkdir(
        parents=True,
        exist_ok=True,
        mode=0o700,
    )
    os.chmod(stream_dir, 0o700)

    rtsp_url = tapo_camera_rtsp_url(c)
    rtsp_fd, rtsp_input = ffmpeg_rtsp_input(rtsp_url)
    playlist = stream_dir / "index.m3u8"
    segment_pattern = stream_dir / "seg_%05d.ts"

    cmd = [
        ffmpeg,
        "-hide_banner",
        "-loglevel", "error",
        "-f", "concat",
        "-safe", "0",
        "-protocol_whitelist",
        "file,crypto,http,https,tcp,tls,udp,rtp,rtsp",
        "-i", rtsp_input,
        "-an",
        "-c:v", "copy",
        "-f", "hls",
        "-hls_time", "1",
        "-hls_list_size", "4",
        "-hls_flags", "delete_segments+append_list+omit_endlist",
        "-hls_segment_filename", str(segment_pattern),
        str(playlist),
    ]

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            pass_fds=(rtsp_fd,),
        )
    finally:
        os.close(rtsp_fd)

    TAPO_CAMERA_STREAMS[key] = {
        "proc": proc,
        "dir": stream_dir,
        "last_viewer_at": now,
    }

    return f"/api/tapo/camera-hls/{key}/index.m3u8"

def prune_tapo_camera_streams():
    now = time.time()

    for key, entry in list(TAPO_CAMERA_STREAMS.items()):
        if now - float(entry.get("last_viewer_at", 0) or 0) <= TAPO_CAMERA_STREAM_TTL_SECONDS:
            continue

        proc = entry.get("proc")

        if proc and proc.poll() is None:
            proc.terminate()

            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()

        TAPO_CAMERA_STREAMS.pop(key, None)

def _classify_tapo_device(model: str, device_type: str) -> dict[str, Any]:
    return classify_tapo_device(model, device_type)

def _run_discovery_text() -> str:
    venv_kasa = Path(sys.executable).with_name("kasa")
    cmd = [str(venv_kasa), "discover"]

    try:
        completed = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=25,
            env=_kasa_cli_environment(),
        )
    except subprocess.TimeoutExpired as e:
        output = e.stdout or ""

        if isinstance(output, bytes):
            output = output.decode("utf-8", errors="replace")

        if "Device Type:" in output and "IP:" in output:
            return output

        raise RuntimeError(
            f"{' '.join(cmd)} timed out after 25 seconds: {str(output).strip()[:1000]}"
        )

    except Exception as e:
        raise RuntimeError(f"{' '.join(cmd)} failed: {e}")

    output = completed.stdout or ""

    if "Device Type:" in output and "IP:" in output:
        return output

    raise RuntimeError(
        f"{' '.join(cmd)} rc={completed.returncode}: {output.strip()[:1000]}"
    )

def debug_tapo_discovery_text() -> str:
    return _run_discovery_text()

def _parse_kasa_discovery(text: str) -> list[dict[str, Any]]:
    devices = []
    current = {}

    field_map = {
        "Device Type": "device_type",
        "Device Model": "model",
        "IP": "ip",
        "MAC": "mac",
        "Device Id (hash)": "device_id_hash",
        "Owner (hash)": "owner_hash",
        "Encrypt Type": "encrypt_type",
        "HTTP Port": "http_port",
        "Login version": "login_version",
        "Status": "status",
        "State": "state",
        "Battery": "battery",
        "Battery Level": "battery",
        "Battery Percent": "battery",
        "Battery Percentage": "battery",
    }

    for raw_line in text.splitlines():
        line = raw_line.strip()

        if line.startswith("== ") and current.get("ip"):
            devices.append(current)
            current = {}
            continue

        if ":" not in line:
            continue

        label, value = line.split(":", 1)
        label = label.strip()
        value = value.strip()

        key = field_map.get(label)
        if key:
            current[key] = value

    if current.get("ip"):
        devices.append(current)

    out = []

    for d in devices:
        device_type = str(d.get("device_type") or "").upper()
        model = str(d.get("model") or "")

        if "TAPO" not in device_type and not model:
            continue

        ip = d.get("ip", "")
        mac = d.get("mac", "")
        device_id = _device_id(mac, ip)

        profile = _classify_tapo_device(model, device_type)

        discovered_power = _coerce_tapo_power_state(d.get("state"))

        item = {
            "id": device_id,
            "ip": ip,
            "mac": mac,
            "alias": model or ip,
            "model": model,
            "device_type": device_type,
            "device_id_hash": d.get("device_id_hash", ""),
            "owner_hash": d.get("owner_hash", ""),
            "encrypt_type": d.get("encrypt_type", ""),
            "http_port": d.get("http_port") or "80",
            "login_version": d.get("login_version", ""),
            "discovery_state": d.get("state", ""),
            "is_on": discovered_power,
            "brightness": None,
            "dimmable": profile["supports_brightness"],
            "supported": profile["supported"],
            "control_ready": False,
            "control_error": "",
            "status": d.get("status", ""),
            "battery": d.get("battery", ""),
            "battery_level": d.get("battery", ""),
            "battery_percent": d.get("battery", ""),
            "last_seen": time.time(),
            **profile,
        }

        out.append(item)

    return out

async def _api_client():
    _require_credentials()
    return ApiClient(TAPO_USERNAME, TAPO_PASSWORD)

def _append_unique(items: list[str], *values: str):
    for value in values:
        clean = str(value or "").strip().lower()

        if clean and clean not in items:
            items.append(clean)

def _model_method_candidates(model: str) -> list[str]:
    raw = str(model or "").strip().lower()
    base = raw.split("(", 1)[0].strip()
    clean = re.sub(r"[^a-z0-9]+", "", base)

    candidates = []

    if clean:
        _append_unique(candidates, clean)

        family = re.match(r"^([a-z]+\d+)", clean)

        if family:
            _append_unique(candidates, family.group(1))

    return candidates

def _control_methods_for_model(model: str, device_type: str) -> list[str]:
    profile = _classify_tapo_device(model, device_type)
    kind = profile["kind"]

    if kind in {"camera", "unknown"}:
        return []

    if kind == "hub":
        return ["h100", *_model_method_candidates(model)]

    if kind in {"bulb", "lightstrip"}:
        return bulb_control_methods(model)

    if kind == "outlet_extender":
        return outlet_extender_control_methods(model)

    if kind == "plug":
        return plug_control_methods(model)

    return []

async def _get_tapo_device(item: dict[str, Any], verify_cached: bool = True):
    device_id = item.get("id")
    host = str(item.get("ip") or "").strip()

    if not host:
        raise RuntimeError("Missing Tapo host")

    cached = _tapo_handles.get(device_id)

    if cached and not verify_cached:
        return cached

    if not await _tapo_host_reachable(host):
        if device_id:
            _tapo_handles.pop(device_id, None)

        raise RuntimeError(f"Tapo device unreachable at {host}:80")

    if cached:
        try:
            await _tapo_wait(
                cached.get_device_info(),
                TAPO_DEVICE_CALL_TIMEOUT_SECONDS,
                f"{host} cached get_device_info"
            )
            return cached
        except Exception:
            _tapo_handles.pop(device_id, None)

    client = await _api_client()
    methods = _control_methods_for_model(item.get("model", ""), item.get("device_type", ""))

    errors = []

    for method_name in methods:
        method = getattr(client, method_name, None)

        if not method:
            errors.append(f"ApiClient has no {method_name}()")
            continue

        try:
            dev = await _tapo_wait(
                method(host),
                TAPO_DEVICE_CALL_TIMEOUT_SECONDS,
                f"{method_name}({host})"
            )

            if verify_cached:
                await _tapo_wait(
                    dev.get_device_info(),
                    TAPO_DEVICE_CALL_TIMEOUT_SECONDS,
                    f"{method_name}({host}).get_device_info"
                )

            if device_id:
                _tapo_handles[device_id] = dev

            return dev
        except Exception as e:
            errors.append(f"{method_name} failed: {e}")

            if device_id:
                _tapo_handles.pop(device_id, None)

            if "unreachable" in str(e).lower() or "timed out" in str(e).lower():
                break

    raise RuntimeError("; ".join(errors) or f"No working control method for {item.get('model')}")

def _info_to_dict(info) -> dict[str, Any]:
    if hasattr(info, "to_dict"):
        return info.to_dict()

    if isinstance(info, dict):
        return dict(info)

    return {
        key: value
        for key, value in vars(info).items()
        if not key.startswith("_")
    }

def _device_has_any_method(dev, names) -> bool:
    return any(callable(getattr(dev, name, None)) for name in names)

async def _maybe_await(value):
    if inspect.isawaitable(value):
        return await value

    return value

async def _tapo_wait(value, timeout_seconds: float, label: str):
    try:
        return await asyncio.wait_for(_maybe_await(value), timeout=timeout_seconds)
    except asyncio.TimeoutError as e:
        raise TimeoutError(f"{label} timed out after {timeout_seconds:g}s") from e

async def _tapo_host_reachable(host: str, port: int = 80) -> bool:
    host = str(host or "").strip()

    if not host:
        return False

    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port),
            timeout=TAPO_DEVICE_CONNECT_TIMEOUT_SECONDS
        )

        writer.close()
        await writer.wait_closed()
        return True
    except Exception:
        return False

def _first_present(data: dict[str, Any], *keys):
    for key in keys:
        if key in data and data.get(key) is not None:
            return data.get(key)

    return None

def _decode_tapo_name(value: Any) -> str:
    text = str(value or "").strip()

    if not text:
        return ""

    try:
        decoded = base64.b64decode(text, validate=True).decode("utf-8").strip()

        if decoded:
            return decoded
    except Exception:
        pass

    return text

def _coerce_tapo_power_state(value):
    if value is None:
        return None

    if isinstance(value, bool):
        return value

    if isinstance(value, (int, float)):
        return bool(value)

    text = str(value or "").strip().lower()

    if text in {"1", "true", "on", "yes", "enabled"}:
        return True

    if text in {"0", "false", "off", "no", "disabled"}:
        return False

    return None

def _normalize_tapo_children(
    info: dict[str, Any],
    model: str = "",
    device_type: str = "",
    parent_name: str = "",
) -> list[dict[str, Any]]:
    raw = (
        info.get("children")
        or info.get("child_device_list")
        or info.get("childDeviceList")
        or info.get("child_devices")
        or info.get("childDevices")
        or info.get("devices")
        or info.get("items")
        or []
    )

    if isinstance(raw, dict):
        raw = (
            raw.get("children")
            or raw.get("child_device_list")
            or raw.get("childDeviceList")
            or raw.get("child_devices")
            or raw.get("childDevices")
            or raw.get("devices")
            or raw.get("items")
            or []
        )

    if not isinstance(raw, list):
        return []

    children = []

    for index, child in enumerate(raw):
        if not isinstance(child, dict):
            try:
                child = _info_to_dict(child)
            except Exception:
                continue

        position = child.get("position")
        slot_number = child.get("slot_number")

        try:
            position = int(position)
        except (TypeError, ValueError):
            position = index + 1

        child_id = (
            child.get("id")
            or child.get("device_id")
            or child.get("deviceId")
            or child.get("child_id")
            or child.get("childId")
            or child.get("original_device_id")
            or child.get("originalDeviceId")
            or str(position)
        )

        child_model = str(
            child.get("model")
            or child.get("device_model")
            or child.get("deviceModel")
            or child.get("child_model")
            or child.get("childModel")
            or ""
        ).strip()
        alias = (
            _decode_tapo_name(child.get("nickname"))
            or _decode_tapo_name(child.get("alias"))
            or str(child.get("name") or "").strip()
            or child_model
            or f"Outlet {position}"
        )

        power = _first_present(
            child,
            "device_on",
            "is_on",
            "on",
            "state"
        )

        is_light = any(
            token in str(child.get(key) or alias or "").strip().lower()
            for key in ("type", "kind", "category", "component", "device_type", "deviceType", "name", "alias", "nickname")
            for token in ("nightlight", "night light", "light", "led")
        )
        supports_brightness = bool(_first_present(
            child,
            "supports_brightness",
            "supportsBrightness",
            "dimmable",
            "is_dimmable",
            "isDimmable"
        ))
        supports_color_temp = bool(_first_present(
            child,
            "supports_color_temp",
            "supportsColorTemp",
            "supports_color_temperature",
            "supportsColorTemperature",
            "color_temp_supported",
            "colorTempSupported"
        ))
        supports_color = bool(_first_present(
            child,
            "supports_color",
            "supportsColor",
            "supports_hue",
            "supportsHue",
            "full_color",
            "fullColor"
        ))

        battery_low_raw = _first_present(
            child,
            "at_low_battery",
            "battery_low",
            "batteryLow",
            "low_battery",
            "lowBattery"
        )
        battery_low = _coerce_tapo_power_state(battery_low_raw) is True

        children.append({
            "id": str(child_id),
            "index": max(0, position - 1),
            "cli_index": index,
            "position": position,
            "slot_number": slot_number,
            "alias": alias,
            "model": child_model,
            "category": str(child.get("category") or "").strip(),
            "avatar": str(child.get("avatar") or "").strip(),
            "type": str(child.get("type") or child.get("device_type") or child.get("deviceType") or "").strip(),
            "device_id": str(child.get("device_id") or child.get("deviceId") or "").strip(),
            "parent_device_id": str(child.get("parent_device_id") or child.get("parentDeviceId") or "").strip(),
            "mac": str(child.get("mac") or "").strip(),
            "status": str(child.get("status") or "").strip(),
            "rssi": child.get("rssi"),
            "signal_level": child.get("signal_level"),
            "at_low_battery": battery_low,
            "battery_low": battery_low,
            "battery_state": "low" if battery_low else "ok",
            "battery": _first_present(child, "battery", "battery_level", "battery_percent", "battery_percentage"),
            "is_usb": bool(child.get("is_usb")),
            "is_light": is_light,
            "supports_brightness": supports_brightness,
            "supports_color_temp": supports_color_temp,
            "supports_color": supports_color,
            "is_on": _coerce_tapo_power_state(power),
            "raw": child,
        })

    return normalize_outlet_extender_children(children, model, device_type, parent_name)

def _default_tapo_outlet_count(model: str, device_type: str) -> int:
    return default_outlet_count(model, device_type)

def _default_tapo_outlet_children(model: str, device_type: str, parent_name: str = "") -> list[dict[str, Any]]:
    return default_outlet_children(model, device_type, parent_name)

async def _read_tapo_children(dev, info: dict[str, Any], item: dict[str, Any]) -> list[dict[str, Any]]:
    model = str(item.get("model") or info.get("model") or "").strip()
    device_type = str(item.get("device_type") or info.get("device_type") or info.get("type") or "").strip()
    parent_name = str(item.get("alias") or info.get("nickname") or info.get("alias") or model or "").strip()
    children = _normalize_tapo_children(info, model, device_type, parent_name)

    if children:
        return sorted(children, key=lambda child: int(child.get("position") or child.get("index") or 0))

    for method_name in (
        "get_child_device_list",
        "get_child_device_list_json",
        "get_child_device_component_list",
        "get_child_devices",
        "get_children",
        "children",
    ):
        method = getattr(dev, method_name, None)

        if not callable(method):
            continue

        try:
            if method_name == "get_child_device_list_json":
                raw = await _maybe_await(method(0))
            else:
                raw = await _maybe_await(method())

            if isinstance(raw, list):
                payload = {"children": raw}
            elif isinstance(raw, dict):
                payload = raw
            else:
                payload = _info_to_dict(raw)

            children = _normalize_tapo_children(payload, model, device_type, parent_name)

            if children:
                return sorted(children, key=lambda child: int(child.get("position") or child.get("index") or 0))

        except Exception:
            continue

    return []

async def _call_tapo_method(dev, names, *args):
    errors = []

    for name in names:
        fn = getattr(dev, name, None)

        if not callable(fn):
            continue

        try:
            return await _tapo_wait(
                fn(*args),
                TAPO_DEVICE_CALL_TIMEOUT_SECONDS,
                f"Tapo {name}"
            )
        except TypeError as e:
            errors.append(f"{name}{args} failed: {e}")
        except Exception as e:
            errors.append(f"{name} failed: {e}")

    raise ValueError("; ".join(errors) or f"Tapo device does not support: {', '.join(names)}")

async def _set_tapo_power(dev, enabled: bool):
    if enabled:
        return await _call_tapo_method(dev, ("on", "turn_on", "set_on"))

    return await _call_tapo_method(dev, ("off", "turn_off", "set_off"))

async def _set_tapo_child_power_with_kasa_cli(item: dict[str, Any], child_index: str, enabled: bool):
    clean_index = str(child_index or "").strip()

    if not clean_index.isdigit():
        raise ValueError("Missing child index for Tapo outlet extender")

    host = str(item.get("ip") or "").strip()

    if not host:
        raise ValueError("Missing Tapo host for outlet extender")

    kasa_bin = str(Path(sys.executable).with_name("kasa"))

    cmd = [
        kasa_bin,
        "--host", host,
        "--type", "smart",
        "feature",
        "--child-index", clean_index,
        "state",
        "True" if enabled else "False",
    ]

    try:
        completed = await asyncio.to_thread(
            subprocess.run,
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=15,
            env=_kasa_cli_environment(),
        )
    except subprocess.TimeoutExpired as e:
        raise TimeoutError(_command_timeout_message(cmd, 15)) from e

    if completed.returncode != 0:
        raise RuntimeError(
            completed.stdout.strip()
            or f"kasa child power command failed with rc={completed.returncode}"
        )

    return completed.stdout

async def _read_tapo_children_with_kasa_cli(item: dict[str, Any]) -> dict[str, Any]:
    host = str(item.get("ip") or "").strip()

    # Extender child state must be read from the same Kasa implementation
    # already used to control those children, because the Tapo response can
    # contain complete child metadata while omitting every power Boolean.
    if not host:
        raise ValueError("Missing Tapo host for outlet extender")

    kasa_bin = str(Path(sys.executable).with_name("kasa"))

    # A single JSON state request returns every child under
    # get_child_device_list, avoiding one subprocess per extender outlet.
    cmd = [
        kasa_bin,
        "--host", host,
        "--type", "smart",
        "--json",
        "state",
    ]

    try:
        completed = await asyncio.to_thread(
            subprocess.run,
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=TAPO_DEVICE_CALL_TIMEOUT_SECONDS,
            env=_kasa_cli_environment(),
        )
    except subprocess.TimeoutExpired as e:
        raise TimeoutError(
            _command_timeout_message(cmd, TAPO_DEVICE_CALL_TIMEOUT_SECONDS)
        ) from e

    # Keep command failures explicit so a malformed response cannot silently
    # replace valid cached child states with unknown values.
    if completed.returncode != 0:
        raise RuntimeError(
            (completed.stderr or completed.stdout or "").strip()
            or f"kasa child state command failed with rc={completed.returncode}"
        )

    try:
        payload = json.loads(completed.stdout or "")
    except json.JSONDecodeError as e:
        # Limit the diagnostic preview so an unexpected CLI response cannot
        # flood the KotiBot log during repeated dashboard refreshes.
        preview = " ".join(
            (completed.stdout or completed.stderr or "").split()
        )[:240]
        raise RuntimeError(
            f"kasa child state returned invalid JSON: {preview or 'empty response'}"
        ) from e

    # python-kasa stores current extender children in this exact section of
    # its raw state response, including each child’s device_on value.
    child_payload = (
        payload.get("get_child_device_list")
        if isinstance(payload, dict)
        else None
    )

    if not isinstance(child_payload, dict):
        raise RuntimeError("kasa child state response is missing get_child_device_list")

    raw_children = child_payload.get("child_device_list")

    if not isinstance(raw_children, list) or not raw_children:
        raise RuntimeError("kasa child state response contains no extender children")

    # Reject metadata-only responses so the existing merge can preserve the
    # last confirmed states instead of replacing them with null values.
    has_power_states = any(
        isinstance(child, dict)
        and _coerce_tapo_power_state(
            _first_present(child, "device_on", "is_on", "on", "state")
        ) is not None
        for child in raw_children
    )

    if not has_power_states:
        raise RuntimeError("kasa child state response contains no power values")

    return child_payload

async def _ensure_tapo_native_fade(item: dict[str, Any]) -> bool:
    if str(item.get("kind") or "").lower() not in {"bulb", "lightstrip"}:
        return False

    device_id = str(item.get("id") or item.get("ip") or "").strip()
    host = str(item.get("ip") or "").strip()

    if not device_id or not host:
        return False

    target = (
        max(0, min(60, int(TAPO_NATIVE_FADE_ON_SECONDS))),
        max(0, min(60, int(TAPO_NATIVE_FADE_OFF_SECONDS))),
    )

    if _tapo_native_fade_ready.get(device_id) == target:
        item["native_fade_ready"] = True
        item["native_fade_on_seconds"] = target[0]
        item["native_fade_off_seconds"] = target[1]
        item.pop("native_fade_error", None)
        return True

    kasa_bin = str(Path(sys.executable).with_name("kasa"))

    try:
        _require_credentials()

        for feature_id, seconds in (
            ("smooth_transition_on", target[0]),
            ("smooth_transition_off", target[1]),
        ):
            cmd = [
                kasa_bin,
                "--host", host,
                "--type", "smart",
                "feature",
                feature_id,
                str(seconds),
            ]

            try:
                completed = await asyncio.to_thread(
                    subprocess.run,
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    timeout=TAPO_NATIVE_FADE_COMMAND_TIMEOUT_SECONDS,
                    env=_kasa_cli_environment(),
                )
            except subprocess.TimeoutExpired as e:
                raise TimeoutError(
                    _command_timeout_message(
                        cmd,
                        TAPO_NATIVE_FADE_COMMAND_TIMEOUT_SECONDS
                    )
                ) from e

            if completed.returncode != 0:
                raise RuntimeError(
                    completed.stdout.strip()
                    or f"kasa feature command failed with rc={completed.returncode}"
                )
            
    except Exception as e:
        error = str(e)
        _tapo_native_fade_errors[device_id] = error
        item["native_fade_ready"] = False
        item["native_fade_error"] = error

        _LOGGER.warning(
            "Tapo native fade configuration failed for %s: %s",
            item.get("alias") or device_id,
            error,
        )

        return False

    _tapo_native_fade_ready[device_id] = target
    _tapo_native_fade_errors.pop(device_id, None)

    item["native_fade_ready"] = True
    item["native_fade_on_seconds"] = target[0]
    item["native_fade_off_seconds"] = target[1]
    item.pop("native_fade_error", None)

    return True

async def _set_tapo_child_power(dev, child_id: str, enabled: bool, child_position: str = ""):
    names = (
        "set_child_device_state",
        "set_child_device_power",
        "set_child_power",
        "set_child_device_on",
    )

    errors = []
    clean_child_id = str(child_id or "").strip()
    clean_position = str(child_position or "").strip()

    for name in names:
        fn = getattr(dev, name, None)

        if not callable(fn):
            continue

        for args in (
            (clean_child_id, enabled),
            (int(clean_child_id), enabled) if clean_child_id.isdigit() else None,
        ):
            if args is None:
                continue

            try:
                return await _maybe_await(fn(*args))
            except Exception as e:
                errors.append(f"{name}{args} failed: {e}")

    plug_fn = getattr(dev, "plug", None)

    if callable(plug_fn):
        plug_attempts = []

        if clean_position.isdigit():
            plug_attempts.append({"position": int(clean_position)})

        plug_attempts.append({"device_id": clean_child_id})

        if clean_child_id.isdigit():
            plug_attempts.append({"position": int(clean_child_id)})

        for kwargs in plug_attempts:
            try:
                plug = await _maybe_await(plug_fn(**kwargs))

                if enabled:
                    return await _call_tapo_method(plug, ("on", "turn_on", "set_on"))

                return await _call_tapo_method(plug, ("off", "turn_off", "set_off"))

            except Exception as e:
                errors.append(f"plug({kwargs}) failed: {e}")

    raise ValueError("; ".join(errors) or f"Tapo child device does not support power control: {clean_child_id}")

async def _enrich_control_state(item: dict[str, Any]) -> dict[str, Any]:
    existing_children = item.get("children") if isinstance(item.get("children"), list) else []

    profile = _classify_tapo_device(item.get("model", ""), item.get("device_type", ""))
    item.update(profile)

    if existing_children:
        item["children"] = existing_children

    if item.get("kind") in {"camera", "unknown"}:
        item["control_ready"] = False
        item["control_error"] = "" if item.get("kind") != "unknown" else "Unsupported Tapo device class"
        return item

    try:
        dev = await _get_tapo_device(item)
        info = _info_to_dict(await dev.get_device_info())

        item["control_ready"] = True
        item["control_error"] = ""
        item["raw"] = info

        if "nickname" in info:
            item["alias"] = info.get("nickname") or item["alias"]
        if "model" in info:
            item["model"] = info.get("model") or item["model"]

        profile = _classify_tapo_device(item.get("model", ""), item.get("device_type", ""))
        item.update(profile)

        children = []

        if item.get("kind") == "outlet_extender":
            children = await _read_tapo_children(dev, info, item)

            if not children and existing_children:
                children = existing_children

            if not children:
                children = _default_tapo_outlet_children(
                    item.get("model", ""),
                    item.get("device_type", ""),
                    item.get("alias") or item.get("model") or ""
                )

            # The Tapo library can return valid extender identities and names
            # while leaving every child power state null, as seen in the saved
            # P306 state. Fill those missing values from Kasa’s live state.
            needs_kasa_child_state = children and any(
                isinstance(child, dict)
                and _coerce_tapo_power_state(child.get("is_on")) is None
                for child in children
            )

            if needs_kasa_child_state:
                try:
                    kasa_child_payload = await _read_tapo_children_with_kasa_cli(item)
                    kasa_children = _normalize_tapo_children(
                        kasa_child_payload,
                        item.get("model", ""),
                        item.get("device_type", ""),
                        item.get("alias") or item.get("model") or "",
                    )

                    # Reuse the shared extender merge so stable child IDs,
                    # dashboard names, room settings, and confirmed power
                    # values remain attached to the correct physical outlets.
                    if kasa_children:
                        children = merge_outlet_extender_child_metadata(
                            children,
                            kasa_children,
                            item.get("model", ""),
                            item.get("device_type", ""),
                            item.get("alias") or item.get("model") or "",
                        )

                except Exception as e:
                    # A child-state read failure must not mark the reachable
                    # parent unavailable; downstream merging will retain each
                    # child’s last confirmed Boolean state.
                    _LOGGER.warning(
                        "Tapo extender child-state refresh failed for %s: %s",
                        item.get("alias") or item.get("id") or item.get("ip"),
                        e,
                    )

        power = _first_present(info, "device_on", "is_on", "on", "state")

        item["children"] = children

        if children:
            child_states = [child.get("is_on") for child in children]

            if any(state is True for state in child_states):
                item["is_on"] = True
            elif child_states and all(state is False for state in child_states):
                item["is_on"] = False
            else:
                item["is_on"] = None
        else:
            item["is_on"] = _coerce_tapo_power_state(power)
        item["brightness"] = info.get("brightness", item.get("brightness"))
        item["color_temperature"] = (
            info.get("color_temp")
            or info.get("color_temperature")
            or info.get("colour_temperature")
            or item.get("color_temperature")
            or 4200
        )
        item["hue"] = info.get("hue", item.get("hue", 45))
        item["saturation"] = info.get("saturation", item.get("saturation", 100))
        if item.get("kind") in {"bulb", "lightstrip"}:
            item = update_bulb_capabilities_from_device(item, dev, _device_has_any_method)

    except Exception as e:
        item["control_ready"] = False
        item["control_error"] = str(e)

        item["is_on"] = None

        device_id = item.get("id")
        if device_id:
            _tapo_handles.pop(device_id, None)

        if isinstance(item.get("children"), list):
            item["children"] = [
                {
                    **child,
                    "is_on": None,
                    "device_on": None,
                    "on": None,
                    "state": None,
                }
                for child in item["children"]
                if isinstance(child, dict)
            ]

    return item

async def _discover_tapo(force: bool = False) -> list[dict[str, Any]]:
    global _tapo_last_scan

    now = time.time()

    if not force and _tapo_devices and now - _tapo_last_scan < TAPO_CACHE_SECONDS:
        return list(_tapo_devices.values())

    discovery_text = _run_discovery_text()
    discovered = _parse_kasa_discovery(discovery_text)

    if not discovered:
        raise RuntimeError(f"Tapo discovery returned no parseable devices: {discovery_text[:500]}")

    enriched = await asyncio.gather(*[
        _enrich_control_state(item)
        for item in discovered
    ])
    enriched = await enrich_tapo_energy_devices(
        enriched,
        _get_tapo_device,
    )

    _tapo_devices.clear()

    for item in enriched:
        _tapo_devices[item["id"]] = item

    _tapo_last_scan = now

    return list(_tapo_devices.values())

async def list_tapo_devices(force: bool = False) -> list[dict[str, Any]]:
    return await _discover_tapo(force=force)

async def refresh_tapo_devices(
    devices: list[dict[str, Any]],
    energy_force: bool = False,
) -> list[dict[str, Any]]:
    items = [
        dict(item)
        for item in devices
        if item.get("id") and item.get("ip")
    ]

    if not items:
        return []

    async def refresh_one(item):
        try:
            return await asyncio.wait_for(
                _enrich_control_state(item),
                timeout=TAPO_DEVICE_REFRESH_TIMEOUT_SECONDS
            )
        except Exception as e:
            item["control_ready"] = False
            item["control_error"] = str(e)
            item["is_on"] = None

            if isinstance(item.get("children"), list):
                item["children"] = [
                    {
                        **child,
                        "is_on": None,
                        "device_on": None,
                        "on": None,
                        "state": None,
                    }
                    for child in item["children"]
                    if isinstance(child, dict)
                ]

            device_id = item.get("id")
            if device_id:
                _tapo_handles.pop(device_id, None)

            return item

    refreshed = await asyncio.gather(*[
        refresh_one(item)
        for item in items
    ])
    refreshed = await enrich_tapo_energy_devices(
        refreshed,
        _get_tapo_device,
        force=energy_force,
    )

    for item in refreshed:
        device_id = item.get("id")
        if device_id:
            _tapo_devices[device_id] = item

    return refreshed

async def _get_cached_item(device_id: str) -> dict[str, Any]:
    item = _tapo_devices.get(device_id)

    if not item:
        raise KeyError(device_id)

    return item

async def _set_tapo_light_value_without_power(
    dev,
    item: dict[str, Any],
    device_id: str,
    builder_method: str,
    method_names,
    *args,
    fast: bool = False,
) -> dict[str, Any]:
    if not fast:
        item = await _enrich_control_state(item)

        if item.get("control_ready") is False:
            item["last_command_at"] = time.time()
            _tapo_devices[device_id] = item
            raise RuntimeError(item.get("control_error") or "Tapo device is unavailable")

    if item.get("is_on") is not False:
        await _call_tapo_method(dev, method_names, *args)
        return item

    async def set_value_then_restore_off():
        try:
            await _call_tapo_method(dev, method_names, *args)
        finally:
            await _set_tapo_power(dev, False)

        return item

    set_builder = getattr(dev, "set", None)

    if not callable(set_builder):
        return await set_value_then_restore_off()

    builder = set_builder()
    off = getattr(builder, "off", None)

    if not callable(off):
        return await set_value_then_restore_off()

    builder = off()
    set_value = getattr(builder, builder_method, None)

    if not callable(set_value):
        return await set_value_then_restore_off()

    builder = set_value(*args)
    send = getattr(builder, "send", None)

    if not callable(send):
        return await set_value_then_restore_off()

    await _tapo_wait(
        send(dev),
        TAPO_DEVICE_CALL_TIMEOUT_SECONDS,
        f"Tapo set {builder_method} while off"
    )

    return item

def _tapo_lighting_value_matches(item: dict[str, Any], action: str, value) -> bool:
    def close(actual, expected, tolerance=0):
        try:
            return abs(int(actual) - int(expected)) <= tolerance
        except Exception:
            return False

    action = str(action or "").strip().lower()

    if action in {"brightness", "brightness_no_power"}:
        return close(item.get("brightness"), value, 1)

    if action in {"color_temperature", "color_temperature_no_power"}:
        return close(item.get("color_temperature"), value, 25)

    if action in {"color", "color_no_power"} and isinstance(value, dict):
        try:
            actual_hue = int(item.get("hue")) % 360
            expected_hue = int(value.get("hue", 0)) % 360
            hue_delta = abs(actual_hue - expected_hue)
            hue_matches = min(hue_delta, 360 - hue_delta) <= 1
        except Exception:
            hue_matches = False

        return (
            hue_matches
            and close(item.get("saturation"), value.get("saturation", 100), 1)
        )

    return True

async def _confirm_tapo_lighting_command(
    dev,
    item: dict[str, Any],
    device_id: str,
    action: str,
    value,
) -> dict[str, Any]:
    preserve_power = action.endswith("_no_power")

    if (
        (preserve_power or item.get("is_on") is True)
        and _tapo_lighting_value_matches(item, action, value)
    ):
        return item

    await asyncio.sleep(0.35)

    if action in {"brightness", "brightness_no_power"}:
        if action == "brightness":
            await _call_tapo_method(dev, ("on", "turn_on", "set_on"))
            await _call_tapo_method(
                dev,
                ("set_brightness",),
                int(value or 0)
            )
        else:
            item = await _set_tapo_light_value_without_power(
                dev,
                item,
                device_id,
                "brightness",
                ("set_brightness",),
                int(value or 0),
            )

    elif action in {"color_temperature", "color_temperature_no_power"}:
        if action == "color_temperature":
            await _call_tapo_method(dev, ("on", "turn_on", "set_on"))
            await _call_tapo_method(
                dev,
                ("set_color_temperature", "set_colour_temperature", "set_color_temp"),
                int(value or 0)
            )
        else:
            item = await _set_tapo_light_value_without_power(
                dev,
                item,
                device_id,
                "color_temperature",
                ("set_color_temperature", "set_colour_temperature", "set_color_temp"),
                int(value or 0),
            )

    elif action in {"color", "color_no_power"} and isinstance(value, dict):
        if action == "color":
            await _call_tapo_method(dev, ("on", "turn_on", "set_on"))
            await _call_tapo_method(
                dev,
                ("set_hue_saturation", "set_hsv", "set_color"),
                max(0, min(360, int(value.get("hue", 0)))),
                max(0, min(100, int(value.get("saturation", 100))))
            )
        else:
            item = await _set_tapo_light_value_without_power(
                dev,
                item,
                device_id,
                "hue_saturation",
                ("set_hue_saturation", "set_hsv", "set_color"),
                max(0, min(360, int(value.get("hue", 0)))),
                max(0, min(100, int(value.get("saturation", 100)))),
            )

    item = await _enrich_control_state(item)

    if item.get("control_ready") is False:
        raise RuntimeError(
            item.get("control_error")
            or f"Tapo lighting verification failed for {device_id}"
        )

    if (
        (not preserve_power and item.get("is_on") is not True)
        or not _tapo_lighting_value_matches(item, action, value)
    ):
        raise RuntimeError(
            f"Tapo {device_id} {action} command did not reach the requested state"
        )

    return item

async def set_tapo_device(device_id: str, action: str, value: int | dict | None = None, fast: bool = False) -> dict[str, Any]:

    if action == "color_temp":
        action = "color_temperature"

    item = await _get_cached_item(device_id)
    kind = str(item.get("kind") or "").lower()

    if kind in {"camera", "unknown", "button"}:
        raise ValueError(f"Tapo {kind or 'device'} does not support power/light commands yet")

    dev = await _get_tapo_device(item, verify_cached=not fast)

    child_id = ""

    child_position = ""
    child_index = ""

    if isinstance(value, dict):
        child_id = str(
            value.get("child_id")
            or value.get("childId")
            or value.get("outlet_id")
            or value.get("outletId")
            or ""
        ).strip()

        child_position = str(
            value.get("position")
            or value.get("child_position")
            or value.get("childPosition")
            or ""
        ).strip()

        child_index = str(
            value.get("child_index")
            or value.get("childIndex")
            or value.get("cli_index")
            or value.get("cliIndex")
            or ""
        ).strip()

    if action == "child_on":
        action = "on"
        child_id = child_id or str((value or {}).get("id") or "").strip()

    elif action == "child_off":
        action = "off"
        child_id = child_id or str((value or {}).get("id") or "").strip()

    if kind == "outlet_extender" and action in {"on", "off"} and not child_id:
        raise ValueError("Outlet extenders require a child_id")

    # Fast automation commands must reach the device immediately. Native-fade
    # configuration is optional setup work and remains on the verified
    # dashboard/manual-command path.
    if (
        not fast
        and action in {"on", "off"}
        and not child_id
        and kind in {"bulb", "lightstrip"}
    ):
        await _ensure_tapo_native_fade(item)

    if action == "on":
        if child_id:
            if kind == "outlet_extender":
                await _set_tapo_child_power_with_kasa_cli(item, child_index, True)
            else:
                await _set_tapo_child_power(dev, child_id, True, child_position)
        else:
            await _set_tapo_power(dev, True)

    elif action == "off":
        if child_id:
            if kind == "outlet_extender":
                await _set_tapo_child_power_with_kasa_cli(item, child_index, False)
            else:
                await _set_tapo_child_power(dev, child_id, False, child_position)
        else:
            await _set_tapo_power(dev, False)

    elif action in {"brightness", "brightness_no_power"}:
        brightness = int(value or 0)

        if brightness < 1 or brightness > 100:
            raise ValueError("brightness must be 1-100")

        if action == "brightness":
            await _call_tapo_method(dev, ("on", "turn_on", "set_on"))
            await _call_tapo_method(dev, ("set_brightness",), brightness)
        else:
            item = await _set_tapo_light_value_without_power(
                dev,
                item,
                device_id,
                "brightness",
                ("set_brightness",),
                brightness,
                fast=fast,
            )

    elif action in {"color_temperature", "color_temperature_no_power"}:
        color_temperature = int(value or 0)

        if color_temperature < 2500 or color_temperature > 6500:
            raise ValueError("color temperature must be 2500-6500")

        if action == "color_temperature":
            await _call_tapo_method(dev, ("on", "turn_on", "set_on"))
            await _call_tapo_method(
                dev,
                ("set_color_temperature", "set_colour_temperature", "set_color_temp"),
                color_temperature
            )
        else:
            item = await _set_tapo_light_value_without_power(
                dev,
                item,
                device_id,
                "color_temperature",
                ("set_color_temperature", "set_colour_temperature", "set_color_temp"),
                color_temperature,
                fast=fast,
            )

    elif action in {"color", "color_no_power"}:
        if not isinstance(value, dict):
            raise ValueError("color value must include hue and saturation")

        hue = int(value.get("hue", 0))
        saturation = int(value.get("saturation", 100))

        hue = max(0, min(360, hue))
        saturation = max(0, min(100, saturation))

        if action == "color":
            await _call_tapo_method(dev, ("on", "turn_on", "set_on"))
            await _call_tapo_method(
                dev,
                ("set_hue_saturation", "set_hsv", "set_color"),
                hue,
                saturation
            )
        else:
            item = await _set_tapo_light_value_without_power(
                dev,
                item,
                device_id,
                "hue_saturation",
                ("set_hue_saturation", "set_hsv", "set_color"),
                hue,
                saturation,
                fast=fast,
            )

    else:
        raise ValueError(f"Unknown Tapo action: {action}")

    if fast:
        item = dict(item)
        item["control_ready"] = True
        item["control_error"] = ""
    else:
        item = await _enrich_control_state(item)

    children = item.get("children") if isinstance(item.get("children"), list) else []

    if item.get("control_ready") is False:
        raise RuntimeError(item.get("control_error") or "Tapo command failed")

    if not fast and action in {
        "brightness",
        "brightness_no_power",
        "color_temperature",
        "color_temperature_no_power",
        "color",
        "color_no_power",
    }:
        item = await _confirm_tapo_lighting_command(
            dev,
            item,
            device_id,
            action,
            value
        )

    if action in {"on", "off"}:
        desired_on = action == "on"

        if not fast and not child_id and item.get("is_on") is not desired_on:
            raise RuntimeError(
                item.get("control_error")
                or f"Tapo command did not change power state to {action}"
            )

        if child_id and children:
            for child in children:
                if not isinstance(child, dict):
                    continue

                child_keys = {
                    str(child.get("id") or ""),
                    str(child.get("index") or ""),
                    str(child.get("position") or ""),
                    str(child.get("cli_index") or ""),
                }

                if child_id in child_keys or child_position in child_keys or child_index in child_keys:
                    child["is_on"] = desired_on

            child_states = [
                child.get("is_on")
                for child in children
                if isinstance(child, dict)
            ]

            if any(state is True for state in child_states):
                item["is_on"] = True
            elif child_states and all(state is False for state in child_states):
                item["is_on"] = False
            else:
                item["is_on"] = None
        else:
            item["is_on"] = desired_on

    elif action in {"brightness", "brightness_no_power"}:
        if action == "brightness":
            item["is_on"] = True
        item["brightness"] = int(value or item.get("brightness") or 0)

    elif action in {"color_temperature", "color_temperature_no_power"}:
        if action == "color_temperature":
            item["is_on"] = True
        item["color_temperature"] = int(value or 0)

    elif action in {"color", "color_no_power"}:
        if action == "color":
            item["is_on"] = True
        item["hue"] = int(value.get("hue", 0))
        item["saturation"] = int(value.get("saturation", 100))

    item["last_command_at"] = time.time()
    _tapo_devices[device_id] = item

    return {
        "ok": True,
        "id": device_id,
        "action": action,
        "device": item,
    }

async def set_tapo_device_from_info(item: dict[str, Any], action: str, value: int | dict | None = None, fast: bool = False) -> dict[str, Any]:
    device_id = item.get("id")

    if not device_id:
        raise KeyError("missing tapo id")

    existing = _tapo_devices.get(device_id, {})

    model = item.get("model") or existing.get("model", "")
    device_type = item.get("device_type") or existing.get("device_type", "")
    profile = _classify_tapo_device(model, device_type)

    existing.update({
        "id": device_id,
        "ip": item.get("ip") or existing.get("ip", ""),
        "model": model,
        "device_type": device_type,

        "kind": item.get("kind") or existing.get("kind") or profile["kind"],
        "dashboard_section": item.get("dashboard_section") or existing.get("dashboard_section") or profile["dashboard_section"],

        "is_bulb": bool(item.get("is_bulb", existing.get("is_bulb", profile["is_bulb"]))),
        "is_plug": bool(item.get("is_plug", existing.get("is_plug", profile["is_plug"]))),
        "is_outlet_extender": bool(item.get("is_outlet_extender", existing.get("is_outlet_extender", profile["is_outlet_extender"]))),
        "is_camera": bool(item.get("is_camera", existing.get("is_camera", profile["is_camera"]))),
        "dimmable": bool(item.get("dimmable", existing.get("dimmable", profile["supports_brightness"]))),
        "supports_power": bool(item.get("supports_power", existing.get("supports_power", profile["supports_power"]))),
        "supports_brightness": bool(item.get("supports_brightness", existing.get("supports_brightness", profile["supports_brightness"]))),
        "supports_color_temp": bool(item.get("supports_color_temp", existing.get("supports_color_temp", profile["supports_color_temp"]))),
        "supports_color": bool(item.get("supports_color", existing.get("supports_color", profile["supports_color"]))),
        "children": item.get("children") if isinstance(item.get("children"), list) else existing.get("children", []),
    })

    for key in (
        "battery",
        "battery_level",
        "battery_percent",
    ):
        if key in item:
            existing[key] = item.get(key)

    for key in ("is_on", "brightness", "color_temperature", "hue", "saturation"):
        if key in item:
            existing[key] = item.get(key)

    _tapo_devices[device_id] = existing

    return await set_tapo_device(device_id, action, value, fast=fast)

async def tapo_on(device_id: str) -> dict[str, Any]:
    return await set_tapo_device(device_id, "on")

async def tapo_off(device_id: str) -> dict[str, Any]:
    return await set_tapo_device(device_id, "off")

async def tapo_brightness(device_id: str, brightness: int) -> dict[str, Any]:
    return await set_tapo_device(device_id, "brightness", brightness)
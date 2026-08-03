import re
import shutil
import subprocess
import time

_DEVICE_LINE_RE = re.compile(r"^Device\s+([0-9A-Fa-f:]{17})\s+(.+?)\s*$")
_MAC_RE = re.compile(r"^[0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5}$")
BLUETOOTH_PAIR_SCAN_PROC = None


def _clean_text(value):
    return " ".join(str(value or "").replace("\r", " ").replace("\n", " ").split())


def _clean_address(value):
    address = str(value or "").strip().upper()
    return address if _MAC_RE.match(address) else ""


def _run_bluetoothctl(args, timeout=8):
    command = ["bluetoothctl", *[str(arg) for arg in args]]

    if shutil.which("bluetoothctl") is None:
        return {
            "ok": False,
            "stdout": "",
            "stderr": "bluetoothctl was not found on this server",
            "returncode": 127,
        }

    try:
        proc = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=max(1, int(timeout or 8)),
            check=False,
        )
        stderr = _clean_text(proc.stderr)

        return {
            "ok": proc.returncode == 0,
            "stdout": proc.stdout or "",
            "stderr": stderr,
            "returncode": proc.returncode,
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "ok": False,
            "stdout": exc.stdout or "",
            "stderr": "bluetoothctl timed out",
            "returncode": 124,
        }
    except Exception as exc:
        return {
            "ok": False,
            "stdout": "",
            "stderr": _clean_text(exc),
            "returncode": 1,
        }


def _scan_bluetoothctl(seconds):
    if shutil.which("bluetoothctl") is None:
        return {
            "ok": False,
            "stdout": "",
            "stderr": "bluetoothctl was not found on this server",
            "returncode": 127,
        }

    proc = None

    try:
        proc = subprocess.Popen(
            ["bluetoothctl", "scan", "on"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        time.sleep(seconds)
        proc.terminate()

        try:
            stdout, stderr = proc.communicate(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()
            stdout, stderr = proc.communicate(timeout=2)

        return {
            "ok": proc.returncode in (0, -15, -9, None),
            "stdout": stdout or "",
            "stderr": _clean_text(stderr),
            "returncode": proc.returncode,
        }
    except Exception as exc:
        if proc is not None:
            try:
                proc.kill()
            except Exception:
                pass

        return {
            "ok": False,
            "stdout": "",
            "stderr": _clean_text(exc),
            "returncode": 1,
        }


def _parse_adapter_show(output):
    adapter = {
        "address": "",
        "name": "",
        "alias": "",
        "powered": False,
        "discoverable": False,
        "pairable": False,
        "discovering": False,
    }

    for raw_line in str(output or "").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("["):
            continue

        if line.startswith("Controller "):
            parts = line.split(maxsplit=2)
            if len(parts) > 1:
                adapter["address"] = parts[1].upper()
            if len(parts) > 2:
                adapter["name"] = parts[2].strip()
            continue

        if ":" not in line:
            continue

        key, value = line.split(":", 1)
        key = key.strip().lower().replace(" ", "_")
        value = value.strip()

        if key in ("alias", "name"):
            adapter[key] = value
        elif key in ("powered", "discoverable", "pairable", "discovering"):
            adapter[key] = value.lower() == "yes"

    return adapter


def _parse_device_lines(output):
    devices = []
    seen = set()

    for raw_line in str(output or "").splitlines():
        match = _DEVICE_LINE_RE.match(raw_line.strip())
        if not match:
            continue

        address = match.group(1).upper()
        if address in seen:
            continue

        seen.add(address)
        devices.append({
            "address": address,
            "name": match.group(2).strip() or address,
        })

    return devices


def _parse_device_info(address, output):
    device = {
        "address": address,
        "name": address,
        "alias": "",
        "paired": False,
        "trusted": False,
        "blocked": False,
        "connected": False,
        "rssi": None,
    }

    for raw_line in str(output or "").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("["):
            continue

        if line.startswith("Device "):
            parts = line.split(maxsplit=2)
            if len(parts) > 2:
                device["name"] = parts[2].strip() or address
            continue

        if ":" not in line:
            continue

        key, value = line.split(":", 1)
        key = key.strip().lower().replace(" ", "_")
        value = value.strip()

        if key in ("name", "alias"):
            device[key] = value
        elif key in ("paired", "trusted", "blocked", "connected"):
            device[key] = value.lower() == "yes"
        elif key == "rssi":
            try:
                device["rssi"] = int(value)
            except Exception:
                device["rssi"] = None

    return device


def _device_info(address):
    res = _run_bluetoothctl(["info", address], timeout=6)
    device = _parse_device_info(address, res.get("stdout", ""))
    device["ok"] = res.get("ok")
    if res.get("stderr"):
        device["error"] = res.get("stderr")
    return device


def _device_list(command):
    res = _run_bluetoothctl([command], timeout=8)
    devices = _parse_device_lines(res.get("stdout", ""))

    enriched = []
    for device in devices[:80]:
        info = _device_info(device["address"])
        if not info.get("name") or info.get("name") == device["address"]:
            info["name"] = device.get("name") or device["address"]
        enriched.append(info)

    return {
        "ok": res.get("ok"),
        "devices": enriched,
        "error": res.get("stderr", ""),
    }


def _quick_device_lines(kind=""):
    args = ["devices"]

    if kind:
        args.append(kind)

    res = _run_bluetoothctl(args, timeout=3)
    devices = _parse_device_lines(res.get("stdout", ""))

    return {
        "ok": res.get("ok"),
        "devices": devices,
        "error": res.get("stderr", ""),
    }


def _bluetooth_pairing_scan_active():
    return BLUETOOTH_PAIR_SCAN_PROC is not None and BLUETOOTH_PAIR_SCAN_PROC.poll() is None


def _start_bluetooth_pairing_scan():
    global BLUETOOTH_PAIR_SCAN_PROC

    if shutil.which("bluetoothctl") is None:
        return {
            "ok": False,
            "stderr": "bluetoothctl was not found on this server",
            "returncode": 127,
        }

    if _bluetooth_pairing_scan_active():
        return {"ok": True, "stderr": "", "returncode": 0}

    try:
        BLUETOOTH_PAIR_SCAN_PROC = subprocess.Popen(
            ["bluetoothctl", "scan", "on"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        time.sleep(0.2)

        return {"ok": True, "stderr": "", "returncode": 0}
    except Exception as exc:
        BLUETOOTH_PAIR_SCAN_PROC = None

        return {
            "ok": False,
            "stderr": _clean_text(exc),
            "returncode": 1,
        }


def _stop_bluetooth_pairing_scan():
    global BLUETOOTH_PAIR_SCAN_PROC

    proc = BLUETOOTH_PAIR_SCAN_PROC
    BLUETOOTH_PAIR_SCAN_PROC = None

    if proc is not None and proc.poll() is None:
        try:
            proc.terminate()
            proc.wait(timeout=2)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

    return _run_bluetoothctl(["scan", "off"], timeout=4)


def _pairing_device_list():
    paired_addresses = {
        device["address"]
        for device in _paired_device_list().get("devices", [])
        if device.get("address")
    }
    devices_res = _quick_device_lines()
    devices = []

    for device in devices_res.get("devices", [])[:80]:
        address = device.get("address")

        if not address or address in paired_addresses:
            continue

        devices.append({
            "address": address,
            "name": device.get("name") or address,
            "alias": device.get("name") or address,
            "paired": False,
            "trusted": False,
            "blocked": False,
            "connected": False,
            "rssi": None,
        })

    return {
        "ok": devices_res.get("ok"),
        "devices": devices,
        "error": devices_res.get("error", ""),
    }


def _paired_device_list():
    paired_res = _quick_device_lines("Paired")
    paired = paired_res.get("devices", [])

    if not paired:
        fallback_res = _run_bluetoothctl(["paired-devices"], timeout=3)
        fallback_devices = _parse_device_lines(fallback_res.get("stdout", ""))

        if fallback_devices or not paired_res.get("ok"):
            paired_res = {
                "ok": fallback_res.get("ok"),
                "devices": fallback_devices,
                "error": fallback_res.get("stderr", ""),
            }
            paired = fallback_devices

    trusted = {device["address"] for device in _quick_device_lines("Trusted").get("devices", [])}
    connected = {device["address"] for device in _quick_device_lines("Connected").get("devices", [])}

    return {
        "ok": paired_res.get("ok"),
        "devices": [
            {
                "address": device["address"],
                "name": device.get("name") or device["address"],
                "alias": device.get("name") or device["address"],
                "paired": True,
                "trusted": device["address"] in trusted,
                "blocked": False,
                "connected": device["address"] in connected,
                "rssi": None,
            }
            for device in paired[:80]
        ],
        "error": paired_res.get("error", ""),
    }

def _bluetooth_status():
    show_res = _run_bluetoothctl(["show"], timeout=8)
    paired_res = _paired_device_list()

    return {
        "ok": bool(show_res.get("ok")),
        "adapter": _parse_adapter_show(show_res.get("stdout", "")),
        "paired": paired_res.get("devices", []),
        "error": show_res.get("stderr") or paired_res.get("error") or "",
    }

def register_bluetooth_routes(app, ctx):
    @app.route("/api/bluetooth/status", methods=["GET"])
    def api_bluetooth_status():
        return app.response_class(
            response=ctx["json_dumps"](_bluetooth_status()),
            status=200,
            mimetype="application/json",
        )

    @app.route("/api/bluetooth/pairing/start", methods=["POST"])
    def api_bluetooth_pairing_start():
        _run_bluetoothctl(["power", "on"], timeout=4)
        _run_bluetoothctl(["pairable", "on"], timeout=4)
        scan_res = _start_bluetooth_pairing_scan()
        status = _bluetooth_status()
        status["ok"] = bool(scan_res.get("ok"))
        status["pairing"] = True
        status["error"] = scan_res.get("stderr") or status.get("error") or ""

        return app.response_class(
            response=ctx["json_dumps"]({
                "ok": bool(scan_res.get("ok")),
                "status": status,
                "error": status.get("error", ""),
            }),
            status=200 if scan_res.get("ok") else 500,
            mimetype="application/json",
        )

    @app.route("/api/bluetooth/pairing/devices", methods=["GET"])
    def api_bluetooth_pairing_devices():
        devices_res = _pairing_device_list()

        return app.response_class(
            response=ctx["json_dumps"]({
                "ok": bool(devices_res.get("ok")),
                "devices": devices_res.get("devices", []),
                "status": _bluetooth_status(),
                "error": devices_res.get("error", ""),
            }),
            status=200 if devices_res.get("ok") else 500,
            mimetype="application/json",
        )

    @app.route("/api/bluetooth/pairing/cancel", methods=["POST"])
    def api_bluetooth_pairing_cancel():
        scan_res = _stop_bluetooth_pairing_scan()
        _run_bluetoothctl(["pairable", "off"], timeout=4)
        status = _bluetooth_status()
        status["pairing"] = False

        return app.response_class(
            response=ctx["json_dumps"]({
                "ok": True,
                "status": status,
                "error": scan_res.get("stderr") or status.get("error") or "",
            }),
            status=200,
            mimetype="application/json",
        )

    @app.route("/api/bluetooth/adapter", methods=["POST"])
    def api_bluetooth_adapter():
        payload = ctx["request_json"]()
        action = str(payload.get("action") or "").strip().lower()
        actions = {
            "power_on": ["power", "on"],
            "power_off": ["power", "off"],
            "pairable_on": ["pairable", "on"],
            "pairable_off": ["pairable", "off"],
            "discoverable_on": ["discoverable", "on"],
            "discoverable_off": ["discoverable", "off"],
        }

        if action not in actions:
            return app.response_class(
                response=ctx["json_dumps"]({"ok": False, "error": "unknown_bluetooth_adapter_action"}),
                status=400,
                mimetype="application/json",
            )

        result = _run_bluetoothctl(actions[action], timeout=8)
        status = _bluetooth_status()
        status["ok"] = bool(result.get("ok"))
        status["command_error"] = result.get("stderr") or ""
        return app.response_class(response=ctx["json_dumps"](status), status=200 if result.get("ok") else 500, mimetype="application/json")

    @app.route("/api/bluetooth/scan", methods=["POST"])
    def api_bluetooth_scan():
        payload = ctx["request_json"]()
        seconds = ctx["safe_int"](payload.get("seconds"))
        seconds = max(3, min(seconds if seconds is not None else 8, 15))

        _run_bluetoothctl(["power", "on"], timeout=8)
        scan_res = _scan_bluetoothctl(seconds)
        _run_bluetoothctl(["scan", "off"], timeout=8)
        time.sleep(0.2)

        devices_res = _device_list("devices")

        return app.response_class(response=ctx["json_dumps"]({
            "ok": bool(devices_res.get("ok")),
            "devices": devices_res.get("devices", []),
            "error": scan_res.get("stderr") or devices_res.get("error") or "",
        }), status=200, mimetype="application/json")

    @app.route("/api/bluetooth/device", methods=["POST"])
    def api_bluetooth_device():
        payload = ctx["request_json"]()
        address = _clean_address(payload.get("address"))
        action = str(payload.get("action") or "").strip().lower()
        actions = {
            "pair": ["pair", address],
            "connect": ["connect", address],
            "disconnect": ["disconnect", address],
            "trust": ["trust", address],
            "untrust": ["untrust", address],
            "remove": ["remove", address],
        }

        if not address:
            return app.response_class(response=ctx["json_dumps"]({"ok": False, "error": "invalid_bluetooth_address"}), status=400, mimetype="application/json")

        if action not in actions:
            return app.response_class(response=ctx["json_dumps"]({"ok": False, "error": "unknown_bluetooth_device_action"}), status=400, mimetype="application/json")

        result = _run_bluetoothctl(actions[action], timeout=12)

        device = _device_info(address) if action != "remove" else {"address": address}
        return app.response_class(response=ctx["json_dumps"]({
            "ok": bool(result.get("ok")),
            "device": device,
            "error": result.get("stderr") or "",
        }), status=200 if result.get("ok") else 500, mimetype="application/json")
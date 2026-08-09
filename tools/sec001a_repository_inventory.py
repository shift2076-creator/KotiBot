#!/usr/bin/env python3
"""Create the value-free SEC-001A repository/source inventory.

This scanner reads tracked source code and .gitignore only. It never opens
JSON/JSONL state, credentials, environment files, databases, media, logs, or
other runtime data. Output is limited to names, repository-relative source
locations, and operation types.
"""

from __future__ import annotations

import argparse
import ast
from collections import defaultdict
from pathlib import Path
import re
import subprocess


DEFAULT_OUTPUT = Path(
    "docs/security/SEC-001A_REPOSITORY_SOURCE_INVENTORY.md"
)
SCANNER_PATH = "tools/sec001a_repository_inventory.py"
SEC001A_REVIEWED_SOURCE_COMMIT = (
    "6ba497399573176b6fe48f99379f1c30ba92678f"
)
PYTHON_SUFFIX = ".py"
TEXT_SOURCE_SUFFIXES = {
    ".html",
    ".js",
    ".kt",
    ".kts",
    ".py",
    ".xml",
}
RUNTIME_FILE_RE = re.compile(
    r"(?:^|[/\\])[^/\\]+(?:"
    r"\.jsonl?(?:\.[A-Za-z0-9_-]+)?|"
    r"\.sqlite3?|\.db|\.log|\.bak(?:\.[A-Za-z0-9_-]+)?|"
    r"\.tmp|\.pid|\.pem|\.key|\.p12|\.pfx|"
    r"\.mp4|\.m3u8|\.apk"
    r")$",
    re.IGNORECASE,
)
RUNTIME_DIRECTORY_NAMES = {
    "cache",
    "camera_hls",
    "chip_tool_storage",
    "chip_tool_subscription_storage",
    "logs",
    "recordings",
    "runtime",
    "temp",
    "tmp",
    "videos",
}
TRACKED_RUNTIME_RE = re.compile(
    r"(?:\.jsonl?(?:\..*)?|\.sqlite3?|\.db|\.log|\.bak(?:\..*)?|"
    r"\.tmp|\.pid|\.pem|\.key|\.p12|\.pfx)$",
    re.IGNORECASE,
)
ENV_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]+$")
ENV_HELPERS = {
    "_env_bool",
    "_matter_env_bool",
    "_matter_env_seconds",
    "env_enabled",
}
READ_CALLS = {
    "from_service_account_file",
    "json_exists",
    "load",
    "loads",
    "open",
    "read_bytes",
    "read_json",
    "read_text",
}
WRITE_CALLS = {
    "chmod",
    "dump",
    "dumps",
    "mkdir",
    "open",
    "replace",
    "rename",
    "rmtree",
    "unlink",
    "write",
    "write_bytes",
    "write_json_atomic",
    "write_text",
}
BROWSER_STORAGE_RE = re.compile(
    r"\b(localStorage|sessionStorage)\."
    r"(getItem|setItem|removeItem)\(\s*(['\"])([^'\"]+)\3"
)
INDEXED_DB_RE = re.compile(
    r"\bindexedDB\.open\(\s*(['\"])([^'\"]+)\1"
)
DYNAMIC_ENVIRONMENT_NAMES = {
    "KOTIBOT_MATTER_SENSOR_SUBSCRIBE_ENABLED": (
        "subsystems/matter/matter_routes.py",
        "dynamic environment prefix",
    ),
    "KOTIBOT_MATTER_SENSOR_SUBSCRIBE_INITIAL_DELAY_SECONDS": (
        "subsystems/matter/matter_routes.py",
        "dynamic environment prefix",
    ),
    "KOTIBOT_MATTER_SENSOR_SUBSCRIBE_MAX_SECONDS": (
        "subsystems/matter/matter_routes.py",
        "dynamic environment prefix",
    ),
    "KOTIBOT_MATTER_SENSOR_SUBSCRIBE_MIN_SECONDS": (
        "subsystems/matter/matter_routes.py",
        "dynamic environment prefix",
    ),
    "KOTIBOT_MATTER_SENSOR_SUBSCRIBE_RETRY_SECONDS": (
        "subsystems/matter/matter_routes.py",
        "dynamic environment prefix",
    ),
}

DYNAMIC_BROWSER_STORAGE_NAMES = (
    ("localStorage", "dashboardRoomOrder", "static/js/dashboard-state.js", 443),
    ("localStorage", "dashboardControlsRoomOrder", "static/js/dashboard-state.js", 444),
    ("localStorage", "dashboardMonitorsRoomOrder", "static/js/dashboard-state.js", 445),
    ("localStorage", "dashboardSensorsRoomOrder", "static/js/dashboard-state.js", 446),
    ("localStorage", "kotibot_environment_temperature_unit", "subsystems/matter/static/js/matter-render.js", 162),
)

# Each value is: data class, household/personal classification, lifecycle.
BROWSER_STORAGE_REVIEW = {
    "cardDebugInfo": ("UI preference", "No", "Active"),
    "dashboardActiveRoomFilter": ("Legacy UI preference", "No", "Removal only"),
    "dashboardControlsRoomOrder": ("Household layout", "Household room names/order", "Active"),
    "dashboardDefaultsVersion": ("UI schema marker", "No", "Active"),
    "dashboardGroupByRoom": ("UI preference", "No", "Active"),
    "dashboardInfoShown": ("UI preference", "No", "Active"),
    "dashboardMaxColumns": ("Legacy UI preference", "No", "Removal only"),
    "dashboardMonitorsRoomOrder": ("Household layout", "Household room names/order", "Active"),
    "dashboardPage": ("UI preference", "No", "Active"),
    "dashboardRoomOrder": ("Household layout", "Household room names/order", "Active"),
    "dashboardSelectedCameraId": ("Household device selection", "Household device identifier", "Active"),
    "dashboardSensorsRoomOrder": ("Household layout", "Household room names/order", "Active"),
    "dashboardSpacing": ("Legacy UI preference", "No", "Removal only"),
    "dashboardTextSize": ("Accessibility preference", "No", "Active"),
    "dashboardTheme": ("UI preference", "No", "Active read"),
    "debugMode": ("Legacy UI preference", "No", "Compatibility write"),
    "kotibot.tapo.activeLightSchemes": ("Legacy lighting configuration", "Household lighting state", "Removal only"),
    "kotibot.tapo.lightSchemes": ("Legacy lighting configuration", "Household lighting presets", "Removal only"),
    "kotibot_environment_temperature_unit": ("Legacy UI preference", "No", "Removal only"),
    "previewViewerId": ("Browser viewer identifier", "Pseudonymous personal metadata", "Active"),
}

# Each source-relative entry is: line, current use, PATH-001 disposition.
SOURCE_RELATIVE_PATH_REVIEW = {
    "kotibot_server.py": ((14, "Code and static-asset root", "Retain as installation-code path; never place runtime data below it"),),
    "server_core/preflight.py": ((86, "requirements.txt lookup", "Retain as installation metadata path"),),
    "subsystems/automations/automations_routes.py": ((33, "Tapo module loader", "Retain as installation-code path"),),
    "subsystems/automations/trigger_routes.py": ((32, "Tapo module loader", "Retain as installation-code path"),),
    "subsystems/client-tapo/tapo_control.py": (
        (40, "Camera HLS runtime directory", "Move to OS temporary/cache root in PATH-001C"),
        (44, "Default camera recording directory", "Move to OS media root in PATH-001C"),
    ),
    "subsystems/file-server/file_server_routes.py": ((9, "Operator-provided APK directory", "Move to external package/media root in PATH-001C"),),
    "subsystems/security/kotibot_security.py": ((1684, "Security CLI state/audit base", "Use protected state/audit resolver in PATH-001C"),),
    "tests/test_security_policy.py": ((15, "Test-only repository root", "Test fixture only; no runtime destination"),),
}

RUNTIME_LITERAL_OWNERS = {
    "*.apk": "File server / Android package distribution",
    "<absolute-path-redacted>": "Tapo camera API routes (not filesystem paths)",
    "activity_state.json": "Activities",
    "android_home_state.json": "Android Home client state",
    "automations_state.json": "Automations",
    "camera_hls": "Tapo camera streaming",
    "chip_tool_storage": "Matter controller",
    "chip_tool_subscription_storage": "Matter controller subscriptions",
    "environment_state.json": "Environment",
    "firebase-service-account.json": "Notifications credentials",
    "index.m3u8": "Tapo camera HLS",
    "matter_device_state.json": "Matter device state",
    "matter_state.json": "Matter controller state",
    "notification_queue.jsonl": "Notifications",
    "runtime": "Tapo camera runtime",
    "security_actions.json": "Security actions",
    "security_audit.jsonl": "Security audit",
    "security_state.json": "Authentication and security",
    "server_state.json": "Core registry and server state",
    "tapo_config.json": "Tapo integration configuration",
    "tapo_device_state.json": "Tapo device state",
    "tapo_lighting_state.json": "Tapo lighting and automations",
    "videos": "Video recordings",
}

PERSISTENCE_ACCESS_REVIEW = {
    "*.apk": (
        "subsystems/file-server/file_server_routes.py:apk_files/send_apk/get_app_file",
        "—",
        "Flask serves files placed in get-app by deployment or an operator",
    ),
    "<absolute-path-redacted>": (
        "—",
        "—",
        "Scanner false positive: Tapo camera API URLs, not filesystem paths",
    ),
    "activity_state.json": (
        "subsystems/activities/activity_log.py:KotiBotActivityLog._load_locked",
        "subsystems/activities/activity_log.py:KotiBotActivityLog._save_locked",
        "—",
    ),
    "android_home_state.json": (
        "server_core/state.py:load_state",
        "server_core/state.py:load_state/save_state",
        "—",
    ),
    "automations_state.json": (
        "server_core/state.py:load_state; subsystems/automations/automations_routes.py:read_automation_state/read_tapo_recharge_rules; subsystems/client-tapo/tapo_routes.py:read_tapo_recharge_rules",
        "server_core/state.py:load_state/save_state; subsystems/automations/automations_routes.py:write_automation_state/write_tapo_recharge_rules; subsystems/client-tapo/tapo_routes.py:write_tapo_recharge_rules",
        "—",
    ),
    "camera_hls": (
        "subsystems/client-tapo/tapo_routes.py:api_tapo_camera_hls",
        "subsystems/client-tapo/tapo_control.py:module initialization/start_tapo_camera_stream/stop_tapo_camera_stream/prune_tapo_camera_streams",
        "FFmpeg writes HLS playlists and segments; Flask serves them",
    ),
    "chip_tool_storage": (
        "subsystems/matter/matter_runtime.py:chip_tool_storage_dir/recommission_node",
        "subsystems/matter/matter_runtime.py:chip_tool_storage_dir/recommission_node",
        "chip-tool reads and writes Matter controller/fabric storage",
    ),
    "chip_tool_subscription_storage": (
        "subsystems/matter/matter_runtime.py:chip_tool_subscription_storage_dir",
        "subsystems/matter/matter_runtime.py:chip_tool_subscription_storage_dir/recommission_node",
        "chip-tool reads and writes subscription controller storage",
    ),
    "environment_state.json": (
        "subsystems/environment/environment_routes.py:read_state_unlocked",
        "subsystems/environment/environment_routes.py:write_state_unlocked/ensure_state_file",
        "—",
    ),
    "firebase-service-account.json": (
        "subsystems/notifications/kotibot_push.py:KotiBotPushQueue._fcm_credentials",
        "—",
        "Google Auth loads the credential file",
    ),
    "index.m3u8": (
        "subsystems/client-tapo/tapo_routes.py:api_tapo_camera_hls",
        "—",
        "FFmpeg writes the playlist; Flask serves it",
    ),
    "matter_device_state.json": (
        "server_core/state.py:load_state",
        "server_core/state.py:load_state/save_state",
        "—",
    ),
    "matter_state.json": (
        "subsystems/matter/matter_runtime.py:MatterRuntime.read_state; subsystems/environment/environment_routes.py:matter_state_debug",
        "subsystems/matter/matter_runtime.py:MatterRuntime.write_state",
        "—",
    ),
    "notification_queue.jsonl": (
        "subsystems/notifications/kotibot_push.py:KotiBotPushQueue.recent",
        "subsystems/notifications/kotibot_push.py:KotiBotPushQueue._append_queue_item",
        "—",
    ),
    "runtime": (
        "subsystems/client-tapo/tapo_routes.py:api_tapo_camera_hls",
        "subsystems/client-tapo/tapo_control.py:module initialization/start_tapo_camera_stream/stop_tapo_camera_stream/prune_tapo_camera_streams",
        "FFmpeg writes transient stream files",
    ),
    "security_actions.json": (
        "server_core/state.py:load_state",
        "server_core/state.py:load_state/save_state",
        "—",
    ),
    "security_audit.jsonl": (
        "—",
        "subsystems/security/kotibot_security.py:KotiBotSecurity.audit",
        "Operators or audit tooling may read the rotated log",
    ),
    "security_state.json": (
        "subsystems/security/kotibot_security.py:KotiBotSecurity._load_state",
        "subsystems/security/kotibot_security.py:KotiBotSecurity._save_state",
        "—",
    ),
    "server_state.json": (
        "server_core/state.py:load_state",
        "server_core/state.py:load_state/save_state",
        "—",
    ),
    "tapo_config.json": (
        "kotibot_server.py:tapo_config_enabled",
        "subsystems/client-tapo/tapo_admin_routes.py:tapo_enable/tapo_disable",
        "—",
    ),
    "tapo_device_state.json": (
        "server_core/state.py:load_state",
        "server_core/state.py:load_state/save_state",
        "—",
    ),
    "tapo_lighting_state.json": (
        "subsystems/automations/automations_routes.py:read_lighting_state; subsystems/client-tapo/tapo_routes.py:read_tapo_lighting_state",
        "subsystems/automations/automations_routes.py:write_lighting_state; subsystems/client-tapo/tapo_routes.py:write_tapo_lighting_state",
        "—",
    ),
    "videos": (
        "subsystems/video/video_routes.py:video_file",
        "subsystems/video/video_routes.py:register_video_routes/upload_video; subsystems/client-tapo/tapo_control.py:module initialization/start_tapo_camera_recording/stop_tapo_camera_recording",
        "FFmpeg records and normalizes video files; Flask serves them",
    ),
}

ROUTE_PERSISTED_FIELDS = tuple(
    "enabled from_deviceID from_output trigger threshold threshold_unit "
    "arm_states to_kind action_type to_deviceID to_input targetID "
    "power_action filename sound_volume target_key_deviceID title message "
    "duration_seconds minimum_duration_seconds repeat timer_seconds "
    "repeat_seconds cooldown_seconds auto_off auto_off_seconds retrigger "
    "last_notification_at".split()
)

# Rows contain: object/record, literal fields, optional SOURCE:GROUP, review note.
# Dynamic identifiers are names; the scanner never reads runtime values.
PERSISTED_FIELD_REVIEW = {
    "android_home_state.json": (
        ("root", ("clients",), "", "Writer replaces the root object."),
        ("clients.<deviceID> camera state", (), "server_core/state.py:ANDROID_CAMERA_STATE_KEYS", "Only the declared camera allowlist is written."),
        ("clients.<deviceID> door-sensor state", (), "server_core/state.py:ANDROID_DSS_STATE_KEYS", "Only the declared door-sensor allowlist is written."),
    ),
    "automations_state.json": (
        ("root managed fields", ("tapo_recharge_android_battery", "device_automations", "tapo_day_reset"), "", "Read/modify/write preserves unknown top-level legacy fields."),
        ("tapo_recharge_android_battery.<deviceID>", ("type", "clientName", "enabled", "targetID", "targetDeviceID", "child_id", "child_index", "child_position", "lowBattery", "fullBattery"), "", "Managed fields are listed; migrated legacy fields pass through."),
        ("device_automations[]", ROUTE_PERSISTED_FIELDS, "", "scope is removed; last_notification_at is conditional; loaded legacy fields pass through on save."),
        ("tapo_day_reset", ("type", "enabled", "resetHour", "lastRunDate"), "", "The managed object is normalized to these fields."),
    ),
    "matter_device_state.json": (
        ("root", ("devices",), "", "Writer replaces the root object."),
        ("devices.<deviceID>", (), "server_core/state.py:MATTER_DEVICE_STATE_KEYS", "Only the declared Matter allowlist is written."),
    ),
    "security_actions.json": (
        ("root", ("actions",), "", "Writer replaces the root object."),
        ("actions[]", ROUTE_PERSISTED_FIELDS, "", "scope is removed; last_notification_at is conditional; loaded legacy fields pass through on save."),
    ),
    "server_state.json": (
        ("root", ("clients", "system"), "", "Writer replaces the root object."),
        ("clients group names", ("tapo", "matter", "android_home", "android_key", "unprovisioned", "other"), "", "Each group contains client records."),
        ("clients.tapo[]", (), "server_core/state.py:TAPO_SERVER_STATE_KEYS", "Only the group allowlist is written."),
        ("clients.matter[]", (), "server_core/state.py:MATTER_SERVER_STATE_KEYS", "Only persistent identity and user configuration are written."),
        ("clients.android_home[]", (), "server_core/state.py:ANDROID_HOME_SERVER_STATE_KEYS", "Only the group allowlist is written."),
        ("clients.android_key[]", (), "server_core/state.py:ANDROID_KEY_SERVER_STATE_KEYS", "Only the group allowlist is written."),
        ("clients.unprovisioned[]", (), "server_core/state.py:UNPROVISIONED_SERVER_STATE_KEYS", "Only the group allowlist is written."),
        ("clients.other[]", (), "server_core/state.py:OTHER_SERVER_STATE_KEYS", "Only the group allowlist is written."),
        ("system", ("armed", "arm_state", "armState"), "", "arm_state and armState are both currently written."),
    ),
    "tapo_device_state.json": (
        ("root", ("devices",), "", "Writer replaces the root object."),
        ("devices.<deviceID>", (), "server_core/state.py:TAPO_DEVICE_STATE_KEYS", "Only the declared Tapo allowlist is written."),
        ("devices.<deviceID>.tapo_children[]", ("<all child fields except raw>",), "", "Child dictionaries are copied dynamically after raw is removed."),
    ),
    "tapo_lighting_state.json": (
        ("root", ("schemes", "activeSchemes", "modeConfig"), "", "The Tapo route normalizer writes these root fields."),
        ("schemes.<target>[]", ("favorite", "icon", "label", "mode", "preset", "savedAt"), "", "Targets are home, device:<deviceID>, or room:<deviceID-list>."),
        ("schemes.<target>[].preset managed fields", ("brightness", "colorTemperature", "whiteSaturation", "hue", "saturation"), "", "The preset object passes through, so extension fields can persist."),
        ("activeSchemes.<target>", ("<mode name>",), "", "Dynamic target-to-mode mapping; no nested object fields."),
        ("modeConfig.<mode>.<target>", ("power", "preset"), "", "Values normalize to a choice string or this two-field object."),
    ),
}

PERSISTED_FIELD_REVIEW.update({
    "activity_state.json": (
        ("root", ("events", "last_signatures"), "", "Writer normalizes and replaces the root object."),
        ("events bucket names", ("day_0_previous_24_hours", "day_1_yesterday", "day_2_two_days_ago", "day_3_three_days_ago", "day_4_four_days_ago", "day_5_five_days_ago", "day_6_six_days_ago"), "", "Fixed seven-day bucket set."),
        ("events.<bucket> category names", ("automation", "security", "system", "users"), "", "Fixed category set; kind names below each category are dynamic."),
        ("events.<bucket>.<category>.<kind>[]", ("deviceID", "ts", "state"), "", "Compact event allowlist."),
        ("last_signatures.<dynamic signature>", ("<state signature>",), "", "Dynamic deduplication map; no nested object fields."),
    ),
    "environment_state.json": (
        ("root", ("settings", "weather_cache"), "", "Writer normalizes and replaces the root object."),
        ("settings", ("zip_code", "weather_source", "air_quality_source", "refresh_seconds"), "", "Closed settings allowlist."),
        ("weather_cache", ("ok", "zip_code", "source", "lookup_source", "station_source", "updated_at", "location", "station", "stations_checked", "temperature_f", "humidity_percent", "condition", "timestamp", "icon", "error", "air_quality"), "", "Refresh writes these fields; loaded cache extensions survive until refresh."),
        ("weather_cache.location", ("latitude", "longitude", "city", "state"), "", "ZIP lookup result fields."),
        ("weather_cache.station and stations_checked[]", ("id", "name", "url", "latitude", "longitude", "distance_miles"), "", "NOAA station summary fields."),
        ("weather_cache.air_quality", ("aqi", "label", "parameter", "dominant_pollutant", "pollutants", "reporting_area", "source", "source_id", "timestamp", "updated_at", "error"), "", "AirNow cache fields."),
        ("weather_cache.air_quality.pollutants[]", ("name", "aqi", "label", "timestamp"), "", "AirNow pollutant fields."),
    ),
    "firebase-service-account.json": (
        ("Google service-account document", ("type", "project_id", "private_key_id", "private_key", "client_email", "client_id", "auth_uri", "token_uri", "auth_provider_x509_cert_url", "client_x509_cert_url", "universe_domain"), "", "Externally supplied and validated by Google Auth; KotiBot never writes it and Google-owned extensions may exist."),
    ),
    "matter_state.json": (
        ("root", ("enabled", "chip_tool", "chip_tool_storage", "bypass_attestation", "nodes", "last_command", "settings"), "", "Runtime reconstructs this root before each write."),
        ("settings", ("temperature_unit",), "", "Managed field listed; loaded settings extensions pass through."),
        ("nodes.<node_id> managed fields", ("node_id", "alias", "manufacturer", "model", "source", "notes", "updated_at", "endpoints", "recommissioned_at", "last_inspection", "last_inspection_at", "matter_children", "matter_discovered_at", "matter_discovery"), "", "Loaded node extensions pass through."),
        ("nodes.<node_id>.endpoints[]", ("endpoint", "matter_kind", "matter_kinds", "matter_onoff", "matter_switch_position", "matter_switch_positions", "matter_switch_multipress_max"), "", "Inspection summary fields."),
        ("nodes.<node_id>.matter_children[]", ("endpoint", "kinds", "clusters", "source"), "", "endpoint and kinds are normalized; discovery diagnostic extensions pass through."),
        ("nodes.<node_id>.last_inspection", ("parts_list", "endpoints"), "", "Nested endpoint names and values are dynamic diagnostics."),
        ("nodes.<node_id>.matter_discovery", ("ok", "source", "parts", "parts_reads", "endpoints", "updated_at"), "", "Nested endpoint names and diagnostic fields are dynamic."),
        ("command/diagnostic result", ("ok", "returncode", "command", "stdout", "stderr", "started_at", "finished_at", "parsed", "value"), "", "Shared chip-tool result fields; parsed and value are conditional."),
    ),
    "notification_queue.jsonl": (
        ("each JSONL record", ("ts", "event_type", "deviceID", "title", "body", "data", "status"), "", "data is a caller-provided extension object; the FCM token is not written to the queue."),
    ),
    "security_audit.jsonl": (
        ("each JSONL record", ("ts", "event", "status", "method", "path", "ip", "dashboard_email", "deviceID", "<event-specific fields>"), "", "Request fields are conditional; event-specific fields are bounded and secret-like names are redacted before writing."),
    ),
    "security_state.json": (
        ("root managed fields", ("session_secret", "device_keys", "dashboard_sessions", "device_enrollments", "dashboard_users"), "", "Unknown root extensions pass through; legacy nonces and dashboard login fields are removed during migration."),
        ("dashboard_users.<email>", ("password_hash", "created_at", "updated_at", "status", "session_version"), "", "Dashboard authentication record."),
        ("dashboard_sessions.<session hash>", ("email", "created_at", "last_seen_at", "expires_at", "user_version"), "", "Server-side dashboard session record."),
        ("device_enrollments.<deviceID>", ("token_hash", "issued_at", "expires_at"), "", "Short-lived enrollment record."),
        ("device_keys.<deviceID>", ("current", "previous", "rotated_at"), "", "Current and grace-period key slots."),
        ("device key slot", ("key_id", "secret", "issued_at", "status", "expires_at", "revoked_at"), "", "expires_at and revoked_at are conditional."),
    ),
    "tapo_config.json": (
        ("root", ("enabled",), "", "Enable and disable replace the file with this single field."),
    ),
})


def _git(root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=root,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return completed.stdout


def _dotted_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id

    if isinstance(node, ast.Attribute):
        prefix = _dotted_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr

    return ""


def _literal_string(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _safe_runtime_literal(
    value: str,
    *,
    allow_directory: bool = False,
) -> str | None:
    value = str(value or "").strip()

    if not value or "\n" in value or "\r" in value:
        return None

    if "://" in value:
        return None

    normalized = value.replace("\\", "/")
    path_parts = {part.lower() for part in normalized.split("/") if part}
    is_runtime_file = bool(RUNTIME_FILE_RE.search(normalized))
    is_runtime_directory = bool(
        allow_directory
        and path_parts.intersection(RUNTIME_DIRECTORY_NAMES)
    )

    if not is_runtime_file and not is_runtime_directory:
        return None

    if Path(value).is_absolute():
        return "<absolute-path-redacted>"

    return normalized


class PythonInventory(ast.NodeVisitor):
    def __init__(self, source_path: str) -> None:
        self.source_path = source_path
        self.environment_names: dict[str, set[str]] = defaultdict(set)
        self.runtime_literals: dict[str, set[str]] = defaultdict(set)
        self.operations: list[tuple[str, int, str]] = []
        self.candidate_keys: set[str] = set()
        self.schema_keys: dict[str, set[str]] = defaultdict(set)
        self.string_groups: dict[str, tuple[str, ...]] = {}
        self.source_relative_lines: set[int] = set()

    def _location(self, node: ast.AST) -> str:
        return f"{self.source_path}:{getattr(node, 'lineno', 0)}"

    def visit_Name(self, node: ast.Name) -> None:
        if node.id == "__file__":
            self.source_relative_lines.add(node.lineno)
        self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant) -> None:
        if isinstance(node.value, str):
            candidate = _safe_runtime_literal(node.value)

            if candidate:
                self.runtime_literals[candidate].add(
                    self._location(node)
                )
        self.generic_visit(node)

    def visit_BinOp(self, node: ast.BinOp) -> None:
        if isinstance(node.op, ast.Div):
            for child in ast.walk(node):
                value = _literal_string(child)

                if value is None:
                    continue

                candidate = _safe_runtime_literal(
                    value,
                    allow_directory=True,
                )

                if candidate:
                    self.runtime_literals[candidate].add(
                        self._location(child)
                    )

        self.generic_visit(node)

    def visit_Dict(self, node: ast.Dict) -> None:
        for key in node.keys:
            value = _literal_string(key)
            if value:
                self.candidate_keys.add(value)
        self.generic_visit(node)

    def visit_Subscript(self, node: ast.Subscript) -> None:
        value = _literal_string(node.slice)
        if value:
            self.candidate_keys.add(value)
        self.generic_visit(node)

    def _string_group(self, node: ast.AST) -> tuple[str, ...] | None:
        value = _literal_string(node)

        if value is not None:
            return (value,)

        if isinstance(node, ast.Name):
            return self.string_groups.get(node.id)

        if isinstance(node, (ast.List, ast.Set, ast.Tuple)):
            values = []

            for item in node.elts:
                group = self._string_group(item)

                if group is None:
                    return None

                values.extend(group)

            return tuple(values)

        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            left = self._string_group(node.left)
            right = self._string_group(node.right)

            if left is not None and right is not None:
                return left + right

        return None

    def visit_Assign(self, node: ast.Assign) -> None:
        names = [
            target.id
            for target in node.targets
            if isinstance(target, ast.Name)
        ]

        for name in names:
            if "STATE_KEYS" not in name and not name.endswith("_KEYS"):
                continue

            values = self._string_group(node.value)

            if values is None:
                continue

            self.string_groups[name] = values
            self.schema_keys[name].update(values)

        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        dotted = _dotted_name(node.func)
        short_name = dotted.rsplit(".", 1)[-1]
        first = _literal_string(node.args[0]) if node.args else None

        if first and short_name in {"Path", "with_name", "with_suffix"}:
            candidate = _safe_runtime_literal(
                first,
                allow_directory=True,
            )

            if candidate:
                self.runtime_literals[candidate].add(
                    self._location(node)
                )

        if dotted in {"os.environ.get", "os.getenv"}:
            if first and ENV_NAME_RE.fullmatch(first):
                self.environment_names[first].add(self._location(node))
        elif short_name in ENV_HELPERS:
            if first and ENV_NAME_RE.fullmatch(first):
                self.environment_names[first].add(self._location(node))

        if short_name in {"get", "pop", "setdefault"} and first:
            self.candidate_keys.add(first)

        read = short_name in READ_CALLS
        write = short_name in WRITE_CALLS

        if read or write:
            operation = "read/write" if read and write else (
                "read" if read else "write"
            )
            self.operations.append((operation, node.lineno, dotted))

        self.generic_visit(node)


def _tracked_files(root: Path) -> list[str]:
    output = _git(root, "ls-files", "-z")
    return sorted(path for path in output.split("\0") if path)


def _markdown_cell(value: str) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def _join_locations(locations: set[str]) -> str:
    return ", ".join(f"`{item}`" for item in sorted(locations))


def _join_field_names(fields: tuple[str, ...] | set[str]) -> str:
    return ", ".join(
        f"`{_markdown_cell(field)}`"
        for field in fields
    )


def build_inventory(root: Path) -> str:
    tracked = _tracked_files(root)
    environment_names: dict[str, set[str]] = defaultdict(set)
    runtime_literals: dict[str, set[str]] = defaultdict(set)
    operations: list[tuple[str, int, str, str]] = []
    candidate_keys: dict[str, set[str]] = defaultdict(set)
    schema_keys: dict[str, dict[str, set[str]]] = defaultdict(dict)
    source_relative: dict[str, set[int]] = defaultdict(set)
    browser_storage: list[tuple[str, str, str, int]] = []

    for relative in tracked:
        if relative == SCANNER_PATH:
            continue

        path = root / relative

        if path.suffix.lower() not in TEXT_SOURCE_SUFFIXES:
            continue

        try:
            text = path.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeError):
            continue

        for line_number, line in enumerate(text.splitlines(), 1):
            for match in BROWSER_STORAGE_RE.finditer(line):
                browser_storage.append((
                    match.group(1),
                    match.group(4),
                    relative,
                    line_number,
                ))

            for match in INDEXED_DB_RE.finditer(line):
                browser_storage.append((
                    "indexedDB",
                    match.group(2),
                    relative,
                    line_number,
                ))

        if path.suffix.lower() != PYTHON_SUFFIX:
            continue

        try:
            tree = ast.parse(text, filename=relative)
        except SyntaxError:
            continue

        visitor = PythonInventory(relative)
        visitor.visit(tree)

        for name, locations in visitor.environment_names.items():
            environment_names[name].update(locations)

        for literal, locations in visitor.runtime_literals.items():
            runtime_literals[literal].update(locations)

        operations.extend(
            (relative, line, operation, call)
            for operation, line, call in visitor.operations
        )

        if visitor.operations or visitor.runtime_literals:
            candidate_keys[relative].update(visitor.candidate_keys)

        if visitor.schema_keys:
            schema_keys[relative] = visitor.schema_keys

        if visitor.source_relative_lines:
            source_relative[relative].update(
                visitor.source_relative_lines
            )

    for name, (source, note) in DYNAMIC_ENVIRONMENT_NAMES.items():
        environment_names[name].add(f"{source} ({note})")

    browser_storage.extend(DYNAMIC_BROWSER_STORAGE_NAMES)

    unowned_runtime_literals = sorted(
        set(runtime_literals) - set(RUNTIME_LITERAL_OWNERS)
    )

    unreviewed_persistence_literals = sorted(
        set(runtime_literals) - set(PERSISTENCE_ACCESS_REVIEW)
    )

    if unowned_runtime_literals:
        rendered = ", ".join(unowned_runtime_literals)
        raise RuntimeError(
            f"runtime literals require owner review: {rendered}"
        )

    if unreviewed_persistence_literals:
        rendered = ", ".join(unreviewed_persistence_literals)
        raise RuntimeError(
            f"runtime literals require persistence review: {rendered}"
        )

    json_persistence_literals = {
        literal
        for literal in runtime_literals
        if re.search(r"\.jsonl?$", literal, re.IGNORECASE)
    }
    missing_field_review_files = sorted(
        json_persistence_literals - set(PERSISTED_FIELD_REVIEW)
    )
    stale_field_review_files = sorted(
        set(PERSISTED_FIELD_REVIEW) - json_persistence_literals
    )

    if missing_field_review_files or stale_field_review_files:
        missing = ", ".join(missing_field_review_files) or "none"
        stale = ", ".join(stale_field_review_files) or "none"
        raise RuntimeError(
            "persisted-field review mismatch: "
            f"missing={missing}; stale={stale}"
        )

    missing_schema_groups = []

    for rows in PERSISTED_FIELD_REVIEW.values():
        for _record, _fields, schema_reference, _note in rows:
            if not schema_reference:
                continue

            source, group = schema_reference.rsplit(":", 1)

            if group not in schema_keys.get(source, {}):
                missing_schema_groups.append(schema_reference)

    if missing_schema_groups:
        rendered = ", ".join(sorted(set(missing_schema_groups)))
        raise RuntimeError(
            f"persisted-field review groups missing from source: {rendered}"
        )

    detected_browser_names = {item[1] for item in browser_storage}
    missing_browser_reviews = sorted(
        detected_browser_names - set(BROWSER_STORAGE_REVIEW)
    )
    stale_browser_reviews = sorted(
        set(BROWSER_STORAGE_REVIEW) - detected_browser_names
    )

    if missing_browser_reviews or stale_browser_reviews:
        missing = ", ".join(missing_browser_reviews) or "none"
        stale = ", ".join(stale_browser_reviews) or "none"
        raise RuntimeError(
            f"browser storage review mismatch: missing={missing}; stale={stale}"
        )

    stale_dynamic_browser_sources = []

    for _storage, key, source, line in DYNAMIC_BROWSER_STORAGE_NAMES:
        source_lines = (root / source).read_text(
            encoding="utf-8-sig"
        ).splitlines()

        if line < 1 or line > len(source_lines) or key not in source_lines[line - 1]:
            stale_dynamic_browser_sources.append(f"{source}:{line}:{key}")

    if stale_dynamic_browser_sources:
        rendered = ", ".join(stale_dynamic_browser_sources)
        raise RuntimeError(
            f"dynamic browser storage sources require review: {rendered}"
        )

    detected_source_relative = {
        (source, line)
        for source, line_numbers in source_relative.items()
        for line in line_numbers
    }
    reviewed_source_relative = {
        (source, line)
        for source, rows in SOURCE_RELATIVE_PATH_REVIEW.items()
        for line, _use, _disposition in rows
    }

    if detected_source_relative != reviewed_source_relative:
        missing = sorted(detected_source_relative - reviewed_source_relative)
        stale = sorted(reviewed_source_relative - detected_source_relative)
        raise RuntimeError(
            "source-relative PATH-001 review mismatch: "
            f"missing={missing or 'none'}; stale={stale or 'none'}"
        )

    ignored_patterns = []
    gitignore = root / ".gitignore"

    if gitignore.exists():
        ignored_patterns = [
            line.strip()
            for line in gitignore.read_text(
                encoding="utf-8-sig"
            ).splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]

    head = _git(root, "rev-parse", "HEAD").strip()
    lines = [
        "# SEC-001A — Repository and source inventory",
        "",
        f"Source commit at scan time: `{head}`",
        "",
        "## Safety boundary",
        "",
        "This report was generated from tracked source code, tracked path names, "
        "and `.gitignore` patterns only. The scanner did not open runtime JSON, "
        "JSONL, environment files, credentials, databases, logs, media, archives, "
        "Matter controller storage, or virtual-environment files.",
        "",
        "All entries below are names and repository-relative source locations. "
        "Broad candidate lists are retained as supporting evidence; the reviewed "
        "tables are authoritative.",
        "",
        "## Tracked runtime-looking paths",
        "",
    ]

    tracked_runtime = [
        path for path in tracked if TRACKED_RUNTIME_RE.search(path)
    ]

    if tracked_runtime:
        lines.extend(f"- `{path}`" for path in tracked_runtime)
    else:
        lines.append("- None detected by filename.")

    lines.extend([
        "",
        "## Ignored path patterns",
        "",
    ])
    lines.extend(f"- `{pattern}`" for pattern in ignored_patterns)

    lines.extend([
        "",
        "## Runtime path literals declared in source",
        "",
        "| Path or pattern name | Reviewed owner | Source locations |",
        "| --- | --- | --- |",
    ])

    for literal, locations in sorted(runtime_literals.items()):
        lines.append(
            f"| `{_markdown_cell(literal)}` | "
            f"{_markdown_cell(RUNTIME_LITERAL_OWNERS[literal])} | "
            f"{_join_locations(locations)} |"
        )

    lines.extend([
        "",
        "## Source-relative paths carried into PATH-001",
        "",
        "| Source location | Current use | PATH-001 disposition |",
        "| --- | --- | --- |",
    ])

    for source, rows in sorted(SOURCE_RELATIVE_PATH_REVIEW.items()):
        for line, current_use, disposition in rows:
            lines.append(
                f"| `{source}:{line}` | "
                f"{_markdown_cell(current_use)} | "
                f"{_markdown_cell(disposition)} |"
            )

    lines.extend([
        "",
        "## Environment-variable names",
        "",
        "| Variable name | Source locations |",
        "| --- | --- |",
    ])

    for name, locations in sorted(environment_names.items()):
        lines.append(f"| `{name}` | {_join_locations(locations)} |")

    lines.extend([
        "",
        "## Reviewed persistent storage readers and writers",
        "",
        "This table reconciles repository call sites with indirect access by "
        "libraries, subprocesses, deployment, and operators. A dash means no "
        "reader, writer, or indirect accessor was found in that category.",
        "",
        "| Path or pattern | Reviewed readers | Reviewed writers | Indirect/external access |",
        "| --- | --- | --- | --- |",
    ])

    for literal in sorted(runtime_literals):
        readers, writers, indirect = PERSISTENCE_ACCESS_REVIEW[literal]
        lines.append(
            f"| `{_markdown_cell(literal)}` | "
            f"{_markdown_cell(readers)} | "
            f"{_markdown_cell(writers)} | "
            f"{_markdown_cell(indirect)} |"
        )

    lines.extend([
        "",
        "## Reviewed persisted fields",
        "",
        "This SEC-001A.2.2 table replaces broad candidate keys with fields "
        "confirmed at each writer or external schema boundary. It records names "
        "only and explicitly identifies dynamic or pass-through fields.",
        "",
        "| File | Object or record | Fields actually persisted | Source review note |",
        "| --- | --- | --- | --- |",
    ])

    for literal, rows in sorted(PERSISTED_FIELD_REVIEW.items()):
        for record, literal_fields, schema_reference, note in rows:
            fields = literal_fields
            source_note = note

            if schema_reference:
                source, group = schema_reference.rsplit(":", 1)
                fields = tuple(sorted(schema_keys[source][group]))
                source_note = f"{note} Declared by {schema_reference}."

            lines.append(
                f"| `{_markdown_cell(literal)}` | "
                f"`{_markdown_cell(record)}` | "
                f"{_join_field_names(fields)} | "
                f"{_markdown_cell(source_note)} |"
            )

    lines.extend([
        "",
        "## Candidate persistence-related source operations",
        "",
        "This deliberately broad scanner output is retained as supporting "
        "evidence. It includes non-persistence calls such as string replacement "
        "and JSON response serialization; the reviewed table above is authoritative.",
        "",
        "| Source location | Operation | Call |",
        "| --- | --- | --- |",
    ])

    for source, line, operation, call in sorted(operations):
        lines.append(
            f"| `{source}:{line}` | {operation} | `{call}` |"
        )

    lines.extend([
        "",
        "## Declared state-key groups",
        "",
    ])

    for source, groups in sorted(schema_keys.items()):
        lines.append(f"### `{source}`")
        lines.append("")

        for group, keys in sorted(groups.items()):
            rendered = ", ".join(f"`{key}`" for key in sorted(keys))
            lines.append(f"- `{group}`: {rendered or 'No literal keys.'}")

        lines.append("")

    lines.extend([
        "## Candidate persisted key names by source file",
        "",
        "This deliberately broad static list is retained as supporting evidence. "
        "It includes API-only and in-memory-only names; the reviewed persisted-"
        "fields table above is authoritative.",
        "",
    ])

    for source, keys in sorted(candidate_keys.items()):
        rendered = ", ".join(f"`{key}`" for key in sorted(keys))
        lines.append(f"### `{source}`")
        lines.append("")
        lines.append(rendered or "No literal candidate keys.")
        lines.append("")

    lines.extend([
        "## Reviewed browser storage classification",
        "",
        "| Storage | Key/database name | Data class | Household/personal data | Lifecycle | Source locations |",
        "| --- | --- | --- | --- | --- | --- |",
    ])

    if browser_storage:
        storage_locations: dict[tuple[str, str], set[str]] = defaultdict(set)

        for storage, key, source, line in set(browser_storage):
            storage_locations[(storage, key)].add(f"{source}:{line}")

        for (storage, key), locations in sorted(storage_locations.items()):
            data_class, privacy_class, lifecycle = BROWSER_STORAGE_REVIEW[key]
            lines.append(
                f"| `{storage}` | `{_markdown_cell(key)}` | "
                f"{_markdown_cell(data_class)} | "
                f"{_markdown_cell(privacy_class)} | "
                f"{_markdown_cell(lifecycle)} | "
                f"{_join_locations(locations)} |"
            )
    else:
        lines.append("| — | None detected | — | — | — | — |")

    review_complete = head == SEC001A_REVIEWED_SOURCE_COMMIT
    marker = "c" if review_complete else " "

    lines.extend([
        "",
        "## SEC-001A review gate",
        "",
        f"Manual value-free source review recorded for `{SEC001A_REVIEWED_SOURCE_COMMIT}`. "
        "The report contains names and source locations only; no runtime values "
        "or personal-data values were read.",
        "",
        "- [c] Every runtime path literal is assigned to an owning subsystem.",
        "- [c] Every direct and indirect source reader/writer is reconciled.",
        f"- [{marker}] Candidate JSON/JSONL keys are reduced to keys actually persisted.",
        f"- [{marker}] Browser storage names are classified for household/personal data.",
        f"- [{marker}] Every source-relative runtime path is carried into PATH-001.",
        f"- [{marker}] The report is manually confirmed to contain no values or personal-data values.",
        "",
    ])

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Generate a value-free SEC-001A repository/source inventory."
        )
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"output path relative to the repository (default: {DEFAULT_OUTPUT})",
    )
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    output = args.output

    if not output.is_absolute():
        output = root / output

    output = output.resolve()

    try:
        output.relative_to(root)
    except ValueError as exc:
        raise SystemExit("output must remain inside the repository") from exc

    report = build_inventory(root)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(report, encoding="utf-8", newline="\n")
    print(output.relative_to(root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

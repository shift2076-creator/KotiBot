# SEC-001A — Repository and source inventory

Source commit at scan time: `4a64a3f0712e84489428e6dd7cee08f57edc9735`

## Safety boundary

This report was generated from tracked source code, tracked path names, and `.gitignore` patterns only. The scanner did not open runtime JSON, JSONL, environment files, credentials, databases, logs, media, archives, Matter controller storage, or virtual-environment files.

All entries below are names and repository-relative source locations. Candidate lists require human review before SEC-001A is checked off.

## Tracked runtime-looking paths

- `subsystems/activities/.activity_state.json.1729725.547546372928.1784905069770990818.tmp`
- `subsystems/security/security_audit.jsonl.1`

## Ignored path patterns

- `__pycache__/`
- `*.py[cod]`
- `.pytest_cache/`
- `.mypy_cache/`
- `.ruff_cache/`
- `.venv/`
- `venv/`
- `env/`
- `server_state.json`
- `**/server_state.json`
- `**/security_actions.json`
- `**/automations_state.json`
- `**/tapo_lighting_state.json`
- `*.pid`
- `*.log`
- `logs/`
- `runtime/`
- `temp/`
- `tmp/`
- `.Trash-*/`
- `*.swp`
- `*~`
- `.env`
- `.env.*`
- `!.env.example`
- `*.pem`
- `*.key`
- `*.p12`
- `*.pfx`
- `credentials*.json`
- `secrets*.json`
- `recordings/`
- `static/recordings/`
- `static/hls/`
- `static/cache/`
- `.gradle/`
- `**/build/`
- `local.properties`
- `.idea/`
- `.vscode/`
- `.DS_Store`
- `Thumbs.db`
- `subsystems/notifications/firebase-service-account.json`
- `subsystems/security/security_state.json`
- `*.json`
- `*.ufo`
- `*.ufo/`
- `subsystems/matter/chip_tool_storage/`
- `subsystems/matter/chip_tool_subscription_storage/`
- `*.psd`
- `*.bak`
- `*.bak.*`
- `*.jsonl`
- `*.apk`
- `subsystems/video/videos/`
- `static/img/favicons/FLASK_ROUTES.txt`
- `static/img/favicons/HEAD_SNIPPET.txt`

## Runtime path literals declared in source

| Path or pattern name | Reviewed owner | Source locations |
| --- | --- | --- |
| `*.apk` | File server / Android package distribution | `subsystems/file-server/file_server_routes.py:14` |
| `<absolute-path-redacted>` | Tapo camera API routes (not filesystem paths) | `server_core/status.py:331`, `subsystems/client-tapo/tapo_control.py:358`, `subsystems/client-tapo/tapo_control.py:417`, `subsystems/client-tapo/tapo_routes.py:2771` |
| `activity_state.json` | Activities | `server_core/subsystems.py:99` |
| `android_home_state.json` | Android Home client state | `kotibot_server.py:116` |
| `automations_state.json` | Automations | `server_core/paths.py:80` |
| `camera_hls` | Tapo camera streaming | `subsystems/client-tapo/tapo_control.py:41` |
| `chip_tool_storage` | Matter controller | `subsystems/matter/matter_runtime.py:587` |
| `chip_tool_subscription_storage` | Matter controller subscriptions | `subsystems/matter/matter_runtime.py:592`, `subsystems/matter/matter_runtime.py:916` |
| `environment_state.json` | Environment | `subsystems/environment/environment_routes.py:80` |
| `firebase-service-account.json` | Notifications credentials | `kotibot_server.py:118`, `subsystems/notifications/kotibot_push.py:31` |
| `index.m3u8` | Tapo camera HLS | `subsystems/client-tapo/tapo_control.py:379`, `subsystems/client-tapo/tapo_routes.py:3013` |
| `matter_device_state.json` | Matter device state | `kotibot_server.py:115` |
| `matter_state.json` | Matter controller state | `subsystems/environment/environment_routes.py:81`, `subsystems/matter/matter_runtime.py:568` |
| `notification_queue.jsonl` | Notifications | `subsystems/notifications/kotibot_push.py:28` |
| `runtime` | Tapo camera runtime | `subsystems/client-tapo/tapo_control.py:40` |
| `security_actions.json` | Security actions | `server_core/paths.py:76` |
| `security_audit.jsonl` | Security audit | `subsystems/security/kotibot_security.py:206` |
| `security_state.json` | Authentication and security | `kotibot_server.py:119`, `subsystems/security/kotibot_security.py:205` |
| `server_state.json` | Core registry and server state | `server_core/paths.py:68` |
| `tapo_config.json` | Tapo integration configuration | `kotibot_server.py:93` |
| `tapo_device_state.json` | Tapo device state | `kotibot_server.py:114` |
| `tapo_lighting_state.json` | Tapo lighting and automations | `server_core/paths.py:88` |
| `videos` | Video recordings | `subsystems/client-tapo/tapo_control.py:44`, `subsystems/video/video_routes.py:11` |

## Source-relative path construction

| Source file | `__file__` lines |
| --- | --- |
| `kotibot_server.py` | 14 |
| `server_core/preflight.py` | 86 |
| `subsystems/automations/automations_routes.py` | 33 |
| `subsystems/automations/trigger_routes.py` | 32 |
| `subsystems/client-tapo/tapo_control.py` | 40, 44 |
| `subsystems/file-server/file_server_routes.py` | 9 |
| `subsystems/security/kotibot_security.py` | 1684 |
| `tests/test_security_policy.py` | 15 |

## Environment-variable names

| Variable name | Source locations |
| --- | --- |
| `KOTIBOT_ALLOWED_ORIGINS` | `subsystems/security/kotibot_security.py:1655` |
| `KOTIBOT_AUTOMATIONS_SECONDS` | `subsystems/automations/automations_routes.py:1186` |
| `KOTIBOT_CAMERA_TALK_CONNECTED_TTL_SECONDS` | `subsystems/voice/voice_routes.py:12` |
| `KOTIBOT_CAMERA_TALK_DISABLE_DEFAULT_STUN` | `subsystems/voice/voice_routes.py:129` |
| `KOTIBOT_CAMERA_TALK_ENDED_TTL_SECONDS` | `subsystems/voice/voice_routes.py:13` |
| `KOTIBOT_CAMERA_TALK_ICE_SERVERS` | `subsystems/voice/voice_routes.py:98` |
| `KOTIBOT_CAMERA_TALK_PENDING_ACTIVE_POLL_MS` | `subsystems/voice/voice_routes.py:15` |
| `KOTIBOT_CAMERA_TALK_PENDING_IDLE_POLL_MS` | `subsystems/voice/voice_routes.py:14` |
| `KOTIBOT_CAMERA_TALK_PENDING_TTL_SECONDS` | `subsystems/voice/voice_routes.py:11` |
| `KOTIBOT_CAMERA_TALK_STUN_URLS` | `subsystems/voice/voice_routes.py:117` |
| `KOTIBOT_CAMERA_TALK_TURN_CREDENTIAL` | `subsystems/voice/voice_routes.py:138` |
| `KOTIBOT_CAMERA_TALK_TURN_URLS` | `subsystems/voice/voice_routes.py:125` |
| `KOTIBOT_CAMERA_TALK_TURN_USERNAME` | `subsystems/voice/voice_routes.py:137` |
| `KOTIBOT_CLOUDFLARE_API_TOKEN` | `subsystems/network/external_ip.py:25`, `subsystems/network/external_ip.py:74` |
| `KOTIBOT_CLOUDFLARE_PROXIED` | `subsystems/network/external_ip.py:135` |
| `KOTIBOT_CLOUDFLARE_RECORD_ID` | `subsystems/network/external_ip.py:105` |
| `KOTIBOT_CLOUDFLARE_RECORD_TYPE` | `subsystems/network/external_ip.py:106`, `subsystems/network/external_ip.py:142`, `subsystems/network/external_ip.py:42` |
| `KOTIBOT_CLOUDFLARE_ZONE_ID` | `subsystems/network/external_ip.py:104`, `subsystems/network/external_ip.py:134`, `subsystems/network/external_ip.py:26` |
| `KOTIBOT_COOKIE_SECURE` | `subsystems/security/kotibot_security.py:92` |
| `KOTIBOT_DASHBOARD_EMAIL` | `subsystems/security/kotibot_security.py:1750`, `subsystems/security/kotibot_security.py:1770` |
| `KOTIBOT_DASHBOARD_PASSWORD` | `subsystems/security/kotibot_security.py:1695` |
| `KOTIBOT_DATA_DIR` | `server_core/paths.py:15` |
| `KOTIBOT_DEV_STATIC_NO_CACHE` | `kotibot_server.py:132` |
| `KOTIBOT_EXTERNAL_IP_CHECK_SECONDS` | `subsystems/network/external_ip.py:183` |
| `KOTIBOT_EXTERNAL_IP_ENABLED` | `subsystems/network/external_ip.py:176`, `subsystems/network/external_ip.py:24` |
| `KOTIBOT_JSON_FLUSH_SECONDS` | `server_core/io.py:13` |
| `KOTIBOT_MATTER_BYPASS_ATTESTATION` | `subsystems/matter/matter_runtime.py:624` |
| `KOTIBOT_MATTER_CHIP_TOOL` | `subsystems/matter/matter_runtime.py:574`, `subsystems/matter/matter_runtime.py:667` |
| `KOTIBOT_MATTER_DISCOVERY_TTL_SECONDS` | `subsystems/matter/matter_runtime.py:1032` |
| `KOTIBOT_MATTER_SENSOR_SUBSCRIBE_ENABLED` | `subsystems/matter/matter_routes.py (dynamic environment prefix)` |
| `KOTIBOT_MATTER_SENSOR_SUBSCRIBE_INITIAL_DELAY_SECONDS` | `subsystems/matter/matter_routes.py (dynamic environment prefix)` |
| `KOTIBOT_MATTER_SENSOR_SUBSCRIBE_MAX_SECONDS` | `subsystems/matter/matter_routes.py (dynamic environment prefix)` |
| `KOTIBOT_MATTER_SENSOR_SUBSCRIBE_MIN_SECONDS` | `subsystems/matter/matter_routes.py (dynamic environment prefix)` |
| `KOTIBOT_MATTER_SENSOR_SUBSCRIBE_RETRY_SECONDS` | `subsystems/matter/matter_routes.py (dynamic environment prefix)` |
| `KOTIBOT_MATTER_SYNC_ENABLED` | `subsystems/matter/matter_routes.py:1083` |
| `KOTIBOT_MATTER_SYNC_INITIAL_DELAY_SECONDS` | `subsystems/matter/matter_routes.py:1087` |
| `KOTIBOT_NOAA_USER_AGENT` | `subsystems/environment/environment_routes.py:161`, `subsystems/environment/environment_routes.py:175` |
| `KOTIBOT_PREVIEW_VIEWER_TTL_SECONDS` | `kotibot_server.py:146` |
| `KOTIBOT_PUBLIC_HOSTNAME` | `subsystems/network/external_ip.py:133` |
| `KOTIBOT_SECURITY` | `subsystems/security/kotibot_security.py:1646` |
| `KOTIBOT_TAPO_COMMAND_WORKERS` | `subsystems/client-tapo/tapo_routes.py:74` |
| `KOTIBOT_TAPO_DISCOVERY_SECONDS` | `subsystems/client-tapo/tapo_routes.py:78` |
| `KOTIBOT_TAPO_ENABLED` | `kotibot_server.py:97` |
| `KOTIBOT_TAPO_ENERGY_SECONDS` | `subsystems/client-tapo/tapo_energy.py:15` |
| `KOTIBOT_TAPO_ENERGY_TIMEOUT_SECONDS` | `subsystems/client-tapo/tapo_energy.py:19` |
| `KOTIBOT_TAPO_RECORDING_DIR` | `subsystems/client-tapo/tapo_control.py:42` |
| `KOTIBOT_TAPO_WATCHER_SECONDS` | `subsystems/client-tapo/tapo_routes.py:75` |
| `KOTIBOT_TRUSTED_PROXY_CIDRS` | `subsystems/security/kotibot_security.py:1652` |
| `LOCALAPPDATA` | `server_core/paths.py:32` |
| `TAPO_CACHE_SECONDS` | `subsystems/client-tapo/tapo_control.py:32` |
| `TAPO_CAMERA_PASSWORD` | `subsystems/client-tapo/tapo_control.py:133` |
| `TAPO_CAMERA_RTSP_PATH` | `subsystems/client-tapo/tapo_control.py:134` |
| `TAPO_CAMERA_USERNAME` | `subsystems/client-tapo/tapo_control.py:132` |
| `TAPO_DEVICE_CALL_TIMEOUT_SECONDS` | `subsystems/client-tapo/tapo_control.py:34` |
| `TAPO_DEVICE_CONNECT_TIMEOUT_SECONDS` | `subsystems/client-tapo/tapo_control.py:33` |
| `TAPO_DEVICE_REFRESH_TIMEOUT_SECONDS` | `subsystems/client-tapo/tapo_control.py:35` |
| `TAPO_PASSWORD` | `subsystems/client-tapo/tapo_control.py:31` |
| `TAPO_USERNAME` | `subsystems/client-tapo/tapo_control.py:30` |
| `XDG_DATA_HOME` | `server_core/paths.py:41` |

## Reviewed persistent storage readers and writers

This table reconciles repository call sites with indirect access by libraries, subprocesses, deployment, and operators. A dash means no reader, writer, or indirect accessor was found in that category.

| Path or pattern | Reviewed readers | Reviewed writers | Indirect/external access |
| --- | --- | --- | --- |
| `*.apk` | subsystems/file-server/file_server_routes.py:apk_files/send_apk/get_app_file | — | Flask serves files placed in get-app by deployment or an operator |
| `<absolute-path-redacted>` | — | — | Scanner false positive: Tapo camera API URLs, not filesystem paths |
| `activity_state.json` | subsystems/activities/activity_log.py:KotiBotActivityLog._load_locked | subsystems/activities/activity_log.py:KotiBotActivityLog._save_locked | — |
| `android_home_state.json` | server_core/state.py:load_state | server_core/state.py:load_state/save_state | — |
| `automations_state.json` | server_core/state.py:load_state; subsystems/automations/automations_routes.py:read_automation_state/read_tapo_recharge_rules; subsystems/client-tapo/tapo_routes.py:read_tapo_recharge_rules | server_core/state.py:load_state/save_state; subsystems/automations/automations_routes.py:write_automation_state/write_tapo_recharge_rules; subsystems/client-tapo/tapo_routes.py:write_tapo_recharge_rules | — |
| `camera_hls` | subsystems/client-tapo/tapo_routes.py:api_tapo_camera_hls | subsystems/client-tapo/tapo_control.py:module initialization/start_tapo_camera_stream/stop_tapo_camera_stream/prune_tapo_camera_streams | FFmpeg writes HLS playlists and segments; Flask serves them |
| `chip_tool_storage` | subsystems/matter/matter_runtime.py:chip_tool_storage_dir/recommission_node | subsystems/matter/matter_runtime.py:chip_tool_storage_dir/recommission_node | chip-tool reads and writes Matter controller/fabric storage |
| `chip_tool_subscription_storage` | subsystems/matter/matter_runtime.py:chip_tool_subscription_storage_dir | subsystems/matter/matter_runtime.py:chip_tool_subscription_storage_dir/recommission_node | chip-tool reads and writes subscription controller storage |
| `environment_state.json` | subsystems/environment/environment_routes.py:read_state_unlocked | subsystems/environment/environment_routes.py:write_state_unlocked/ensure_state_file | — |
| `firebase-service-account.json` | subsystems/notifications/kotibot_push.py:KotiBotPushQueue._fcm_credentials | — | Google Auth loads the credential file |
| `index.m3u8` | subsystems/client-tapo/tapo_routes.py:api_tapo_camera_hls | — | FFmpeg writes the playlist; Flask serves it |
| `matter_device_state.json` | server_core/state.py:load_state | server_core/state.py:load_state/save_state | — |
| `matter_state.json` | subsystems/matter/matter_runtime.py:MatterRuntime.read_state; subsystems/environment/environment_routes.py:matter_state_debug | subsystems/matter/matter_runtime.py:MatterRuntime.write_state | — |
| `notification_queue.jsonl` | subsystems/notifications/kotibot_push.py:KotiBotPushQueue.recent | subsystems/notifications/kotibot_push.py:KotiBotPushQueue._append_queue_item | — |
| `runtime` | subsystems/client-tapo/tapo_routes.py:api_tapo_camera_hls | subsystems/client-tapo/tapo_control.py:module initialization/start_tapo_camera_stream/stop_tapo_camera_stream/prune_tapo_camera_streams | FFmpeg writes transient stream files |
| `security_actions.json` | server_core/state.py:load_state | server_core/state.py:load_state/save_state | — |
| `security_audit.jsonl` | — | subsystems/security/kotibot_security.py:KotiBotSecurity.audit | Operators or audit tooling may read the rotated log |
| `security_state.json` | subsystems/security/kotibot_security.py:KotiBotSecurity._load_state | subsystems/security/kotibot_security.py:KotiBotSecurity._save_state | — |
| `server_state.json` | server_core/state.py:load_state | server_core/state.py:load_state/save_state | — |
| `tapo_config.json` | kotibot_server.py:tapo_config_enabled | subsystems/client-tapo/tapo_admin_routes.py:tapo_enable/tapo_disable | — |
| `tapo_device_state.json` | server_core/state.py:load_state | server_core/state.py:load_state/save_state | — |
| `tapo_lighting_state.json` | subsystems/automations/automations_routes.py:read_lighting_state; subsystems/client-tapo/tapo_routes.py:read_tapo_lighting_state | subsystems/automations/automations_routes.py:write_lighting_state; subsystems/client-tapo/tapo_routes.py:write_tapo_lighting_state | — |
| `videos` | subsystems/video/video_routes.py:video_file | subsystems/video/video_routes.py:register_video_routes/upload_video; subsystems/client-tapo/tapo_control.py:module initialization/start_tapo_camera_recording/stop_tapo_camera_recording | FFmpeg records and normalizes video files; Flask serves them |

## Reviewed persisted fields — core and device state

This SEC-001A.2.2.1 table replaces broad candidate keys with fields confirmed at the writers for the core registry, automation/security actions, lighting state, and three device snapshots. It records names only. Remaining persistence files stay open for SEC-001A.2.2.2.

| File | Object or record | Fields actually persisted | Source review note |
| --- | --- | --- | --- |
| `android_home_state.json` | `root` | `clients` | Writer replaces the root object. |
| `android_home_state.json` | `clients.<deviceID> camera state` | `android_sensors`, `available_cameras`, `cameraEnabled`, `camera_auto_rotation`, `camera_auto_rotation_at`, `camera_auto_rotation_lens`, `camera_enabled`, `exposure_compensation`, `frame_captured_ms`, `frame_last_seen`, `frame_seq`, `last_motion_at`, `last_motion_score`, `motion_active`, `motion_detection_enabled`, `motion_detection_threshold`, `motion_flashlight_enabled`, `motion_recording_active`, `motion_screen_enabled`, `preview_by_lens`, `recording`, `recording_enabled`, `selected_camera` | Only the declared camera allowlist is written. Declared by server_core/state.py:ANDROID_CAMERA_STATE_KEYS. |
| `android_home_state.json` | `clients.<deviceID> door-sensor state` | `android_sensors`, `calibrating`, `calibration_samples`, `close_angle_threshold`, `door_angle`, `door_event_ms`, `door_status`, `doorbell_muted`, `ignore_door_open_until_closed`, `last_chime_at`, `last_transition_at`, `open_angle_threshold`, `openness_score`, `smoothing_window` | Only the declared door-sensor allowlist is written. Declared by server_core/state.py:ANDROID_DSS_STATE_KEYS. |
| `automations_state.json` | `root managed fields` | `tapo_recharge_android_battery`, `device_automations`, `tapo_day_reset` | Read/modify/write preserves unknown top-level legacy fields. |
| `automations_state.json` | `tapo_recharge_android_battery.<deviceID>` | `type`, `clientName`, `enabled`, `targetID`, `targetDeviceID`, `child_id`, `child_index`, `child_position`, `lowBattery`, `fullBattery` | Managed fields are listed; migrated legacy fields pass through. |
| `automations_state.json` | `device_automations[]` | `enabled`, `from_deviceID`, `from_output`, `trigger`, `threshold`, `threshold_unit`, `arm_states`, `to_kind`, `action_type`, `to_deviceID`, `to_input`, `targetID`, `power_action`, `filename`, `sound_volume`, `target_key_deviceID`, `title`, `message`, `duration_seconds`, `minimum_duration_seconds`, `repeat`, `timer_seconds`, `repeat_seconds`, `cooldown_seconds`, `auto_off`, `auto_off_seconds`, `retrigger`, `last_notification_at` | scope is removed; last_notification_at is conditional; loaded legacy fields pass through on save. |
| `automations_state.json` | `tapo_day_reset` | `type`, `enabled`, `resetHour`, `lastRunDate` | The managed object is normalized to these fields. |
| `matter_device_state.json` | `root` | `devices` | Writer replaces the root object. |
| `matter_device_state.json` | `devices.<deviceID>` | `battery`, `battery_low`, `battery_state`, `brand`, `calibrating`, `contact_open`, `contact_state_value`, `door_angle`, `door_event_ms`, `door_status`, `doorbell_muted`, `humidity_percent`, `humidity_raw`, `ip`, `last_motion_at`, `last_transition_at`, `manufacturer`, `matter_battery_charge_level`, `matter_battery_charge_state`, `matter_battery_low`, `matter_battery_percent`, `matter_battery_percent_remaining_raw`, `matter_battery_replacement_needed`, `matter_button_event`, `matter_button_event_at`, `matter_button_position`, `matter_button_press_count`, `matter_cluster`, `matter_contact_open_when`, `matter_device_type`, `matter_endpoint`, `matter_hardware_version`, `matter_kind`, `matter_kinds`, `matter_last_sync_at`, `matter_node_id`, `matter_node_label`, `matter_onoff`, `matter_product_name`, `matter_reachable`, `matter_serial_number`, `matter_software_version`, `matter_switch_multipress_max`, `matter_switch_position`, `matter_switch_positions`, `matter_vendor_name`, `model`, `motion_active`, `occupancy_state_value`, `openness_score`, `temperature_c`, `temperature_raw` | Only the declared Matter allowlist is written. Declared by server_core/state.py:MATTER_DEVICE_STATE_KEYS. |
| `security_actions.json` | `root` | `actions` | Writer replaces the root object. |
| `security_actions.json` | `actions[]` | `enabled`, `from_deviceID`, `from_output`, `trigger`, `threshold`, `threshold_unit`, `arm_states`, `to_kind`, `action_type`, `to_deviceID`, `to_input`, `targetID`, `power_action`, `filename`, `sound_volume`, `target_key_deviceID`, `title`, `message`, `duration_seconds`, `minimum_duration_seconds`, `repeat`, `timer_seconds`, `repeat_seconds`, `cooldown_seconds`, `auto_off`, `auto_off_seconds`, `retrigger`, `last_notification_at` | scope is removed; last_notification_at is conditional; loaded legacy fields pass through on save. |
| `server_state.json` | `root` | `clients`, `system` | Writer replaces the root object. |
| `server_state.json` | `clients group names` | `tapo`, `matter`, `android_home`, `android_key`, `unprovisioned`, `other` | Each group contains client records. |
| `server_state.json` | `clients.tapo[]` | `clientName`, `clientRole`, `deviceID`, `provisioned`, `source`, `zone_name` | Only the group allowlist is written. Declared by server_core/state.py:TAPO_SERVER_STATE_KEYS. |
| `server_state.json` | `clients.matter[]` | `clientName`, `clientRole`, `deviceID`, `provisioned`, `source`, `zone_name` | Only persistent identity and user configuration are written. Declared by server_core/state.py:MATTER_SERVER_STATE_KEYS. |
| `server_state.json` | `clients.android_home[]` | `androidVersion`, `battery`, `battery_low`, `battery_state`, `brand`, `clientName`, `clientRole`, `deviceID`, `fcm_token`, `fcm_token_at`, `hasDSSHW`, `heartbeat_interval_ms`, `ip`, `provisioned`, `version`, `zone_name` | Only the group allowlist is written. Declared by server_core/state.py:ANDROID_HOME_SERVER_STATE_KEYS. |
| `server_state.json` | `clients.android_key[]` | `androidVersion`, `battery`, `battery_low`, `battery_state`, `brand`, `clientName`, `clientRole`, `deviceID`, `fcm_token`, `fcm_token_at`, `heartbeat_interval_ms`, `ip`, `provisioned`, `version`, `zone_name` | Only the group allowlist is written. Declared by server_core/state.py:ANDROID_KEY_SERVER_STATE_KEYS. |
| `server_state.json` | `clients.unprovisioned[]` | `androidVersion`, `battery`, `battery_low`, `battery_state`, `brand`, `clientName`, `clientRole`, `detectedRole`, `deviceID`, `fcm_token`, `fcm_token_at`, `hasDSSHW`, `heartbeat_interval_ms`, `ip`, `manufacturer`, `model`, `provisioned`, `source`, `version`, `zone_name` | Only the group allowlist is written. Declared by server_core/state.py:UNPROVISIONED_SERVER_STATE_KEYS. |
| `server_state.json` | `clients.other[]` | `battery`, `battery_low`, `battery_state`, `brand`, `clientName`, `clientRole`, `deviceID`, `ip`, `manufacturer`, `model`, `provisioned`, `source`, `version`, `zone_name` | Only the group allowlist is written. Declared by server_core/state.py:OTHER_SERVER_STATE_KEYS. |
| `server_state.json` | `system` | `armed`, `arm_state`, `armState` | arm_state and armState are both currently written. |
| `tapo_device_state.json` | `root` | `devices` | Writer replaces the root object. |
| `tapo_device_state.json` | `devices.<deviceID>` | `tapo_alias`, `tapo_battery`, `tapo_battery_level`, `tapo_battery_low`, `tapo_battery_percent`, `tapo_battery_state`, `tapo_brightness`, `tapo_child_avatar`, `tapo_child_category`, `tapo_child_id`, `tapo_child_kind`, `tapo_child_mac`, `tapo_child_model`, `tapo_child_name`, `tapo_child_rssi`, `tapo_child_signal_level`, `tapo_child_status`, `tapo_child_type`, `tapo_children`, `tapo_children_initialized`, `tapo_color_temperature`, `tapo_control_error`, `tapo_control_ready`, `tapo_dashboard_section`, `tapo_desired_brightness`, `tapo_desired_color_temperature`, `tapo_desired_hue`, `tapo_desired_lighting_mode`, `tapo_desired_lighting_updated_at`, `tapo_desired_saturation`, `tapo_desired_white_saturation`, `tapo_device_type`, `tapo_dimmable`, `tapo_hide_dashboard`, `tapo_hue`, `tapo_id`, `tapo_ip`, `tapo_is_bulb`, `tapo_is_button`, `tapo_is_camera`, `tapo_is_hub`, `tapo_is_hub_child`, `tapo_is_on`, `tapo_is_outlet_extender`, `tapo_is_plug`, `tapo_is_switch`, `tapo_kind`, `tapo_last_trigger_at`, `tapo_last_trigger_event`, `tapo_last_trigger_event_id`, `tapo_last_trigger_id`, `tapo_mac`, `tapo_model`, `tapo_onvif_port`, `tapo_parent_alias`, `tapo_parent_device_id`, `tapo_parent_id`, `tapo_parent_ip`, `tapo_parent_model`, `tapo_pending_power_commands`, `tapo_room_power`, `tapo_rtsp_url`, `tapo_saturation`, `tapo_supports_brightness`, `tapo_supports_color`, `tapo_supports_color_temp`, `tapo_supports_onvif`, `tapo_supports_power`, `tapo_supports_rtsp`, `tapo_trigger_log_supported` | Only the declared Tapo allowlist is written. Declared by server_core/state.py:TAPO_DEVICE_STATE_KEYS. |
| `tapo_device_state.json` | `devices.<deviceID>.tapo_children[]` | `<all child fields except raw>` | Child dictionaries are copied dynamically after raw is removed. |
| `tapo_lighting_state.json` | `root` | `schemes`, `activeSchemes`, `modeConfig` | The Tapo route normalizer writes these root fields. |
| `tapo_lighting_state.json` | `schemes.<target>[]` | `favorite`, `icon`, `label`, `mode`, `preset`, `savedAt` | Targets are home, device:<deviceID>, or room:<deviceID-list>. |
| `tapo_lighting_state.json` | `schemes.<target>[].preset managed fields` | `brightness`, `colorTemperature`, `whiteSaturation`, `hue`, `saturation` | The preset object passes through, so extension fields can persist. |
| `tapo_lighting_state.json` | `activeSchemes.<target>` | `<mode name>` | Dynamic target-to-mode mapping; no nested object fields. |
| `tapo_lighting_state.json` | `modeConfig.<mode>.<target>` | `power`, `preset` | Values normalize to a choice string or this two-field object. |

## Candidate persistence-related source operations

This deliberately broad scanner output is retained as supporting evidence. It includes non-persistence calls such as string replacement and JSON response serialization; the reviewed table above is authoritative.

| Source location | Operation | Call |
| --- | --- | --- |
| `kotibot_server.py:56` | read | `path.read_bytes` |
| `kotibot_server.py:60` | read | `DASHBOARD_ICON_CSS_FILE.read_text` |
| `kotibot_server.py:63` | write | `stylesheet.replace` |
| `kotibot_server.py:69` | write | `stylesheet.replace` |
| `kotibot_server.py:81` | read | `stylesheet_path.read_text` |
| `kotibot_server.py:82` | write | `stylesheet.replace` |
| `kotibot_server.py:101` | read | `TAPO_CONFIG_FILE.read_text` |
| `kotibot_server.py:101` | read | `json.loads` |
| `kotibot_server.py:391` | write | `replace` |
| `kotibot_server.py:391` | write | `replace` |
| `kotibot_server.py:668` | write | `json.dumps` |
| `kotibot_server.py:910` | write | `json.dumps` |
| `server_core/clients.py:48` | write | `value.replace` |
| `server_core/io.py:39` | write | `path.parent.mkdir` |
| `server_core/io.py:40` | write | `json.dumps` |
| `server_core/io.py:43` | read | `path.read_text` |
| `server_core/io.py:53` | read/write | `tmp_path.open` |
| `server_core/io.py:55` | write | `f.write` |
| `server_core/io.py:59` | write | `tmp_path.replace` |
| `server_core/io.py:60` | write | `os.chmod` |
| `server_core/io.py:65` | write | `tmp_path.unlink` |
| `server_core/io.py:83` | read | `json.loads` |
| `server_core/io.py:83` | read | `path.read_text` |
| `server_core/paths.py:113` | write | `directory.mkdir` |
| `server_core/paths.py:120` | write | `os.chmod` |
| `server_core/preflight.py:21` | read | `requirements_file.read_text` |
| `server_core/routes.py:49` | write | `json.dumps` |
| `server_core/security_actions.py:73` | write | `replace` |
| `server_core/security_actions.py:73` | write | `replace` |
| `server_core/security_actions.py:468` | write | `raw.replace` |
| `server_core/state.py:261` | read | `read_json` |
| `server_core/state.py:280` | write | `write_json_atomic` |
| `server_core/state.py:371` | read | `read_json` |
| `server_core/state.py:381` | write | `write_json_atomic` |
| `server_core/state.py:580` | write | `write_json_atomic` |
| `subsystems/activities/activity_log.py:31` | write | `self.state_file.parent.mkdir` |
| `subsystems/activities/activity_log.py:55` | write | `replace` |
| `subsystems/activities/activity_log.py:55` | write | `replace` |
| `subsystems/activities/activity_log.py:461` | read | `read_json` |
| `subsystems/activities/activity_log.py:490` | write | `write_json_atomic` |
| `subsystems/automations/automations_routes.py:409` | read | `read_json` |
| `subsystems/automations/automations_routes.py:416` | write | `write_json_atomic` |
| `subsystems/automations/automations_routes.py:423` | read | `read_json` |
| `subsystems/automations/automations_routes.py:452` | write | `write_json_atomic` |
| `subsystems/automations/automations_routes.py:685` | write | `replace` |
| `subsystems/automations/automations_routes.py:796` | write | `clean.replace` |
| `subsystems/automations/automations_routes.py:801` | write | `clean.replace` |
| `subsystems/automations/trigger_routes.py:87` | write | `replace` |
| `subsystems/automations/trigger_routes.py:87` | write | `replace` |
| `subsystems/automations/trigger_routes.py:104` | write | `value.replace` |
| `subsystems/automations/trigger_routes.py:587` | write | `replace` |
| `subsystems/automations/trigger_routes.py:1557` | write | `clean_trigger.replace` |
| `subsystems/bluetooth/bluetooth_routes.py:12` | write | `replace` |
| `subsystems/bluetooth/bluetooth_routes.py:12` | write | `replace` |
| `subsystems/bluetooth/bluetooth_routes.py:139` | write | `replace` |
| `subsystems/bluetooth/bluetooth_routes.py:199` | write | `replace` |
| `subsystems/client-android-home/client_android_home_telemetry.py:134` | read/write | `Image.open` |
| `subsystems/client-tapo/tapo_admin_routes.py:46` | write | `write_json_atomic` |
| `subsystems/client-tapo/tapo_admin_routes.py:58` | write | `tapo_config_file.parent.mkdir` |
| `subsystems/client-tapo/tapo_admin_routes.py:59` | write | `json.dumps` |
| `subsystems/client-tapo/tapo_admin_routes.py:59` | write | `tapo_config_file.write_text` |
| `subsystems/client-tapo/tapo_control.py:47` | write | `TAPO_CAMERA_HLS_ROOT.mkdir` |
| `subsystems/client-tapo/tapo_control.py:52` | write | `TAPO_CAMERA_RECORDING_ROOT.mkdir` |
| `subsystems/client-tapo/tapo_control.py:58` | write | `os.chmod` |
| `subsystems/client-tapo/tapo_control.py:59` | write | `os.chmod` |
| `subsystems/client-tapo/tapo_control.py:120` | write | `ip.replace` |
| `subsystems/client-tapo/tapo_control.py:175` | write | `os.write` |
| `subsystems/client-tapo/tapo_control.py:216` | write | `replace` |
| `subsystems/client-tapo/tapo_control.py:216` | write | `replace` |
| `subsystems/client-tapo/tapo_control.py:225` | write | `recording_dir.mkdir` |
| `subsystems/client-tapo/tapo_control.py:230` | write | `os.chmod` |
| `subsystems/client-tapo/tapo_control.py:306` | write | `path.unlink` |
| `subsystems/client-tapo/tapo_control.py:368` | write | `shutil.rmtree` |
| `subsystems/client-tapo/tapo_control.py:370` | write | `stream_dir.mkdir` |
| `subsystems/client-tapo/tapo_control.py:375` | write | `os.chmod` |
| `subsystems/client-tapo/tapo_control.py:1108` | read | `json.loads` |
| `subsystems/client-tapo/tapo_extenders.py:14` | write | `replace` |
| `subsystems/client-tapo/tapo_extenders.py:14` | write | `replace` |
| `subsystems/client-tapo/tapo_extenders.py:17` | write | `replace` |
| `subsystems/client-tapo/tapo_routes.py:88` | write | `text.replace` |
| `subsystems/client-tapo/tapo_routes.py:94` | write | `text.replace` |
| `subsystems/client-tapo/tapo_routes.py:166` | write | `key.replace` |
| `subsystems/client-tapo/tapo_routes.py:169` | write | `key.replace` |
| `subsystems/client-tapo/tapo_routes.py:233` | read | `read_json` |
| `subsystems/client-tapo/tapo_routes.py:242` | write | `write_json_atomic` |
| `subsystems/client-tapo/tapo_routes.py:317` | write | `replace` |
| `subsystems/client-tapo/tapo_routes.py:1044` | write | `replace` |
| `subsystems/client-tapo/tapo_routes.py:1044` | write | `replace` |
| `subsystems/client-tapo/tapo_routes.py:1047` | write | `clean.replace` |
| `subsystems/client-tapo/tapo_routes.py:1050` | write | `clean.replace` |
| `subsystems/client-tapo/tapo_routes.py:1060` | write | `replace` |
| `subsystems/client-tapo/tapo_routes.py:1109` | write | `json.dumps` |
| `subsystems/client-tapo/tapo_routes.py:1116` | write | `json.dumps` |
| `subsystems/client-tapo/tapo_routes.py:1243` | read | `read_json` |
| `subsystems/client-tapo/tapo_routes.py:1260` | read | `read_json` |
| `subsystems/client-tapo/tapo_routes.py:1278` | write | `write_json_atomic` |
| `subsystems/client-tapo/tapo_routes.py:1474` | write | `replace` |
| `subsystems/client-tapo/tapo_routes.py:1474` | write | `replace` |
| `subsystems/client-tapo/tapo_routes.py:1489` | write | `clean_kind.replace` |
| `subsystems/client-tapo/tapo_routes.py:1745` | write | `replace` |
| `subsystems/client-tapo/tapo_routes.py:2234` | write | `replace` |
| `subsystems/client-tapo/tapo_routes.py:2862` | write | `replace` |
| `subsystems/client-tapo/tapo_types.py:100` | write | `text.replace` |
| `subsystems/environment/environment_routes.py:78` | write | `environment_dir.mkdir` |
| `subsystems/environment/environment_routes.py:130` | read | `read_json` |
| `subsystems/environment/environment_routes.py:150` | write | `write_json_atomic` |
| `subsystems/environment/environment_routes.py:153` | read | `json_exists` |
| `subsystems/environment/environment_routes.py:170` | read/write | `REMOTE_OPENER.open` |
| `subsystems/environment/environment_routes.py:172` | read | `json.loads` |
| `subsystems/environment/environment_routes.py:184` | read/write | `REMOTE_OPENER.open` |
| `subsystems/environment/environment_routes.py:859` | read | `json_exists` |
| `subsystems/environment/environment_routes.py:869` | read | `read_json` |
| `subsystems/environment/environment_routes.py:944` | read | `json_exists` |
| `subsystems/file-server/file_server_routes.py:10` | write | `apk_dir.mkdir` |
| `subsystems/matter/matter_routes.py:26` | write | `matter_dir.mkdir` |
| `subsystems/matter/matter_runtime.py:144` | write | `replace` |
| `subsystems/matter/matter_runtime.py:146` | write | `replace` |
| `subsystems/matter/matter_runtime.py:155` | write | `replace` |
| `subsystems/matter/matter_runtime.py:162` | write | `replace` |
| `subsystems/matter/matter_runtime.py:234` | read | `read_json` |
| `subsystems/matter/matter_runtime.py:243` | write | `write_json_atomic` |
| `subsystems/matter/matter_runtime.py:300` | write | `replace` |
| `subsystems/matter/matter_runtime.py:300` | write | `replace` |
| `subsystems/matter/matter_runtime.py:300` | write | `replace` |
| `subsystems/matter/matter_runtime.py:313` | write | `replace` |
| `subsystems/matter/matter_runtime.py:313` | write | `replace` |
| `subsystems/matter/matter_runtime.py:313` | write | `replace` |
| `subsystems/matter/matter_runtime.py:528` | write | `replace` |
| `subsystems/matter/matter_runtime.py:588` | write | `storage_dir.mkdir` |
| `subsystems/matter/matter_runtime.py:593` | write | `storage_root.mkdir` |
| `subsystems/matter/matter_runtime.py:689` | write | `selected_storage_dir.mkdir` |
| `subsystems/matter/matter_runtime.py:824` | write | `raw_nodes.replace` |
| `subsystems/matter/matter_runtime.py:880` | write | `shutil.rmtree` |
| `subsystems/matter/matter_runtime.py:881` | write | `storage_dir.rename` |
| `subsystems/matter/matter_runtime.py:882` | write | `repair_dir.mkdir` |
| `subsystems/matter/matter_runtime.py:896` | write | `shutil.rmtree` |
| `subsystems/matter/matter_runtime.py:899` | write | `backup_dir.rename` |
| `subsystems/matter/matter_runtime.py:904` | write | `shutil.rmtree` |
| `subsystems/matter/matter_runtime.py:905` | write | `backup_dir.rename` |
| `subsystems/matter/matter_runtime.py:914` | write | `repair_dir.rename` |
| `subsystems/matter/matter_runtime.py:915` | write | `shutil.rmtree` |
| `subsystems/matter/matter_runtime.py:1753` | write | `proc.stdin.write` |
| `subsystems/network/external_ip.py:82` | write | `json.dumps` |
| `subsystems/network/external_ip.py:98` | read | `json.loads` |
| `subsystems/network/external_ip.py:156` | write | `json.dumps` |
| `subsystems/notifications/kotibot_push.py:39` | write | `json.dumps` |
| `subsystems/notifications/kotibot_push.py:47` | write | `self.queue_file.parent.mkdir` |
| `subsystems/notifications/kotibot_push.py:53` | read/write | `os.open` |
| `subsystems/notifications/kotibot_push.py:60` | write | `stream.write` |
| `subsystems/notifications/kotibot_push.py:63` | write | `os.chmod` |
| `subsystems/notifications/kotibot_push.py:163` | read | `service_account.Credentials.from_service_account_file` |
| `subsystems/notifications/kotibot_push.py:213` | write | `json.dumps` |
| `subsystems/notifications/kotibot_push.py:229` | read | `json.loads` |
| `subsystems/notifications/kotibot_push.py:273` | write | `json.dumps` |
| `subsystems/notifications/kotibot_push.py:289` | read | `json.loads` |
| `subsystems/notifications/kotibot_push.py:309` | read/write | `self.queue_file.open` |
| `subsystems/notifications/kotibot_push.py:322` | read | `json.loads` |
| `subsystems/security/kotibot_security.py:73` | write | `json.dumps` |
| `subsystems/security/kotibot_security.py:425` | write | `audit_file.parent.mkdir` |
| `subsystems/security/kotibot_security.py:436` | write | `backup_file.unlink` |
| `subsystems/security/kotibot_security.py:438` | write | `audit_file.replace` |
| `subsystems/security/kotibot_security.py:439` | write | `os.chmod` |
| `subsystems/security/kotibot_security.py:447` | read/write | `os.open` |
| `subsystems/security/kotibot_security.py:450` | write | `stream.write` |
| `subsystems/security/kotibot_security.py:453` | write | `os.chmod` |
| `subsystems/security/kotibot_security.py:713` | read | `json.loads` |
| `subsystems/security/kotibot_security.py:714` | read | `state_file.read_text` |
| `subsystems/security/kotibot_security.py:728` | write | `os.chmod` |
| `subsystems/security/kotibot_security.py:734` | write | `state_file.parent.mkdir` |
| `subsystems/security/kotibot_security.py:750` | read/write | `os.open` |
| `subsystems/security/kotibot_security.py:753` | write | `json.dump` |
| `subsystems/security/kotibot_security.py:759` | write | `stream.write` |
| `subsystems/security/kotibot_security.py:763` | write | `tmp.replace` |
| `subsystems/security/kotibot_security.py:764` | write | `os.chmod` |
| `subsystems/security/kotibot_security.py:768` | write | `tmp.unlink` |
| `subsystems/security/kotibot_security.py:1707` | write | `json.dumps` |
| `subsystems/security/kotibot_security.py:1746` | write | `json.dumps` |
| `subsystems/security/kotibot_security.py:1759` | write | `json.dumps` |
| `subsystems/security/kotibot_security.py:1783` | write | `json.dumps` |
| `subsystems/security/kotibot_security.py:1792` | write | `json.dumps` |
| `subsystems/security/kotibot_security.py:1808` | write | `json.dumps` |
| `subsystems/soundboard/soundboard_routes.py:40` | write | `wav_dir.mkdir` |
| `subsystems/video/video_routes.py:12` | write | `video_dir.mkdir` |
| `subsystems/video/video_routes.py:25` | write | `replace` |
| `subsystems/video/video_routes.py:25` | write | `replace` |
| `subsystems/video/video_routes.py:104` | read | `json.loads` |
| `subsystems/video/video_routes.py:136` | write | `replace` |
| `subsystems/video/video_routes.py:210` | write | `temp_path.unlink` |
| `subsystems/video/video_routes.py:214` | write | `os.chmod` |
| `subsystems/video/video_routes.py:215` | write | `temp_path.replace` |
| `subsystems/video/video_routes.py:216` | write | `os.chmod` |
| `subsystems/video/video_routes.py:283` | write | `recording_dir.mkdir` |
| `subsystems/video/video_routes.py:328` | write | `recording_dir.mkdir` |
| `subsystems/video/video_routes.py:333` | write | `os.chmod` |
| `subsystems/video/video_routes.py:345` | read/write | `os.open` |
| `subsystems/video/video_routes.py:367` | write | `path.unlink` |
| `subsystems/video/video_routes.py:402` | write | `replace` |
| `subsystems/voice/voice_routes.py:31` | write | `replace` |
| `subsystems/voice/voice_routes.py:31` | write | `replace` |
| `subsystems/voice/voice_routes.py:31` | write | `replace` |
| `subsystems/voice/voice_routes.py:31` | write | `sdp.replace` |
| `subsystems/voice/voice_routes.py:102` | read | `json.loads` |
| `subsystems/voice/voice_routes.py:311` | write | `json.dumps` |
| `tests/test_security_policy.py:19` | read | `read_text` |
| `tests/test_security_policy.py:38` | read | `read_text` |

## Declared state-key groups

### `server_core/state.py`

- `ANDROID_CAMERA_STATE_KEYS`: `android_sensors`, `available_cameras`, `cameraEnabled`, `camera_auto_rotation`, `camera_auto_rotation_at`, `camera_auto_rotation_lens`, `camera_enabled`, `exposure_compensation`, `frame_captured_ms`, `frame_last_seen`, `frame_seq`, `last_motion_at`, `last_motion_score`, `motion_active`, `motion_detection_enabled`, `motion_detection_threshold`, `motion_flashlight_enabled`, `motion_recording_active`, `motion_screen_enabled`, `preview_by_lens`, `recording`, `recording_enabled`, `selected_camera`
- `ANDROID_DSS_STATE_KEYS`: `android_sensors`, `calibrating`, `calibration_samples`, `close_angle_threshold`, `door_angle`, `door_event_ms`, `door_status`, `doorbell_muted`, `ignore_door_open_until_closed`, `last_chime_at`, `last_transition_at`, `open_angle_threshold`, `openness_score`, `smoothing_window`
- `ANDROID_HOME_SERVER_STATE_KEYS`: `androidVersion`, `battery`, `battery_low`, `battery_state`, `brand`, `clientName`, `clientRole`, `deviceID`, `fcm_token`, `fcm_token_at`, `hasDSSHW`, `heartbeat_interval_ms`, `ip`, `provisioned`, `version`, `zone_name`
- `ANDROID_KEY_SERVER_STATE_KEYS`: `androidVersion`, `battery`, `battery_low`, `battery_state`, `brand`, `clientName`, `clientRole`, `deviceID`, `fcm_token`, `fcm_token_at`, `heartbeat_interval_ms`, `ip`, `provisioned`, `version`, `zone_name`
- `ANDROID_SHARED_SERVER_STATE_KEYS`: `androidVersion`, `battery`, `battery_low`, `battery_state`, `brand`, `clientName`, `clientRole`, `deviceID`, `fcm_token`, `fcm_token_at`, `heartbeat_interval_ms`, `ip`, `provisioned`, `version`, `zone_name`
- `COMMON_CLIENT_STATE_KEYS`: `clientName`, `clientRole`, `deviceID`, `provisioned`, `zone_name`
- `MATTER_DEVICE_STATE_KEYS`: `battery`, `battery_low`, `battery_state`, `brand`, `calibrating`, `contact_open`, `contact_state_value`, `door_angle`, `door_event_ms`, `door_status`, `doorbell_muted`, `humidity_percent`, `humidity_raw`, `ip`, `last_motion_at`, `last_transition_at`, `manufacturer`, `matter_battery_charge_level`, `matter_battery_charge_state`, `matter_battery_low`, `matter_battery_percent`, `matter_battery_percent_remaining_raw`, `matter_battery_replacement_needed`, `matter_button_event`, `matter_button_event_at`, `matter_button_position`, `matter_button_press_count`, `matter_cluster`, `matter_contact_open_when`, `matter_device_type`, `matter_endpoint`, `matter_hardware_version`, `matter_kind`, `matter_kinds`, `matter_last_sync_at`, `matter_node_id`, `matter_node_label`, `matter_onoff`, `matter_product_name`, `matter_reachable`, `matter_serial_number`, `matter_software_version`, `matter_switch_multipress_max`, `matter_switch_position`, `matter_switch_positions`, `matter_vendor_name`, `model`, `motion_active`, `occupancy_state_value`, `openness_score`, `temperature_c`, `temperature_raw`
- `MATTER_SERVER_STATE_KEYS`: `clientName`, `clientRole`, `deviceID`, `provisioned`, `source`, `zone_name`
- `OTHER_SERVER_STATE_KEYS`: `battery`, `battery_low`, `battery_state`, `brand`, `clientName`, `clientRole`, `deviceID`, `ip`, `manufacturer`, `model`, `provisioned`, `source`, `version`, `zone_name`
- `TAPO_DEVICE_STATE_KEYS`: `tapo_alias`, `tapo_battery`, `tapo_battery_level`, `tapo_battery_low`, `tapo_battery_percent`, `tapo_battery_state`, `tapo_brightness`, `tapo_child_avatar`, `tapo_child_category`, `tapo_child_id`, `tapo_child_kind`, `tapo_child_mac`, `tapo_child_model`, `tapo_child_name`, `tapo_child_rssi`, `tapo_child_signal_level`, `tapo_child_status`, `tapo_child_type`, `tapo_children`, `tapo_children_initialized`, `tapo_color_temperature`, `tapo_control_error`, `tapo_control_ready`, `tapo_dashboard_section`, `tapo_desired_brightness`, `tapo_desired_color_temperature`, `tapo_desired_hue`, `tapo_desired_lighting_mode`, `tapo_desired_lighting_updated_at`, `tapo_desired_saturation`, `tapo_desired_white_saturation`, `tapo_device_type`, `tapo_dimmable`, `tapo_hide_dashboard`, `tapo_hue`, `tapo_id`, `tapo_ip`, `tapo_is_bulb`, `tapo_is_button`, `tapo_is_camera`, `tapo_is_hub`, `tapo_is_hub_child`, `tapo_is_on`, `tapo_is_outlet_extender`, `tapo_is_plug`, `tapo_is_switch`, `tapo_kind`, `tapo_last_trigger_at`, `tapo_last_trigger_event`, `tapo_last_trigger_event_id`, `tapo_last_trigger_id`, `tapo_mac`, `tapo_model`, `tapo_onvif_port`, `tapo_parent_alias`, `tapo_parent_device_id`, `tapo_parent_id`, `tapo_parent_ip`, `tapo_parent_model`, `tapo_pending_power_commands`, `tapo_room_power`, `tapo_rtsp_url`, `tapo_saturation`, `tapo_supports_brightness`, `tapo_supports_color`, `tapo_supports_color_temp`, `tapo_supports_onvif`, `tapo_supports_power`, `tapo_supports_rtsp`, `tapo_trigger_log_supported`
- `TAPO_SERVER_STATE_KEYS`: `clientName`, `clientRole`, `deviceID`, `provisioned`, `source`, `zone_name`
- `UNPROVISIONED_SERVER_STATE_KEYS`: `androidVersion`, `battery`, `battery_low`, `battery_state`, `brand`, `clientName`, `clientRole`, `detectedRole`, `deviceID`, `fcm_token`, `fcm_token_at`, `hasDSSHW`, `heartbeat_interval_ms`, `ip`, `manufacturer`, `model`, `provisioned`, `source`, `version`, `zone_name`

## Candidate persisted key names by source file

This is a deliberately broad static list. Remove API-only and in-memory-only names during review; do not add values.

### `kotibot_server.py`

`/static/css/theme-<theme>.css`, `/static/img/dashboard-icons/kotibot-icons.css`, `Cache-Control`, `Content-Security-Policy`, `Cross-Origin-Opener-Policy`, `Cross-Origin-Resource-Policy`, `Expires`, `KOTIBOT_ANDROID_HOME_APPLY_SEEN_CLIENT`, `KOTIBOT_CANCEL_AUTOMATION_ROUTE_RUNTIME`, `KOTIBOT_DEV_STATIC_NO_CACHE`, `KOTIBOT_ENVIRONMENT_SNAPSHOT`, `KOTIBOT_MATTER_SETTINGS_SNAPSHOT`, `KOTIBOT_PREVIEW_VIEWER_TTL_SECONDS`, `KOTIBOT_REMOVE_RECHARGE_AUTOMATIONS_FOR_DEVICE`, `KOTIBOT_TAPO_ENABLED`, `KOTIBOT_TAPO_LIGHTING_STATE_SNAPSHOT`, `KOTIBOT_VOICE_TALK_ACTIVE_FOR_TARGET`, `Permissions-Policy`, `Pragma`, `Referrer-Policy`, `Retry-After`, `Server-Timing`, `Strict-Transport-Security`, `X-Content-Type-Options`, `X-Device-ID`, `X-Frame-Options`, `X-Koti-Enrollment`, `X-KotiBot-Route-Ms`, `activities_dir`, `activity_log`, `age_text`, `android_home_apply_seen_client`, `android_home_state_file`, `app`, `apply_enabled_roles`, `armed`, `automation_state_file`, `automation_type_device_routes`, `automation_type_tapo_recharge`, `base_dir`, `broadcast_state`, `build_dashboard_bootstrap`, `cancel_door_sound_repeat`, `cancel_motion_recording_stop`, `cancel_route_runtime`, `clean_arm_state`, `clean_filename_part`, `clean_zone_name`, `clientName`, `clientRole`, `client_android_home_dir`, `client_android_key_dir`, `client_has_role`, `client_role_cam`, `client_role_dss`, `client_role_key`, `client_role_tapo`, `client_role_unp`, `client_status_sort_key`, `client_tapo_dir`, `clients`, `close_angle_threshold`, `current_server_ip`, `current_status_payload`, `dark`, `dashboard_auth_status`, `dashboard_authenticated`, `deviceID`, `door_recalibration_active_timeout_seconds`, `door_recalibration_command_keys`, `door_recalibration_command_timeout_seconds`, `door_sound_repeat_allowed`, `duration_text`, `enabled`, `enrollmentToken`, `environment_dir`, `environment_snapshot`, `error`, `external_ip_check_loop`, `file_server_dir`, `fire_camera_motion_routes`, `fire_door_routes`, `fire_environment_routes`, `flush_json_writes`, `get_clients_for_device`, `get_unprovisioned_client`, `hasDSSHW`, `init_client`, `is_client_stale`, `json_dumps`, `keyID`, `kotiKeyID`, `kotiKeySecret`, `light`, `load_state`, `matter_device_state_file`, `matter_dir`, `matter_settings_snapshot`, `matter_stale_client_seconds`, `matter_sync_stop`, `motionDetectionEnabled`, `motion_detection_enabled`, `needs_heartbeat`, `normalize_after_state_load`, `normalize_client_roles`, `now_epoch`, `now_local`, `ok`, `open_angle_threshold`, `pending_command`, `play_wav_file`, `preview_requested_for_client`, `preview_viewer_ttl_seconds`, `provisioned`, `prune_invalid_routes_for_clients`, `prune_routes_for_client_change`, `push_queue`, `queue_door_recalibration`, `register_core_subsystems`, `register_enabled_subsystems`, `register_seen_client`, `removedAutomations`, `request_ip`, `request_json`, `routes`, `runtime`, `safe_bool`, `safe_float`, `safe_int`, `save_state`, `schedule_door_sound_repeat`, `secret`, `security`, `security_actions_file`, `serverPort`, `server_start_epoch`, `set_routes`, `set_system_arm_state`, `snapshot_client`, `sse_listeners`, `stale_client_seconds`, `start_external_ip_loop`, `start_registered_subsystem_loops`, `state_file`, `state_lock`, `static_version`, `subsystems_dir`, `sync_arming_motion_detection`, `systemArmed`, `system_arm_state`, `system_armed`, `tapo_config_file`, `tapo_device_state_file`, `tapo_enabled`, `tapo_import_error`, `tapo_lighting_state_file`, `tapo_lighting_state_snapshot`, `tapo_routes_loaded`, `tapo_watcher_stop`, `used_room_names`, `v`, `voice_talk_active_for_target`, `zoneName`, `zone_name`

### `server_core/clients.py`

`androidVersion`, `android_home_apply_seen_client`, `apply_enabled_roles`, `armed`, `battery`, `brand`, `calibrating`, `calibration_samples`, `cameraEnabled`, `camera_auto_rotation`, `camera_auto_rotation_at`, `camera_auto_rotation_lens`, `cancel_door_sound_repeat`, `clean_zone_name`, `clientName`, `clientRole`, `client_has_role`, `client_role_cam`, `client_role_dss`, `client_role_key`, `client_role_tapo`, `client_role_unp`, `clients`, `detectedRole`, `deviceID`, `door_angle`, `door_recalibration_command_keys`, `door_recalibration_command_timeout_seconds`, `door_status`, `fcm_token`, `fcm_token_at`, `frame`, `frame_last_seen`, `frame_seq`, `get_clients_for_device`, `get_unprovisioned_client`, `hasDSSHW`, `heartbeat_interval_ms`, `heartbeat_pending`, `heartbeat_requested_at`, `ignore_door_open_until_closed`, `init_client`, `ip`, `last_seen`, `needs_heartbeat`, `normalize_client_roles`, `now_epoch`, `openness_score`, `pending_command`, `preview_viewers`, `provisioned`, `prune_routes_for_client_change`, `queue_door_recalibration`, `recalibrate`, `recalibrateSeq`, `recalibrate_seq`, `recalibration_ignore_until`, `recalibration_phase`, `recalibration_requested_at`, `recording`, `recordingEnabled`, `recording_enabled`, `register_seen_client`, `request_ip`, `request_json`, `system_armed`, `telemetry_count`, `triggerRecalibrate`, `used_room_names`, `version`, `zone_name`

### `server_core/io.py`

`KOTIBOT_JSON_FLUSH_SECONDS`

### `server_core/paths.py`

`KOTIBOT_DATA_DIR`, `LOCALAPPDATA`, `XDG_DATA_HOME`

### `server_core/preflight.py`

No literal candidate keys.

### `server_core/routes.py`

`/`, `/client-rooms`, `/subsystems/<subsystem_name>/static/<path:filename>`, `Cache-Control`, `Expires`, `KOTIBOT_ACTIVITY_LOG`, `Pragma`, `X-Accel-Buffering`, `armState`, `arm_state`, `armed`, `bad`, `base_dir`, `build_dashboard_bootstrap`, `clean_arm_state`, `clean_filename_part`, `client_has_role`, `client_role_tapo`, `clients`, `current_status_payload`, `dashboard_authenticated`, `flush_json_writes`, `kotibot_session`, `login_error`, `message`, `mode`, `ok`, `pending_command`, `provisioned`, `rate`, `rooms`, `save_state`, `security`, `set_system_arm_state`, `setup`, `sse_listeners`, `state`, `state_lock`, `static_version`, `subsystems_dir`, `sync_arming_motion_detection`, `systemArmed`, `tapo_enabled`, `used_room_names`

### `server_core/security_actions.py`

`action`, `actionType`, `action_type`, `activeArmStates`, `active_arm_states`, `armState`, `armStates`, `arm_state`, `arm_states`, `cancel_door_sound_repeat`, `cancel_route_runtime`, `clean_arm_state`, `clientName`, `client_has_role`, `client_role_cam`, `client_role_dss`, `client_role_key`, `client_role_tapo`, `clients`, `contact_open`, `contact_state_value`, `deviceID`, `door_sound_repeat_allowed`, `filename`, `from_deviceID`, `from_device_id`, `from_output`, `from_trigger`, `humidity_percent`, `manufacturer`, `matter_cluster`, `matter_device_type`, `matter_kind`, `matter_kinds`, `model`, `notificationTargetDeviceID`, `notification_target_deviceID`, `provisioned`, `prune_invalid_routes_for_clients`, `prune_routes_for_client_change`, `repeat`, `repeatSound`, `routes`, `set_routes`, `sound`, `source`, `sourceDeviceID`, `source_deviceID`, `source_device_id`, `system_arm_state`, `tapo_child_avatar`, `tapo_child_category`, `tapo_child_kind`, `tapo_child_type`, `tapo_device_type`, `tapo_kind`, `targetDeviceID`, `targetID`, `targetKeyDeviceID`, `target_deviceID`, `target_device_id`, `target_id`, `target_key_deviceID`, `temperature_c`, `to_deviceID`, `to_device_id`, `to_input`, `to_kind`, `trigger`

### `server_core/state.py`

`actions`, `android_home`, `android_home_state_file`, `android_key`, `armState`, `arm_state`, `armed`, `automation_state_file`, `automation_type_device_routes`, `automation_type_tapo_recharge`, `automations`, `broadcast_state`, `calibrating`, `clean_arm_state`, `clean_zone_name`, `clientName`, `clientRole`, `client_has_role`, `client_role_cam`, `client_role_dss`, `client_role_key`, `client_role_tapo`, `clients`, `close_angle_threshold`, `deviceID`, `door_status`, `heartbeat_pending`, `heartbeat_requested_at`, `init_client`, `last_seen`, `load_state`, `matter`, `matter_device_state_file`, `needs_heartbeat`, `open_angle_threshold`, `openness_score`, `other`, `pending_command`, `provisioned`, `routes`, `save_state`, `scope`, `security_actions_file`, `set_routes`, `set_system_arm_state`, `source`, `state_file`, `system`, `system_arm_state`, `system_armed`, `tapo`, `tapo_device_state_file`, `tapo_recharge`, `tapo_recording`, `tapo_recording_enabled`, `type`, `unprovisioned`, `zone_name`

### `server_core/status.py`

`age_text`, `androidVersion`, `armState`, `arm_state`, `armed`, `aspect_ratio`, `auth`, `battery`, `battery_low`, `battery_state`, `brand`, `build_dashboard_bootstrap`, `calibrating`, `cameraTalkActive`, `cameraTalkAvailable`, `camera_auto_rotation`, `camera_auto_rotation_at`, `camera_auto_rotation_lens`, `camera_talk_active`, `camera_talk_available`, `children`, `clean_filename_part`, `clean_zone_name`, `clientName`, `clientRole`, `client_has_role`, `client_role_cam`, `client_role_dss`, `client_role_key`, `client_role_tapo`, `client_role_unp`, `client_status_sort_key`, `clients`, `contact_open`, `contact_state_value`, `control_error`, `control_ready`, `current_server_ip`, `current_status_payload`, `dashboard_auth_status`, `dashboard_authenticated`, `detectedRole`, `deviceID`, `door_status`, `doorbell_muted`, `duration_text`, `environment`, `environment_snapshot`, `frame`, `frame_age`, `frame_last_seen`, `frame_live`, `frame_seq`, `generated_at`, `generated_at_ms`, `hasDSSHW`, `heartbeat_interval_ms`, `humidity_percent`, `humidity_raw`, `ip`, `is_client_stale`, `key_status`, `last_key_state`, `last_key_state_at`, `last_motion_at`, `last_motion_score`, `last_seen`, `last_update`, `latest_frame_url`, `local_ip`, `manufacturer`, `matter_action_settings`, `matter_battery_attr_reads`, `matter_battery_charge_level`, `matter_battery_charge_state`, `matter_battery_low`, `matter_battery_percent`, `matter_battery_percent_remaining_raw`, `matter_battery_replacement_needed`, `matter_bridged_basic_reads`, `matter_button_event`, `matter_button_event_at`, `matter_button_position`, `matter_button_press_count`, `matter_cluster`, `matter_contact_open_when`, `matter_device_type`, `matter_endpoint`, `matter_hardware_version`, `matter_kind`, `matter_kinds`, `matter_last_sync_at`, `matter_node_id`, `matter_node_label`, `matter_onoff`, `matter_product_name`, `matter_reachable`, `matter_reads`, `matter_serial_number`, `matter_settings`, `matter_settings_snapshot`, `matter_software_version`, `matter_stale_client_seconds`, `matter_switch_multipress_max`, `matter_switch_position`, `matter_switch_positions`, `matter_vendor_name`, `model`, `motionActive`, `motionDetectionEnabled`, `motionDetectionThreshold`, `motionFlashlightEnabled`, `motionScreenEnabled`, `motion_active`, `motion_detection_enabled`, `motion_detection_threshold`, `motion_flashlight_enabled`, `motion_screen_enabled`, `now_epoch`, `now_local`, `occupancy_state_value`, `ok`, `openness_score`, `preview_aspect`, `preview_by_lens`, `preview_requested`, `preview_requested_for_client`, `preview_viewer_ttl_seconds`, `preview_viewers`, `provisioned`, `recording_enabled`, `selected_camera`, `server`, `server_ip`, `server_ip_address`, `server_start_epoch`, `server_time`, `server_uptime_seconds`, `server_uptime_text`, `snapshot_client`, `source`, `stale`, `stale_client_seconds`, `state_lock`, `status`, `system_arm_state`, `system_armed`, `tapoHideDashboard`, `tapoRoomPower`, `tapo_alias`, `tapo_battery`, `tapo_battery_level`, `tapo_battery_low`, `tapo_battery_percent`, `tapo_battery_state`, `tapo_brightness`, `tapo_child_avatar`, `tapo_child_category`, `tapo_child_id`, `tapo_child_kind`, `tapo_child_mac`, `tapo_child_model`, `tapo_child_name`, `tapo_child_rssi`, `tapo_child_signal_level`, `tapo_child_status`, `tapo_child_type`, `tapo_children`, `tapo_color_temperature`, `tapo_control_error`, `tapo_control_ready`, `tapo_dashboard_section`, `tapo_device_type`, `tapo_dimmable`, `tapo_hide_dashboard`, `tapo_hls_url`, `tapo_hue`, `tapo_id`, `tapo_ip`, `tapo_is_bulb`, `tapo_is_button`, `tapo_is_camera`, `tapo_is_hub`, `tapo_is_hub_child`, `tapo_is_on`, `tapo_is_outlet_extender`, `tapo_is_plug`, `tapo_is_switch`, `tapo_kind`, `tapo_lighting_state`, `tapo_lighting_state_snapshot`, `tapo_mac`, `tapo_model`, `tapo_onvif_port`, `tapo_parent_alias`, `tapo_parent_device_id`, `tapo_parent_id`, `tapo_parent_ip`, `tapo_parent_model`, `tapo_recording`, `tapo_recording_enabled`, `tapo_recording_file`, `tapo_room_power`, `tapo_saturation`, `tapo_supports_brightness`, `tapo_supports_color`, `tapo_supports_color_temp`, `tapo_supports_onvif`, `tapo_supports_power`, `tapo_supports_rtsp`, `temperature_c`, `temperature_raw`, `uptime_seconds`, `uptime_text`, `used_zones`, `version`, `visual_motion_active`, `voice_talk_active_for_target`, `zoneName`, `zone_name`

### `server_core/subsystems.py`

`KOTIBOT_ACTIVITY_LOG`, `KOTIBOT_AUTOMATIONS_LOOP`, `KOTIBOT_ENVIRONMENT_LOOP`, `KOTIBOT_ENVIRONMENT_SNAPSHOT`, `KOTIBOT_MATTER_SENSOR_SUBSCRIBE_LOOP`, `KOTIBOT_MATTER_SYNC_LOOP`, `KOTIBOT_TAPO_NORMALIZE_LOADED_CLIENTS`, `KOTIBOT_TAPO_STATE_WATCHER_LOOP`, `activities_dir`, `activity_log`, `age_text`, `app`, `apply_enabled_roles`, `automation_state_file`, `base_dir`, `broadcast_state`, `cancel_door_sound_repeat`, `cancel_motion_recording_stop`, `clean_zone_name`, `client_android_home_dir`, `client_android_key_dir`, `client_has_role`, `client_role_cam`, `client_role_dss`, `client_role_key`, `client_role_tapo`, `client_tapo_dir`, `clients`, `device_power_changed`, `door_sound_repeat_allowed`, `environment_dir`, `external_ip_check_loop`, `file_server_dir`, `fire_camera_motion_routes`, `fire_door_routes`, `fire_environment_routes`, `get_clients_for_device`, `get_routes`, `get_unprovisioned_client`, `handle_key_telemetry`, `init_client`, `is_client_stale`, `json_dumps`, `loop`, `matter_dir`, `matter_sync_stop`, `normalize_after_state_load`, `normalize_client_roles`, `now_epoch`, `now_local`, `play_wav_file`, `preview_requested_for_client`, `prune_invalid_routes_for_clients`, `prune_routes_for_client_change`, `push_queue`, `queue_door_recalibration`, `register_core_subsystems`, `register_enabled_subsystems`, `register_seen_client`, `request_json`, `routes`, `runtime`, `safe_float`, `safe_int`, `save_state`, `schedule_door_sound_repeat`, `security`, `set_routes`, `snapshot`, `snapshot_client`, `start_external_ip_loop`, `start_registered_subsystem_loops`, `state_lock`, `sync_arming_motion_detection`, `sync_device_automation_target_power`, `system_arm_state`, `system_armed`, `tapo_config_file`, `tapo_enabled`, `tapo_import_error`, `tapo_lighting_state_file`, `tapo_routes_loaded`, `tapo_watcher_stop`

### `subsystems/activities/activity_log.py`

`accent`, `alias`, `category`, `childId`, `child_id`, `child_name`, `clientName`, `detail`, `deviceID`, `deviceId`, `device_id`, `display_name`, `events`, `has_more`, `icon`, `id`, `items`, `kind`, `last_signatures`, `matter_node_label`, `matter_product_name`, `name`, `oldest_ts`, `position`, `record_initial`, `room`, `slot_number`, `source`, `state`, `status`, `tapo_alias`, `tapo_children`, `time`, `ts`, `type`, `zone`, `zoneName`, `zone_name`

### `subsystems/automations/automations_routes.py`

`/api/automations`, `KOTIBOT_AUTOMATIONS_LOOP`, `KOTIBOT_AUTOMATIONS_SECONDS`, `KOTIBOT_AUTOMATIONS_WAKE`, `KOTIBOT_REMOVE_RECHARGE_AUTOMATIONS_FOR_DEVICE`, `action`, `actionType`, `action_type`, `activeSchemes`, `activity_log`, `alias`, `autoOff`, `autoOffSeconds`, `auto_off`, `auto_off_seconds`, `automation`, `automationID`, `automation_state_file`, `automations`, `battery`, `brightness`, `broadcast_state`, `childId`, `child_id`, `child_index`, `child_position`, `children`, `clean_zone_name`, `cli_index`, `clientDeviceID`, `clientID`, `clientName`, `client_has_role`, `client_id`, `client_name`, `client_role_cam`, `client_role_dss`, `client_role_key`, `client_role_tapo`, `clients`, `colorTemperature`, `color_temperature`, `commands`, `control_error`, `control_ready`, `cooldownSeconds`, `cooldown_seconds`, `dashboard_section`, `dayReset`, `device`, `deviceID`, `deviceIDs`, `deviceName`, `device_automations`, `device_id`, `device_name`, `device_type`, `dimmable`, `display_name`, `durationSeconds`, `duration_seconds`, `enabled`, `error`, `filename`, `from_deviceID`, `from_output`, `fullBattery`, `heartbeat_interval_ms`, `hue`, `id`, `index`, `installedTypes`, `ip`, `is_bulb`, `is_camera`, `is_on`, `is_outlet_extender`, `is_plug`, `item`, `key`, `kind`, `label`, `lastRunDate`, `last_seen`, `loaded`, `lowBattery`, `message`, `minimumDurationSeconds`, `minimum_duration_seconds`, `mode`, `modeConfig`, `model`, `name`, `now_epoch`, `ok`, `position`, `preset`, `provisioned`, `repeat`, `repeatSeconds`, `repeat_seconds`, `resetHour`, `result`, `retrigger`, `safe_int`, `saturation`, `save_state`, `schemes`, `snapshot_client`, `soundVolume`, `sound_volume`, `source`, `sourceDeviceID`, `state_lock`, `supports_brightness`, `supports_color`, `supports_color_temp`, `supports_power`, `tapo_alias`, `tapo_brightness`, `tapo_children`, `tapo_color_temperature`, `tapo_control_error`, `tapo_control_ready`, `tapo_dashboard_section`, `tapo_device_type`, `tapo_dimmable`, `tapo_hue`, `tapo_id`, `tapo_ip`, `tapo_is_bulb`, `tapo_is_camera`, `tapo_is_on`, `tapo_is_outlet_extender`, `tapo_is_plug`, `tapo_kind`, `tapo_lighting_state_file`, `tapo_model`, `tapo_recharge`, `tapo_saturation`, `tapo_supports_brightness`, `tapo_supports_color`, `tapo_supports_color_temp`, `tapo_supports_power`, `targetDeviceID`, `targetID`, `targetKeyDeviceID`, `targetName`, `target_key_deviceID`, `targets`, `threshold`, `thresholdUnit`, `threshold_unit`, `timer_seconds`, `title`, `to_deviceID`, `to_input`, `to_kind`, `trigger`, `type`, `value`

### `subsystems/automations/trigger_routes.py`

`KOTIBOT_CANCEL_AUTOMATION_ROUTE_RUNTIME`, `KOTIBOT_TAPO_RECOVER_DESIRED_LIGHTING`, `action`, `actionType`, `action_type`, `activeArmStates`, `active_arm_states`, `activity_log`, `alias`, `armState`, `armStates`, `arm_state`, `arm_states`, `autoOff`, `autoOffSeconds`, `auto_off`, `auto_off_seconds`, `automationID`, `body`, `brightness`, `broadcast_state`, `cancel_door_sound_repeat`, `childId`, `childIndex`, `childPosition`, `child_id`, `child_index`, `child_name`, `child_position`, `children`, `cli_index`, `clientName`, `client_has_role`, `client_role_cam`, `client_role_key`, `clients`, `color_temperature`, `control_error`, `control_ready`, `cooldownSeconds`, `cooldown_seconds`, `dashboard_section`, `device`, `deviceID`, `deviceId`, `device_id`, `device_type`, `dimmable`, `display_name`, `door_close`, `door_open`, `doorbell_muted`, `durationSeconds`, `duration_seconds`, `enabled`, `error`, `eventTime`, `fcm_token`, `filename`, `fire_camera_motion_routes`, `fire_door_routes`, `fire_environment_routes`, `from_deviceID`, `from_device_id`, `from_output`, `from_trigger`, `get_clients_for_device`, `get_routes`, `hue`, `humidity_above`, `humidity_below`, `id`, `index`, `ip`, `is_bulb`, `is_camera`, `is_on`, `is_outlet_extender`, `is_plug`, `kind`, `last_notification_at`, `message`, `minDurationSeconds`, `min_duration_seconds`, `minimumDurationSeconds`, `minimum_duration_seconds`, `model`, `motion`, `motionDetectionEnabled`, `motion_active`, `motion_detection_enabled`, `motion_flashlight_enabled`, `motion_recording_active`, `motion_screen_enabled`, `name`, `notificationTargetDeviceID`, `notification_target_deviceID`, `notification_title`, `now_epoch`, `now_local`, `off`, `ok`, `on`, `pending_command`, `play_wav_file`, `position`, `powerAction`, `power_action`, `provisioned`, `push_queue`, `recordingDurationSeconds`, `recordingEnabled`, `recording_duration_seconds`, `recording_enabled`, `repeat`, `repeatSeconds`, `repeatSound`, `repeat_seconds`, `retrigger`, `retriggerTimer`, `route_recording_until`, `routes`, `saturation`, `save_state`, `schedule_door_sound_repeat`, `scope`, `sensor_clear`, `set_routes`, `slot_number`, `sound`, `soundVolume`, `sound_volume`, `sourceClientName`, `sourceDeviceID`, `source_deviceID`, `source_device_id`, `state_lock`, `supports_brightness`, `supports_color`, `supports_color_temp`, `supports_power`, `sync_arming_motion_detection`, `sync_device_automation_target_power`, `system_arm_state`, `tapo_alias`, `tapo_brightness`, `tapo_children`, `tapo_color_temperature`, `tapo_control_error`, `tapo_control_ready`, `tapo_dashboard_section`, `tapo_device_type`, `tapo_dimmable`, `tapo_hue`, `tapo_id`, `tapo_ip`, `tapo_is_bulb`, `tapo_is_camera`, `tapo_is_on`, `tapo_is_outlet_extender`, `tapo_is_plug`, `tapo_kind`, `tapo_model`, `tapo_recording`, `tapo_recording_enabled`, `tapo_recording_file`, `tapo_saturation`, `tapo_supports_brightness`, `tapo_supports_color`, `tapo_supports_color_temp`, `tapo_supports_power`, `targetDeviceID`, `targetID`, `targetKeyDeviceID`, `targetRole`, `target_deviceID`, `target_device_id`, `target_id`, `target_key_deviceID`, `temperature_above`, `temperature_below`, `threshold`, `thresholdUnit`, `threshold_unit`, `timerSeconds`, `timer_seconds`, `title`, `to_deviceID`, `to_device_id`, `to_input`, `to_kind`, `trigger`, `volume`, `volumePercent`, `volume_percent`

### `subsystems/bluetooth/bluetooth_routes.py`

`action`, `adapter`, `address`, `alias`, `blocked`, `command_error`, `connect`, `connected`, `device`, `devices`, `disconnect`, `discoverable`, `discoverable_off`, `discoverable_on`, `discovering`, `error`, `json_dumps`, `name`, `ok`, `pair`, `pairable`, `pairable_off`, `pairable_on`, `paired`, `pairing`, `power_off`, `power_on`, `powered`, `remove`, `request_json`, `returncode`, `rssi`, `safe_int`, `seconds`, `status`, `stderr`, `stdout`, `trust`, `trusted`, `untrust`

### `subsystems/client-android-home/client_android_home_telemetry.py`

`KOTIBOT_AUTOMATIONS_WAKE`, `X-Client-Role`, `X-Device-ID`, `X-Forwarded-For`, `X-Koti-Frame-Captured-Ms`, `activity_log`, `armed`, `aspect_ratio`, `battery`, `broadcast_state`, `calibrating`, `cameraEnabled`, `cameraTargetRotation`, `camera_auto_rotation`, `camera_auto_rotation_at`, `camera_auto_rotation_lens`, `camera_frame_motion_score`, `camera_target_rotation`, `cancel_door_sound_repeat`, `cancel_motion_recording_stop`, `clientName`, `clientRole`, `client_has_role`, `client_role_cam`, `client_role_dss`, `client_role_key`, `client_role_tapo`, `deviceID`, `deviceName`, `doorAngle`, `door_angle`, `door_event_ms`, `door_recalibration_active_timeout_seconds`, `door_recalibration_command_timeout_seconds`, `door_recalibration_hold_seconds`, `door_status`, `error`, `eventTimeMs`, `event_time_ms`, `fire_camera_motion_routes`, `fire_door_routes`, `frame`, `frame_captured_ms`, `frame_last_seen`, `frame_seq`, `get_clients_for_device`, `get_unprovisioned_client`, `handle_camera_motion_detected`, `handle_door_telemetry`, `handle_key_telemetry`, `heartbeat_pending`, `heartbeat_requested_at`, `ignore_door_open_until_closed`, `ip`, `last_motion_at`, `last_motion_score`, `last_seen`, `last_transition_at`, `motionAlertFlashlightUntilMs`, `motionAlertScreenUntilMs`, `motionDetected`, `motionDetectionEnabled`, `motionDetectionThreshold`, `motionScore`, `motionThreshold`, `motion_active`, `motion_detected`, `motion_detection_enabled`, `motion_detection_threshold`, `motion_flashlight_enabled`, `motion_probe_pixels`, `motion_recording_active`, `motion_score`, `motion_screen_enabled`, `name`, `needs_heartbeat`, `normalize_client_roles`, `now_epoch`, `ok`, `openDoor`, `open_door`, `opendoor`, `opennessScore`, `openness_score`, `pending_command`, `previewAspect`, `previewRequest`, `previewRequested`, `preview_by_lens`, `preview_requested_for_client`, `provisioned`, `recalibration_ignore_until`, `recalibration_phase`, `recordingEnabled`, `recording_enabled`, `register_seen_client`, `resolvedCameraRotation`, `resolved_camera_rotation`, `safe_float`, `safe_int`, `save_state`, `selectedCamera`, `selected_camera`, `serverPort`, `snapshot_client`, `state_lock`, `systemArmed`, `system_armed`, `tapo_kind`, `type`

### `subsystems/client-tapo/tapo_admin_routes.py`

`base_dir`, `client_has_role`, `client_role_tapo`, `clients`, `detectedRole`, `enabled`, `error`, `from_deviceID`, `get_routes`, `loaded`, `ok`, `restarting`, `save_state`, `set_routes`, `state_lock`, `tapo_config_file`, `tapo_disable`, `tapo_enable`, `tapo_enabled`, `tapo_import_error`, `tapo_routes_loaded`, `tapo_status`, `to_deviceID`

### `subsystems/client-tapo/tapo_control.py`

`Battery`, `Battery Level`, `Battery Percent`, `Battery Percentage`, `Device Id (hash)`, `Device Model`, `Device Type`, `Encrypt Type`, `HTTP Port`, `IP`, `KASA_PASSWORD`, `KASA_USERNAME`, `KOTIBOT_TAPO_RECORDING_DIR`, `Login version`, `MAC`, `Owner (hash)`, `State`, `Status`, `TAPO_CACHE_SECONDS`, `TAPO_CAMERA_PASSWORD`, `TAPO_CAMERA_RTSP_PATH`, `TAPO_CAMERA_USERNAME`, `TAPO_DEVICE_CALL_TIMEOUT_SECONDS`, `TAPO_DEVICE_CONNECT_TIMEOUT_SECONDS`, `TAPO_DEVICE_REFRESH_TIMEOUT_SECONDS`, `TAPO_PASSWORD`, `TAPO_USERNAME`, `action`, `alias`, `at_low_battery`, `avatar`, `battery`, `battery_level`, `battery_low`, `battery_percent`, `battery_state`, `brightness`, `category`, `childDeviceList`, `childDevices`, `childId`, `childIndex`, `childModel`, `childPosition`, `child_device_list`, `child_devices`, `child_id`, `child_index`, `child_model`, `child_position`, `children`, `cliIndex`, `cli_index`, `clientName`, `color_temp`, `color_temperature`, `colour_temperature`, `control_error`, `control_ready`, `dashboard_section`, `device`, `deviceID`, `deviceId`, `deviceModel`, `deviceType`, `device_id`, `device_id_hash`, `device_model`, `device_on`, `device_type`, `devices`, `dimmable`, `dir`, `discovery_state`, `encrypt_type`, `get_child_device_list`, `http_port`, `hue`, `id`, `index`, `ip`, `is_bulb`, `is_camera`, `is_light`, `is_on`, `is_outlet_extender`, `is_plug`, `is_usb`, `items`, `kind`, `last_command_at`, `last_seen`, `last_viewer_at`, `login_version`, `mac`, `model`, `name`, `native_fade_error`, `native_fade_off_seconds`, `native_fade_on_seconds`, `native_fade_ready`, `nickname`, `ok`, `on`, `originalDeviceId`, `original_device_id`, `outletId`, `outlet_id`, `owner_hash`, `parentDeviceId`, `parent_device_id`, `path`, `position`, `proc`, `raw`, `rssi`, `saturation`, `signal_level`, `slot_number`, `started_at`, `state`, `status`, `supported`, `supports_brightness`, `supports_color`, `supports_color_temp`, `supports_power`, `tapo_alias`, `tapo_ip`, `tapo_model`, `type`, `zone_name`

### `subsystems/client-tapo/tapo_extenders.py`

`alias`, `childId`, `child_id`, `cli_index`, `clientName`, `deviceId`, `device_id`, `id`, `index`, `is_light`, `is_on`, `is_outlet`, `is_usb`, `kind`, `name`, `nickname`, `originalDeviceId`, `original_device_id`, `position`, `raw`, `status`, `supports_brightness`, `supports_color`, `supports_color_temp`, `supports_power`, `tapo_alias`, `tapo_child_id`, `tapo_child_index`, `tapo_child_kind`, `tapo_child_name`, `tapo_child_position`, `tapo_hide_dashboard`, `tapo_is_bulb`, `tapo_is_outlet_child`, `tapo_is_plug`, `tapo_kind`, `tapo_room_power`, `tapo_supports_power`

### `subsystems/client-tapo/tapo_routes.py`

`/api/tapo/camera-hls/<stream_key>/<path:filename>`, `/api/tapo/debug-discovery`, `/api/tapo/devices`, `/api/tapo/lighting-state`, `/api/tapo/recharge`, `Cache-Control`, `Expires`, `KOTIBOT_AUTOMATIONS_WAKE`, `KOTIBOT_REMOVE_RECHARGE_AUTOMATIONS_FOR_DEVICE`, `KOTIBOT_TAPO_COMMAND_WORKERS`, `KOTIBOT_TAPO_DISCOVERY_SECONDS`, `KOTIBOT_TAPO_LIGHTING_STATE_SNAPSHOT`, `KOTIBOT_TAPO_NORMALIZE_LOADED_CLIENTS`, `KOTIBOT_TAPO_RECOVER_DESIRED_LIGHTING`, `KOTIBOT_TAPO_STATE_WATCHER_LOOP`, `KOTIBOT_TAPO_WATCHER_SECONDS`, `Pragma`, `_client_deviceID`, `action`, `actions`, `active`, `activeHomeMode`, `activeSchemes`, `activity_log`, `alias`, `automation_state_file`, `automations`, `battery`, `battery_level`, `battery_percent`, `brightness`, `broadcast_state`, `bulb`, `busy`, `camera`, `cameraEnabled`, `camera_enabled`, `childId`, `childIndex`, `childPosition`, `child_id`, `child_index`, `child_name`, `child_position`, `children`, `clean_zone_name`, `cliIndex`, `cli_index`, `client`, `clientName`, `clientRole`, `client_has_role`, `client_name`, `client_role_tapo`, `clients`, `colorTemperature`, `color_temperature`, `commands`, `control_error`, `control_ready`, `count`, `current_power_w`, `dashboard_section`, `day`, `deferred`, `desired`, `detectedRole`, `device`, `deviceID`, `deviceIDs`, `deviceId`, `deviceName`, `device_id`, `device_id_hash`, `device_ids`, `device_name`, `device_power_changed`, `device_type`, `devices`, `dimmable`, `display_name`, `distance`, `enabled`, `energy_available`, `energy_error`, `energy_updated_at`, `error`, `evening`, `failedCount`, `favorite`, `force`, `fullBattery`, `home`, `hub`, `hue`, `icon`, `id`, `index`, `init_client`, `ip`, `is_bulb`, `is_camera`, `is_hub`, `is_on`, `is_outlet_extender`, `is_plug`, `item`, `key`, `kind`, `label`, `last_seen`, `lightingMode`, `lightingRecovered`, `lighting_mode`, `lightstrip`, `loaded`, `lowBattery`, `mac`, `mode`, `modeConfig`, `model`, `month_energy_kwh`, `month_runtime_minutes`, `movie`, `name`, `newName`, `nightlight`, `now_epoch`, `ok`, `okCount`, `onvif_port`, `originalDeviceId`, `original_device_id`, `outletId`, `outlet_extender`, `outlet_id`, `pendingPowerKeys`, `plug`, `position`, `power`, `preset`, `previewRequested`, `previewRotation`, `preview_by_lens`, `preview_requested`, `preview_viewers`, `provisioned`, `prune_routes_for_client_change`, `raw`, `recharge`, `recording`, `recordingEnabled`, `refresh_clients`, `removed`, `results`, `retryable`, `room`, `room_name`, `rotation`, `rules`, `safe_int`, `saturation`, `save_state`, `savedAt`, `schemes`, `seconds`, `selected_camera`, `slot_number`, `snapshot_client`, `source`, `stage`, `state_lock`, `supported`, `supports_brightness`, `supports_color`, `supports_color_temp`, `supports_energy`, `supports_onvif`, `supports_power`, `supports_rtsp`, `tapo`, `tapoChildId`, `tapoHideDashboard`, `tapoRoomPower`, `tapoRoomPowerChildren`, `tapo_alias`, `tapo_battery`, `tapo_battery_level`, `tapo_battery_percent`, `tapo_brightness`, `tapo_child_kind`, `tapo_child_name`, `tapo_children`, `tapo_children_initialized`, `tapo_color_temperature`, `tapo_control_error`, `tapo_control_ready`, `tapo_current_power_w`, `tapo_dashboard_section`, `tapo_desired_brightness`, `tapo_desired_color_temperature`, `tapo_desired_hue`, `tapo_desired_lighting_mode`, `tapo_desired_lighting_updated_at`, `tapo_desired_saturation`, `tapo_desired_white_saturation`, `tapo_device_type`, `tapo_dimmable`, `tapo_energy_available`, `tapo_energy_error`, `tapo_energy_updated_at`, `tapo_hide_dashboard`, `tapo_hls_url`, `tapo_hue`, `tapo_id`, `tapo_ip`, `tapo_is_bulb`, `tapo_is_camera`, `tapo_is_hub`, `tapo_is_hub_child`, `tapo_is_on`, `tapo_is_outlet_extender`, `tapo_is_plug`, `tapo_kind`, `tapo_lighting_state_file`, `tapo_mac`, `tapo_model`, `tapo_month_energy_kwh`, `tapo_month_runtime_minutes`, `tapo_onvif_port`, `tapo_pending_power_commands`, `tapo_recharge`, `tapo_recording`, `tapo_recording_enabled`, `tapo_recording_file`, `tapo_room_power`, `tapo_room_power_children`, `tapo_rtsp_url`, `tapo_saturation`, `tapo_supports_brightness`, `tapo_supports_color`, `tapo_supports_color_temp`, `tapo_supports_energy`, `tapo_supports_onvif`, `tapo_supports_power`, `tapo_supports_rtsp`, `tapo_today_energy_kwh`, `tapo_today_runtime_minutes`, `tapo_watcher_stop`, `targetDeviceID`, `targetID`, `targets`, `today_energy_kwh`, `today_runtime_minutes`, `type`, `updatedAt`, `vacuum`, `value`, `viewerId`, `whiteSaturation`, `white_saturation`, `zoneName`, `zone_name`

### `subsystems/client-tapo/tapo_types.py`

`children`, `dashboard_section`, `is_bulb`, `is_camera`, `is_hub`, `is_outlet_extender`, `is_plug`, `kind`, `onvif_port`, `rtsp_url`, `supported`, `supports_brightness`, `supports_children`, `supports_color`, `supports_color_temp`, `supports_energy`, `supports_onvif`, `supports_power`, `supports_rtsp`

### `subsystems/environment/environment_routes.py`

`/api/environment/debug`, `/api/environment/settings`, `/api/environment/status`, `@id`, `Accept`, `CO`, `KOTIBOT_NOAA_USER_AGENT`, `NO2`, `OZONE`, `SO2`, `User-Agent`, `airQualitySource`, `air_quality`, `air_quality_source`, `aqi`, `aqi_text`, `base_dir`, `broadcast_state`, `candidates`, `cards`, `children`, `city`, `clientName`, `clientRole`, `client_count`, `clients`, `color`, `command`, `condition`, `coordinates`, `deviceID`, `devices`, `distance_miles`, `dominant_pollutant`, `enabled`, `endpoint`, `environment_dir`, `environment_stop`, `error`, `exists`, `features`, `geometry`, `humidity_percent`, `humidity_raw`, `humidity_status`, `humidity_text`, `icon`, `id`, `indoor`, `indoor_devices`, `kind`, `kinds`, `label`, `last_command`, `last_seen`, `latitude`, `location`, `longitude`, `lookup_source`, `loop`, `matter_children`, `matter_kind`, `matter_kinds`, `matter_last_sync_at`, `matter_node_label`, `matter_state`, `model`, `name`, `node_id`, `nodes`, `now_epoch`, `observationStations`, `official_label`, `ok`, `outdoor`, `parameter`, `path`, `place name`, `places`, `pollutants`, `properties`, `refresh`, `refreshSeconds`, `refresh_seconds`, `refresh_weather`, `reporting_area`, `returncode`, `role`, `settings`, `snapshot`, `source`, `source_id`, `sources`, `state`, `state abbreviation`, `state_file`, `state_file_exists`, `state_lock`, `station`, `stationIdentifier`, `station_id`, `station_source`, `stations_checked`, `status`, `stderr`, `stderr_tail`, `stdout`, `stdout_tail`, `temperature_c`, `temperature_f`, `temperature_raw`, `temperature_status`, `temperature_text`, `textDescription`, `timestamp`, `updated_at`, `url`, `value`, `weatherSource`, `weather_cache`, `weather_cache_keys`, `weather_source`, `zipCode`, `zip_code`, `zoneName`, `zone_name`

### `subsystems/file-server/file_server_routes.py`

`error`, `filename`, `files`, `kind`, `modified`, `ok`, `size`, `url`, `version`

### `subsystems/matter/matter_routes.py`

`/api/matter/snapshot`, `/api/matter/status`, `/api/matter/sync`, `KOTIBOT_MATTER_RUNTIME`, `KOTIBOT_MATTER_SENSOR_SUBSCRIBE_LOOP`, `KOTIBOT_MATTER_SETTINGS_SNAPSHOT`, `KOTIBOT_MATTER_SYNC_LOOP`, `__loop__`, `active`, `activity_log`, `androidVersion`, `armed`, `auto`, `backup`, `base_dir`, `battery`, `battery_attr_reads`, `battery_low`, `battery_state`, `brand`, `bridged_basic`, `bridged_basic_reads`, `broadcast_state`, `busy`, `button`, `calibrating`, `children`, `client`, `clientName`, `clientRole`, `client_role_dss`, `clients`, `clusters`, `contact`, `contact_open`, `contact_state_value`, `detectedRole`, `deviceID`, `device_count`, `devices`, `door_angle`, `door_event_ms`, `door_status`, `doorbell_muted`, `endpoint`, `environment`, `error`, `fcm_token`, `fcm_token_at`, `fire_camera_motion_routes`, `fire_door_routes`, `fire_environment_routes`, `force_discovery`, `hardware_version_string`, `hasDSSHW`, `heartbeat_pending`, `heartbeat_requested_at`, `humidity`, `humidity_percent`, `humidity_raw`, `ip`, `kind`, `kinds`, `last_motion_at`, `last_seen`, `last_transition_at`, `manufacturer`, `matter_battery_attr_reads`, `matter_battery_charge_level`, `matter_battery_charge_state`, `matter_battery_low`, `matter_battery_percent`, `matter_battery_percent_remaining_raw`, `matter_battery_replacement_needed`, `matter_bridged_basic_reads`, `matter_button_event`, `matter_button_event_at`, `matter_button_position`, `matter_button_press_count`, `matter_cluster`, `matter_contact_open_when`, `matter_device_type`, `matter_dir`, `matter_endpoint`, `matter_hardware_version`, `matter_kind`, `matter_kinds`, `matter_last_sync_at`, `matter_node_id`, `matter_node_label`, `matter_onoff`, `matter_product_name`, `matter_reachable`, `matter_reads`, `matter_serial_number`, `matter_software_version`, `matter_switch_multipress_max`, `matter_switch_position`, `matter_switch_positions`, `matter_sync_stop`, `matter_vendor_name`, `max_interval`, `min_interval`, `model`, `motion`, `motion_active`, `name`, `needs_heartbeat`, `node_id`, `node_label`, `now_epoch`, `occupancy_state_value`, `ok`, `openness_score`, `output`, `pending_command`, `position`, `previous_value`, `product_name`, `provisioned`, `reachable`, `reads`, `received_at`, `returncode`, `runtime`, `save_state`, `serial_number`, `settings`, `snapshot`, `snapshots`, `software_version_string`, `source`, `stale`, `state`, `state_lock`, `status`, `switch`, `sync_ok`, `telemetry_count`, `temperature`, `temperature_c`, `temperature_raw`, `updated_at`, `value`, `vendor_name`, `version`, `zone_name`

### `subsystems/matter/matter_runtime.py`

`KOTIBOT_MATTER_BYPASS_ATTESTATION`, `KOTIBOT_MATTER_CHIP_TOOL`, `KOTIBOT_MATTER_DISCOVERY_TTL_SECONDS`, `alias`, `attempted`, `attribute`, `auto`, `backup`, `battery`, `battery_attr_reads`, `battery_low`, `battery_state`, `boolean-state`, `boolean_state`, `bridged_basic`, `bridged_basic_reads`, `button`, `button_attr_reads`, `bypass_attestation`, `children`, `chip_cluster`, `chip_tool`, `chip_tool_found`, `chip_tool_storage`, `cluster`, `cluster_id`, `cluster_name`, `clusters`, `color-control`, `color_control`, `color_temperature_mireds`, `command`, `contact`, `contact_open`, `contact_state_value`, `current_level`, `current_position`, `device_type_list`, `discovery`, `enabled`, `endpoint`, `endpoints`, `error`, `event_count`, `finished_at`, `forceDiscovery`, `force_discovery`, `generic-switch`, `generic_switch`, `hardware_version_string`, `humidity`, `humidity_percent`, `humidity_raw`, `inspection`, `kind`, `kinds`, `label`, `labels`, `last_command`, `last_inspection`, `last_inspection_at`, `level`, `level-control`, `level_control`, `manufacturer`, `matter_battery_charge_level`, `matter_battery_charge_state`, `matter_battery_low`, `matter_battery_percent`, `matter_battery_percent_remaining_raw`, `matter_battery_replacement_needed`, `matter_button_position`, `matter_children`, `matter_discovered_at`, `matter_discovery`, `matter_hardware_version`, `matter_kind`, `matter_kinds`, `matter_node_label`, `matter_onoff`, `matter_product_name`, `matter_reachable`, `matter_serial_number`, `matter_software_version`, `matter_switch_multipress_max`, `matter_switch_position`, `matter_switch_positions`, `matter_vendor_name`, `maxInterval`, `max_interval`, `minInterval`, `min_interval`, `mireds`, `model`, `momentary-switch`, `momentary_switch`, `motion`, `motion_active`, `multi_press_max`, `name`, `node`, `nodeID`, `nodeIDs`, `node_id`, `node_ids`, `node_label`, `nodes`, `notes`, `number_of_positions`, `occupancy`, `occupancy_sensing`, `occupancy_state_value`, `ok`, `on-off`, `on_off`, `onoff`, `parsed`, `parts`, `parts_list`, `parts_reads`, `product_name`, `reachable`, `reads`, `received_at`, `recommissioned_at`, `relative_humidity`, `returncode`, `rolled_back`, `serial_number`, `server_list`, `settings`, `setupCode`, `setup_code`, `snapshots`, `software_version_string`, `source`, `started_at`, `stderr`, `stdout`, `subscription_command`, `switch`, `temperature`, `temperatureUnit`, `temperature_c`, `temperature_measurement`, `temperature_raw`, `temperature_unit`, `transitionTime`, `transition_time`, `updated_at`, `valid`, `value`, `value_kind`, `values`, `vendor_name`

### `subsystems/network/external_ip.py`

`Accept`, `Authorization`, `Content-Type`, `KOTIBOT_CLOUDFLARE_API_TOKEN`, `KOTIBOT_CLOUDFLARE_RECORD_ID`, `KOTIBOT_CLOUDFLARE_RECORD_TYPE`, `KOTIBOT_CLOUDFLARE_ZONE_ID`, `KOTIBOT_EXTERNAL_IP_CHECK_LOOP`, `KOTIBOT_EXTERNAL_IP_CHECK_SECONDS`, `KOTIBOT_EXTERNAL_IP_STOP`, `KOTIBOT_PUBLIC_HOSTNAME`, `User-Agent`, `content`, `dns_last_set`, `id`, `last_seen`, `name`, `proxied`, `result`, `success`, `ttl`, `type`

### `subsystems/notifications/kotibot_push.py`

`Authorization`, `Content-Type`, `android`, `body`, `channel_id`, `data`, `deviceID`, `error`, `event_type`, `message`, `notification`, `ok`, `priority`, `reason`, `response`, `skipped`, `sound`, `status`, `title`, `token`, `ts`

### `subsystems/security/kotibot_security.py`

`/api/security/status`, `KOTIBOT_ALLOWED_ORIGINS`, `KOTIBOT_DASHBOARD_EMAIL`, `KOTIBOT_DASHBOARD_PASSWORD`, `KOTIBOT_TRUSTED_PROXY_CIDRS`, `Origin`, `Referer`, `Retry-After`, `Sec-Fetch-Site`, `TRUSTED_HOSTS`, `X-Device-ID`, `X-Forwarded-For`, `X-Koti-Body-SHA256`, `X-Koti-Key-ID`, `X-Koti-Nonce`, `X-Koti-Signature`, `X-Koti-Timestamp`, `allowed_origins`, `alreadyIssued`, `audit_file`, `created_at`, `current`, `dashboard_authenticated`, `dashboard_email`, `dashboard_login_mode`, `dashboard_password_hash`, `dashboard_session_count`, `dashboard_sessions`, `dashboard_user`, `dashboard_user_count`, `dashboard_users`, `deviceID`, `deviceId`, `device_enrollments`, `device_key_count`, `device_keys`, `email`, `enabled`, `enrollmentExpiresAt`, `enrollmentPending`, `enrollmentToken`, `error`, `event`, `expires_at`, `host`, `ip`, `issued_at`, `keyID`, `keyId`, `key_id`, `kid`, `last_seen_at`, `message`, `method`, `nonces`, `ok`, `password`, `password_hash`, `path`, `port`, `previous`, `removed`, `replaced_existing_dashboard_users`, `revoked_at`, `rotate`, `rotated_at`, `scheme`, `secret`, `session_secret`, `session_version`, `state_file`, `status`, `storeThisOnClient`, `token_hash`, `trusted_proxy_networks`, `ts`, `updated_at`, `user_version`

### `subsystems/soundboard/soundboard_routes.py`

`KOTIBOT_SOUNDBOARD_CANCEL_DOOR_REPEAT`, `KOTIBOT_SOUNDBOARD_PLAY_WAV_FILE`, `KOTIBOT_SOUNDBOARD_SCHEDULE_DOOR_REPEAT`, `alarm`, `alarms`, `base_dir`, `bell`, `bells`, `buzzer`, `buzzers`, `calibrating`, `cancel_door_sound_repeat`, `categories`, `category`, `clients`, `deviceID`, `display_name`, `door_sound_repeat_allowed`, `door_status`, `filename`, `files`, `ok`, `play_wav_file`, `schedule_door_sound_repeat`, `state_lock`, `volume`, `volume_percent`, `wav_dir`, `wavs`

### `subsystems/video/video_routes.py`

`application/octet-stream`, `autoRotation`, `base_dir`, `broadcast_state`, `clean_zone_name`, `clientCorrection`, `clientName`, `clientRole`, `client_has_role`, `client_name`, `client_role_cam`, `clients`, `deviceID`, `effectiveRotation`, `error`, `filename`, `last_seen`, `last_video_at`, `last_video_auto_rotation`, `last_video_client_correction`, `last_video_effective_rotation`, `last_video_file`, `last_video_lens`, `last_video_path`, `last_video_probed_rotation`, `last_video_rotation`, `last_video_rotation_applied`, `last_video_rotation_error`, `last_video_rotation_source`, `last_video_state_rotation`, `last_video_state_rotation_source`, `now_epoch`, `ok`, `path`, `probedRotation`, `provisioned`, `rotate`, `rotation`, `rotationApplied`, `rotationError`, `rotationSource`, `safe_int`, `save_state`, `segmentIndex`, `segmentStartMs`, `selectedCamera`, `selected_camera`, `side_data_list`, `stateRotation`, `stateRotationSource`, `state_lock`, `streams`, `tags`, `video`, `video/mp4`, `video/quicktime`, `video/webm`, `video/x-matroska`, `videoCorrectionDegrees`, `video_correction_degrees`, `zoneName`, `zone_name`

### `subsystems/voice/voice_routes.py`

`/api/camera-talk/session/<sessionID>`, `/api/voice/session/<sessionID>`, `KOTIBOT_CAMERA_TALK_CONNECTED_TTL_SECONDS`, `KOTIBOT_CAMERA_TALK_DISABLE_DEFAULT_STUN`, `KOTIBOT_CAMERA_TALK_ENDED_TTL_SECONDS`, `KOTIBOT_CAMERA_TALK_ICE_SERVERS`, `KOTIBOT_CAMERA_TALK_PENDING_ACTIVE_POLL_MS`, `KOTIBOT_CAMERA_TALK_PENDING_IDLE_POLL_MS`, `KOTIBOT_CAMERA_TALK_PENDING_TTL_SECONDS`, `KOTIBOT_CAMERA_TALK_STUN_URLS`, `KOTIBOT_CAMERA_TALK_TURN_CREDENTIAL`, `KOTIBOT_CAMERA_TALK_TURN_URLS`, `KOTIBOT_CAMERA_TALK_TURN_USERNAME`, `KOTIBOT_VOICE_TALK_ACTIVE_FOR_TARGET`, `X-Device-ID`, `action_type`, `answer`, `at`, `candidate`, `clientCandidates`, `client_candidates`, `client_claimed_at`, `client_has_role`, `client_role_cam`, `client_role_key`, `client_role_tapo`, `clients`, `createdAt`, `created_at`, `credential`, `dashboardCandidates`, `dashboard_candidates`, `deviceID`, `ended`, `endedBy`, `ended_by`, `error`, `fcm`, `fcm_token`, `iceServers`, `id`, `is_client_stale`, `now_epoch`, `offer`, `ok`, `pollAfterMs`, `provisioned`, `push_queue`, `queued`, `reason`, `sdp`, `session`, `sessionID`, `sessions`, `skipped`, `sourceDeviceID`, `state`, `state_lock`, `tapo_kind`, `targetDeviceID`, `type`, `updatedAt`, `updated_at`, `urls`, `username`

### `tests/test_security_policy.py`

`Origin`

## Browser storage names

| Storage | Key/database name | Source location |
| --- | --- | --- |
| `localStorage` | `cardDebugInfo` | `static/js/dashboard-actions.js:6339` |
| `localStorage` | `cardDebugInfo` | `static/js/dashboard-actions.js:6807` |
| `localStorage` | `dashboardActiveRoomFilter` | `static/js/dashboard-state.js:216` |
| `localStorage` | `dashboardDefaultsVersion` | `static/js/dashboard-state.js:33` |
| `localStorage` | `dashboardDefaultsVersion` | `static/js/dashboard-state.js:41` |
| `localStorage` | `dashboardGroupByRoom` | `static/js/dashboard-actions.js:6319` |
| `localStorage` | `dashboardGroupByRoom` | `static/js/dashboard-actions.js:6597` |
| `localStorage` | `dashboardInfoShown` | `static/js/dashboard-actions.js:6340` |
| `localStorage` | `dashboardInfoShown` | `static/js/dashboard-main.js:654` |
| `localStorage` | `dashboardMaxColumns` | `static/js/dashboard-actions.js:6589` |
| `localStorage` | `dashboardMaxColumns` | `static/js/dashboard-state.js:217` |
| `localStorage` | `dashboardPage` | `static/js/dashboard-state.js:77` |
| `localStorage` | `dashboardPage` | `static/js/dashboard-state.js:102` |
| `localStorage` | `dashboardSelectedCameraId` | `static/js/dashboard-render.js:1581` |
| `localStorage` | `dashboardSelectedCameraId` | `static/js/dashboard-render.js:1588` |
| `localStorage` | `dashboardSelectedCameraId` | `static/js/dashboard-render.js:1600` |
| `localStorage` | `dashboardSpacing` | `static/js/dashboard-actions.js:6588` |
| `localStorage` | `dashboardSpacing` | `static/js/dashboard-main.js:678` |
| `localStorage` | `dashboardSpacing` | `static/js/dashboard-state.js:40` |
| `localStorage` | `dashboardSpacing` | `static/js/dashboard-state.js:215` |
| `localStorage` | `dashboardTextSize` | `static/js/dashboard-actions.js:6363` |
| `localStorage` | `dashboardTextSize` | `static/js/dashboard-actions.js:6368` |
| `localStorage` | `dashboardTextSize` | `static/js/dashboard-actions.js:6373` |
| `localStorage` | `dashboardTheme` | `templates/index.html:18` |
| `localStorage` | `debugMode` | `static/js/dashboard-actions.js:6341` |
| `localStorage` | `kotibot.tapo.activeLightSchemes` | `subsystems/client-tapo/static/js/tapo-actions.js:2149` |
| `localStorage` | `kotibot.tapo.lightSchemes` | `subsystems/client-tapo/static/js/tapo-actions.js:2148` |
| `localStorage` | `previewViewerId` | `static/js/dashboard-state.js:272` |
| `localStorage` | `previewViewerId` | `static/js/dashboard-state.js:310` |

## SEC-001A review gate

Do not check off SEC-001A until:

- [c] Every runtime path literal is assigned to an owning subsystem.
- [c] Every direct and indirect source reader/writer is reconciled.
- [ ] Candidate JSON/JSONL keys are reduced to keys actually persisted.
- [ ] Browser storage names are classified for household/personal data.
- [ ] Every source-relative runtime path is carried into PATH-001.
- [ ] The report is manually confirmed to contain no values or personal data.

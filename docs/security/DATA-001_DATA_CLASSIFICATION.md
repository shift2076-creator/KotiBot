# DATA-001 — Runtime data classification

Review commits:

- DATA-001A: `61281ff18ba286a10b10e4f811786db6d0de6efb`
- DATA-001B.1: `f4d399cca993d3c2d05d126860d4e3c7972dc1a3`

## Safety boundary

This document classifies file names, object paths, and field names only. It
contains no file contents, runtime values, credential values, personal-data
values, household names, device identifiers, account names, or absolute home
paths.

SEC-001A remains authoritative for the exhaustive persisted-field inventory.
SEC-001D remains authoritative for readers, writers, current permission
classes, loss impact, retention requirements, and proposed destinations.

## Classification rules

| Class | Decision rule |
| --- | --- |
| Durable user intent | Explicit configuration or a deliberate user choice that must survive restart, outage, and migration. |
| Irreplaceable identity | A stable identity whose loss would break enrollment, references, or ownership even if live telemetry can be rediscovered. |
| Reconstructible live state | A current observation, capability, derived value, or run marker that can be re-established by startup or synchronization. |
| Replaceable cache | Data retained only to avoid repeated work; deleting it may cost time or network activity but must not change authoritative behavior. |
| Protected credential | A secret, token, key, authentication verifier, or credential metadata that must remain in a protected store. |
| Retained history | A time-ordered event, audit, notification, or media record retained under an explicit policy. |
| Obsolete data | A duplicate, compatibility-only persisted field, unknown pass-through field with no current reader, or superseded representation. |

Each leaf field receives one primary class according to its required handling.
A fixed container key is classified as durable user intent when it is part of
the durable schema, while its children retain their own classifications. A
mixed file receives the class of its most sensitive current leaf field.

Stable identity wins over rediscoverability when losing the identity would
break durable references. Unknown or pass-through fields are not assumed to be
durable: without a named current reader they are obsolete and must not cross a
migration boundary. Classification alone does not authorize deletion; removal
still requires the downstream migration, compatibility, backup, and rollback
gates.

## DATA-001A scope

This first checkpoint classifies the four files already relocated by
PATH-001A and PATH-001B:

- `server_state.json`
- `security_actions.json`
- `automations_state.json`
- `tapo_lighting_state.json`

DATA-001 remains open until DATA-001B through DATA-001D classify and reconcile
the remaining files, fields, storage, history, media, configuration, and
obsolete residue.

## File-level classification

| File | Current primary class | Reason |
| --- | --- | --- |
| `server_state.json` | Protected credential | The current schema mixes durable intent and stable identity with FCM tokens. It remains credential-bearing until those fields migrate. |
| `security_actions.json` | Durable user intent | The file defines deliberate security responses and their targets. Its bounded execution timestamp does not change the file's primary purpose. |
| `automations_state.json` | Durable user intent | The file defines user automation rules, recharge thresholds, and day-reset configuration. Bounded execution timestamps are subordinate fields. |
| `tapo_lighting_state.json` | Durable user intent | Saved schemes and mode configuration are deliberate household lighting configuration. Active-mode state is a subordinate reconstructible field. |

## `server_state.json`

| Object or fields | Classification | Required handling |
| --- | --- | --- |
| Root `clients`, fixed client-group containers `tapo`, `matter`, `android_home`, `android_key`, `unprovisioned`, `other`, and root `system` | Durable user intent | Retain the closed schema containers. They do not make every child durable. |
| `deviceID` in every client group | Irreplaceable identity | Preserve unchanged across migration because automations, security actions, enrollment, and device relationships use it as a stable reference. |
| `clientName`, `clientRole`, `provisioned`, `zone_name` | Durable user intent | Preserve user-visible naming, role/provisioning decisions, and zone assignment. Treat these conservatively as durable even when an unprovisioned client first supplied a default. |
| `fcm_token`, `fcm_token_at` | Protected credential | Move out of durable state through SEC-002–SEC-004, expose only an opaque reference where necessary, rotate under SEC-006, and remove old copies only after validation. |
| `source`, `detectedRole`, `ip`, `battery`, `battery_low`, `battery_state`, `brand`, `androidVersion`, `version`, `heartbeat_interval_ms`, `hasDSSHW`, `manufacturer`, `model` | Reconstructible live state | Re-establish from enrollment, discovery, or the first post-start synchronization. Stop persisting after STATE-004/STATE-005 provide a safe unknown-to-known transition. |
| `system.arm_state` | Durable user intent | Preserve the last deliberate mode. Whether startup restores or safely defers that mode remains the explicit restart-policy decision. |
| `system.armed` | Reconstructible live state | Derive from the canonical `arm_state`; do not retain as a second authority after schema migration. |
| `system.armState` | Obsolete data | Remove from persistence after compatibility validation. APIs may continue emitting a compatibility alias without storing the duplicate. |

The durable backup set is the stable identity and deliberate user-intent
fields. Live device metadata must not enter long-term backups once removed from
the schema. Until FCM tokens are migrated, every copy and backup of this file
must be handled as a protected credential.

## `security_actions.json`

| Object or fields | Classification | Required handling |
| --- | --- | --- |
| Root `actions` | Durable user intent | Preserve as the closed container for security action configuration. |
| `enabled`, `from_deviceID`, `from_output`, `trigger`, `threshold`, `threshold_unit`, `arm_states`, `to_kind`, `action_type`, `to_deviceID`, `to_input`, `targetID`, `power_action`, `filename`, `sound_volume`, `target_key_deviceID`, `title`, `message`, `duration_seconds`, `minimum_duration_seconds`, `repeat`, `timer_seconds`, `repeat_seconds`, `cooldown_seconds`, `auto_off`, `auto_off_seconds`, `retrigger` | Durable user intent | Preserve together as each configured rule. Device identifiers here are durable references to the identity owned by `server_state.json`, not independent identity records. |
| `last_notification_at` | Retained history | Retain one bounded execution timestamp per applicable rule through restart so cooldown enforcement cannot silently reset. It is not durable user intent and needs no long-term history backup. |
| Any unlisted legacy or pass-through action field | Obsolete data | Do not migrate unless a current reader is first identified and the field is explicitly reclassified. |

The complete configured action list requires a validated, versioned
last-known-good backup. The bounded cooldown timestamp must survive restart but
does not require long-term historical backup.

## `automations_state.json`

| Object or fields | Classification | Required handling |
| --- | --- | --- |
| Root `tapo_recharge_android_battery`, `device_automations`, `tapo_day_reset` | Durable user intent | Preserve as the only approved top-level automation containers. |
| `tapo_recharge_android_battery.<deviceID>` map key | Durable user intent | Preserve as the user's selected source-device reference; canonical identity remains owned by `server_state.json`. |
| Recharge fields `type`, `clientName`, `enabled`, `targetID`, `targetDeviceID`, `child_id`, `child_index`, `child_position`, `lowBattery`, `fullBattery` | Durable user intent | Preserve the selected target and charging thresholds as one rule. |
| `device_automations[]` configured fields listed for `security_actions.json`, excluding `last_notification_at` | Durable user intent | Preserve as each configured automation rule. |
| `device_automations[].last_notification_at` | Retained history | Retain one bounded execution timestamp per applicable rule through restart so cooldown enforcement cannot silently reset. Do not retain older notification timestamps here. |
| Day-reset fields `type`, `enabled`, `resetHour` | Durable user intent | Preserve the deliberate schedule and enablement choice. |
| Day-reset field `lastRunDate` | Retained history | Retain the single bounded execution date through restart so the daily reset remains idempotent. Replace it as the schedule advances; do not build an unbounded run history here. |
| Unknown top-level, recharge, automation, or day-reset pass-through fields | Obsolete data | Do not migrate without a named current reader and explicit reclassification. |

Back up the rules, thresholds, targets, and schedule configuration. Preserve
the bounded execution timestamps through restart and migration, but exclude
them from long-term historical backup.

## `tapo_lighting_state.json`

| Object or fields | Classification | Required handling |
| --- | --- | --- |
| Root `schemes` and dynamic scheme target keys | Durable user intent | Preserve saved home, room, and device scheme assignments. Dynamic target keys are durable references, not independent identity records. |
| Scheme fields `favorite`, `icon`, `label`, `mode`, `preset`, `savedAt` | Durable user intent | Preserve user-facing configuration and `savedAt`, which is currently used for conflict selection and ordering. |
| Preset fields `brightness`, `colorTemperature`, `whiteSaturation`, `hue`, `saturation` | Durable user intent | Preserve the complete normalized lighting preset. |
| Root `activeSchemes` and each dynamic target-to-mode value | Reconstructible live state | Treat as the current applied-mode snapshot. Re-establish from deliberate activation and synchronized device state rather than treating it as saved configuration. |
| Root `modeConfig`, dynamic mode/target keys, and fields `power`, `preset` | Durable user intent | Preserve the configured per-mode target behavior. |
| Any unlisted preset extension or pass-through field | Obsolete data | Do not carry it into a closed migrated schema unless a current reader is identified and the field is explicitly classified. |

Back up saved schemes, normalized presets, and mode configuration. Do not make
the active-scheme snapshot authoritative over post-start device
synchronization.

## DATA-001A review gate

- [c] The seven classification classes have explicit decision rules.
- [c] Every reviewed field in the four PATH-001A/PATH-001B files has a primary classification.
- [c] Mixed containers, stable references, runtime markers, compatibility aliases, and unknown pass-through fields have explicit handling rules.
- [c] Credential-bearing state remains protected until migration and rotation complete.
- [c] Durable backup sets and non-durable exclusions are recorded.
- [c] No runtime contents, values, personal-data values, household names, device identifiers, account names, or absolute home paths were captured.

DATA-001A is complete. DATA-001 remains open.

## DATA-001B.1 scope

This checkpoint classifies the complete persisted schemas for:

- `activity_state.json`
- `android_home_state.json`

Environment, Matter, and Tapo state/configuration remain in DATA-001B.2 and
DATA-001B.3. Authentication, credentials, controller identity, history outside
Activities, media, caches, archives, temporary data, and source-tree residue
remain in DATA-001C and DATA-001D.

## DATA-001B.1 file-level classification

| File | Current primary class | Reason |
| --- | --- | --- |
| `activity_state.json` | Retained history | The `events` tree is bounded household, automation, user, system, and security history. `last_signatures` is a subordinate replaceable deduplication cache. |
| `android_home_state.json` | Durable user intent | The file mixes deliberate camera/door settings with a stable device-identity join, live telemetry, an operational cooldown timestamp, and obsolete compatibility fields. |

## `activity_state.json`

| Object or fields | Classification | Required handling |
| --- | --- | --- |
| Root `events` | Retained history | Keep only under the explicit Activity retention policy. It is not authoritative device state or durable configuration. |
| Fixed buckets `day_0_previous_24_hours`, `day_1_yesterday`, `day_2_two_days_ago`, `day_3_three_days_ago`, `day_4_four_days_ago`, `day_5_five_days_ago`, `day_6_six_days_ago` | Retained history | Preserve the current seven-day window until STATE-006 approves the final bounded retention policy. Expired events must not migrate. |
| Fixed categories `automation`, `security`, `system`, `users`, and dynamic kind names below each category | Retained history | Treat the category and kind paths as event-history metadata. Keep only kinds containing valid retained events. |
| Event fields `deviceID`, `ts`, `state` | Retained history | Retain together as the compact event record. `deviceID` is a historical reference, `ts` supplies ordering/expiry, and `state` is the recorded event text. Do not promote any of them to current device authority. |
| Root `last_signatures` and each `last_signatures.<dynamic signature>` key/value | Replaceable cache | Use only to suppress duplicate state-change events. It may be rebuilt from post-start observations and must not enter long-term backups. Its startup baseline behavior must be covered by STATE-004 before deliberate cache removal. |
| Any other root, bucket, category, event, or signature structure | Obsolete data | The writer reconstructs the closed root, bucket/category set, compact event allowlist, and scalar signature map. Do not migrate rejected legacy or malformed fields. |

The current writer already normalizes Activity history into seven rolling
24-hour buckets. `max_events` limits a page request, not the stored event
count, so STATE-006 must still make the retention and backup policy explicit.
Back up Activity history only if that policy deliberately makes it recoverable;
never back up `last_signatures` as authoritative data.

## `android_home_state.json`

| Object or fields | Classification | Required handling |
| --- | --- | --- |
| Root `clients` | Durable user intent | Retain as the closed container while durable Android Home settings remain in this file. It does not make every client field durable. |
| Dynamic `clients.<deviceID>` map keys | Irreplaceable identity | Preserve the exact join to the identity owned by `server_state.json`. Do not create, rename, or independently recover an Android Home identity from this snapshot. |
| Camera fields `motion_detection_enabled`, `motion_detection_threshold`, `motion_flashlight_enabled`, `motion_screen_enabled`, `selected_camera` | Durable user intent | Preserve deliberate motion and camera choices across restart and migration. Validate ranges and the `front`/`back` camera choice when the schema is split. |
| `preview_by_lens.<front\|back>.aspect_ratio` | Durable user intent | Preserve the selected per-lens preview aspect. Reject other dynamic lens names and nested pass-through fields unless a current reader is identified first. |
| Camera fields `frame_seq`, `frame_last_seen`, `frame_captured_ms`, `recording_enabled`, `motion_active`, `motion_recording_active`, `last_motion_at`, `last_motion_score`, `camera_auto_rotation`, `camera_auto_rotation_at`, `camera_auto_rotation_lens` | Reconstructible live state | Start frame, recording-session, motion, and orientation state from a safe unknown/off baseline and re-establish it from commands or telemetry. `recording_enabled` is an operational recording-session toggle and is also temporarily driven by motion; it is not a durable recording preference. |
| Camera fields `recording`, `available_cameras`, `exposure_compensation`, `camera_enabled`, `cameraEnabled` | Obsolete data | These allowlisted fields have no current Android Home producer/behavioral reader in the reviewed source. Do not migrate them as configuration. Add a named reader/writer and reclassify first if a future client contract requires one. |
| Door fields `open_angle_threshold`, `close_angle_threshold`, `smoothing_window`, `doorbell_muted` | Durable user intent | Preserve calibration/configuration and the deliberate mute choice. Validate the external Android client contract before changing defaults or field names. |
| Door field `last_chime_at` | Retained history | Preserve only the single bounded operational timestamp needed to avoid replaying a chime across restart. It needs no long-term history backup and must move to an explicit cooldown/retention owner in STATE-006. |
| Door fields `door_status`, `calibrating`, `calibration_samples`, `last_transition_at`, `openness_score`, `door_angle`, `door_event_ms`, `ignore_door_open_until_closed` | Reconstructible live state | Treat sensor observations, calibration progress, event ordering, transition timing, and the post-calibration safety latch as runtime state. The loader already forces `door_status` to `unknown`; STATE-004 must define the complete safe cold-start baseline before these fields stop persisting. |
| Shared camera/door field `android_sensors` | Obsolete data | The reviewed source allowlists the field but has no current producer or behavioral reader. Do not migrate it without a named client contract and explicit reclassification. |
| Unknown client keys, unmatched client entries, other per-client fields, other `preview_by_lens` children, and any non-`clients` root field | Obsolete data | The writer uses fixed camera/door allowlists and replaces the root. Do not carry pass-through or rejected legacy data across migration. |

The Android Home backup set is limited to the device join keys and the durable
camera/door settings above. Exclude recording-session state, live telemetry,
calibration progress, derived orientation, the deduplicated/obsolete aliases,
and other rejected fields. Preserve `last_chime_at` only as a bounded restart
marker, not as long-term history.

## DATA-001B.1 review gate

- [c] Every Activity root, fixed bucket, fixed category, dynamic kind, compact event field, and dynamic signature entry has a primary classification.
- [c] Every field in `ANDROID_CAMERA_STATE_KEYS` and `ANDROID_DSS_STATE_KEYS`, including shared, dynamic, compatibility, and currently unread fields, has a primary classification.
- [c] Durable backup fields, retained-but-not-backed-up markers, reconstructible state, replaceable cache, and obsolete exclusions are explicit.
- [c] No runtime contents, values, personal-data values, household names, device identifiers, account names, credential values, or absolute home paths were captured.

DATA-001B.1 is complete. DATA-001B and DATA-001 remain open.

## DATA-001B.2 scope

This checkpoint classifies the complete persisted schemas for:

- `environment_state.json`
- `matter_device_state.json`
- the non-controller-identity settings, node registry, discovery cache, and
  diagnostic fields in `matter_state.json`

Protected Matter fabric/controller identity, `chip_tool_storage/`,
subscription storage and copies, controller repair/rollback directories,
attestation policy, and credential-bearing commissioning inputs remain
excluded for DATA-001C. Tapo configuration/device state remains in
DATA-001B.3.

## DATA-001B.2 file-level classification

| File | Current primary class | Reason |
| --- | --- | --- |
| `environment_state.json` | Durable user intent | The file mixes deliberate location/provider/refresh preferences with a replaceable NOAA, station, ZIP-lookup, and AirNow cache. |
| `matter_device_state.json` | Reconstructible live state | The file is primarily a duplicate capability/telemetry snapshot. Stable node/endpoint joins and `doorbell_muted` are subordinate fields that must be separated before the snapshot is removed. |
| `matter_state.json` | Irreplaceable identity | The `nodes` registry currently supplies the stable node references needed for synchronization and is mixed with durable metadata, executable-path configuration, replaceable discovery/command diagnostics, compatibility fields, and unknown pass-through node fields. Protected controller/fabric storage is classified separately in DATA-001C. |

## `environment_state.json`

| Object or fields | Classification | Required handling |
| --- | --- | --- |
| Root `settings` | Durable user intent | Preserve as a closed durable-settings container after it is separated from cache data. |
| `settings.zip_code` | Durable user intent | Preserve the deliberate location choice as private household metadata. It is not a credential, but ordinary API/log output must not expose it unnecessarily. |
| `settings.weather_source`, `settings.air_quality_source`, `settings.refresh_seconds` | Durable user intent | Preserve the normalized provider and refresh choices. Retain range/provider validation during migration. |
| Compatibility inputs `settings.zipCode`, `settings.weatherSource`, `settings.airQualitySource`, `settings.refreshSeconds` | Obsolete data | The cleaner accepts these names but the writer emits only canonical snake-case fields. Do not persist or migrate the aliases. |
| Unknown or unlisted `settings` children | Obsolete data | `clean_settings` replaces the settings object with the closed canonical schema. Do not recover discarded settings without a named reader and explicit reclassification. |
| Root `weather_cache` | Replaceable cache | Move to `<cache-root>/environment/` with freshness/TTL handling. It must not enter durable backups or determine authoritative household configuration. |
| Cache status/source fields `ok`, `zip_code`, `source`, `lookup_source`, `station_source`, `updated_at`, `error` | Replaceable cache | Retain only for a bounded cache generation and provider/freshness display. The cached ZIP is a duplicate of durable settings and must not become a second authority. |
| Current-observation fields `temperature_f`, `humidity_percent`, `condition`, `timestamp`, `icon` | Replaceable cache | Re-fetch from the configured provider. A stale copy may be labeled for degraded display but is not durable or authoritative state. |
| `location.latitude`, `location.longitude`, `location.city`, `location.state` | Replaceable cache | Reconstruct from the configured ZIP lookup. Treat as private location metadata while cached; do not include in durable backups. |
| `station.id`, `station.name`, `station.url`, `station.latitude`, `station.longitude`, `station.distance_miles` | Replaceable cache | Reconstruct from NOAA station discovery. Validate remote URLs again before use rather than trusting cached URLs as configuration. |
| `stations_checked[]` and each station summary field listed for `station` | Replaceable cache | Keep only as bounded provider-selection diagnostics for the cache generation. Do not retain as history. |
| `air_quality.aqi`, `label`, `parameter`, `dominant_pollutant`, `reporting_area`, `source`, `source_id`, `timestamp`, `updated_at`, `error` | Replaceable cache | Reconstruct from the selected AirNow source. Preserve freshness and attribution while cached, but exclude from durable backup. |
| `air_quality.pollutants[]` fields `name`, `aqi`, `label`, `timestamp` | Replaceable cache | Treat as current provider observations within the same bounded AirNow cache generation. |
| Unknown root fields and unknown/unlisted `weather_cache`, `location`, `station`, `stations_checked[]`, `air_quality`, or `pollutants[]` fields | Obsolete data | The current state reader/writer can pass unknown cache children through until refresh. A split cache schema must use closed normalized fields and discard unknown pass-through data. |

The Environment durable backup set is exactly the four canonical settings
fields. Weather, location lookup, station-selection, observation, AirNow,
error, attribution, and freshness data are replaceable cache. STATE-006 must
split these classes and define the bounded stale-display policy before the
mixed file is retired.

## `matter_device_state.json`

| Object or fields | Classification | Required handling |
| --- | --- | --- |
| Root `devices` | Reconstructible live state | Retain only as the current mixed-schema container until stable joins and deliberate settings are separated. The container does not make telemetry durable. |
| Dynamic `devices.<deviceID>` map keys | Irreplaceable identity | Preserve the exact join to the identity owned by `server_state.json`. Do not create or rename device identity from this telemetry snapshot. |
| `matter_node_id`, `matter_endpoint` | Irreplaceable identity | Preserve as the stable node/endpoint join used to reconstruct the same device identity and its durable references after synchronization. These identifiers are not a substitute for protected fabric/controller storage. |
| `doorbell_muted` | Durable user intent | Preserve the deliberate mute choice in the future durable Matter settings schema. |
| `matter_contact_open_when` | Obsolete data | Do not migrate. Runtime intentionally fixes Matter BooleanState contact semantics and refuses to relearn polarity from persisted client state. |
| Discovery/network/identity-description fields `ip`, `brand`, `manufacturer`, `model`, `matter_kind`, `matter_kinds`, `matter_device_type`, `matter_cluster`, `matter_vendor_name`, `matter_product_name`, `matter_node_label`, `matter_hardware_version`, `matter_software_version`, `matter_serial_number`, `matter_reachable` | Reconstructible live state | Re-establish from authoritative Matter discovery and Basic Information reads. User names and zones remain owned by `server_state.json`; discovered labels must not overwrite them after restart. |
| Capability fields `matter_switch_positions`, `matter_switch_multipress_max` | Reconstructible live state | Re-read from the endpoint capability/attribute contract before enabling related controls. |
| Synchronization/observation fields `matter_last_sync_at`, `battery`, `battery_low`, `battery_state`, `temperature_raw`, `temperature_c`, `humidity_raw`, `humidity_percent`, `contact_state_value`, `contact_open`, `occupancy_state_value`, `motion_active`, `last_motion_at`, `door_status`, `openness_score`, `door_angle`, `door_event_ms`, `last_transition_at`, `calibrating`, `matter_onoff`, `matter_switch_position`, `matter_button_position`, `matter_button_event`, `matter_button_event_at`, `matter_button_press_count` | Reconstructible live state | Start unknown and rebuild through the first authoritative snapshot/subscription baseline. Do not fire automation, security, Activity, or UI transition behavior from these persisted observations. |
| Battery-detail fields `matter_battery_percent_remaining_raw`, `matter_battery_percent`, `matter_battery_charge_level`, `matter_battery_charge_state`, `matter_battery_replacement_needed`, `matter_battery_low` | Reconstructible live state | Re-read from PowerSource attributes. Derive generic battery fields from the current authoritative observation instead of persisting both representations. |
| Unknown device keys, unmatched device entries, non-dictionary entries, and any non-`devices` root field | Obsolete data | The current writer reconstructs the file from `MATTER_DEVICE_STATE_KEYS` and drops unknown fields. Do not carry rejected or legacy data across migration. |

The Matter device-snapshot backup set is limited to the dynamic device join,
`matter_node_id`, `matter_endpoint`, and `doorbell_muted` until those fields
move to durable owners. Every capability, vendor/product description,
reachability flag, reading, derived door/motion/button value, battery value,
and synchronization timestamp must be excluded from long-term backups after
STATE-004/STATE-005 establish the cold-start baseline.

## `matter_state.json` non-controller-identity fields

| Object or fields | Classification | Required handling |
| --- | --- | --- |
| Root `enabled` | Durable user intent | Preserve the deliberate Matter integration enablement choice in a closed configuration schema. |
| Root `chip_tool` | Durable user intent | Preserve only as validated high-integrity operator configuration when no environment override is authoritative. Do not allow an unvalidated persisted executable path to become command authority. |
| Root `settings` and `settings.temperature_unit` | Durable user intent | Preserve the normalized display-unit preference. |
| Unknown `settings` children | Obsolete data | `read_state` currently merges and re-persists unknown nested settings even though no current reader uses them. Exclude them from the migrated closed settings schema. |
| Legacy root `temperature_unit` | Obsolete data | Read only as a compatibility fallback for `settings.temperature_unit`; write only the canonical nested field after migration. |
| Root `chip_tool_storage` | Obsolete data | The loaded JSON field is ignored and runtime derives the directory. Do not migrate the persisted path. Classify and migrate the actual protected controller directory in DATA-001C/PATH-001C.4. |
| Root `bypass_attestation` | Obsolete data | The loaded JSON field is ignored; the laboratory-only override is derived from the environment. Do not migrate the persisted duplicate. Classify the high-risk environment configuration in DATA-001C. |
| Root `nodes` and dynamic `nodes.<node_id>` map keys | Irreplaceable identity | Preserve stable node references needed to synchronize and join commissioned devices. The map is not the controller fabric itself and cannot replace protected controller backup/restore. |
| `nodes.<node_id>.node_id` | Irreplaceable identity | Preserve and validate equality with the canonical dynamic map key. Reject conflicts rather than silently renaming a commissioned reference. |
| Node fields `alias`, `manufacturer`, `model`, `source`, `notes` | Durable user intent | Preserve values deliberately saved through the Matter node API. Separate user metadata from rediscovered device descriptions so discovery cannot overwrite explicit choices. |
| Node `updated_at` | Retained history | Retain at most the single bounded configuration-update timestamp if the final UI/audit policy uses it; otherwise drop it during STATE-006. It is not configuration authority. |
| Node `recommissioned_at` | Retained history | Retain at most the single bounded recommission marker until the final audit/retention owner is selected. It must not substitute for controller rollback material. |
| Node `endpoints` and current endpoint summaries | Reconstructible live state | Inspection overwrites this field with discovered endpoint/kind/capability summaries. Rebuild it from the controller. If explicit endpoint mappings become user configuration, store them under a separate validated field before migration. |
| Node `matter_children`, `matter_discovered_at`, and `matter_discovery` | Replaceable cache | Treat as the endpoint discovery cache and its freshness/diagnostic metadata. Delete or rebuild without changing commissioned identity or deliberate node metadata. |
| `matter_children[]` named fields `endpoint`, `kinds`, `clusters`, `source`, `bridged_basic`, `bridged_basic_reads`, `button_attr_reads`, `battery_attr_reads`, `matter_switch_positions`, `matter_switch_multipress_max`, `matter_battery_charge_level`, `matter_battery_charge_state`, `matter_battery_replacement_needed`, `matter_battery_low`, `battery_low`, `battery_state`, `server_list` | Replaceable cache | Keep only in the bounded discovery generation. Endpoint and capability values here are cached observations, not independent durable identity records. |
| `matter_discovery` fields `ok`, `source`, `parts`, `parts_reads`, `endpoints`, `updated_at`; dynamic endpoint details and their `endpoint`, `kinds`, `clusters`, `bridged_basic`, read/attribute diagnostic maps, capability/battery values, and `server_list` | Replaceable cache | Reconstruct by descriptor and attribute discovery. Bound and redact diagnostic text; do not back it up or retain it as history. |
| Node `last_inspection`, `last_inspection_at` | Replaceable cache | Treat the most recent descriptor/device-type/server-list inspection and timestamp as replaceable diagnostics, not retained audit history. |
| `last_inspection.parts_list`; dynamic `last_inspection.endpoints`; endpoint fields `device_type_list`, `server_list`, `matter_kinds`, `values`; and `values` command/capability fields | Replaceable cache | Re-run inspection when needed. Apply the same bounded/redacted handling as other Matter command diagnostics. |
| Root `last_command` fields `ok`, `returncode`, `command`, `stdout`, `stderr`, `started_at`, `finished_at` | Replaceable cache | Keep only as bounded current diagnostics. Setup codes must remain redacted; output must not enter backups or long-term history. |
| Unknown root fields | Obsolete data | `read_state` rebuilds a selected root and drops unknown root fields on the next write. Do not recover or migrate them. |
| Unknown node fields and unknown/unlisted recursive fields below `endpoints`, `matter_children`, `matter_discovery`, `last_inspection`, or `last_command` | Obsolete data | The current node loader and normalizer can pass unknown fields through. A migrated schema must use explicit durable fields and closed bounded-cache fields; unknown pass-through data must not cross the boundary. |

The durable `matter_state.json` backup set for this checkpoint is limited to
`enabled`, validated `chip_tool` configuration when applicable,
`settings.temperature_unit`, node map keys, matching `node_id`, deliberate
node metadata, and the two bounded operational timestamps only while their
retention remains approved. Exclude endpoint snapshots, discovery and
inspection trees, command results/output, ignored compatibility/path fields,
environment-derived attestation state, and unknown pass-through fields.
Protected controller/fabric identity requires its separate DATA-001C decision
and tested backup/restore path before any relocation or cleanup.

## DATA-001B.2 review gate

- [c] Every canonical and compatibility Environment setting has a primary classification.
- [c] Every currently produced Environment weather, location, station, and AirNow cache field has a primary classification, including nested lists and unknown pass-through handling.
- [c] Every field in `MATTER_DEVICE_STATE_KEYS`, the dynamic device join, and rejected/unknown device entries has a primary classification.
- [c] Every selected `matter_state.json` root setting, node identity/metadata field, endpoint/discovery/inspection/command cache, bounded timestamp, compatibility field, and unknown pass-through class has explicit handling.
- [c] Protected Matter fabric/controller identity, storage/subscription copies, repair/rollback directories, attestation policy, and commissioning credentials remain explicitly deferred to DATA-001C.
- [c] Durable backup fields, bounded markers, reconstructible telemetry, replaceable cache, and obsolete exclusions are explicit.
- [c] No runtime contents, values, personal-data values, household names, device identifiers, account names, credential values, setup codes, command output, or absolute home paths were captured.

DATA-001B.2 is complete. DATA-001B and DATA-001 remain open.

## DATA-001B.3 scope

This checkpoint classifies the complete persisted schemas for:

- `tapo_config.json`
- `tapo_device_state.json`

It also closes the persistence boundary for dynamic outlet-extender children:
the writer now retains only named fields and discards raw vendor dictionaries,
normalized compatibility inputs, malformed child entries, and unknown
pass-through data. Tapo lighting configuration was classified in DATA-001A.
Credentials, recordings, camera HLS files, other cache/media data, and obsolete
source-tree residue remain in DATA-001C and DATA-001D.

## DATA-001B.3 file-level classification

| File | Current primary class | Reason |
| --- | --- | --- |
| `tapo_config.json` | Durable user intent | The sole canonical field records the deliberate integration enablement choice. |
| `tapo_device_state.json` | Irreplaceable identity | Dynamic device and child joins are mixed with deliberate display/recovery choices, reconstructible discovery and telemetry, transient command state, compatibility residue, and formerly open vendor child dictionaries. |

## `tapo_config.json`

| Object or fields | Classification | Required handling |
| --- | --- | --- |
| Root `enabled` | Durable user intent | Preserve only a JSON boolean. The server now reads this file through the typed object-state reader and fails closed for missing, invalid, unreadable, or non-boolean configuration. |
| Unknown root fields and non-boolean `enabled` values | Obsolete data | Do not migrate or interpret truthy strings/numbers. The admin writer replaces the file with the closed one-field schema. |

The file now resolves to `<state-root>/tapo/tapo_config.json`, outside the
source tree, and uses the shared atomic last-known-good writer. Preserve a
validated primary and backup through migration. It contains no Tapo account or
camera credential.

## `tapo_device_state.json` device records

| Object or fields | Classification | Required handling |
| --- | --- | --- |
| Root `devices` | Irreplaceable identity | Retain as the current mixed-schema container only until identity and deliberate settings are separated from live state. |
| Dynamic `devices.<deviceID>` map keys | Irreplaceable identity | Preserve the exact join to the identity owned by `server_state.json`; never generate or rename identity from discovery telemetry alone. |
| `tapo_id`, `tapo_mac` | Irreplaceable identity | Preserve as stable Tapo discovery/control joins until a validated identity migration proves the canonical minimum. They do not replace the KotiBot `deviceID`. |
| `tapo_alias`, `tapo_room_power`, `tapo_hide_dashboard` | Durable user intent | Preserve the user-visible Tapo alias and deliberate room/dashboard membership choices. `clientName` and `zone_name` remain canonically owned by `server_state.json`. |
| `tapo_desired_lighting_mode`, `tapo_desired_brightness`, `tapo_desired_color_temperature`, `tapo_desired_hue`, `tapo_desired_saturation`, `tapo_desired_white_saturation` | Durable user intent | Preserve the last deliberate lighting target used to restore user-selected light behavior after a device becomes reachable again. Normalize ranges/mode names before a future schema split. |
| `tapo_desired_lighting_updated_at` | Retained history | Retain only the single bounded timestamp used to qualify the current desired-lighting target. It is not long-term Activity history. |
| Discovery/type/capability fields `tapo_model`, `tapo_device_type`, `tapo_ip`, `tapo_kind`, `tapo_dashboard_section`, `tapo_dimmable`, `tapo_is_bulb`, `tapo_is_plug`, `tapo_is_outlet_extender`, `tapo_is_hub`, `tapo_is_camera`, `tapo_supports_power`, `tapo_supports_brightness`, `tapo_supports_color_temp`, `tapo_supports_color`, `tapo_supports_rtsp`, `tapo_supports_onvif`, `tapo_onvif_port` | Reconstructible live state | Rebuild from authenticated Tapo discovery/device information. Start capabilities unknown until the first authoritative refresh rather than treating persisted flags as proof of support. |
| Control/lighting observations `tapo_control_ready`, `tapo_control_error`, `tapo_is_on`, `tapo_brightness`, `tapo_color_temperature`, `tapo_hue`, `tapo_saturation` | Reconstructible live state | Establish a cold-start baseline from the first successful refresh. Do not fire state-change behavior from these persisted observations. |
| Battery fields `tapo_battery`, `tapo_battery_level`, `tapo_battery_percent`, `tapo_battery_low`, `tapo_battery_state` | Reconstructible live state | Re-read and normalize one canonical battery representation. Do not persist duplicate vendor aliases after STATE-005. |
| Legacy flattened child fields `tapo_is_hub_child`, `tapo_is_button`, `tapo_is_switch`, `tapo_child_id`, `tapo_child_name`, `tapo_child_kind`, `tapo_child_model`, `tapo_child_category`, `tapo_child_avatar`, `tapo_child_type`, `tapo_child_mac`, `tapo_child_status`, `tapo_child_rssi`, `tapo_child_signal_level`, `tapo_parent_device_id`, `tapo_parent_id`, `tapo_parent_model`, `tapo_parent_alias`, `tapo_parent_ip` | Obsolete data | These fields belong to retired standalone hub-child client records or have no current producer/behavioral reader. The current normalizer removes retired records, and the closed writer now excludes the flattened compatibility representation. |
| `tapo_children_initialized` | Durable user intent | Preserve the one-time outlet-layout initialization marker until child settings move to their final closed durable schema; it prevents defaults from overwriting established names/hide choices. |
| `tapo_pending_power_commands` and every dynamic pending-command child | Replaceable cache | Never persist. It is an in-memory command/recovery queue that must not replay stale commands after restart. The closed writer now excludes it. |
| `tapo_trigger_log_supported`, `tapo_last_trigger_event`, `tapo_last_trigger_id`, `tapo_last_trigger_event_id`, `tapo_last_trigger_at` | Obsolete data | No current producer or behavioral reader exists outside the legacy persistence allowlist. The closed writer now excludes these fields. |
| `tapo_rtsp_url` | Protected credential | Never persist because an RTSP URL can embed camera credentials. Runtime already removes legacy copies and the closed writer now excludes the field at the persistence boundary. Credential sourcing/rotation remains in DATA-001C and SEC-002–SEC-006. |
| Unknown device fields, unmatched device entries, non-dictionary records, malformed `tapo_children`, and non-`devices` root fields | Obsolete data | Do not migrate. The writer reconstructs the root from the closed device/child contracts and rejects malformed child containers. |

## `tapo_device_state.json` child records

| Object or fields | Classification | Required handling |
| --- | --- | --- |
| `tapo_children[]` and child identity fields `id`, `device_id`, `parent_device_id`, `mac`, `position` | Irreplaceable identity | Preserve the minimum stable parent/child join and physical outlet position so deliberate child settings remain attached to the correct outlet. Reconcile duplicates/conflicts instead of renaming silently. |
| Child ordering/control selectors `index`, `cli_index`, `slot_number`, `tapo_child_id`, `tapo_child_position`, `tapo_child_index` | Reconstructible live state | Rebuild or derive from canonical identity/position and the current device contract. Retain temporarily for control compatibility until the child schema is migrated. |
| Child naming/location fields `alias`, `name`, `clientName`, `zone_name`, `room`, `room_name`, `zone`, `tapo_alias`, `tapo_child_name` | Durable user intent | Preserve established child display/location choices. Normalize to one canonical name and one canonical zone owner in STATE-005 rather than keeping every alias indefinitely. |
| `tapo_room_power`, `tapo_hide_dashboard` | Durable user intent | Preserve deliberate room-power membership and dashboard visibility, including explicit `false` values. |
| Child descriptor/capability fields `model`, `category`, `avatar`, `type`, `kind`, `tapo_kind`, `tapo_child_kind`, `is_usb`, `is_light`, `is_outlet`, `tapo_is_outlet_child`, `tapo_is_plug`, `tapo_is_bulb`, `supports_power`, `supports_brightness`, `supports_color_temp`, `supports_color`, `tapo_supports_power` | Reconstructible live state | Rebuild from current child discovery and model defaults. Do not treat persisted capabilities as authoritative before synchronization. |
| Child observation fields `status`, `rssi`, `signal_level`, `battery`, `at_low_battery`, `battery_low`, `battery_state`, `is_on` | Reconstructible live state | Start unknown and rebuild from current child telemetry. Do not restore power/battery/reachability authority from disk. |
| Child `raw`, `nickname`, vendor camel-case/snake-case compatibility inputs, power aliases `device_on`/`on`/`state`, and any unknown vendor field | Obsolete data | The normalizer already produces canonical fields. The closed child writer now drops raw vendor dictionaries, duplicate compatibility inputs, and all other pass-through fields. |

The Tapo durable backup set is limited to device/child joins, aliases and
location/display choices, room-power/hide choices, the child-initialization
marker, and desired-lighting targets with their single current timestamp.
Exclude discovery data, network addresses, capabilities, control errors,
power/color/battery observations, transient pending commands, legacy trigger
fields, raw vendor payloads, unknown extensions, and any credential-bearing
RTSP URL. STATE-004/STATE-005 must establish the cold-start baseline before
the remaining reconstructible telemetry is removed from persistence.

## DATA-001B.3 review gate

- [c] The Tapo integration enablement field and all rejected configuration fields have a primary classification.
- [c] Every field in the current Tapo device persistence contract, including dynamic device keys, identity, user intent, desired-lighting recovery, telemetry, capability, legacy, transient-command, and credential-risk fields, has explicit handling.
- [c] Every canonical persisted outlet-extender child field has a primary classification.
- [c] Raw vendor child dictionaries, compatibility inputs, malformed entries, unknown pass-through fields, transient pending commands, unused trigger fields, and RTSP URLs are now excluded by the production persistence boundary.
- [c] Durable backup fields, bounded markers, reconstructible telemetry, replaceable cache, obsolete exclusions, and protected credential handling are explicit.
- [c] No runtime contents, values, personal-data values, household names, device identifiers, account names, credential values, RTSP URLs, raw vendor payloads, or absolute home paths were captured.

DATA-001B.3 and DATA-001B are complete. DATA-001 remains open.

## DATA-001C scope

This checkpoint classifies protected authentication, credential,
configuration, controller-identity, and dependency-environment data found by
SEC-001D. It covers:

- `security_state.json` and its last-known-good copy
- `firebase-service-account.json`
- credential-bearing environment entries and protected operator configuration
- Matter controller, fabric, subscription, repair, and rollback storage
- commissioning inputs and attestation policy
- `.venv`, `.env.shared`, `.env.example`, and the protected systemd
  environment file

Audit/notification history, recordings, browser storage, archives, general
caches, temporary data, and obsolete source-tree residue remain in
DATA-001D. This classification does not authorize secret rotation, deletion of
legacy copies, or Matter identity relocation. Those actions remain gated by
SEC-002 through SEC-006 and PATH-001C.4/PATH-001C.8.

## DATA-001C file-level classification

| Path or pattern | Current primary class | Required handling |
| --- | --- | --- |
| `security_state.json`, `security_state.lkg.json` | Protected credential | Store outside the source tree under a private protected-state root. Preserve a validated primary and last-known-good copy. Never log or expose field values. |
| `firebase-service-account.json` and any copy | Protected credential | Treat the whole document as one composite credential even though some metadata is public. Move through the approved credential loader, rotate it, then remove legacy copies only after verified cutover. |
| Protected systemd environment file, including `/etc/kotibot/tapo.env` | Protected credential | Keep root-owned and mode `0600`; later split or load individual credentials through the SEC-002 decision. Do not copy values into state, logs, tests, or Git. |
| Source `.env.shared` | Obsolete data | No approved application or systemd reader was found. Because it may contain secret values, handle it as a protected credential until SEC-006 rotates/removes it. |
| `.env.example` | Durable user intent | Keep only documented variable names and non-secret placeholders/default guidance. It is reproducible documentation and must never contain a working credential. |
| `matter/chip_tool_storage/**` and configured controller-storage root | Protected credential | Opaque controller/fabric identity contains irreplaceable commissioning authority and secret material. Preserve and back up the complete validated tree as a protected unit. Never reinitialize it to solve a path error. |
| `matter/chip_tool_subscription_storage/**` | Protected credential | Current subscription workers copy controller storage into these trees, mixing irreplaceable identity with replaceable subscription state. Protect and preserve the complete tree until implementation proves a safe split. |
| `chip_tool_storage.bad-*` | Protected credential | Retain as bounded protected controller rollback history until a verified recovery policy supersedes it. Never classify it as ordinary cache. |
| `.chip_tool_storage.repair-*` | Protected credential | Treat as protected temporary staging containing controller identity. Remove only after a verified repair commit or rollback, never by generic temporary cleanup. |
| `.venv/**` | Replaceable cache | Rebuild from reviewed dependency declarations and interpreter requirements. It is not a backup source or credential store. If any credential contamination is found, protect the contaminated copy and rebuild under SEC-007 before removal. |

Mixed protected files inherit the handling of their most sensitive leaf. A
path name alone never proves that a file is replaceable: Matter storage and
virtual-environment findings have different recovery requirements even when
both are implementation-managed directories.

## `security_state.json`

| Object or fields | Classification | Required handling |
| --- | --- | --- |
| Root `session_secret` | Protected credential | Preserve exactly across compatible migration because it signs dashboard sessions. Rotate only through SEC-006 with an explicit forced-session-revocation decision. |
| Root `device_keys` and dynamic `device_keys.<deviceID>` map keys | Irreplaceable identity | Preserve the exact association between a stable device identity and its authentication material. Conflicts require review; never generate a replacement identity silently. |
| Device-key fields `current.key_id`, `previous.key_id` | Irreplaceable identity | Preserve key identifiers with their matching secret records so signed requests and the bounded rotation grace period remain coherent. |
| Device-key fields `current.secret`, `previous.secret` | Protected credential | Store only in protected authentication state, never in general device state, API responses after issuance, logs, fixtures, or long-term unencrypted archives. |
| Device-key fields `issued_at`, `expires_at`, parent `rotated_at`, and previous `revoked_at` | Retained history | Retain only the bounded timestamps required to enforce current/previous-key validity and rotation. They are security metadata, not an unbounded audit trail. |
| Device-key fields `status` | Durable user intent | Preserve explicit active/revoked security decisions. A discovery or restart must not reactivate revoked credentials. |
| Root `dashboard_users` and dynamic normalized-email keys | Irreplaceable identity | Preserve account identity and its association with the verifier and revocation state. Normalize and reconcile conflicts without printing account values. |
| User `password_hash` | Protected credential | Treat password verifiers as secrets. Preserve the strongest current verifier and allow a proven login to upgrade legacy hashes without retaining the old verifier indefinitely. |
| User `status`, `session_version` | Durable user intent | Preserve disablement and session-revocation generation. These fields control authorization and must not reset during migration. |
| User `created_at`, `updated_at` | Retained history | Retain the bounded account lifecycle timestamps; do not duplicate them into general history. |
| Legacy root `dashboard_email`, `dashboard_password_hash` | Obsolete data | Maintain only through the current login-upgrade compatibility path. Migrate to `dashboard_users`, validate access, rotate/upgrade as applicable, then remove through SEC-006. Until removal, the fields remain credential-sensitive. |
| Root `dashboard_sessions` and dynamic hashed-session keys | Protected credential | Treat active session records as revocable credential state. Preserve only for a deliberate compatible migration; exclude from long-term identity backups and expire/revoke them according to policy. |
| Session fields `email`, `user_version` | Irreplaceable identity | Keep only within the protected session record to bind it to the account and current revocation generation. They are not independent account authority. |
| Session fields `created_at`, `last_seen_at`, `expires_at` | Retained history | Retain only for the bounded active session lifetime and prune expired entries. |
| Root `device_enrollments` and dynamic device keys | Protected credential | Treat pending enrollment records as short-lived credential state. They need compatibility during a live cutover but must not enter long-term backups. |
| Enrollment `token_hash` | Protected credential | Preserve only for the bounded enrollment window and never expose or log it. |
| Enrollment `issued_at`, `expires_at` | Retained history | Retain solely to enforce the short enrollment lifetime; prune expired entries. |
| Legacy root `dashboard_key`, `dashboard_key_hash`, or equivalent static dashboard-key fields found by inventory | Obsolete data | Do not restore static dashboard-key authentication. Handle any surviving values as protected credentials until rotation/removal is complete. |
| Legacy root `nonces` and dynamic nonce entries | Obsolete data | The loader discards persisted nonces. Replay nonces now live only in bounded memory and are a replaceable cache. |
| In-memory replay nonce and rate-limit maps | Replaceable cache | Keep bounded and process-local. Restart may clear them; they must never be persisted as durable authority or backed up. |
| Any unknown root, user, device-key, session, or enrollment field | Obsolete data | Do not migrate without a named current reader, a closed schema decision, and an explicit classification. |

The recoverable security-identity set is the session signing secret, device
identity/key records, dashboard account/verifier records, and authorization
revocation state. Active browser sessions and pending enrollment tokens are
protected but short-lived; they are not long-term backup content. A recovery
that cannot validate the primary and last-known-good copy must fail closed
rather than initialize empty authentication state.

## Firebase service-account document

| Object or fields | Classification | Required handling |
| --- | --- | --- |
| `private_key` | Protected credential | Store only through the approved protected credential loader. Never print, log, embed in fixtures, or persist in general notification state. |
| `private_key_id` | Protected credential | Keep with the matching private key as credential metadata and rotate/remove with it. |
| `client_email`, `client_id` | Irreplaceable identity | Preserve the service-account identity with the approved credential version; do not treat rediscovered project metadata as a substitute. |
| `project_id` | Durable user intent | Preserve the explicitly selected Firebase project association. Validate it against deployment configuration during migration. |
| `type`, `auth_uri`, `token_uri`, `auth_provider_x509_cert_url`, `client_x509_cert_url`, `universe_domain` | Durable user intent | Preserve only as validated service-account configuration within the protected composite document. Do not independently copy fields into ordinary state. |
| Unknown or provider-added fields | Obsolete data | Do not copy into a closed replacement format without an identified SDK reader and explicit review. The original composite remains protected until cutover is validated. |

Even fields that are individually public inherit protected handling while
they reside in the credential document. Notification history and queued
payloads are separate DATA-001D concerns and must never receive service-account
material.

## Environment credentials and protected configuration

| Variable or setting | Classification | Required handling |
| --- | --- | --- |
| `TAPO_USERNAME`, `TAPO_PASSWORD`, `TAPO_CAMERA_USERNAME`, `TAPO_CAMERA_PASSWORD` | Protected credential | Move through the approved secret loader, validate device/camera access, rotate where supported, and remove legacy copies only after rollback testing. |
| `KOTIBOT_CLOUDFLARE_API_TOKEN` | Protected credential | Load from the approved secret store and rotate after verified cutover. Never place it in dashboard configuration or logs. |
| `KOTIBOT_CAMERA_TALK_TURN_USERNAME`, `KOTIBOT_CAMERA_TALK_TURN_CREDENTIAL`, and composite `KOTIBOT_CAMERA_TALK_ICE_SERVERS` entries containing credentials | Protected credential | Separate credential material from non-secret server URLs where the final loader permits. Treat the composite value as a credential until parsed and migrated safely. |
| `KOTIBOT_DASHBOARD_EMAIL` | Irreplaceable identity | Use only as an intentional bootstrap/account identity input. Do not print it or persist it outside protected security state. |
| `KOTIBOT_DASHBOARD_PASSWORD` | Protected credential | Accept only as protected bootstrap input, avoid process arguments/logs, hash into protected security state, then remove the plaintext source under SEC-006. |
| `KOTIBOT_ALLOWED_ORIGINS`, Cloudflare account/zone/tunnel identifiers, STUN/TURN URLs without embedded credentials, public hostname, trusted proxy CIDRs, RTSP path, NOAA user-agent identifier, Tapo recording directory, and `KOTIBOT_DATA_DIR` | Durable user intent | Preserve as validated operator/deployment configuration. These are not credentials unless a concrete value embeds one; composite or contaminated values inherit protected handling. |
| Runtime tuning and feature-policy variables recorded by SEC-001D, including timeouts, intervals, thresholds, thread/process choices, cookie/security flags, and Matter command/attestation options | Durable user intent | Preserve reviewed operator choices, use safe defaults, and validate security-sensitive settings. Do not back up transient process-derived values. |
| Unknown environment entries | Obsolete data | Do not migrate by copying an entire process environment. Add only named, classified entries after identifying a current reader. |

Environment-variable names may be documented; their runtime values may not.
SEC-002 selects the final per-secret mechanism. SEC-003 must retain only the
minimum compatibility loader required for a reversible migration.

## Matter controller identity and commissioning

| Object, input, or storage | Classification | Required handling |
| --- | --- | --- |
| Opaque controller/fabric storage databases, keys, certificates, counters, and provider-specific files | Protected credential | Preserve the validated storage tree atomically with private ownership/modes. Its internal identity and secret material is irreplaceable even when individual files are undocumented. |
| Stable fabric, controller, node, and operational-certificate identifiers inside controller storage | Irreplaceable identity | Preserve exact associations. Never recreate controller storage as a path-migration fallback because recommissioning may be required and node references may break. |
| Subscription worker copies of controller identity | Protected credential | Protect as credential-bearing duplicates. PATH-001C.4 must eliminate unnecessary duplication only after proving subscription workers can use a safe shared/read-only identity or separated cache. |
| Subscription/session freshness and reconnect state, once proven separable from controller identity | Replaceable cache | Reconstruct through resubscription. It is not part of the long-term controller backup after a safe schema/path split exists. |
| Commissioning `setup_code` and equivalent onboarding payload | Protected credential | Keep transient in memory or a protected one-use channel, redact from command logs and diagnostics, and never persist in device state, Matter state, shell history guidance, or audits. |
| Attestation-bypass policy and configured controller-tool path | Durable user intent | Treat as security-sensitive operator configuration. Validate explicitly and default safely; a persisted compatibility copy must not override the approved environment/configuration authority. |
| Persisted `chip_tool_storage` and `bypass_attestation` fields in `matter_state.json` | Obsolete data | Current runtime authority is explicit configuration. Do not migrate these ignored compatibility fields back into durable state. |
| Controller command output, inspection output, and repair diagnostics | Replaceable cache | Keep bounded and redacted. Never allow setup codes, keys, certificates, or full controller storage content into logs or long-term history. |

PATH-001C.4 remains open because relocating this identity requires a verified
backup, copy, service-identity validation, rollback exercise, and proof that
subscription storage no longer risks divergent controller copies.

## Virtual-environment findings

| Object or finding | Classification | Required handling |
| --- | --- | --- |
| Installed packages, generated console scripts, bytecode, caches, activation scripts, and interpreter links under `.venv` | Replaceable cache | Rebuild from the selected interpreter and reviewed dependency declarations. Exclude from durable backups and release archives. |
| Dependency declarations, lock files, and deliberate interpreter/platform requirements outside `.venv` | Durable user intent | Preserve, review, and pin sufficiently for a reproducible rebuild. The generated environment is not the authority. |
| Ordinary running-process state derived from the environment | Reconstructible live state | Recreate at service start; do not persist snapshots of the full environment. |
| Unexpected `.pth`, activation customization, package configuration, or embedded credential material | Protected credential | None was approved by the reviewed inventory. If discovered later, isolate the contaminated environment, rotate the credential, and rebuild under SEC-007 rather than migrating the contamination. |
| Group-writable virtual-environment/code permissions found by SEC-001D | Obsolete data | Do not preserve insecure permission metadata. Rebuild with the deployment ownership/mode contract finalized by PATH-002. |

SEC-007 remains conditional: the reviewed findings did not establish a
credential inside `.venv`, but any later positive finding requires a protected
quarantine and clean rebuild.

## DATA-001C review gate

- [c] Every known authentication-state container and leaf field has a primary classification and recovery rule.
- [c] Firebase service-account identity, configuration, key material, and unknown-field handling are explicit without recording values.
- [c] Every credential-bearing environment name and every reviewed non-secret protected/operator configuration class has explicit handling.
- [c] Matter controller/fabric identity, subscription copies, rollback/repair storage, commissioning inputs, attestation policy, and obsolete persisted compatibility fields are classified.
- [c] Virtual-environment content, dependency authority, contamination handling, and permission findings are classified.
- [c] Short-lived sessions/enrollments, replaceable in-memory security caches, durable revocation choices, protected recovery material, and obsolete compatibility fields have distinct retention/backup treatment.
- [c] The production migration is copy-first and fails closed on invalid state, symlinks, or a missing primary with a remaining recovery copy; legacy source copies remain available for rollback.
- [c] No runtime contents, credential values, personal-data values, account values, device identifiers, setup codes, controller contents, command output, or absolute home paths were captured.

DATA-001C is complete. DATA-001 remains open pending DATA-001D.

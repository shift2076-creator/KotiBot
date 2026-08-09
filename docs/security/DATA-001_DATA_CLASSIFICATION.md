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

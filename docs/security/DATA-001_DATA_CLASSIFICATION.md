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

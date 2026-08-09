# DATA-001 — Runtime data classification

Source commit reviewed: `61281ff18ba286a10b10e4f811786db6d0de6efb`

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
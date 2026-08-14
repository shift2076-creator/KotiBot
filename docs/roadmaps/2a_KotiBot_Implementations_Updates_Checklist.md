# KotiBot Implementations and Updates Working Checklist

Status updated through: `70d119c386017c6c39e280d6fc6aa756ee3eae52`
Roadmap: `KotiBot_Implementations_Updates_Roadmap.md`
Stability companion: `KotiBot_Fixes_Stability_Checklist.md`

This checklist owns new capabilities and deliberate product updates. Fixes, hardening, migrations, regressions, and release auditing belong in the Fixes and Stability pair. No new item is complete until its children and integrated result are verified.

## Implementation execution order

1. Complete **PLATFORM-001.1–001.6** so paths, services, permissions/ACLs, dependencies, installation, and rollback have shared Linux/Windows contracts before setup code is written.
2. Complete **SECACT-001** so the current Security System Actions page presents canonical configured responses before the setup wizard creates additional actions.
3. Complete **AUTH-001** so first-login Firebase trust, local session continuity, recovery, and migration are defined before the setup wizard creates an administrator.
4. Build **SETUP-001–008** against the platform, action-summary, and authentication contracts.
5. Implement **FEEDBACK-001** and **LAYOUT-001** through their shared owners rather than page-specific render paths.
6. Continue camera/media, Tapo-zone, custom-mode, environment, and Matter work in dependency order.

## Cross-platform Linux, Windows, and SBC support
- [ ] **PLATFORM-001** Deliver supported Linux and Windows operation while preserving Raspberry Pi-class single-board computers as a primary efficiency target. Dependency: SEC-004–006, PATH-001D, STATE-007. Size: XL.
  - [ ] **PLATFORM-001.1** Define the supported Linux distributions, Windows releases, CPU architectures, Python versions, Raspberry Pi models, service/desktop modes, and per-subsystem capability matrix.
  - [ ] **PLATFORM-001.2** Define and implement one platform-adapter contract for paths, services, process control, permissions/ACLs, temporary data, external-tool discovery, and platform capability reporting.
  - [ ] **PLATFORM-001.3** Implement Windows-native durable-state, cache, temporary, credential, log, media, and package roots with private ACL validation and zero source-tree runtime writes.
  - [ ] **PLATFORM-001.4** Route Linux service and desktop operation through the same contract while preserving current systemd hardening, private modes, and known-good runtime behavior.
  - [ ] **PLATFORM-001.5** Normalize FFmpeg, Matter `chip-tool`, Bluetooth, notification, and other external-dependency discovery with explicit supported, degraded, and unavailable results per platform.
  - [ ] **PLATFORM-001.6** Implement repeatable Linux and Windows install, service registration/start/stop, upgrade, backup, restore, rollback, and uninstall-residue procedures.
  - [ ] **PLATFORM-001.7** Add automated Linux/Windows test coverage plus physical Raspberry Pi startup, idle-resource, disk-I/O, dashboard, camera, and device-event latency budgets.
  - [ ] **PLATFORM-001.8** Update platform documentation and release claims only after the complete clean-install, upgrade, restart, security, permissions/ACL, rollback, feature, and performance matrices pass.

## Security System Actions response summaries
- [ ] **SECACT-001** Replace zone/device grouping on the Security System Actions page with canonical action-based summaries before setup-wizard implementation begins. Dependency: none. Size: L.
  - [ ] **SECACT-001.1** Inventory every saved security-action type, target form, timer, repeat rule, ordering field, mode restriction, edit route, and deletion/reference path.
  - [ ] **SECACT-001.2** Define one action-summary registry owned by the canonical action schema rather than by zones or rendered device cards.
  - [ ] **SECACT-001.3** Render clear primary labels including `Turn On Devices`, `Turn Off Devices`, `Play “Sound Name”`, `Notify Control Clients`, and `Start Recording`, with singular/plural and target-count detail where applicable.
  - [ ] **SECACT-001.4** Preserve action identity, ordering, editing, deletion, timers, repeats, mode restrictions, unavailable-target handling, and mixed-action sequences without restoring zone grouping.
  - [ ] **SECACT-001.5** Verify every action/target combination, empty and legacy states, renamed/deleted targets, responsive layouts, restart persistence, and later setup-wizard interoperability.

## Universal three-second popup feedback
- [ ] **FEEDBACK-001** Extend the existing shared three-second popup modal through one audited event registry with semantic success/warning presentation and individually disableable instances. Dependency: none. Size: L.
  - [ ] **FEEDBACK-001.1** Inventory eligible deliberate user outcomes—including security-mode changes, scene changes, provisioning, and settings saves—and exclude continuous sensors, synchronization chatter, and other high-frequency events.
  - [ ] **FEEDBACK-001.2** Define one canonical event/presentation registry with stable instance IDs, success/warning severity, text ownership, the existing three-second hold/fade contract, and no duplicate page-specific modal logic.
  - [ ] **FEEDBACK-001.3** Render success with a large KotiBot-mint thumbs-up centered above the success text and warning with a large gold exclamation centered above the warning text; use no glow and preserve explicit readable and accessible wording.
  - [ ] **FEEDBACK-001.4** Add a Popup Feedback section on the KotiBot Settings page whose per-instance controls are generated from the same registry and persisted as deliberate server-owned user intent.
  - [ ] **FEEDBACK-001.5** Integrate the approved security, scene, provisioning, settings, and other audited events with predictable replacement/deduplication, warning precedence, modal-stack safety, and no added polling.
  - [ ] **FEEDBACK-001.6** Verify enable/disable persistence across reload/restart, rapid actions, failure/retry, navigation, reduced motion, screen readers, narrow/medium/wide viewports, and absence of noisy or duplicate feedback.

## Firebase email authentication for first login
- [ ] **AUTH-001** Replace password-based first-administrator login/bootstrap with Firebase Email Authentication, then issue and retain KotiBot's existing protected local session credentials for subsequent authenticated access. Dependency: SEC-004, PLATFORM-001.2–001.6. Size: L.
  - [ ] **AUTH-001.1** Define the first-login state machine, approved Firebase project/audience/issuer, authorized-email policy, stable Firebase UID-to-KotiBot identity mapping, replay boundary, offline/unavailable behavior, and explicit reauthentication/recovery rules without a password fallback that weakens authentication.
  - [ ] **AUTH-001.2** Implement the first-login Firebase email flow under the existing CSP, origin, login-overlay, rate-limit, and error-redaction boundaries; never expose dashboard data beneath or before authentication.
  - [ ] **AUTH-001.3** Verify Firebase ID tokens server-side through the approved SDK/service-account owner, including signature, issuer, audience, expiry, revocation, email verification, authorized identity, and concurrent first-login protection.
  - [ ] **AUTH-001.4** Atomically bind the verified Firebase UID/email to the protected KotiBot administrator identity, issue the existing secure local session, and retain only required local account/session material in protected credential storage—never a Firebase password or reusable token in ordinary state.
  - [ ] **AUTH-001.5** Migrate the existing administrator without lockout; verify first login, subsequent local session continuity, logout, expiry, revocation, email change, lost-client recovery, Firebase outage, restart, rollback, and absence of authentication values from APIs, logs, browser-visible state, and ordinary JSON.

## Shared dashboard layout alignment
- [complete] **LAYOUT-001** Center partially filled Controls, Monitor, and Sensors content grids and vertically center the navigation aside in greater-than-two-thirds mode through the correct shared responsive layout owners. Dependency: none. Size: M.
  - [complete] **LAYOUT-001.1** Identify the shared grid and aside layout owners and define one responsive contract that preserves canonical card ordering, widths, gaps, focus order, scrolling, and full-row alignment without page-specific duplicate CSS.
  - [complete] **LAYOUT-001.2** Center zero/one/partial-row content on Controls, Monitor, and Sensors only when the rendered cards do not fill the available column allocation; keep complete rows and dynamic updates stable.
  - [complete] **LAYOUT-001.3** Vertically center the aside only in greater-than-two-thirds mode while preserving short-viewport scrolling, sticky/fixed behavior, safe-area spacing, keyboard access, and existing layouts at smaller ratios.
  - [complete] **LAYOUT-001.4** Verify empty, single-card, partial-row, full-row, hidden/filtered, long-label, live-add/remove, narrow/medium/wide, short-height, touch, pointer, and keyboard cases on all three pages.


## Initial setup wizard
- [ ] **SETUP-001** Define initialized/uninitialized state and maintenance re-entry through the shared platform contract. Dependency: SEC-003–006, PLATFORM-001.1–001.6, SECACT-001, AUTH-001. Size: S.
- [ ] **SETUP-002** System/runtime preflight screen. Dependency: PATH-001, STATE-003. Size: M.
- [ ] **SETUP-003** Administrator, dashboard-origin, and exact local trusted-host setup. Detect or collect the approved LAN hostname/IP, require confirmation, persist `KOTIBOT_TRUSTED_HOSTS` without wildcards through the platform adapter—systemd configuration on Linux and the approved Windows service/configuration mechanism on Windows—and verify signed Android telemetry through the configured endpoint. Dependency: SETUP-001, PLATFORM-001.2–001.6. Size: M.
- [ ] **SETUP-004** Secure integration credential entry and validation. Dependency: SEC-003. Size: M.
- [ ] **SETUP-005** Tapo discovery and zone-import review. Dependency: ZONE-001/002 research. Size: L.
  - [ ] **SETUP-005.1** Validate credentials and run bounded Tapo discovery with progress, cancellation, and redacted errors.
  - [ ] **SETUP-005.2** Normalize discovered devices, capabilities, homes, and rooms into a review-only model.
  - [ ] **SETUP-005.3** Present device inclusion, naming, zone import, merge/rename/defer, and conflict choices.
  - [ ] **SETUP-005.4** Commit approved choices atomically and verify retry, resume, rollback, and idempotent rerun.
- [ ] **SETUP-006** Matter/Android enrollment guidance. Dependency: SETUP-001. Size: M.
- [ ] **SETUP-007** Review, atomic commit, resume, rollback, and recovery. Dependency: SETUP-002–006. Size: L.
  - [ ] **SETUP-007.1** Build a complete redacted review showing every pending configuration, credential reference, and device/zone action.
  - [ ] **SETUP-007.2** Persist resumable wizard progress without storing credential values in ordinary state or browser storage.
  - [ ] **SETUP-007.3** Validate all dependencies and stage the complete configuration before changing active state.
  - [ ] **SETUP-007.4** Commit atomically with rollback on any failure and clear temporary setup material safely.
  - [ ] **SETUP-007.5** Exercise interruption, restart, resume, cancel, rollback, recovery, and successful maintenance re-entry.
- [ ] **SETUP-008** Clean-install end-to-end test on every supported Linux/Windows host mode, including the Raspberry Pi resource target. Dependency: SETUP-007, PLATFORM-001.7. Size: M.

## Camera foundation
- [ ] **CAM-001** Define Android frame timestamp contract in UTC. Dependency: none. Size: S.
- [ ] **CAM-002** Send capture time from Android and retain server receive fallback. Dependency: CAM-001. Size: M.
- [ ] **CAM-003** Add responsive localized timestamp and stale-feed overlay. Dependency: CAM-002. Size: M.
- [ ] **CAM-004** Decide viewer-only versus burned-in export timestamps. Dependency: CAM-001. Status: Decision.
- [ ] **MEDIA-001** Add load-aware Android recording-chunk transfer admission and deferred delivery without interrupting capture or starving completed recordings. Dependency: STAB-013, PATH-001C.7. Size: L.
  - [ ] **MEDIA-001.1** Define a bounded server-capacity signal from active Tapo/Android recordings, transcodes, upload/reassembly work, queue depth, memory, and disk pressure; use thresholds and hysteresis rather than broad high-frequency polling.
  - [ ] **MEDIA-001.2** Add authenticated server admission/defer responses with bounded retry guidance, fairness, priority, and no credential, topology, or unrelated load disclosure.
  - [ ] **MEDIA-001.3** Keep Android capture writing the verified private chunk spool while transfer is deferred; resume through event-driven or bounded-backoff scheduling without busy polling, wake storms, duplicate uploads, or unbounded device storage.
  - [ ] **MEDIA-001.4** Preserve idempotent chunk identity, ordering, integrity verification, acknowledgement, retry/resume, atomic reassembly, and cleanup across accepted, deferred, interrupted, and restarted transfers.
  - [ ] **MEDIA-001.5** Verify idle/normal/saturated recovery, many simultaneous Tapo recordings, multiple Android clients, prolonged deferral, fairness/no starvation, disconnect, server/client restart, storage limits, final playback equivalence, and Raspberry Pi CPU/memory/disk/network impact.
- [ ] **TCAM-001** Verify exact Tapo camera capabilities against installed libraries/models. Dependency: none. Size: M research.
- [ ] **TCAM-002** Capability-driven camera control API/UI. Dependency: TCAM-001. Size: L.
  - [ ] **TCAM-002.1** Define normalized camera capability and command contracts from verified model/library support.
  - [ ] **TCAM-002.2** Implement authenticated server adapters with timeouts, redacted errors, and per-command results.
  - [ ] **TCAM-002.3** Render only supported controls and states in responsive camera settings and monitor views.
  - [ ] **TCAM-002.4** Verify supported models, unsupported capabilities, offline recovery, concurrent commands, and regressions.
- [ ] **TCAM-003** Determine push, polling, or vision source for motion. Dependency: TCAM-001. Size: M research.
- [ ] **TCAM-004** Normalize/deduplicate motion events and integrate Activities. Dependency: TCAM-003. Size: L.
  - [ ] **TCAM-004.1** Define the canonical Tapo motion event, source timestamps, confidence/status fields, and deduplication window.
  - [ ] **TCAM-004.2** Implement source ingestion and bounded deduplication without persisting reconstructible raw telemetry.
  - [ ] **TCAM-004.3** Record normalized start/clear Activity entries with correct camera identity and retention behavior.
  - [ ] **TCAM-004.4** Verify repeated events, reconnects, clock skew, restart baselines, and false-event suppression.
- [ ] **TCAM-005** Integrate motion with automations, notifications, and security actions. Dependency: TCAM-004. Size: L.
  - [ ] **TCAM-005.1** Expose canonical Tapo motion triggers through the ordinary automation engine.
  - [ ] **TCAM-005.2** Integrate notification targeting, cooldowns, and redacted Activity/audit results.
  - [ ] **TCAM-005.3** Integrate security actions, recording targets, timers, repeats, and mode restrictions.
  - [ ] **TCAM-005.4** Verify deduplication across consumers, restart behavior, unavailable targets, and partial failures.

## Tapo zones
- [ ] **ZONE-001** Verify Tapo room-read capability. Dependency: none. Size: S research.
- [ ] **ZONE-002** Verify Tapo room-write capability and limitations. Dependency: ZONE-001. Size: S research.
- [ ] **ZONE-003** Define stable Tapo-home/room/device to KotiBot-zone mapping. Dependency: ZONE-001. Size: M.
- [ ] **ZONE-004** Import rooms during setup with merge/rename/defer choices. Dependency: ZONE-003, SETUP-005. Size: L.
  - [ ] **ZONE-004.1** Fetch and normalize Tapo home/room/device mappings into a non-mutating import preview.
  - [ ] **ZONE-004.2** Implement per-room merge, rename, create, and defer decisions with collision validation.
  - [ ] **ZONE-004.3** Apply the reviewed import atomically while preserving stable device and zone references.
  - [ ] **ZONE-004.4** Verify restart persistence, retry behavior, rollback, and idempotent re-import.
- [ ] **ZONE-005** Implement explicit outbound sync only if supported. Dependency: ZONE-002/003. Size: L; conditional.
  - [ ] **ZONE-005.1** Confirm the supported write operations and stop this task as not applicable when safe outbound room sync is unavailable.
  - [ ] **ZONE-005.2** Add a preview showing exact outbound changes, unsupported devices, and conflicts without writing.
  - [ ] **ZONE-005.3** Apply only explicit user-approved changes with per-operation results and rollback data.
  - [ ] **ZONE-005.4** Verify partial-failure recovery, idempotent retry, rate limiting, and no automatic background writes.
- [ ] **ZONE-006** Conflict handling and rollback. Dependency: ZONE-004/005. Size: M.
- [ ] **ZONE-007** Verify renames preserve schemes, favorites, automations, and IDs. Dependency: ZONE-004–006. Size: M.

## Custom modes
- [ ] **LIGHT-001** Versioned custom zone-lighting mode schema with stable IDs. Dependency: STATE-001–003. Size: M.
- [ ] **LIGHT-002** Editor: create, preview, duplicate, rename, order, favorite, delete. Dependency: LIGHT-001. Size: L.
  - [ ] **LIGHT-002.1** Implement create, validate, preview, and save flows against the versioned mode schema.
  - [ ] **LIGHT-002.2** Implement duplicate and rename while preserving stable IDs and rejecting collisions.
  - [ ] **LIGHT-002.3** Implement ordering and favorite controls with durable persistence and responsive UI behavior.
  - [ ] **LIGHT-002.4** Implement reference-aware deletion confirmation, fallback behavior, and editor regression tests.
- [ ] **LIGHT-003** Per-device preset/action model. Dependency: LIGHT-001. Size: L.
  - [ ] **LIGHT-003.1** Define normalized per-device power, brightness, temperature, color, transition, and no-change actions.
  - [ ] **LIGHT-003.2** Add capability-aware validation and defaults for bulbs, plugs, extenders, and unsupported targets.
  - [ ] **LIGHT-003.3** Implement preview and apply execution with bounded concurrency, partial results, and rollback information.
  - [ ] **LIGHT-003.4** Add schema migration, persistence, and mixed-device regression fixtures.
- [ ] **LIGHT-004** Homepage, zone, schedule, and automation integration. Dependency: LIGHT-002/003. Size: L.
  - [ ] **LIGHT-004.1** Integrate custom modes into homepage and zone controls with correct active-state reconciliation.
  - [ ] **LIGHT-004.2** Integrate custom modes into schedules and ordinary automations using stable IDs.
  - [ ] **LIGHT-004.3** Integrate custom modes into security actions without duplicating execution logic.
  - [ ] **LIGHT-004.4** Verify restart, rename, delete, offline-device, partial-failure, and responsive UI behavior.
- [ ] **LIGHT-005** Reference-aware deletion and migration tests. Dependency: LIGHT-004. Size: M.
- [ ] **SECMODE-001** Versioned custom security-mode schema. Dependency: LIGHT-001 patterns. Size: L.
  - [ ] **SECMODE-001.1** Define stable mode IDs, display metadata, activation policy, sensor/action references, delays, and fallback fields.
  - [ ] **SECMODE-001.2** Add strict schema validation, normalization, version upgrades, and closed unknown-field handling.
  - [ ] **SECMODE-001.3** Migrate built-in At Home, Asleep, and Away behavior into compatible canonical definitions without changing behavior.
  - [ ] **SECMODE-001.4** Add round-trip, upgrade, invalid-input, and reference-integrity tests.
- [ ] **SECMODE-002** Sensor/action/delay editor and validation. Dependency: SECMODE-001. Size: XL.
  - [ ] **SECMODE-002.1** Build mode create, duplicate, rename, ordering, and metadata editing.
  - [ ] **SECMODE-002.2** Build sensor/trigger selection with capability-aware event and threshold configuration.
  - [ ] **SECMODE-002.3** Build action/target editing for sound, notification, recording, and device-control responses.
  - [ ] **SECMODE-002.4** Build entry, exit, trigger, cooldown, repeat, and post-trigger delay controls with validation.
  - [ ] **SECMODE-002.5** Add complete reference validation, conflict reporting, preview, and safe save/cancel behavior.
  - [ ] **SECMODE-002.6** Verify accessibility, responsive layout, persistence, invalid input, and complex multi-rule editing.
- [ ] **SECMODE-003** Safe activation, fallback mode, and audit records. Dependency: SECMODE-002. Size: L.
  - [ ] **SECMODE-003.1** Define and implement atomic activation, deactivation, and mode-transition state handling.
  - [ ] **SECMODE-003.2** Implement missing/invalid-mode fallback without firing false triggers or silently disarming.
  - [ ] **SECMODE-003.3** Emit bounded redacted audit records for activation, fallback, failures, and user changes.
  - [ ] **SECMODE-003.4** Verify restart restoration, concurrent requests, unavailable devices, partial action failure, and rollback.
- [ ] **SECMODE-004** Homepage, automation, and reference-aware deletion integration. Dependency: SECMODE-003. Size: L.
  - [ ] **SECMODE-004.1** Integrate custom modes into homepage controls and active-mode rendering.
  - [ ] **SECMODE-004.2** Integrate stable security-mode references into automations and schedules.
  - [ ] **SECMODE-004.3** Implement reference-aware rename/delete previews, blocking conflicts, and explicit fallback reassignment.
  - [ ] **SECMODE-004.4** Verify responsive UI, restart, stale references, deletion recovery, and existing built-in behavior.

## Environment and Matter validation
- [ ] **ENV-001** Rank external data: alerts, precipitation, wind, UV, AQI, daylight, pollen. Dependency: decision. Size: S.
- [ ] **ENV-002** Provider adapter/cache/attribution/failure architecture. Dependency: ENV-001. Size: M.
- [ ] **ENV-003** Responsive environmental-page information hierarchy. Dependency: ENV-001. Size: M.
- [ ] **ENV-004** Implement selected external panels and last-known-good states. Dependency: ENV-002/003. Size: L.
  - [ ] **ENV-004.1** Implement provider adapters and normalized models for the selected external datasets.
  - [ ] **ENV-004.2** Add bounded cache, attribution, freshness, timeout, and last-known-good handling.
  - [ ] **ENV-004.3** Render responsive loading, current, stale, partial, unavailable, and attribution states.
  - [ ] **ENV-004.4** Verify provider failures, malformed data, restart cache behavior, rate limits, and accessibility.
- [ ] **ENV-005** Indoor/outdoor zone trends. Dependency: ENV-003. Size: L.
  - [ ] **ENV-005.1** Define normalized trend samples, units, aggregation windows, retention, and missing-data behavior.
  - [ ] **ENV-005.2** Implement bounded indoor per-zone and outdoor trend storage without duplicating live telemetry.
  - [ ] **ENV-005.3** Build responsive accessible trend views with unit conversion and source/freshness context.
  - [ ] **ENV-005.4** Verify sparse data, sensor replacement, timezone boundaries, restart, retention pruning, and performance.
- [ ] **MATTER-001** Select/acquire non-Tapo Matter hardware. Dependency: hardware. Status: Blocked.
- [ ] **MATTER-002** Build fixtures and written hardware test matrix. Dependency: none. Size: M.
- [ ] **MATTER-003** Validate outlet, dimmer, color light, contact, motion, environment, and multi-endpoint devices. Dependency: MATTER-001/002. Size: L.
  - [ ] **MATTER-003.1** Validate commissioning, discovery, identity, and basic control for outlets and on/off devices.
  - [ ] **MATTER-003.2** Validate level, color-temperature, and full-color capabilities for dimmers and lights.
  - [ ] **MATTER-003.3** Validate contact, motion/occupancy, temperature, humidity, battery, and stale-state behavior.
  - [ ] **MATTER-003.4** Validate multi-endpoint identity, grouping, naming, removal, and independent endpoint control.
  - [ ] **MATTER-003.5** Record model/firmware results, unsupported capabilities, latency, failures, and required fixes in the hardware matrix.
- [ ] **MATTER-004** Validate restart, subscription recovery, latency, stale state, automation, removal, and recommissioning. Dependency: MATTER-003. Size: L.
  - [ ] **MATTER-004.1** Validate server/controller restart and cold-start baselines without false automation or security events.
  - [ ] **MATTER-004.2** Validate subscription interruption, backoff, recovery, duplicate suppression, and stale-state transitions.
  - [ ] **MATTER-004.3** Measure command/event latency and verify automation and security-action timing under normal and degraded conditions.
  - [ ] **MATTER-004.4** Validate device/endpoint removal, reference cleanup, offline recovery, and recommissioning.
  - [ ] **MATTER-004.5** Validate controller backup/restore, fabric identity preservation, and regression behavior across all tested device classes.

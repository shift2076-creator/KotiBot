# KotiBot Implementations and Updates Roadmap

Baseline: `38189fd18efdd1ea5dd7fccf48f6874d186226a2`
Status updated through: `70d119c386017c6c39e280d6fc6aa756ee3eae52`
Prepared: 2026-08-11
Current product line: KotiBot 0.8
Companion: `KotiBot_Implementations_Updates_Checklist.md`
Stability companion: `KotiBot_Fixes_Stability_Roadmap.md`

## Purpose

This roadmap owns new capabilities, deliberate behavior changes, platform expansion, information architecture, setup experience, and feature integration. Defects, regressions, hardening, migrations, and release auditing remain in the Fixes and Stability pair.

## Working rules

1. PRE code must always come from the latest committed SHA supplied for that task.
2. Back up all durable runtime data before schema, path, or persistence changes.
3. Security controls stay enabled while compatibility problems are corrected; CSP, authentication, and origin checks are not weakened to make a feature work.
4. Every regression fix receives an automated test when practical.
5. Every feature must define failure behavior, logging, persistence, authorization, and rollback before implementation.
6. Hardware-dependent work may be designed and fixture-tested early, but cannot be marked complete without physical-device validation.
7. KotiBot must never create installation, household, device, activity, credential, cache, log, recording, or other runtime data beneath the Git worktree.
8. Persist user intent and irreplaceable identity; rebuild observable device state; cache replaceable external data; protect credentials separately.
9. On startup, live device state begins as unknown. The first authoritative Tapo, Matter, or Android synchronization establishes a baseline and must not generate a false automation or security event.

Classification rule: implementation items must define failure behavior, security boundaries, persistence ownership, resource impact, rollback, and verification. Any newly exposed defect is recorded separately in the Fixes and Stability pair.

## Implementation milestone overview

| Track | Target | Primary outcome | Exit gate |
|---|---:|---|---|
| Cross-platform foundation | Before setup implementation / 0.9.0 support gate | Native Linux and Windows operation with Raspberry Pi-class efficiency | Platform, install, ACL/permission, service, dependency, rollback, and performance matrices pass |
| Security-action summaries | Before setup implementation | Present canonical configured responses rather than devices grouped by zone | Every action type, edit/delete path, and mixed-action case renders correctly |
| Popup feedback framework | 0.8.x | Consistent three-second success/warning feedback with per-instance settings | Registry, accessibility, persistence, deduplication, and event matrices pass |
| Firebase first-login authentication | Before setup implementation | Verify the first administrator through Firebase email, then retain KotiBot-owned protected local session continuity | Token, bootstrap, migration, recovery, revocation, outage, and exposure matrices pass |
| Dashboard layout alignment | 0.8.x | Center partial Controls/Monitor/Sensors grids and the wide-mode aside through shared responsive owners | Partial/full grid, height, viewport, input, and accessibility matrices pass |
| Initial setup | 0.8.3 | Secure resumable first-run and maintenance wizard on supported platforms | Clean installation reaches a working dashboard without manual file editing |
| Camera and recording foundation | 0.8.4 | Timestamp Android feeds, preserve chunked capture, defer transfer under load, and establish Tapo control/motion support | Timestamp, chunk/reassembly, load recovery, control, motion, authorization, and resource tests pass |
| Tapo zone integration | 0.8.5 | Import Tapo zones and define controlled outbound synchronization | Import, conflict, rename, and unsupported-operation behavior pass |
| Custom modes | 0.8.6 | Custom zone-lighting and security modes | Versioned schemas, editors, execution, migration, and automation integration pass |
| Environment and Matter | 0.9.0 | Expand environment intelligence and validate non-Tapo Matter hardware | External-data resilience and physical-hardware matrix pass |

---

## Cross-platform Linux, Windows, and SBC support

KotiBot will support both Linux and Windows without weakening its security, persistence, or service-operation contracts. Raspberry Pi-class single-board computers remain a primary efficiency target rather than a special-case fork.

### Support contract

- Define supported Linux distributions, Windows releases, CPU architectures, Python versions, and service/desktop operating modes.
- Keep platform-specific paths, permissions, services, process control, and external-tool discovery behind explicit platform adapters.
- Use native durable-state, cache, temporary, credential, log, media, and package locations on each platform.
- Preserve Linux systemd hardening while providing a Windows service/configuration equivalent.
- Define explicit supported, degraded, and unavailable behavior for Matter, FFmpeg camera work, Bluetooth, notifications, and other external dependencies.
- Maintain a bounded Raspberry Pi performance budget covering startup, idle CPU/memory, device-event latency, disk writes, preview/recording work, and dashboard responsiveness.

### Exit criteria

- Linux and Windows clean-install, upgrade, restart, rollback, permissions/ACL, backup/restore, and uninstall-residue matrices pass.
- Cross-platform tests verify that no runtime path falls inside the source tree.
- Raspberry Pi-class hardware meets the published resource and latency budget.
- README and release claims distinguish current support from roadmap targets until the complete matrix passes.

## Security-action response summaries — required before setup

Before the new setup wizard is implemented, the Security System Actions page must stop presenting saved responses as devices grouped by zone. It must summarize the actions the wizard actually created, using the canonical action schema and action identity.

Recommended primary labels:

- `Turn On Devices`
- `Turn Off Devices`
- `Play “Sound Name”`
- `Notify Control Clients`
- `Start Recording`

Each displayed row must preserve editing, deletion, ordering, timers, repeat rules, mode restrictions, and target details without reverting to zone-based grouping. Singular actions remain singular; multi-target power actions may summarize their target count without making the zone the owner.

The setup wizard is blocked until this action-first representation and its complete action-type matrix are verified.

## Universal three-second popup feedback

Extend the existing shared three-second popup modal through one audited registry rather than adding page-specific success messages.

### Semantic presentation

- Success: a large KotiBot-mint thumbs-up centered above explicit success text, without glow.
- Warning: a large gold exclamation centered above explicit warning text, without glow.
- Icons reinforce meaning but never replace readable text or accessible status semantics.
- Preserve the existing three-second hold and bounded fade unless a warning requires deliberate acknowledgement; do not use longer timers to conceal slow operations.

### Candidate-event audit

Audit security-mode changes, scene changes, provisioning, settings saves, and other deliberate user actions. Exclude continuous sensor updates, repeated state synchronization, and other high-frequency events that would create noise.

### Settings ownership

Add one Popup Feedback section on the KotiBot Settings page, driven by the same event registry. Every eligible popup instance must have its own disable control without duplicating event names or persistence logic. Preferences are deliberate durable user intent and must not live only in browser-local state.

### Exit criteria

- Rapid actions deduplicate or replace feedback predictably.
- Warnings take precedence over success feedback.
- Modal stacking, navigation, failure, retry, reduced-motion, and screen-reader behavior are verified.
- Disabled instances remain disabled after reload and restart without suppressing unrelated feedback.

## Firebase email authentication for first login

Replace the password-based first-administrator login/bootstrap with Firebase Email Authentication. Firebase proves the initial identity; after successful server-side verification, KotiBot binds that stable Firebase identity to its protected local administrator record and issues the existing KotiBot session for subsequent authenticated access.

Security and ownership requirements:

- The browser never sends a Firebase password to KotiBot. The server accepts only an ID token and verifies its signature, issuer, audience, expiry, revocation, verified-email status, and authorized identity through the approved Firebase owner.
- First-login bootstrap is atomic and single-winner. Concurrent or replayed attempts cannot replace the administrator or create a second privileged identity.
- KotiBot stores only the stable Firebase identity mapping and its existing local account/session material in protected credential state. Firebase passwords, reusable tokens, and refresh credentials never enter ordinary JSON, logs, audit output, or KotiBot APIs.
- Subsequent access uses the existing protected KotiBot session contract. Logout, expiry, revocation, email changes, lost-client recovery, and required reauthentication must be explicit and fail closed.
- Existing-administrator migration includes a tested rollback/recovery path that cannot silently re-enable weaker password bootstrap or lock out the household.
- Firebase outage behavior is bounded: an already valid KotiBot session follows the local session contract, while a required new authentication never bypasses Firebase verification.

Exit criteria:

- First login, subsequent session continuity, restart, concurrent bootstrap, invalid/expired/revoked token, unauthorized/unverified email, Firebase outage, logout, expiry, recovery, migration, and rollback matrices pass.
- Login overlay, same-origin, CSP, rate limiting, public-route, cookie, and unauthenticated-exposure protections remain intact.
- No authentication value appears in ordinary state, browser-visible bootstrap data, application/audit logs, or error output.

## Shared dashboard layout alignment

Use the shared responsive grid and aside owners to improve balance without changing device order or inventing page-specific positioning rules.

- Center Controls, Monitor, and Sensors cards when the rendered items do not fill the columns allocated to the current viewport.
- Preserve stable card widths, gaps, canonical ordering, focus order, and full-row behavior as devices are hidden, filtered, added, removed, or updated live.
- Vertically center the navigation aside only in greater-than-two-thirds mode. Short-height screens must remain scrollable and keyboard accessible, with existing behavior preserved at smaller ratios.
- Verify empty, one-card, partial-row, full-row, long-label, narrow/medium/wide, short-height, touch, pointer, keyboard, and live-update cases on all three pages.


## Milestone 2 — Initial setup wizard

**Implementation gate:** Do not begin the setup wizard until PLATFORM-001.1–001.6, SECACT-001, and AUTH-001 are complete. The wizard must use platform-native configuration/service mechanisms rather than embedding Linux-only systemd assumptions.

The setup wizard depends on the secure configuration architecture. It must never write passwords back into JSON.

### Proposed flow

1. **Welcome and system check** — Python/runtime versions, writable state paths, network status, time/timezone.
2. **Administrator authentication** — verify the approved Firebase email identity, atomically bind the first administrator, and issue the protected local KotiBot session without collecting or storing a Firebase password.
3. **Dashboard address** — configure exact HTTPS origin(s), proxy expectations, and Cloudflare/public-host status.
4. **Core services** — notifications, weather/environment provider, media/storage paths.
5. **Tapo integration** — collect credentials directly into the secure store, test authentication, discover devices.
6. **Zone import** — show Tapo/KotiBot zone candidates and let the user merge, rename, or defer them.
7. **Matter and Android enrollment** — verify controller state and present enrollment instructions.
8. **Review and validation** — display only non-secret configuration and run end-to-end checks.
9. **Atomic commit** — write final configuration, mark setup complete, and start normal dashboard access.

Requirements:

- Resumable after interruption.
- Idempotent and safe to rerun in maintenance mode.
- No partially configured dashboard is exposed.
- Secret fields are never returned to the browser after submission.
- Failed tests identify the exact corrective action.
- A recovery path exists if allowed-origin configuration prevents login.

---

## Milestone 3 — Camera foundation

### 3.1 Timestamp on Android camera feeds

Use the frame-capture timestamp as the authoritative value, not the viewer's current clock.

Design:

- Android client sends capture time with each frame/stream update.
- Server normalizes it to UTC and retains source/device identity.
- UI overlays localized date/time without modifying the original frame bytes.
- If source time is unavailable, use server receive time and mark it as a fallback.
- Show a stale-feed indicator when the newest frame exceeds the defined age threshold.
- Timestamp remains legible at every camera tile size and does not obstruct controls.

Acceptance criteria:

- Correct across timezone/DST changes.
- Survives reconnects and page changes.
- Screenshot/recording policy explicitly defines whether the overlay is visual-only or burned into exported media.

### 3.2 Tapo camera control

Start with a feasibility spike against the exact installed Tapo libraries and camera models. Build only controls supported reliably by the local/device API.

Candidate scope:

- Live-view start/stop and viewer accounting.
- Pan/tilt and home position where supported.
- Privacy mode, status LED, alarm/siren, or night mode where supported and safe.
- Recording controls and retention behavior.
- Capability-driven UI so unsupported controls never render.
- Per-command authorization, timeout, retry, and activity logging.

### 3.3 Tapo motion detection

Determine whether each model/library supplies push events, polling state, or stream analysis. Prefer device-generated events; use server-side vision only as a deliberate fallback.

Event contract should include device ID, event type, source timestamp, receive timestamp, confidence/zone where available, and deduplication ID. Integrate with Activities, notifications, security actions, and automations without duplicate triggers.

### 3.4 Load-aware Android recording transfer

First prove through STAB-013 that Android clients still capture small, ordered, independently recoverable chunks and that the server reassembles them exactly. Then add capacity-aware transfer admission without coupling capture continuity to current server load.

Design:

- Derive a bounded capacity state from active Tapo/Android recordings, transcodes, upload/reassembly work, queue depth, memory, and disk pressure. Use thresholds and hysteresis; do not add high-frequency global polling.
- When capacity is constrained, return an authenticated defer result with bounded retry guidance. Do not expose unrelated server activity or topology.
- Android continues writing to its private bounded chunk spool, defers network delivery, and resumes by event or bounded backoff without busy polling, duplicate uploads, wake storms, or unbounded storage growth.
- Preserve stable recording/chunk IDs, ordering, integrity checks, idempotent acknowledgement, retry/resume, atomic finalization, and cleanup after verified completion.
- Apply fairness and age/priority rules so prolonged Tapo activity cannot starve completed Android recordings indefinitely.

Acceptance criteria:

- Normal transfer remains prompt when capacity is available.
- Many simultaneous Tapo recordings cause bounded deferral rather than failed capture, corrupt output, or uncontrolled server load.
- Multiple Android clients, prolonged deferral, disconnect, retry, duplicate/out-of-order delivery, client/server restart, low device/server storage, and recovery all produce complete playable recordings or explicit recoverable failure.
- Raspberry Pi CPU, memory, disk I/O, network use, transfer latency, and queue growth remain within measured budgets.

---

## Milestone 4 — Tapo zone import and synchronization

### 4.1 Feasibility and data mapping

Verify whether the installed local libraries expose Tapo cloud/home room assignments and whether they support changing them. Treat unsupported cloud operations as a documented limitation rather than simulating success.

Define a normalized mapping:

- Tapo account/home identifier.
- Tapo room identifier and display name.
- KotiBot zone identifier and display name.
- Device identifier mapping.
- Last import/sync time and conflict state.

### 4.2 Recommended ownership model

Use a controlled model instead of automatic unrestricted two-way sync:

- Initial setup may import Tapo rooms into KotiBot.
- After import, KotiBot is the source of truth for dashboard grouping and automations.
- If outbound Tapo room changes are supported, expose an explicit **Sync zone to Tapo** option.
- Never rename or move Tapo devices silently.
- Detect conflicts and require a choice: keep KotiBot, use Tapo, or unlink.

Acceptance criteria:

- Duplicate room names and unassigned devices are handled predictably.
- Renames do not break lighting schemes, favorites, automations, or stored device IDs.
- Failed/unsupported outbound synchronization leaves KotiBot state intact and reports the reason.

---

## Milestone 5 — Custom modes

### 5.1 Custom zone lighting modes

Create a versioned mode schema with stable IDs separate from editable labels.

Capabilities:

- Name, icon, color/accent, ordering, and favorite status.
- Per-device power, brightness, color temperature, hue, saturation, and ignore behavior.
- Preview, save, duplicate, rename, reorder, and delete.
- Use from zone controls, homepage scenes, schedules, and automations.
- Reference tracking so deletion warns about affected automations/actions.
- Migration of current built-in and custom schemes without changing their behavior.

### 5.2 Custom security modes

Build after the lighting-mode schema and editor patterns are stable.

Capabilities:

- Stable mode ID, label, icon, ordering, and visual state.
- Per-sensor armed/ignored state.
- Entry/exit delays and optional confirmation behavior.
- Per-trigger actions, notifications, recordings, and device responses.
- Explicit fallback/default mode that cannot be deleted accidentally.
- Reference tracking for automations, homepage buttons, and security actions.
- Audit log records the actor, previous mode, new mode, and result.

Security guardrails:

- Prevent an invalid custom mode from silently disabling all sensors.
- Validate every referenced device/action before activation.
- Fail closed or retain the previous valid mode when activation is incomplete.

---

## Milestone 6 — Environmental intelligence and Matter validation

### 6.1 Flesh out the environmental page

Prioritize actionable information over data density:

1. Active weather alerts and severity.
2. Current conditions and short forecast.
3. Precipitation probability/timing.
4. Wind, gusts, and direction.
5. UV index and exposure guidance.
6. Air quality and pollutant detail.
7. Sunrise, sunset, daylight, and moon information.
8. Pollen/allergen information if a reliable provider is selected.
9. Indoor/outdoor comparison and trends by zone.

Engineering requirements:

- Provider adapters, explicit attribution, cache TTLs, and request budgets.
- Last-known-good data with age labeling during provider failure.
- Unit preferences and timezone consistency.
- No external provider key is exposed to the browser.
- Mobile and wide-layout information hierarchy defined before styling.

### 6.2 Non-Tapo Matter hardware validation

Hardware-dependent. Prepare fixtures and a written matrix now; complete validation when devices are available.

Suggested matrix:

- On/off outlet.
- Dimmable light.
- Color/color-temperature light.
- Contact sensor.
- Occupancy/motion sensor.
- Temperature/humidity sensor.
- Multi-endpoint device.
- Optional lock only after authorization and fail-safe design review.

For each device record commissioning, restart persistence, subscription recovery, command latency, stale/offline behavior, UI classification, zone assignment, automations, and removal/recommissioning.

---

## Recommended implementation order

1. Complete the cross-platform support contract and platform abstraction through PLATFORM-001.6.
2. Complete SECACT-001 so existing security actions have an action-first representation before the setup wizard creates more of them.
3. Complete AUTH-001 so the setup wizard creates its administrator through the final Firebase/local-session trust contract.
4. Implement the setup wizard against the platform abstraction, action-summary, authentication, and secure-storage contracts.
5. Audit and integrate FEEDBACK-001 and LAYOUT-001 through their shared owners without noisy notifications or duplicated responsive CSS.
6. Continue camera/media, Tapo-zone, custom-mode, environment, and non-Tapo Matter work in dependency order.

## Implementation decisions still required

- Should exported Android snapshots/recordings contain a burned-in timestamp, or should the timestamp be viewer-only?
- Which Tapo camera models and controls are in the first supported hardware set?
- Should Tapo-to-KotiBot zone import be one-time, manually repeatable, or scheduled?
- If Tapo supports outbound room changes, should synchronization be per-device or per-zone?
- Which non-Tapo Matter devices will be purchased or borrowed for the validation matrix?
- Which external environmental data is most valuable after alerts, precipitation, wind, UV, and AQI?
- Should users be allowed to delete built-in lighting/security modes, or only hide and reorder them?
- Should KotiBot restore the last deliberate security arming mode after restart or require an explicit safe startup mode?
- Which Linux distributions, Windows releases, CPU architectures, and Raspberry Pi models form the initial supported platform matrix?
- After a protected KotiBot session expires or is revoked, must reauthentication always return to Firebase email, or may a deliberately provisioned device-bound local credential be used? Do not silently reintroduce a password.
- Which measured server-pressure thresholds, hysteresis, maximum deferral, and fairness policy should govern Android recording-chunk transfer on Raspberry Pi hardware?

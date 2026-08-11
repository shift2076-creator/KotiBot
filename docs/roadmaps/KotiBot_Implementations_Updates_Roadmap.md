# KotiBot Implementations and Updates Roadmap

Baseline: `38189fd18efdd1ea5dd7fccf48f6874d186226a2`
Status updated through: `457f19ac6b2e213e1058b2168534ddef3bc92b98`
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
| Initial setup | 0.8.3 | Secure resumable first-run and maintenance wizard on supported platforms | Clean installation reaches a working dashboard without manual file editing |
| Camera foundation | 0.8.4 | Timestamp Android feeds and establish Tapo control/motion support | Timestamp, control, motion, authorization, and resource tests pass |
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


## Milestone 2 — Initial setup wizard

**Implementation gate:** Do not begin the setup wizard until PLATFORM-001.1–001.6 and SECACT-001 are complete. The wizard must use platform-native configuration/service mechanisms rather than embedding Linux-only systemd assumptions.

The setup wizard depends on the secure configuration architecture. It must never write passwords back into JSON.

### Proposed flow

1. **Welcome and system check** — Python/runtime versions, writable state paths, network status, time/timezone.
2. **Administrator account** — create the first account, verify password rules, generate session secrets securely.
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
3. Implement the setup wizard against the platform abstraction and secure storage contracts.
4. Audit and integrate universal popup feedback through FEEDBACK-001 without adding noisy or duplicated notifications.
5. Continue camera, Tapo-zone, custom-mode, environment, and non-Tapo Matter work in dependency order.

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

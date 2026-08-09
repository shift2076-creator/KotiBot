# KotiBot Development Roadmap

Baseline: `38189fd18efdd1ea5dd7fccf48f6874d186226a2`
Prepared: 2026-08-08
Current product line: KotiBot 0.8

## Purpose

This roadmap orders the remaining security corrections and requested product work so that later features build on stable authentication, reliable persistence, and a secure configuration model. Dependencies are stated per task. The remaining 0.8.1 regression and acceptance tests are intentionally deferred to the near-final release gate; they do not block the 0.8.2 credentials and persistence work.

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

## Milestone overview

| Milestone | Proposed release | Primary outcome | Size | Exit gate |
|---|---:|---|---:|---|
| 1. Secure configuration | 0.8.2 | Remove personal runtime data from the Git worktree, eliminate unnecessary stale state, remove plaintext credentials, and harden persistence | L | No runtime writes enter the worktree; secret scan, migration, cold-start sync, permissions, and rollback tests pass |
| 2. Initial setup | 0.8.3 | Add a resumable, secure first-run wizard | L | Clean installation reaches a working dashboard without manual file editing |
| 3. Camera foundation | 0.8.4 | Timestamp Android feeds and establish Tapo camera event/control support | L | Timestamp, control, motion, and authorization tests pass |
| 4. Tapo zone integration | 0.8.5 | Import Tapo zones and define controlled outbound synchronization | M/L | Import, conflict, rename, and unsupported-operation behavior pass |
| 5. Custom modes | 0.8.6 | Custom zone-lighting and security modes | XL | Versioned schemas, editors, execution, migration, and automation integration pass |
| 6. Environment and Matter | 0.9.0 | Expand environment intelligence and validate non-Tapo Matter hardware | L + hardware | External-data resilience and hardware matrix pass |
| 7. Deferred testing | 0.8.1/0.9.0 gate | Run the deferred 0.8.1 regression suite against the completed architecture | M | Origin, CSP, mutation, exposure, startup, and deployment gates pass |
| 8. Release audit | 0.9.0 gate | Full functional and security audit | M | No unresolved critical/high findings |

---

## Completed and remaining 0.8.1 stabilization work

The close-button and inline-handler corrections were addressed first. The remaining dynamic-HTML review stays open, but the broader 0.8.1 regression and acceptance testing has moved to Milestone 7 so 0.8.2 can proceed now.

### 0.1 Correct the incomplete Tapo close-button conversion

Current findings in `7719f9f`:

- Light/zone close correctly uses `data-tapo-modal-close="light"`.
- Camera close is incorrectly labeled and mapped as `manager`; it must use `camera`.
- Tapo-manager close still uses CSP-blocked inline `onclick`; it must use `manager` through the delegated handler.

Acceptance criteria:

- Light/zone, device, camera, and Tapo-manager X buttons close the correct modal.
- Closing a submodal restores its parent correctly.
- No Tapo close button uses an inline event handler.

### 0.2 Repository-wide CSP compatibility sweep

Search all HTML and JavaScript-generated markup for:

- `onclick=`, `onchange=`, `oninput=`, `onsubmit=`, `onload=` and other `on*=` attributes.
- `javascript:` URLs.
- Inline scripts or styles not explicitly covered by the nonce/hash policy.
- Dynamic HTML that interpolates unescaped user, device, network, or API data.

Convert interactions to delegated listeners or `addEventListener`. Preserve strict CSP.

Acceptance criteria:

- Browser console contains no CSP violations during a complete UI walkthrough.
- A source-policy test fails if a prohibited inline event handler is introduced.

## Milestone 1 — Secure configuration and persistent state

### 1.1 Inventory every personal, secret-bearing, and runtime location

Scan without printing secret values or personal data. Report only file paths, JSON key names, environment-variable names, readers/writers, ownership, permission metadata, and classifications.

Include:

- Tracked, ignored, generated, temporary, backup, and legacy JSON/JSONL files.
- `.env*`, systemd units/drop-ins, and `/etc/kotibot/` files.
- Python, JavaScript, Android resources, test fixtures, backups, logs, and crash output.
- Git history and release archives if credentials or personal data may ever have been committed.
- Virtual-environment activation scripts, `.pth` files, package configuration, and locally modified installed packages.
- Matter controller/fabric storage, subscription storage, media, recordings, thumbnails, uploads, queues, caches, and audit files even when they are not JSON.

For every item, record:

- Owning subsystem and every direct or indirect reader/writer.
- Whether it contains household, device, activity, location, account, credential, or diagnostic data.
- Whether it is authoritative, user-created, reconstructible, cached, historical, or obsolete.
- Whether it must survive restart and what breaks if it is lost.
- Required retention, backup, restore, ownership, and proposed destination.

### 1.2 Classify persistence by ownership and necessity

Use these rules:

- **Persist:** user intent, names, zones, favorites, automations, security actions, calibration/configuration owned by the server, commissioned Matter identity, and other irreplaceable identity.
- **Rebuild:** power, brightness, color, battery, IP, reachability, live sensor readings, camera/recording status, errors, and other observable device state.
- **Cache:** weather, AQI, discovery diagnostics, thumbnails, and replaceable external results. Cache may survive restart for graceful degraded display, but it is never authoritative and must have an age/TTL.
- **Protect separately:** credentials, private keys, service accounts, enrollment material, reusable tokens, authentication state, and session secrets.
- **Retain deliberately:** activities, security audit records, notification history, and recordings only under explicit retention and rotation policies.
- **Remove:** duplicate state, obsolete migrations, diagnostics that have no supported consumer, and files described as durable queues when no restart/retry behavior exists.

### 1.3 Define OS-native storage roots and a central resolver

No subsystem may derive a runtime path from its source file or write beneath the application directory. Introduce one central path policy and pass resolved paths into subsystems.

| Purpose | Linux system service | Windows service | Windows per-user application |
|---|---|---|---|
| Durable state | `/var/lib/kotibot/` | `%PROGRAMDATA%\KotiBot\state\` | `%LOCALAPPDATA%\KotiBot\state\` |
| Replaceable cache | `/var/cache/kotibot/` | `%PROGRAMDATA%\KotiBot\cache\` | `%LOCALAPPDATA%\KotiBot\cache\` |
| Protected configuration | `/etc/kotibot/` | `%PROGRAMDATA%\KotiBot\config\` | `%APPDATA%\KotiBot\config\` |
| High-value credentials | systemd `LoadCredential=` or `/etc/kotibot/credentials.d/` | protected service credential storage | protected per-user credential storage |
| Logs/audit | systemd journal or a protected log directory | protected application log directory | `%LOCALAPPDATA%\KotiBot\logs\` |

Roaming storage is for configuration intentionally shared between a user's Windows machines. Live device state, controller identity, queues, cache, and other machine-specific data must not roam.

A non-secret development override such as `KOTIBOT_DATA_DIR` may select a test state root. It must not carry credentials, and production defaults must not depend on the launch working directory.

### 1.4 Reduce, split, or eliminate the current runtime files

| Current file or directory | Required disposition |
|---|---|
| `tapo_config.json` | Eliminate in its current form. Move credentials to protected storage and retain only necessary non-secret integration settings. |
| `tapo_lighting_state.json` | Retain custom `schemes` and `modeConfig`; do not trust persisted `activeSchemes` as current device state after restart. Recompute a match after the first Tapo pull or report no matching active scheme. |
| `tapo_device_state.json` | Eliminate persisted live power, brightness, color, battery, IP, reachability, errors, and child status. Preserve only KotiBot-owned device preferences in the durable configuration store. |
| `matter_device_state.json` | Eliminate rebuilt telemetry and reachability. Preserve only user configuration and server-owned interpretation such as aliases, zones, and contact polarity. |
| `android_home_state.json` | Eliminate live camera, door, motion, recording, and sensor state. Persist a setting only when KotiBot—not the Android client—is authoritative for it. |
| `server_state.json` | Reduce to durable registry identity and user intent. Remove live IP, battery, status, version, telemetry, pending commands, and reusable credentials/tokens. |
| `automations_state.json` | Retain as authoritative user configuration until a later store replaces it. |
| `security_actions.json` | Retain or deliberately consolidate with automations; never reconstruct user-created actions from live state. |
| `security_state.json` | Migrate authentication/security state to a protected store such as `/var/lib/kotibot/security.sqlite3`; do not silently recreate it after read failure. |
| `matter_state.json` | Retain commissioned node identity and user settings; remove `last_command`, inspection dumps, transient discovery output, and observable telemetry. |
| Matter `chip_tool_storage/` and related controller data | Retain as critical controller/fabric state outside the worktree with private permissions and tested backup/restore. |
| `environment_state.json` | Persist ZIP/provider/refresh preferences; move weather and AQI results to replaceable cache with timestamps and TTLs. |
| `activity_state.json` | Optional product history. Keep outside the worktree only when Recent Activity is enabled, with a bounded retention policy. |
| `security_audit.jsonl` | Retain outside the worktree with rotation, integrity, and retention rules. |
| `notification_queue.jsonl` | Make it a real bounded restart-safe retry queue, or replace/remove it if it only duplicates notification history. |
| `firebase-service-account.json` | Retain only as protected credential material outside the worktree; never return or log its contents. |

### 1.5 Cold-start state contract

- Initialize all live device values as unknown/offline/connecting rather than restoring the last observation.
- Perform authoritative startup synchronization for Tapo, Matter, and Android clients.
- Treat the first successful observation as a baseline; it must not fire edge-triggered automations or security actions.
- Permit commands only when the owning subsystem has established current reachability and capability state.
- Preserve a last-known observation only for explicitly labeled history or degraded display, never as authoritative control state.

### 1.6 Remove usernames and passwords from JSON

Recommended target architecture:

- Use systemd `LoadCredential=` for high-value secrets when practical.
- Otherwise use root-owned files under `/etc/kotibot/credentials.d/`, readable only by root and the KotiBot service identity (`0640` or stricter).
- Use `EnvironmentFile=` only for values that can safely be represented there; never place those files in the repository directory.
- Durable state may contain non-secret configuration and opaque credential references, but not usernames, passwords, API tokens, private keys, session tokens, reusable device enrollment secrets, or FCM tokens in general device state.
- API responses and logs must never echo secret values.

Migration sequence:

1. Add secure secret loading with backward-compatible detection.
2. Copy credentials into the new store atomically.
3. Validate access as the systemd service identity.
4. Remove secret fields from JSON and write the sanitized schema.
5. Rotate all migrated credentials.
6. Remove credentials from backups, logs, artifacts, and Git history where applicable.
7. Remove the backward-compatible plaintext reader after the migration window.
8. Verify that the running service cannot write to the Git worktree and creates no runtime artifact there during startup, normal use, tests, or shutdown.

### 1.7 Virtual-environment exposure risk

A normal `.venv` does not need application usernames or passwords; it usually contains only Python packages, scripts, metadata, and bytecode. Risk exists if credentials were:

- Written into `bin/activate`, pip configuration, `.pth` files, package source, generated modules, or test fixtures.
- Embedded as Python string literals and compiled into `.pyc` files.
- Captured in package logs, tracebacks, shell history, or build artifacts.
- Made readable to another local account through overly broad permissions.

The virtual environment is not web-accessible by default and is ignored by Git, so remote exposure is low when filesystem and web-server boundaries are correct. It must still be included in a path-only secret scan. If a real credential is discovered there, remove the source, rebuild the virtual environment from `requirements.txt`, and rotate the credential.

### 1.8 Fail visibly and recover safely

Runtime readers such as Tapo lighting state must not turn missing, corrupt, or permission-denied files into silent empty configurations.

Required behavior:

- Distinguish missing, invalid, and unreadable files.
- Log a redacted, actionable error.
- Preserve the last known-good atomic backup.
- Never overwrite a recoverable state file with an empty default following a read failure.
- Apply private file permissions after every atomic write.

### 1.9 Migration and rollback requirements

1. Stop mutation or stop the service and make a recoverable backup of every durable source file and directory.
2. Create destination roots with the intended service identity and private directory modes.
3. Copy and transform into temporary destination files; never delete the legacy copy first.
4. Validate schema, ownership, permissions, cross-subsystem path consistency, and readability as the systemd service identity.
5. Start KotiBot against the new paths and verify cold-start synchronization without false events.
6. Confirm that all durable mutations survive restart and no runtime file appears beneath the Git worktree.
7. Retain a clearly named migration backup for the defined rollback window, then remove it through an explicit cleanup step.

Milestone exit gate:

- The source/application tree remains unchanged during a complete boot, UI walkthrough, device synchronization, mutation test, and clean shutdown.
- A repository guard fails if a runtime path resolves beneath the worktree or a known runtime filename is introduced there.
- Secret scans of the worktree, runtime data, logs, backups, and responses report no forbidden values.
- Rebuilt live state is correct after the first authoritative pull and no startup baseline generates a false event.
- Durable configuration, automations, security state, Matter controller identity, activities selected for retention, and rollback backups behave as documented.
- Production credentials have been rotated after successful migration.

---

## Milestone 2 — Initial setup wizard

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

## Milestone 7 — Deferred 0.8.1 regression and acceptance testing

These tests were moved later so they exercise the completed storage and credential architecture rather than being repeated before and after 0.8.2.

### Same-origin and CSP regression coverage

Add tests for:

| Origin/Referer | `Sec-Fetch-Site` | Expected |
|---|---|---|
| Exact configured HTTPS origin | any valid browser value | Allow |
| `null` | `same-origin` | Allow |
| Absent | `same-origin` | Allow |
| `null` | `cross-site` | Block 403 |
| Absent | absent | Block 403 |
| Attacker origin | `same-origin` or `cross-site` | Block 403 |

Add a source-policy test that rejects inline event attributes and `javascript:` URLs.

### Authenticated mutation smoke test

Exercise one real state change from every subsystem:

- Login/logout and persistent session.
- Tapo power, lighting favorite, zone/device rename, camera settings, and recording.
- Scenes and security modes/actions.
- Automations and deletion cleanup.
- Matter commands.
- Notifications and audio playback.
- Android client/device settings.

For each action, check response status, UI state, persisted state after reload and restart, audit output, service logs, and the absence of runtime writes beneath the worktree.

### Unauthenticated exposure test

While logged out, verify that direct requests cannot retrieve dashboard HTML, bootstrap data, APIs, subsystem scripts, camera streams, recordings, configuration, runtime state, or credential material. Resize the login viewport repeatedly and confirm that no dashboard DOM or network activity appears beneath it.

### Startup and deployment gate

Create one repeatable pre-restart procedure that verifies:

- Virtual environment uses the expected Python interpreter.
- `requirements.txt` is installed exactly.
- Python files compile and `wsgi` imports successfully.
- Security-policy and startup tests pass.
- Allowed-origin configuration is valid.
- Runtime roots and secret stores have the correct owner/mode.
- The application tree is read-only to the service and remains free of runtime artifacts.
- Backup and rollback procedures have been exercised using non-production fixtures.

Do not restart the production service until the gate passes.

---

## Milestone 8 — Final audit and release gate

### Functional audit

- Every page at narrow, medium, and wide viewports.
- All modal/submodal transitions.
- All state-changing APIs and persistence after restart.
- Android, Tapo, Matter, environment, notifications, voice/audio, automation, and security flows.
- Cold start, dependency failure, network loss, provider outage, and partial-device failure.

### Security audit

- Authentication/session fixation, expiration, logout, and browser restart persistence.
- CSRF/origin/Fetch Metadata behavior.
- CSP, XSS, dynamic HTML escaping, and external asset policy.
- Route authorization and unauthenticated content exposure.
- Device signatures, nonce/replay behavior, timestamp windows, and enrollment throttling.
- Upload type/size/path validation and media authorization.
- Secret storage, redaction, filesystem permissions, backups, and Git history.
- Rate limits, proxy trust, audit-log integrity, and log rotation.
- Dependency vulnerabilities and production server configuration.

Release requirement: no unresolved critical or high-severity finding; medium findings must have an owner, mitigation, and scheduled milestone.

---

## Recommended first working sprint

1. Complete SEC-001: inventory every personal, secret-bearing, and runtime path without printing values or personal data.
2. Classify every file and field as durable intent, irreplaceable identity, reconstructible live state, cache, credential, retained history, or obsolete data.
3. Define the central OS-native storage resolver and remove source-relative runtime path construction.
4. Implement typed read failures, last-known-good backups, and private atomic writes before relocating data.
5. Establish the cold-start contract and stop persisting observable Tapo, Matter, and Android live state.
6. Migrate durable non-secret runtime data outside the Git worktree with validation and rollback.
7. Migrate and rotate credentials using systemd credentials or protected files, then make the application tree read-only to the service.
8. Run the deferred 0.8.1 origin, CSP, mutation, exposure, startup, and deployment tests near the release gate.

## Decisions to make before implementation

- Should exported Android snapshots/recordings contain a burned-in timestamp, or should the timestamp be viewer-only?
- Which Tapo camera models and controls are in the first supported hardware set?
- Should Tapo-to-KotiBot zone import be one-time, manually repeatable, or scheduled?
- If Tapo supports outbound room changes, should synchronization be per-device or per-zone?
- Which non-Tapo Matter devices will be purchased/borrowed for the validation matrix?
- Which external environmental data is most valuable after alerts, precipitation, wind, UV, and AQI?
- Should users be allowed to delete built-in lighting/security modes, or only hide/reorder them?
- Should KotiBot restore the last deliberate security arming mode after restart or require an explicit safe startup mode?
- What retention periods should apply to Activities, security audit records, notification history, and recordings?

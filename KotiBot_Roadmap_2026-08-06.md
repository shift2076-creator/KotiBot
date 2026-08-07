# KotiBot Development Roadmap

Baseline: `7719f9fc24a3a853c65a60b6ef55361a2cfef732`  
Prepared: 2026-08-06  
Current product line: KotiBot 0.8

## Purpose

This roadmap orders the remaining security corrections and requested product work so that later features build on stable authentication, reliable persistence, and a secure configuration model. Each milestone has an exit gate; the next milestone should not begin until the preceding gate passes.

## Working rules

1. PRE code must always come from the latest committed SHA supplied for that task.
2. Back up runtime JSON state before schema or persistence changes.
3. Security controls stay enabled while compatibility problems are corrected; CSP, authentication, and origin checks are not weakened to make a feature work.
4. Every regression fix receives an automated test when practical.
5. Every feature must define failure behavior, logging, persistence, authorization, and rollback before implementation.
6. Hardware-dependent work may be designed and fixture-tested early, but cannot be marked complete without physical-device validation.

## Milestone overview

| Milestone | Proposed release | Primary outcome | Size | Exit gate |
|---|---:|---|---:|---|
| 0. Stabilize | 0.8.1 | Repair current CSP regressions and lock in security behavior | S | All pages, mutations, and modals pass smoke tests |
| 1. Secure configuration | 0.8.2 | Remove plaintext usernames/passwords from JSON and harden persistence | M | Secret scan is clean and rotated credentials work |
| 2. Initial setup | 0.8.3 | Add a resumable, secure first-run wizard | L | Clean installation reaches a working dashboard without manual file editing |
| 3. Camera foundation | 0.8.4 | Timestamp Android feeds and establish Tapo camera event/control support | L | Timestamp, control, motion, and authorization tests pass |
| 4. Tapo zone integration | 0.8.5 | Import Tapo zones and define controlled outbound synchronization | M/L | Import, conflict, rename, and unsupported-operation behavior pass |
| 5. Custom modes | 0.8.6 | Custom zone-lighting and security modes | XL | Versioned schemas, editors, execution, migration, and automation integration pass |
| 6. Environment and Matter | 0.9.0 | Expand environment intelligence and validate non-Tapo Matter hardware | L + hardware | External-data resilience and hardware matrix pass |
| 7. Release audit | 0.9.0 gate | Full functional and security audit | M | No unresolved critical/high findings |

---

## Milestone 0 — Stabilize the secured application

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

### 0.3 Expand same-origin regression coverage

Add tests for:

| Origin/Referer | `Sec-Fetch-Site` | Expected |
|---|---|---|
| Exact configured HTTPS origin | any valid browser value | Allow |
| `null` | `same-origin` | Allow |
| Absent | `same-origin` | Allow |
| `null` | `cross-site` | Block 403 |
| Absent | absent | Block 403 |
| Attacker origin | `same-origin` or `cross-site` | Block 403 |

### 0.4 Authenticated mutation smoke test

Exercise one real state change from every subsystem:

- Login/logout and persistent session.
- Tapo power, lighting favorite, zone/device rename, camera settings, and recording.
- Scenes and security modes/actions.
- Automations and deletion cleanup.
- Matter commands.
- Notifications and audio playback.
- Android client/device settings.

For each action, check response status, UI state, persisted state after reload, audit output, and service logs.

### 0.5 Unauthenticated exposure test

While logged out, verify that direct requests cannot retrieve dashboard HTML, bootstrap data, APIs, subsystem scripts, camera streams, recordings, configuration, or runtime state. Resize the login viewport repeatedly and confirm that no dashboard DOM or network activity appears beneath it.

### 0.6 Startup and deployment gate

Create one repeatable pre-restart procedure that verifies:

- Virtual environment uses the expected Python interpreter.
- `requirements.txt` is installed exactly.
- Python files compile and `wsgi` imports successfully.
- Security-policy and startup tests pass.
- allowed-origin configuration is valid.
- Runtime files and secret stores have correct owner/mode.

Do not restart the production service until the gate passes.

---

## Milestone 1 — Secure configuration and persistent state

### 1.1 Inventory every secret-bearing location

Scan without printing secret values. Report only file paths, JSON key names, environment-variable names, and permission metadata.

Include:

- Tracked and ignored JSON files.
- `.env*`, systemd units/drop-ins, and `/etc/kotibot/` files.
- Python, JavaScript, Android resources, test fixtures, backups, logs, and crash output.
- Git history and release archives if credentials may ever have been committed.
- Virtual-environment activation scripts, `.pth` files, package configuration, and locally modified installed packages.

### 1.2 Remove usernames and passwords from JSON

Recommended target architecture:

- Use systemd `LoadCredential=` for high-value secrets when practical.
- Otherwise use root-owned files under `/etc/kotibot/`, readable only by root and the KotiBot service identity (`0640` or stricter).
- Use `EnvironmentFile=` only for values that can safely be represented there; never place those files in the repository directory.
- Runtime JSON may contain non-secret configuration and opaque credential references, but not usernames, passwords, API tokens, private keys, session tokens, or reusable device enrollment secrets.
- API responses and logs must never echo secret values.

Migration sequence:

1. Add secure secret loading with backward-compatible detection.
2. Copy credentials into the new store atomically.
3. Validate access as the systemd service identity.
4. Remove secret fields from JSON and write the sanitized schema.
5. Rotate all migrated credentials.
6. Remove credentials from backups, logs, artifacts, and Git history where applicable.
7. Remove the backward-compatible plaintext reader after the migration window.

### 1.3 Virtual-environment exposure risk

A normal `.venv` does not need application usernames or passwords; it usually contains only Python packages, scripts, metadata, and bytecode. Risk exists if credentials were:

- Written into `bin/activate`, pip configuration, `.pth` files, package source, generated modules, or test fixtures.
- Embedded as Python string literals and compiled into `.pyc` files.
- Captured in package logs, tracebacks, shell history, or build artifacts.
- Made readable to another local account through overly broad permissions.

The virtual environment is not web-accessible by default and is ignored by Git, so remote exposure is low when filesystem and web-server boundaries are correct. It must still be included in a path-only secret scan. If a real credential is discovered there, remove the source, rebuild the virtual environment from `requirements.txt`, and rotate the credential.

### 1.4 Fail visibly and recover safely

Runtime readers such as Tapo lighting state must not turn missing, corrupt, or permission-denied files into silent empty configurations.

Required behavior:

- Distinguish missing, invalid, and unreadable files.
- Log a redacted, actionable error.
- Preserve the last known-good atomic backup.
- Never overwrite a recoverable state file with an empty default following a read failure.
- Apply private file permissions after every atomic write.

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

## Milestone 7 — Final audit and release gate

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

1. Correct camera and manager modal close mappings.
2. Run the complete inline-handler/CSP sweep.
3. Add the missing same-origin and CSP source-policy tests.
4. Execute the authenticated mutation and unauthenticated exposure smoke tests.
5. Inventory secret-bearing JSON/environment/systemd locations without printing values.
6. Decide between systemd credentials and protected `/etc/kotibot/` files for each secret class.
7. Back up runtime state and begin the backward-compatible credential migration.
8. Implement the Android camera capture timestamp as the first contained feature after the stabilization gate passes.

## Decisions to make before implementation

- Should exported Android snapshots/recordings contain a burned-in timestamp, or should the timestamp be viewer-only?
- Which Tapo camera models and controls are in the first supported hardware set?
- Should Tapo-to-KotiBot zone import be one-time, manually repeatable, or scheduled?
- If Tapo supports outbound room changes, should synchronization be per-device or per-zone?
- Which non-Tapo Matter devices will be purchased/borrowed for the validation matrix?
- Which external environmental data is most valuable after alerts, precipitation, wind, UV, and AQI?
- Should users be allowed to delete built-in lighting/security modes, or only hide/reorder them?


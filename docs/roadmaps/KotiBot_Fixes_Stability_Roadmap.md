# KotiBot Fixes and Stability Roadmap

Baseline: `38189fd18efdd1ea5dd7fccf48f6874d186226a2`
Status updated through: `70d119c386017c6c39e280d6fc6aa756ee3eae52`
Prepared: 2026-08-11
Current product line: KotiBot 0.8
Companion: `KotiBot_Fixes_Stability_Checklist.md`
Implementation companion: `KotiBot_Implementations_Updates_Roadmap.md`

## Purpose

This roadmap owns defect correction, security hardening, persistence and migration safety, performance regressions, interaction reliability, compatibility failures, regression coverage, and release auditing. New capabilities and deliberate product expansions belong in the Implementations and Updates pair so completed fixes cannot be obscured by feature work.

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

Classification rule: when implementation work exposes an existing defect or regression, record and verify the correction here. Do not hide fixes inside an implementation item.

## Stability milestone overview

| Track | Target | Primary outcome | Exit gate |
|---|---:|---|---|
| Current stabilization | 0.8.x | Close known visual, interaction, client-role, camera, provisioning, CSP, and origin regressions | Every STAB item passes its complete affected browser/device matrix |
| Secure configuration and persistent state | 0.8.2 | Remove runtime and credential material from the worktree and make persistence explicit, private, recoverable, and read-only-source compatible | Migration, permissions, rollback, cold-start, and no-worktree-write gates pass |
| Deferred regression and acceptance testing | 0.9.0 gate | Exercise origin, CSP, authenticated mutation, exposure, startup, and deployment behavior against the completed architecture | TEST and OPS gates pass |
| Final audit | 0.9.0 gate | Complete functional, security, storage, dependency, and production-configuration audits | No unresolved critical/high finding; every accepted medium has an owner and mitigation |

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

### 0.3 Capture August 10–11 incidental stability fixes for the final audit

These fixes landed while Milestone 1 work continued. They are recorded here so the final functional and security audit explicitly retests them. “Implemented” records source evidence; it does not replace the open audit-verification entries in the working checklist.

| ID | Implemented result | Source evidence | Final audit verification |
|---|---|---|---|
| STAB-006 | New-device role detection now distinguishes KotiBot Control clients from KotiBot Monitor clients, merges camera/door capabilities for Monitor clients, preserves an already provisioned role, and renders the matching labels, defaults, icons, and controls. | `3a7981cacd4fb21cd886250e24eadc037fe37da3`, `e0b3ef765e9fe01edeb30e12c0d5ffdaa139625f`, and `cb93c89f062bf4d271c0011ed45380fb92922a79`; `tests/test_android_client_role_detection.py`. | Enroll one Control client and one camera/door Monitor client, restart KotiBot and both clients, and verify that classification, labels, controls, and roles do not drift. |
| STAB-007 | Android frame upload now imports and consumes Flask’s signed request-context identity, eliminating the missing-`g` failure before the camera upload handler can authorize and accept a frame. | `a823d053d48bfe9a501740147a3d6a3bb4c2b1ec`; `tests/test_android_frame_upload_context.py`. | Exercise a live signed Android camera upload before and after service/client restart; verify frames update and an unsigned or non-camera request remains rejected. |
| STAB-008 | Tapo preview handling now owns HLS-player teardown, detached-player cleanup, source reset, visibility-based sleep/wake, wake deduplication, heartbeat refresh, and actionable preview-request failure logging. | `1e67ae33fc6c820ff4a26829a55a0cd3526e17a3`. | Repeatedly open, close, navigate away from, and return to every Tapo preview; verify reconnect behavior, no duplicate/ghost player, no stale source, and bounded viewer/HLS activity. |
| STAB-009 | Provisioning now uses the shared popup modal for offline-device feedback and successful creation, shows success before the status refresh can replace the New Device UI, and holds the popup for 3 seconds before a 300 ms fade. | `8505d17ff28068b4004cf9aa190689e6b482f941` and `f89d7e9518c351efddbf21269a24031e404a0802`; `tests/test_android_client_role_detection.py`. | Verify both offline provisioning and successful provisioning on the live dashboard, including message content, 3-second hold, fade, modal cleanup, and the final provisioned client state. |
| TEST-001 | Firefox-style `Origin: null` with `Sec-Fetch-Site: same-origin` now has direct regression coverage and remains allowed by the same-origin policy. | `dc0fdf55fb9d85fd9c507baa69d6e7089f92cd21`; `tests/test_security_policy.py`. | Preserve the allowed same-origin case and complete TEST-002’s absent/cross-site/attacker matrix without weakening the existing boundary. |


### 0.4 Newly raised dashboard and touch-interaction stability work

These items were identified after the August 10–11 fixes. They remain open until their complete visual and interaction matrices are verified.

#### STAB-010 — Make the Video Recording indicator unmistakable

The inactive recording-light icon must be visibly subdued. While recording, it must become fully red with a noticeable pulsing glow.

Acceptance criteria:

- Inactive is clearly present but dull enough that it cannot be mistaken for recording.
- Active is full red and immediately distinguishable in every dashboard location that renders the indicator.
- The pulse is CSS-driven and adds no polling, repeated JavaScript work, or state queries.
- A reduced-motion presentation remains fully red and unmistakable without relying on animation.
- The indicator is verified at narrow, medium, and wide viewports and against every affected background.

#### STAB-011 — Isolate zone reordering from pull-to-refresh

Zone reordering must begin only from an explicit grab icon button placed to the left of the zone title. Pull-to-refresh must be suppressed only for the active reorder gesture, not for ordinary page scrolling.

Acceptance criteria:

- The title itself no longer acts as the drag surface.
- The grab icon button has an accessible label, visible focus behavior, and a touch target consistent with other KotiBot icon buttons.
- Touch, pointer, and mouse reordering begin only from the handle.
- Pull-to-refresh and page scrolling remain available outside an active handle-initiated reorder.
- Reorder completion, cancellation, persistence, and page refresh preserve the intended zone order.

#### STAB-012 — Keep KotiBot Monitor edit controls role-correct

The dashboard Edit Android Client view must not render Door or Camera entries for a KotiBot Monitor client. The correction must come from the canonical role/capability model rather than a page-only text or CSS hide.

Acceptance criteria:

- KotiBot Monitor clients never render Door or Camera entries in the edit view.
- Other Android client classes retain exactly the controls supported by their canonical role and advertised capabilities.
- Initial render, role changes, save, cancel, reload, reconnect, and server/client restart cannot restore the incorrect entries.
- Automated coverage exercises each Android client class and rejects future role/capability leakage.

#### STAB-013 — Preserve chunked Android recording and exact reassembly

Before final live recording verification closes PATH-001C.7, audit the Android capture, local spool, signed upload, server storage, and reassembly path. Clients must still record small bounded chunks so a network or server interruption cannot invalidate an entire recording.

Acceptance criteria:

- Chunk duration/size, recording ID, chunk sequence, source timestamps, integrity metadata, and completion semantics are explicit and bounded.
- Capture continues into a private bounded local spool while transfer is unavailable; acknowledged chunks alone are eligible for cleanup.
- Upload authentication, duplicate delivery, missing/out-of-order chunks, retry, reconnect, client/server restart, cancellation, and storage exhaustion fail predictably without corrupting the final recording.
- Reassembly is atomic and produces byte-equivalent or media-equivalent output with no duplicated, skipped, or reordered interval.
- Normal-load live Android and Tapo recordings pass from capture through playback under the protected media root with zero worktree writes.
- Load-aware transfer admission and deferral are implemented separately through MEDIA-001 after this existing contract is proven.

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

## Stability decisions still required

- What retention periods should apply to Activities, security audit records, notification history, and recordings?
- Which Linux and Windows host/version combinations become mandatory security and regression targets before cross-platform support is advertised as complete?

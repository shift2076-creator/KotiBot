# KotiBot Deferred Stability, State, Migration, and Release Updates

Source roadmap baseline: `38189fd18efdd1ea5dd7fccf48f6874d186226a2`  
Source roadmap status marker: `70d119c386017c6c39e280d6fc6aa756ee3eae52`  
Product line: KotiBot 0.8

## Purpose

This file owns **valid KotiBot work that does not need to block safe local-agent source access**.

It includes:

- Completed stability history worth retaining for regression context.
- Remaining known functional defects.
- Persistence/cold-start/retention improvements.
- Eventual OS-native durable-state migration work.
- Generalized migration/rollback fixture engineering.
- Deferred regression, deployment, functional, and security release gates.

Safe local-agent access is governed separately by `1a_KotiBot_Safe_Local_Agent_Access.md`.

---

# Stability work

## Completed stability history

- [complete] **STAB-001** Correct camera close label and map it to `camera`.
- [complete] **STAB-002** Replace Tapo-manager inline close handler and map it to `manager`.
- [complete] **STAB-003** Verify light/device/zone/camera/manager close and parent restoration.
- [complete] **STAB-004** Sweep generated/static markup for inline handlers and `javascript:` URLs.
- [complete] **STAB-005** Audit dynamic HTML escaping under strict CSP.
- [complete] **STAB-006** Audit-verify New Devices role correction: distinguish KotiBot Control from KotiBot Monitor clients, merge camera/door Monitor capabilities, preserve provisioned roles, and retain correct labels/defaults/icons/controls across enrollment and restart. Evidence: `3a7981cacd4fb21cd886250e24eadc037fe37da3`, `e0b3ef765e9fe01edeb30e12c0d5ffdaa139625f`, `cb93c89f062bf4d271c0011ed45380fb92922a79`, `tests/test_android_client_role_detection.py`.
- [complete] **STAB-007** Audit-verify Android frame-upload request-context fix; signed camera uploads succeed while unsigned/non-camera uploads remain rejected. Evidence: `a823d053d48bfe9a501740147a3d6a3bb4c2b1ec`, `tests/test_android_frame_upload_context.py`.
- [complete] **STAB-008** Audit-verify Tapo HLS preview lifecycle cleanup, visibility sleep/wake, wake deduplication, heartbeat refresh, and bounded repeated navigation. Evidence: `1e67ae33fc6c820ff4a26829a55a0cd3526e17a3`.
- [complete] **STAB-009** Audit-verify shared provisioning popup flow for offline/success outcomes, 3-second hold, 300 ms fade, cleanup, and final client state. Evidence: `8505d17ff28068b4004cf9aa190689e6b482f941`, `f89d7e9518c351efddbf21269a24031e404a0802`, `tests/test_android_client_role_detection.py`.
- [complete] **STAB-010** Recording indicator inactive/active visual state and reduced-motion behavior.
- [complete] **STAB-011** Accessible zone reorder handle isolated from pull-to-refresh.
- [complete] **STAB-012** Remove incorrect Door/Camera edit entries for KotiBot Monitor clients while preserving canonical role/capability behavior.

## Remaining known functional defects

### STAB-013 — Android chunked recording and exact reassembly

- [] **STAB-013** Audit and restore the Android recording chunk contract: clients continuously capture bounded, independently recoverable chunks with stable recording/chunk identity, ordering and integrity metadata, authenticated retry/resume, and byte/media-equivalent server reassembly.

Acceptance criteria:

- Chunk duration/size, recording ID, chunk sequence, source timestamps, integrity metadata, and completion semantics are explicit and bounded.
- Capture continues into a private bounded local spool while transfer is unavailable; only acknowledged chunks are eligible for cleanup.
- Duplicate delivery, missing/out-of-order chunks, retries, reconnects, client/server restarts, cancellation, and storage exhaustion fail predictably without corrupting the final recording.
- Reassembly is atomic and yields byte-equivalent or media-equivalent output with no duplicated, skipped, or reordered interval.
- Android and Tapo recordings pass capture-through-playback under the protected media root with zero source-tree runtime writes.
- Load-aware transfer admission/deferral remains owned by implementation item `MEDIA-001` after this existing contract is proven.

Dependency: completed `PATH-001C.7`. Size: M.

### STAB-014 — Tapo P306 child power reliability

- [] **STAB-014** Restore reliable Tapo P306 extender child power control: target the selected child by stable identity, require a confirmed live physical state transition, preserve saved child names/zones/visibility, and reject command paths that report success without changing the intended outlet.

Dependency: none. Size: S.

### STAB-015 — Matter occupancy reliability

- [] **STAB-015** Restore reliable Matter occupancy reporting and downstream behavior.

Acceptance criteria:

- Every physical occupied/unoccupied transition reaches authoritative Matter state reliably.
- Restart/subscription baseline does not emit false events.
- Retrigger/timer semantics remain correct.
- Each real transition reaches dashboard, automation, and security consumers once, without polling or duplicate firing.
- Current observed defect—physical occupancy changes detected only about half the time—is eliminated and verified physically.

Dependency: completed `PATH-001C.4`. Size: M.

---

# Deferred state and persistence refinement

These items improve correctness, data minimization, retention, portability, and eventual packaging. They are worthwhile but are not prerequisites for granting an agent access to an already-sanitized development checkout.

## STATE-004 — Cold-start live-state contract

- [] **STATE-004** Define cold start so live Tapo/Matter/Android state begins unknown; first authoritative synchronization establishes a baseline without firing false automation/security events.

Target behavior:

- Initialize live values as unknown/offline/connecting rather than restoring old observations as truth.
- Perform authoritative startup synchronization.
- Treat the first successful observation as baseline, not an edge event.
- Permit commands only after current reachability/capability has been established.
- Last-known observations may be shown only as explicitly labeled history/degraded display, never as authoritative control state.

Dependency: completed `DATA-001`. Size: M.

## STATE-005 — Stop persisting reconstructible telemetry

- [] **STATE-005** Stop persisting reconstructible Tapo, Matter, and Android live telemetry. Retain only KotiBot-owned settings and irreplaceable identity.
  - [] **STATE-005.1** Define closed durable-field allowlists and unknown-state startup behavior for Tapo, Matter, and Android.
  - [] **STATE-005.2** Remove reconstructible Tapo telemetry while preserving names, zones, references, schemes/preferences, and deliberate settings.
  - [] **STATE-005.3** Remove reconstructible Matter telemetry while preserving controller identity, node references, aliases/zones, contact interpretation, and deliberate settings.
  - [] **STATE-005.4** Remove reconstructible Android telemetry and verify clean restart synchronization without false events.

Dependency: `STATE-004`. Size: L.

### Durable/rebuild guidance

Persist user intent and irreplaceable identity. Rebuild power, brightness, color, battery, IP, reachability, live sensor values, camera/recording status, and other observable device state. Keep cache explicitly non-authoritative and time-bounded.

## STATE-006 — Cache separation and bounded retention

- [] **STATE-006** Split Environment preferences from weather/AQI cache, trim Matter diagnostics, and define bounded retention/rotation for Activities, audits, notifications, recordings, and other history.

Open product decisions:

- Activities retention period.
- Security-audit retention/rotation policy.
- Notification history/queue retention and whether the queue is a real restart-safe retry queue.
- Recording retention policy and storage-pressure behavior.
- Environment weather/AQI cache TTL and stale-display rules.

Dependency: completed `DATA-001`, `PATH-001`. Size: M.

## STATE-007 — Eventual final OS-native durable-state roots

- [] **STATE-007** Migrate durable non-secret runtime data to final service/desktop roots when packaging/deployment work warrants it. Preserve validated rollback copies.
  - [] **STATE-007.1** Resolve service/desktop platform mode and produce the exact source-to-destination migration map.
  - [] **STATE-007.2** Create private destinations and validated rollback copies without changing active service paths.
  - [] **STATE-007.3** Migrate and atomically cut over durable non-secret state; validate ownership, modes, schemas, and service startup.
  - [] **STATE-007.4** Exercise rollback, reapply migration, retain approved recovery material, and defer old-path cleanup until verification completes.

Preferred eventual roots:

| Purpose | Linux system service | Windows service | Windows per-user app |
|---|---|---|---|
| Durable state | `/var/lib/kotibot/` | `%PROGRAMDATA%\\KotiBot\\state\\` | `%LOCALAPPDATA%\\KotiBot\\state\\` |
| Replaceable cache | `/var/cache/kotibot/` | `%PROGRAMDATA%\\KotiBot\\cache\\` | `%LOCALAPPDATA%\\KotiBot\\cache\\` |
| Protected configuration | `/etc/kotibot/` | `%PROGRAMDATA%\\KotiBot\\config\\` | `%APPDATA%\\KotiBot\\config\\` |
| High-value credentials | systemd `LoadCredential=` or protected `/etc/kotibot/credentials.d/` | protected service credential storage | protected per-user credential storage |
| Logs/audit | journal or protected log directory | protected application log directory | `%LOCALAPPDATA%\\KotiBot\\logs\\` |

Machine-specific device/controller/runtime state must not roam between Windows hosts. A non-secret development override may select test state roots, but production defaults must not depend on the launch working directory.

Dependency: `STATE-004–006`, completed central path policy. Size: L.

---

# Deferred generalized migration engineering

`MIGRATE-001` is intentionally **not** a prerequisite for sanitizing the current already-migrated host or enabling local-agent source access. It remains valuable for future packaging/upgrades and supported legacy-layout migration.

- [] **MIGRATE-001** Exercise complete backup, forward migration, service-user validation, cold-start synchronization, rollback, cleanup, and re-migration using non-production fixtures.
  - [] **MIGRATE-001.1** Build sanitized fixtures covering every durable schema, credential reference, history class, cache, media path, and expected migration failure mode.
  - [] **MIGRATE-001.2** Exercise backup and forward migration from each supported legacy layout into resolved runtime roots.
  - [] **MIGRATE-001.3** Validate the migrated installation as the service identity, including permissions and intended access denials.
  - [] **MIGRATE-001.4** Validate cold-start synchronization, automations, security actions, notifications, media, and restart behavior without false events.
  - [] **MIGRATE-001.5** Exercise rollback and re-migration, then verify bounded cleanup and retained recovery material.

Dependency: activate when `STATE-007`/packaging migration becomes real release work. Size: L.

---

# Deferred regression and acceptance testing

These tests should exercise the completed architecture near the release gate rather than being repeatedly run as prerequisites for local-agent access.

## Same-origin and CSP regression matrix

| Origin/Referer | `Sec-Fetch-Site` | Expected |
|---|---|---|
| Exact configured HTTPS origin | any valid browser value | Allow |
| `null` | `same-origin` | Allow |
| Absent | `same-origin` | Allow |
| `null` | `cross-site` | Block 403 |
| Absent | absent | Block 403 |
| Attacker origin | `same-origin` or `cross-site` | Block 403 |

Preserve a source-policy test rejecting inline event attributes and `javascript:` URLs.

## Authenticated mutation smoke test

Exercise at least one real state change from every subsystem:

- Login/logout and persistent session.
- Tapo power, lighting favorite, zone/device rename, camera settings, and recording.
- Scenes and security modes/actions.
- Automations and deletion cleanup.
- Matter commands.
- Notifications and audio playback.
- Android client/device settings.

For each, check response status, UI result, persisted user intent after reload/restart where applicable, audit/log behavior, and absence of source-tree runtime writes.

## Unauthenticated exposure test

While logged out, verify direct requests cannot retrieve protected dashboard/bootstrap/API/subsystem content, camera streams, recordings, configuration, runtime state, or credential material. Confirm no protected dashboard DOM/network activity is exposed beneath the login surface.

## Startup and deployment gate

Create a repeatable pre-restart/release procedure that verifies:

- Expected Python interpreter/virtual environment.
- Required dependencies are installed as intended.
- Python compile/import/startup checks pass.
- Security-policy/startup tests pass.
- Allowed-origin configuration is valid.
- Runtime roots and secret stores have intended ownership/modes.
- Production code is separated from runtime artifacts and protected from service-side writes.
- Relevant backup/rollback procedures have been exercised with non-production fixtures where a migration is being released.

---

# Final functional and security release audit

The broad application-security review formerly overloaded into local-agent `AGENT-AUDIT-001.2` lives here instead.

## Functional audit

- Every page at narrow, medium, and wide viewports.
- Modal/submodal transitions.
- State-changing APIs and intended persistence after restart.
- Android, Tapo, Matter, Environment, notifications, voice/audio, automation, and security flows.
- Cold start, dependency failure, network loss, provider outage, and partial-device failure.

## Security audit

- Authentication/session fixation, expiration, logout, browser restart persistence, and session cleanup.
- CSRF/origin/Fetch Metadata behavior.
- CSP, XSS, dynamic HTML escaping, and external asset policy.
- Route authorization and unauthenticated content exposure.
- Device signatures, nonce/replay behavior, timestamp windows, and enrollment throttling.
- Upload type/size/path validation and media authorization.
- Credential loading/redaction, protected state, filesystem permissions, backups, recovery material, and Git-history considerations.
- Symlink/path containment and runtime-root enforcement.
- Rate limits, proxy trust, audit-log integrity, and log rotation.
- Dependency vulnerabilities and production server/runtime configuration.

Release requirement: no unresolved critical/high-severity finding; accepted medium findings require an owner, mitigation, and scheduled milestone.

---

# Deferred-work priorities

A reasonable order after local-agent access is safely enabled:

1. Fix real current functional defects: `STAB-014`, `STAB-015`, then `STAB-013` according to operational impact.
2. Implement `STATE-004` cold-start semantics before removing persisted telemetry.
3. Complete `STATE-005` data-minimization work.
4. Define `STATE-006` retention/cache policy.
5. Activate `STATE-007` and `MIGRATE-001` when packaging/cross-platform deployment actually needs final OS-native migration.
6. Run deferred acceptance testing and the final functional/security release audit near the release gate.

The beta-release checklist remains inactive until explicitly activated for beta work.

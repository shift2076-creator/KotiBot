# KotiBot Roadmap Working Checklist

Baseline: `38189fd18efdd1ea5dd7fccf48f6874d186226a2`

## 0.8.1 — Stabilization

- [c] **STAB-001** Correct camera close label and map it to `camera`. Dependency: none. Size: XS.
- [c] **STAB-002** Replace Tapo-manager inline close handler and map it to `manager`. Dependency: none. Size: XS.
- [c] **STAB-003** Verify light/device/zone/camera/manager close and parent restoration. Dependency: STAB-001/002. Size: S.
- [c] **STAB-004** Sweep all generated/static markup for inline handlers and `javascript:` URLs. Dependency: none. Size: M.
- [c] **STAB-005** Audit dynamic HTML escaping under strict CSP. Dependency: STAB-004. Size: M.

Remaining 0.8.1 regression and acceptance testing is deferred to the pre-release gate near the end of this checklist.

## 0.8.2 — Credentials and persistence

- [ ] **SEC-001** Complete SEC-001A through SEC-001D without printing values or personal data. Dependency: none. Size: L.
  - [c] **SEC-001A** Repository/source inventory: enumerate tracked files, ignored path patterns, source-relative runtime paths, JSON/JSONL key names, environment-variable names, and every source reader/writer. Record names and locations only; never values. Dependency: none. Size: M.
    - [c] **SEC-001A.1** Refresh the value-free repository scan and assign every detected runtime path literal to its owning subsystem.
    - [c] **SEC-001A.2** Reconcile actual persistence access and fields.
      - [c] **SEC-001A.2.1** Reconcile direct, indirect, library, subprocess, deployment, and operator readers/writers for every detected runtime path.
      - [c] **SEC-001A.2.2** Reduce candidate JSON/JSONL keys to fields actually persisted.
        - [c] **SEC-001A.2.2.1** Reconcile the core registry, automation/security actions, lighting state, and Tapo, Matter, and Android Home device snapshots.
        - [c] **SEC-001A.2.2.2** Reconcile activities, environment, Matter controller state, notifications, security state/audit, Tapo configuration, and credentials.
    - [c] **SEC-001A.3** Classify browser storage, carry source-relative runtime paths into PATH-001, and manually confirm that the report contains no values or personal data.
  - [c] **SEC-001B** Live-host inventory: enumerate ignored/untracked runtime files, systemd units/drop-ins, `/etc/kotibot/`, environment-file names, `.venv` activation/`.pth`/configuration paths, logs, media, backups, caches, Matter storage, and owner/group/mode/symlink metadata. Never read or print values. Dependency: SEC-001A. Size: M.
    - [c] **SEC-001B.1** Add a metadata-only collector that writes its private report outside the repository with private permissions.
    - [c] **SEC-001B.2** Run the collector as the actual service operator and manually review every discovered and missing path without copying host-specific values into Git.
    - [c] **SEC-001B.3** Reconcile unexpected paths, permission problems, symlinks, and environment-file declarations; record only sanitized path patterns and conclusions needed by SEC-001D.
  - [ ] **SEC-001C** History/release inventory: scan Git history, tags, and local release archives for sensitive path names and secret-variable/key names. Record suspect commits and artifact names without displaying file contents or values. Dependency: SEC-001A. Size: M.
  - [ ] **SEC-001D** Consolidated reviewed inventory: record each path/pattern, key names, readers/writers, permission metadata, data/sensitivity class, restart need, loss impact, retention/backup requirement, and proposed destination. Reconcile all unexpected findings and verify that no captured report contains values or personal data. Dependency: SEC-001A–C. Size: M.
- [ ] **DATA-001** Classify every current file and field as durable user intent, irreplaceable identity, reconstructible live state, replaceable cache, protected credential, retained history, or obsolete data. Dependency: SEC-001. Size: M.
- [ ] **PATH-001** Add one OS-native path resolver for code, durable state, cache, protected configuration, credentials, logs/audit, media, and temporary data. No subsystem may derive a runtime path from `__file__` or the launch directory. Dependency: DATA-001. Size: M.
  - [c] **PATH-001A** Create the external application-data root and relocate `server_state.json` and `security_actions.json`.
  - [c] **PATH-001B** Relocate `automations_state.json` and `tapo_lighting_state.json`.
  - [ ] **PATH-001C** Add and use the remaining durable-state, cache, log, media, credential, and temporary-file locations.
  - [ ] **PATH-001D** Verify that no runtime-generated data is written inside the source tree.
- [ ] **STATE-001** Replace silent state-read failure with typed missing/invalid/unreadable errors and redacted logging. Dependency: SEC-001. Size: M.
- [ ] **STATE-002** Add validated last-known-good backups and prevent empty overwrite after any failed read. Dependency: STATE-001. Size: M.
- [ ] **STATE-003** Enforce private directory/file permissions after every atomic write and validate access as the service identity. Dependency: PATH-001, STATE-001. Size: S.
- [ ] **STATE-004** Define cold start: live state begins unknown; first Tapo/Matter/Android sync establishes a baseline without firing false automation/security events. Dependency: DATA-001. Size: M.
- [ ] **STATE-005** Stop persisting reconstructible Tapo, Matter, and Android telemetry. Retain only server-owned settings and irreplaceable identity. Dependency: STATE-004. Size: L.
- [ ] **STATE-006** Split environment settings from weather/AQI cache; trim Matter diagnostics; define bounded retention for Activities, audits, notifications, recordings, and other history. Dependency: DATA-001, PATH-001. Size: M.
- [ ] **STATE-007** Migrate durable non-secret runtime data to `/var/lib/kotibot/` on Linux services, `%PROGRAMDATA%\KotiBot` on Windows services, or per-user app-data roots for desktop mode. Preserve validated rollback copies. Dependency: PATH-001, STATE-001–006. Size: L.
- [ ] **SEC-002** Classify each secret and choose systemd `LoadCredential`, protected `/etc/kotibot/credentials.d/` file, or another protected platform store. Dependency: SEC-001, DATA-001. Size: S.
- [ ] **SEC-003** Add backward-compatible secure secret loading. Dependency: SEC-002. Size: M.
- [ ] **SEC-004** Migrate Tapo credentials, Firebase service account material, authentication secrets, tokens, and other credentials out of worktree JSON atomically. Dependency: SEC-003. Size: L.
- [ ] **SEC-005** Sanitize durable schemas and all API/log output; allow only non-secret configuration and opaque credential references. Dependency: SEC-004. Size: M.
- [ ] **SEC-006** Rotate migrated credentials and remove old copies. Dependency: SEC-004/005. Size: M.
- [ ] **SEC-007** Rebuild `.venv` if any credential is found inside it. Dependency: SEC-001. Size: S; conditional.
- [ ] **PATH-002** Make the installed code/worktree read-only to the running service and permit writes only to declared runtime roots. Dependency: STATE-007, SEC-004. Size: M.
- [ ] **AGENT-001** Run local development agents under a separate non-service identity or sandbox with a clean source checkout, no inherited service environment, no access to runtime/credential roots, restricted network access, and no direct production or `main` publication authority. Verify denied reads before use. Dependency: SEC-001C, SEC-004, PATH-001D/PATH-002. Size: M.
- [ ] **GIT-001** Add a repository guard that fails when a runtime path resolves inside the worktree or a known installation/runtime filename is introduced there. Dependency: PATH-001, STATE-007. Size: S.
- [ ] **MIGRATE-001** Exercise complete backup, migration, service-user validation, cold-start synchronization, rollback, and cleanup using non-production fixtures. Dependency: STATE-007, SEC-004–006, PATH-002. Size: L.

## 0.8.3 — Initial setup wizard

- [ ] **SETUP-001** Define initialized/uninitialized state and maintenance re-entry. Dependency: SEC-003–006. Size: S.
- [ ] **SETUP-002** System/runtime preflight screen. Dependency: PATH-001, STATE-003. Size: M.
- [ ] **SETUP-003** Administrator and dashboard-origin setup. Dependency: SETUP-001. Size: M.
- [ ] **SETUP-004** Secure integration credential entry and validation. Dependency: SEC-003. Size: M.
- [ ] **SETUP-005** Tapo discovery and zone-import review. Dependency: ZONE-001/002 research. Size: L.
- [ ] **SETUP-006** Matter/Android enrollment guidance. Dependency: SETUP-001. Size: M.
- [ ] **SETUP-007** Review, atomic commit, resume, rollback, and recovery. Dependency: SETUP-002–006. Size: L.
- [ ] **SETUP-008** Clean-install end-to-end test. Dependency: SETUP-007. Size: M.

## 0.8.4 — Camera foundation

- [ ] **CAM-001** Define Android frame timestamp contract in UTC. Dependency: none. Size: S.
- [ ] **CAM-002** Send capture time from Android and retain server receive fallback. Dependency: CAM-001. Size: M.
- [ ] **CAM-003** Add responsive localized timestamp and stale-feed overlay. Dependency: CAM-002. Size: M.
- [ ] **CAM-004** Decide viewer-only versus burned-in export timestamps. Dependency: CAM-001. Status: Decision.
- [ ] **TCAM-001** Verify exact Tapo camera capabilities against installed libraries/models. Dependency: none. Size: M research.
- [ ] **TCAM-002** Capability-driven camera control API/UI. Dependency: TCAM-001. Size: L.
- [ ] **TCAM-003** Determine push, polling, or vision source for motion. Dependency: TCAM-001. Size: M research.
- [ ] **TCAM-004** Normalize/deduplicate motion events and integrate Activities. Dependency: TCAM-003. Size: L.
- [ ] **TCAM-005** Integrate motion with automations, notifications, and security actions. Dependency: TCAM-004. Size: L.

## 0.8.5 — Tapo zones

- [ ] **ZONE-001** Verify Tapo room-read capability. Dependency: none. Size: S research.
- [ ] **ZONE-002** Verify Tapo room-write capability and limitations. Dependency: ZONE-001. Size: S research.
- [ ] **ZONE-003** Define stable Tapo-home/room/device to KotiBot-zone mapping. Dependency: ZONE-001. Size: M.
- [ ] **ZONE-004** Import rooms during setup with merge/rename/defer choices. Dependency: ZONE-003, SETUP-005. Size: L.
- [ ] **ZONE-005** Implement explicit outbound sync only if supported. Dependency: ZONE-002/003. Size: L; conditional.
- [ ] **ZONE-006** Conflict handling and rollback. Dependency: ZONE-004/005. Size: M.
- [ ] **ZONE-007** Verify renames preserve schemes, favorites, automations, and IDs. Dependency: ZONE-004–006. Size: M.

## 0.8.6 — Custom modes

- [ ] **LIGHT-001** Versioned custom zone-lighting mode schema with stable IDs. Dependency: STATE-001–003. Size: M.
- [ ] **LIGHT-002** Editor: create, preview, duplicate, rename, order, favorite, delete. Dependency: LIGHT-001. Size: L.
- [ ] **LIGHT-003** Per-device preset/action model. Dependency: LIGHT-001. Size: L.
- [ ] **LIGHT-004** Homepage, zone, schedule, and automation integration. Dependency: LIGHT-002/003. Size: L.
- [ ] **LIGHT-005** Reference-aware deletion and migration tests. Dependency: LIGHT-004. Size: M.
- [ ] **SECMODE-001** Versioned custom security-mode schema. Dependency: LIGHT-001 patterns. Size: L.
- [ ] **SECMODE-002** Sensor/action/delay editor and validation. Dependency: SECMODE-001. Size: XL.
- [ ] **SECMODE-003** Safe activation, fallback mode, and audit records. Dependency: SECMODE-002. Size: L.
- [ ] **SECMODE-004** Homepage, automation, and reference-aware deletion integration. Dependency: SECMODE-003. Size: L.

## 0.9.0 — Environment and Matter validation

- [ ] **ENV-001** Rank external data: alerts, precipitation, wind, UV, AQI, daylight, pollen. Dependency: decision. Size: S.
- [ ] **ENV-002** Provider adapter/cache/attribution/failure architecture. Dependency: ENV-001. Size: M.
- [ ] **ENV-003** Responsive environmental-page information hierarchy. Dependency: ENV-001. Size: M.
- [ ] **ENV-004** Implement selected external panels and last-known-good states. Dependency: ENV-002/003. Size: L.
- [ ] **ENV-005** Indoor/outdoor zone trends. Dependency: ENV-003. Size: L.
- [ ] **MATTER-001** Select/acquire non-Tapo Matter hardware. Dependency: hardware. Status: Blocked.
- [ ] **MATTER-002** Build fixtures and written hardware test matrix. Dependency: none. Size: M.
- [ ] **MATTER-003** Validate outlet, dimmer, color light, contact, motion, environment, and multi-endpoint devices. Dependency: MATTER-001/002. Size: L.
- [ ] **MATTER-004** Validate restart, subscription recovery, latency, stale state, automation, removal, and recommissioning. Dependency: MATTER-003. Size: L.

## Deferred 0.8.1 testing — pre-release gate

- [ ] **TEST-001** Add Firefox `Origin: null` same-origin regression test. Dependency: none. Size: XS.
- [ ] **TEST-002** Add absent/cross-site/attacker origin matrix. Dependency: TEST-001. Size: S.
- [ ] **TEST-003** Add source-policy test forbidding inline event attributes and `javascript:` URLs. Dependency: STAB-004. Size: S.
- [ ] **TEST-004** Authenticated mutation/restart smoke matrix, including verification that no runtime file is written beneath the worktree. Dependency: STAB-005, MIGRATE-001. Size: L.
- [ ] **TEST-005** Unauthenticated exposure and login-resize test, including runtime data, media, and credential endpoints. Dependency: STAB-005, SEC-006. Size: M.
- [ ] **OPS-001** Repeatable dependency/import/test/origin/path/permission/backup pre-restart gate. Dependency: TEST-001–003, PATH-002, MIGRATE-001. Size: M.

## Final release gate

- [ ] **AUDIT-001** Full functional walkthrough at narrow/medium/wide viewports.
- [ ] **AUDIT-002** Authentication, session, CSRF/origin, CSP/XSS, and authorization audit.
- [ ] **AUDIT-003** Device signature, nonce/replay, enrollment, and rate-limit audit.
- [ ] **AUDIT-004** Upload, media, path, secret, permission, backup, and log audit.
- [ ] **AUDIT-005** Dependency and production-server configuration audit.
- [ ] **AUDIT-006** Resolve every critical/high finding; assign mitigation and milestone to every accepted medium finding.

## Open decisions

- [ ] Timestamp overlay: viewer-only or burned into exported media?
- [ ] First supported Tapo camera models and controls?
- [ ] Tapo zone import: one-time, manually repeatable, or scheduled?
- [ ] Outbound Tapo sync: per-device or per-zone?
- [ ] Non-Tapo Matter hardware list and budget?
- [ ] Environmental information priority after alerts and current conditions?
- [ ] Built-in modes: deletable, hideable, or reorder-only?
- [ ] Restart policy: restore the last deliberate security arming mode or require an explicit safe startup mode?
- [ ] Retention periods for Activities, security audit records, notification history, and recordings?

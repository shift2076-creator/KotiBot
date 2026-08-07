# KotiBot Roadmap Working Checklist

Baseline: `7719f9fc24a3a853c65a60b6ef55361a2cfef732`

Status values: `Not started`, `Research`, `Blocked`, `In progress`, `Review`, `Done`.

## 0.8.1 — Stabilization

- [ ] **STAB-001** Correct camera close label and map it to `camera`. Dependency: none. Size: XS.
- [ ] **STAB-002** Replace Tapo-manager inline close handler and map it to `manager`. Dependency: none. Size: XS.
- [ ] **STAB-003** Verify light/device/zone/camera/manager close and parent restoration. Dependency: STAB-001/002. Size: S.
- [ ] **STAB-004** Sweep all generated/static markup for inline handlers and `javascript:` URLs. Dependency: none. Size: M.
- [ ] **STAB-005** Audit dynamic HTML escaping under strict CSP. Dependency: STAB-004. Size: M.
- [ ] **TEST-001** Add Firefox `Origin: null` same-origin regression test. Dependency: none. Size: XS.
- [ ] **TEST-002** Add absent/cross-site/attacker origin matrix. Dependency: TEST-001. Size: S.
- [ ] **TEST-003** Add source-policy test forbidding inline event attributes. Dependency: STAB-004. Size: S.
- [ ] **TEST-004** Authenticated mutation smoke matrix. Dependency: STAB-001–005. Size: M.
- [ ] **TEST-005** Unauthenticated exposure and login-resize test. Dependency: STAB-001–005. Size: M.
- [ ] **OPS-001** Repeatable dependency/import/test/origin/permission pre-restart gate. Dependency: TEST-001–003. Size: M.

## 0.8.2 — Credentials and persistence

- [ ] **SEC-001** Inventory secret-bearing JSON, environment, systemd, code, backups, logs, history, and `.venv` paths without printing values. Dependency: 0.8.1. Size: M.
- [ ] **SEC-002** Classify each secret and choose `LoadCredential`, protected file, or environment storage. Dependency: SEC-001. Size: S.
- [ ] **SEC-003** Add backward-compatible secure secret loading. Dependency: SEC-002. Size: M.
- [ ] **SEC-004** Migrate Tapo and other usernames/passwords out of JSON atomically. Dependency: SEC-003. Size: M.
- [ ] **SEC-005** Sanitize JSON schemas and all API/log output. Dependency: SEC-004. Size: M.
- [ ] **SEC-006** Rotate migrated credentials and remove old copies. Dependency: SEC-004/005. Size: M.
- [ ] **SEC-007** Rebuild `.venv` if any credential is found inside it. Dependency: SEC-001. Size: S; conditional.
- [ ] **STATE-001** Replace silent state-read failure with typed errors and redacted logging. Dependency: 0.8.1. Size: M.
- [ ] **STATE-002** Add last-known-good backups and prevent empty overwrite after read failure. Dependency: STATE-001. Size: M.
- [ ] **STATE-003** Enforce private permissions after every atomic write. Dependency: STATE-001. Size: S.

## 0.8.3 — Initial setup wizard

- [ ] **SETUP-001** Define initialized/uninitialized state and maintenance re-entry. Dependency: SEC-003–006. Size: S.
- [ ] **SETUP-002** System/runtime preflight screen. Dependency: OPS-001. Size: M.
- [ ] **SETUP-003** Administrator and dashboard-origin setup. Dependency: SETUP-001. Size: M.
- [ ] **SETUP-004** Secure integration credential entry and validation. Dependency: SEC-003. Size: M.
- [ ] **SETUP-005** Tapo discovery and zone-import review. Dependency: ZONE-001/002 research. Size: L.
- [ ] **SETUP-006** Matter/Android enrollment guidance. Dependency: SETUP-001. Size: M.
- [ ] **SETUP-007** Review, atomic commit, resume, rollback, and recovery. Dependency: SETUP-002–006. Size: L.
- [ ] **SETUP-008** Clean-install end-to-end test. Dependency: SETUP-007. Size: M.

## 0.8.4 — Camera foundation

- [ ] **CAM-001** Define Android frame timestamp contract in UTC. Dependency: 0.8.1. Size: S.
- [ ] **CAM-002** Send capture time from Android and retain server receive fallback. Dependency: CAM-001. Size: M.
- [ ] **CAM-003** Add responsive localized timestamp and stale-feed overlay. Dependency: CAM-002. Size: M.
- [ ] **CAM-004** Decide viewer-only versus burned-in export timestamps. Dependency: CAM-001. Status: Decision.
- [ ] **TCAM-001** Verify exact Tapo camera capabilities against installed libraries/models. Dependency: 0.8.1. Size: M research.
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


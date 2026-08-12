# KotiBot Fixes and Stability Working Checklist

Status updated through: `70d119c386017c6c39e280d6fc6aa756ee3eae52`
Roadmap: `KotiBot_Fixes_Stability_Roadmap.md`
Implementation companion: `KotiBot_Implementations_Updates_Checklist.md`

This checklist owns fixes, hardening, migrations, stability, regression verification, and release auditing. New capabilities and deliberate product expansions belong in the Implementations and Updates pair. Newly raised work remains unchecked until its complete affected matrix is verified.

## Security and Stability
- [complete] **STAB-001** Correct camera close label and map it to `camera`. Dependency: none. Size: XS.
- [complete] **STAB-002** Replace Tapo-manager inline close handler and map it to `manager`. Dependency: none. Size: XS.
- [complete] **STAB-003** Verify light/device/zone/camera/manager close and parent restoration. Dependency: STAB-001/002. Size: S.
- [complete] **STAB-004** Sweep all generated/static markup for inline handlers and `javascript:` URLs. Dependency: none. Size: M.
- [complete] **STAB-005** Audit dynamic HTML escaping under strict CSP. Dependency: STAB-004. Size: M.
- [complete] **STAB-006** Audit-verify the implemented New Devices role correction: distinguish KotiBot Control from KotiBot Monitor clients, merge camera/door Monitor capabilities, preserve provisioned roles, and retain correct labels, defaults, icons, and controls across enrollment and restart. Implementation evidence: `3a7981cacd4fb21cd886250e24eadc037fe37da3`, `e0b3ef765e9fe01edeb30e12c0d5ffdaa139625f`, `cb93c89f062bf4d271c0011ed45380fb92922a79`, and `tests/test_android_client_role_detection.py`. Dependency: none. Size: S.
- [complete] **STAB-007** Audit-verify the implemented Android frame-upload context fix: signed request identity reaches the upload handler without a missing-`g` failure, live camera frames succeed, and unsigned or non-camera uploads remain rejected across restart. Implementation evidence: `a823d053d48bfe9a501740147a3d6a3bb4c2b1ec` and `tests/test_android_frame_upload_context.py`. Dependency: none. Size: S.
- [complete] **STAB-008** Audit-verify the implemented Tapo preview lifecycle correction: HLS players are torn down and detached players cleaned up, sources reset, visibility sleep/wake and wake deduplication remain bounded, heartbeat refresh works, and repeated navigation leaves no duplicate, ghost, or stale preview. Implementation evidence: `1e67ae33fc6c820ff4a26829a55a0cd3526e17a3`. Dependency: PATH-001C.6. Size: S.
- [complete] **STAB-009** Audit-verify the implemented provisioning popup flow: offline and successful outcomes use the shared popup modal, success appears before status refresh, the popup holds for 3 seconds and fades for 300 ms, and final client state remains correct. Implementation evidence: `8505d17ff28068b4004cf9aa190689e6b482f941`, `f89d7e9518c351efddbf21269a24031e404a0802`, and `tests/test_android_client_role_detection.py`. Dependency: STAB-006. Size: S.
- [complete] **STAB-010** Make every Video Recording indicator deliberately dull while inactive and full red with a noticeable CSS-driven pulsing glow while recording; provide an unmistakable non-animated active state under reduced-motion preferences and verify every dashboard location/background/viewport. Dependency: none. Size: S.
- [complete] **STAB-011** Move the zone reorder grab surface to an accessible icon button left of the zone title and suppress pull-to-refresh only during a handle-initiated reorder gesture; preserve ordinary scrolling/pull-to-refresh, cancellation, persistence, and touch/pointer/mouse behavior elsewhere. Dependency: none. Size: S.
- [complete] **STAB-012** Remove the incorrect Door and Camera entries from the dashboard Edit Android Client view for KotiBot Monitor clients; preserve the correct role/capability controls for every other Android client class and verify initial render, role changes, save/cancel, reload, and restart. Dependency: STAB-006. Size: S.
- [ ] **STAB-013** Audit and restore the Android recording chunk contract: prove that clients continuously capture bounded, independently recoverable chunks with stable recording/chunk identity, ordering and integrity metadata, authenticated retry/resume, and byte/media-equivalent server reassembly before PATH-001C.7 is completed. Load-aware transfer scheduling is owned separately by implementation item MEDIA-001. Dependency: PATH-001C.7. Size: M.
- [complete] **SEC-001** Complete SEC-001A through SEC-001D without printing values or personal data. Dependency: none. Size: L.
  - [complete] **SEC-001A** Repository/source inventory: enumerate tracked files, ignored path patterns, source-relative runtime paths, JSON/JSONL key names, environment-variable names, and every source reader/writer. Record names and locations only; never values. Dependency: none. Size: M.
    - [complete] **SEC-001A.1** Refresh the value-free repository scan and assign every detected runtime path literal to its owning subsystem.
    - [complete] **SEC-001A.2** Reconcile actual persistence access and fields.
      - [complete] **SEC-001A.2.1** Reconcile direct, indirect, library, subprocess, deployment, and operator readers/writers for every detected runtime path.
      - [complete] **SEC-001A.2.2** Reduce candidate JSON/JSONL keys to fields actually persisted.
        - [complete] **SEC-001A.2.2.1** Reconcile the core registry, automation/security actions, lighting state, and Tapo, Matter, and Android Home device snapshots.
        - [complete] **SEC-001A.2.2.2** Reconcile activities, environment, Matter controller state, notifications, security state/audit, Tapo configuration, and credentials.
    - [complete] **SEC-001A.3** Classify browser storage, carry source-relative runtime paths into PATH-001, and manually confirm that the report contains no values or personal data.
  - [complete] **SEC-001B** Live-host inventory: enumerate ignored/untracked runtime files, systemd units/drop-ins, `/etc/kotibot/`, environment-file names, `.venv` activation/`.pth`/configuration paths, logs, media, backups, caches, Matter storage, and owner/group/mode/symlink metadata. Never read or print values. Dependency: SEC-001A. Size: M.
    - [complete] **SEC-001B.1** Add a metadata-only collector that writes its private report outside the repository with private permissions.
    - [complete] **SEC-001B.2** Run the collector as the actual service operator and manually review every discovered and missing path without copying host-specific values into Git.
    - [complete] **SEC-001B.3** Reconcile unexpected paths, permission problems, symlinks, and environment-file declarations; record only sanitized path patterns and conclusions needed by SEC-001D.
  - [complete] **SEC-001C** History/release inventory: scan Git history, tags, and local release archives for sensitive path names and secret-variable/key names. Record suspect commits and artifact names without displaying file contents or values. Dependency: SEC-001A. Size: M.
    - [complete] **SEC-001C.1** Add a value-free scanner for every commit reachable from local references, commit-target tag snapshots, annotated tag key names, and supported local release archives. Write its private report outside the repository with private permissions.
    - [complete] **SEC-001C.2** Run the scanner on the actual repository and every local release/archive root; manually review every finding, skipped item, unreadable item, and unsupported archive without copying values into Git.
    - [complete] **SEC-001C.3** Record only sanitized suspect commit IDs, tag names, artifact/member names, sensitive path classes, secret-variable/key names, and dispositions needed by SEC-001D; confirm the private report and committed review contain no values or personal data.
  - [complete] **SEC-001D** Consolidated reviewed inventory: record each path/pattern, key names, readers/writers, permission metadata, data/sensitivity class, restart need, loss impact, retention/backup requirement, and proposed destination. Reconcile all unexpected findings and verify that no captured report contains values or personal data. Dependency: SEC-001A–C. Size: M.
- [complete] **DATA-001** Classify every current file and field as durable user intent, irreplaceable identity, reconstructible live state, replaceable cache, protected credential, retained history, or obsolete data. Dependency: SEC-001. Size: M.
  - [complete] **DATA-001A** Define the classification rules and classify every field in `server_state.json`, `security_actions.json`, `automations_state.json`, and `tapo_lighting_state.json`.
  - [complete] **DATA-001B** Classify Activities, Android Home, Environment, Matter and Tapo state/configuration files, including dynamic and pass-through fields.
    - [complete] **DATA-001B.1** Classify Activity history/deduplication state and Android Home persisted state, including dynamic, compatibility, and currently unread fields. Dependency: DATA-001A. Size: S.
    - [complete] **DATA-001B.2** Classify Environment and Matter settings/device state, including dynamic and pass-through fields but excluding protected Matter controller identity. Dependency: DATA-001B.1. Size: M.
    - [complete] **DATA-001B.3** Classify Tapo configuration/device state, including children, dynamic fields, and pass-through behavior; reconcile and close DATA-001B. Dependency: DATA-001B.2. Size: M.
  - [complete] **DATA-001C** Classify authentication/security state, Firebase and environment credentials, Matter controller identity, protected configuration, and virtual-environment findings.
  - [complete] **DATA-001D** Classify audit/notification history, recordings, browser storage, archives, caches, temporary data, and obsolete residue; reconcile every SEC-001D entry and close DATA-001.

## Read-only source execution order

1. **Completed — PATH-001C.4:** Matter controller/fabric and subscription storage now use protected explicit paths with validated rollback material and live controller, command, subscription, restart, and permission verification.
2. **Next — PATH-001C.7, PATH-001C.9, and PATH-001C.10:** externalize recordings, served APKs, and runtime staging. `tools/`, `tests/`, `temp/`, and `docs/` remain repository content for now, but the running service may not write into them.
3. Complete **SEC-002**, then **SEC-003**, then **PATH-001C.8**, then **SEC-004**: establish secure loaders and move credential/authentication material without exposing values or losing rollback capability.
4. Complete **PATH-001D**, then **GIT-001**: prove normal service operation creates or modifies nothing beneath the worktree and prevent regressions.
5. Complete **STATE-003–007**, then **PATH-002**: finish permission, schema/retention, and service-root migration work before enforcing a read-only installed source tree.
6. Complete **SEC-005/006** and **MIGRATE-001**, then **PATH-003** and **GIT-002**: sanitize and rotate credentials, exercise recovery, retire verified legacy runtime copies, and reduce `.gitignore` to developer/operator residue.

- [ ] **PATH-001** Add one OS-native path resolver for code, durable state, cache, protected configuration, credentials, logs/audit, media, and temporary data. No subsystem may derive a runtime path from `__file__` or the launch directory. Dependency: DATA-001. Size: M.
  - [complete] **PATH-001A** Create the external application-data root and relocate `server_state.json` and `security_actions.json`.
  - [complete] **PATH-001B** Relocate `automations_state.json` and `tapo_lighting_state.json`.
  - [ ] **PATH-001C** Add and use the remaining durable-state, cache, log, media, credential, and temporary-file locations.
    - [complete] **PATH-001C.1** Route Activity history to `<log-root>/activity/activity_state.json`, preserve existing history, enforce private permissions, and verify production use. Dependency: SEC-001D. Size: S.
    - [complete] **PATH-001C.2** Route the security audit and its rotation file to `<log-root>/security/security_audit.jsonl{,.1}`, preserve existing history, enforce private permissions, and verify production writes. Dependency: SEC-001D. Size: S.
    - [complete] **PATH-001C.3** Route remaining durable non-secret Tapo, Android Home, Environment, Matter settings/device, and related state files through the resolver. Dependency: DATA-001B. Size: M.
    - [complete] **PATH-001C.4** Route Matter controller/fabric identity and subscription storage through explicit protected paths without risking irreplaceable identity. Treat both current storage trees as protected and irreplaceable until subscription-only cache content is proven safely separable. Dependency: DATA-001C. Size: M.
      - [complete] **PATH-001C.4.1** Inventory every controller, worker, subprocess, repair, and operator consumer of `chip_tool_storage` and `chip_tool_subscription_storage`; define explicit protected runtime paths without reading or exposing stored values.
      - [complete] **PATH-001C.4.2** Copy `chip_tool_storage`, `chip_tool_storage.bad-*`, and `.chip_tool_storage.repair-*` into the protected Matter root with private ownership/modes and validated rollback copies; never initialize replacement identity after a path or read failure.
      - [complete] **PATH-001C.4.3** Copy `chip_tool_subscription_storage` as protected data and wire every subscription worker to its explicit runtime path. Do not classify or relocate any portion as cache until tests prove it contains no controller/fabric identity.
      - [complete] **PATH-001C.4.4** Cut over atomically and verify controller/fabric identity, commissioned nodes, commands, subscriptions, restart recovery, repair behavior, and rollback before authorizing legacy-tree cleanup.
    - [complete] **PATH-001C.5** Route notification history/queue data and any remaining application-owned logs or audit reports through explicit log/history paths. Dependency: DATA-001D. Size: M.
    - [complete] **PATH-001C.6** Add and use explicit replaceable-cache and transient-runtime paths, including Tapo camera HLS data and the future Environment weather/AQI cache. Dependency: DATA-001B/D. Size: M.
      - [complete] **PATH-001C.6.1** Define validated external cache and transient-runtime roots, plus private Tapo HLS and future Environment cache destinations. Do not change an active consumer in this checkpoint.
      - [complete] **PATH-001C.6.2** Route Tapo HLS generation, serving, and pruning through the explicit transient-runtime path without changing dashboard URLs or deleting legacy residue.
      - [complete] **PATH-001C.6.3** Verify private permissions, stream creation/serving/pruning, restart behavior, and zero cache writes beneath the worktree. Keep the Environment cache consumer deferred to STATE-006 and leave cleanup to PATH-001D/003.
    - [implemented - final live recording verification remains] **PATH-001C.7** Route Android and Tapo recordings through the protected media root while preserving existing media and leaving retention policy to STATE-006. Dependency: DATA-001D. Size: M.
    - [complete] **PATH-001C.8** Add and use protected configuration, credential, and authentication-state paths only after their storage choices and compatibility loaders are defined. Dependency: DATA-001C, SEC-002/003. Size: M.
    - [complete] **PATH-001C.9** Add a package/deployment root for served Android APKs so deployment artifacts are not managed as source-tree runtime data. Dependency: DATA-001D. Size: S.
    - [complete] **PATH-001C.10** Add and use the temporary-data root for runtime staging, transcodes, and Samba/operator temporary files; preserve nothing classified as replaceable temporary data. Dependency: DATA-001D. Size: M.
  - [ ] **PATH-001D** Verify recursively that normal service operation creates or modifies no file or directory inside the source tree. Dependency: PATH-001C, SEC-004. Size: L.
    - [ ] **PATH-001D.1** Perform a recursive static inventory of every production writer, library/subprocess path, atomic-write companion, backup, rotation, and fallback; reject runtime derivation from `__file__`, the launch directory, or any worktree path.
    - [ ] **PATH-001D.2** Snapshot or trace startup, restart, device synchronization, dashboard mutations, automations, security actions, notifications, recordings, APK serving/deployment, Matter subscriptions/repair, caches, logs, and temporary staging as the service identity.
    - [ ] **PATH-001D.3** Eliminate every remaining worktree write and add regression coverage that fails whenever a resolved runtime destination or observed runtime mutation falls beneath the worktree.
    - [ ] **PATH-001D.4** Verify that `tools/`, `tests/`, `temp/`, and `docs/` may remain as developer/operator repository content but are never production service write targets.
- [complete] **STATE-001** Replace silent state-read failure with typed missing/invalid/unreadable errors and redacted logging. Dependency: SEC-001. Size: M.
- [complete] **STATE-002** Add validated last-known-good backups and prevent empty overwrite after any failed read. Dependency: STATE-001. Size: M.
- [ ] **STATE-003** Enforce private directory/file permissions after every atomic write and validate access as the service identity. Dependency: PATH-001, STATE-001. Size: S.
- [ ] **STATE-004** Define cold start: live state begins unknown; first Tapo/Matter/Android sync establishes a baseline without firing false automation/security events. Dependency: DATA-001. Size: M.
- [ ] **STATE-005** Stop persisting reconstructible Tapo, Matter, and Android telemetry. Retain only server-owned settings and irreplaceable identity. Dependency: STATE-004. Size: L.
  - [ ] **STATE-005.1** Define closed durable-field allowlists and unknown-state startup behavior for Tapo, Matter, and Android.
  - [ ] **STATE-005.2** Remove reconstructible Tapo telemetry from persistence while preserving names, zones, references, and deliberate settings.
  - [ ] **STATE-005.3** Remove reconstructible Matter telemetry from persistence while preserving controller identity, node references, and deliberate settings.
  - [ ] **STATE-005.4** Remove reconstructible Android telemetry from persistence and verify clean restart synchronization without false events.
- [ ] **STATE-006** Split environment settings from weather/AQI cache; trim Matter diagnostics; define bounded retention for Activities, audits, notifications, recordings, and other history. Dependency: DATA-001, PATH-001. Size: M.
- [ ] **STATE-007** Migrate durable non-secret runtime data to `/var/lib/kotibot/` on Linux services, `%PROGRAMDATA%\KotiBot` on Windows services, or per-user app-data roots for desktop mode. Preserve validated rollback copies. Dependency: PATH-001, STATE-001–006. Size: L.
  - [ ] **STATE-007.1** Resolve the service/desktop platform mode and produce the exact source-to-destination migration map.
  - [ ] **STATE-007.2** Create private destinations and validated rollback copies without changing the active service paths.
  - [ ] **STATE-007.3** Migrate and atomically cut over durable non-secret state, then validate ownership, modes, schemas, and service startup.
  - [ ] **STATE-007.4** Exercise rollback, reapply the migration, retain the approved recovery copy, and defer old-path cleanup until verification completes.
- [complete] **SEC-002** Classify each secret and choose systemd `LoadCredential`, protected `/etc/kotibot/credentials.d/` file, or another protected platform store. Dependency: SEC-001, DATA-001. Size: S.
- [complete] **SEC-003** Add backward-compatible secure secret loading. Dependency: SEC-002. Size: M.
- [complete] **SEC-004** Migrate Tapo credentials, Firebase service account material, authentication secrets, tokens, and other credentials out of worktree JSON atomically. Dependency: SEC-003, PATH-001C.8. Size: L.
  - [complete] **SEC-004.1** Migrate Tapo account and camera credentials through the approved protected loader while retaining a tested rollback path.
  - [complete] **SEC-004.2** Migrate Firebase service-account material and verify notification authentication without exposing credential contents.
  - [complete] **SEC-004.3** Migrate dashboard/device authentication secrets, enrollment material, sessions, and persisted tokens from source-tree state.
  - [complete] **SEC-004.4** Migrate remaining credential-bearing environment entries and composite connection values into their approved stores.
  - [complete] **SEC-004.5** Verify backward compatibility, protected permissions, restart behavior, and absence of credential values from ordinary state; leave rotation and old-copy removal to SEC-006.
- [ ] **SEC-005** Sanitize durable schemas and all API/log output; allow only non-secret configuration and opaque credential references. Dependency: SEC-004. Size: M.
- [ ] **SEC-006** Rotate migrated credentials and remove old copies. Dependency: SEC-004/005. Size: M.
- [ ] **SEC-007** Rebuild `.venv` if any credential is found inside it. Dependency: SEC-001. Size: S; conditional.
- [ ] **GIT-001** Add a repository guard that fails when a runtime path resolves inside the worktree or a known installation/runtime filename is newly introduced there. Dependency: PATH-001D, SEC-004. Size: S.
- [ ] **PATH-002** Make the entire installed code/worktree read-only to the running service and permit writes only to declared runtime roots. Dependency: STATE-007, SEC-004, PATH-001D, GIT-001. Size: M.
- [ ] **MIGRATE-001** Exercise complete backup, migration, service-user validation, cold-start synchronization, rollback, and cleanup using non-production fixtures. Dependency: STATE-007, SEC-004–006, PATH-002. Size: L.
  - [ ] **MIGRATE-001.1** Build sanitized fixtures covering every durable schema, credential reference, history class, cache, media path, and expected failure mode.
  - [ ] **MIGRATE-001.2** Exercise backup and forward migration from each supported legacy layout into the resolved runtime roots.
  - [ ] **MIGRATE-001.3** Validate the migrated installation as the service identity, including permissions and denied source/credential access.
  - [ ] **MIGRATE-001.4** Validate cold-start synchronization, automations, security actions, notifications, media, and restart behavior without false events.
  - [ ] **MIGRATE-001.5** Exercise rollback and re-migration, then verify bounded cleanup and retained recovery material.
- [ ] **PATH-003** Remove verified legacy runtime JSON/JSONL, logs, Matter storage, APKs, recordings, caches, staging files, backups, and obsolete residue from the source tree only after external recovery copies and rollback have been validated. Preserve `tools/`, `tests/`, `temp/`, `docs/`, and deliberate source assets. Dependency: MIGRATE-001, SEC-006. Size: M.
- [ ] **GIT-002** Reduce `.gitignore` to genuine developer/operator residue and defense-in-depth local-secret exclusions. Remove broad runtime exclusions for JSON/JSONL, logs, APKs, recordings, media, caches, and staging; retain only necessary entries such as `.venv/`, tool/editor caches, local secret files, and `/temp/`. Dependency: PATH-003, GIT-001. Size: S.
- [ ] **AGENT-001** Run local development agents under a separate non-service identity or sandbox with a clean source checkout, no inherited service environment, no access to runtime/credential roots, restricted network access, and no direct production or `main` publication authority. Verify denied reads before use. Dependency: SEC-001C, SEC-006, PATH-002/003, GIT-002. Size: M.

## 0.9 Beta release gate
- [complete] **TEST-001** Add Firefox `Origin: null` same-origin regression test. Implementation evidence: `dc0fdf55fb9d85fd9c507baa69d6e7089f92cd21` and `tests/test_security_policy.py`. Dependency: none. Size: XS.
- [complete] **TEST-002** Add absent/cross-site/attacker origin matrix. Dependency: TEST-001. Size: S.
- [complete] **TEST-003** Add source-policy test forbidding inline event attributes and `javascript:` URLs. Dependency: STAB-004. Size: S.
- [ ] **TEST-004** Authenticated mutation/restart smoke matrix, including verification that no runtime file is written beneath the worktree. Dependency: STAB-005, MIGRATE-001. Size: L.
  - [ ] **TEST-004.1** Build authenticated fixtures and helpers for every dashboard and device mutation class.
  - [ ] **TEST-004.2** Exercise core state, automation, security, device, environment, notification, media, and setup mutations.
  - [ ] **TEST-004.3** Restart between mutation groups and verify durable intent, cold-start baselines, sessions, and bounded history.
  - [ ] **TEST-004.4** Snapshot the worktree before and after each matrix run and fail on any runtime-generated path or content change.
  - [ ] **TEST-004.5** Verify cleanup, repeatability, failure diagnostics, and execution as the production service identity.
- [ ] **TEST-005** Unauthenticated exposure and login-resize test, including runtime data, media, and credential endpoints. Dependency: STAB-005, SEC-006. Size: M.
- [ ] **OPS-001** Repeatable dependency/import/test/origin/path/permission/backup pre-restart gate. Dependency: TEST-001–003, PATH-002, MIGRATE-001. Size: M.
- [ ] **AUDIT-001** Full functional walkthrough at narrow/medium/wide viewports. Size: L.
  - [ ] **AUDIT-001.1** Define the page, modal, wizard, device-state, role, and narrow/medium/wide viewport matrix.
  - [ ] **AUDIT-001.2** Walk through core navigation, Home, Controls, Monitor, Sensors, Environment, Activities, and Settings.
  - [ ] **AUDIT-001.3** Walk through device management, automations, scenes, security actions, camera controls, Matter, Tapo, and setup flows.
  - [ ] **AUDIT-001.4** Record reproducible failures, verify fixes, and rerun the complete affected matrix without accepting visual or functional regressions.
- [ ] **AUDIT-002** Authentication, session, CSRF/origin, CSP/XSS, and authorization audit. Size: L.
  - [ ] **AUDIT-002.1** Audit login, logout, cookie flags, expiry, renewal, invalidation, concurrent sessions, and restart behavior.
  - [ ] **AUDIT-002.2** Audit same-origin, opaque/absent Origin, Fetch Metadata, trusted proxy, host, and cross-site mutation handling.
  - [ ] **AUDIT-002.3** Audit CSP, dynamic HTML escaping, URL handling, upload names, rendered metadata, and DOM injection surfaces.
  - [ ] **AUDIT-002.4** Audit public, dashboard, enrollment, and signed-device authorization across every route and method.
  - [ ] **AUDIT-002.5** Record findings with severity and evidence, verify fixes, and rerun the complete authentication/security matrix.
- [ ] **AUDIT-003** Device signature, nonce/replay, enrollment, and rate-limit audit. Size: L.
  - [ ] **AUDIT-003.1** Audit canonical signing, body hashes, timestamps, device/key identity binding, and comparison behavior.
  - [ ] **AUDIT-003.2** Audit nonce storage, replay rejection, clock skew, restart behavior, concurrency, and bounded-memory handling.
  - [ ] **AUDIT-003.3** Audit enrollment creation, expiry, single use, rotation, revocation, removal, and identity mismatch handling.
  - [ ] **AUDIT-003.4** Audit login/enrollment/device rate limits, proxy-aware client identity, retry responses, and denial-of-service boundaries.
  - [ ] **AUDIT-003.5** Record findings with severity and evidence, verify fixes, and rerun the complete signed-device matrix.
- [ ] **AUDIT-004** Upload, media, path, secret, permission, backup, and log audit. Size: L.
  - [ ] **AUDIT-004.1** Audit upload authentication, size/part limits, signatures, extensions, filenames, content validation, and partial files.
  - [ ] **AUDIT-004.2** Audit media authorization, path containment, MIME/range behavior, recording access, retention, and deletion.
  - [ ] **AUDIT-004.3** Audit every runtime root, temporary/atomic file, symlink boundary, owner/group/mode, and source-tree write prohibition.
  - [ ] **AUDIT-004.4** Audit credential loading, API/state/browser exposure, environment handling, redaction, notifications, and audit/application logs.
  - [ ] **AUDIT-004.5** Audit backup encryption/protection, validation, restore, retention, cleanup, and loss of irreplaceable identity.
  - [ ] **AUDIT-004.6** Record findings with severity and evidence, verify fixes, and rerun the complete storage/media/security matrix.
- [ ] **AUDIT-005** Dependency and production-server configuration audit. Size: M.
  - [ ] **AUDIT-005.1** Audit pinned direct/transitive dependencies, known vulnerabilities, licenses, update policy, and reproducible installation.
  - [ ] **AUDIT-005.2** Audit Waitress, Flask, systemd, reverse-proxy, TLS, trusted-host/proxy, request-limit, and security-header configuration.
  - [ ] **AUDIT-005.3** Audit service identity, environment declarations, restart limits, resource limits, startup ordering, health checks, and operational logging.
  - [ ] **AUDIT-005.4** Record findings with severity and evidence, verify fixes, and rerun the dependency/production configuration checks.
- [ ] **AUDIT-006** Resolve every critical/high finding; assign mitigation and milestone to every accepted medium finding. Size: L.
  - [ ] **AUDIT-006.1** Consolidate and deduplicate findings from AUDIT-001–005 with owners, severity, evidence, and affected releases.
  - [ ] **AUDIT-006.2** Resolve every critical finding and rerun its complete affected audit matrix.
  - [ ] **AUDIT-006.3** Resolve every high finding and rerun its complete affected audit matrix.
  - [ ] **AUDIT-006.4** Assign an explicit mitigation, owner, milestone, and acceptance rationale to every remaining medium finding.
  - [ ] **AUDIT-006.5** Run the complete release audit suite and close the gate only when no unowned or unresolved critical/high finding remains.

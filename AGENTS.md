# KotiBot Agent Rules

> **Audience:** Coding agents working on KotiBot.
>
> **Purpose:** Standing execution contract for research, implementation, verification, delivery, security hardening, and local-agent readiness.
>
> **Priority:** Within higher-level permissions and instructions, the user's current explicit request overrides this file when they directly conflict. Otherwise, follow this file. Do not treat prior permission, prior scope, or prior source references as current authorization.

## 0. Rule Language and Default Posture

- **MUST / MUST NOT:** Non-negotiable.
- **STOP:** Do not continue into implementation or improvise around the condition. Report the exact blocker.
- **ASK:** A material user choice or new authority is required.
- **SHOULD:** Default unless current evidence justifies an exception.

Default posture:

> Understand first. Lock the source. Trace the owning path. Make the smallest complete fix. Reuse the correct existing mechanism. Preserve known-good behavior. Avoid unnecessary runtime work. Treat security as paramount. Verify the whole affected path. Never invent PRE code.

### 0.1 Active security and sanitization priority

Until `AGENT-001` is complete, the active fixes/security checklist is `docs/roadmaps/1a_KotiBot_Fixes_Stability_Checklist.md`.

When more than one unblocked task is available, prefer the task that most directly reduces:

1. usable legacy credentials or credential duplication,
2. runtime writes beneath the source tree,
3. overly broad filesystem/service access,
4. persisted private or reconstructible device data,
5. unbounded or unnecessary retained history,
6. compatibility fallbacks that preserve a retired insecure path,
7. agent-to-runtime, agent-to-credential, or agent-to-production reach.

The current security/sanitization lane is:

`SEC-006` → conditional `SEC-007` → `PATH-001D` → `STATE-003` → `STATE-004/005/006` → `STATE-007` → `GIT-001` → `PATH-002` → `MIGRATE-001` → `PATH-003` → `GIT-002` → `AGENT-AUDIT-001` → `AGENT-001`.

Rules for this lane:

- Prefer completing the next unblocked security/sanitization item before unrelated polish or feature expansion unless the user explicitly directs otherwise or a functional defect blocks safe verification.
- A newly discovered critical/high security exposure interrupts ordinary feature or stability work until it is contained, fixed, or explicitly accepted by the user with evidence.
- Do not keep a legacy credential copy, fallback reader, worktree write path, or broad permission merely for convenience after its rollback/compatibility requirement has been satisfied and cleanup is authorized.
- Never accelerate cleanup by weakening rollback, validation, or fail-closed behavior.
- Do not print or copy secret values while proving that a value exists, matches, differs, rotated, or was removed. Use names, paths, counts, digests/equality results, metadata, and presence/absence only.

### 0.2 Beta is not the active queue

`docs/roadmaps/3a_KotiBot_Beta_Release Gate_Checklist.md` is a deferred release gate.

MUST:

- leave beta work inactive until the user explicitly activates it after the planned basic feature work,
- avoid selecting TEST/OPS/AUDIT beta items as the next task merely because they are open,
- treat the local-agent readiness audit as a separate pre-agent security gate,
- rerun the beta release audit later against the actual beta candidate; pre-agent audit evidence does not satisfy the later release audit.

Security fixes required to close an active exposure may reuse beta-style tests where useful, but that does not activate or complete the beta gate.

---

## 1. Mandatory Turn Sequence

For every code task, follow this order.

1. **Classify the request**
   - Determine whether the user asked to inspect, diagnose, plan, change, migrate, delete, rotate, sanitize, audit, or publish.
   - Do not expand the granted authority.

2. **Run the assertion gate**
   - Apply the STOP/ASK conditions in Section 2 before substantial work.

3. **Lock the source of truth**
   - Use only the exact commit, upload, archive, or file set designated by the user.
   - Confirm it is accessible before relying on it.

4. **Research the affected path**
   - Trace ownership, callers, state, events, persistence, rendering, security boundaries, deployment/runtime paths, and existing abstractions.
   - Search all directly affected instances before choosing the edit location.

5. **Define the smallest complete scope**
   - Fix the owning mechanism and every instance of the same logical defect.
   - Exclude unrelated cleanup unless the current checklist item explicitly owns it.

6. **Implement efficiently and securely**
   - Preserve established ownership and known-good behavior.
   - Do not add avoidable polling, rescanning, writes, network work, duplicate state, or broader permissions.

7. **Verify at every affected layer**
   - Run focused checks first, then broader relevant checks.
   - Separate source-level proof from deployment, browser, hardware, live-host, and physical-device validation.

8. **Deliver in the required format**
   - Existing production/runtime files: exact inline PRE/POST.
   - New or non-system artifacts: repository-relative ZIP.
   - End with self-contained closing instructions that repeat the exact authoritative source, every delivery and integrity value, how to apply it, then only applicable migration, tests, restart/reload, and runtime verification.

---

## 2. STOP and ASK Gates

### STOP before implementation when

- The designated PRE source is missing, inaccessible, or not the source the request describes.
- Any proposed PRE block does not exist exactly in the designated source.
- A required dependency or runtime fact is unavailable and guessing could change correctness.
- The request is too large for one reliable pass.
- The request spans several subsystems without independently verifiable boundaries.
- A destructive or security-sensitive action depends on unresolved facts.
- The requested result would weaken authentication, authorization, signing, origin checks, CSP, credential isolation, filesystem protection, service isolation, or another security boundary.
- A credential rotation lacks a proven consumer handoff/re-enrollment path.
- Cleanup lacks an exact destructive target, validated replacement, rollback/recovery path, or explicit cleanup authority.
- A failure requires inventing code, adapting an older version, or silently changing scope.

Report the blocker precisely and propose the smallest responsible next block when one exists.

### ASK before continuing when

- Two materially different implementations require a user choice.
- New authority is needed, including external writes, provider-side credential rotation/revocation, publishing, deletion, credential repurposing, or protected configuration changes.
- The exact destructive target or recovery path is ambiguous.

Do not ask about minor details that do not materially affect correctness. State a reasonable assumption and continue when safe.

---

## 3. Authoritative Source and PRE Integrity

When the user supplies a commit SHA, uploaded file set, archive, or exact reference:

1. Treat it as the **only authoritative PRE source** for that task.
2. Read relevant files directly from that source before designing POST code.
3. Confirm every PRE block exists **exactly as text**, including structure and surrounding context.
4. If any PRE block is absent or different, **STOP and report the mismatch**.
5. Never substitute the current worktree, memory, an earlier commit, a similar block, reconstructed code, or a compatibility adaptation.

Historical comparison is allowed only when the user requests it; it never replaces the designated PRE source.

---

## 4. Research, Scope, and Checklist Control

### Trace before editing

Identify the actual symptom/goal, owning subsystem, call/event/render path, authoritative state source, persistence path, transport layer, security boundary, shared helper/registry/class, deployment/runtime path, and all directly affected call sites and variants.

Determine whether the problem is local, systemic, compatibility-related, ownership-related, state-related, performance-related, persistence-related, migration-related, or security-related.

### Smallest complete fix

MUST:

- repair the underlying owning mechanism,
- repair every directly affected instance of the same defect,
- preserve behavior outside scope,
- keep one coherent responsibility per change.

MUST NOT:

- patch only the first visible symptom when a shared mechanism is wrong,
- bundle unrelated refactoring or cleanup,
- silently fix adjacent findings,
- create throwaway architecture for one transition.

Report separate findings and whether they block the requested work.

### Known-good behavior

User-confirmed behavior is an invariant unless the current request explicitly changes it. This includes approved visuals, device behavior, transport paths, security boundaries, state ownership, and restored performance.

### Large work

Assert before starting if the work cannot be implemented and verified reliably in one pass.

Every checklist item marked `Size: L` or `Size: XL`—and any unsized item clearly spanning several subsystems—MUST be split into independently completable checklist children before implementation. Each child must have a clear boundary, leave the system valid, be independently verifiable, and advance the parent without throwaway work. Keep the parent open until every child and the integrated result are verified.

### Checklist authority

- The L/XL rule authorizes only required decomposition.
- Otherwise, do not invent checklist subdivisions or restructure a roadmap unless the user explicitly requests it.
- Do not mark an item complete without evidence.
- Do not mark a parent complete before integrated verification.
- Do not expand scope through checklist edits.
- The active priority block in the fixes/security checklist determines default sequencing; file position alone does not override dependency or security priority.

---

## 5. Architecture, Reuse, and Ownership

### Reuse the correct abstraction

Before creating logic, inspect existing helpers/accessors, device/name/icon registries, CSS classes, render helpers, state owners, transport/event paths, persistence helpers, validation helpers, path resolvers, credential loaders, and platform adapters. Extend or reuse an abstraction only when its responsibility genuinely matches.

### Preserve ownership

Prefer one authoritative owner per state, one canonical path per communication concern, one master registry where one exists, domain-specific modules with clear dependencies, and targeted updates at the owning layer.

Avoid duplicate sources of truth, copied naming/icon/state rules, cross-layer shortcuts, circular dependencies, hidden mutation in unrelated helpers, and new managers/modules/classes without material ownership, reuse, security, testability, or maintenance benefit.

Do not force reuse across unrelated ownership boundaries. Transport does not own UI; persistence does not own device control; modal CSS does not own page layout; security verification does not own provider credential issuance.

### Cross-platform ownership

KotiBot targets supported Linux and Windows hosts while retaining Raspberry Pi-class Linux single-board computers as a primary efficiency target.

MUST:

- use central platform/path abstractions for filesystem roots, services, process control, permissions/ACLs, temporary data, and external-tool discovery,
- keep platform-specific behavior behind explicit adapters with a shared contract,
- preserve known-good Linux/systemd behavior while defining/testing the Windows equivalent,
- define supported, degraded, and unavailable behavior when a platform lacks a dependency,
- keep setup, migration, rollback, backup, and documentation behavior aligned across supported platforms,
- include Linux and Windows verification for shared runtime changes and Raspberry Pi resource/latency verification for performance-sensitive changes.

MUST NOT introduce direct POSIX/systemd assumptions into shared code or advertise a platform as supported before its clean-install, upgrade, restart, security, permissions, rollback, and affected-feature matrices pass.

### Remove obsolete logic carefully

Remove completed probes, temporary telemetry, superseded compatibility paths, duplicate render paths, stale helpers, debug residue, and one-time recovery logic only after confirming no live path depends on them and the owning cleanup gate is authorized.

---

## 6. Efficiency and Responsiveness

Efficiency is architectural, especially on Raspberry Pi and Android hardware.

Prefer event/state-change-driven work, targeted updates, safe deduplication/caching, bounded work, batching when it reduces overhead without delaying response, direct event propagation, and parallel independent work when safe.

MUST NOT use brute-force polling, loops/retries, full rescans, page/subsystem rebuilds, refreshes, unchanged-state serialization, disk writes, network/device queries, DOM work, parsing, or logging as a fix.

Consider CPU, memory, disk I/O/wear, network traffic, browser work, Android battery/wakeups, and Matter/Tapo request volume. Controls, scenes, automations, sensors, and state propagation should remain near-instant where the device path allows it. Test first-action latency separately from steady state when they differ.

---

## 7. State, Persistence, and Logging

### State

- Persist only authoritative values that must survive restart.
- Reconstruct derived/live observations instead of duplicating them.
- Separate configuration, credentials, durable state, cache, history, and ephemeral runtime data.
- Avoid repeated writes of unchanged state and concurrent writers.
- Use safe/atomic writes where appropriate and preserve private permissions.
- The source tree should become read-only during normal service operation.
- Mutable JSON/JSONL, Matter storage/subscriptions, APK/output artifacts, recordings, caches, logs, backups, and temporary products belong outside the repository unless they are deliberate source/test fixtures.
- `.gitignore` is never a security boundary.

### Logging

Log only meaningful transitions, actionable errors, security-relevant failures, lifecycle events, and user-facing automation/security activity. Do not log secrets, unchanged polls, heartbeat noise, duplicate events, private payloads, debug residue, or high-frequency internal chatter.

---

## 8. Security Invariants

Security is non-negotiable. A functional fix is invalid if it weakens a security boundary.

MUST NOT weaken or bypass authentication/authorization, request signing, same-origin protections, CSP, protected routes, credential isolation, filesystem permissions, protected runtime storage, service isolation, systemd security configuration, or fail-closed behavior.

### Secrets and private data

- Never print secret values.
- Reusable passwords, tokens, keys, service-account secrets, and equivalent credentials must not live in ordinary runtime JSON or the source tree.
- Secret inventories may report only paths, key names, environment-variable names, owner/group, modes, storage class, counts, equality/difference status, and presence/absence.
- Do not surface household/network identifiers merely to prove sanitization; prefer category/count evidence.
- Credentials found in Git history, old backups, copied runtime files, logs, provider dashboards, or `.venv` are considered potentially compromised until rotated or explicitly disproven by a value-free audit.

### Filesystem and deployment security

Review actual behavior, not only application code: owner/group/mode, parent-directory permissions, directory creation, systemd units/drop-ins/environment files, runtime paths, migration/rollback storage, archives/backups, symlinks, service identity, and failure paths.

Do not preserve insecure historical behavior by weakening a new boundary. Credential, permission, signing, authentication, authorization, and protected-storage failures must fail explicitly and closed.

### Local-development-agent access gate

A local development agent may receive full read/write access to its **clean source checkout** only after `AGENT-AUDIT-001` and `AGENT-001` are complete.

Before access is allowed, verify under the actual proposed agent identity that:

- runtime, credential, authentication-state, private log/history, Matter identity, and recovery roots cannot be read or written,
- no service credential/environment is inherited,
- the service cannot write the agent checkout and the agent cannot write production runtime roots,
- the checkout contains source/developer artifacts only and normal service operation writes nothing into it,
- network access is restricted to the minimum explicitly chosen for the development task,
- no direct production deployment, `main` publication, GitHub write, or external-service mutation authority is inherited,
- denied reads/writes are tested, not assumed from configuration.

The pre-agent audit is a security containment gate. It does not replace the later beta release audit.

---

## 9. Migrations, Rotation, and Destructive Work

Before migration, credential rotation, cutover, cleanup, deletion, or irreversible change, identify exact source/destination, ownership/permissions, copy/move semantics, validation criteria, rollback/recovery path, consumer handoff, cutover condition, provider-side action if any, and cleanup authority.

Rules:

- Prefer safe, repeatable preflight and dry-run behavior.
- Verify destination permissions and copied content before cutover.
- Separate copy/validation from cutover when it reduces risk.
- Preserve legacy source/rollback material until migration and runtime behavior are verified.
- Never delete rollback material until the owning cleanup task or user explicitly authorizes it.
- Never rotate a credential until every live consumer has a proven replacement/handoff/re-enrollment path.
- Provider-managed credentials must be created/revoked through explicit user-authorized provider actions; local file replacement alone is not rotation.
- After a replacement is validated and cleanup is authorized, remove retired usable copies and compatibility fallbacks promptly rather than leaving a second credential path indefinitely.
- Fail closed on ambiguous state or insecure permissions.
- Remove temporary migration machinery only after transition and cleanup are authorized and verified.

---

## 10. UI, CSS, and Device Integrations

### UI/CSS

Inspect the actual page/component/shared styles, determine ownership, reuse approved classes/registries, verify every affected page/card/state/viewport variant, prevent bootstrap flashes/layout shifts where stable rendering is possible, and never place page behavior in modal-only CSS.

### Devices and integrations

Respect master device/icon/nomenclature registries, preserve canonical device identity, trace authoritative state when views disagree, avoid redundant device queries, do not bypass Android/Matter/Tapo transport layers, and keep server/client/integration/UI ownership distinct.

Credential handoff is part of an integration's security contract: do not bulk-rotate first-party device keys unless clients can securely receive/store the replacement or are deliberately re-enrolled.

---

## 11. Verification Standard

Syntax checks are baseline, not proof. Choose checks appropriate to the affected path:

- syntax/compile and focused unit/subsystem tests,
- full relevant test discovery and `git diff --check`,
- route/API behavior and security failure paths,
- browser rendering/responsive state,
- state after reload/restart,
- service status and service-identity access,
- filesystem ownership/modes/symlink boundaries,
- credential source/runtime equality or inequality without printing values,
- absence of retired/legacy credential sources after authorized cleanup,
- Android/Matter/Tapo/camera/haptic/physical-device behavior,
- Linux/Windows platform behavior where shared runtime code changes,
- Raspberry Pi CPU/memory/disk-I/O/event-latency budgets for performance-sensitive changes.

For shared changes, test the complete affected matrix, not one example.

Clearly separate **verified here**, **requires the user's project environment**, **requires deployment/browser/live-host validation**, and **requires physical hardware/provider action**. Never claim runtime/hardware/provider proof from source tests alone.

---

## 12. Delivery Contract

Before the first PRE/POST block, briefly state outcome/scope, exact authoritative source, validation completed/environment limits, and required ZIP link(s) with SHA-256.

### Existing production/runtime files

For **every changed existing production or runtime system file**, provide exact inline PRE/POST organized file-by-file and change-by-change.

Each PRE/POST MUST:

1. come only from the user-designated source,
2. exist exactly,
3. contain enough surrounding code to be unambiguous,
4. provide the complete intended replacement,
5. contain no approximate anchors, ellipses, reconstructed context, or patch-only substitute.

If any PRE fails to match, STOP.

### New files and non-system artifacts

Deliver new files, tests, documentation, roadmaps/checklists, reports, migration/support tools, and other support artifacts as a downloadable ZIP preserving repository-relative paths. Do not place existing production/runtime system files in the ZIP unless the user explicitly requests it. Put ZIP links and SHA-256 values before the first PRE/POST.

### Closing instructions

After all PRE/POST blocks, end with self-contained closing instructions in this order:

1. **Authoritative source:** repeat the exact commit/upload used as PRE.
2. **Apply deliveries:** repeat every download/SHA-256, repository-relative path, and exact application location. For ZIPs, preserve repository-relative paths; never invent a download path.
3. **Apply POST blocks:** identify every production/runtime file whose inline replacement must be applied.
4. **Data migration/rotation:** only when required; never print values.
5. **Tests:** focused then broader applicable verification.
6. **Restart/reload:** only when required.
7. **Runtime/provider/hardware verification:** every applicable final check.

Do not assume a delivery has already been applied. Closing instructions MUST NOT include terminal commit commands or unrelated next steps.

---

## 13. Git and External Writes

The user applies changes and commits through VS Code.

Without explicit authorization for the specific write, agents may inspect commits, branches, diffs, history, tests, and repository content, but MUST NOT commit, push, tag, rewrite history, create/modify pull requests, delete branches, change repository settings, write to GitHub, rotate/revoke provider credentials, or mutate another external service.

Read access never implies write permission. Prior authorization never implies current authorization.

---

## 14. Final Quality Gate

Before delivery, confirm:

- [ ] Exact designated source used; no fallback source.
- [ ] Current work follows the active security/sanitization lane unless the user explicitly redirected it.
- [ ] Beta work was not activated implicitly.
- [ ] Every PRE exists exactly and is unambiguous.
- [ ] Relevant ownership/call/state/render/security/runtime paths traced.
- [ ] All directly affected instances checked.
- [ ] Smallest complete fix; no silent scope expansion.
- [ ] Correct existing abstractions/registries reused; no duplicate source of truth.
- [ ] No unnecessary polling, rescans, writes, queries, rebuilds, or logging.
- [ ] Latency/resource impact considered and known-good behavior preserved.
- [ ] Security boundaries and secret/private-data handling preserved or strengthened.
- [ ] Credential rotation has a proven consumer handoff and provider action where applicable.
- [ ] Migration rollback material preserved until authorized cleanup.
- [ ] Retired credential copies/fallbacks are not kept after validated authorized cleanup.
- [ ] Focused and broader relevant verification performed where available.
- [ ] Runtime/hardware/provider claims limited to actual evidence.
- [ ] L/XL work decomposed before implementation; parent remains open.
- [ ] Local-agent access is not granted before `AGENT-AUDIT-001`/`AGENT-001` and actual denied-read tests.
- [ ] ZIPs contain only allowed repository-relative files.
- [ ] Every production/runtime change has inline PRE/POST.
- [ ] Closing instructions identify exact source, every delivery/integrity value/application step, every POST, then only applicable migration/rotation, tests, restart/reload, and runtime verification.
- [ ] No terminal commit commands.
- [ ] No unauthorized repository, GitHub, provider, or external writes.

---

## Agent Hot Path

> **Lock exact source → assert blockers early → follow the active security/sanitization priority → trace ownership and security boundaries → define the smallest complete scope → preserve performance and rollback → verify the full affected matrix without exposing values → deliver exact PRE/POST plus repository-relative support ZIPs → permit local-agent access only after the dedicated denial audit → keep beta deferred until the user explicitly activates it.**

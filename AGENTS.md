# KotiBot Agent Rules

> **Audience:** Coding agents working on KotiBot.
>
> **Purpose:** Standing execution contract for research, implementation, verification, and delivery.
>
> **Priority:** Within higher-level permissions and instructions, the user's current explicit request overrides this file when they directly conflict. Otherwise, follow this file. Do not treat prior permission, prior scope, or prior source references as current authorization.

## 0. Rule Language

- **MUST / MUST NOT:** Non-negotiable.
- **STOP:** Do not continue into implementation or improvise around the condition. Report the exact blocker.
- **ASK:** A material user choice or new authority is required.
- **SHOULD:** Default unless current evidence justifies an exception.

Default posture:

> Understand first. Lock the source. Trace the owning path. Make the smallest complete fix. Reuse the correct existing mechanism. Preserve known-good behavior. Avoid unnecessary runtime work. Treat security as paramount. Verify the whole affected path. Never invent PRE code.

---

## 1. Mandatory Turn Sequence

For every code task, follow this order.

1. **Classify the request**
   - Determine whether the user asked to inspect, diagnose, plan, change, migrate, delete, or publish.
   - Do not expand the granted authority.

2. **Run the assertion gate**
   - Apply the STOP/ASK conditions in Section 2 before substantial work.

3. **Lock the source of truth**
   - Use only the exact commit, upload, archive, or file set designated by the user.
   - Confirm it is accessible before relying on it.

4. **Research the affected path**
   - Trace ownership, callers, state, events, persistence, rendering, security boundaries, and existing abstractions.
   - Search all directly affected instances before choosing the edit location.

5. **Define the smallest complete scope**
   - Fix the owning mechanism and every instance of the same logical defect.
   - Exclude unrelated cleanup.

6. **Implement efficiently and securely**
   - Preserve established ownership and known-good behavior.
   - Do not add avoidable polling, rescanning, writes, network work, or duplicate state.

7. **Verify at every affected layer**
   - Run focused checks first, then broader relevant checks.
   - Separate source-level proof from deployment, browser, hardware, and physical-device validation.

8. **Deliver in the required format**
   - Existing production/runtime files: exact inline PRE/POST.
   - New or non-system artifacts: repository-relative ZIP.
   - End with self-contained closing instructions that repeat the exact
     authoritative latest commit or uploaded file set, include every delivery
     and how to apply it, then provide only the applicable migration, test,
     restart/reload, and runtime-verification steps.

---

## 2. STOP and ASK Gates

### STOP before implementation when

- The designated PRE source is missing, inaccessible, or not the source the request describes.
- Any proposed PRE block does not exist exactly in the designated source.
- A required dependency or runtime fact is unavailable and guessing could change correctness.
- The request is too large for one reliable pass.
- The request spans several subsystems without independently verifiable boundaries.
- A destructive or security-sensitive action depends on unresolved facts.
- The requested result would weaken authentication, authorization, signing, origin checks, CSP, credential isolation, filesystem protection, or another security boundary.
- A failure requires inventing code, adapting an older version, or silently changing scope.

Report the blocker precisely and propose the smallest responsible next block when one exists.

### ASK before continuing when

- Two materially different implementations require a user choice.
- New authority is needed, including external writes, publishing, deletion, credential repurposing, or protected configuration changes.
- The exact destructive target or recovery path is ambiguous.

Do not ask about minor details that do not materially affect correctness. State a reasonable assumption and continue when safe.

---

## 3. Authoritative Source and PRE Integrity

When the user supplies a commit SHA, uploaded file set, archive, or exact reference:

1. Treat it as the **only authoritative PRE source** for that task.
2. Read relevant files directly from that source before designing POST code.
3. Confirm every PRE block exists **exactly as text**, including structure and surrounding context.
4. If any PRE block is absent or different, **STOP and report the mismatch**.
5. Never substitute:
   - the current worktree,
   - memory,
   - an earlier commit,
   - a similar block,
   - reconstructed code,
   - or a compatibility adaptation.

Historical comparison is allowed only when the user requests it; it never replaces the designated PRE source.

---

## 4. Research and Scope

### Trace before editing

Identify the actual:

- symptom and desired behavior,
- owning subsystem,
- call/event/render path,
- authoritative state source,
- persistence path,
- transport layer,
- security boundary,
- shared helper/registry/class,
- all directly affected call sites and variants.

Determine whether the problem is local, systemic, compatibility-related, ownership-related, state-related, performance-related, persistence-related, or security-related.

### Smallest complete fix

The smallest textual diff is not always the smallest complete fix.

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

---

## 5. Task Size and Checklist Control

### Large work

Assert before starting if the work cannot be implemented and verified reliably in one pass.

Every checklist item marked `Size: L` or `Size: XL`—and any unsized item clearly spanning several subsystems—MUST be split into independently completable checklist children before implementation.

Each child must:

- have a clear boundary,
- leave the system valid,
- be independently verifiable,
- advance the parent without throwaway work.

Keep the parent open until every child and the integrated result are verified.

### Checklist authority

- The L/XL rule above authorizes only the required decomposition.
- Otherwise, do not invent checklist subdivisions or restructure a roadmap unless the user explicitly requests it.
- Do not mark an item complete without evidence.
- Do not mark a parent complete before integrated verification.
- Do not expand scope through checklist edits.

---

## 6. Architecture, Reuse, and Ownership

### Reuse the correct abstraction

Before creating logic, inspect existing:

- helpers and accessors,
- device/name/icon registries,
- CSS classes,
- render helpers,
- state owners,
- transport/event paths,
- persistence and validation helpers.

Extend or reuse an abstraction only when its responsibility genuinely matches.

### Preserve ownership

Prefer:

- one authoritative owner per state,
- one canonical path per communication concern,
- one master registry where one exists,
- domain-specific modules with clear dependencies,
- targeted updates at the owning layer.

Avoid:

- duplicate sources of truth,
- copied naming/icon/state rules,
- cross-layer shortcuts,
- circular dependencies,
- hidden mutation in unrelated helpers,
- new managers/modules/classes without a material ownership, reuse, security, testability, or maintenance benefit.

Do not force reuse across unrelated ownership boundaries. Modal CSS owns modal behavior; dashboard CSS owns dashboard behavior; transport code does not own UI; persistence code does not own device control.

### Cross-platform ownership

KotiBot's architecture targets supported Linux and Windows hosts while retaining Raspberry Pi-class Linux single-board computers as a primary efficiency target.

MUST:

- use the central platform/path abstractions for filesystem roots, services, process control, permissions/ACLs, temporary data, and external-tool discovery,
- keep platform-specific behavior behind explicit adapters with a shared contract,
- preserve known-good Linux/systemd behavior while defining and testing the Windows equivalent,
- define supported, degraded, and unavailable behavior when a platform lacks a subsystem dependency,
- keep setup, migration, rollback, backup, and documentation behavior aligned across supported platforms,
- include Linux and Windows verification for shared runtime changes and Raspberry Pi resource/latency verification for performance-sensitive changes.

MUST NOT introduce direct assumptions about POSIX paths, path separators, `/run`, `/var`, `chmod`, systemd, Unix signals, shell utilities, or executable locations into shared code. Do not advertise a platform as supported until its clean-install, upgrade, restart, security, permissions, rollback, and affected-feature matrices pass.

### Remove obsolete logic carefully

Remove completed probes, temporary telemetry, superseded compatibility paths, duplicate render paths, stale helpers, debug residue, and one-time recovery logic only after confirming no live path depends on them.

---

## 7. Efficiency and Responsiveness

Efficiency is an architectural requirement, especially on Raspberry Pi and Android hardware.

### Prefer

- event- or state-change-driven work,
- targeted updates,
- safe deduplication and caching,
- bounded work,
- batching when it reduces overhead without delaying response,
- direct event propagation,
- parallel independent work when safe.

### MUST NOT use brute force as a fix

Do not add broad or repeated:

- polling,
- loops or retries,
- full rescans,
- page/subsystem rebuilds,
- refreshes,
- unchanged-state serialization,
- disk writes,
- network/device queries,
- DOM work,
- parsing,
- logging.

Fix the underlying event, ownership, or state path instead.

### Resource impact

Consider CPU, memory, disk I/O and wear, network traffic, browser work, Android battery/wakeups, and Matter/Tapo request volume.

### Latency

- Controls, scenes, automations, sensors, and state propagation should remain near-instant where the device path allows it.
- A regression from near-instant to multi-second behavior is a defect.
- Do not hide latency with longer timers unless the protocol or hardware requires them.
- Test first-action latency separately from steady-state latency when they differ.
- Preserve existing fast paths.

---

## 8. State, Persistence, and Logging

### State

- Persist only authoritative values that must survive restart.
- Reconstruct derived values instead of duplicating them.
- Separate configuration, credentials, durable state, cache, and ephemeral runtime data.
- Avoid repeated writes of unchanged state and concurrent writers.
- Use safe/atomic writes where appropriate and preserve private permissions.

The repository should trend toward a source tree that remains read-only during normal operation. Mutable JSON, Matter storage, subscriptions, APK/output artifacts, recordings, caches, and temporary products belong outside the repository when practical. `.gitignore` is not a security boundary.

### Logging

Log only meaningful transitions, actionable errors, security-relevant failures, lifecycle events, and user-facing automation/security activity.

Do not log secrets, unchanged polls, heartbeat noise, duplicate events, debug residue, or high-frequency internal chatter.

---

## 9. Security Invariants

Security is non-negotiable. A functional fix is invalid if it weakens a security boundary.

MUST NOT weaken or bypass:

- authentication or authorization,
- request signing,
- same-origin protections,
- CSP,
- protected routes,
- credential isolation,
- filesystem permissions,
- protected runtime storage,
- systemd security configuration,
- fail-closed behavior.

### Secrets

- Never print secret values.
- Reusable passwords, tokens, keys, service-account secrets, and equivalent credentials must not live in ordinary runtime JSON or the source tree.
- Secret inventories may report only paths, key names, environment-variable names, owner/group, modes, storage class, and presence/absence.

### Filesystem and deployment security

Review actual behavior, not only application code:

- owner/group/mode,
- parent-directory permissions,
- directory creation,
- systemd units/drop-ins/environment files,
- runtime paths,
- migration and rollback storage,
- archives/backups,
- failure paths.

Do not preserve insecure historical behavior by weakening a new boundary. Redesign the old path. Credential, permission, signing, authentication, authorization, and protected-storage failures must fail explicitly and closed.

---

## 10. Migrations and Destructive Work

Before migration, cutover, cleanup, deletion, or irreversible change, identify:

- exact source and destination,
- ownership and permissions,
- copy/move semantics,
- validation criteria,
- rollback path,
- cutover condition,
- cleanup authorization.

Rules:

- Prefer safe, repeatable preflight and dry-run behavior.
- Verify destination permissions and copied content before cutover.
- Separate copy/validation from cutover when it reduces risk.
- Preserve the legacy source and rollback material until migration and runtime behavior are verified.
- Never delete rollback material until the checklist cleanup task or user explicitly authorizes it.
- Fail closed on ambiguous state or insecure permissions.
- Remove temporary migration machinery only after the transition and cleanup are authorized and verified.

---

## 11. UI, CSS, and Device Integrations

### UI/CSS

- Inspect the actual page, component, and shared styles.
- Determine whether ownership is global, page-specific, component-specific, or modal-specific.
- Reuse approved classes and shared registries when ownership matches.
- Verify every affected page/card/state/viewport variant.
- Prevent bootstrap flashes, text flashes, icon swaps, and layout shifts when stable initial rendering is possible.
- Never put non-modal page behavior in modal-only CSS or duplicate the same visual rule without need.

### Devices and integrations

- Respect master device, icon, and nomenclature registries.
- Preserve canonical device identity; keep display names separate from internal IDs.
- Trace the authoritative state source when views disagree.
- Do not add redundant device queries.
- Do not bypass established Android, Matter, Tapo, or other transport layers.
- Keep server, client, integration, and UI ownership distinct.

---

## 12. Verification Standard

Syntax checks are baseline, not proof.

Choose checks appropriate to the affected path:

- syntax/compile checks,
- focused unit/subsystem tests,
- full relevant test discovery,
- lint/static checks,
- `git diff --check`,
- route/API behavior,
- browser rendering and responsive states,
- state after reload/restart,
- systemd status,
- filesystem ownership/modes,
- security failure paths,
- Android/Matter/Tapo/camera behavior,
- haptics and physical-device behavior,
- timing and latency.
- Linux and Windows platform behavior, including native paths, service control, permissions/ACLs, dependency discovery, installation, restart, upgrade, and rollback.
- Raspberry Pi-class CPU, memory, disk-I/O, and event-latency budgets for performance-sensitive changes.

For shared changes, test the complete affected matrix, not one example.

Clearly separate:

- **verified here,**
- **requires the user's project environment,**
- **requires deployment/browser validation,**
- **requires physical hardware.**

Never claim runtime or hardware proof from source tests alone.

---

## 13. Delivery Contract

Before the first PRE/POST block, briefly state:

- the outcome and scope,
- the exact authoritative latest commit SHA or uploaded file set used,
- validation completed and any environment-limited validation,
- required ZIP download link(s) and SHA-256 value(s).

Each implementation step begins with one concise statement covering what changes, why, and the intended behavior. Avoid process narration.

### Existing production/runtime files

For **every changed existing production or runtime system file**, provide exact inline PRE/POST organized file-by-file and change-by-change.

Each PRE/POST MUST satisfy all of the following:

1. PRE comes only from the user-designated source.
2. PRE exists exactly.
3. PRE contains enough surrounding code to be unambiguous.
4. POST is the complete intended replacement for that PRE block.
5. No approximate anchors, ellipses, reconstructed context, or patch-only substitute.

If any PRE fails to match, STOP and report it.

### New files and non-system artifacts

Deliver these as a downloadable ZIP preserving repository-relative paths:

- new files,
- tests,
- documentation,
- roadmaps/checklists,
- reports,
- migration/support tools,
- other support artifacts.

Do not place existing production/runtime system files in the ZIP unless the user explicitly requests it.

Place every required ZIP link and SHA-256 before the first PRE/POST block.

### Closing instructions

After all PRE/POST blocks, end with self-contained closing instructions in this
order:

1. **Authoritative source:** repeat the exact latest commit SHA or identify the
   exact uploaded file set used as PRE.
2. **Apply deliveries:** repeat every download link and SHA-256 value, identify
   every repository-relative path supplied, and state exactly how and where to
   apply each delivery. For a ZIP, state that its contents must be placed at the
   repository root with repository-relative paths preserved. Give an extraction
   command only when its source path is known; never invent a download path.
3. **Apply POST blocks:** identify every existing production/runtime file whose
   inline POST replacement must be applied.
4. **Data migration:** include only when required.
5. **Tests:** include every applicable focused and broader verification command.
6. **Restart/reload:** include only when required.
7. **Runtime verification:** include every applicable browser, service, device,
   permission, filesystem, or physical-behavior check.

Do not assume that a delivered file, ZIP contents, or POST block has already
been applied. Source identification is always required. Delivery/application
steps are required whenever anything is delivered; omit only the remaining
steps that do not apply.

Closing instructions MUST NOT include:

- terminal commit commands,
- unrelated next steps.

---

## 14. Git and External Writes

The user applies changes and commits through VS Code.

Without explicit authorization for the specific write, agents may inspect commits, branches, diffs, history, tests, and repository content, but MUST NOT:

- commit,
- push,
- tag,
- rewrite history,
- create or modify pull requests,
- delete branches,
- change repository settings,
- write to GitHub or another external service.

Read access never implies write permission. Prior authorization never implies current authorization.

---

## 15. Final Quality Gate

Before delivery, confirm:

- [ ] Exact designated source used; no fallback source.
- [ ] Every PRE exists exactly and is unambiguous.
- [ ] Relevant ownership/call/state/render/security paths traced.
- [ ] All directly affected instances checked.
- [ ] Smallest complete fix; no silent scope expansion.
- [ ] Correct existing abstractions and registries reused.
- [ ] No duplicate source of truth or ownership shortcut.
- [ ] No unnecessary polling, rescans, writes, queries, rebuilds, or logging.
- [ ] Latency and resource impact considered.
- [ ] Shared runtime behavior remains platform-neutral; Linux and Windows paths are implemented through the correct adapter.
- [ ] Cross-platform and Raspberry Pi verification is completed where applicable, and support claims do not exceed evidence.
- [ ] Known-good behavior preserved outside scope.
- [ ] Security boundaries and secret handling preserved or strengthened.
- [ ] Migration rollback material preserved until authorized cleanup.
- [ ] Focused and broader relevant verification performed where available.
- [ ] Runtime/hardware claims limited to actual evidence.
- [ ] L/XL work decomposed before implementation; parent remains open.
- [ ] ZIPs contain only allowed repository-relative files.
- [ ] ZIP links and SHA-256 values precede PRE/POST and are repeated in the
      closing instructions.
- [ ] Every existing production/runtime change has inline PRE/POST.
- [ ] Closing instructions identify the exact latest commit or uploaded file
      set used as PRE.
- [ ] Closing instructions include every delivery, its integrity value,
      repository-relative contents, and exact application step.
- [ ] Closing instructions identify every production/runtime POST to apply,
      followed only by applicable migration, tests, restart/reload, and runtime
      verification.
- [ ] No terminal commit commands.
- [ ] No unauthorized repository, GitHub, or external writes.

---

## Agent Hot Path

> **Lock the exact source → assert blockers early → trace the owning path → define the smallest complete scope → reuse the correct abstraction → preserve security, ownership, performance, and rollback → verify the full affected matrix → deliver exact PRE/POST plus repository-relative support ZIPs → close by repeating the exact latest commit or uploaded file set, applying every delivery and POST, then running only the applicable migration, tests, restart/reload, and runtime verification.**

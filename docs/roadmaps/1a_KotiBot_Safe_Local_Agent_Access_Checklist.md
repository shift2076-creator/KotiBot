# KotiBot Safe Local Agent Access

## Purpose

This file is the **only active gate for enabling a local development agent** with full read/write access to a sanitized KotiBot source checkout.

It intentionally excludes product fixes, persistence redesign, cross-platform storage migration, release engineering, and broad final-release auditing unless one of those items is discovered to be necessary to protect the agent/source/runtime boundary.

The goal is narrow:

- The agent may read and modify a clean development source checkout.
- The checkout contains no usable credentials, private runtime state, household history, private media, Matter controller identity, recovery material, or production-only artifacts.
- The agent cannot read or modify protected runtime, credential, recovery, or production-service locations merely because it can edit source.
- Normal KotiBot service operation never writes into the source checkout.
- Source/runtime boundary failures are caught by focused regression coverage.

---

# Checklist

## Completed security and sanitization foundation — do not repeat wholesale

These items remain historical prerequisites and are already complete. Reuse their existing tools/tests/evidence where a focused final check needs them; do not rerun their full audit programs merely for ceremony.

- [complete] **SEC-001** Inventory and reconcile repository, live-host, history/release, and sensitive/runtime locations without printing values or personal data.
  - [complete] **SEC-001A** Repository/source inventory.
  - [complete] **SEC-001B** Live-host metadata inventory.
  - [complete] **SEC-001C** Git-history/release/archive inventory.
  - [complete] **SEC-001D** Consolidated reviewed inventory and classification inputs.
- [complete] **DATA-001** Classify current files/fields as durable intent, irreplaceable identity, reconstructible live state, cache, protected credential, retained history, or obsolete data.
- [complete] **PATH-001** Central explicit runtime-path policy. `PATH-001A` through `PATH-001C` are complete; closure depends only on the remaining `PATH-001D.3` source-boundary work below.
  - [complete] **PATH-001A** Relocate `server_state.json` and `security_actions.json` to external application data.
  - [complete] **PATH-001B** Relocate `automations_state.json` and `tapo_lighting_state.json`.
  - [complete] **PATH-001C** Route remaining durable state, cache, log/audit, media, credential/protected state, deployment artifacts, and temporary data through explicit external roots.
    - [complete] **PATH-001C.1** Activity history externalized.
    - [complete] **PATH-001C.2** Security audit/rotation externalized.
    - [complete] **PATH-001C.3** Remaining Tapo/Android/Environment/Matter non-secret state routed externally.
    - [complete] **PATH-001C.4** Matter controller/fabric identity and subscription storage moved to explicit protected paths with rollback validation.
    - [complete] **PATH-001C.5** Notification/history and remaining application logs routed externally.
    - [complete] **PATH-001C.6** Replaceable cache/transient runtime roots established; Tapo HLS routed externally.
    - [complete] **PATH-001C.7** Android/Tapo recordings routed to protected media root.
    - [complete] **PATH-001C.8** Protected configuration, credentials, and authentication-state paths established.
    - [complete] **PATH-001C.9** Served Android APK/deployment artifacts moved outside source runtime data.
    - [complete] **PATH-001C.10** Temporary staging/transcode/Samba-operator runtime data routed externally.
  - [complete] **PATH-001D** Prove normal production service operation creates or modifies nothing beneath the source checkout.
    - [complete] **PATH-001D.1** Recursive static writer/path inventory completed; production runtime derivation from `__file__`, launch directory, or worktree paths rejected.
    - [complete] **PATH-001D.2** Live startup/restart/device/dashboard/automation/security/notification/recording/APK/Matter/cache/log/temp paths exercised as the service identity.
- [complete] **STATE-001** Typed missing/invalid/unreadable state-read failures with redacted logging.
- [complete] **STATE-002** Validated last-known-good backup behavior and protection against empty overwrite after failed reads.
- [complete] **SEC-002** Secret classes and protected storage choices defined.
- [complete] **SEC-003** Backward-compatible protected secret loading implemented.
- [complete] **SEC-004** Credentials/authentication material migrated out of ordinary worktree state.
- [complete] **SEC-005** Durable schemas and API/log output sanitized.
- [complete] **SEC-006** Migrated credentials rotated; live consumers validated; retired usable copies/fallbacks removed.
- [complete] **SEC-007** `.venv` value-free audit passed; rebuild not triggered.

---

## Remaining agent-access gates

### PATH-001D.3 — Finish no-worktree-write enforcement

- [complete] **PATH-001D.3** Eliminate every remaining production worktree write and close `PATH-001`/`PATH-001D` with focused regression coverage.

Required result:

- No resolved production runtime destination may fall beneath the source checkout.
- No normal service mutation observed during representative runtime exercise may create, modify, rotate, back up, stage, cache, or delete a file beneath the source checkout.
- Regression coverage must fail on either a resolved runtime path or an observed runtime mutation beneath the checkout.
- `tools/`, `tests/`, `temp/`, and `docs/` may remain developer/operator repository content, but production code must never treat them as runtime write destinations.
- Prefer resolver/path-containment assertions over a growing blacklist of runtime filenames.

Dependency: completed `PATH-001C`, `SEC-004`; reuse completed `PATH-001D.1/.2` evidence. Size: S–M.

### STATE-003 — Private permissions after every protected/private write

- [complete] **STATE-003** Enforce intended private directory/file ownership and modes after every atomic write that targets protected/private runtime data, and validate access as the service identity.

Required result:

- Atomic replace/rotation/backup paths do not accidentally widen permissions.
- Credential, authentication state, Matter identity, private logs/history, and protected media retain their intended access boundaries after mutation.
- Failure to apply the required ownership/mode is visible and does not silently continue with a less-private file.

Dependency: `PATH-001`, `STATE-001`. Size: S.

### PATH-003 — Remove verified legacy runtime/private residue from source

- [] **PATH-003** Remove verified legacy runtime JSON/JSONL, logs, Matter storage, APK/runtime deployment residue, recordings, caches, staging files, obsolete backups, and other runtime residue from the source checkout.

Safety rules:

- Delete only after the authoritative external destination or required recovery copy has already been validated from the actual completed migrations.
- If a residue item has uncertain ownership, recovery value, or active readership, stop on that item rather than deleting it speculatively.
- Preserve deliberate source/developer content including `tools/`, `tests/`, `temp/`, `docs/`, fixtures, and source assets.
- This task does **not** require building the deferred `MIGRATE-001` universal fixture matrix before cleaning this already-migrated host.

Dependency: `SEC-006`, `PATH-001D.3`, relevant existing migration/rollback evidence. Size: M.

### GIT-002 — Make `.gitignore` transparent again

- [] **GIT-002** Reduce `.gitignore` to genuine developer/operator residue and defense-in-depth local-secret exclusions after `PATH-003` cleanup.

Required result:

- Remove broad exclusions that could silently hide newly reintroduced runtime JSON/JSONL, logs, APKs, recordings/media, caches, or staging data.
- Retain deliberate exclusions such as `.venv/`, editor/tool caches, local secret files, and `/temp/` where appropriate.
- The source/runtime boundary is enforced by `PATH-001D.3`; `.gitignore` is not used as a substitute security boundary.

Dependency: `PATH-003`, `PATH-001D.3`. Size: S.

### PATH-002 — Separate agent-editable source from live production execution

- [] **PATH-002** Establish a practical production/source boundary before granting agent write access.

Required result:

- The agent-editable checkout must **not** be the live production execution tree whose code the running KotiBot service imports/executes.
- Use a separate development checkout/sandbox and a deliberate human-controlled promotion/deployment step into the production install, or an equivalent architecture that provides the same separation.
- The production service identity must not write source code.
- The agent identity must not gain write authority to the production install, production runtime roots, credential stores, recovery material, or service-management controls merely because it can edit the development checkout.
- No migration to `/var/lib/kotibot/` or other future final storage root is required here if the current external runtime roots are already private and correctly separated.

Dependency: `PATH-001D.3`, `STATE-003`, `PATH-003`, `GIT-002`. Size: S–M.

### AGENT-AUDIT-001 — Focused local-agent boundary audit

- [] **AGENT-AUDIT-001** Audit the final sanitized development checkout and the actual proposed agent identity/sandbox. This is a focused access-boundary gate, not a repeat of the entire application security audit.

Required checks:

1. **Source residue check**
   - Reuse the existing value-free scanners against the final development checkout.
   - Confirm no usable credential, authentication state, private history/log, Matter controller identity, private media, recovery material, or production runtime state is present beneath the checkout.
   - Confirm `.venv` remains free of protected credential material using the existing value-free audit rather than a rebuild unless triggered.

2. **Source/runtime separation check**
   - Confirm every production runtime root resolves outside the checkout.
   - Confirm no hidden compatibility fallback can redirect protected/runtime writes back beneath the checkout.
   - Confirm the running production service does not execute/import from the agent-editable development checkout.

3. **Actual agent-identity denial check**
   - Grant/read the source checkout exactly as intended for normal agent work.
   - Prove denied reads and writes to credential stores, authentication state, Matter identity, private log/history, protected media where appropriate, recovery copies, production runtime roots, and the production install.
   - Confirm the agent does not inherit the production service environment or reusable credentials.
   - Confirm no direct production publication/service-management authority and no automatic direct publication to protected branches/remotes.

4. **Regression gate**
   - Run focused path/permission/security tests affected by the sanitation work.
   - Run the normal full automated test suite.
   - Run the live denial matrix under the proposed agent identity.
   - Retain only sanitized evidence; no secret values or personal data belong in source reports.

Exit condition: every source/runtime/credential boundary above fails closed. Any discovered application-security issue unrelated to agent access moves to the deferred release/security audit unless it directly breaks this boundary.

Dependency: `PATH-001D.3`, `STATE-003`, `PATH-003`, `GIT-002`, `PATH-002`; completed `SEC-001–007`. Size: M.

### AGENT-001 — Enable local development agent access

- [] **AGENT-001** Enable the local development agent with full read/write access to the audited clean development checkout.

Required continuing boundaries:

- Separate non-service identity/sandbox.
- No credential/recovery/private-runtime access.
- No production-install or service-management write authority.
- No inherited production service environment.
- Network and publication authority limited to the explicitly intended development workflow.
- Promotion/deployment to production remains a deliberate human-controlled action.

Dependency: `AGENT-AUDIT-001`. Size: S.

---

## Agent-access completion condition

Safe local-agent access is authorized when all seven remaining gates above are complete. `STAB`, `STATE-004–007`, `MIGRATE-001`, deferred acceptance testing, and the final release audit remain valid future work but do not block authorization unless a focused agent-boundary check discovers a direct dependency.

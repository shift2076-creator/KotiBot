# KotiBot full audit — bounded execution plan

Source baseline: `edf516f7b4e25668bf1e8a9275ae46d1d8c7e09a`  
Repository: `shift2076-creator/KotiBot`  
Prepared: September 25, 2026 (America/New_York)  
Status: planning complete; application audit not yet executed.

## Working size

Use one checklist chunk per focused Astra extra-high session. A chunk owns one behavior family or trust boundary, its direct dependencies, and the evidence needed to assess it. Model effort does not establish correctness; the evidence does.

Start with approximately 3–8 primary modules or a bounded set of functions in a large module. This is a planning heuristic, never a coverage limit. Follow relevant callers, consumers, state, UI and security helpers outside that set. Large files must be partitioned by named functions/flows, never arbitrary line ranges. The first action inside a chunk is to enumerate its exact functions, routes and cases in the behavior register.

If one chunk contains more than roughly six substantial scenarios, several independent state machines, or cannot be reviewed and verified with room to challenge its results, split it into independently completable children before deep work. For example, KB-D02 can become caller-class route groups with a final route reconciliation; KB-H06 can become separate Matter, Tapo and Android setup flows. Keep the parent open. Do not fragment one tightly coupled transaction just to meet a file count.

Reserve approximately one quarter of a session's working capacity for reproduction, verification and handoff. This is a practical heuristic, not a model context-limit claim or time guarantee. A hardware/soak session can span elapsed time and may need several scheduled observations. Fifty initial chunks are an inventory of bounded work, not a promise that exactly fifty chats will finish the audit.

## Authority and existing checklists

This package plans a full product audit at the user's request. It makes no production changes, grants no local-agent access and does not activate the beta release gate. Subsequent audit sessions may inspect source and use isolated synthetic fixtures within their agreed scope. Fixes, deletion, migration, credential changes, deployments and disruptive live actions require the applicable task authority. Do not repeatedly request authority already given in the active session.

`AGENTS.md` and the existing roadmaps remain authoritative. Preserve completed security work; reuse its evidence with a targeted applicability check against this baseline. Do not repeat whole migrations or historical secret inventories for ceremony. The active local-access lane remains PATH-003 → GIT-002 → PATH-002 → AGENT-AUDIT-001 → AGENT-001 after the completed PATH-001D.3/STATE-003 foundations. KB-B01/B03 assess those facts; they do not perform cleanup or enable access.

The full product audit and local-agent access gate are distinct. Public-source review can proceed without granting a local agent production access. A critical/high exposure invokes the repository's stop/containment rule. A blocked hardware or identity check remains open; independent source work can continue where its own prerequisites are met.

Existing deferred beta TEST/OPS/AUDIT items are cross-references, not completed by this package. Later beta acceptance must use the actual beta candidate.

## Execution order

Begin **KB-A00 → KB-A01 → KB-B01 → KB-B02**. Complete KB-B03 when the real identity/deployment evidence is available; do not substitute configuration assumptions for denied-access checks. Then follow the explicit prerequisites below. KB-C03/C04 put the observed slow service stop under review early. KB-E02 retains the Matter fixes as regression scenarios; it does not start from an assumption that those changes are flawless.

Groups are organizational, not indivisible tasks. Readiness follows dependencies. `ALL_REQUIRED` in KB-J06 includes all required evidence, any newly created children, and remediation verification. No parallel agents are required by this plan. If separate reviewers are explicitly authorized later, give them independent bounded scopes and the same baseline.

A prerequisite normally supplies the reviewed contract or environment needed for the dependent work; it need not have all eventual hardware proof closed. Record which upstream evidence is being consumed and any assumption still open. For example, missing Android app source may block the client-side portion of KB-E05 while its reviewed server event contract still supports synthetic KB-F02 tests. Do not use this to claim the missing client/hardware proof. If an unknown upstream fact can change the dependent conclusion, block that affected case.

## Definition of completion

Each chunk must provide:

1. Exact revision and environment, including external versions when relevant.
2. A list of reviewed functions/routes/behaviors and an end-to-end ownership trace.
3. Expected behavior grounded in code contracts, requirements or explicit user decisions.
4. Reproduction or test results for required normal, failure, recovery and concurrency cases; omitted dimensions require a reason.
5. Confirmed findings separated from hypotheses, with sanitized evidence and limitations.
6. Updated registers and a short handoff naming the next unblocked chunk.

Use `not_started`, `in_progress`, `review_complete`, `verified`, `blocked`, or `not_applicable`. `review_complete` means the review is finished but fixes or required proof may remain. `verified` requires all listed acceptance cases and remediation proof, or an explicit recorded risk acceptance for any exception. Never use `verified` because a file was merely read. Mark `not_applicable` only with a reason and reviewed scope. Parent closure requires integrated verification.

For cross-layer work, separately mark **source**, **isolated tests**, **browser**, **live host**, and **physical hardware** evidence. A skipped test is not a pass. Zero discovered tests is not a pass. A synthetic vendor response does not prove a physical state transition. Do not inflate coverage by counting static assets as reviewed runtime behavior.

## Source inventory and external inputs

The non-truncated Git tree contains **367 tracked files**. `coverage.json` records every path, blob SHA, byte size, planned review ownership, and initial status. These are planning assignments based on the pinned tree, not completed semantic reviews. KB-A00 must refine symbol/route/state ownership and explicitly account for any discovered additional repository, binary or runtime component.

The repository includes 68 test files and 26 operator tools. Large owners include dashboard actions/rendering, Tapo routes/control/UI, Matter runtime/routes and the security module. Their entry points intentionally recur in multiple chunks, each with a different behavior boundary. Coverage must record which symbols each chunk reviewed so repetition cannot conceal gaps.

No Android `.kt` or `.java` source appears in this tree. Obtain the appropriate app source/build revision for client-side review; server routes and documentation do not establish client implementation correctness. The tracked systemd content is a credential drop-in, not the complete effective service. KB-I02 requires sanitized actual unit/drop-ins, proxy settings and dependency/native-tool versions. The deployed Pi revision is not yet independently established by this plan.

Committed files are only one inventory surface. KB-A00/B01/I02 must account for deployed tracked/untracked/ignored residue, installed packages, native tools, reverse-proxy configuration, scheduled services, external clients and recovery locations using metadata and value-free evidence. Do not export credentials, private recordings or household identifiers to this package.

Windows support remains unproven until the appropriate matrix exists. Inspect platform adapters and record Linux/Pi versus Windows behavior explicitly; missing Windows execution evidence is a limitation, not an implicit pass or a reason to rewrite the platform during this audit.

## Existing evidence and known observations

- The new commit contains the four delivered Matter production changes and the new reliability tests. Comparison against the tested local patch found only two extra blank lines in production files.
- The earlier local run reported 48 passing tests for the focused Matter/state set. The user subsequently reported the missing test/dependency checks passing. These are historical results, not a fresh full-suite run at this commit.
- The user confirmed the service became active after a slow stop and reported a positive result. Long-term sensor delivery, all device classes, and soak behavior remain unverified.
- Known follow-through includes STAB-013 recording chunks, STAB-014 P306 control, STAB-015 occupancy, and STATE-004 cold-start behavior beyond the Matter patch. Their roadmap checkboxes are not changed here.

## Chunk checklist

### A. Baseline and coverage — 2 chunks

- [ ] **KB-A00 — Scope, inventory, and ownership map**

  Prerequisites: none. Evidence: source.

  Entry points: `AGENTS.md`, `README.md`, `docs/roadmaps/*`, `server_core/subsystems.py`.

  Required proof:
  - Reconcile all 367 tracked files and identify external inputs.
  - Inventory routes, state stores, workers, pages and integration boundaries.
  - Record exclusions and assign every behavior an owner.

- [ ] **KB-A01 — Test harness and evidence baseline**

  Prerequisites: KB-A00. Evidence: isolated tests.

  Entry points: `tests/*`, `requirements.txt`, `server_core/preflight.py`.

  Required proof:
  - Map existing tests to real behavior and identify mock or source-text-only assertions.
  - Run the normal suite safely with explicit dependency and skip accounting.
  - Capture commands, revision, environment and coverage gaps without invoking production.

### B. Source, runtime and credential boundaries — 3 chunks

- [ ] **KB-B01 — Runtime roots and source residue**

  Prerequisites: KB-A00. Evidence: source and isolated fixtures.

  Entry points: `server_core/paths.py`, `server_core/private_paths.py`, `.gitignore`, `tools/path001d*`, `tools/path003*`.

  Required proof:
  - Check resolved roots, containment, symlinks and fallback readers.
  - Reconcile PATH-003 and GIT-002 against current evidence without deleting anything.
  - Exercise path escape and no-source-write rejection with synthetic roots.

- [ ] **KB-B02 — Credential and private-file boundaries**

  Prerequisites: KB-B01, KB-A01. Evidence: source and isolated fixtures.

  Entry points: `server_core/credentials.py`, `server_core/device_credentials.py`, `server_core/integration_credentials.py`, `server_core/private_paths.py`, `deploy/systemd/*/*`.

  Required proof:
  - Map secret consumers and fail-closed behavior for missing or unreadable stores.
  - Verify private modes after creation, atomic replacement, backup and failure.
  - Check value-free errors and retired-reader absence using synthetic credentials.

- [ ] **KB-B03 — Actual production and agent separation**

  Prerequisites: KB-B01, KB-B02. Evidence: live identity checks.

  Entry points: `docs/roadmaps/1a_KotiBot_Safe_Local_Agent_Access_Checklist.md`, `deploy/systemd/*/*`.

  Required proof:
  - Identify actual service execution tree, runtime roots and proposed agent identity.
  - Verify service cannot write source and agent cannot access protected runtime or production controls.
  - Reconcile PATH-002 and AGENT-AUDIT-001 with actual denial evidence without granting access.

### C. State and service lifecycle — 4 chunks

- [ ] **KB-C01 — State I/O and recoverable failure**

  Prerequisites: KB-A01, KB-B01, KB-B02. Evidence: isolated tests.

  Entry points: `server_core/io.py`, `server_core/private_paths.py`, `tests/test_state_backups.py`, `tests/test_typed_state_reads.py`.

  Required proof:
  - Test missing, invalid, truncated, non-object and unreadable state distinctly.
  - Exercise interrupted replace, permission failure, disk-full simulation and concurrent writers.
  - Prove backup validity and restoration without empty overwrite.

- [ ] **KB-C02 — Client identity and cold-start state**

  Prerequisites: KB-C01. Evidence: source and isolated tests.

  Entry points: `server_core/state.py`, `server_core/clients.py`, `server_core/status.py`.

  Required proof:
  - Classify intent, identity, live observations and cache fields across Matter, Tapo and Android.
  - Verify unknown and stale states, role identity and first-report baselines.
  - Preserve names, zones, visibility and references across restart without false actions.

- [ ] **KB-C03 — Bootstrap and subsystem registration**

  Prerequisites: KB-A01, KB-B01. Evidence: source and isolated tests.

  Entry points: `kotibot_server.py`, `wsgi.py`, `server_core/preflight.py`, `server_core/subsystems.py`.

  Required proof:
  - Trace import, registration and startup order with optional dependencies absent.
  - Check startup partial failure and repeated initialization do not duplicate workers or routes.
  - Map ownership and readiness signals without treating a listening socket as full readiness.

- [ ] **KB-C04 — Shutdown, locks, workers and subprocesses**

  Prerequisites: KB-C03. Evidence: source and isolated tests.

  Entry points: `kotibot_server.py`, `server_core/subsystems.py`, `subsystems/matter/matter_runtime.py`, `subsystems/client-tapo/tapo_routes.py`, `subsystems/video/video_routes.py`.

  Required proof:
  - Build worker and lock-order inventory including cancellation and subprocess ownership.
  - Exercise stop during blocked I/O, concurrent request and partial startup.
  - Investigate the observed roughly 90-second stop with bounded reproduction and retain live confirmation for I02.

### D. Authentication and API security — 5 chunks

- [ ] **KB-D01 — Dashboard accounts and sessions**

  Prerequisites: KB-A01, KB-B02. Evidence: source and isolated API tests.

  Entry points: `subsystems/security/kotibot_security.py`, `subsystems/security/security_routes.py`, `tests/test_dashboard_session*.py`, `tests/test_sec0063*.py`.

  Required proof:
  - Map login, logout, roles, cookie settings and password-change behavior.
  - Exercise expiry, renewal, invalidation, concurrent sessions and restart.
  - Verify failures reveal no reusable authentication material.

- [ ] **KB-D02 — Every route and its authorization**

  Prerequisites: KB-A00, KB-D01. Evidence: source and isolated API tests.

  Entry points: `server_core/routes.py`, `server_core/subsystems.py`, `subsystems/*/*routes.py`, `subsystems/security/kotibot_security.py`.

  Required proof:
  - Enumerate registered route and method pairs with intended caller classes.
  - Test unauthenticated, wrong-role, wrong-device and correct-caller behavior.
  - Include static, media, APK, SSE or other transports actually present and document exceptions.

- [ ] **KB-D03 — Origin, proxy, host and browser input policy**

  Prerequisites: KB-D01, KB-D02. Evidence: isolated API and browser tests.

  Entry points: `subsystems/security/kotibot_security.py`, `templates/*`, `static/js/dashboard-api.js`, `tests/test_security_policy.py`, `tests/test_security_trusted_hosts.py`, `tests/test_source_markup_policy.py`.

  Required proof:
  - Exercise absent, opaque, valid and attacker origins plus Fetch Metadata.
  - Test forwarded headers and trusted-host decisions at the configured trust boundary.
  - Trace representative untrusted strings through HTML, URL, JSON and DOM sinks under CSP.

- [ ] **KB-D04 — Device enrollment and key lifecycle**

  Prerequisites: KB-B02, KB-D02. Evidence: source and isolated API tests.

  Entry points: `subsystems/security/kotibot_security.py`, `server_core/device_credentials.py`, `subsystems/client-android-home/client_android_home_routes.py`, `tests/test_sec0062*.py`.

  Required proof:
  - Exercise enrollment expiry, single-use consumption and wrong-identity requests.
  - Verify staged handoff, replacement, revocation and removal preserve client ownership.
  - Check restart and interrupted handoff with synthetic identities without rotating real devices.

- [ ] **KB-D05 — Signatures, replay and request limits**

  Prerequisites: KB-D04. Evidence: isolated API and concurrency tests.

  Entry points: `subsystems/security/kotibot_security.py`, `subsystems/client-android-home/client_android_home_telemetry.py`, `subsystems/client-android-key/*py`.

  Required proof:
  - Test canonical request/body signing, timestamp windows and identity binding.
  - Exercise replay, concurrent nonce reuse, clock skew and restart.
  - Verify bounded nonce/rate-limit state and proxy-aware caller attribution.

### E. Device protocols and event ownership — 6 chunks

- [ ] **KB-E01 — Matter identity, discovery and commands**

  Prerequisites: KB-C02, KB-D02. Evidence: source and simulated chip-tool.

  Entry points: `subsystems/matter/matter_runtime.py`, `subsystems/matter/matter_routes.py`, `tests/test_path001c4_matter_runtime_wiring.py`.

  Required proof:
  - Trace controller identity, endpoint discovery and stable child mapping.
  - Exercise command failure, timeout, malformed output and concurrent sync or recommission.
  - Preserve identity and protected storage through failed operations.

- [ ] **KB-E02 — Matter subscriptions and event delivery**

  Prerequisites: KB-E01, KB-C04. Evidence: source and simulated chip-tool.

  Entry points: `subsystems/matter/matter_runtime.py`, `subsystems/matter/matter_routes.py`, `tests/test_matter_reliability.py`.

  Required proof:
  - Trace bulb, occupancy, contact, environment, reachability, battery and button reports.
  - Exercise initial baseline, duplicates, ordering, quiet heartbeat and noise without reports.
  - Verify independent node recovery, cancellation and downstream event delivery without false freshness.

- [ ] **KB-E03 — Tapo commands and extender child identity**

  Prerequisites: KB-C02, KB-D02. Evidence: source and mocked vendor APIs.

  Entry points: `subsystems/client-tapo/tapo_control.py`, `subsystems/client-tapo/tapo_extenders.py`, `subsystems/client-tapo/tapo_bulbs.py`, `subsystems/client-tapo/tapo_plugs.py`, `tests/test_tapo_command_integrity.py`.

  Required proof:
  - Trace selected device or P306 child to vendor command target.
  - Test timeout, wrong child, stale cached result and partial multi-device failure.
  - Define command acceptance versus confirmed physical transition and preserve saved metadata.

- [ ] **KB-E04 — Tapo discovery, telemetry and energy**

  Prerequisites: KB-E03, KB-C01. Evidence: source and mocked vendor APIs.

  Entry points: `subsystems/client-tapo/tapo_routes.py`, `subsystems/client-tapo/tapo_types.py`, `subsystems/client-tapo/tapo_energy.py`, `subsystems/client-tapo/tapo_admin_routes.py`, `tests/test_tapo_persistence_contract.py`.

  Required proof:
  - Trace discovery merge and stable roles, capabilities and child IDs.
  - Verify cold-start unknown, offline recovery and retained settings.
  - Check energy units, timestamps, cache bounds and request/write volume.

- [ ] **KB-E05 — Android telemetry, roles and presence**

  Prerequisites: KB-C02, KB-D04, KB-D05. Evidence: server tests and external client source.

  Entry points: `subsystems/client-android-home/*py`, `subsystems/client-android-key/*py`, `server_core/clients.py`, `tests/test_android_client_role_detection.py`, `tests/test_key_client_dashboard_session.py`.

  Required proof:
  - Trace role and device identity across enrollment, heartbeat, presence and removal.
  - Test delayed, duplicated and out-of-order telemetry without false door or motion actions.
  - Pair server contract with pinned Android client source or explicitly block client-side conclusions.

- [ ] **KB-E06 — Activities and event history**

  Prerequisites: KB-C02. Evidence: source and isolated tests.

  Entry points: `subsystems/activities/*py`, `static/js/dashboard-log.js`, `server_core/security_actions.py`.

  Required proof:
  - Trace producer event identity, normalization, ordering and deduplication.
  - Verify retention and privacy without losing meaningful user events.
  - Test concurrent writes, restart, malformed history and API output.

### F. Automations and security behavior — 3 chunks

- [ ] **KB-F01 — Automation and scene definitions**

  Prerequisites: KB-C01, KB-D02. Evidence: source and isolated API tests.

  Entry points: `subsystems/automations/automations_routes.py`, `subsystems/automations/trigger_routes.py`.

  Required proof:
  - Inventory implemented rule, scene, condition and action schemas.
  - Exercise validation, save/edit/delete and dangling device or zone references.
  - Verify persistence and partial-write recovery preserve intended rules.

- [ ] **KB-F02 — Triggers, schedules and timers**

  Prerequisites: KB-F01, KB-E02, KB-E04, KB-E05. Evidence: isolated time and event tests.

  Entry points: `subsystems/automations/trigger_routes.py`, `subsystems/automations/automations_routes.py`, `server_core/subsystems.py`.

  Required proof:
  - Test event edges, repeated occupancy, retrigger, debounce and duplicate delivery.
  - Exercise timers, cancellation, restart, midnight, DST and clock changes where schedules exist.
  - Check overlapping actions and slow or failed devices for bounded execution.

- [ ] **KB-F03 — Security modes and action dispatch**

  Prerequisites: KB-F02, KB-D02, KB-E06. Evidence: isolated event and API tests.

  Entry points: `server_core/security_actions.py`, `subsystems/security/security_routes.py`, `subsystems/security/kotibot_security.py`.

  Required proof:
  - Trace Home, Asleep and Away transitions and their authoritative state.
  - Exercise arming delays, sensor baselines, cancellation and restart.
  - Verify recording, sound and notification dispatch honor mode and device state exactly once where required.

### G. Media and supporting integrations — 9 chunks

- [ ] **KB-G01 — Android camera frames and upload admission**

  Prerequisites: KB-D05, KB-E05. Evidence: isolated API tests.

  Entry points: `subsystems/client-android-home/client_android_home_telemetry.py`, `subsystems/video/video_routes.py`, `tests/test_android_frame_upload_context.py`.

  Required proof:
  - Verify signed identity and camera capability reach the frame handler.
  - Exercise malformed, oversized, concurrent and interrupted frame requests.
  - Check timestamp/freshness contract, bounded memory and protected staging.

- [ ] **KB-G02 — Android recording chunks and reassembly**

  Prerequisites: KB-G01, KB-C01. Evidence: fixture media and external client source.

  Entry points: `subsystems/client-android-home/client_android_home_telemetry.py`, `subsystems/video/video_routes.py`, `docs/ANDROID_CAMERA_SUBSYSTEM.md`.

  Required proof:
  - Map recording/chunk identity, sequence, integrity and acknowledgment contract.
  - Exercise duplicate, missing, reordered, interrupted and resumed chunk delivery.
  - Prove byte or decoded-media equivalence as appropriate and explicitly distinguish metadata from media proof.

- [ ] **KB-G03 — Recording, transcoding and media serving**

  Prerequisites: KB-G02, KB-D02, KB-B01. Evidence: isolated media fixtures.

  Entry points: `subsystems/video/video_routes.py`, `subsystems/client-tapo/tapo_routes.py`, `server_core/paths.py`, `tests/test_media_runtime_paths.py`.

  Required proof:
  - Trace recording process ownership, FFmpeg arguments and failure cleanup.
  - Test media authorization, ranges, MIME, containment and symlink rejection.
  - Verify bounded retention and recovery from partial output without deleting live recordings.

- [ ] **KB-G04 — Tapo camera streaming and preview lifecycle**

  Prerequisites: KB-E04, KB-G03. Evidence: mocked streams and browser.

  Entry points: `subsystems/client-tapo/tapo_routes.py`, `subsystems/client-tapo/static/js/tapo-actions.js`, `subsystems/client-tapo/static/js/tapo-render.js`, `tests/test_tapo_preview_lifecycle.py`.

  Required proof:
  - Trace start/stop, HLS cache ownership and stream failure.
  - Exercise repeated open/close, detached players, visibility changes and reconnect.
  - Check preview/recording interactions and bounded process, connection and cache counts.

- [ ] **KB-G05 — Notification delivery and privacy**

  Prerequisites: KB-B02, KB-E06. Evidence: isolated provider mocks.

  Entry points: `subsystems/notifications/*py`, `server_core/device_credentials.py`, `tests/test_device_notification_credentials.py`, `tests/test_sec005_notification_history_privacy.py`.

  Required proof:
  - Trace recipient identity, provider credential source and delivery result.
  - Exercise invalid tokens, provider timeout, retry and duplicate delivery.
  - Verify bounded history, redaction and meaningful failure status.

- [ ] **KB-G06 — Environment and external network data**

  Prerequisites: KB-C01, KB-D02. Evidence: isolated provider mocks.

  Entry points: `subsystems/environment/environment_routes.py`, `subsystems/network/external_ip.py`, `subsystems/environment/static/js/environment-render.js`.

  Required proof:
  - Check provider parsing, units, timestamps and user-config ownership.
  - Exercise timeout, invalid JSON, stale cache, rate limiting and offline operation.
  - Verify bounded refresh and private location/network data handling.

- [ ] **KB-G07 — Bluetooth discovery and presence**

  Prerequisites: KB-C02, KB-D02. Evidence: source and adapter mocks.

  Entry points: `subsystems/bluetooth/bluetooth_routes.py`, `server_core/subsystems.py`.

  Required proof:
  - Trace discovery, identity and presence consumers.
  - Exercise missing adapter, permissions, cancellation and stale observations.
  - Check scan cadence, concurrency and Linux/unsupported-platform behavior.

- [ ] **KB-G08 — Voice and soundboard action boundaries**

  Prerequisites: KB-D02, KB-F03. Evidence: isolated API and browser tests.

  Entry points: `subsystems/voice/*py`, `subsystems/voice/static/js/*`, `subsystems/soundboard/*py`, `subsystems/soundboard/wavs/*/*`.

  Required proof:
  - Map voice command interpretation to authorized actions and audio output.
  - Exercise invalid input, timeouts, cancellation and concurrent playback.
  - Verify audio asset containment, browser permission failure and bounded resource lifetime.

- [ ] **KB-G09 — APK and file-server delivery**

  Prerequisites: KB-D02, KB-B01. Evidence: isolated API fixtures.

  Entry points: `subsystems/file-server/*py`, `tests/test_file_server_apk_layout.py`, `tests/test_package_runtime_paths.py`.

  Required proof:
  - Map supported package names, versions and access policy.
  - Exercise traversal, symlink, missing file and partial package cases.
  - Verify external artifact roots and correct response headers without exposing runtime files.

### H. Browser behavior and accessibility — 7 chunks

- [ ] **KB-H01 — Browser bootstrap, transport and state ownership**

  Prerequisites: KB-C02, KB-D03. Evidence: source and browser.

  Entry points: `static/js/dashboard-main.js`, `static/js/dashboard-api.js`, `static/js/dashboard-state.js`, `static/js/dashboard-events.js`, `templates/index.html`.

  Required proof:
  - Trace first render, authoritative updates and connection loss/recovery.
  - Exercise reload, duplicate listener setup, delayed responses and session expiry.
  - Verify unknown/stale/healthy distinctions and bounded DOM/update work.

- [ ] **KB-H02 — Device controls, zones and shared rendering**

  Prerequisites: KB-H01, KB-E03. Evidence: source and browser.

  Entry points: `static/js/dashboard-actions.js`, `static/js/dashboard-render.js`, `static/js/dashboard-utils.js`, `static/css/*`, `tests/test_dashboard_zone_reorder_handle.py`.

  Required proof:
  - Cover Home/Controls device classes, zone ordering, names, favorites and hidden devices.
  - Test command pending/success/failure and canonical IDs across views.
  - Verify mouse, touch, keyboard and cancel/reload preserve intent.

- [ ] **KB-H03 — Monitor and camera interaction**

  Prerequisites: KB-H01, KB-G01, KB-G04. Evidence: source and browser.

  Entry points: `static/js/dashboard-actions.js`, `static/js/dashboard-render.js`, `subsystems/client-android-home/static/js/*`, `subsystems/client-tapo/static/js/*`, `tests/test_camera_recording_indicator.py`.

  Required proof:
  - Cover preview, recording, talk controls and stale feed states.
  - Verify recording indicators and reduced motion across dashboard locations.
  - Exercise navigation, modal close, resize and media teardown.

- [ ] **KB-H04 — Sensors, Environment and Activities views**

  Prerequisites: KB-H01, KB-E06, KB-G06. Evidence: source and browser.

  Entry points: `static/js/dashboard-render.js`, `static/js/dashboard-log.js`, `subsystems/environment/static/js/*`, `subsystems/matter/static/js/*`.

  Required proof:
  - Map displayed values, units, timestamps and history to authoritative observations.
  - Exercise missing, stale, invalid and rapidly changing data.
  - Verify page filters, narrow layouts and actionable errors without fabricated freshness.

- [ ] **KB-H05 — Account, session and security settings UI**

  Prerequisites: KB-H01, KB-D01, KB-F03. Evidence: source and browser.

  Entry points: `templates/login.html`, `static/js/dashboard-actions.js`, `static/js/dashboard-render.js`, `tests/test_dashboard_user_accounts_ui.py`, `tests/test_dashboard_session_management.py`.

  Required proof:
  - Cover login/logout, account management and session invalidation flows.
  - Verify security mode/configuration feedback for permitted and denied roles.
  - Test keyboard focus, errors, cancel and narrow/medium/wide layouts.

- [ ] **KB-H06 — Device setup, management and integration editors**

  Prerequisites: KB-H01, KB-E01, KB-E04, KB-E05. Evidence: source and browser.

  Entry points: `static/js/dashboard-actions.js`, `subsystems/matter/static/js/*`, `subsystems/client-tapo/static/js/*`, `subsystems/client-android-home/static/js/*`, `tests/test_dashboard_new_device_modal_navigation.py`.

  Required proof:
  - List every implemented add/edit/remove/recommission/provision flow and role variant.
  - Test success, failure, cancellation, back navigation and duplicate submissions.
  - Check capability-driven controls, identity preservation and sensitive-value handling.

- [ ] **KB-H07 — Automation and scene editor flows**

  Prerequisites: KB-H01, KB-F01, KB-F02. Evidence: source and browser.

  Entry points: `subsystems/automations/static/js/*`, `static/js/dashboard-actions.js`, `static/js/dashboard-render.js`, `static/css/modals.css`.

  Required proof:
  - Exercise create/edit/duplicate/delete and references exposed by current UI.
  - Verify saved rule semantics match displayed trigger, conditions and actions.
  - Test invalid forms, missing devices, cancel/reopen and responsive accessibility.

### I. Deployment, dependencies and operator tools — 5 chunks

- [ ] **KB-I01 — Dependencies, vendored assets and provenance**

  Prerequisites: KB-A00, KB-A01. Evidence: source and current advisory lookup.

  Entry points: `requirements.txt`, `licenses/*`, `LICENSE`, `subsystems/client-tapo/static/vendor/*`, `static/img/dashboard-icons/LICENSE*`.

  Required proof:
  - Inventory direct, transitive and native dependencies plus asset provenance.
  - Check applicable current advisories against exact installed versions using primary sources.
  - Review pinning, reproducibility, licenses and vendored update exposure.

- [ ] **KB-I02 — Actual deployment and resource controls**

  Prerequisites: KB-B03, KB-C04, KB-D03, KB-I01. Evidence: live metadata and planned lifecycle test.

  Entry points: `wsgi.py`, `kotibot_server.py`, `deploy/systemd/*/*`, `README.md`.

  Required proof:
  - Record sanitized full unit/drop-ins, runtime versions, proxy/TLS and deployed revision.
  - Verify bind/trust boundaries, timeouts, limits, readiness and service identity.
  - Measure actual stop/start and explain or reproduce the earlier long stop without assuming the patch fixed it.

- [ ] **KB-I03 — Path migration and cleanup tools**

  Prerequisites: KB-A01, KB-B01, KB-C01. Evidence: source and disposable fixtures.

  Entry points: `tools/path*`, `tests/test_path*.py`.

  Required proof:
  - Trace preflight, copy, validation, cutover, rollback and exact deletion targeting.
  - Exercise wrong revision, symlink, partial copy, interrupted run and repeat invocation.
  - Prove tools preserve recovery material unless explicit cleanup authority and validation exist.

- [ ] **KB-I04 — Credential, privacy and inventory tools**

  Prerequisites: KB-A01, KB-B02, KB-D04. Evidence: source and disposable fixtures.

  Entry points: `tools/sec*`, `tools/state003*`, `tests/test_sec*.py`, `tests/test_state003_private_permissions.py`.

  Required proof:
  - Map inventory/verification, migration, rotation and retired-copy cleanup modes.
  - Exercise authority checks, interrupted handoff, ambiguous target and value-free failure.
  - Verify real secret material cannot leak through reports and never rotate production in this audit chunk.

- [ ] **KB-I05 — Operator documentation and support claims**

  Prerequisites: KB-I01, KB-I02. Evidence: source and isolated setup where available.

  Entry points: `README.md`, `AGENTS.md`, `docs/*`, `docs/roadmaps/*`, `docs/security/*`.

  Required proof:
  - Check setup, start/stop, backup/restore and recovery instructions against actual behavior.
  - Reconcile current versus historical checklist references without rewriting history.
  - Record Linux/Pi support evidence and Windows roadmap limitations, plus unavailable external client/build sources.

### J. Hardware, recovery, soak and closure — 6 chunks

- [ ] **KB-J01 — Matter physical acceptance**

  Prerequisites: KB-E02, KB-F02, KB-H02, KB-H04. Evidence: physical Matter devices.

  Entry points: `subsystems/matter/*py`, `tests/test_matter_reliability.py`.

  Required proof:
  - Exercise repeated bulb and occupied/unoccupied transitions through state, UI and consumers.
  - Test one node offline while another remains live, then reconnect and service restart.
  - Measure event loss, duplicates and first/steady-state latency with device/firmware and scenario counts.

- [ ] **KB-J02 — Tapo physical acceptance**

  Prerequisites: KB-E04, KB-G04, KB-H02, KB-H03. Evidence: physical Tapo devices.

  Entry points: `subsystems/client-tapo/*py`.

  Required proof:
  - Verify exact P306 child changes physically and metadata survives.
  - Exercise available bulb/plug/hub/sensor/camera paths with offline and reconnect cases.
  - Record unsupported/unavailable capabilities and per-device latency rather than infer success from API return.

- [ ] **KB-J03 — Android physical acceptance**

  Prerequisites: KB-E05, KB-G02, KB-G05, KB-H03. Evidence: physical Android clients and pinned app build.

  Entry points: `subsystems/client-android-home/*py`, `subsystems/client-android-key/*py`.

  Required proof:
  - Test Control/Monitor/Key roles actually installed plus foreground/background and reconnect.
  - Verify camera frame/chunk continuity, upload resume and reconstructed media.
  - Observe real notifications, presence and battery/resource behavior with client version evidence.

- [ ] **KB-J04 — Integrated restart, restore and failure recovery**

  Prerequisites: KB-C01, KB-F03, KB-G03, KB-I02, KB-J01, KB-J02, KB-J03. Evidence: isolated deployment then scheduled live checks.

  Entry points: `server_core/*`, `subsystems/*/*py`.

  Required proof:
  - Test restart during active automation, upload, subscription and recording in staging.
  - Simulate network loss, disk full, clock change, corrupt state and unavailable credentials safely.
  - Restore protected backups and verify identity, durable intent and unknown baselines before any live counterpart.

- [ ] **KB-J05 — Pi workload and soak**

  Prerequisites: KB-I02, KB-J04. Evidence: representative Pi workload.

  Entry points: `kotibot_server.py`, `server_core/*`, `subsystems/*/*py`, `static/js/*`.

  Required proof:
  - Define representative device/action workload and agreed resource and latency budgets first.
  - Track memory, CPU, descriptors, threads/processes, disk writes, network traffic and event loss.
  - Run an initial 24-hour observation with planned recovery events, extending only for unresolved risk or slower timers.

- [ ] **KB-J06 — Independent closure and regression review**

  Prerequisites: ALL_REQUIRED. Evidence: source, tests and recorded live evidence.

  Entry points: `docs/audits/edf516f/*`.

  Required proof:
  - Challenge findings, severity and negative conclusions against original requirements.
  - Reconcile every file, behavior, route/method, role, state store, worker and external input.
  - Retest accepted fixes on pinned revisions and record remaining risk without declaring beta readiness.

## Existing roadmap crosswalk

| Existing owner | Audit chunks | Closure limit |
|---|---|---|
| PATH-003, GIT-002 | KB-B01, KB-I03 | Review and fixture evidence do not authorize live deletion or ignore changes |
| PATH-002, AGENT-AUDIT-001, AGENT-001 | KB-B03, KB-I02 | Actual identity denials required; access enablement is separate |
| STATE-001/002/003 completed foundation | KB-B02, KB-C01 | Reuse and check regressions, not repeat completed migrations |
| STATE-004/005/006 | KB-C02, KB-E02/E04/E05/E06, KB-G05/G06 | Audit current behavior; redesign is a separate fix task |
| STAB-013 | KB-G02, KB-J03 | Requires client and actual reconstructed-media evidence |
| STAB-014 | KB-E03, KB-J02 | Requires correct physical P306 child transition |
| STAB-015 | KB-E02, KB-F02, KB-J01 | Requires repeated physical transitions through all consumers |
| Deferred MIGRATE-001 | KB-I03, KB-J04 | Fixture evidence only unless specific migration work is authorized |
| Beta TEST/OPS/AUDIT groups | KB-D*, KB-H*, KB-I*, KB-J* | Evidence may inform later work; beta gate stays inactive |

## Fix and revision discipline

An audit finding produces a scoped remediation proposal with owning files, affected contracts and required regression proof. It does not silently become a rewrite. Once a fix is authorized, use the repository's exact PRE/POST delivery contract and support ZIP rules.

For each accepted fix, record the new commit, changed symbols, affected chunks and required rechecks. Keep the original baseline immutable. Add a new candidate revision; carry evidence forward only when its assumptions and dependency paths remain applicable. Reopen affected behaviors and integrated checks. Do not restart every audit chunk merely because one file changed, and do not claim the mixed-revision evidence proves a final candidate until reconciled.

## Completion and residual risk

KB-J06 needs a second deliberate pass against the evidence and negative conclusions. Prefer an explicitly authorized independent reviewer; otherwise do a fresh session with the pinned source and evidence, without treating the first narrative as proof. A second model opinion alone is not independent evidence.

Every tracked artifact must have a reasoned disposition, but artifact count is not functional coverage. Every registered route/method/caller class, persistent store, worker, UI flow and physical integration in scope also needs a disposition. Resolve critical/high findings before clean closure under repository policy; any explicit risk acceptance must retain impact, evidence, owner and expiry/review date. Medium findings need a fix plan or explicit acceptance. Unavailable hardware/source remains an unresolved limitation. A 24-hour soak provides bounded observation, not a reliability guarantee.

# KotiBot server and core audit

Date: 2026-09-25  
Authoritative application source: `edf516f7b4e25668bf1e8a9275ae46d1d8c7e09a`  
Repository: `shift2076-creator/KotiBot`  
Disposition: audit completed; no application changes applied.

## Assessment

There are substantive open defects despite the passing regression suite. The highest priorities are failed startup overwriting healthy state documents, persistence depending on dashboard publication, unsafe concurrent snapshots, and device operations that can obstruct unrelated work. These deserve attention before general cleanup.

The main efficiency problem is repeated whole-system work for small changes: rebuilding status, copying six persistence documents, rebuilding static assets, and repeated device discovery and reads. Existing batching and caches already help; the repair should extend those owners and remove redundant work.

This audit covers all 15 requested Python files, including the empty package initializer: 6,448 lines. Relevant Android, Matter, Tapo, automation, environment, voice, security, network, dashboard, and deployment callers were traced. Fourteen isolated reproduction scenarios completed successfully against the actual implementation. Here, successful reproduction means the undesirable behavior was observed; it does not mean a fix passed.

All 128 available non-test files matched their pinned Git blobs after the audit. No private runtime state, real credentials, live devices, or production service was accessed. The earlier 533-case test result remains useful regression evidence; this audit did not rerun that unchanged suite or add its fault probes to it.

## Findings at a glance

High means possible state loss, broad loss of responsiveness, or failure of an authoritative operation. Medium means narrower correctness, lifecycle, protection, or material efficiency problems. Severity describes potential impact, not proof that the problem has occurred on your installation.

| ID | Priority | Finding | Evidence |
|---|---|---|---|
| A01 | High | Failed startup can replace healthy subsystem documents with empty state and then appear loaded | Two fault probes |
| A02 | High | A dashboard broadcast failure prevents persistence; callers cannot detect the failure | Fault probe and route trace |
| A03 | High | Shared-state locking is inconsistent; concurrent saves can queue only part of a snapshot | Concurrency probe and Matter caller trace |
| A04 | High; adjacent | Cancelled Tapo connection waits can permanently hold a shared lock; discovery also bypasses configured read deadlines | Two fault probes |
| A05 | High; adjacent | Automation device I/O can run while holding the global state lock | Integration probe and Android/timer traces |
| A06 | High if capacity is reached | Persistent status streams can consume every HTTP worker | Actual Waitress dispatcher and stream-generator probe; live configuration unknown |
| A07 | Medium | Notification-token mutations remain in memory after failed persistence, making retries falsely appear complete | Fault probe |
| A08 | Medium | Generic JSON path normalization follows a symlink before private-file enforcement | Filesystem probe |
| A09 | Medium | Shutdown lacks coordinated worker stopping and a reliable deadline; restart reports acceptance as success | Source trace |
| A10 | Medium | Small changes repeatedly rebuild, serialize, and queue whole-system state | Route probe and hot-path trace |
| A11 | Medium; adjacent | Routine Tapo work forces repeated discovery and duplicate device reads | Device-read probe and watcher trace |
| A12 | Medium | Static assets are rebuilt per request and development cache policy is enabled by default | Asset probe and source trace |
| A13 | Medium | Control/KEY clients are always reported non-stale, including never-seen clients | Status probe |
| A14 | Low | Dead definitions and repeated compatibility work add maintenance cost | Reference and ownership review |

“Adjacent” identifies findings outside the requested main/core files that directly affect their operation. They are reported for visibility and require an explicitly scoped repair before editing those subsystems.

## A01 — Startup failure can damage otherwise healthy state

Locations: `server_core/state.py:302–321,361–411,593–755`; `kotibot_server.py:1264–1275`.

The state wrappers convert typed read failures into empty dictionaries. The main client-list reader also converts an invalid schema into an empty list. `load_state()` then clears/rebuilds the shared registry and writes all current state documents. It does not stage and validate the entire input before mutating live state or queuing writes.

In the corrupt-main-file probe, the generic writer correctly refused to overwrite the corrupt main file. However, five other documents had already been queued. After flushing, the previously populated Tapo, Matter, and Android documents each contained zero records. Last-known-good backups may retain earlier data; this is not a claim that every recovery copy is destroyed.

The first load returned false, but the second returned true without retrying because `state_loaded` was set even after failure. A valid JSON document with `clients: 42` instead returned true immediately and queued all six documents. Main startup ignores the return value and proceeds; the missing main system configuration also falls back to a disarmed/default state.

Repair: distinguish a genuinely new installation from corrupt, unreadable, missing-with-backup, and structurally invalid state. Validate and stage all authoritative inputs before publishing them. A failed load must queue no replacement documents and must prevent dependent workers from starting. Record “loaded” only after success.

Acceptance: failure in any input preserves every healthy primary document and existing in-memory registry; retry after repair really reloads; intentional first installation still works.

## A02 — Persistence depends on successful dashboard publication

Locations: `server_core/state.py:601–606`; `server_core/routes.py:101–107`.

`save_state()` calls `broadcast_state()` first. Both operations share a broad exception handler that logs and returns no success/failure result. Injecting a broadcast exception produced zero persistence calls. A route can then continue and report success even though it did not save the accepted change.

Repair: separate authoritative persistence from optional publication and expose a meaningful result to callers. Clearly distinguish an accepted queued write from a durable write. A status-rendering failure must not prevent a valid configuration change from being saved. Do not simply reverse the two statements and leave error reporting ambiguous.

Acceptance: broadcast failure does not lose a save; persistence failure produces an honest API result and a deliberate in-memory rollback or recovery state.

## A03 — The shared-state lock contract is not consistently enforced

Locations: `server_core/state.py:429–606`; `server_core/status.py:94–103,434–480`; `kotibot_server.py:953–974,1149–1159`; representative caller `subsystems/matter/matter_routes.py:811–823`.

State helpers rely on callers holding the shared lock, but Matter callbacks update under the lock and call `save_state()` after releasing it. The main broadcaster builds status without acquiring that lock. Status generation also changes preview-viewer state, so it is not purely a read.

A controlled concurrent registry insertion during a real save caused a swallowed `RuntimeError` after only two of six state documents had been queued. Other interleavings can produce inconsistent observations even without an exception.

Repair: establish one explicit boundary for taking a consistent state snapshot. Copy the required state while locked, then perform expensive encoding and I/O outside the lock. Use clear APIs for already-locked callers. A blanket conversion to `RLock` would not solve inconsistent snapshots or long critical sections.

Acceptance: concurrent enrollment, removal, Matter events, and status publication cannot throw dictionary-mutation errors or queue a mixed/partial logical snapshot.

## A04 — Tapo cancellation and discovery deadlines need repair

Locations: `subsystems/client-tapo/tapo_control.py:695–749,1396–1422,1535–1559,1585–1590`.

The cold-connect lock is acquired using `await asyncio.to_thread(lock.acquire)` before entering the `try/finally` that releases it. Cancelling a coroutine while that thread waits does not cancel the underlying lock acquisition. When the previous owner releases the lock, the abandoned worker acquires it and no coroutine releases it.

The probe reproduced exactly that sequence: cancelled task, no connection call, global connection lock still held. Subsequent cold connections can stall. The six-second refresh timeout makes cancellation a real execution path. Merely moving code into a larger `finally` is insufficient unless ownership is tracked correctly.

Separately, discovery gathers `_enrich_control_state()` calls without the outer deadline used by ordinary refresh. That function performs a later direct `get_device_info()` call outside KotiBot's per-call timeout wrapper. A synthetic stalled read remained pending beyond both configured call and refresh deadlines. Actual waiting may be limited by SDK behavior, but KotiBot is not enforcing its own deadline on that path.

Repair: make lock ownership cancellation-safe, bound waiting as well as network calls, and give discovery enrichment a deliberate deadline. Preserve the serialization that prevents overlapping first-use authentication.

Acceptance: cancelling a queued connection waiter cannot leak a lock or strand executor shutdown; one stalled discovered device cannot prevent progress for healthy devices. This audit does not establish that these defects caused the previously observed 90-second service stop.

## A05 — Slow device calls can block unrelated server activity

Locations: `subsystems/client-android-home/client_android_home_telemetry.py:473` and its door-route call chain; `subsystems/automations/trigger_routes.py:803–864,942–1000`.

Android telemetry invokes route actions while holding the shared state lock. A Tapo action synchronously waits for device communication. The delayed auto-off callback also holds that lock during the device call. The integration probe observed the lock held inside the mocked device operation; a concurrent status lock acquisition timed out.

Repair: decide the action under the lock, perform bounded device I/O outside it, then reconcile the result under the lock using identity/version checks. Preserve retrigger and timer-cancellation semantics.

Acceptance: an offline or slow plug does not delay unrelated status, telemetry, enrollment, or configuration operations; stale command results cannot overwrite newer intent.

## A06 — SSE streams can exhaust HTTP worker capacity

Locations: `server_core/routes.py:122–173`; dashboard `EventSource` setup; `README.md:307`.

The status stream is an indefinite WSGI generator. The documented launch command specifies no worker count. Waitress 3.0.2 defaults to four request workers; when all are occupied, additional tasks wait. This behavior is documented by [Waitress](https://docs.pylonsproject.org/projects/waitress/en/stable/design.html).

Using the actual Waitress dispatcher and actual core stream generators, four streams occupied all four workers. A short queued task ran only after the streams closed. This is a dispatcher-level reproduction, not a live HTTP load test.

The effective production command, reverse proxy, and worker count were unavailable. Four tabs are therefore a demonstrated problem for the documented default, not a verified threshold for the live installation. Any finite worker pool needs a deliberate stream budget or a different serving boundary.

Repair: establish the deployed concurrency model, reserve request capacity, and bound/admit streaming connections. Evaluate a suitable streaming serving boundary if needed. Increasing threads alone postpones saturation; adding independent WSGI processes currently risks duplicated device loops and divergent in-process state.

Acceptance: the supported number of dashboards and video streams leaves bounded response time for telemetry and control requests, including reconnect bursts.

## A07 — Failed token persistence poisons retry behavior

Location: `server_core/device_credentials.py:192–231`.

`set_token()` changes the in-memory map before synchronous persistence. On failure, that new entry remains; retrying the same token takes the “already present” return path without another write. Removal has the equivalent problem: the memory entry is gone, retry returns false, and a previously persisted entry can return after restart.

Both paths were reproduced with a failed writer. Each attempted disk persistence only once across the failed call and retry.

Repair: stage, persist, then commit the in-memory mutation, or reliably restore the prior value on failure. Test update and removal independently.

## A08 — Path normalization defeats a symlink protection boundary

Locations: `server_core/io.py:74–86,208–238`; `server_core/private_paths.py` enforcement helpers.

The generic JSON helpers call `Path.resolve()` before enforcing private-file rules. A symlink is therefore turned into its destination before the no-symlink check sees it. A disposable fixture confirmed that a write through a state-file symlink changed the target and created the target's `.lkg` file while leaving the original link in place.

This requires filesystem access sufficient to place or redirect a link. It is not a demonstrated remote exploit. Specialized stores that explicitly check their original path may add protection, but the generic helper does not uphold that contract itself.

Repair: validate the original path and relevant components before resolving; use appropriate descriptor-based/no-follow operations to avoid check/use races. Define the policy for configured root aliases deliberately. Test through the JSON API as well as the lower-level private-path helper.

## A09 — Lifecycle ownership and restart reporting are incomplete

Locations: `kotibot_server.py:1256–1287`; `server_core/subsystems.py:471–527`; `server_core/io.py:339–373,397–416`; `server_core/routes.py:283–305`.

Importing the main module registers subsystems, loads state, and starts workers. The signal handler stops only the JSON writer; it does not signal the registered device/health loops or retain a complete set of handles for joining them. The five-second writer join is not a total shutdown deadline: the subsequent flush can wait indefinitely for its lock or I/O.

The signal handler also performs locking and flushing directly. Python's [signal documentation](https://docs.python.org/3.12/library/signal.html) warns about synchronization locks in handlers. A coordinated shutdown must run in ordinary control flow rather than rely on complex work inside the signal callback.

The restart route returns “Restarting” before its timer runs. On Linux it discards the child process's output and does not inspect its exit result. Failure due to service configuration or authorization can remain invisible. The Windows branch exits after spawning without verifying a successful handoff.

Repair: explicit, idempotent startup/shutdown ownership; stop producers before final persistence; retain and bound joins and external work; report restart acceptance and subsequent outcome honestly. Validate the actual service configuration. The cause of the historical slow stop remains unproven.

## A10 — Whole-system persistence and status work is amplified

Locations: `server_core/state.py:99–156,429–599`; `server_core/routes.py:101–104`; `server_core/status.py:94–103,434–480`; `subsystems/environment/environment_routes.py:128–144,701–710`; `subsystems/voice/voice_routes.py:195–209`.

Every save rebuilds six documents, rescans client collections, revisits legacy automation migration, and queues deep copies. Some stored Matter observations are explicitly cleared at startup, indicating that durable configuration and transient observations remain mixed.

A single metadata POST produced three complete status builds, two broadcasts, and six queued state documents. These are not six immediate disk writes: the existing writer coalesces by path and skips unchanged encoded content, with a default 30-second flush interval.

Each full status build sorts/scans clients, may expire preview viewers, calls environment snapshot code that reads JSON unless served from pending memory, and checks voice sessions per eligible camera. Android frame status publication can occur every 0.5 seconds; routine telemetry is throttled to five seconds. A small frame-related change therefore triggers work unrelated to that frame. Duplicate payload aliases also increase bytes, but require a consumer inventory before removal.

Repair: separate durable configuration from observations; queue only dirty state domains; publish once per logical change; cache owner-maintained read-only environment and voice summaries; coalesce before building/encoding payloads. Keep clock-only display updates local to the browser where appropriate. Consider versioned deltas only if measured payload cost warrants them.

Acceptance: one metadata operation publishes once; a frame tick does not reread unrelated state files or queue configuration documents; unchanged inputs cause no unnecessary device calls or physical writes. Measure CPU, bytes, and p95 control latency on the Pi before claiming a percentage improvement.

## A11 — Tapo discovery and reads do more work than necessary

Locations: `subsystems/client-tapo/tapo_routes.py:80–87,1633–1665,1875–1920`; `subsystems/client-tapo/tapo_control.py:473–507,695–749,1396–1422,1535–1559`.

Defaults schedule a watcher pass every 20 seconds after work completes and rediscovery when 60 seconds have elapsed. Rediscovery forces the cache to be bypassed, spawns `kasa discover`, enriches discovered devices, persists, and broadcasts. Ordinary refresh also broadcasts when it refreshed clients, without requiring a changed status value. These intervals are configurable, and actual traffic depends on devices and environment.

For a healthy cached plug, `_get_tapo_device()` probes reachability and reads device information to validate the handle. `_enrich_control_state()` immediately reads that information again. The probe recorded one reachability check and two device-info reads for one refresh.

Repair: reuse the information already fetched; budget concurrency; reserve broad rediscovery for enrollment, address changes, or a deliberate slower reconciliation policy; back off unavailable devices; refresh active/needed capabilities at an appropriate cadence. Preserve discovery of newly added devices and reliable reconnect behavior. Device polling that lacks a push alternative is not automatically obsolete.

## A12 — Static assets are repeatedly rebuilt and caching is disabled by default

Locations: `kotibot_server.py:67–100,178–181,244–253,313–334`.

The icon stylesheet loader reads and base64-encodes every SVG on each call. The source tree contains 136 icon SVGs plus the logo. The theme loader builds both themes for a request for one. Two synthetic dark-theme requests read both dark and light image files twice.

`KOTIBOT_DEV_STATIC_NO_CACHE` defaults to enabled, adding no-store behavior to development asset responses. The actual deployment environment may override it.

Repair: build/cache immutable asset output once per release or content change, generate only the needed variant, and make development cache bypass explicit. Preserve CSP behavior and no-store treatment of authenticated state. This is a small independent optimization with a clear request/read-count check.

## A13 — Control client liveness is misleading

Location: `server_core/status.py:160–179,331–341`; health loop `kotibot_server.py:1149–1159`.

KEY clients unconditionally return false from the stale check, while the displayed control status is derived directly from that value. A provisioned client with `last_seen=0` was reported Online. It also cannot trigger stale handling through the main health loop.

Repair: distinguish control capability/visibility from actual recent contact. Use the reported heartbeat interval with deliberate bounded grace, or display an explicitly different presence state if always-available capability is the intended meaning. Tapo uses separate readiness semantics and should not receive the same blanket change.

## A14 — Cleanup candidates and compatibility boundaries

Confirmed unused or ineffective wiring in the inspected caller graph includes main-module `AUTOMATIONS_DIR`, `SECURITY_DIR`, `BLUETOOTH_DIR`, `CALIBRATION_REQUIRED_SAMPLES`, and `SMOOTHING_WINDOW`. `current_server_ip()` and `safe_bool()` are passed through context entries with no active consumer found. The former therefore is not evidence of recurring external traffic.

The dashboard security bootstrap probes several historical endpoint/attribute alternatives. State saving revisits legacy recharge migration on every save. These are candidates for a documented one-time normalization boundary and a direct current interface.

Do not indiscriminately delete callback placeholders that are replaced during subsystem registration; those are active wiring. Do not declare the flat-list state reader, payload aliases, or explicit credential migration tools obsolete without verifying their remaining supported inputs and consumers. No broad deprecation of Python/Flask APIs was established by this review; the concrete cleanup is mostly local compatibility and dead wiring.

## Existing mechanisms worth retaining

The typed JSON reader, blocked unsafe writes, last-known-good backup behavior, private-file enforcement, per-path write coalescing, and unchanged-content comparison are useful foundations. Their caller integration is where several defects occur.

SSE has a one-item per-listener queue and rechecks session authorization, limiting retained backlog and preventing post-revocation publication. That does not prevent expensive payload construction or worker exhaustion. Tapo already avoids overlapping watcher refreshes. Environment checks run every 60 seconds but normally fetch weather only when its configured age requires it (default 900 seconds). External-IP checks are opt-in, default to 300 seconds, and avoid resetting unchanged DNS. These are not evidence of an indiscriminate network-wide busy loop.

## Recommended repair order

These are proposed repair areas, not a replacement roadmap or permission to change adjacent subsystems.

1. **State integrity:** A01–A03 first; cover failed reads, inconsistent snapshots, honest save results, and recovery. Include token retry and JSON path handling as separately verifiable changes at the same persistence boundary (A07–A08).
2. **Device operation reliability:** A04–A05; then remove proven duplicate reads and tune discovery ownership (A11). Cancellation and lock behavior must be fixed before increasing concurrency.
3. **Serving and lifecycle:** verify the actual service command, then address A06 and A09 with request-capacity and shutdown tests.
4. **Status and update efficiency:** A10 and liveness semantics A13, preserving dashboard and device behavior.
5. **Small independent cleanup:** asset caching A12; remove only confirmed dead/retired wiring from A14 after consumer checks.

Begin with state integrity. Broad refactoring or rewriting the server is not required to establish safer behavior.

## Evidence and limits

`evidence/probe-results.json` contains nine scenarios. `evidence/network-results.json` contains five. The included scripts reproduce those results with temporary files, synthetic clients, patched network operations, and local worker threads. They never import the live main module: selected main functions are isolated from its AST. See `REPRODUCE.md` for the exact environment and commands.

No percentage CPU/network saving, live exploit, physical-device result, full deployment compatibility, or explanation of the historical service-stop delay is claimed. Effective environment values, the complete systemd unit, proxy buffering/timeouts, live stream count, SDK/device behavior under real failure, and Pi measurements remain deployment validation items. Dependency vulnerability scanning and a complete subsystem audit are outside this main/core review.

## File coverage

| File | Reviewed responsibilities / disposition |
|---|---|
| `kotibot_server.py` | Startup, shared registry, publication, routes, assets, signal handling; A01–A03, A09, A12, A14 |
| `server_core/__init__.py` | Empty package initializer |
| `server_core/clients.py` | Classification, normalization, role/capability initialization; traced into status/state, no separate confirmed high finding |
| `server_core/credentials.py` | Protected credential loading and environment handoff; inspected without accessing credentials |
| `server_core/device_credentials.py` | Notification-token load/save/update/remove; A07 |
| `server_core/integration_credentials.py` | Integration credential parsing and explicit migration support; migration compatibility must not be confused with a runtime fallback |
| `server_core/io.py` | Typed reads, backups, queued/synchronous writes, shutdown; A01 interaction, A08–A10 |
| `server_core/paths.py` | Explicit runtime roots and preparation; reviewed alongside A08; effective host permissions not inspected |
| `server_core/preflight.py` | Requirements and startup validation; no claim of a full dependency/CVE audit |
| `server_core/private_paths.py` | Permission and symlink/descriptor enforcement; A08 caller bypass |
| `server_core/routes.py` | Metadata/status/SSE/restart paths and locking; A02, A06, A09–A10 |
| `server_core/security_actions.py` | Route/action normalization and compatibility classification; inspected with state and trigger owners |
| `server_core/state.py` | Main/subsystem restoration, migration, persistence; A01–A03, A10, A14 |
| `server_core/status.py` | Snapshot construction, side effects, role/liveness behavior; A03, A10, A13 |
| `server_core/subsystems.py` | Registration, dependency injection, worker ownership; A09, A14 |

“No separate finding” records scope coverage, not proof of absence of defects. Exact pinned blob identities and file counts are in `evidence/source-integrity.json`.

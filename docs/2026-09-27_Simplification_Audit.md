# KotiBot simplification and correctness audit — 2026-09-27

The strongest simplification opportunity is consolidating ownership of commands,
state changes and dashboard updates. Several newer paths implement ordering or
failure handling correctly while older callers retain different behavior. Those
differences cause reproducible defects as well as unnecessary work.

This report records the original audit and subsequent bounded implementation.
The initial audit changed no application code. Finding 01 is now implemented in
the development checkout, with verification recorded below. Existing working
changes and the user's roadmap deletions were preserved; no full audit was repeated.

**Upstream research follow-up.** The
[Tapo and Matter research note](2026-09-27_Tapo_Matter_Research.md) records
primary sources checked on September 27, 2026 and refines findings 01, 02 and
05. Preserve capability-specific behavior, necessary state observations and
protocol recovery while consolidating application ownership. SDK retries and
application attempts must be counted separately. The deployed Matter controller
revision and live-device behavior remain unverified.

**Source and coverage.** Current `/workspace/kotibot` working files at HEAD
`0c273d031fa2b2aa23ba975acc3af6f4c53e9ad3`, including preserved uncommitted
agent-access changes. The application files cited below were unchanged from
that HEAD at audit time. No deleted roadmap was restored or used to select work.
The inventory covered 227 Python/JavaScript/CSS/HTML files and 110,153 lines,
excluding vendored code and scratch files: 88 application files / 68,695 lines,
104 test files / 22,322 lines, and 35 tooling/deployment files / 19,136 lines.
Size was used to locate responsibilities, not as proof of bloat.

Detailed tracing covered central state/persistence/status, dashboard ingress and
rendering, Tapo interactive/Scene/scheduled/event command paths, Matter command
and configuration persistence, Android telemetry/motion, and notification
delivery. Environment, media, voice, startup wiring and test architecture received
targeted inspection. This was not a line-by-line review of every file, a renewed
isolation/security certification, or a beta release audit. Native Android source
is not in this checkout. Browser rendering, live devices, Raspberry Pi resource
measurements and Windows runtime behavior were not exercised.

**Original audit verification.** The existing Python suite ran 718 tests: 717 passed and one
test requiring an actual alternate UID was skipped. All 10 Scene JavaScript tests passed.
`git diff --check` passed. Initial runs hit the inner sandbox's loopback-socket
restriction and then rejected test fixtures placed inside the source tree. The
successful full run used approved execution in the existing development
container with the suite's normal external temporary directory. These were test
environment issues, not application failures.

Additional isolated reproductions used real functions or function bodies,
existing test fixtures, synthetic state and controlled network/process doubles.
They contacted no devices/providers and read no production credentials. Their
results are described under each finding. Local scratch reproductions remain in
`temp/astra_audit_probes.py` and `temp/astra_audit_probes.js`; full-suite output is
in `temp/astra-audit-python-tests-final.log`. Those ignored scratch files are local
evidence, not dependencies of the application or this report.

| ID | Priority | Finding | Evidence |
| --- | --- | --- | --- |
| 01 | P1 | Scheduled Tapo commands bypass ordering and overwrite replacement clients | Fixed locally; 107 Tapo tests pass; hardware checks pending |
| 02 | P1 | Matter command completion erases concurrent configuration edits | Reproduced |
| 03 | P1 | Failed arm-mode save still changes live mode and pending commands | Reproduced |
| 04 | P1 | Partial multi-file state flush can prevent restart | Reproduced |
| 05 | P2 | Older Tapo batch path replays ambiguous failures | Reproduced; UI caller distinction traced |
| 06 | P2 | Dashboard accepts failed and out-of-order status responses | Reproduced |
| 07 | P2 | Always-on dashboard profiler retains an unbounded event history | Reproduced |
| 08 | P2 | Notification “queue” loses delivery outcomes and has no concurrency bound | Reproduced with controlled sends |
| 09 | P2 | Broad snapshots, duplicate publication and repeated normalization amplify updates | Call paths and read counts verified |
| 10 | P2 | Every motion report recreates a timer and requests durable persistence | Reproduced |
| 11 | P3 | Obsolete asset/motion paths and production-default debug behavior remain | Source trace; missing-file failure reproduced |

P1 means correctness/reliability work to prioritize before cosmetic refactoring.
P2 means a demonstrated defect or avoidable runtime cost, without a claim that
its production frequency or hardware impact has been measured. P3 is cleanup
that should follow consumer/dependency checks.

Locations and reproductions below describe the original audit baseline. The
implementation follow-up under 01 describes current working files. Findings
02–11 remain open.

**01 — Scheduled Tapo commands bypass the existing command owner.**

Locations: `subsystems/automations/automations_routes.py:855` (recharge), `:985`
(daily reset), and `:708` (result reconciliation). Compare
`subsystems/client-tapo/tapo_routes.py:2202`,
`subsystems/automations/trigger_routes.py:1045`, and
`subsystems/tapo_commands.py`.

Interactive and event-triggered paths use the per-device command queue and
identity checks. Recharge and daily reset call `set_tapo_device_from_info`
directly. Their result handler looks up the current client by ID and applies an
old result without checking whether that client was replaced during device I/O.
The lower-level connection lock orders authentication, not whole commands or
reconciliation.

Evidence: a recharge fixture sent a command from a second thread while another
thread held the app's queue for that device. Replacing the registry entry during
that send still resulted in the replacement client's power state being
overwritten by the old operation. Both conditions were asserted.

Simplify by routing scheduled operations through the existing command owner,
capturing identity when reserving work, and reconciling only that identity.
Daily lighting changes can reuse the combined Scene transport where device
capabilities support it. Consolidate the duplicated command-item/result mapping
at that boundary. Preserve per-device independence and keep device I/O outside
the global state lock.

Verify overlapping recharge/manual/Scene/trigger commands, removal and
replacement during a send, queue timeouts, and independence from an offline
device. Measure physical first-action latency separately after deployment.

**Implementation follow-up — September 27, 2026.** Recharge and daily reset now
use one scheduled dispatcher and the existing application-wide Tapo queue. Each
device sequence retains its reservation through result reconciliation. Before
each send and reconciliation, the dispatcher checks both the original registry
object and its connection identity. Removed, replaced or readdressed clients
cannot receive a stale result. Transport inputs, including child lists, are
detached from mutable registry state.

The dashboard and scheduler share command-item mapping, identity capture and
scalar result application in `subsystems/tapo_commands.py`. Device I/O and queue
waits remain outside `STATE_LOCK`; different chargers can progress concurrently
within the existing eight-worker bound. Recharge rechecks battery freshness,
battery value and target power after acquiring its slot. Daily reset rechecks
power and keeps its whole lighting sequence in that slot. A failed sequence
retains already accepted results, stops its remaining commands and preserves the
existing five-minute daily retry backoff without marking the reset complete.
Batch completion persists current registry state without reapplying old results.

The existing device setter, capability handling, state observations and session
recovery remain in use. Moving daily lighting to combined Scene writes belongs
to the separately verified transport work in finding 05; it was not necessary
to correct this ordering defect.

**Follow-up verification.** All **107 Tapo tests passed**, including 13 new
scheduled-command regressions in
`tests/devices/tapo/test_tapo_scheduled_commands.py`. Coverage includes manual
command overlap, queued and in-flight client replacement, removal/readdressing,
battery changes, queue timeout recovery, detached child state, explicit failure,
partial daily failure, and progress beside an offline charger. Existing Scene,
dashboard, event-automation, camera and transport tests also passed. The command
was `PYTHONDONTWRITEBYTECODE=1 /opt/tests/bin/python -m tests devices.tapo -v`;
output is in `temp/astra-tapo-scheduled-tests.log`.

An existing mocked Kasa test stalled during asyncio shutdown inside the inner
sandbox; the suite passed in 2.810 seconds with approved execution in the existing
development container. No devices or credentials were used. Whitespace validation
passed with `git -c core.whitespace=trailing-space,space-before-tab,cr-at-eol diff --check`,
preserving the automation file's existing CRLF endings. The whole Python suite
was not rerun for this bounded change. Physical-device behavior, first-action
latency, Raspberry Pi resource use and Windows execution remain unverified.

**02 — Matter diagnostics overwrite newer durable intent.**

Locations: `subsystems/matter/matter_runtime.py:714`, `:805`, `:821`, and
`subsystems/matter/matter_routes.py:1238`.

`_run_chip_tool` reads the whole Matter document before starting a subprocess,
adds `last_command` after it returns, and writes that old document back.
Settings/node routes can update the same document while the command is running.
The subscription-process lock does not protect this read/modify/write sequence.

Evidence: the controlled subprocess saved a new temperature unit and a new node
before returning. Both operations completed successfully; command completion then
restored the old unit and removed the new node. The fixture asserted both losses.

Simplify by separating transient command diagnostics from durable node/settings
intent. Give configuration mutations one synchronized owner with narrow updates.
Do not hold that owner's lock across external commands or compensate with a
second whole-document copy. Review the other read/modify/write methods on the
same owner when implementing the correction.

Verify concurrent settings/node edits against read, inspect, snapshot and command
completion, including failures. Restart must retain accepted configuration.

**03 — A rejected arm-mode save has already changed the live system.**

Location: `server_core/routes.py:228`. Compare the explicit rollback in
`server_core/routes.py:26` for client metadata.

The arm route changes system mode, client fields and pending commands, and calls
motion synchronization before `save_state`. A `StateSaveError` produces HTTP 503
without restoring those changes. The caller is told to retry while the server
already operates in the requested mode; pending device commands can still be
delivered. This reproduction covers in-memory and queued effects, not physical
device delivery.

Evidence: forced save rejection returned 503, but live mode and the client's
pending mode were both `away`; motion synchronization had already run once.

Simplify around a consistent mutation boundary: validate and prepare the change,
accept its persistence, then publish state and release device-side effects.
Reuse the existing metadata failure contract. Audit other mutating callers of
`save_state` as part of that bounded change instead of adding bespoke rollback
patches independently to every route. Distinguish queue acceptance from durable
disk commitment; finding 04 addresses the latter.

Verify rejected saves preserve mode, client fields, pending commands and timer
state, with no publication or device action. Verify accepted saves still perform
each intended effect once.

**04 — One logical snapshot is six independent disk replacements.**

Locations: `server_core/state.py:596`, `:616`, `:637`;
`server_core/io.py:327`, `:370`.

`write_json_batch_atomic` explicitly guarantees atomic queue acceptance only.
The flush writes automation, action and subsystem documents independently, with
the main client registry last. A partial flush can leave a subsystem record that
the old registry does not know. Startup then correctly rejects it as an orphan,
but no complete committed generation is selected automatically. Individual
last-known-good files do not establish which cross-file combination is valid.

Evidence: added one synthetic Tapo device, accepted all six documents, failed the
main registry write after companion writes, and discarded process-local queues
to model restart. The new subsystem record remained on disk and a fresh state
loader returned false. The fixture used real serialization and file writes.

Simplify the durable ownership boundary before adding recovery heuristics. Put
values that must commit together into one authoritative commit unit, or select
one completely written generation through an atomic commit marker. Keep secrets
and protected storage isolated. Choosing the representation needs a small design
comparison and migration/recovery plan; this audit does not prescribe a new
database or authorize a migration.

Verify interruption after every write boundary, including device addition and
removal. Restart must load either the prior complete state or the new complete
state, never a mixed generation. Preserve existing fail-closed corruption checks.

**05 — A newer Scene path coexists with generic retry-driven dispatch.**

Locations: `subsystems/client-tapo/tapo_routes.py:2540`, especially `:2727`;
`subsystems/client-tapo/tapo_control.py:1773`; compare
`subsystems/client-tapo/tapo_scenes.py:40`.

The generic batch branch retries most command exceptions three times with sleeps.
It does not distinguish an explicit rejection from a timeout after a command
possibly reached the device. Separately, the older light setter sleeps 350 ms and
resends after an observed mismatch. The Scene path already combines supported
light fields and treats ambiguous failures more carefully.

Evidence: a generic batch with a simulated lost reply attempted the same send
three times, then returned `ok: false`. The sole browser call site found for the
batch endpoint supplies `activeHomeMode` and takes the newer Scene branch;
therefore the generic replay result is not evidence that current Home Scenes
replay. Individual dashboard controls and scheduled commands still use the
older light setter. External users of the generic branch were not inventoried.

Simplify by sharing command validation, ordering, device-capability handling and
result reconciliation. Extend the proven transport where semantics match; retire
the generic branch only after checking external consumers. Keep explicit session
rejection distinct from ambiguous transport failure. Any required observation
should update reported state without blindly replaying the write.

Verify send counts, ambiguous failure, explicit session expiry, dimmable-only
bulbs, outlet children, power-preserving presets and slow reported-state updates.
Use hardware checks before removing behavior needed by a supported device.

**06 — General dashboard status lacks the protections already used by Scenes.**

Locations: `static/js/dashboard-api.js:1042` (`applyDashboardStatusData`), `:1205`
(`refreshStatusData`), and `:1480` onward (stream/poll lifecycle).

The main `refreshStatusData` implementation consumes JSON without checking HTTP
success or `data.ok`. An error document becomes an empty client list. Polls also
have no in-flight guard or freshness check against SSE; an earlier request can
complete after a newer stream update and overwrite it. The later fallback
definition has an HTTP check but is unreachable when the main definition exists.

Evidence: a synthetic 503 response was accepted and cleared the stored client
list. A pending poll resolved after a newer SSE snapshot and changed version 2 /
power-on back to version 1 / power-off. Both cases executed the actual ingress
functions in a JavaScript VM.

Simplify to one validated status ingress and one transport lifecycle. Preserve
the last valid snapshot on failure, bound outstanding polls, and reject responses
superseded by newer state. A server revision is stronger than request order alone
when combining transports. Normalize the accepted payload once. Preserve the
current capacity fallback for clients that cannot obtain an SSE slot.

Verify malformed/error responses, slow polls, reconnects, SSE/poll interleaving,
authorization expiry and recovery without empty-dashboard flashes.

**07 — Startup instrumentation runs for the whole dashboard lifetime.**

Locations: `static/js/dashboard-api.js:22` and `static/js/dashboard-render.js:3590`.

Every profiler mark/measure appends to `entries` and emits `console.debug`.
Instrumentation remains wired to fetch and ordinary renders after startup.
There is no cap, reset or production opt-in. A long-lived dashboard therefore
retains an ever-growing diagnostic history even with developer tools closed.

Evidence: 10,000 marks left 10,001 retained entries including initialization.
Source search found no trimming/reset of this collection. This proves unbounded
retention, not a measured browser memory total or frame-time regression.

Simplify by removing completed instrumentation or making diagnostics explicitly
enabled, bounded and off by default. Preserve actionable errors separately.
Verify a long session has bounded diagnostic state and negligible disabled cost.

**08 — Notification history is presented as a queue but has no delivery lifecycle.**

Locations: `subsystems/notifications/kotibot_push.py:198`, `:228`, `:247`, `:278`,
and `:444`.

Each send starts a new daemon thread. Background wrappers discard the returned
success/failure. The JSONL entry remains `queued_fcm_pending` even after a failed
send, and there is no worker that drains/replays persisted pending entries.
There is also no append-history retention limit in this class; `recent()` limits
reading to a tail, not disk growth. Provider authentication can further serialize
those otherwise unbounded threads behind its credential lock.

Evidence: 20 controlled failed sends produced 20 thread starts and 20 history
entries still marked pending. No provider was contacted. This confirms the class
behavior; any external host log-rotation policy was not checked.

Simplify by defining the actual delivery contract and using a bounded dispatcher
with explicit, redacted outcomes. Separate retained event history from pending
delivery. Preserve the existing `persist_history=False` handling of protected
handoff payloads. Durable retry requirements must be chosen explicitly; blindly
retrying every alert is not the proposed fix.

Verify failed and successful outcomes, overload, graceful shutdown, any intended
restart semantics, retention, and absence of credentials in persisted history.

**09 — Updates perform avoidable work across unrelated responsibilities.**

Locations: `server_core/state.py:596`, `:616`; `kotibot_server.py:955`;
`server_core/status.py:434`; `subsystems/environment/environment_routes.py:128`,
`:701`; `static/js/dashboard-api.js:1042`; `static/js/dashboard-render.js:3590`.

Every central save builds/copies/validates six complete documents. A save also
broadcasts, while callers such as `subsystems/automations/trigger_routes.py:2065`
explicitly broadcast immediately afterward. Each broadcast with listeners builds
and serializes the full status while holding the shared state lock. Environment
snapshot construction rereads its JSON state. Camera uploads can invoke this
whole path every 0.5 seconds even if the viewer is on another dashboard page.
The browser then repeats normalization and the same broad root-server alias
mapping in both API ingestion and rendering.

Evidence: 20 unchanged environment snapshots caused 20 state reads after flushing
the fixture's pending writes. A central save queued six documents. Duplicate
publication call sites and the two browser normalization paths were traced.
The JSON writer already avoids unchanged disk replacement, and card rendering
already reuses existing card nodes: this finding does not claim every save writes
six files or every render rebuilds the entire DOM.

Simplify first by giving publication one owner, caching environment configuration
at its existing owner, and normalizing once at ingress. Then restrict persistence
and update work to the affected durable domain/device where measurements justify
it. Keep required protocol compatibility at explicit boundaries rather than
repeating alias searches throughout the application. No new general event bus is
required to remove the demonstrated duplication.

Verify publications per mutation, unchanged-state read/serialization counts,
cross-page correctness, camera freshness transitions and first-action latency.
Measure state-lock duration, CPU and browser work on the actual Raspberry Pi and
dashboard devices before promising a speedup.

**10 — Repeated motion reports allocate timers and persist live observations.**

Locations: `subsystems/client-android-home/client_android_home_telemetry.py:171`,
`:216`, and the telemetry `state_dirty`/`save_state` path around `:618`.

Each active motion report cancels its previous timer, starts another `Timer`
thread, and returns true for durable state dirtiness. This happens even when
recording is already active and no durable setting changed. That triggers the
full save/publication work described above. Extending the idle deadline is
required; starting a new thread and rebuilding persistence each time is not.

Evidence: 20 reports at the same fixture time constructed 20 timers, cancelled
19 and returned durable dirtiness 20 times. Timers were controlled doubles.

Simplify to one outstanding expiry timer per camera and an updated deadline.
On expiry, stop or reschedule for the remaining idle duration. Keep live motion
observations separate from durable configuration changes. Preserve automation
semantics for repeated motion and manual recording ownership.

Verify continuous motion, idle expiry, recording already active manually,
client removal/replacement and simultaneous stop/report events. Measure actual
event rates and thread churn on device before quantifying resource savings.

**11 — Obsolete alternatives and debugging defaults are still shipped.**

Locations: `kotibot_server.py:27`, `:71`, `:239`, `:246`, `:180`, `:330`;
`templates/index.html:8`; `subsystems/client-android-home/client_android_home_telemetry.py:129`.

The icon inlining route reads `static/img/dashboard-icons/kotibot-icons.css`,
which is absent. The actual template loads `static/css/kotibot-icons.css`.
Calling the old loader raised `FileNotFoundError`; normal dashboard icons use
the valid path, so this is an obsolete/broken alternative, not a demonstrated
normal-page failure. Theme requests also read/encode both themes to serve one.
`KOTIBOT_DEV_STATIC_NO_CACHE` defaults to enabled despite versioned asset URLs;
the actual production override was not inspected.

The Python image-motion scorer is defined and returned but has no caller in
this checkout. Its optional Pillow import/warning survives alongside telemetry-
reported motion. This establishes a dead local call path, not that Pillow is
unused everywhere in the project.

Simplify by removing verified unconsumed alternatives, serving the canonical
assets once, and making development-only diagnostics/cache behavior explicit.
Check external route consumers before removal. Preserve CSP, theme switching,
camera behavior and every remaining dependency user.

**Next implementation boundary.** Tapo command ownership (01) is implemented and
verified locally as described above. Next address Matter configuration ownership
(02), followed by transactional state mutation
(03–04), each with its own focused verification. Dashboard ingress (06) and the
bounded profiler change (07) are independent. Findings 05 and 09 identify code
that should shrink as ownership is consolidated; they do not justify a wholesale
rewrite. Retain the existing security checks, per-device queue, combined Scene
writes, bounded SSE queues and source/runtime separation.

No commits, deployment, credential changes, security-boundary changes or roadmap
recreation were performed. The report records demonstrated source/fixture
behavior; it does not claim these defects were observed on production hardware.

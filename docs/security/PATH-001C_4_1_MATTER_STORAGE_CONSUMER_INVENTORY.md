# PATH-001C.4.1 — Matter storage consumer inventory

PRE source: `e4da8392326e0217cb763dab9852a7510d3dd697`

## Scope and safety boundary

This checkpoint inventories path consumers and defines protected destinations.
It does not read Matter storage contents, copy data, change the active
controller path, change subscription behavior, delete any path, or authorize
legacy cleanup. Both storage trees and every controller-derived repair or
rollback tree remain protected and irreplaceable.

## Explicit protected destinations

| Purpose | Resolver property | Destination |
| --- | --- | --- |
| Protected Matter parent | `RuntimePaths.matter_protected_dir` | `<data-root>/protected/matter/` |
| Active controller/fabric storage | `RuntimePaths.matter_controller_storage_dir` | `<data-root>/protected/matter/controller/` |
| Subscription controller copies and subscription state | `RuntimePaths.matter_subscription_storage_dir` | `<data-root>/protected/matter/subscriptions/` |

`prepare_runtime_directories()` creates only the protected Matter parent and
enforces mode `0700` on POSIX. It deliberately does not create either storage
leaf. PATH-001C.4.2 and PATH-001C.4.3 must populate and validate those leaves
before any runtime consumer is allowed to use them. An absent, unreadable, or
invalid controller leaf must fail closed; it must never be treated as a reason
to initialize replacement identity.

The protected Matter parent also owns the migrated legacy rollback and repair
names `chip_tool_storage.bad-*` and `.chip_tool_storage.repair-*`. They remain
protected recovery material. This checkpoint does not create, rename, prune,
or reclassify them.

## Current path flow

| Layer | Consumer | Current behavior at the PRE source | Required later cutover |
| --- | --- | --- | --- |
| Server bootstrap | `kotibot_server.py` | Defines `MATTER_DIR` beneath `<source>/subsystems/matter/`, keeps `matter_state.json` there, and passes `MATTER_DIR` into subsystem registration. | Pass explicit controller and subscription storage roots from `RUNTIME_PATHS`; move the mixed controller state separately under its roadmap owner. |
| Subsystem wiring | `server_core/subsystems.py` | Receives `matter_dir`, passes it to `register_matter_routes()`, and separately passes the controller-state file to Environment's debug reader. | Preserve the state-file separation and forward the two protected storage paths explicitly. |
| Matter registration | `subsystems/matter/matter_routes.py:register_matter_routes` | Accepts `matter_dir`, falls back to a source-derived directory, creates it, and constructs one `MatterRuntime`. | Remove the source fallback for storage authority and require the explicit protected roots. |
| Controller runtime | `MatterRuntime.chip_tool_storage_dir()` | Derives `<matter-dir>/chip_tool_storage` and creates it on access. | Use the injected protected controller leaf and reject missing/invalid migrated identity instead of silently creating it. |
| Subscription runtime | `MatterRuntime.chip_tool_subscription_storage_dir()` | Derives `<matter-dir>/chip_tool_subscription_storage/<subscription-id>` and seeds a missing worker directory by copying the controller tree. | Use the injected protected subscription root; retain copy-first behavior only after the source controller tree is validated. |
| Status/state compatibility | `MatterRuntime.default_state()` and `MatterRuntime.status()` | Emit the current derived controller path as `chip_tool_storage`. `read_state()` does not accept the persisted field as path authority. | Continue treating the persisted field as non-authoritative; emit only the active resolved path where operationally necessary. |

## Controller and subprocess consumers

| Consumer | Storage used | Process behavior | Notes |
| --- | --- | --- | --- |
| `_run_chip_tool()` | Active controller storage unless an explicit repair directory is supplied | Runs `chip-tool` with `--storage-directory <path>` by `subprocess.run()`; the process working directory is the current Matter directory. | All commissioning, inspection, reads, discovery, snapshots, and device-control methods converge here. |
| `commission_code()` | Active controller storage | Calls `_run_chip_tool()` for pairing. | A wrong or empty path can create a different controller identity and is therefore a cutover blocker. |
| `recommission_node()` | Active controller, `chip_tool_storage.bad-*`, `.chip_tool_storage.repair-*`, and subscription root | Stops subscriptions, renames the active tree to a rollback tree, commissions in repair storage, restores on failure, promotes on success, then removes the subscription tree. | PATH-001C.4.2/.4 must preserve these atomic rename, rollback, and same-filesystem assumptions under the protected parent. Generic cache/temp cleanup may not touch these paths. |
| `subscribe_sensor_states()` | Per-node subscription storage seeded from active controller storage | Starts interactive `chip-tool` by `subprocess.Popen()` with `--storage-directory`; commands are written to stdin and output is consumed by the worker. | Subscription storage contains controller copies and remains protected in full. |
| `_matter_sensor_subscribe_loop()` | Subscription storage through `subscribe_sensor_states()` | One background subscription worker iterates configured Matter nodes, serializes access, retries, and restarts around maintenance/synchronization. | Every worker must receive the same explicit subscription root after cutover. |
| `_matter_sync_loop()` and route-triggered sync/control | Active controller storage through ordinary runtime methods | Startup and dashboard operations eventually call `_run_chip_tool()`. | Verification must cover startup sync, manual sync, reads, and commands, not only commissioning. |

`MatterRuntime.stop_subscription()` terminates tracked interactive processes but
does not itself resolve storage. The locks and maintenance events in
`matter_routes.py` coordinate these consumers and must remain part of the
atomic cutover and rollback sequence.

## Repair and rollback path operations

At the PRE source, `recommission_node()` performs all of the following beneath
the source-derived Matter directory:

1. Resolve and create `chip_tool_storage/`.
2. Select a unique `chip_tool_storage.bad-<timestamp>[-<suffix>]` rollback path.
3. Remove any colliding `.chip_tool_storage.repair-<token>` tree.
4. Rename active storage to the rollback path.
5. Create the repair tree and run commissioning against it.
6. On exceptions or unsuccessful commissioning, remove repair storage and
   restore the rollback tree.
7. On success, promote repair storage and recursively remove subscription
   storage so workers rebuild against the new controller identity.

These operations prove that active, rollback, repair, and subscription paths
must be on a deliberately selected protected filesystem. PATH-001C.4.2/.4
must validate the copied trees before cutover and must test both exception and
non-zero-result rollback paths. Cleanup remains prohibited.

## Operator and configuration consumers

| Surface | Finding |
| --- | --- |
| `README.md` | Documents `KOTIBOT_MATTER_CHIP_TOOL` for selecting the executable and warns that controller storage is sensitive. It provides no supported controller-storage override. |
| Environment/configuration names | The PRE source has no `KOTIBOT_*` variable that authoritatively selects either Matter storage tree. The persisted `matter_state.json` `chip_tool_storage` field is output/compatibility data, not an accepted override. |
| systemd/live-host review | The sanitized SEC-001B review records the two source-tree storage trees and protected systemd configuration metadata. It records no approved external storage-path consumer. No environment values or storage contents were read for this checkpoint. |
| `.gitignore` | Ignores both legacy source-tree storage directories. This is defense in depth only and remains unchanged until PATH-003/GIT-002. |
| Security inventories | SEC-001A, SEC-001B, SEC-001D, and DATA-001C consistently classify the controller, subscription copies, rollback trees, and repair trees as protected identity material requiring preservation and tested recovery. |

No separate repository script, service helper, repair utility, deployment
helper, or documented operator command reads or writes either storage tree at
the PRE source. The production consumers are the bootstrap/wiring chain,
`MatterRuntime`, its `chip-tool` subprocesses, and the background subscription
worker described above.

## Required handoff to PATH-001C.4.2–4.4

- PATH-001C.4.2 must copy and validate the active controller tree plus every
  matching rollback and repair tree into the protected Matter parent, with
  private ownership/modes and a separately validated rollback copy.
- PATH-001C.4.3 must copy the complete subscription tree as protected data and
  inject the explicit controller/subscription paths into every runtime and
  worker. No portion is cache yet.
- PATH-001C.4.4 must stop workers, cut over atomically, and verify controller
  identity, commissioned nodes, commands, subscriptions, restart recovery,
  repair behavior, and rollback before any legacy cleanup is considered.

## Completion evidence

- All repository consumers and documented live-host/operator surfaces were
  inventoried without reading stored values.
- Controller and subscription destinations are explicit resolver
  properties beneath the protected root and outside the source tree.
- Startup creates only the private protected parent; it cannot create a
  replacement controller or subscription leaf.
- Copy, wiring, cutover, verification, rollback, reclassification, and
  cleanup remain open under PATH-001C.4.2–4.4.

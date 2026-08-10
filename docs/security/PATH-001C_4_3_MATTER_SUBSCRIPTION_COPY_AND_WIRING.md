# PATH-001C.4.3 — Protected Matter subscription copy and wiring

PRE source: `f5f2378b798ba1c3eeb4f1cc0d869e9fa7df9c84`

## Boundary

This checkpoint copies the complete legacy
`chip_tool_subscription_storage/` tree into protected primary and rollback
destinations. It also removes implicit controller and subscription path
derivation from the Matter runtime: both paths are now required inputs from
the server bootstrap through the subsystem registrar and route registrar to
every `MatterRuntime` consumer and subscription worker.

This checkpoint does not activate the protected copies. The bootstrap keeps
the existing worktree controller and subscription trees selected so applying
the code cannot perform a partial cutover. PATH-001C.4.4 owns the atomic
selection change and live functional and rollback verification.

No legacy tree is moved, renamed, or deleted. The copied subscription tree is
still treated entirely as protected controller/fabric data; no portion is
reclassified as cache.

## Destination layout

| Legacy source | Protected primary | Protected recovery copy |
| --- | --- | --- |
| `subsystems/matter/chip_tool_subscription_storage/` | `<data-root>/protected/matter/subscriptions/` | `<data-root>/protected/matter/rollback/subscriptions/` |

The subscription-copy tool requires the PATH-001C.4.2 primary and rollback
controller copies to exist, match the current legacy controller tree, and have
private ownership and modes before subscription data can be copied.

## Runtime path wiring

The active path authority now follows one explicit chain:

1. `kotibot_server.py` defines the selected controller and subscription
   storage paths.
2. `server_core/subsystems.py` requires both values in its context and passes
   them to Matter registration.
3. `subsystems/matter/matter_routes.py` requires both values and constructs
   `MatterRuntime` with them.
4. `MatterRuntime` uses the explicit controller path for every ordinary
   `chip-tool` call and for recommission repair/rollback placement.
5. Every subscription worker obtains its per-node storage beneath the explicit
   subscription root and passes that location to interactive `chip-tool`.

The two bootstrap selectors intentionally still point to the legacy worktree
trees in this checkpoint. PATH-001C.4.4 can therefore perform a small,
auditable selector change only after both protected trees have been validated.

## Fail-closed behavior

The subscription-copy tool:

- requires `kotibot.service` to report exactly `inactive` before and after a
  copy;
- rejects root execution and expects the KotiBot service identity;
- validates the protected Matter parent plus the PATH-001C.4.2 controller
  primary and rollback copies before doing subscription work;
- rejects symlinks and non-regular/non-directory entries;
- creates complete private staging copies, compares content manifests, and
  promotes them by rename;
- accepts an empty but present subscription tree because it is still an exact
  protected state snapshot;
- refuses to overwrite a conflicting primary or rollback destination;
- supports idempotent revalidation of matching private destinations;
- rechecks the stopped service and source manifest after copying; and
- reports only aggregate counts and status, never stored names, contents, or
  absolute paths.

The runtime no longer creates a missing controller directory. A missing,
non-directory, or symlinked configured controller path fails closed rather
than silently initializing replacement identity. Subscription directories may
be created only beneath the explicitly supplied subscription root and are
seeded from the explicitly supplied controller tree.

## Operator interface

`tools/path001c4_migrate_matter_subscription_storage.py` defaults to a
non-mutating preflight. Actual copying requires `--copy`. It does not change
runtime selection or authorize cleanup.

## Deferred work

- PATH-001C.4.4 must stop Matter workers, revalidate controller and
  subscription copies, select both protected paths atomically, and verify the
  controller/fabric identity, commissioned nodes, commands, subscriptions,
  restart recovery, recommission repair behavior, and rollback.
- The legacy worktree trees remain protected rollback material. Their physical
  removal remains prohibited until the verified migration and PATH-003 cleanup
  gate authorize retirement.
- Safe separation of replaceable subscription state from controller identity
  remains unproven and is not attempted here.
- The roadmap remains user-controlled and is not modified by this checkpoint.

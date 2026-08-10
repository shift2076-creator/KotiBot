# PATH-001C.4.2 — Protected Matter controller copy

PRE source: `540154fea5838aa2fb382cedb23bbec1ec6f1e1b`

## Boundary

This checkpoint adds an offline, copy-only operator tool. It copies the active
`chip_tool_storage` tree and every matching `chip_tool_storage.bad-*` and
`.chip_tool_storage.repair-*` tree into the protected Matter root. It also
creates and validates a second recovery copy beneath the protected `rollback/`
directory.

It does not copy subscription storage, change any active runtime path, start
`chip-tool`, alter `matter_state.json`, delete or rename legacy data, authorize
cleanup, or check off a roadmap item.

## Destination layout

| Legacy source | Protected primary | Protected recovery copy |
| --- | --- | --- |
| `chip_tool_storage/` | `<data-root>/protected/matter/controller/` | `<data-root>/protected/matter/rollback/controller/` |
| `chip_tool_storage.bad-*/` | Same basename beneath `<data-root>/protected/matter/` | Same basename beneath `<data-root>/protected/matter/rollback/` |
| `.chip_tool_storage.repair-*/` | Same basename beneath `<data-root>/protected/matter/` | Same basename beneath `<data-root>/protected/matter/rollback/` |

The original worktree trees remain the active runtime authority and the first
rollback path until PATH-001C.4.3/.4 complete wiring and cutover verification.

## Fail-closed behavior

The operator tool:

- requires `kotibot.service` to report exactly `inactive` before and after a
  copy;
- rejects root execution so copied ownership remains the KotiBot service
  identity;
- requires the protected Matter parent to exist already with private
  ownership and mode;
- rejects a missing or empty active controller tree without creating a
  destination leaf;
- rejects symlinks, sockets, FIFOs, devices, and every non-directory,
  non-regular entry;
- builds content manifests without printing paths, filenames, hashes, or file
  contents;
- copies through a private staging directory on the destination filesystem;
- verifies every copied file and directory before promotion and again after
  all copies complete;
- enforces directory mode `0700` and regular-file mode `0600` with current
  operator UID/GID ownership;
- refuses to overwrite any existing destination; an existing tree is accepted
  only when its complete manifest and private metadata match the source;
- rescans every legacy source after copying and fails if anything changed; and
- is idempotent when all previously copied trees remain exact and private.

The default invocation performs preflight only. Copying requires the explicit
`--copy` option. Output is limited to counts, validation status, and explicit
statements that subscription storage, runtime cutover, and cleanup remain
unchanged.

## Deferred work

- PATH-001C.4.3 still owns the complete protected subscription-tree copy and
  explicit controller/subscription path wiring for every worker.
- PATH-001C.4.4 still owns atomic cutover, controller/fabric identity checks,
  commissioned-node verification, commands, subscriptions, restart recovery,
  repair behavior, rollback exercises, and cleanup authorization.
- The roadmap remains user-controlled and is not modified by this checkpoint.

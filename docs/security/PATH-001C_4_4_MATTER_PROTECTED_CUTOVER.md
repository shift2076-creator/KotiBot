# PATH-001C.4.4 — Matter protected-path cutover

PRE source: `47bd873ecc6bf49efe2bbe1d6010d1397a03af96`

## Outcome

Commit `47bd873ecc6bf49efe2bbe1d6010d1397a03af96` changed Matter runtime authority
from the worktree `chip_tool_storage/` and
`chip_tool_subscription_storage/` trees to the explicit protected paths
defined by `RuntimePaths`. This stopped-service cutover preserves the selected
protected controller as runtime authority, creates a current pre-cutover
rollback copy of each protected primary, and relocates the now-inactive
worktree trees into protected rollback storage. If protected subscription
storage is not present yet, it is initialized from the preserved worktree
subscription tree before relocation.

The worktree no longer contains active, rollback, repair, or subscription
`chip_tool_*` storage after the cutover. The `chip-tool` executable remains the
separate configured third-party tool beneath `~/tools/connectedhomeip/`; it is
not moved by this checkpoint.

No Matter storage is deleted. The earlier PATH-001C.4.2 recovery copy, selected
protected primaries, current pre-cutover copies, and relocated original trees
remain separate protected recovery material. The PATH-001C.4.2 recovery copy
may legitimately differ from a protected controller advanced by normal runtime
activity after the protected selector was applied.

## Protected layout

| Purpose | Protected location |
| --- | --- |
| Active controller/fabric identity | `<data-root>/protected/matter/controller/` |
| Active subscription storage | `<data-root>/protected/matter/subscriptions/` |
| Earlier PATH-001C.4.2 controller recovery copy | `<data-root>/protected/matter/rollback/controller/` |
| Current stopped-service cutover copies | `<data-root>/protected/matter/rollback/pre-cutover/{controller,subscriptions,...}` |
| Relocated original worktree trees | `<data-root>/protected/matter/rollback/legacy-worktree/` |

Matching `chip_tool_storage.bad-*` and `.chip_tool_storage.repair-*` trees are
also copied to `pre-cutover/` and relocated to `legacy-worktree/`. They remain
protected rollback or repair material and are not treated as ordinary cache.

## Cutover transaction

`tools/path001c4_cutover_matter_storage.py` performs these operations only when
`kotibot.service` reports exactly `inactive`:

1. Validate the private protected Matter root and verify the PATH-001C.4.2
   protected controller and earlier rollback controller copy both exist and
   remain private.
2. Manifest the selected protected controller, any selected protected
   subscriptions, and the now-inactive worktree controller, subscription,
   rollback, and repair trees without printing stored names, paths, or
   contents.
3. Initialize only a missing protected subscription primary from the preserved
   worktree subscription tree.
4. Create private current copies of the selected protected authority beneath
   `rollback/pre-cutover/`.
5. Recheck the stopped service and verify the worktree trees did not change during
   preparation.
6. Rename the original worktree trees into `rollback/legacy-worktree/`, enforce
   private modes, and restore already-moved trees if any later rename fails.
7. Recheck the stopped service and verify each protected primary matches its
   current rollback, and each relocated original remains intact. A relocated
   inactive controller is not required to match the selected protected
   controller.

The default invocation is a non-mutating preflight. `--cutover` is required for
the relocation. A completed relocation can be rerun for idempotent validation.

## Runtime selection and failure behavior

`kotibot_server.py` selects
`RuntimePaths.matter_controller_storage_dir` and
`RuntimePaths.matter_subscription_storage_dir`. The existing explicit path
wiring passes those values through the subsystem and route registrars to every
`MatterRuntime` and subscription worker.

Runtime refuses to initialize a missing controller path or follow a symlinked
controller/subscription path. Recommission repair and rollback directories are
created beside the explicit controller primary, and successful recommissioning
resets only the explicit subscription root.

If relocation preparation fails, the worktree trees remain. The tool never
overwrites an existing protected primary from an inactive worktree tree. If
relocation of multiple legacy trees fails, already-relocated trees are renamed
back before the tool exits. The service is never started by the migration
tool.

## Live completion verification

Live-host verification completed on 2026-08-10 at source
`f54029071ea58ba90bdbd573b988a1ed1df57f87`.

Verification confirmed:

- the protected controller retained the expected commissioned-node authority;
- the read-only Matter snapshot command completed successfully;
- a subscription-driven contact event reached its configured audible action;
- the service restarted with `ActiveState=active`, `SubState=running`,
  `Result=success`, and a zero main-process status;
- the effective service umask is `0077`;
- a recursive post-restart scan found no protected Matter directory or file
  with a mode broader than `0700` or `0600`;
- no `chip_tool_storage*` or repair tree was recreated in the worktree; and
- all 52 targeted PATH-001C.4 tests passed, including explicit-path,
  cutover, idempotency, repair, and rollback coverage.

PATH-001C.4 is complete. Both active Matter trees remain protected and
irreplaceable; subscription storage has not been reclassified as cache.

The protected rollback material remains. Later cleanup requires the separate
PATH-003 authorization; this checkpoint does not authorize deletion.

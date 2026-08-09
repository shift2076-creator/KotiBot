The private collector report remains outside the repository with mode 0600.This review records aliases, generalized patterns, permission classes, anddispositions only. It contains no runtime file contents, credential values,environment values, household names, device identifiers, account names, orabsolute home paths.

Review summary

The collector recorded 126 present entries, 9 expected missing locations,and no metadata-denied, scan-denied, metadata-error, or unresolved entries.

The external per-user data root and its state files use private directory andfile modes.

The protected system environment file is root-owned, mode 0600, and itssystemd declaration resolves successfully.

KotiBot systemd unit and drop-in ownership and modes are conventional.

Virtual-environment interpreter symlinks resolve normally, and no unexpected.pth file was detected.

Missing service data, log, cache, backup, runtime, temporary, and unusedper-user configuration roots are expected under the current per-userdeployment model.

Reconciled findings and dispositions

Sanitized path or pattern

Finding

Disposition

<source>/.env.shared

Ignored, group-readable/group-writable environment file; no tracked source reference or systemd declaration was found.

Treat as a potentially obsolete credential source. Classify in DATA-001, migrate any required names through SEC-002–SEC-004, rotate through SEC-006 when applicable, and remove the source-tree copy only after validated migration.

<source>/.Trash-*/**

Deleted state backups and Trash metadata remain beneath the worktree.

Treat as obsolete worktree residue. Quarantine or remove during PATH-001D cleanup after any required rollback copy is placed outside the source tree.

<source>/temp/**

Samba temporary files and a local archive remain beneath the worktree.

Treat as replaceable temporary residue. Quarantine or remove during PATH-001D and route future temporary data through PATH-001C.

<source>/subsystems/client-tapo/runtime/**

Transient camera HLS data is generated beneath the worktree.

Move to the external runtime/cache location in PATH-001C; verify absence from the worktree in PATH-001D.

<source>/subsystems/video/videos/**

Private recordings are stored beneath the worktree.

Move to protected external media storage in PATH-001C/STATE-006; include retention and backup decisions in DATA-001 and SEC-001D.

<source>/subsystems/matter/chip_tool_storage/**

Critical Matter controller/fabric material remains beneath the worktree; some directories and metadata files are group-writable or broadly readable.

Preserve as irreplaceable identity, migrate to protected external state in PATH-001C/STATE-007, enforce private modes in STATE-003, and test backup/restore before cleanup.

<source>/subsystems/matter/chip_tool_subscription_storage/**

Matter subscription controller copies and history remain beneath the worktree with mixed modes.

Classify controller identity versus replaceable subscription cache in DATA-001, migrate retained material through PATH-001C/STATE-007, and enforce private modes in STATE-003.

<source>/subsystems/notifications/firebase-service-account.json

Protected credential file has a private mode but remains beneath the worktree.

Migrate through SEC-002–SEC-004, rotate through SEC-006, then remove the source-tree copy.

<source>/subsystems/client-tapo/tapo_config.json

Non-secret integration flag remains beneath the worktree with a broadly readable mode.

Eliminate the current file form during DATA-001/STATE-005; retain only necessary non-secret integration intent in the selected durable schema.

<source>/subsystems/**/*_state.json

Durable intent, retained history, mixed settings/cache, and reconstructible device snapshots remain mixed beneath the worktree.

Classify each file and field in DATA-001; eliminate reconstructible telemetry in STATE-004/STATE-005 and migrate retained state through PATH-001C/STATE-006/STATE-007.

<source>/.venv/**

The environment root and configuration metadata are group-writable, but interpreter symlinks are expected and no unexpected .pth path was found.

Make installed code and its environment non-writable to the service in PATH-002. Apply SEC-007 only if SEC-001C finds prior or current credential contamination.

<etc-kotibot>/tapo.env

Root-owned protected environment file is mode 0600 and its systemd declaration resolves.

Accept for the current deployment; formally classify and migrate/rotate as required by SEC-002–SEC-006.

<systemd-etc>/kotibot.service{,.d/**}

Unit and drop-in metadata is root-owned with conventional public-readable modes; no unexpected symlink or unresolved environment-file declaration was found.

Accept; carry declared configuration and credential dependencies into SEC-001D.

<data-root>/**

Current external state and audit paths use 0700 directories and 0600 files.

Accept as the current per-user baseline; carry into PATH-001/STATE-003 and later service-mode migration decisions.

SEC-001B review gate

[c] The private host report remains outside the repository with mode 0600.

[c] Every present, missing, denied, unresolved, error, and symlink status wasmanually reviewed.

[c] Every unexpected path or permission finding has a recorded dispositionand downstream roadmap owner.

[c] Expected missing locations are reconciled with the current per-userdeployment model.

[c] No runtime contents, credential values, environment values, personal-datavalues, household names, or device identifiers were copied into this review.
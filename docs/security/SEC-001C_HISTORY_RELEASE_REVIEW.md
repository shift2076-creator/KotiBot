# SEC-001C — Git history and release archive review

Source commit at scan time: `aa7d91f4968e62c6dd78b2fe5b3c1ff828c9fbe9`

## Safety boundary

The private collector report remains outside the repository with mode `0600`.
The collector and this committed review contain names, identifiers,
classifications, counts, and dispositions only. They contain no file contents,
matching lines, credential values, environment values, personal data, or
absolute home paths.

## Reviewed coverage

- Git references inventoried: `3`
- Unique commits scanned: `45`
- History findings reviewed: `60`
- Tags inventoried: `1`
- Tagged-snapshot findings reviewed: `18`
- Local archives inventoried: `27`
- Local-archive findings reviewed: `109`
- Unsupported archives: `0`
- Unreadable archives: `1`

The first archive pass used an 8 MiB per-member text limit and deferred 46
large APK members. A second pass used a 64 MiB limit. It scanned every deferred
member and left no size-limited archive members.

## Git history and tag dispositions

| Commit or tag | Sanitized finding | Disposition |
| --- | --- | --- |
| `364e721f27856fdb473bba965b59cb635b22544a` | `subsystems/activities/.activity_state.json.<temporary-suffix>.tmp` was committed as a runtime-state path. | Carry the path into SEC-001D. Keep future activity data outside the source tree and remove the retained runtime copy only during coordinated cleanup under SEC-006. |
| `c135a48288b94b07d3e6b066ebc41062fdddf338` | `subsystems/security/security_audit.jsonl.1` was committed as a backup/log path and contained the `dashboard_email` key name. | Carry the path and key name into SEC-001D. Keep future audit data outside the source tree under an explicit retention policy and remove the retained copy only during coordinated cleanup under SEC-006. |
| `v0.8` targeting `364e721f27856fdb473bba965b59cb635b22544a` | The tagged snapshot contains the Activities runtime-state temporary path. | Replace or retire the affected tag during coordinated cleanup under SEC-006. Treat already-distributed copies as non-recallable and rotate credentials where exposure is possible. |

All other Git-history and tagged-snapshot findings were reviewed as
identifier-only occurrences in source code, browser form handling, tests,
scanner patterns, or roadmap text. They include authentication, FCM, Tapo,
Cloudflare, TURN, and credential-loader names but do not establish that a value
was committed. Their current configuration and rotation requirements remain
covered by SEC-002 through SEC-006.

## Local archive dispositions

Ten KotiBot Android APKs under
`subsystems/file-server/get-app/<KotiBot-package>.apk` were fully scanned and
produced no findings. Their initially deferred large DEX and native-library
members were cleared by the 64 MiB follow-up pass.

The archives beneath `<source>/.Trash-1000/files/` are obsolete worktree
residue. Most findings are redundant Python or JavaScript source identifiers,
including old source copies. The following archive members require security
follow-up:

| Artifact | Member or class | Detected names or classification | Disposition |
| --- | --- | --- | --- |
| `<source>/.Trash-1000/files/dx.zip` | `notifications/firebase-service-account.json` | Service credential path; `client_email`, `private_key`, `private_key_id` | Rotate the Firebase service-account credential in SEC-006, then remove the archive during PATH-001D. |
| `<source>/.Trash-1000/files/dx.zip` | `server_state.json` | Runtime state; `fcm_token`, `fcm_token_at`, `kotiKeySecret`, `namaiKeySecret` | Rotate affected device/key credentials and tokens in SEC-006, then remove the archive during PATH-001D. |
| `<source>/.Trash-1000/files/dx.zip` | `notifications/notification_queue.jsonl` | Backup/log and runtime-state path | Remove during PATH-001D after applying the DATA-001 retention decision. |
| `<source>/.Trash-1000/files/json_files.zip` | `subsystems/notifications/firebase-service-account.json` | Service credential path; `client_email`, `private_key`, `private_key_id` | Rotate the Firebase service-account credential in SEC-006, then remove the archive during PATH-001D. |
| `<source>/.Trash-1000/files/json_files.zip` | `server_state.json` | Runtime state; `fcm_token`, `fcm_token_at`, `kotiKeySecret`, `namaiKeySecret` | Rotate affected device/key credentials and tokens in SEC-006, then remove the archive during PATH-001D. |
| `<source>/.Trash-1000/files/json_files.zip` | Runtime-state JSON files for Activities, automations, security actions, Android Home, Tapo, environment, and Matter | Runtime-state paths | Classify retention in DATA-001 and remove the archive during PATH-001D. |
| `<source>/temp/temp.zip` | `SecurityCameraService.kt`, `TLMService.kt` | TURN credential/username and FCM synchronization identifier names | Identifier-only Android source findings. Remove or relocate the temporary archive during PATH-001D. |

The remaining Trash archives were scanned successfully and contain only source
identifier findings or no findings. Preserve nothing from Trash inside the
source tree; move any deliberately retained rollback material to protected
storage outside the repository before PATH-001D cleanup.

`<source>/.Trash-1000/files/android-studio-quail1-patch2-linux.tar.gz` is a
truncated, unreadable third-party Android Studio installer rather than a
KotiBot release artifact. It had no readable members and should be removed as
obsolete Trash residue during PATH-001D. Its unreadable status does not block
SEC-001C because its origin, class, and disposition have been recorded.

## SEC-001C conclusion

SEC-001C.1 through SEC-001C.3 are complete. The reviewed history, tag, Trash,
credential-archive, runtime-state, and temporary-archive findings above are the
sanitized inputs required by SEC-001D. Credential rotation and coordinated
retained-history cleanup remain deferred to SEC-006; worktree cleanup remains
deferred to PATH-001D.

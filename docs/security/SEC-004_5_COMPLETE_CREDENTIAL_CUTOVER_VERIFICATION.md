# SEC-004.5 complete credential cutover verification

SEC-004.5 is the integrated verification boundary for every credential class
migrated by SEC-004. It does not migrate, rotate, overwrite, remove, or display
credentials. It verifies the live Linux service after restart and preserves all
legacy rollback sources for SEC-006.

## Verification coverage

The combined verifier checks:

- `kotibot.service` is active with a positive main process ID.
- The active process received a systemd `CREDENTIALS_DIRECTORY`, proving it
  started after the `LoadCredential` cutover.
- All six runtime credential copies are present and byte-identical to the
  manager-owned sources without printing their contents.
- The systemd runtime directory and files have consistent ownership, no access
  for `other`, and no group write/execute access to credential files. This
  accepts systemd's read-only `0550/0440` presentation without weakening the
  manager-owned source requirements.
- `/etc/kotibot/credentials.d` is root-owned mode `0700`, and every source
  credential is root-owned mode `0600` on POSIX.
- Tapo single-line credentials, the Firebase JSON object, and the closed
  integration credential schema are valid.
- Protected security and notification directories/files are external to the
  source tree, owned by the active service identity, and have exact private
  permissions.
- The active service identity is read from the effective UID/GID fields in
  `/proc/<MainPID>/status`; `/proc/<MainPID>` directory ownership is not used.
- Primary and last-known-good protected authentication/notification files are
  present and private.
- Dashboard users, sessions, device keys, enrollments, and notification tokens
  remain in their protected stores.
- Every ordinary-state `*.json` document, including `.lkg.json` copies, is free
  of forbidden credential fields and protected credential values.
- The four Tapo environment fallbacks and legacy Firebase file remain
  byte/logically equivalent to their protected credentials, without displaying
  either side. The ignored legacy security file remains private, parseable,
  and available.
- Configured integration credentials remain logically equivalent to their
  matching legacy environment sources.

The ordinary-state audit constructs in-memory fingerprints from selected
protected fields. It reports only a repository-relative state filename and a
forbidden key name when applicable. It never prints a credential, identity,
service environment value, protected-state value, or absolute data-root path.

## Backward-compatibility evidence

Automated fixtures exercise the protected and compatibility paths without
altering production storage:

- named Tapo environment fallback when no protected file is selected;
- Firebase legacy-file fallback when no protected file is selected;
- integration environment fallback when no protected document is selected;
- protected-file precedence and fail-closed behavior from SEC-004.1–004.4;
- legacy authentication-state and FCM-token migrations;
- runtime/source mismatch, insecure permissions, missing rollback sources,
  forbidden ordinary keys, and credential values embedded in ordinary data.

The live verifier never disables `LoadCredential` or temporarily exposes the
service to legacy credentials. Backward compatibility is exercised with
isolated fixtures, while live rollback sources are checked for private
retention and equivalence wherever the source is immutable credential input.

## Linux/systemd audit

Run the tests first, then restart once and run the verifier from the repository
root. Root access is required to inspect manager-owned and systemd runtime
credential files. The tool derives the active data root from the service
process, so running under `sudo` does not redirect the audit to root's home.

```bash
sudo systemctl restart kotibot
systemctl is-active kotibot

sudo .venv/bin/python \
  tools/sec0045_verify_complete_credential_cutover.py \
  --service kotibot \
  --minimum-tokens 1
```

Expected output contains counts only:

```text
SEC-004.5 complete credential cutover verification passed.
service-restart-state: active (runtime-credentials=6)
protected-auth-state: ready (...counts only...)
ordinary-state: sanitized (documents=<count>)
legacy-rollback-sources: retained (sources=<count>)
```

If the running service uses a deliberately configured data root that cannot be
derived from its process environment, supply that exact absolute root with
`--data-root`. Do not use the option to bypass a path-resolution failure until
the service configuration has been inspected.

## Failure handling

A stopped verification performs no write. Preserve the exact error message,
but never paste file contents or service environment values. Important failure
classes include:

- runtime credential missing or different from its protected source;
- active service missing its systemd runtime credential directory;
- missing, symbolic-linked, malformed, or insecure protected storage;
- missing legacy rollback source before SEC-006 authorization;
- forbidden credential key in an ordinary active or last-known-good file;
- protected credential value found in ordinary state.

Do not delete, rewrite, sanitize, chmod, or replace a reported file until its
ownership and rollback role are resolved. A credential-bearing ordinary backup
must be handled as protected rollback material, not casually deleted.

## Completion boundary

A passing test batch, active restart, and passing combined verifier provide the
evidence to complete SEC-004.5 and the SEC-004 parent. They also complete the
credential-migration condition attached to PATH-001C.8. Checklist status is
updated separately by the user.

Credential rotation and removal of `/etc/kotibot/tapo.env`, ignored legacy
Firebase/security files, legacy integration environment entries, `.env.shared`,
and other old copies remain exclusively SEC-006 work.

## Platform boundary

The data/credential comparison and ordinary-state audit operate on explicit
paths and have platform-neutral fixtures. The live process adapter in this
checkpoint is intentionally Linux/systemd-specific. Windows service credential
loading, ACL verification, restart control, rollback, and full support claims
remain with the Windows service adapter and platform validation roadmap.

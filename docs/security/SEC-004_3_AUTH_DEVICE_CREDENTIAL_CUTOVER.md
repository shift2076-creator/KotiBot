# SEC-004.3 authentication and device credential cutover

SEC-004.3 separates persistent authentication material from ordinary KotiBot
state. Dashboard users, password hashes, sessions, enrollment hashes, device
HMAC keys, and the dashboard session secret remain in protected security state.
Android FCM registration tokens now live in a dedicated protected device
credential file instead of `server_state.json`.

## Runtime ownership

- Protected security state:
  `<data-root>/protected/security/security_state.json`
- Protected device notification credentials:
  `<data-root>/protected/devices/notification_credentials.json`
- Ordinary state, which must not contain FCM token fields:
  `<data-root>/state/server_state.json`

Protected directories are mode `0700` and protected files are mode `0600` on
POSIX systems. Runtime paths remain outside the source tree.

## Automatic startup migration

No manual copy step is required. Before network-facing subsystem loops start,
KotiBot performs this ordered cutover:

1. Read legacy `fcm_token` and `fcm_token_at` fields from ordinary state.
2. Atomically copy valid records into the protected credential store.
3. Prefer an existing protected record when its timestamp is at least as new.
4. Load clients with tokens hydrated only from the protected store.
5. Rewrite and immediately flush ordinary state without the legacy fields.

The protected write completes before ordinary state is sanitized. If protected
state is invalid, unreadable, symlinked, or missing while its last-known-good
copy exists, startup stops instead of silently discarding credentials. The
ordinary-state rewrite is not forced if state loading fails.

Atomic writes keep `.lkg.json` recovery copies. Do not delete those copies or
other retained legacy rollback material until the later cleanup phase explicitly
authorizes removal.

## Post-deployment validation

After applying the code, restart KotiBot and confirm it stays active:

```bash
sudo systemctl restart kotibot
systemctl is-active kotibot
```

Run the metadata-only verifier. It reports counts and storage status, never
credential values, device IDs, email addresses, or session identifiers:

```bash
.venv/bin/python tools/sec0043_verify_auth_credential_cutover.py
```

If at least one Android control client is expected to have registered an FCM
token, require that invariant explicitly:

```bash
.venv/bin/python tools/sec0043_verify_auth_credential_cutover.py \
  --minimum-tokens 1
```

Then exercise one Android notification registration or reconnect, send one test
notification, restart KotiBot, and send another. Removing a client should also
remove its protected notification token record. Re-run the verifier after each
operation when auditing the cutover.

For a restart failure, inspect only service metadata and redacted application
errors first:

```bash
journalctl -u kotibot -n 100 --no-pager
```

Do not paste protected JSON contents or credential values into issue reports,
shell history, or audit notes.

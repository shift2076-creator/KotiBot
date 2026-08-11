# SEC-004.4 integration credential cutover

SEC-004.4 moves the remaining active credential-bearing environment inputs
into one closed protected document. The runtime loads that document once and
passes one immutable credential owner to the Cloudflare and camera-talk
subsystems. It does not print values, rotate credentials, remove legacy
sources, or move non-secret operator configuration.

## Storage boundary

The protected document is:

```text
<credential-root>/integration-credentials.json
```

Its closed version-1 schema permits only these fields:

- `version`
- `cloudflare_api_token`
- `camera_talk_turn_username`
- `camera_talk_turn_credential`
- `camera_talk_ice_servers`

The migration tool safely parses a legacy composite ICE-server value before
writing it. Unknown root fields, malformed JSON, invalid types, insecure
permissions, symbolic links, and unsupported schema versions fail closed. An
existing protected document is authoritative; runtime never combines it with
legacy secret environment values.

These non-secret or sensitive-but-non-credential settings remain in protected
operator configuration rather than the credential document:

- Cloudflare zone ID, DNS record ID/type, hostname, proxied flag, and interval
- camera-talk STUN/TURN URLs, default-STUN switch, timeouts, and tuning
- runtime paths and platform/service configuration

Dashboard bootstrap email and password are deliberately excluded. SEC-004.3
already terminates those inputs in protected user/password-hash state, and
duplicating plaintext in this document would create a second credential owner.
The obsolete source `.env.shared` still has no approved reader and remains
retained as protected rollback residue until SEC-006 authorizes rotation and
removal.

## Linux/systemd preflight and copy

Run from the repository root while `kotibot.service` is active. Complete the
copy before installing the updated `LoadCredential` drop-in, because systemd
expects every declared source file to exist.

```bash
sudo .venv/bin/python tools/sec004_migrate_service_credentials.py \
  --service kotibot

sudo .venv/bin/python tools/sec004_migrate_service_credentials.py \
  --service kotibot \
  --copy

sudo .venv/bin/python tools/sec004_migrate_service_credentials.py \
  --service kotibot
```

The expanded tool continues to verify the existing Tapo and Firebase files and
adds `integration-credentials.json`. Existing identical files report
`already-current`; the new document reports `ready`, then `copied`, then
`already-current`. Output contains names and status only.

Verify filesystem metadata without reading contents:

```bash
sudo stat -c '%a %U:%G %n' /etc/kotibot/credentials.d

sudo find /etc/kotibot/credentials.d \
  -mindepth 1 -maxdepth 1 -type f \
  -printf '%m %u:%g %f\n' | sort
```

The directory must be root-owned mode `0700`; each source credential must be
root-owned mode `0600`.

Install the updated drop-in only after the protected document exists:

```bash
sudo install -D -m 0644 \
  deploy/systemd/kotibot.service.d/credentials.conf \
  /etc/systemd/system/kotibot.service.d/credentials.conf

sudo systemctl daemon-reload
sudo systemctl restart kotibot
systemctl is-active kotibot
```

Run the metadata-only verifier. Add either requirement flag when that
integration is expected on this deployment:

```bash
sudo .venv/bin/python \
  tools/sec0044_verify_integration_credential_cutover.py

sudo .venv/bin/python \
  tools/sec0044_verify_integration_credential_cutover.py \
  --require-cloudflare \
  --require-camera-talk
```

The verifier reports only configured/not-configured state and an ICE-server
count. It never prints tokens, usernames, credentials, URLs, or document
contents.

## Runtime validation

After restart:

1. Confirm the service remains active and has no credential-loader error.
2. If Cloudflare updating is enabled, observe the next normal external-IP
   cycle. Do not force an unnecessary DNS mutation solely for verification.
3. Start one normal camera-talk session and confirm ICE negotiation succeeds.
4. Restart KotiBot and repeat the camera-talk check.
5. Confirm ordinary state, application logs, and audit output contain no copied
   integration credential values.

SEC-004.5 owns the combined restart, permissions, backward-compatibility, and
ordinary-state absence audit across all SEC-004 credential classes. This
checkpoint supplies its integration-specific runtime and metadata evidence.

## Compatibility and rollback

If no protected integration document is selected, the shared loader retains a
named compatibility fallback for the four legacy integration environment
variables. Once any protected document exists, even a version-only document,
it is authoritative and legacy secret values cannot fill missing fields.

For rollback during this migration window, move the installed
`credentials.conf` outside the unit's `.d` directory, run
`systemctl daemon-reload`, and restart KotiBot. The unchanged environment
sources remain available to the compatibility loader. Preserve both source
sets until SEC-006 explicitly authorizes rotation and removal.

## Windows boundary

The shared loader supports an explicit absolute `KOTIBOT_CREDENTIALS_DIR` and
the OS-native Windows credential directory. This Linux/systemd migration tool
does not write Windows credentials because service-account ACL provisioning
belongs to the later Windows service adapter. Do not claim Windows credential
migration complete from this checkpoint.

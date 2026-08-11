# SEC-004.1/2 Tapo and Firebase credential cutover

This checkpoint moves the four Tapo account/camera values and the complete
Firebase service-account document into protected service credential files. It
does not print values, rotate credentials, remove legacy sources, or alter
ordinary runtime state.

## Safety and rollback contract

- The copy tool defaults to a read-only preflight.
- Tapo values are read directly from the running `kotibot` process environment
  through `/proc/<MainPID>/environ`; they never enter command arguments or
  command output.
- The Firebase source is read without following a final symbolic link.
- Existing destination files must be private and byte-identical. A conflict
  stops the entire preflight before any write.
- Copy mode writes private temporary files, flushes them, and atomically
  replaces only absent destinations.
- `/etc/kotibot/tapo.env` and the legacy Firebase file remain unchanged for
  rollback. Rotation and removal remain deferred to SEC-006.

## Linux/systemd preflight and copy

Run from the repository root while `kotibot.service` is active:

```bash
sudo .venv/bin/python tools/sec004_migrate_service_credentials.py \
  --service kotibot

sudo .venv/bin/python tools/sec004_migrate_service_credentials.py \
  --service kotibot \
  --copy
```

The output contains credential names and `ready`, `copied`, or
`already-current` status only. It never contains credential values.

Verify names, ownership, and modes without reading contents:

```bash
sudo stat -c '%a %U:%G %n' /etc/kotibot/credentials.d

sudo find /etc/kotibot/credentials.d \
  -mindepth 1 -maxdepth 1 -type f \
  -printf '%m %u:%g %f\n' | sort
```

The directory must be `0700`; every credential file must be `0600`.

## Cut over to systemd LoadCredential

Install the supplied drop-in, reload systemd, and restart KotiBot:

```bash
sudo install -D -m 0644 \
  deploy/systemd/kotibot.service.d/credentials.conf \
  /etc/systemd/system/kotibot.service.d/credentials.conf

sudo systemctl daemon-reload
sudo systemctl restart kotibot
systemctl is-active kotibot
```

The runtime loader prefers systemd's `CREDENTIALS_DIRECTORY`, then an explicit
absolute `KOTIBOT_CREDENTIALS_DIR`. Windows desktop mode may use its OS-native
credential location directly. Linux `/etc/kotibot/credentials.d` is the
manager-owned `LoadCredential` source and is not probed directly by the service
unless `KOTIBOT_CREDENTIALS_DIR` explicitly selects it. A missing protected
file may use the matching legacy environment variable or legacy Firebase path
during the migration window. An existing selected protected file that is
unreadable, insecure, malformed, empty, oversized, or a symbolic link fails
closed and never falls back.

## Functional verification

After restart:

1. Confirm KotiBot discovers and controls at least one Tapo light or plug.
2. Open a Tapo camera preview and confirm the stream starts.
3. Start and stop one Tapo camera recording.
4. Trigger one notification action and confirm its Android FCM delivery.
5. Restart KotiBot once more and repeat one Tapo command, one camera preview,
   and one notification.
6. Confirm service logs contain no credential-loader, Tapo-authentication, or
   Firebase-authentication error and no credential values.

## Rollback

If validation fails, move the installed `credentials.conf` drop-in outside the
unit's `.d` directory, run `systemctl daemon-reload`, and restart KotiBot. The
unchanged `EnvironmentFile` and legacy Firebase source then remain available to
the compatibility fallback. Preserve the protected copies for diagnosis; do
not delete or rotate either source set in this checkpoint.

## Windows boundary

The shared runtime loader supports an explicit `KOTIBOT_CREDENTIALS_DIR` and
OS-native Windows credential paths. This Linux/systemd copy tool intentionally
refuses Windows writes because Windows service-account ACL provisioning and
verification require the later Windows service adapter. Do not claim Windows
credential migration complete from this checkpoint.

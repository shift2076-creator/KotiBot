# KotiBot Users (app)

The KotiBot portal on kotibot: sign-in, invitations and joining, account administration, the notification inbox, the Devices page for phone sync, and per-person vault enrollment. It runs as container `pivault-users`. Routes are in `app/urls.py`, logic in `subsystems/accounts/portal/`, and background docs in `app/docs/` (`VAULT.md`, `NOTIFICATIONS.md`).

## Deploy

Only the installer deploys this app. Build it on the deploy machine and run it:

```sh
python3 deploy/installer/build.py ~/Downloads/PiVault-Users-Install.sh
bash ~/Downloads/PiVault-Users-Install.sh
```

- It connects to `snx@192.168.4.90`, by IP only. It needs key access for that user, or it asks for the account password once and reuses it for SSH and sudo. No Docker or sudo runs on the deploy machine.
- Before any live route changes, it builds the image, runs the backend tests without network access, validates the candidate Compose and Caddy configuration, and backs up the configuration and the Users database. A failed start or failed HTTPS probe rolls back.
- It rewrites only its own marked blocks: the portal and launcher Caddy routes, the app HTTPS sites, the `pivault-users` Compose service, and the launcher script block. It does not recreate the `homepage` container.
- It installs one systemd timer and coordinator, `pivault-maintenance`, which runs nightly at 2:00 AM America/New_York. An enabled old cinema timer moves into it; a disabled one stays disabled.
- The first successful install prints a 30-minute first-Admin invitation for `snx` when no Users identity exists. Reinstalls keep existing accounts.

## Accounts and access

- Admins assign name, role and service access in the six-step Add User wizard.
- Service access: Books, Games, Videos, Photos and Radicale are Shared or No access. Music is Shared, Per user or No access. Documents is Per user or No access. Password Manager is always per person.
- Shared logins are one entry per service, held in the Admin's own Vaultwarden. Joining copies the entry into the new vault through a sealed copy. The QR code carries the key, so the typed code alone cannot complete a join that needs shared logins. Details are in `docs/VAULT.md`.
- Per-person Vaultwarden accounts use the same password as KotiBot. Key generation and encryption run in the browser. The server does not store the KotiBot password in plain text.
- Only the main KotiBot account is an administrator. Jellyfin, Navidrome and Paperless sub-accounts are never administrators.
- Invitation codes are four characters, case-insensitive, single-use, and expire after 30 minutes. They are stored as keyed digests.
- `python manage.py list_accounts` prints account names only, for each service.

## Client apps

- Each nightly run checks the official source of each client (Bitwarden Android, the Bitwarden Firefox add-on, F-Droid, AdAway, DAVx5, Jellyfin, Organic Maps and Vibrdrome) and downloads its newest stable release.
- Each download is checked for exact size, SHA-256 and archive structure, then published atomically. A failure keeps the current copy and raises a notification. An older release never replaces a newer one.
- Downloads never install on devices. Installing is a manual step. The Devices page pins which release phones sync to, and only releases approved in the Admin inbox can be pinned.
- Only hosts listed in `safe_url()` in `subsystems/accounts/portal/client_packages.py` are contacted, and only when Offline mode is off.

## Offline mode and certificate

- An Admin sets Internet jobs to Paused on the Network page (`/network`). While it is paused, the nightly job does nothing: client checks, downloads and the cinema step all pause without notices.
- The same page sets Ethernet and Wi-Fi each to Off, Internet or Local. Only one port can be Internet, and one must stay on. Saving records the choice; the Pi's network is not changed yet.
- Admins download the KotiBot root certificate from Settings, under PiVault Certificate (`/certificate`, `/certificate/ca.crt`). The page lists the steps for each browser and phone. Each device must trust it once.

## Notifications

The Admin bell holds approvals and failures: cinema file-size reviews, client update approvals and maintenance failures. Unread state is per admin, and decisions are shared. See `docs/NOTIFICATIONS.md`.

## Tests and checks

From `app/`, with a development-only secret that must never be used on kotibot:

```sh
PIVAULT_SECRET_KEY=dev-only-test-key PIVAULT_DATA=/tmp/pv-data python manage.py test portal
python manage.py check
python manage.py makemigrations --check --dry-run
```

From the repository root:

```sh
python -m unittest discover -s installer -p 'test*.py'
python -m unittest discover -s tools/check -p 'test*.py'
python tools/vault_compat.py /absolute/path/to/official/bw.js
```

- Python 3.12 or later. The installer tests need PyYAML. Some of them take a lock under `/run/lock/`, so they need root.
- `vault_compat.py` also needs Node and OpenSSL. It runs the official Bitwarden CLI against an isolated local HTTPS fixture with TLS verification on. Fixture credentials are test-only.

## Secrets

Integration secrets live in root-managed files on pivault, outside the application image. Never commit or paste them.

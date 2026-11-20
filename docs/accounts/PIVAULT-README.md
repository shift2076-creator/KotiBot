# KotiBot Server (repo name still PiVault)

An offline services hub on a Raspberry Pi 5 (kotibot): media, knowledge, organization and password management behind one HTTPS portal.

## Rules

- Offline by default. Normal operation makes no outbound connections.
- Online sync runs only in the nightly maintenance job, only when Offline mode is off, and only to hosts on the allowlist in `subsystems/accounts/portal/client_packages.py` (`safe_url()`): GitHub, Mozilla, F-Droid and archive.org (the nightly cinema round).
- Adding an outbound host needs an allowlist entry there and an update to the project instructions.
- Address kotibot by IP only (`192.168.4.90`). Hostnames appear only in the sync allowlist.
- Never fetch at runtime from CDNs, package registries or install scripts.
- Do not delete or untrack `subsystems/jobs/cinema/rights-evidence/archive-metadata/`. `cinema-rights.py` reads it.

## Layout

| Folder | What it is | Where it runs |
|---|---|---|
| `app/` | The portal: sign-in, joining, invitations, vault enrollment, notifications (Django). See `docs/accounts/README.md`. | Container `pivault-users` on kotibot |
| `deploy/stack/` | The container stack around the app: reference `docker-compose.yml`, Homepage add-on, launcher stylesheet and favicons. See `deploy/stack/homepage/README.md`. | Docker Compose on kotibot |
| `jobs/` | Scheduled scripts: `maintenance.py` (nightly 02:00) and `cinema/` (candidate resolver, transfers, rights records) | systemd on kotibot |
| `installer/` | Builds the one-file installer and installs `app/` onto kotibot | Built on the deploy machine, runs on kotibot |
| `tools/` | Read-only integration check, Bitwarden compatibility check, favicon block generator, and `network_plan.py` (pure planner for network port roles; runs nothing) | Any machine with a checkout |

## Entry points

- `app/manage.py`: Django commands, including `migrate`, `test portal`, `first_admin`, `list_accounts` and `offline_mode`.
- `app/settings.py`: portal settings. `app/urls.py`: every portal route.
- `subsystems/accounts/portal/`: views and logic, with `integrations/`, `static/portal/` (browser scripts and the shared `pivault.css`), `templates/` (`base.html` is the shell every page extends), `tests/`, `management/commands/` and `migrations/`. Background docs are in `app/docs/`, including `PORTAL-UI.md` for the page shell.
- `deploy/installer/build.py` produces `PiVault-Users-Install.sh`. `deploy/installer/install.py` is what that installer runs on kotibot.
- `subsystems/jobs/maintenance.py` is installed to `/srv/pi-server/users/maintenance.py`. `subsystems/jobs/cinema/PiVault-Cinema.sh` is installed to `/home/snx/pi-services/cinema/`.

## Live paths on kotibot

The repository is not deployed as a folder. The installer copies what it needs:

- Portal image: built from `app/`, run as container `pivault-users`.
- Compose file: `/home/snx/pi-services/docker-compose.yml`. Some services there are managed by hand, and the installer rewrites only its own. `deploy/stack/docker-compose.yml` is a reference copy and can differ by a line.
- Configuration and data: `/srv/pi-server/config/` (root-owned).

## Tests

Network planner: `python3 -m unittest test_network_plan` from `tools/`. Other commands are in `docs/accounts/README.md` (portal, installer and checker suites) and `deploy/stack/homepage/README.md` (launcher assets).

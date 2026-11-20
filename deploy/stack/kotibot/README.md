# KotiBot service

KotiBot (smart-home dashboard, `github.com/shift2076-creator/KotiBot`) runs as the `kotibot` container in the PiVault Compose stack. Caddy serves it at `https://192.168.4.90:8449` like the other apps, and the launcher has an admin-only **KotiBot** tile.

| File | Purpose |
|---|---|
| `Dockerfile` | Builds the image from one pinned KotiBot commit (`KOTIBOT_REF`). |

## How it is wired

- **Host network.** The container uses the Pi's network so Matter and Tapo discovery (mDNS and other LAN multicast) can see the devices. It listens only on the Docker bridge gateway (`172.18.0.1:5000`, set by `KOTIBOT_LISTEN`), and Caddy proxies to that address, as it does for Radicale. If the Compose network is recreated, read the gateway again (`claude/PiVault Cheat Sheet.md` §3) and update `KOTIBOT_LISTEN` and the Caddy site together.
- **Origin.** KotiBot accepts only the exact HTTPS origin in `KOTIBOT_ALLOWED_ORIGINS` (`https://192.168.4.90:8449`) and trusts forwarded headers only from `KOTIBOT_TRUSTED_PROXY_CIDRS` (`172.18.0.0/16`, the Compose bridge).
- **Hardening.** Non-root user (1000:1000), read-only root filesystem, all capabilities dropped, `no-new-privileges`. Source is root-owned under `/opt/kotibot`. State is under `/data`, credentials under `/credentials`, and `/cache` and `/run/kotibot` are tmpfs.
- **Bluetooth.** The image has `bluetoothctl` (the `bluez` package) and the Compose file mounts the host D-Bus socket `/run/dbus/system_bus_socket`, so KotiBot talks to the Pi's own `bluetoothd`. The host's D-Bus policy (`/etc/dbus-1/system.d/bluetooth.conf`) allows any user to reach `org.bluez`, so uid 1000 needs no group. The image's `bluez` (Debian 13) is newer than the host's (5.66, Debian 12); not verified together on pivault yet. The socket is a door to the whole system bus, so it widens what a compromised container can reach.
- **Not included.** Sound output (PulseAudio socket) is not mounted. Add it only when a feature needs it, and say so here.

## Build

On pivault, from a checkout of this repository. The image tag is the first 12 characters of the commit:

```
sudo docker build -t pivault-kotibot:3048de61b9d9 --build-arg KOTIBOT_REF=3048de61b9d95f511d0c9a8918f5269e9adbc308 deploy/stack/kotibot
```

The build clones KotiBot from GitHub and fails if the checked-out commit differs from `KOTIBOT_REF`. To update KotiBot, change `KOTIBOT_REF` here, the tag in `deploy/stack/docker-compose.yml`, and the command above together.

`requests` is installed on top of KotiBot's pins, because KotiBot imports it but its `requirements.txt` does not list it. A clean install of KotiBot 0.8 stops at start-up with an `ImportError` without it.

## Home shelves

**Continue watching (Jellyfin).** KotiBot signs in to Jellyfin as one non-administrator account, reads that account's resume list and shows it on the Home page. Jellyfin API keys are admin-level, so none is used. The account is the shared Jellyfin login, so the shelf shows its watch history.

- The container reaches Jellyfin at `KOTIBOT_JELLYFIN_URL` (`http://172.18.0.1:8096`). Jellyfin publishes `172.18.0.1:8096` on the Compose bridge gateway only, the way Radicale does, so the port is not open on the LAN. Caddy keeps serving `https://192.168.4.90:8096`.
- Credentials are two single-line files in `/srv/pi-server/config/kotibot/credentials/` (mode 600, owner 1000): `jellyfin-username` and `jellyfin-password`. Create them with hidden prompts, never on a command line:

  ```
  D=/srv/pi-server/config/kotibot/credentials
  read -rp 'Jellyfin user: ' U; printf '%s\n' "$U" | sudo sh -c "umask 077; cat > $D/jellyfin-username"; unset U
  read -rsp 'Jellyfin password: ' P; echo; printf '%s\n' "$P" | sudo sh -c "umask 077; cat > $D/jellyfin-password"; unset P
  sudo chown 1000:1000 $D/jellyfin-username $D/jellyfin-password
  sudo ls -l $D/jellyfin-username $D/jellyfin-password
  ```

- If the URL is unset, a credential is missing or Jellyfin is down, the row stays hidden. Check with `sudo docker logs --tail 20 kotibot | grep -i jellyfin`.

## Settings tools and navbar links (added 2026-11-18)

These replace the PiVault launcher tiles. Every link is built in the browser as `https://<current host>[:port]/<path>`, opens in a new tab and makes no request from the dashboard. They work on the LAN only: from `https://kotibot.app` they point at `kotibot.app:<port>`, which the tunnel does not serve. KotiBot has no admin role, so every signed-in user sees every link. The PiVault portal still asks for an admin sign-in on its admin pages.

- Settings (the navbar's System button), section Tools: Add User `/users/add`, Password Manager `:8448`, Portainer `:9443`, Radicale `:5232`.
- Navbar, under Sensors: Documents `:8085`, Photos `:8446`. After a spacer: Arcade `:8000`, Library `:8083`, Jukebox `/music/`, Theater `:8096`. After a spacer: Wiki `:8084`. After a spacer: System.
- Source: `DASHBOARD_PIVAULT_TOOLS`, `DASHBOARD_ASIDE_SERVICES_TOP`, `DASHBOARD_ASIDE_SERVICES_ENTERTAINMENT` and `DASHBOARD_ASIDE_SERVICES_WIKI` in `static/js/dashboard-render.js` (KotiBot repo). Tests: `tests/dashboard/interface/test_settings_pivault_tools.py` and `test_aside_service_links.py`.
- Icons: `file-lines`, `image`, `book`, `calendar-days` and `globe` are Font Awesome Free 6.7.2 solid icons (CC BY 4.0), registered in `static/css/kotibot-icons.css`.
- Host rule (KotiBot `d4c6fcb`): the apps and portal pages are served by Caddy under `192.168.4.90` only. When KotiBot is opened as `https://kotibot.lan`, these links therefore use the IP (`DASHBOARD_PIVAULT_HOST` in `dashboard-render.js`, applied to any host ending in `.lan`); any other host is used as it is. Before that fix, every link here was dead from `kotibot.lan` (owner report, 2026-11-18 21:51).
- PiVault Certificate (added 2026-11-18, KotiBot `a245671`): a Settings row that opens a window with the root certificate's SHA-256 fingerprint, a download and trust steps per device. It replaces the old Tools link to the portal's `/certificate` page. The installer copies the public root certificate (never the key) to `/srv/pi-server/config/kotibot/pki/pivault-root.crt`, and the compose file mounts that folder read-only at `/opt/pivault-pki` (`KOTIBOT_PIVAULT_ROOT_CERT`). Without the file the window says the certificate is not available yet. Run the installer first, then swap the image.
- Network (KotiBot `46620fa`): a Settings row that opens a window for the two port roles and the Internet jobs switch. It replaces the portal's `/network` page and the old Tools link. The values are one JSON file, `/srv/pi-server/config/site/site-settings.json`, mounted at `/site` in both KotiBot (`KOTIBOT_SITE_SETTINGS`) and the portal (`PIVAULT_SITE_SETTINGS`), so the nightly jobs that ask the portal about offline mode read what is set here. The installer creates the folder before it recreates the portal. Saving records the choice only; it does not change the Pi's network. Values saved on the old portal page are not carried over: the file starts at the defaults (Ethernet off, Wi-Fi internet, jobs running), so check the window once after deploying.
- Admin notifications and Android devices (KotiBot `78bd1c6`): two more Settings rows. They replace the portal's `/notifications` bell page and `/devices` page. KotiBot keeps its own small database in `/data/pivault-admin` and its own verified client downloads in `/data/pivault-clients`. The shared outbox folder `/srv/pi-server/config/notifications` is mounted at `/notifications`; KotiBot is now the only reader of its `inbox/` and writes cinema approvals to `decisions/`. The portal's `notify()` now writes to that same outbox instead of its own database, so users-flow notices appear in KotiBot too. The 2:00 AM job runs both the portal's client check (the portal still serves vault users' downloads) and `python -m subsystems.pivault_admin.maintain` in the kotibot container. The sync buttons need the helper running on the computer the phone is plugged into; the dashboard's page policy allows the browser to call `http://127.0.0.1:8765` for that. Old portal notification history and registered devices are not carried over: phones re-register on their next sync. Nothing creates `clients.update` approvals any more, so they are not ported.
- Not checked: the navbar clips what does not fit (`.dashboard-aside` has `overflow: hidden`), so on a short or landscape phone screen the lower links may be cut off.

## First run (fresh state)

The Pi 5 starts with no KotiBot data. Run on pivault, one step at a time:

1. Create the folders. The service user is uid 1000, and KotiBot requires private (700) state folders and credential files no more open than 640:

   ```
   sudo install -d -m 700 -o 1000 -g 1000 /srv/pi-server/config/kotibot /srv/pi-server/config/kotibot/data /srv/pi-server/config/kotibot/credentials /srv/pi-server/config/kotibot/bin
   sudo install -d -m 700 -o 1000 -g 1000 /srv/pi-server/config/kotibot/data/protected /srv/pi-server/config/kotibot/data/protected/matter /srv/pi-server/config/kotibot/data/protected/matter/controller
   ```

   KotiBot refuses to start Matter without the `controller` folder, so that it never creates a replacement identity by accident.

2. Credentials, in `/srv/pi-server/config/kotibot/credentials/` (mode 600, owner 1000). Do not paste values anywhere. Names only:
   - `integration-credentials.json`: required. `{"version": 1}` is enough when no integration is used.
   - `tapo-username`, `tapo-password`, `tapo-camera-username`, `tapo-camera-password`: Tapo account and camera logins, one line each. Tapo stays off until `KOTIBOT_TAPO_ENABLED` is set (it is, in Compose).
   - `firebase-service-account.json`: push notifications.

3. `chip-tool` (Matter): put an arm64 build in `/srv/pi-server/config/kotibot/bin/chip-tool`. It is mounted read-only at `/opt/chip-tool`. The copy on the old Pi 4 is at `/home/shift2076/tools/connectedhomeip/out/linux-arm64-chip-tool/chip-tool`. The Dockerfile installs the libraries that build needs (checked with `ldd` on the Pi 4, 2026-11-17). Matter attestation stays on (KotiBot's default). Only if adding a device fails with an attestation error, set `KOTIBOT_MATTER_BYPASS_ATTESTATION: 'true'` in the Compose environment, knowing it skips the genuine-device check. Test the binary with `sudo docker exec kotibot /opt/chip-tool/chip-tool --help`.

4. Start it: `cd /home/snx/pi-services && sudo docker compose -p pi-services up -d kotibot`.

5. Create the dashboard login with your real email address (the example one would become your username). KotiBot prompts for the password, so run this interactively. `PYTHONPATH` is needed because KotiBot's own README command fails with `No module named 'server_core'` when run this way:

   ```
   sudo docker exec -it -e PYTHONPATH=/opt/kotibot kotibot python subsystems/security/kotibot_security.py set-dashboard-login you@example.com
   ```

## Names and external access

**Inside the LAN: `https://kotibot.lan`.** The installer writes a Caddy site for the name on port 443, with a certificate from the same local CA as the IP address sites. The name has to resolve to 192.168.4.90 on your network. Caddy does not do that: add the record in your router or Pi-hole (or rename the Pi, once no other machine on the LAN has that hostname). `https://192.168.4.90:8449` keeps working.

**From outside: `https://kotibot.app` through a Cloudflare Tunnel.** Only KotiBot is reachable this way. No router ports are opened and the other PiVault apps stay LAN-only. The `cloudflared` service in `deploy/stack/docker-compose.yml` makes an outbound connection to Cloudflare. It is not started by the installer, and the live Compose file gets it by hand once the token file below exists, because Compose refuses to run while an `env_file` is missing.

1. In Cloudflare Zero Trust, open Networks, Tunnels and create a **new** tunnel for pivault (do not add a second connector to the old one: two connectors on one tunnel share its hostnames and would split traffic between machines). Copy the connector token: the long string that starts `eyJ…` (in the `docker run … --token` line Cloudflare shows), not the tunnel ID. Never paste it into a chat, a command line or a file in this repository.
2. Store the token on pivault with a hidden prompt, readable by root only:

   ```
   read -rsp 'Tunnel token: ' T; echo; printf 'TUNNEL_TOKEN=%s\n' "$T" | sudo sh -c 'umask 077; cat > /srv/pi-server/config/kotibot/cloudflared.env'; unset T
   sudo ls -l /srv/pi-server/config/kotibot/cloudflared.env
   ```

   Expect mode `-rw-------` and owner `root`.
3. Add the `cloudflared` service from `deploy/stack/docker-compose.yml` to the live Compose file, then `cd /home/snx/pi-services && sudo docker compose -p pi-services up -d --no-deps cloudflared`. After any later change to the token file add `--force-recreate`, because the container reads the file only when it is created. Check `sudo docker logs --tail 20 kotibot-cloudflared` for a registered tunnel connection.
4. In the new tunnel's Public hostnames, add `kotibot.app` and `www.kotibot.app`, type HTTP, URL `172.18.0.1:5000` (the same Compose gateway address KotiBot listens on). Do this before the DNS cut-over: until the tunnel has published hostnames, Cloudflare answers error 1033 for the name.
5. Cut over. The two DNS records for `kotibot.app` and `www.kotibot.app` still point at the old tunnel. Repoint them to the new tunnel, then check the site from outside the LAN (a phone on mobile data). To revert, point the records back at the old tunnel. Stop the old `cloudflared` only after that works.

KotiBot accepts `https://kotibot.app` and `https://www.kotibot.app` as origins (`KOTIBOT_ALLOWED_ORIGINS`), and trusts forwarded headers from the Compose bridge (`172.18.0.0/16`), which covers the `cloudflared` container. The first request through the tunnel is the real test of that: it was not tried here.

The `cloudflared` tag is pinned to `2026.7.3`. A newer release (2026.8.1) exists on GitHub, and the Docker Hub tag list could not be read from the workspace. Check that the pinned tag pulls on pivault before relying on it.

## Checks

```
sudo docker ps --filter name=kotibot --format '{{.Names}} | {{.Status}}'
sudo docker logs --tail 30 kotibot
curl -sk -o /dev/null -w 'kotibot %{http_code}\n' https://192.168.4.90:8449/login
```

Expect the container running, `Serving on http://172.18.0.1:5000` in the log, and `401` for the login page address without a session.

## Smoke test (2026-11-17, not on pivault)

On a Debian-based workspace without Docker, the same environment variables and `waitress-serve --threads=12 wsgi:application` were run from a clean virtual environment at `08dede8d8782`. The server reached "Serving" after `requests`, `integration-credentials.json` and the Matter `controller` folder were provided. The image itself was not built, because the workspace has no Docker daemon. Build and run it on pivault before relying on it.

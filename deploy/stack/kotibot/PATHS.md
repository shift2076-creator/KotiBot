# kotibot.lan paths

`https://kotibot.lan/<path>` is the machine's front door. Caddy (`deploy/installer/configuration.py`, `KOTIBOT_LAN_BODY`) maps
each path to whatever app currently provides that role.

**A path names a role, not a product.** `/theater` is the video service today and may be a self-built one later. The
address, bookmarks and launcher tile stay the same when the app behind it changes.

**Rule for self-built services:** read one base-path setting (for example `KOTIBOT_BASE_PATH`) and build every link,
asset URL and API call from it. Never hard-code a leading `/api` or `/static`. KotiBot itself does not do this yet
(about 230 hard-coded addresses), which is why `/smarthome` redirects for now.

| Path | Role | Today | Prefix setting | Status |
|---|---|---|---|---|
| `/wiki` | Offline reference | Kiwix | `--urlRootLocation=/wiki` (compose command) | stage 1 |
| `/library` | Books | Calibre-Web | `X-Script-Name: /library` header, set by Caddy | stage 1 |
| `/smarthome` | Smart home | KotiBot | none needed: KotiBot is the root of the name; `/smarthome` redirects to `/` | done |
| `/jukebox` | Music | Navidrome | `ND_BASEURL` (today `/music`) | planned |
| `/theater` | Video | Jellyfin | Base URL setting | planned |
| `/photos` | Photos | Lychee | `APP_DIR=/photos` (compose); Caddy strips the prefix (`handle_path`) | stage 2 |
| `/documents` | Documents | Paperless | `PAPERLESS_FORCE_SCRIPT_NAME` | planned |
| `/arcade` | Games | RetroAssembly | not checked | planned |
| `/portainer` | Docker admin | Portainer | `--base-url` and prefix stripping (container must be recreated) | planned, last |

Every app keeps its own port address while it moves. An app told to live under a path answers at its port only if
Caddy sends it there with the prefix, so each port site redirects its root to the path. Phone and desktop clients that
point at a port address keep working through that redirect, unless they need a fixed server URL (Jellyfin and
Subsonic-type music apps do) and then they are re-pointed.

`https://kotibot.lan/` is KotiBot's home page. The old PiVault launcher is retired from this name. The portal pages
(`/users`, `/network`, `/devices`, `/certificate`) stay on `https://192.168.4.90/`.
Names need one DNS entry: `kotibot.lan` to `192.168.4.90`.

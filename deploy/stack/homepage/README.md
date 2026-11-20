# Launcher (Homepage) assets

The PiVault launcher is Homepage v2.6.0 with two files added:

| File | Served as | Installed by |
|---|---|---|
| `custom.css` | `/api/config/custom.css` | Copied to pivault by hand. The installer does not write it. |
| `homepage-addon.js` | Merged into `custom.js` between the `BEGIN PIVAULT` and `END PIVAULT` markers | The installer (`deploy/installer/configuration.py`, `homepage_js`) |

The device copies live in `/srv/pi-server/config/homepage/` on pivault, which Homepage reads as `/app/config`. `services.yaml`, `settings.yaml` and `widgets.yaml` are device data and are not in this repository.

## Layout

- Every rule is scoped to `body:has(#pivault-books)`, so nothing else on the page changes.
- Title: an `h1#pv-title` created by the script, with the keyhole mark as its `::before`. Text is 34px, semibold, in the accent colour, centred. It matches the brand row on the portal pages (`subsystems/accounts/portal/static/portal/pivault.css`, `.pv-brand`).
- Four sections, one per grid row: Entertainment, Knowledge, Organization and Tools. Each row is placed by the id on one tile in the device `services.yaml`: `pivault-books`, `pivault-documents`, `pivault-radicale` and `pivault-password-manager`. The `pivault-books` id also scopes the whole stylesheet. Each section heading is shown. A section with no visible tile is hidden with its heading.
- Columns: 4 wide, 2 at 1199px and below, 1 at 767px and below. The gap is one third of `--pv-column-gap`.
- Tiles: the panel is always visible. Hovering removes its shadow and darkens its top edge. Every ancestor of the list has `overflow: visible`, so shadows are never clipped.
- Width: the title, search, list and toolbar share a 1200px maximum. The admin bell sits in the toolbar. The Settings gear was removed because the Tools tiles repeat its links.
- Admin-only tiles (Add User, PiVault Certificate, Network, Android devices, Radicale, Portainer and KotiBot) are hidden for other users by `deploy/stack/homepage-addon.js` (`ADMIN_TILES`). The hiding uses the `hidden` attribute, which the stylesheet makes win over Homepage's own display classes. Each name must match the tile's `name:` in the device `services.yaml` exactly, or that tile is shown to everyone. Change the two together.
- There is no Settings menu. The toolbar holds only the admin bell. Offline mode lives on the Network page.

## Icons

`deploy/stack/homepage/favicon/` holds the source and the rasters. All of them use the circle design:

- `favicon.svg`: the 16px circle and keyhole. Browsers that accept SVG use it at every size.
- `favicon-16.png`, `favicon-32.png`: rendered from the SVG, transparent outside the circle.
- `favicon.ico`: 16, 32 and 48px frames.
- `apple-touch-icon.png`: 180px, on an opaque `#151c22` square because iOS shows transparent corners as black.

After changing any of these, run `python3 tools/favicon_block.py` from the repository root. It rewrites the `FAVICON` block in `homepage-addon.js`. The installer test `test_favicon_block_matches_its_files` fails when that block is stale.

The portal serves `/favicon.ico`, `/apple-touch-icon.png` and `/manifest.webmanifest` from `subsystems/accounts/portal/static/portal/`. The launcher's sign-in gate skips those three paths, because browsers fetch icons without cookies. The launcher script adds the manifest link to the page head.

## Tests

- `python3 -m unittest discover -s installer -p 'test_homepage_assets.py'`: static checks of the stylesheet and script. Behaviour in a live Homepage must be checked on the device.
- `node --check deploy/stack/homepage-addon.js`.
- The full installer suite, which includes the `custom.js` merge tests: `python3 -m unittest discover -s installer -p 'test*.py'`.

## Deploying

- Stylesheet only: check the file's SHA-256, copy it to pivault, back up the live file to `/srv/pi-server/backups/homepage/`, install it with `sudo install -m 644` into `/srv/pi-server/config/homepage/`, then restart `pivault-homepage`.
- `services.yaml` and `settings.yaml` are device data, not in this repository. Their layout (sections, tile names and tile ids) is set on the device. Back them up to `/srv/pi-server/backups/<stamp>/`, install them with `sudo install -m 644` into `/srv/pi-server/config/homepage/`, then restart `pivault-homepage`.
- `custom.js` (script or favicon changes): the installer deploys it. Run the installer from `main`.
- The installer does not recreate `homepage`. After a change to its environment, such as `HOMEPAGE_ALLOWED_HOSTS`, recreate it on pivault with `sudo docker compose -p pi-services up -d --no-deps --force-recreate homepage` from `/home/snx/pi-services`.

## Retirement (started 2026-11-18)

The launcher is being replaced by KotiBot's home page at `https://kotibot.lan/`. State so far:

- The Tools tiles Add User, Password Manager, PiVault Certificate, Network, Portainer and Android devices moved to KotiBot (Settings, Tools). On pivault the Tools group of `services.yaml` was replaced by one KotiBot tile (owner report, 2026-11-18 20:48). That tile carries `id: pivault-password-manager`, because the stylesheet places the Tools row by that id. Rename the id and the `custom.css` rule together.
- Documents, Photos, Arcade, Library, Jukebox, Theater and Wiki are now links in KotiBot's navbar. Radicale is in KotiBot's Settings, Tools. Their launcher tiles had not been removed when this was written.
- `kotibot.lan` serves KotiBot at its root from `51e4690` (`deploy/installer/configuration.py`, `KOTIBOT_LAN_BODY`). It reaches the Pi only after an installer run.
- Not done: redirecting `https://192.168.4.90/` to `https://kotibot.lan/`, stopping the `homepage` container and dropping the launcher sign-in gate in Caddy. The portal pages (`/users`, `/network`, `/devices`, `/certificate`, `/music`) stay on the IP address.
- `ADMIN_TILES` in `homepage-addon.js` still names the tiles that were removed. That is harmless while the launcher exists.

## Lessons

- Homepage draws a group's heading even when all its tiles are hidden. Hide the heading in CSS. Hide tiles rather than removing them: the tile ids that place each row must stay in `services.yaml`.
- A `clip-path` on a pseudo-element clips its box-shadow. Remove it instead of trying to contain the shadow.
- After an edit, read the whole file again. A stale rule later in the file overrides the new one.
- Homepage's group panel has `overflow-hidden`. Shadows at a tile's edge are clipped unless the panel and each wrapper above the tiles are set to `overflow: visible`.

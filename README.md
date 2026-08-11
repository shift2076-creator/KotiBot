# KotiBot

**A self-hosted smart-home dashboard, automation platform, and home-control system designed to run efficiently on Raspberry Pi-class single-board computers, with full Linux and Windows host support on the roadmap.**

> **Alpha software — KotiBot 0.8**
>
> KotiBot is under active development. Interfaces, configuration formats, and device behavior may change between releases. It is not yet recommended for unattended, security-critical, or production use.

KotiBot brings smart-home devices and services into one responsive web interface, with local device control, Matter integration, Tapo support, Android clients, cameras, sensors, scenes, automations, environmental monitoring, notifications, activity history, and configurable home-security actions.

The project is designed around self-hosting and local control rather than requiring a hosted KotiBot cloud service.

## What KotiBot Does

KotiBot provides a unified dashboard for controlling and monitoring a mixed smart-home environment.

### Dashboard and device control

* Responsive web interface for desktop, tablet, and mobile use
* Zone-based device organization
* Lighting, plugs, switches, sensors, cameras, and other device types
* Favorites and hidden-device management
* Live device state and status
* Per-device configuration
* Activity history

### Tapo integration

KotiBot integrates with TP-Link Tapo devices using local Python libraries and device APIs.

Current integration includes support for device classes such as:

* Smart bulbs and lighting
* Smart plugs
* Power strips and outlet extenders
* Switches
* Sensors
* Hubs
* Cameras

Actual feature availability depends on the capabilities exposed by each device model and the underlying Tapo libraries.

### Matter

KotiBot includes Matter controller integration through `chip-tool`.

Current Matter functionality includes discovery and interaction with capabilities such as:

* On/off devices
* Temperature sensors
* Humidity sensors
* Contact sensors
* Occupancy and motion sensors
* Buttons and switches
* Battery state

> **Compatibility note:** Tapo devices are currently the only devices that have been tested against KotiBot's Matter integration. Matter devices from other manufacturers have not yet been validated and may fail or behave unpredictably.
>
> Reports from users testing other Matter hardware are welcome.

### Android clients

KotiBot supports Android clients that can provide capabilities such as:

* Camera feeds
* Door-state sensing
* Motion sensing
* Device telemetry
* Key/presence functionality
* Push-notification targets

Android clients communicate with the KotiBot server and are represented alongside other household devices in the dashboard.

### Scenes and automations

KotiBot supports reusable household states and event-driven automation.

Current functionality includes:

* Lighting scenes
* Device automations
* Sensor-triggered actions
* Timers and post-trigger behavior
* Device power actions
* Notifications
* Sound playback
* Camera recording actions
* Security-mode-aware actions

### Security modes and actions

KotiBot includes configurable home-security modes and actions.

Current modes include household states such as:

* At Home
* Asleep
* Away

Security actions can react to door, motion, occupancy, environmental, and other supported device events.

**KotiBot is not currently a certified alarm system and should not be treated as a replacement for professionally rated life-safety or security equipment.**

### Cameras and media

KotiBot supports Android and Tapo camera workflows, including live viewing and recording.

Tapo RTSP camera streaming and recording use an installed FFmpeg executable.

Camera credentials are handled separately from normal device state and should never be committed to the repository.

### Environmental monitoring

KotiBot combines indoor sensor measurements with external environmental information for a household-level environmental view.

Supported data includes temperature, humidity, weather, and air-quality information where configured and available.

## Current Status

KotiBot is currently in the **0.8 development line**.

Development is focused on stabilizing the secured application, completing secure configuration storage, establishing platform-native Linux and Windows operation, preserving strong Raspberry Pi-class efficiency, improving first-run setup, expanding camera support, strengthening Tapo integration, adding customizable modes, and broadening Matter hardware testing.

See:

* [`KotiBot_Fixes_Stability_Roadmap.md`](docs/roadmaps/KotiBot_Fixes_Stability_Roadmap.md)
* [`KotiBot_Fixes_Stability_Checklist.md`](docs/roadmaps/KotiBot_Fixes_Stability_Checklist.md)
* [`KotiBot_Implementations_Updates_Roadmap.md`](docs/roadmaps/KotiBot_Implementations_Updates_Roadmap.md)
* [`KotiBot_Implementations_Updates_Checklist.md`](docs/roadmaps/KotiBot_Implementations_Updates_Checklist.md)

for the separated stability and implementation plans and their progress.

## Compatibility

| Component                     | Status                                                 |
| ----------------------------- | ------------------------------------------------------ |
| Raspberry Pi / Linux host     | Current primary platform and SBC efficiency target     |
| Other Linux hosts             | Roadmap validation target; support matrix not complete |
| Windows host                  | Roadmap target; not yet supported                      |
| Python 3.11+                  | Required                                               |
| Tapo local-device integration | Supported and actively developed                       |
| Tapo Matter devices           | Tested                                                 |
| Non-Tapo Matter devices       | Experimental / not yet validated                       |
| Android home clients          | Supported                                              |
| Android key/presence clients  | Supported                                              |
| Tapo cameras                  | Supported with model/capability limitations            |
| FFmpeg camera processing      | Optional, required for applicable Tapo camera features |
| Bluetooth / BlueZ             | Required only for Bluetooth functionality              |

KotiBot is currently developed and validated primarily on Raspberry Pi/Linux. The roadmap now requires native Linux and Windows paths, service control, permissions/ACLs, installation, upgrade, rollback, and feature verification before broader platform support is declared complete. Raspberry Pi-class hardware remains a first-class resource and responsiveness target rather than a reduced-function edition.

## Runtime Requirements

### Required

The current 0.8 runtime requires Linux. Windows support is planned but is not yet an installation option.

* Linux on the current release line
* Python **3.11 or newer**
* `pip`
* Python virtual environment support
* Network access to the smart-home devices KotiBot will control

Python dependencies are defined in [`requirements.txt`](requirements.txt).

Current direct dependencies include:

| Package     | Version |
| ----------- | ------: |
| Flask       |   3.1.3 |
| Werkzeug    |   3.1.8 |
| Waitress    |   3.0.2 |
| python-kasa |  0.10.2 |
| tapo        |   0.9.0 |
| Pillow      |  12.3.0 |
| google-auth |  2.56.2 |

### Feature-dependent system software

Some KotiBot subsystems require external software that is not installed by `pip`.

* **Matter:** `chip-tool` must be installed and available in `PATH`, or its path must be provided with `KOTIBOT_MATTER_CHIP_TOOL`.
* **Tapo camera streaming/recording:** FFmpeg must be installed.
* **Bluetooth:** BlueZ / `bluetoothctl` must be available when Bluetooth functionality is used.

## Installation

KotiBot does not yet include its planned first-run setup wizard. Installation currently requires some manual Linux configuration. Windows installation and service procedures will be documented only after their roadmap validation gates pass.

Clone the repository:

```bash
git clone https://github.com/shift2076-creator/KotiBot.git
cd KotiBot
```

Create a Python virtual environment:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
```

Install the Python dependencies:

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## HTTPS and Origin Configuration

The secured KotiBot dashboard requires an explicitly configured HTTPS origin.

Set the exact public/browser-facing dashboard origin before starting KotiBot:

```bash
export KOTIBOT_ALLOWED_ORIGINS="https://kotibot.example.com"
```

Multiple allowed origins may be supplied as a comma-separated list when required.

The browser-facing installation must use HTTPS. KotiBot's application server can listen on local HTTP behind a trusted HTTPS reverse proxy, but the authenticated dashboard itself is designed around secure browser cookies and exact-origin validation.

If KotiBot is behind a trusted reverse proxy, configure the trusted proxy network deliberately rather than trusting arbitrary forwarded headers:

```bash
export KOTIBOT_TRUSTED_PROXY_CIDRS="127.0.0.1/32"
```

Use the actual proxy network appropriate for your installation.

## Create the Dashboard Login

Before normal dashboard use, initialize the dashboard account.

With `KOTIBOT_ALLOWED_ORIGINS` configured:

```bash
python subsystems/security/kotibot_security.py set-dashboard-login you@example.com
```

KotiBot prompts for the password without placing it in the shell command line.

Additional dashboard-user management commands are available through the same security utility.

## Tapo Configuration

Tapo integration uses environment-provided credentials.

Relevant variables currently include:

```text
TAPO_USERNAME
TAPO_PASSWORD
TAPO_CAMERA_USERNAME
TAPO_CAMERA_PASSWORD
TAPO_CAMERA_RTSP_PATH
KOTIBOT_TAPO_ENABLED
```

Do **not** commit actual credentials to the repository.

The project is actively migrating remaining secret-bearing configuration toward a stricter secure-storage model. See the development roadmap for the current security-configuration milestone.

## Matter Configuration

By default KotiBot looks for `chip-tool` in `PATH`.

A custom executable can be selected with:

```bash
export KOTIBOT_MATTER_CHIP_TOOL="/path/to/chip-tool"
```

Matter controller storage contains sensitive operational and enrollment state and must not be committed or exposed through the web server.

KotiBot also contains a laboratory-only attestation-bypass option for development. It should remain disabled during normal use.

## Running KotiBot

### Development process

The Flask development process can be started with:

```bash
python kotibot_server.py
```

The application process listens on port `5000` by default.

Because the authenticated dashboard requires HTTPS, normal browser access should still be provided through the configured HTTPS frontend/reverse proxy.

### Waitress

For a persistent deployment, use [`wsgi.py`](wsgi.py) with Waitress rather than Flask's development server.

For example:

```bash
waitress-serve --listen=127.0.0.1:5000 wsgi:application
```

`wsgi.py` runs KotiBot's runtime dependency preflight before importing and initializing the server.

A systemd service and HTTPS reverse proxy are recommended for a persistent Raspberry Pi/Linux installation. The cross-platform roadmap requires an equivalent supported Windows service and secure configuration path before Windows support is declared complete.

## Repository Layout

```text
KotiBot/
├── LICENSE                   GNU GPL v3 project license
├── README.md                 Project documentation
├── requirements.txt          Direct Python runtime dependencies
├── kotibot_server.py         Main application bootstrap
├── wsgi.py                   WSGI deployment entry point
├── docs/
│   └── roadmaps/             Paired stability and implementation roadmaps/checklists
├── licenses/
│   └── THIRD_PARTY_NOTICES.md
├── server_core/              Shared server/runtime infrastructure
│   ├── preflight.py          Installed dependency validation
│   └── ...
├── subsystems/               KotiBot feature subsystems
│   ├── activities/
│   ├── automations/
│   ├── bluetooth/
│   ├── client-android-home/
│   ├── client-android-key/
│   ├── client-tapo/
│   ├── environment/
│   ├── matter/
│   ├── notifications/
│   ├── security/
│   ├── soundboard/
│   ├── video/
│   └── ...
├── static/                   Dashboard CSS, JavaScript, images, and icons
├── templates/                Flask HTML templates
└── tests/                    Automated tests
```

Runtime state, credentials, recordings, virtual environments, caches, and other local/private files are intentionally excluded from version control.

## Security

KotiBot's security model includes:

* Authenticated dashboard sessions
* HttpOnly secure session cookies
* Strict browser-origin validation
* Trusted-proxy network validation
* Password hashing
* Login rate limiting
* Per-device authentication keys
* HMAC-authenticated device requests
* Replay protection using timestamps and nonces
* Device enrollment tokens
* Security audit logging
* Private runtime-state handling
* Strict Content Security Policy work

KotiBot is still alpha software. Security-sensitive changes are being actively audited and hardened before the 0.9 release gate.

Never include passwords, API tokens, private keys, device enrollment credentials, camera credentials, security state, or unredacted diagnostic archives in public issues.

## Data and Privacy

KotiBot is intended to be self-hosted.

Camera recordings, device state, security state, Matter controller data, credentials, and household activity can be highly sensitive. Administrators are responsible for protecting the host system, backups, reverse proxy, filesystem permissions, and network access.

Generated recordings and live runtime state are intentionally excluded from this source repository.

## Contributing

KotiBot is under active development, and compatibility reports, bug reports, testing, and code contributions are welcome.

When reporting a device issue, include the manufacturer, model number, connection method, relevant KotiBot version or commit, and a description of the expected and observed behavior.

Do not include passwords, tokens, private keys, setup codes, unredacted configuration files, or other credentials.

For non-Tapo Matter hardware in particular, compatibility reports are valuable because cross-vendor Matter validation is still planned work.

## Development Roadmap

The current roadmap moves KotiBot through:

1. secured-application stabilization
2. secure credential/configuration storage
3. native Linux and Windows platform foundations with Raspberry Pi-class performance targets
4. action-based Security System Actions summaries before setup-wizard implementation
5. universal configurable popup feedback
6. first-run setup
7. expanded camera support
8. Tapo zone integration
9. customizable lighting and security modes
10. expanded environmental features and non-Tapo Matter validation
11. the KotiBot 0.9 release audit

See the paired Fixes/Stability and Implementations/Updates roadmap documents for detailed acceptance criteria and their working checklists for current progress.

## Third-Party Software and Assets

KotiBot depends on open-source software distributed under several GPL-compatible licenses. Direct dependencies, bundled browser software, and locally stored icon artwork are documented in [`licenses/THIRD_PARTY_NOTICES.md`](licenses/THIRD_PARTY_NOTICES.md).

The HLS.js and Font Awesome license files remain beside the assets they cover.

Matter, TP-Link, Tapo, Android, Google, Font Awesome, and other third-party product names and marks belong to their respective owners. Their use describes compatibility or integration and does not imply sponsorship or endorsement.

## License

KotiBot is licensed under the [GNU General Public License v3.0](LICENSE).

Third-party software and assets remain subject to their respective licenses.

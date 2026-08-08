# KotiBot

> ⚠️ **Alpha software.** KotiBot is under daily early development. Expect rough edges. It is not yet recommended for unattended, security-critical, or production use.

KotiBot is a self-hosted smart-home dashboard and automation platform designed for Raspberry Pi.

It brings Matter devices, Tapo lighting and plugs, Android home and key clients, cameras, sensors, environmental monitoring, scenes, security actions, notifications, and household automations together in a single responsive web interface.

## Device Compatibility

**Tapo devices are the only devices that have been tested against the Matter integration.** Non-Tapo Matter devices from other manufacturers have never been tested and are expected to fail or behave unpredictably. If you try KotiBot with a non-Tapo Matter device, please open an issue with the details — reports are welcome, but nothing outside Tapo is currently verified to work.

## Components

- Flask and Waitress server
- Matter device integration
- Tapo bulbs, plugs, switches, extenders, cameras, and sensors
- Android camera, door-sensor, motion, and key-presence clients
- Lighting scenes and device automations
- Home security modes and actions
- Indoor and outdoor environmental monitoring
- Activity history, notifications, video, voice, and soundboard support

## Requirements

- Raspberry Pi (or any Linux host) running Python 3
- Dependencies (see `requirements.txt`):
  - Flask 3.1.3, Werkzeug 3.1.8
  - waitress 3.0.2
  - python-kasa 0.10.2, tapo 0.9.0
  - Pillow 12.3.0
  - google-auth 2.56.2

## Getting Started

```bash
pip install -r requirements.txt
python server.py
```

By default the dev server listens on `0.0.0.0:5000`. For a production-style deployment, use `wsgi.py` with Waitress instead of running `server.py` directly.

## Roadmap

See [`KotiBot_Roadmap_2026-08-06.md`](KotiBot_Roadmap_2026-08-06.md) and [`KotiBot_Roadmap_Checklist.md`](KotiBot_Roadmap_Checklist.md) for planned work and current progress.

## License

## License

This project is licensed under the [GNU General Public License v3.0](LICENSE).
# Third-Party Software and Assets

This document inventories the direct runtime dependencies and bundled third-party assets used by KotiBot. It does not replace the license text or notices supplied by each project.

KotiBot itself is licensed under the [GNU General Public License v3.0](../LICENSE).

## Python runtime dependencies

The versions below match the direct pins in [`requirements.txt`](../requirements.txt).

| Component | Version | Declared license | Project metadata |
| --- | ---: | --- | --- |
| Flask | 3.1.3 | BSD-3-Clause | [PyPI](https://pypi.org/project/Flask/3.1.3/) |
| Werkzeug | 3.1.8 | BSD-3-Clause | [PyPI](https://pypi.org/project/Werkzeug/3.1.8/) |
| Waitress | 3.0.2 | Zope Public License 2.1 | [PyPI](https://pypi.org/project/waitress/3.0.2/) |
| python-kasa | 0.10.2 | GPL-3.0-or-later | [PyPI](https://pypi.org/project/python-kasa/0.10.2/) |
| tapo | 0.9.0 | MIT | [PyPI](https://pypi.org/project/tapo/0.9.0/) |
| Pillow | 12.3.0 | MIT-CMU | [PyPI](https://pypi.org/project/Pillow/12.3.0/) |
| google-auth | 2.56.2 | Apache-2.0 | [PyPI](https://pypi.org/project/google-auth/2.56.2/) |

These packages may install transitive dependencies with their own license terms. Installed distributions retain their own license metadata and notices.

## Bundled browser software and artwork

- **HLS.js 1.6.17** is distributed under the Apache License 2.0. Its bundled notice is stored at [`subsystems/client-tapo/static/vendor/hls.js-1.6.17.LICENSE`](../subsystems/client-tapo/static/vendor/hls.js-1.6.17.LICENSE).
- **Font Awesome Free 6.7.2 icon artwork** is distributed under CC BY 4.0. The local attribution and license note is stored at [`static/img/dashboard-icons/LICENSE-FONT-AWESOME-FREE.txt`](../static/img/dashboard-icons/LICENSE-FONT-AWESOME-FREE.txt).

## External system software

KotiBot can call FFmpeg, BlueZ utilities, and Matter `chip-tool` when the corresponding features are enabled. These tools are installed separately and are not bundled in this repository. Their applicable licenses depend on the packages or builds installed on the host system.

Third-party product names and trademarks are used only to identify compatibility or integration. Their use does not imply sponsorship or endorsement.
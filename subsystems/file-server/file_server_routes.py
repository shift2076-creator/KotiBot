from pathlib import Path
import re
from urllib.parse import quote

from flask import jsonify, send_from_directory


def register_file_server_routes(app, ctx):
    apk_dir = Path(ctx['android_package_dir'])

    def apk_files():
        return sorted(
            [path for path in apk_dir.glob('*.apk') if path.is_file()],
            key=lambda path: path.name.lower(),
        )

    def normalized_apk_stem(path):
        return re.sub(r'[^a-z0-9]+', '-', path.stem.lower()).strip('-')

    def apk_kind(path):
        stem = normalized_apk_stem(path)

        if stem.startswith('kotibot-home'):
            return 'home'

        if stem.startswith('kotibot-key'):
            return 'key'

        return ''

    def apk_version_tuple(path, kind):
        prefix = f'kotibot-{kind}'
        stem = normalized_apk_stem(path)

        if not stem.startswith(prefix):
            return ()

        suffix = stem[len(prefix):].strip('-')
        version = []

        for part in suffix.split('-'):
            if part.isdigit():
                version.append(int(part))
            elif version:
                break

        return tuple(version)

    def find_apk_file(kind):
        candidates = [
            path for path in apk_files()
            if apk_kind(path) == kind
        ]

        if not candidates:
            return None

        return sorted(
            candidates,
            key=lambda path: (apk_version_tuple(path, kind), path.stat().st_mtime, path.name.lower()),
            reverse=True,
        )[0]

    def apk_download_url(path):
        return f"/file-server/get-app/{quote(path.name)}"

    def send_apk(kind, label):
        apk_path = find_apk_file(kind)

        if not apk_path:
            return jsonify({'ok': False, 'error': f'{label} APK not found'}), 404

        return send_from_directory(apk_path.parent, apk_path.name, as_attachment=True)

    @app.route('/file-server/get-app/<path:filename>')
    def get_app_file(filename):
        requested = Path(str(filename or '')).name
        apk_path = apk_dir / requested

        if not requested or not apk_path.is_file() or apk_kind(apk_path) not in ('home', 'key'):
            return jsonify({'ok': False, 'error': 'APK not found'}), 404

        return send_from_directory(apk_dir, apk_path.name, as_attachment=True)

    @app.route('/get-app')
    @app.route('/get-home-client-app')
    def get_home_client_app():
        return send_apk('home', 'Home Client')

    @app.route('/get-key-client-app')
    def get_key_client_app():
        return send_apk('key', 'Key Client')

    @app.route('/api/file-server/apks')
    def api_file_server_apks():
        files = []

        for path in apk_files():
            kind = apk_kind(path)

            if not kind:
                continue

            files.append({
                'filename': path.name,
                'size': path.stat().st_size,
                'modified': path.stat().st_mtime,
                'kind': kind,
                'version': '.'.join(str(part) for part in apk_version_tuple(path, kind)),
                'url': apk_download_url(path),
            })

        return jsonify({'ok': True, 'files': files})
from pathlib import Path
import re
from urllib.parse import quote

from flask import jsonify, send_from_directory


APK_PREFIXES = {
    'home': ('kotibot-monitor', 'kotibot-home'),
    'key': ('kotibot-control', 'kotibot-key'),
}


def register_file_server_routes(app, ctx):
    apk_dirs = {
        'home': Path(ctx['monitor_apk_dir']),
        'key': Path(ctx['controller_apk_dir']),
    }

    def apk_files():
        return sorted(
            [
                path
                for directory in apk_dirs.values()
                for path in directory.glob('*.apk')
                if path.is_file()
            ],
            key=lambda path: path.name.lower(),
        )

    def normalized_apk_stem(path):
        return re.sub(
            r'[^a-z0-9]+',
            '-',
            path.stem.lower(),
        ).strip('-')

    def apk_prefix(path, kind):
        stem = normalized_apk_stem(path)

        for prefix in APK_PREFIXES.get(kind, ()):
            if stem.startswith(prefix):
                return prefix

        return ''

    def apk_kind(path):
        for kind, directory in apk_dirs.items():
            if path.parent == directory and apk_prefix(path, kind):
                return kind

        return ''

    def apk_version_tuple(path, kind):
        prefix = apk_prefix(path, kind)

        if not prefix:
            return ()

        stem = normalized_apk_stem(path)
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
            key=lambda path: (
                apk_version_tuple(path, kind),
                path.stat().st_mtime,
                path.name.lower(),
            ),
            reverse=True,
        )[0]

    def apk_download_url(path):
        return f"/file-server/get-app/{quote(path.name)}"

    def send_apk(kind, label):
        apk_path = find_apk_file(kind)

        if not apk_path:
            return jsonify({
                'ok': False,
                'error': f'{label} APK not found',
            }), 404

        return send_from_directory(
            apk_path.parent,
            apk_path.name,
            as_attachment=True,
        )

    @app.route('/file-server/get-app/<path:filename>')
    def get_app_file(filename):
        requested = Path(str(filename or '')).name
        matches = [
            path for path in apk_files()
            if path.name == requested and apk_kind(path)
        ]

        if not requested or len(matches) != 1:
            return jsonify({
                'ok': False,
                'error': 'APK not found',
            }), 404

        apk_path = matches[0]

        return send_from_directory(
            apk_path.parent,
            apk_path.name,
            as_attachment=True,
        )

    @app.route('/get-app')
    @app.route('/get-home-client-app')
    def get_home_client_app():
        return send_apk('home', 'Monitor')

    @app.route('/get-key-client-app')
    def get_key_client_app():
        return send_apk('key', 'Control')

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
                'version': '.'.join(
                    str(part)
                    for part in apk_version_tuple(path, kind)
                ),
                'url': apk_download_url(path),
            })

        return jsonify({'ok': True, 'files': files})
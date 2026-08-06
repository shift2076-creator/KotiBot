from flask import g, jsonify, request


PUBLIC_LOGIN_ASSETS = {
    '/static/img/KotiBot.svg',
}

PUBLIC_LOGIN_ASSET_PREFIXES = (
    '/static/img/favicons/',
)

ENROLLMENT_PATHS = {
    '/handshake',
    '/api/handshake',
    '/client-handshake',
}

DEVICE_SIGNED_PATHS = {
    '/telemetry',
    '/upload_frame',
    '/upload_video',
    '/api/key-notifications',
    '/api/notifications/fcm-token',
}

DEVICE_SIGNED_PREFIXES = (
    '/api/camera-talk/client/',
    '/api/voice/client/',
)

UNSAFE_METHODS = {'POST', 'PUT', 'PATCH', 'DELETE'}

LOGIN_BODY_LIMIT = 16 * 1024
JSON_BODY_LIMIT = 1024 * 1024
FRAME_BODY_LIMIT = 8 * 1024 * 1024
VIDEO_BODY_LIMIT = 64 * 1024 * 1024


def normalized_method(method):
    method = str(method or '').upper()
    return 'GET' if method == 'HEAD' else method


def request_policy(method, path):
    method = normalized_method(method)
    path = str(path or '')

    if method == 'GET' and path == '/':
        # GET / is a server-side dispatcher. It renders either login.html or
        # index.html after checking the dashboard session.
        return 'public'

    if method == 'POST' and path == '/login':
        return 'public'

    if method == 'GET' and (
        path in PUBLIC_LOGIN_ASSETS
        or any(path.startswith(prefix) for prefix in PUBLIC_LOGIN_ASSET_PREFIXES)
    ):
        return 'public'

    if method == 'POST' and path in ENROLLMENT_PATHS:
        return 'enrollment'

    if (
        path in DEVICE_SIGNED_PATHS
        or any(path.startswith(prefix) for prefix in DEVICE_SIGNED_PREFIXES)
    ):
        return 'device'

    # Every route not explicitly identified above is authenticated dashboard
    # traffic. New routes therefore fail closed without another allowlist edit.
    return 'dashboard'


def request_body_limit(path):
    if path == '/login':
        return LOGIN_BODY_LIMIT

    if path == '/upload_frame':
        return FRAME_BODY_LIMIT

    if path == '/upload_video':
        return VIDEO_BODY_LIMIT

    if request.is_json:
        return JSON_BODY_LIMIT

    return 0


def validate_security_routes(app):
    seen = set()

    for rule in app.url_map.iter_rules():
        for method in rule.methods - {'HEAD', 'OPTIONS'}:
            key = (rule.rule, method)

            if key in seen:
                raise RuntimeError(
                    f'Duplicate Flask route registration: {method} {rule.rule}'
                )

            seen.add(key)

    if ('/', 'POST') in seen:
        raise RuntimeError(
            'POST / must not be a device-handshake alias'
        )

    required = {
        ('/', 'GET'),
        ('/login', 'POST'),
        ('/api/status', 'GET'),
        ('/api/status/stream', 'GET'),
        ('/upload_video', 'POST'),
        ('/api/automation-routes', 'GET'),
        ('/api/notifications/fcm-token', 'POST'),
    }

    missing = required - seen
    if missing:
        formatted = ', '.join(
            f'{method} {path}' for path, method in sorted(missing)
        )
        raise RuntimeError(f'Missing expected security-audited routes: {formatted}')

    app.config['KOTIBOT_ROUTE_SECURITY_POLICY'] = {
        f'{method} {path}': request_policy(method, path)
        for path, method in sorted(seen)
    }


def register_security_routes(app, context):
    security = context['security']

    @app.before_request
    def security_gate():
        limit = request_body_limit(request.path)

        if limit:
            # Flask 3.1 enforces this while the handler reads the stream,
            # including requests without a trustworthy Content-Length.
            request.max_content_length = limit

        content_length = request.content_length

        if (
            limit
            and content_length is not None
            and content_length > limit
        ):
            return jsonify({
                'ok': False,
                'error': 'request_too_large',
            }), 413

        policy = request_policy(request.method, request.path)

        if policy == 'public':
            if request.method in UNSAFE_METHODS:
                return security.require_same_origin()

            return None

        if policy == 'enrollment':
            return None

        if policy == 'device':
            deviceID = str(
                request.headers.get('X-Device-ID') or ''
            ).strip()

            if not deviceID:
                return jsonify({
                    'ok': False,
                    'error': 'missing_deviceID',
                }), 400

            if request.is_json:
                data = request.get_json(silent=True) or {}
                body_deviceID = str(
                    data.get('deviceID')
                    or data.get('deviceId')
                    or ''
                ).strip()

                if body_deviceID and body_deviceID != deviceID:
                    return jsonify({
                        'ok': False,
                        'error': 'device_identity_mismatch',
                    }), 403

            blocked = security.require_device_signature(deviceID)
            if blocked:
                return blocked

            # Signed handlers can consume the identity established by the
            # security boundary rather than trusting another body field.
            g.kotibot_device_id = deviceID
            return None

        blocked = security.require_dashboard()
        if blocked:
            return blocked

        if request.method in UNSAFE_METHODS:
            return security.require_same_origin()

        return None

    return {
        'security_gate': security_gate,
    }

from flask import jsonify, request

DASHBOARD_PROTECTED_EXACT = {
    '/get-app',
    '/video_feed',
    '/api/status',
    '/api/status/stream',
    '/api/system-arm',
    '/api/tapo/status',
    '/api/tapo/enable',
    '/api/tapo/disable',
    '/api/activities/recent',
    '/api/wavs',
    '/api/test-sound',
    '/api/restart-server',
    '/api/routes',
    '/api/tapo/detect',
    '/api/tapo/client-command',
    '/api/provision-client',
    '/provision',
    '/api/recalibrate',
    '/api/remove-client',
    '/api/client-command',
    '/api/preview-viewer',
}

DASHBOARD_PROTECTED_PREFIXES = (
    '/video_feed/',
    '/api/tapo/',
    '/api/matter/',
    '/api/environment/',
    '/api/file-server/',
    '/file-server/get-app/',
    '/api/video-file/',
    '/api/automations',
)

DEVICE_SIGNED_PATHS = {
    '/',
    '/handshake',
    '/api/handshake',
    '/client-handshake',
    '/telemetry',
    '/upload_frame',
    '/api/key-notifications',
}


def register_security_routes(app, context):
    security = context['security']
    state_lock = context['state_lock']
    clients = context['clients']
    client_role_key = context['client_role_key']
    client_has_role = context['client_has_role']

    @app.route('/api/security/keyclient-session', methods=['POST'])
    def security_keyclient_session():
        data = request.get_json(silent=True) or {}
        deviceID = str(data.get('deviceID') or request.headers.get('X-Device-ID') or '').strip()

        if not deviceID:
            return jsonify({'ok': False, 'error': 'missing_deviceID'}), 400

        blocked = security.require_device_signature(deviceID)
        if blocked:
            return blocked

        with state_lock:
            c = clients.get(deviceID)
            allowed = bool(
                c
                and c.get('provisioned')
                and client_has_role(c, client_role_key)
            )

        if not allowed:
            return security.error('keyclient_required', 403)

        response = jsonify({
            'ok': True,
            'dashboardSession': True
        })
        security.set_dashboard_cookie(response)
        
        return response

    @app.before_request
    def security_gate():
        if request.path.startswith('/static/'):
            return None

        if request.path.startswith('/subsystems/') and '/static/' in request.path:
            return None

        if request.path.startswith('/api/security/'):
            return None

        if request.method == 'POST' and request.path in DEVICE_SIGNED_PATHS:
            if request.path in ('/', '/handshake', '/api/handshake', '/client-handshake'):
                return None

            data = request.get_json(silent=True) or {}
            deviceID = data.get('deviceID') or request.headers.get('X-Device-ID')

            if not deviceID:
                return None

            with state_lock:
                existing = clients.get(deviceID)
                provisioned = bool(existing and existing.get('provisioned'))

            if provisioned:
                blocked = security.require_device_signature(deviceID)
                if blocked:
                    return blocked

            return None

        if request.path.startswith('/api/camera-talk/client/') or request.path.startswith('/api/voice/client/'):
            data = request.get_json(silent=True) or {}
            deviceID = data.get('deviceID') or request.headers.get('X-Device-ID')

            if not deviceID:
                return jsonify({'ok': False, 'error': 'missing_deviceID'}), 400

            return security.require_device_signature(deviceID)

        if request.path.startswith('/api/camera-talk/') or request.path.startswith('/api/voice/'):
            return security.require_dashboard()

        if (
            request.path in DASHBOARD_PROTECTED_EXACT
            or any(request.path.startswith(prefix) for prefix in DASHBOARD_PROTECTED_PREFIXES)
        ):
            return security.require_dashboard()

        return None

    return {
        'security_gate': security_gate,
    }

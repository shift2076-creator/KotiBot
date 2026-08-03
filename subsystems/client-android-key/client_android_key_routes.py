from flask import request, jsonify


def register_android_key_routes(app, ctx):
    app.config['KOTIBOT_ANDROID_KEY_CONTEXT'] = ctx

    state_lock = ctx['state_lock']
    clients = ctx['clients']
    client_role_key = ctx['client_role_key']
    client_has_role = ctx['client_has_role']
    safe_int = ctx['safe_int']
    push_queue = ctx['push_queue']

    @app.route('/api/key-notifications', methods=['POST'])
    def api_key_notifications():
        d = request.get_json(silent=True) or {}
        deviceID = str(d.get('deviceID') or request.headers.get('X-Device-ID') or '').strip()
        since_ts = safe_int(d.get('sinceTs', d.get('since_ts', 0))) or 0

        if not deviceID:
            return jsonify({'ok': False, 'error': 'Missing deviceID'}), 400

        with state_lock:
            c = clients.get(deviceID)
            if not c or not client_has_role(c, client_role_key):
                return jsonify({'ok': False, 'error': 'Key client not found'}), 404

        items = []
        for index, item in enumerate(push_queue.recent(200)):
            if item.get('deviceID') != deviceID:
                continue

            ts = safe_int(item.get('ts')) or 0
            if ts <= since_ts:
                continue

            item_id = f"{ts}:{index}:{item.get('event_type', '')}:{item.get('title', '')}:{item.get('body', '')}"

            items.append({
                'id': item_id,
                'ts': ts,
                'event_type': item.get('event_type', ''),
                'title': item.get('title', ''),
                'body': item.get('body', ''),
                'data': item.get('data', {})
            })

        items = items[-20:]

        return jsonify({'ok': True, 'notifications': items})
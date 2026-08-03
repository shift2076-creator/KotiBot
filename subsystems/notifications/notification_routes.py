from flask import jsonify, request


def register_notification_routes(app, context):
    state_lock = context['state_lock']
    clients = context['clients']
    push_queue = context['push_queue']
    now_epoch = context['now_epoch']
    save_state = context['save_state']

    def request_device_id(data):
        return str(data.get('deviceID') or request.headers.get('X-Device-ID') or '').strip()

    @app.post('/api/notifications/fcm-token')
    def api_notifications_fcm_token():
        data = request.get_json(silent=True) or {}
        deviceID = request_device_id(data)
        token = str(data.get('token') or data.get('fcmToken') or data.get('fcm_token') or '').strip()

        if not deviceID:
            return jsonify({'ok': False, 'error': 'missing_deviceID'}), 400

        if not token:
            return jsonify({'ok': False, 'error': 'missing_fcm_token'}), 400

        with state_lock:
            c = clients.get(deviceID)

            if not c:
                return jsonify({'ok': False, 'error': 'client_not_found'}), 404

            c['fcm_token'] = token
            c['fcm_token_at'] = now_epoch()
            save_state()

        return jsonify({'ok': True})

    @app.get('/api/notifications/recent')
    def api_notifications_recent():
        try:
            limit = int(request.args.get('limit', 50) or 50)
        except Exception:
            limit = 50

        limit = max(1, min(200, limit))
        return jsonify({'ok': True, 'items': push_queue.recent(limit)})

    @app.post('/api/notifications/test-fcm')
    def api_notifications_test_fcm():
        data = request.get_json(silent=True) or {}
        deviceID = request_device_id(data)

        if not deviceID:
            return jsonify({'ok': False, 'error': 'missing_deviceID'}), 400

        with state_lock:
            c = clients.get(deviceID)
            token = str((c or {}).get('fcm_token') or '').strip()

        if not token:
            return jsonify({'ok': False, 'error': 'missing_fcm_token'}), 409

        item = push_queue.enqueue_data(
            event_type='fcm_test',
            deviceID=deviceID,
            fcm_token=token,
            data={
                'type': 'fcm_test',
                'action_type': 'FCM_TEST',
                'deviceID': deviceID,
                'message': str(data.get('message') or 'KotiBot FCM test'),
                'sentAt': str(int(now_epoch() * 1000)),
            },
        )

        return jsonify({'ok': True, 'queued': item})
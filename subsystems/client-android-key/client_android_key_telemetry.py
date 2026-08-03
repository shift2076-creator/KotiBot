def register_android_key_telemetry(context):
    safe_int = context['safe_int']
    now_epoch = context['now_epoch']

    def key_string_value(data, *keys):
        for key in keys:
            value = data.get(key)

            if value is not None:
                return str(value or '').strip()

        return ''

    def handle_key_telemetry(c, data):
        changed = False

        fcm_token = key_string_value(data, 'fcmToken', 'fcm_token')

        if fcm_token and fcm_token != c.get('fcm_token'):
            c['fcm_token'] = fcm_token
            c['fcm_token_at'] = now_epoch()
            changed = True

        heartbeat_interval_ms = safe_int(
            data.get(
                'heartbeatIntervalMs',
                data.get('heartbeat_interval_ms', c.get('heartbeat_interval_ms', 30000))
            )
        ) or 30000

        if heartbeat_interval_ms != c.get('heartbeat_interval_ms'):
            c['heartbeat_interval_ms'] = heartbeat_interval_ms
            changed = True

        return changed

    return {
        'handle_key_telemetry': handle_key_telemetry,
    }
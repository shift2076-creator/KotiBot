from flask import request, jsonify, Response


def register_android_home_routes(app, ctx):
    app.config['KOTIBOT_ANDROID_HOME_CONTEXT'] = ctx

    state_lock = ctx['state_lock']
    client_role_cam = ctx['client_role_cam']
    client_role_dss = ctx['client_role_dss']
    client_role_key = ctx['client_role_key']
    client_has_role = ctx['client_has_role']
    get_clients_for_device = ctx['get_clients_for_device']
    normalize_client_roles = ctx['normalize_client_roles']
    apply_enabled_roles = ctx['apply_enabled_roles']
    cancel_motion_recording_stop = ctx['cancel_motion_recording_stop']
    queue_door_recalibration = ctx['queue_door_recalibration']
    cancel_door_sound_repeat = ctx.get('cancel_door_sound_repeat', lambda deviceID: None)
    save_state = ctx['save_state']
    broadcast_state = ctx['broadcast_state']
    clean_zone_name = ctx['clean_zone_name']
    safe_int = ctx['safe_int']
    safe_float = ctx['safe_float']
    now_epoch = ctx['now_epoch']
    system_armed = ctx.get('system_armed', lambda: False)
    push_queue = ctx['push_queue']
    preview_requested_for_client = ctx['preview_requested_for_client']

    def android_battery_value_from_data(data, fallback=None):
        raw = data.get(
            'battery',
            data.get(
                'batteryPct',
                data.get(
                    'batteryPercent',
                    data.get(
                        'batteryPercentage',
                        data.get(
                            'battery_level',
                            data.get('batteryLevel', fallback)
                        )
                    )
                )
            )
        )

        if isinstance(raw, str):
            raw = raw.strip().rstrip('%')

        battery = safe_int(raw)

        if battery is None or battery < 0:
            return fallback

        return max(0, min(100, battery))

    def system_armed_value():
        return bool(system_armed() if callable(system_armed) else system_armed)

    def apply_seen_client(c, data, path='', inc_type=''):
        changed = False

        c['ip'] = request.headers.get('X-Forwarded-For', request.remote_addr or '')
        c['last_seen'] = now_epoch()
        c['heartbeat_pending'] = False
        c['heartbeat_requested_at'] = 0
        c['needs_heartbeat'] = False

        battery = android_battery_value_from_data(data, c.get('battery'))

        if battery != c.get('battery'):
            c['battery'] = battery
            changed = True

        c['armed'] = 1 if system_armed_value() else 0
        c['telemetry_count'] = c.get('telemetry_count', 0) + 1

        deviceID = c.get('deviceID')
        clients = get_clients_for_device(deviceID)
        targets = [c]
        unp_client = next((x for x in clients if not x.get('provisioned')), None)

        if unp_client and unp_client is not c:
            targets.append(unp_client)

        for target in targets:
            if target is not c:
                target_battery = android_battery_value_from_data(data, target.get('battery'))

                if target_battery != target.get('battery'):
                    target['battery'] = target_battery
                    changed = True

            if 'version' in data:
                target['version'] = str(data['version'] or '')

            if 'brand' in data:
                target['brand'] = str(data['brand'])

            if 'androidVersion' in data:
                target['androidVersion'] = str(data['androidVersion'])

        return changed

    app.config['KOTIBOT_ANDROID_HOME_BATTERY_VALUE'] = android_battery_value_from_data
    app.config['KOTIBOT_ANDROID_HOME_APPLY_SEEN_CLIENT'] = apply_seen_client

    @app.route('/video_feed/<deviceID>')
    def video_feed(deviceID):
        with state_lock:
            clients = get_clients_for_device(deviceID)
            c = next((x for x in clients if client_has_role(x, client_role_cam)), None)

            if not c or not c.get('frame'):
                return "No feed", 404

            frame = c['frame']

        return Response(frame, mimetype='image/jpeg')

    @app.route('/api/preview-viewer', methods=['POST'])
    def api_preview_viewer():
        d = request.get_json(silent=True) or {}
        deviceID = d.get('deviceID')
        viewer_id = d.get('viewerId')
        active = bool(d.get('active', True))

        if not deviceID or not viewer_id:
            return jsonify({'error': 'Missing deviceID or viewerId'}), 400

        with state_lock:
            clients = get_clients_for_device(deviceID)
            c = next((x for x in clients if client_has_role(x, client_role_cam)), None)

            if not c:
                return jsonify({'error': 'Camera not found'}), 404

            viewers = c.setdefault('preview_viewers', {})
            was_requested = preview_requested_for_client(c)
            had_viewer = viewer_id in viewers

            if active:
                viewers[viewer_id] = now_epoch()
            else:
                viewers.pop(viewer_id, None)

            has_viewer = viewer_id in viewers
            is_requested = preview_requested_for_client(c)
            c['preview_requested'] = is_requested

            viewer_changed = had_viewer != has_viewer
            requested_changed = was_requested != is_requested
            viewer_count = len(viewers)
            fcm_token = str(c.get('fcm_token') or '').strip()

            should_notify_camera = (
                active
                and has_viewer
                and viewer_changed
            ) or (
                requested_changed
                and not is_requested
            )

            if requested_changed:
                broadcast_state()

        if should_notify_camera:
            if fcm_token:
                push_queue.enqueue_data(
                    event_type='preview_request',
                    deviceID=deviceID,
                    fcm_token=fcm_token,
                    data={
                        'type': 'preview_request',
                        'action_type': 'PREVIEW_REQUEST',
                        'deviceID': deviceID,
                        'previewRequested': '1' if is_requested else '0',
                        'sentAt': str(int(now_epoch() * 1000)),
                    },
                )

        return jsonify({
            'ok': True,
            'previewRequested': is_requested,
            'changed': requested_changed,
            'viewerChanged': viewer_changed,
            'viewerCount': viewer_count,
        })
    
    @app.route('/api/recalibrate', methods=['POST'])
    def recalibrate():
        d = request.get_json() or {}
        deviceID = d.get('deviceID')
        if not deviceID:
            return jsonify({'error': 'Missing deviceID'}), 400

        with state_lock:
            clients = get_clients_for_device(deviceID)
            door_client = next((x for x in clients if client_has_role(x, client_role_dss)), None)

            if not door_client:
                return jsonify({'error': 'Door client not found'}), 404

            cancel_door_sound_repeat(door_client.get('deviceID'))
            recal_seq = queue_door_recalibration(door_client)

            save_state()
            broadcast_state()

        return jsonify({'ok': True, 'recalibrateSeq': recal_seq})
    
    @app.route('/api/client-command', methods=['POST'])
    def client_command():
        d = request.get_json() or {}
        deviceID = d.get('deviceID')
        if not deviceID:
            return jsonify({'error': 'Missing deviceID'}), 400

        requested_roles = normalize_client_roles(d.get('clientRole'))
        requested_role = requested_roles[0] if requested_roles else None

        with state_lock:
            clients = get_clients_for_device(deviceID)

            android_clients = [
                c
                for c in clients
                if isinstance(c, dict)
                and c.get('provisioned')
                and str(c.get('source') or '').strip().lower()
                not in {'tapo', 'matter'}
                and (
                    client_has_role(c, client_role_cam)
                    or client_has_role(c, client_role_dss)
                    or client_has_role(c, client_role_key)
                )
            ]

            if requested_role:
                targets = [
                    c
                    for c in android_clients
                    if client_has_role(c, requested_role)
                ]
            else:
                targets = android_clients

            if not targets:
                return jsonify({
                    'ok': False,
                    'error': 'Android client not found'
                }), 404

            if 'enabledRoles' in d or 'enabled_roles' in d:
                requested_enabled_roles = d.get('enabledRoles', d.get('enabled_roles'))

                for c in clients:
                    ok, error = apply_enabled_roles(c, requested_enabled_roles)
                    if not ok:
                        return jsonify({'ok': False, 'error': error}), 400

                save_state()
                return jsonify({'ok': True})

            for c in targets:
                pending = c.setdefault('pending_command', {})

                if 'recordingEnabled' in d:
                    c['recording_enabled'] = bool(int(d.get('recordingEnabled') or 0))
                    c['motion_recording_active'] = False
                    cancel_motion_recording_stop(c.get('deviceID'))
                    pending['recordingEnabled'] = 1 if c['recording_enabled'] else 0

                if 'motionDetectionEnabled' in d or 'motion_detection_enabled' in d:
                    motion_enabled = bool(int(d.get('motionDetectionEnabled', d.get('motion_detection_enabled', 0)) or 0))
                    c['motion_detection_enabled'] = motion_enabled
                    pending['motionDetectionEnabled'] = 1 if motion_enabled else 0
                    pending['motion_detection_enabled'] = 1 if motion_enabled else 0

                    if not motion_enabled:
                        cancel_motion_recording_stop(c.get('deviceID'))
                        c['motion_active'] = False

                        if c.get('motion_recording_active'):
                            c['motion_recording_active'] = False
                            c['recording_enabled'] = False
                            pending['recordingEnabled'] = 0

                if 'motionDetectionThreshold' in d or 'motion_detection_threshold' in d:
                    threshold = safe_float(d.get('motionDetectionThreshold', d.get('motion_detection_threshold', 18.0)))
                    if threshold is None:
                        threshold = 18.0
                    threshold = max(1.0, min(100.0, threshold))
                    c['motion_detection_threshold'] = threshold
                    pending['motionDetectionThreshold'] = threshold
                    pending['motion_detection_threshold'] = threshold

                if 'motionFlashlightEnabled' in d or 'motion_flashlight_enabled' in d:
                    c['motion_flashlight_enabled'] = bool(int(d.get('motionFlashlightEnabled', d.get('motion_flashlight_enabled', 0)) or 0))
                    pending['motionFlashlightEnabled'] = 1 if c.get('motion_flashlight_enabled') else 0
                    pending['motion_flashlight_enabled'] = 1 if c.get('motion_flashlight_enabled') else 0

                if 'motionScreenEnabled' in d or 'motion_screen_enabled' in d:
                    c['motion_screen_enabled'] = bool(int(d.get('motionScreenEnabled', d.get('motion_screen_enabled', 0)) or 0))
                    pending['motionScreenEnabled'] = 1 if c.get('motion_screen_enabled') else 0
                    pending['motion_screen_enabled'] = 1 if c.get('motion_screen_enabled') else 0

                if 'selectedCamera' in d or 'selected_camera' in d:
                    selected = str(d.get('selectedCamera') or d.get('selected_camera') or 'back').lower()
                    if selected not in ('front', 'back'):
                        selected = 'back'
                    c['selected_camera'] = selected
                    c['camera_auto_rotation'] = None
                    c['camera_auto_rotation_at'] = 0
                    c['camera_auto_rotation_lens'] = ''
                    pending['selectedCamera'] = selected
                    pending['selected_camera'] = selected

                if 'previewAspect' in d or 'preview_aspect' in d:
                    aspect = str(d.get('previewAspect') or d.get('preview_aspect') or '16:9')
                    selected = c.get('selected_camera', 'back')
                    c.setdefault('preview_by_lens', {}).setdefault(selected, {})['aspect_ratio'] = aspect
                    pending['previewAspect'] = aspect

                if 'newName' in d or 'clientName' in d:
                    name = str(d.get('newName') or d.get('clientName') or '').strip()
                    if name:
                        for sibling in clients:
                            sibling['clientName'] = name
                            sibling.setdefault('pending_command', {})['clientName'] = name

                if 'zoneName' in d or 'zone_name' in d:
                    zone_name = clean_zone_name(d.get('zoneName', d.get('zone_name', '')))
                    for sibling in clients:
                        if not client_has_role(sibling, client_role_key):
                            sibling['zone_name'] = zone_name

                for k, v in d.items():
                    normalized_key = ''.join(
                        ch
                        for ch in str(k).lower()
                        if ch.isalnum()
                    )

                    if any(
                        marker in normalized_key
                        for marker in (
                            'secret',
                            'password',
                            'passwd',
                            'token',
                            'credential',
                            'privatekey',
                            'apikey',
                            'keyid',
                        )
                    ):
                        continue

                    if k not in (
                        'deviceID', 'clientRole',
                        'recordingEnabled',
                        'motionDetectionEnabled', 'motion_detection_enabled',
                        'motionDetectionThreshold', 'motion_detection_threshold',
                        'selectedCamera', 'selected_camera',
                        'previewAspect', 'preview_aspect',
                        'motionFlashlightEnabled', 'motion_flashlight_enabled',
                        'motionScreenEnabled', 'motion_screen_enabled',
                        'enabledRoles', 'enabled_roles',
                        'newName', 'clientName'
                    ):
                        pending[k] = v

            save_state()

        return jsonify({'ok': True})
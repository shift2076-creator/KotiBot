from io import BytesIO
from threading import Timer

from flask import g, jsonify, request

try:
    from PIL import Image
except ImportError:
    Image = None

def register_android_home_telemetry(app, context):
    state_lock = context['state_lock']
    client_role_cam = context['client_role_cam']
    client_role_dss = context['client_role_dss']
    client_role_key = context['client_role_key']
    client_role_tapo = context['client_role_tapo']
    client_has_role = context['client_has_role']
    normalize_client_roles = context['normalize_client_roles']
    get_unprovisioned_client = context['get_unprovisioned_client']
    get_clients_for_device = context['get_clients_for_device']
    register_seen_client = context['register_seen_client']
    snapshot_client = context['snapshot_client']
    preview_requested_for_client = context['preview_requested_for_client']
    handle_key_telemetry = context['handle_key_telemetry']
    fire_door_routes = context['fire_door_routes']
    fire_camera_motion_routes = context.get('fire_camera_motion_routes', lambda camera_client, output='motion': False)
    activity_log = context.get('activity_log')
    cancel_door_sound_repeat = context['cancel_door_sound_repeat']
    system_armed = context['system_armed']
    save_state = context['save_state']
    broadcast_state = context['broadcast_state']
    safe_int = context['safe_int']
    safe_float = context['safe_float']
    now_epoch = context['now_epoch']

    motion_recording_idle_seconds = 15.0
    motion_alert_output_seconds = 15.0
    motion_recording_stop_timers = {}
    frame_status_broadcast_interval_seconds = 0.5
    last_frame_status_broadcast_at = 0.0
    routine_telemetry_broadcast_interval_seconds = 5.0
    last_routine_telemetry_broadcast_at = 0.0
    door_recalibration_command_timeout_seconds = float(context.get('door_recalibration_command_timeout_seconds', context.get('door_recalibration_hold_seconds', 18.0)) or 18.0)
    door_recalibration_active_timeout_seconds = float(context.get('door_recalibration_active_timeout_seconds', 12.0) or 12.0)

    if Image is None:
        app.logger.warning('Motion detection unavailable: Pillow is not installed')

    def android_home_client_name(c, fallback='Device'):
        return str(
            c.get('clientName')
            or c.get('name')
            or c.get('deviceName')
            or c.get('deviceID')
            or fallback
        ).strip()

    def record_android_home_activity(c, *, kind, state, status, icon, accent, detail='', record_initial=False):
        if not activity_log or not hasattr(activity_log, 'record_state_change'):
            return None

        try:
            return activity_log.record_state_change(
                deviceID=c.get('deviceID'),
                name=android_home_client_name(c),
                kind=kind,
                state=state,
                status=status,
                icon=icon,
                accent=accent,
                source='android-home',
                detail=detail,
                category='security',
                record_initial=record_initial
            )
        except Exception:
            app.logger.exception('Android Home activity recording failed')
            return None

    def reset_android_home_activity_signature(c, kind):
        if not activity_log or not hasattr(activity_log, 'reset_state_signature'):
            return False

        try:
            return bool(activity_log.reset_state_signature(
                deviceID=c.get('deviceID'),
                kind=kind,
                source='android-home'
            ))
        except Exception:
            app.logger.exception('Android Home activity signature reset failed')
            return False
        
    def camera_surface_rotation_degrees(value):
        rotation = safe_int(value)

        if rotation is None:
            return None

        if rotation in (0, 1, 2, 3):
            return {
                0: 0,
                1: 90,
                2: 180,
                3: 270,
            }.get(rotation)

        if rotation in (0, 90, 180, 270):
            return rotation

        return None

    def valid_camera_frame(frame_bytes):
        if not frame_bytes:
            return False

        return (
            frame_bytes.startswith(b'\xff\xd8\xff')
            or frame_bytes.startswith(
                b'\x89PNG\r\n\x1a\n'
            )
            or (
                len(frame_bytes) >= 12
                and frame_bytes[:4] == b'RIFF'
                and frame_bytes[8:12] == b'WEBP'
            )
        )

    def camera_frame_motion_score(c, frame_bytes):
        if Image is None:
            return None

        try:
            with Image.open(BytesIO(frame_bytes)) as source:
                width, height = source.size

                # Reject decompression bombs before converting pixel data.
                if (
                    width <= 0
                    or height <= 0
                    or width * height > 16_000_000
                ):
                    return None

                image = source.convert('L').resize((64, 36))

            pixels = image.tobytes()
        except Exception:
            return None

        previous = c.get('motion_probe_pixels')
        c['motion_probe_pixels'] = pixels

        if not previous or len(previous) != len(pixels):
            return None

        changed = 0

        for current, old in zip(pixels, previous):
            if abs(current - old) >= 18:
                changed += 1

        return round((changed / max(1, len(pixels))) * 100.0, 3)

    def cancel_motion_recording_stop(deviceID):
        timer = motion_recording_stop_timers.pop(deviceID, None)

        if timer:
            timer.cancel()

    def _schedule_motion_recording_stop_locked(c):
        deviceID = c.get('deviceID')

        if not deviceID:
            return

        cancel_motion_recording_stop(deviceID)

        motion_at = float(c.get('last_motion_at', 0) or 0)
        timer = Timer(motion_recording_idle_seconds, _finish_motion_recording_if_idle, args=(deviceID, motion_at))
        timer.daemon = True
        motion_recording_stop_timers[deviceID] = timer
        timer.start()

    def _finish_motion_recording_if_idle(deviceID, motion_at):
        with state_lock:
            device_clients = get_clients_for_device(deviceID)
            c = next((x for x in device_clients if client_has_role(x, client_role_cam)), None)

            if not c or not c.get('motion_recording_active'):
                return

            last_motion_at = float(c.get('last_motion_at', 0) or 0)

            if last_motion_at > motion_at or now_epoch() - last_motion_at < motion_recording_idle_seconds:
                _schedule_motion_recording_stop_locked(c)
                return

            c['motion_active'] = False
            c['motion_recording_active'] = False
            c['recording_enabled'] = False
            reset_android_home_activity_signature(c, 'camera_motion')
            fire_camera_motion_routes(c, 'inactive')

            pending = c.setdefault('pending_command', {})
            pending['recordingEnabled'] = 0

            motion_recording_stop_timers.pop(deviceID, None)

            save_state()

    def handle_camera_motion_detected(c, score=None):
        if not c.get('motion_detection_enabled'):
            return False

        now = now_epoch()
        previous_motion_at = float(c.get('last_motion_at', 0) or 0)
        was_active = bool(previous_motion_at and now - previous_motion_at < motion_recording_idle_seconds)

        c['motion_active'] = True
        c['last_motion_at'] = now

        if score is not None:
            c['last_motion_score'] = round(score, 3)

        if not c.get('recording_enabled'):
            c['recording_enabled'] = True
            c['motion_recording_active'] = True
            c.setdefault('pending_command', {})['recordingEnabled'] = 1

        if c.get('motion_flashlight_enabled') or c.get('motion_screen_enabled'):
            alert_until_ms = int((now + motion_alert_output_seconds) * 1000)
            pending = c.setdefault('pending_command', {})

            if c.get('motion_flashlight_enabled'):
                pending['motionAlertFlashlightUntilMs'] = alert_until_ms

            if c.get('motion_screen_enabled'):
                pending['motionAlertScreenUntilMs'] = alert_until_ms

        if not was_active:
            detail = ''
            if c.get('last_motion_score') is not None:
                detail = f"score={c.get('last_motion_score')}"

            record_android_home_activity(
                c,
                kind='camera_motion',
                state='detected',
                status='Motion detected',
                icon='motion_sensor_active',
                accent='purple',
                detail=detail,
                record_initial=True
            )

        fire_camera_motion_routes(c, 'motion')

        _schedule_motion_recording_stop_locked(c)

        return True

    def door_recalibration_phase(c):
        return str(c.get('recalibration_phase') or '').strip().lower()

    def door_recalibration_active(c, now=None):
        if now is None:
            now = now_epoch()

        return (
            door_recalibration_phase(c) in ('requested', 'calibrating', 'settling')
            and now <= float(c.get('recalibration_ignore_until', 0) or 0)
        )

    def clear_door_recalibration_state(c):
        changed = False

        for key in ('recalibration_phase', 'recalibration_requested_at', 'recalibration_ignore_until'):
            if c.get(key) not in (None, '', 0):
                c.pop(key, None)
                changed = True

        return changed

    def force_door_closed(c, calibrating=None):
        changed = False

        if c.get('door_status') != 'closed':
            c['door_status'] = 'closed'
            changed = True

        if float(c.get('openness_score', 0.0) or 0.0) != 0.0:
            c['openness_score'] = 0.0
            changed = True

        if float(c.get('door_angle', 0.0) or 0.0) != 0.0:
            c['door_angle'] = 0.0
            changed = True

        if calibrating is not None and int(c.get('calibrating', 0) or 0) != int(calibrating):
            c['calibrating'] = int(calibrating)
            changed = True

        return changed

    def hold_door_recalibration(c, phase, now, timeout_seconds, extend_deadline=True):
        changed = False

        if c.get('recalibration_phase') != phase:
            c['recalibration_phase'] = phase
            changed = True

        if extend_deadline:
            ignore_until = now + timeout_seconds

            if float(c.get('recalibration_ignore_until', 0) or 0) < ignore_until:
                c['recalibration_ignore_until'] = ignore_until
                changed = True

        changed = force_door_closed(c, calibrating=1) or changed
        return changed

    def handle_door_telemetry(c, data):
        changed = False
        now = now_epoch()

        raw_open = (
            data.get('openDoor')
            if 'openDoor' in data
            else data.get('opendoor', data.get('open_door'))
        )

        previous = c.get('door_status', 'unknown')
        open_value = safe_int(raw_open)
        event_ms = safe_int(data.get('eventTimeMs', data.get('event_time_ms')))

        if event_ms is not None:
            last_event_ms = safe_int(c.get('door_event_ms')) or 0

            if event_ms < last_event_ms:
                return changed

            if event_ms != last_event_ms:
                c['door_event_ms'] = event_ms
                changed = True

        reported_calibrating = safe_int(data.get('calibrating')) if 'calibrating' in data else None
        phase = door_recalibration_phase(c)
        phase_active = door_recalibration_active(c, now)

        if phase == 'requested' and not phase_active:
            changed = clear_door_recalibration_state(c) or changed
            phase = ''
            previous = 'unknown'
        elif phase in ('calibrating', 'settling') and not phase_active:
            changed = clear_door_recalibration_state(c) or changed
            c['ignore_door_open_until_closed'] = True
            changed = force_door_closed(c, calibrating=0) or changed
            return changed

        if 'opennessScore' in data or 'openness_score' in data:
            openness_score = safe_float(data.get('opennessScore', data.get('openness_score')))
            if openness_score is not None and openness_score != c.get('openness_score'):
                c['openness_score'] = openness_score
                changed = True

        if 'doorAngle' in data:
            door_angle = safe_float(data.get('doorAngle')) or 0.0
            if door_angle != c.get('door_angle'):
                c['door_angle'] = door_angle
                changed = True
        elif 'door_angle' in data:
            door_angle = safe_float(data.get('door_angle')) or 0.0
            if door_angle != c.get('door_angle'):
                c['door_angle'] = door_angle
                changed = True

        if phase == 'requested' and door_recalibration_active(c, now):
            if reported_calibrating not in (None, 0):
                changed = hold_door_recalibration(c, 'calibrating', now, door_recalibration_active_timeout_seconds) or changed
            else:
                changed = hold_door_recalibration(c, 'requested', now, door_recalibration_command_timeout_seconds, extend_deadline=False) or changed

            return changed

        if reported_calibrating is not None and reported_calibrating != 0:
            changed = hold_door_recalibration(c, 'calibrating', now, door_recalibration_active_timeout_seconds) or changed
            return changed

        if phase in ('calibrating', 'settling'):
            changed = clear_door_recalibration_state(c) or changed
            c['ignore_door_open_until_closed'] = True
            changed = force_door_closed(c, calibrating=0) or changed
            c['last_transition_at'] = now

            cancel_door_sound_repeat(c.get('deviceID'))
            return True

        if open_value is None:
            return changed

        if c.get('ignore_door_open_until_closed'):
            if open_value == 0:
                c.pop('ignore_door_open_until_closed', None)
                changed = True
            else:
                changed = force_door_closed(c, calibrating=0) or changed
                return changed

        current = 'open' if open_value == 1 else 'closed'

        if current != c.get('door_status'):
            c['door_status'] = current
            changed = True

        if current == 'closed':
            if c.get('ignore_door_open_until_closed'):
                c.pop('ignore_door_open_until_closed', None)
                changed = True

            if float(c.get('openness_score', 0.0) or 0.0) != 0.0 and open_value == 0:
                c['openness_score'] = 0.0
                changed = True

            if float(c.get('door_angle', 0.0) or 0.0) != 0.0 and open_value == 0:
                c['door_angle'] = 0.0
                changed = True

        is_transition = previous != current and previous in ('open', 'closed', 'unknown')
        should_fire_routes = is_transition and previous in ('open', 'closed')

        if is_transition:
            c['last_transition_at'] = now
            deviceID = c.get('deviceID')

            if current == 'closed':
                cancel_door_sound_repeat(deviceID)

            if should_fire_routes:
                record_android_home_activity(
                    c,
                    kind='door',
                    state=current,
                    status='Opened' if current == 'open' else 'Closed',
                    icon='sensor_door',
                    accent='green' if current == 'open' else 'red'
                )

                changed = fire_door_routes(c, current) or changed

        return changed or is_transition

    @app.route('/telemetry', methods=['POST'])
    def telemetry():
        nonlocal last_routine_telemetry_broadcast_at

        data = request.get_json(silent=True) or {}
        deviceID = data.get('deviceID') or request.headers.get('X-Device-ID')
        msg_type = str(data.get('type') or '').strip()

        routine_telemetry_types = {
            'telemetry',
            'camera_ping',
            'door_telemetry',
            'key_telemetry',
            'presence_telemetry',
            'camera_motion',
        }

        if not deviceID:
            return jsonify({'ok': True})

        with state_lock:
            device_clients = get_clients_for_device(deviceID)
            if not device_clients:
                device_clients = [get_unprovisioned_client(deviceID)]
            request_roles = normalize_client_roles(data.get('clientRole') or request.headers.get('X-Client-Role') or '')
            is_door_poll = client_role_dss in request_roles or msg_type in ('door_telemetry', 'doorMonitor')
            is_camera_poll = client_role_cam in request_roles or msg_type in ('camera_ping', 'camera_motion')
            is_key_poll = client_role_key in request_roles or msg_type in ('key_telemetry', 'presence_telemetry')

            if is_door_poll:
                c = next((x for x in device_clients if client_has_role(x, client_role_dss)), device_clients[0])
            elif is_camera_poll:
                c = next((x for x in device_clients if client_has_role(x, client_role_cam)), device_clients[0])
            elif is_key_poll:
                c = next((x for x in device_clients if client_has_role(x, client_role_key)), device_clients[0])
            else:
                c = device_clients[0]
            previous_battery = c.get('battery')
            was_live = bool(c.get('last_seen'))
            state_dirty = register_seen_client(c, data, request.path, data.get('type')) or False
            battery = c.get('battery')

            if battery is not None and (not was_live or battery != previous_battery):
                wake_automations = app.config.get('KOTIBOT_AUTOMATIONS_WAKE')

                if callable(wake_automations):
                    wake_automations()

            if is_camera_poll and client_has_role(c, client_role_cam):
                auto_rotation = camera_surface_rotation_degrees(
                    data.get('cameraTargetRotation')
                    or data.get('camera_target_rotation')
                    or data.get('resolvedCameraRotation')
                    or data.get('resolved_camera_rotation')
                )

                if auto_rotation is not None:
                    selected_camera = str(
                        data.get('selectedCamera')
                        or data.get('selected_camera')
                        or c.get('selected_camera')
                        or 'back'
                    ).strip().lower() or 'back'

                    auto_changed = (
                        c.get('camera_auto_rotation') != auto_rotation
                        or c.get('camera_auto_rotation_lens') != selected_camera
                    )

                    c['camera_auto_rotation'] = auto_rotation
                    c['camera_auto_rotation_at'] = now_epoch()
                    c['camera_auto_rotation_lens'] = selected_camera

                    state_dirty = auto_changed or state_dirty

                if 'motionDetectionEnabled' in data or 'motion_detection_enabled' in data:
                    motion_enabled = bool(data.get('motionDetectionEnabled', data.get('motion_detection_enabled')))
                    if c.get('motion_detection_enabled') != motion_enabled:
                        c['motion_detection_enabled'] = motion_enabled
                        state_dirty = True

                if 'motionThreshold' in data or 'motionDetectionThreshold' in data or 'motion_detection_threshold' in data:
                    threshold = safe_float(
                        data.get(
                            'motionThreshold',
                            data.get('motionDetectionThreshold', data.get('motion_detection_threshold'))
                        )
                    )

                    if threshold is not None and threshold != c.get('motion_detection_threshold'):
                        c['motion_detection_threshold'] = threshold
                        state_dirty = True

                if msg_type == 'camera_motion' or data.get('motionDetected') or data.get('motion_detected'):
                    score = safe_float(data.get('motionScore', data.get('motion_score')))
                    state_dirty = handle_camera_motion_detected(c, score) or state_dirty

            if is_door_poll and client_has_role(c, client_role_dss):
                state_dirty = handle_door_telemetry(c, data) or state_dirty

            if is_key_poll and client_has_role(c, client_role_key):
                state_dirty = handle_key_telemetry(c, data) or state_dirty

            res = snapshot_client(c)
            res['ok'] = True
            res['serverPort'] = 5000
            res['armed'] = 1 if system_armed() else 0
            res['systemArmed'] = 1 if system_armed() else 0

            if client_has_role(c, client_role_cam):
                preview_on = preview_requested_for_client(c)
                recording_on = bool(c.get('recording_enabled'))
                selected_camera = c.get('selected_camera', 'back')

                if client_has_role(c, client_role_tapo) and c.get('tapo_kind') == 'camera':
                    selected_camera = 'tapo'

                lens_state = (c.get('preview_by_lens') or {}).get(selected_camera, {})

                res['previewRequested'] = 1 if preview_on else 0
                res['previewRequest'] = 1 if preview_on else 0
                motion_on = bool(c.get('motion_detection_enabled'))

                res['recordingEnabled'] = 1 if recording_on else 0
                res['motionDetectionEnabled'] = 1 if motion_on else 0
                res['motion_detection_enabled'] = 1 if motion_on else 0
                res['motionDetectionThreshold'] = float(c.get('motion_detection_threshold', 18.0) or 18.0)
                res['motion_detection_threshold'] = float(c.get('motion_detection_threshold', 18.0) or 18.0)
                res['cameraEnabled'] = 1 if (preview_on or recording_on or motion_on) else 0
                res['selectedCamera'] = selected_camera
                res['selected_camera'] = selected_camera
                res['previewAspect'] = lens_state.get('aspect_ratio', '16:9')

            pending = dict(c.get('pending_command', {}))

            if pending:
                door_command_keys = ('triggerRecalibrate', 'recalibrateSeq', 'recalibrate_seq', 'recalibrate')

                if not (is_door_poll and client_has_role(c, client_role_dss)):
                    for key in door_command_keys:
                        pending.pop(key, None)

                if pending:
                    res.update(pending)

                    for key in pending:
                        c.get('pending_command', {}).pop(key, None)

                    state_dirty = True

            if state_dirty:
                save_state()
            else:
                should_broadcast = msg_type not in routine_telemetry_types
                now_for_broadcast = now_epoch()

                if (
                    not should_broadcast
                    and now_for_broadcast - last_routine_telemetry_broadcast_at >= routine_telemetry_broadcast_interval_seconds
                ):
                    last_routine_telemetry_broadcast_at = now_for_broadcast
                    should_broadcast = True

                if should_broadcast:
                    broadcast_state()

            return jsonify(res)

    @app.route('/upload_frame', methods=['POST'])
    def upload_frame():
        nonlocal last_frame_status_broadcast_at

        deviceID = str(
            getattr(g, 'kotibot_device_id', '')
        ).strip()

        if not deviceID:
            return "Missing ID", 400

        frame_bytes = request.get_data(cache=True)

        if not valid_camera_frame(frame_bytes):
            return jsonify({
                'ok': False,
                'error': 'invalid_camera_frame',
            }), 415

        with state_lock:
            device_clients = get_clients_for_device(deviceID)

            c = next(
                (
                    client
                    for client in device_clients
                    if client.get('provisioned')
                    and client_has_role(
                        client,
                        client_role_cam,
                    )
                ),
                None,
            )

            if c is None:
                return jsonify({
                    'ok': False,
                    'error': 'camera_role_required',
                }), 403

            now = now_epoch()
            c['ip'] = request.headers.get('X-Forwarded-For', request.remote_addr or '')
            c['last_seen'] = now
            c['heartbeat_pending'] = False
            c['heartbeat_requested_at'] = 0
            c['needs_heartbeat'] = False

            preview_on = preview_requested_for_client(c)
            recording_on = bool(c.get('recording_enabled'))
            motion_on = bool(c.get('motion_detection_enabled'))
            motion_threshold = float(c.get('motion_detection_threshold', 18.0) or 18.0)

            if not preview_on and not recording_on and not motion_on:
                response = {
                    'ok': True,
                    'previewRequested': 0,
                    'previewRequest': 0,
                    'recordingEnabled': 0,
                    'motionDetectionEnabled': 0,
                    'motion_detection_enabled': 0,
                    'motionDetectionThreshold': motion_threshold,
                    'motion_detection_threshold': motion_threshold,
                    'cameraEnabled': 0,
                }

                pending = dict(c.get('pending_command', {}))

                if pending:
                    for key in ('triggerRecalibrate', 'recalibrateSeq', 'recalibrate_seq', 'recalibrate'):
                        pending.pop(key, None)

                if pending:
                    response.update(pending)

                    for key in pending:
                        c.get('pending_command', {}).pop(key, None)

                    save_state()

                return jsonify(response), 200

            frame_captured_ms = safe_int(request.headers.get('X-Koti-Frame-Captured-Ms'))
            last_frame_captured_ms = safe_int(c.get('frame_captured_ms'))
            stale_frame = (
                frame_captured_ms is not None
                and last_frame_captured_ms is not None
                and frame_captured_ms <= last_frame_captured_ms
            )

            if not stale_frame:
                c['frame'] = frame_bytes
                c['frame_captured_ms'] = frame_captured_ms or int(now * 1000)
                c['frame_seq'] = (c.get('frame_seq', 0) + 1) % 10000
                c['frame_last_seen'] = now

                if now - last_frame_status_broadcast_at >= frame_status_broadcast_interval_seconds:
                    last_frame_status_broadcast_at = now
                    broadcast_state()

            response = {
                'ok': True,
                'previewRequested': 1 if preview_on else 0,
                'previewRequest': 1 if preview_on else 0,
                'recordingEnabled': 1 if recording_on else 0,
                'motionDetectionEnabled': 1 if motion_on else 0,
                'motion_detection_enabled': 1 if motion_on else 0,
                'motionDetectionThreshold': float(c.get('motion_detection_threshold', 18.0) or 18.0),
                'motion_detection_threshold': float(c.get('motion_detection_threshold', 18.0) or 18.0),
                'cameraEnabled': 1 if (preview_on or recording_on or motion_on) else 0,
            }

            pending = dict(c.get('pending_command', {}))

            if pending:
                for key in ('triggerRecalibrate', 'recalibrateSeq', 'recalibrate_seq', 'recalibrate'):
                    pending.pop(key, None)

            if pending:
                response.update(pending)

                for key in pending:
                    c.get('pending_command', {}).pop(key, None)

                save_state()

        return jsonify(response), 200

    return {
        'cancel_motion_recording_stop': cancel_motion_recording_stop,
        'handle_camera_motion_detected': handle_camera_motion_detected,
        'handle_door_telemetry': handle_door_telemetry,
        'camera_frame_motion_score': camera_frame_motion_score,
    }

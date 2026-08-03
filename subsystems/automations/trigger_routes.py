from pathlib import Path
import importlib.util
import math
import sys
import threading
import types

from flask import jsonify, request

ARMING_STATES = ('day', 'night', 'away')

_tapo_control = None


def _load_client_tapo_control():
    module_path = None
    here = Path(__file__).resolve()

    for root in [here.parent, *here.parents]:
        candidate = root / 'client-tapo' / 'tapo_control.py'

        if candidate.exists():
            module_path = candidate
            break

    if module_path is None:
        raise ImportError('Unable to find client-tapo/tapo_control.py')

    package_name = 'kotibot_trigger_tapo'
    package_dir = module_path.parent
    package = sys.modules.get(package_name)

    if package is None:
        package = types.ModuleType(package_name)
        package.__path__ = [str(package_dir)]
        sys.modules[package_name] = package

    spec = importlib.util.spec_from_file_location(
        f'{package_name}.tapo_control',
        module_path
    )

    if not spec or not spec.loader:
        raise ImportError(f'Unable to load Tapo control module: {module_path}')

    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    return module


def _get_tapo_control():
    global _tapo_control

    if _tapo_control is None:
        _tapo_control = _load_client_tapo_control()

    return _tapo_control


def _run_tapo_async(*args, **kwargs):
    return _get_tapo_control().run_async(*args, **kwargs)


def _set_tapo_device_from_info(*args, **kwargs):
    return _get_tapo_control().set_tapo_device_from_info(*args, **kwargs)

def _start_tapo_camera_recording(*args, **kwargs):
    return _get_tapo_control().start_tapo_camera_recording(*args, **kwargs)


def _stop_tapo_camera_recording(*args, **kwargs):
    return _get_tapo_control().stop_tapo_camera_recording(*args, **kwargs)

def _norm_route_value(value):
    return str(value or '').strip().lower().replace(' ', '_').replace('-', '_')


def _clean_arm_state(value):
    value = _norm_route_value(value)

    if value in ARMING_STATES:
        return value

    return 'day'


def _clean_arm_states(value):
    if value is None or value == '':
        return []

    if isinstance(value, str):
        value = value.replace('+', ',').split(',')

    if not isinstance(value, (list, tuple, set)):
        return []

    states = []

    for item in value:
        state = _clean_arm_state(item)

        if state not in states:
            states.append(state)

    return states


def register_trigger_routes(app, context):
    state_lock = context['state_lock']
    clients = context['clients']
    get_routes = context['get_routes']
    set_routes = context['set_routes']
    client_role_cam = context['client_role_cam']
    client_role_key = context.get('client_role_key')
    client_has_role = context['client_has_role']
    get_clients_for_device = context['get_clients_for_device']
    play_wav_file = context['play_wav_file']
    schedule_door_sound_repeat = context['schedule_door_sound_repeat']
    cancel_door_sound_repeat = context.get('cancel_door_sound_repeat', lambda deviceID: None)
    save_state = context['save_state']
    broadcast_state = context['broadcast_state']
    push_queue = context.get('push_queue')
    system_arm_state = context.get('system_arm_state', lambda: 'day')
    now_epoch = context.get('now_epoch', lambda: 0)
    now_local = context.get('now_local', lambda: '')
    activity_log = context.get('activity_log')
    activity_log_can_record_event = activity_log is not None and hasattr(activity_log, 'record_event')
    route_timers = {}
    armed_device_off_timers = set()
    android_flashlight_actions = (
        'android_flashlight',
        'motion_flashlight',
        'flashlight',
    )
    android_white_screen_actions = (
        'android_white_screen',
        'motion_screen',
        'white_screen',
    )
    motion_route_actions = (
        'sound',
        'wav',
        'audio',
        'play_sound',
        'notification',
        'notify',
        'push',
        'key_notification',
        'recording',
        'record',
        'video',
        'camera',
        'cam',
        'device',
        'device_on',
        'turn_on_device',
        'turn_on',
        'power_on',
        *android_flashlight_actions,
        *android_white_screen_actions,
    )

    def _route_safe_int(value):
        try:
            return int(value)
        except Exception:
            return None

    def _route_seconds(value, default=0):
        try:
            return max(0, int(float(value if value not in (None, '') else default)))
        except Exception:
            return max(0, int(default or 0))

    def _route_bool(value, default=False):
        if value in (None, ''):
            return bool(default)

        if isinstance(value, bool):
            return value

        if isinstance(value, (int, float)):
            return value != 0

        return str(value).strip().lower() not in ('0', 'false', 'no', 'off', 'disabled')

    def _route_volume(value, default=None):
        if value in (None, ''):
            value = default

        if value in (None, ''):
            return None

        try:
            volume = float(value)
        except Exception:
            return None

        if volume > 1.0:
            volume = volume / 100.0

        return max(0.0, min(volume, 1.0))

    def _route_float(value, default=None):
        if value in (None, ''):
            return default

        try:
            number = float(value)
        except Exception:
            return default

        return number if math.isfinite(number) else default

    def _route_threshold(route):
        for key in ('threshold', 'trigger_threshold', 'threshold_value', 'thresholdValue'):
            threshold = _route_float(route.get(key))

            if threshold is not None:
                return threshold

        return None

    def _current_arm_state():
        return _clean_arm_state(system_arm_state())

    def _route_arm_states(route):
        states = _clean_arm_states(
            route.get('arm_states', route.get('armStates', route.get('active_arm_states', route.get('activeArmStates'))))
        )

        if not states:
            state = route.get('arm_state', route.get('armState'))
            states = _clean_arm_states(state)

        return states

    def _route_enabled_for_current_state(route):
        states = _route_arm_states(route)

        if not states:
            return True

        return _current_arm_state() in states

    def _route_source_device(route):
        return str(
            route.get('from_deviceID')
            or route.get('from_device_id')
            or route.get('sourceDeviceID')
            or route.get('source_deviceID')
            or route.get('source_device_id')
            or ''
        ).strip()

    def _route_target_device(route):
        return str(
            route.get('to_deviceID')
            or route.get('to_device_id')
            or route.get('targetDeviceID')
            or route.get('target_deviceID')
            or route.get('target_device_id')
            or ''
        ).strip()

    def _route_target_id(route):
        return str(
            route.get('targetID')
            or route.get('target_id')
            or route.get('to_input')
            or ''
        ).strip()

    def _route_trigger(route):
        trigger = _norm_route_value(route.get('trigger', route.get('from_trigger')))

        if trigger:
            return trigger

        output = _norm_route_value(route.get('from_output'))

        if output in ('open', 'door_open', 'door_opened'):
            return 'door_open'

        if output in ('close', 'closed', 'door_close', 'door_closed'):
            return 'door_close'

        if output in ('motion', 'motion_detected', 'camera_motion'):
            return 'motion'

        return output

    def _route_action_kind(route):
        return _norm_route_value(
            route.get('action_type')
            or route.get('actionType')
            or route.get('action')
            or route.get('to_kind')
        )

    def _route_matches_trigger(route, source_deviceID, trigger):
        if _route_source_device(route) != source_deviceID:
            return False

        wanted = _norm_route_value(trigger)
        route_trigger = _route_trigger(route)

        aliases = {
            wanted,
            f'door_{wanted}',
            f'door_{wanted}ed',
        }

        if wanted == 'door_open':
            aliases.update({'open', 'opened', 'door_opened'})

        if wanted == 'door_close':
            aliases.update({'close', 'closed', 'door_closed'})

        if wanted == 'motion':
            aliases.update({'camera_motion', 'motion_detected'})

        return route_trigger in aliases

    def _is_tapo_camera_client(client):
        if not client or not client_has_role(client, 'TAPO'):
            return False

        kind = str(client.get('tapo_kind') or client.get('tapo_device_type') or '').strip().lower()

        return kind == 'camera' or bool(client.get('tapo_is_camera'))

    def _is_recordable_camera_client(client):
        return bool(client) and (
            client_has_role(client, client_role_cam) or
            _is_tapo_camera_client(client)
        )

    def _camera_clients_for_route(route, fallback_deviceID=''):
        to_deviceID = _route_target_device(route) or fallback_deviceID

        if not to_deviceID:
            return []

        matches = [
            x for x in get_clients_for_device(to_deviceID)
            if _is_recordable_camera_client(x)
        ]
        direct = clients.get(to_deviceID)

        if direct and _is_recordable_camera_client(direct) and direct not in matches:
            matches.append(direct)

        return matches

    def _key_clients():
        if not client_role_key:
            return []

        return [
            x for x in clients.values()
            if x.get('provisioned') and client_has_role(x, client_role_key)
        ]

    def _notification_target_key_device(route):
        return str(
            route.get('target_key_deviceID')
            or route.get('targetKeyDeviceID')
            or route.get('notification_target_deviceID')
            or route.get('notificationTargetDeviceID')
            or route.get('to_deviceID')
            or route.get('targetDeviceID')
            or ''
        ).strip()
    
    def _send_key_notification(source_client, route, trigger):
        if not push_queue:
            return False

        cooldown_seconds = _route_seconds(route.get('cooldown_seconds', route.get('cooldownSeconds')), 0)
        current_time = now_epoch()

        source_name = source_client.get('clientName') or source_client.get('deviceID') or 'KotiBot'
        event_time = now_local()
        title = str(route.get('title') or route.get('notification_title') or f'{source_name} Alert').strip()
        body = str(route.get('message') or route.get('body') or f'{source_name} triggered {trigger}').strip()
        sent = False
        target_key_deviceID = _notification_target_key_device(route)

        for key_client in _key_clients():
            key_deviceID = str(key_client.get('deviceID') or '').strip()

            if target_key_deviceID and key_deviceID != target_key_deviceID:
                continue

            push_queue.enqueue(
                event_type=f'arming_{trigger}',
                deviceID=key_deviceID,
                title=title,
                body=body,
                fcm_token=key_client.get('fcm_token', ''),
                data={
                    'targetRole': client_role_key,
                    'targetDeviceID': key_deviceID,
                    'sourceDeviceID': source_client.get('deviceID', ''),
                    'sourceClientName': source_name,
                    'trigger': trigger,
                    'armState': _current_arm_state(),
                    'eventTime': event_time,
                }
            )
            sent = True

        if sent and cooldown_seconds:
            route['last_notification_at'] = current_time
            save_state()

        return sent
    
    def _recording_duration(route):
        value = route.get('duration_seconds', route.get('durationSeconds', route.get('recording_duration_seconds', route.get('recordingDurationSeconds', route.get('timer_seconds', route.get('timerSeconds'))))))
        min_value = route.get('minimum_duration_seconds', route.get('minimumDurationSeconds', route.get('min_duration_seconds', route.get('minDurationSeconds'))))

        try:
            seconds = int(value or 0)
        except Exception:
            seconds = 0

        try:
            minimum_seconds = int(min_value or 0)
        except Exception:
            minimum_seconds = 0

        return max(0, min(max(seconds, minimum_seconds), 3600))

    def _schedule_tapo_camera_recording_stop(route, cam, duration):
        if duration <= 0:
            return False

        deviceID = cam.get('deviceID')

        if not deviceID:
            return False

        timer_key = '|'.join([
            'tapo_recording',
            str(deviceID),
            _route_source_device(route),
            _route_trigger(route),
        ])
        existing = route_timers.get(timer_key)
        retrigger = _route_bool(route.get('retrigger', route.get('retriggerTimer')), True)

        if existing and existing.is_alive():
            if not retrigger:
                return False

            existing.cancel()

        def fire_stop():
            with state_lock:
                current = clients.get(deviceID)

                if not _is_tapo_camera_client(current):
                    return

                try:
                    recording_file = _stop_tapo_camera_recording(deviceID)
                except Exception:
                    app.logger.exception('Tapo camera recording stop failed for %s', deviceID)
                    return

                current['tapo_recording'] = False
                current['tapo_recording_enabled'] = False

                if recording_file:
                    current['tapo_recording_file'] = recording_file

                save_state()
                broadcast_state()

        timer = threading.Timer(duration, fire_stop)
        timer.daemon = True
        route_timers[timer_key] = timer
        timer.start()

        return True
    
    def _apply_camera_recording_action(route, trigger, fallback_deviceID=''):
        changed = False
        duration = _recording_duration(route)
        retrigger = _route_bool(route.get('retrigger', route.get('retriggerTimer')), True)

        for cam in _camera_clients_for_route(route, fallback_deviceID=fallback_deviceID):
            if _is_tapo_camera_client(cam):
                deviceID = cam.get('deviceID')

                if not deviceID:
                    continue

                if duration:
                    existing_until = float(cam.get('route_recording_until', 0) or 0)

                    if existing_until > now_epoch() and not retrigger:
                        continue

                try:
                    recording_file = _start_tapo_camera_recording(cam)
                except Exception:
                    app.logger.exception('Tapo camera recording start failed for %s', deviceID)
                    continue

                cam['recording_enabled'] = True
                cam['motion_recording_active'] = True
                cam['tapo_recording'] = True
                cam['tapo_recording_enabled'] = True

                if recording_file:
                    cam['tapo_recording_file'] = recording_file

                if duration:
                    cam['route_recording_until'] = now_epoch() + duration
                    _schedule_tapo_camera_recording_stop(route, cam, duration)

                save_state()
                broadcast_state()
                changed = True
                continue

            pending = cam.setdefault('pending_command', {})
            cam['recording_enabled'] = True
            cam['motion_recording_active'] = True
            pending['recordingEnabled'] = 1

            if trigger == 'motion':
                cam['motion_detection_enabled'] = True
                pending['motionDetectionEnabled'] = 1
                pending['motion_detection_enabled'] = 1

            if duration:
                existing_until = float(cam.get('route_recording_until', 0) or 0)

                if existing_until > now_epoch() and not retrigger:
                    continue

                cam['route_recording_until'] = now_epoch() + duration
                pending['recordingDurationSeconds'] = duration

            changed = True

        return changed

    def _tapo_command_item_from_client(c, deviceID):
        return {
            'id': c.get('tapo_id') or str(deviceID).replace('tapo:', ''),
            'ip': c.get('tapo_ip') or c.get('ip'),
            'model': c.get('tapo_model'),
            'device_type': c.get('tapo_device_type'),

            'kind': c.get('tapo_kind', 'unknown'),
            'dashboard_section': c.get('tapo_dashboard_section', 'control'),

            'control_ready': c.get('tapo_control_ready'),
            'control_error': c.get('tapo_control_error', ''),

            'is_bulb': bool(c.get('tapo_is_bulb')),
            'is_plug': bool(c.get('tapo_is_plug')),
            'is_outlet_extender': bool(c.get('tapo_is_outlet_extender')),
            'is_camera': bool(c.get('tapo_is_camera')),
            'dimmable': bool(c.get('tapo_dimmable')),

            'supports_power': bool(c.get('tapo_supports_power')),
            'supports_brightness': bool(c.get('tapo_supports_brightness')),
            'supports_color_temp': bool(c.get('tapo_supports_color_temp')),
            'supports_color': bool(c.get('tapo_supports_color')),
            'children': c.get('tapo_children') if isinstance(c.get('tapo_children'), list) else [],
        }

    def _update_tapo_client_from_command_result(deviceID, result):
        c = clients.get(deviceID)

        if not c:
            return False

        device = result.get('device') if isinstance(result.get('device'), dict) else {}
        changed = False

        if 'control_ready' in device:
            c['tapo_control_ready'] = device.get('control_ready')
            changed = True

        if 'control_error' in device:
            c['tapo_control_error'] = str(device.get('control_error') or '')
            changed = True

        if 'is_on' in device:
            c['tapo_is_on'] = device.get('is_on')
            changed = True

        if 'brightness' in device:
            c['tapo_brightness'] = _route_safe_int(device.get('brightness'))
            changed = True

        if 'color_temperature' in device:
            c['tapo_color_temperature'] = _route_safe_int(device.get('color_temperature'))
            changed = True

        if 'hue' in device:
            c['tapo_hue'] = _route_safe_int(device.get('hue'))
            changed = True

        if 'saturation' in device:
            c['tapo_saturation'] = _route_safe_int(device.get('saturation'))
            changed = True

        if isinstance(device.get('children'), list):
            c['tapo_children'] = device.get('children')
            changed = True

        return changed

    def _recover_tapo_desired_lighting(deviceID, **options):
        recover = app.config.get(
            'KOTIBOT_TAPO_RECOVER_DESIRED_LIGHTING'
        )

        if not callable(recover):
            return None

        try:
            return recover(deviceID, **options)
        except Exception:
            app.logger.exception(
                'Tapo desired lighting recovery failed for %s',
                deviceID
            )
            return None

    def _tapo_child_value_from_route(route):
        target_id = _route_target_id(route)
        child_id = str(route.get('child_id') or route.get('childId') or '').strip()

        if not child_id and '|' in target_id:
            child_id = target_id.split('|', 1)[1].strip()

        if not child_id:
            return None

        return {
            'child_id': child_id,
            'position': str(route.get('child_position') or route.get('childPosition') or '').strip(),
            'child_index': str(route.get('child_index') or route.get('childIndex') or '').strip(),
        }

    def _tapo_device_off_timer_key(route, target_deviceID, target_id):
        return '|'.join([
            str(target_id or target_deviceID),
            _route_source_device(route),
            _route_trigger(route),
            _route_action_kind(route)
        ])

    def _tapo_target_is_on(route, tapo_client):
        child_value = _tapo_child_value_from_route(route)

        if not child_value:
            return tapo_client.get('tapo_is_on') is True

        requested_keys = {
            str(value).strip()
            for value in (
                child_value.get('child_id'),
                child_value.get('position'),
                child_value.get('child_index'),
            )
            if str(value or '').strip()
        }
        children = tapo_client.get('tapo_children')

        if not requested_keys or not isinstance(children, list):
            return False

        for child in children:
            if not isinstance(child, dict):
                continue

            child_keys = {
                str(value).strip()
                for value in (
                    child.get('id'),
                    child.get('child_id'),
                    child.get('position'),
                    child.get('index'),
                    child.get('cli_index'),
                )
                if str(value or '').strip()
            }

            if requested_keys.intersection(child_keys):
                return child.get('is_on') is True

        return False

    def _cancel_tapo_device_off_action(route, target_deviceID, target_id):
        timer_key = _tapo_device_off_timer_key(route, target_deviceID, target_id)
        armed_device_off_timers.discard(timer_key)
        timer = route_timers.pop(timer_key, None)

        if timer and timer.is_alive():
            timer.cancel()

    def _schedule_tapo_device_off_action(
        route,
        target_deviceID,
        target_id,
        delay_seconds=None,
        restart_existing=None,
        record_sensor_clear=False
    ):
        if not _route_bool(route.get('auto_off', route.get('autoOff')), False):
            return False

        seconds = _route_seconds(
            route.get('auto_off_seconds', route.get('autoOffSeconds', route.get('timer_seconds', route.get('timerSeconds')))),
            0
        )

        if seconds <= 0:
            return False

        timer_key = _tapo_device_off_timer_key(route, target_deviceID, target_id)
        existing = route_timers.get(timer_key)
        retrigger = (
            _route_bool(route.get('retrigger', route.get('retriggerTimer')), True)
            if restart_existing is None
            else bool(restart_existing)
        )

        if existing and existing.is_alive():
            if not retrigger:
                return False

            existing.cancel()

        delay = seconds if delay_seconds is None else max(1, _route_seconds(delay_seconds, 1))
        armed_device_off_timers.add(timer_key)

        def fire_off():
            with state_lock:
                if route_timers.get(timer_key) is not timer:
                    return

                route_timers.pop(timer_key, None)

                if timer_key not in armed_device_off_timers:
                    return

                tapo_client = clients.get(target_deviceID)

                if not tapo_client or not client_has_role(tapo_client, 'TAPO'):
                    armed_device_off_timers.discard(timer_key)
                    return

                child_value = _tapo_child_value_from_route(route)
                command = 'child_off' if child_value else 'off'
                item = _tapo_command_item_from_client(tapo_client, target_deviceID)

                try:
                    result = _run_tapo_async(_set_tapo_device_from_info(
                        item,
                        command,
                        child_value
                    ))
                except Exception:
                    app.logger.exception('Device auto-off route failed for %s', target_deviceID)
                    _schedule_tapo_device_off_action(
                        route,
                        target_deviceID,
                        target_id,
                        delay_seconds=min(15, max(1, seconds)),
                        record_sensor_clear=record_sensor_clear
                    )
                    return

                armed_device_off_timers.discard(timer_key)
                changed = _update_tapo_client_from_command_result(
                    target_deviceID,
                    result or {}
                )

                if changed:
                    save_state()

                if record_sensor_clear:
                    source_client = clients.get(
                        _route_source_device(route)
                    )

                    if isinstance(source_client, dict):
                        _record_route_activity(
                            source_client,
                            route,
                            'sensor_clear',
                            action_state='off'
                        )

                broadcast_state()

        timer = threading.Timer(delay, fire_off)
        timer.daemon = True
        route_timers[timer_key] = timer
        timer.start()

        return True

    def sync_device_automation_target_power(target_deviceID, target_id, is_on):
        target_deviceID = str(target_deviceID or '').strip()
        target_id = str(target_id or '').strip() or f'{target_deviceID}|'
        power_on = _route_bool(is_on, False)
        changed = False

        if not target_deviceID:
            return False

        for route in list(get_routes()):
            if (
                not _route_enabled_for_current_state(route)
                or _route_trigger(route) != 'motion'
                or _route_action_kind(route) not in (
                    'device',
                    'device_on',
                    'turn_on_device',
                    'turn_on',
                    'power_on',
                )
            ):
                continue

            route_target_id = _route_target_id(route)
            route_target_deviceID = _route_target_device(route)

            if not route_target_deviceID and '|' in route_target_id:
                route_target_deviceID = route_target_id.split('|', 1)[0].strip()

            if route_target_deviceID != target_deviceID:
                continue

            if route_target_id:
                normalized_route_target_id = (
                    f'{route_target_id}|'
                    if route_target_id == route_target_deviceID
                    else route_target_id
                )

                if normalized_route_target_id != target_id:
                    continue
            elif target_id != f'{target_deviceID}|':
                continue

            source_client = clients.get(_route_source_device(route))

            if not isinstance(source_client, dict):
                continue

            motion_active = source_client.get('motion_active')

            if not power_on:
                _cancel_tapo_device_off_action(route, target_deviceID, route_target_id)
                continue

            if _route_bool(motion_active, False):
                _cancel_tapo_device_off_action(route, target_deviceID, route_target_id)
                continue

            scheduled = _schedule_tapo_device_off_action(
                route,
                target_deviceID,
                route_target_id,
                restart_existing=True
            )
            changed = scheduled or changed

        return changed
    
    def _apply_tapo_device_on_action(route, schedule_auto_off=True):
        target_id = _route_target_id(route)
        target_deviceID = _route_target_device(route)

        if not target_deviceID and '|' in target_id:
            target_deviceID = target_id.split('|', 1)[0].strip()

        if not target_deviceID:
            app.logger.warning('Device-on route has no target: %s', route)
            return False

        tapo_client = clients.get(target_deviceID)

        if not tapo_client or not client_has_role(tapo_client, 'TAPO'):
            app.logger.warning('Device-on route target is not a Tapo client: %s', target_deviceID)
            return False

        if _tapo_target_is_on(route, tapo_client):
            if schedule_auto_off:
                _schedule_tapo_device_off_action(
                    route,
                    target_deviceID,
                    target_id,
                    restart_existing=True
                )

            return False

        child_value = _tapo_child_value_from_route(route)
        command = 'child_on' if child_value else 'on'
        item = _tapo_command_item_from_client(tapo_client, target_deviceID)

        if not child_value:
            recovered_client = _recover_tapo_desired_lighting(
                target_deviceID,
                allow_off=True,
                desired_only=False,
                force_lighting=False
            )

            if recovered_client:
                item = _tapo_command_item_from_client(
                    recovered_client,
                    target_deviceID
                )

        try:
            result = _run_tapo_async(_set_tapo_device_from_info(
                item,
                command,
                child_value
            ))
        except Exception:
            app.logger.exception('Device-on route failed for %s', target_deviceID)
            return False

        changed = _update_tapo_client_from_command_result(
            target_deviceID,
            result or {}
        )

        if changed:
            save_state()

        broadcast_state()

        if schedule_auto_off:
            _schedule_tapo_device_off_action(
                route,
                target_deviceID,
                target_id,
                restart_existing=True
            )

        return True
    
    def _apply_route_action(
        source_client,
        route,
        trigger,
        schedule_auto_off=True
    ):
        action_kind = _route_action_kind(route)
        filename = route.get('filename') or route.get('sound') or route.get('to_input')

        if action_kind in ('sound', 'wav', 'audio', 'play_sound'):
            if source_client.get('doorbell_muted'):
                return False

            volume = _route_volume(route.get('sound_volume', route.get('volume_percent', route.get('volume'))))
            play_wav_file(filename, volume=volume)

            repeat = route.get('repeat', route.get('repeatSound'))
            if trigger == 'door_open' and repeat is not False:
                schedule_door_sound_repeat(source_client, filename, volume=volume)

            return True

        if action_kind in ('notification', 'notify', 'push', 'key_notification'):
            return _send_key_notification(source_client, route, trigger)

        if action_kind in ('recording', 'record', 'video', 'camera', 'cam'):
            return _apply_camera_recording_action(route, trigger, fallback_deviceID=source_client.get('deviceID', ''))

        if action_kind in android_flashlight_actions:
            return bool(
                client_has_role(source_client, client_role_cam)
                and not client_has_role(source_client, 'TAPO')
                and source_client.get('motion_flashlight_enabled')
            )

        if action_kind in android_white_screen_actions:
            return bool(
                client_has_role(source_client, client_role_cam)
                and not client_has_role(source_client, 'TAPO')
                and source_client.get('motion_screen_enabled')
            )

        if action_kind in ('device', 'device_on', 'turn_on_device', 'turn_on', 'power_on'):
            return _apply_tapo_device_on_action(
                route,
                schedule_auto_off=schedule_auto_off
            )

        return False

    def _matching_routes(source_client, trigger):
        source_deviceID = source_client.get('deviceID')

        if not source_deviceID:
            return []

        return [
            route for route in list(get_routes())
            if _route_enabled_for_current_state(route)
            and _route_matches_trigger(route, source_deviceID, trigger)
        ]

    def _route_is_door_sound_repeat(route):
        return (
            _route_trigger(route) == 'door_open'
            and _route_action_kind(route) in ('sound', 'wav', 'audio', 'play_sound')
            and _route_bool(route.get('repeat', route.get('repeatSound')), True)
        )

    def _route_device_action_satisfied(route):
        if _route_action_kind(route) not in (
            'device',
            'device_on',
            'turn_on_device',
            'turn_on',
            'power_on',
        ):
            return False

        target_id = _route_target_id(route)
        target_deviceID = (
            _route_target_device(route)
        )

        if (
            not target_deviceID
            and '|' in target_id
        ):
            target_deviceID = (
                target_id.split('|', 1)[0]
                .strip()
            )

        if not target_deviceID:
            return False

        target = clients.get(
            target_deviceID
        )

        if (
            not isinstance(target, dict)
            or not client_has_role(
                target,
                'TAPO',
            )
        ):
            return False

        return _tapo_target_is_on(
            route,
            target,
        )

    def fire_door_routes(door_client, output):
        # Device integrations pass the physical state here as "open" or
        # "closed"; route matching below uses only semantic door_open/door_close.
        # Raw Matter BooleanState values must be normalized before this boundary.
        output = _norm_route_value(output)
        trigger = 'door_open' if output == 'open' else 'door_close' if output in ('close', 'closed') else output
        changed = False

        if trigger == 'door_close':
            cancel_door_sound_repeat(door_client.get('deviceID'))

        for route in _matching_routes(
            door_client,
            trigger,
        ):
            action_satisfied = (
                _route_device_action_satisfied(
                    route
                )
            )
            action_applied = (
                _apply_route_action(
                    door_client,
                    route,
                    trigger,
                )
            )

            if (
                action_applied
                or action_satisfied
            ):
                _record_route_activity(
                    door_client,
                    route,
                    trigger,
                )

            changed = (
                action_applied
                or changed
            )

        return changed

    def fire_camera_motion_routes(camera_client, output='motion'):
        trigger = 'motion'
        changed = False
        active = output not in (False, 0) and _norm_route_value(output) not in (
            '0',
            'false',
            'inactive',
            'idle',
            'clear',
            'cleared',
            'no_motion',
            'off',
            'unoccupied',
            'vacant',
            'absent',
        )

        for route in _matching_routes(camera_client, trigger):
            target_id = _route_target_id(route)
            target_deviceID = _route_target_device(route)

            if not target_deviceID and '|' in target_id:
                target_deviceID = target_id.split('|', 1)[0].strip()

            is_device_action = (
                bool(target_deviceID)
                and _route_action_kind(route) in (
                    'device',
                    'device_on',
                    'turn_on_device',
                    'turn_on',
                    'power_on',
                )
            )

            if not active:
                if is_device_action:
                    changed = _schedule_tapo_device_off_action(
                        route,
                        target_deviceID,
                        target_id,
                        restart_existing=False,
                        record_sensor_clear=True
                    ) or changed

                continue

            if is_device_action:
                _cancel_tapo_device_off_action(
                    route,
                    target_deviceID,
                    target_id
                )

            action_applied = _apply_route_action(
                camera_client,
                route,
                trigger,
                schedule_auto_off=False
            )

            if action_applied:
                _record_route_activity(
                    camera_client,
                    route,
                    trigger,
                )

            changed = (
                action_applied
                or changed
            )

        return changed

    def fire_environment_routes(sensor_client, kind, value, previous_value):
        clean_kind = _norm_route_value(kind)
        current = _route_float(value)
        previous = _route_float(previous_value)

        if clean_kind not in ('temperature', 'humidity') or current is None or previous is None or current == previous:
            return False

        changed = False

        for direction in ('above', 'below'):
            trigger = f'{clean_kind}_{direction}'

            for route in _matching_routes(sensor_client, trigger):
                threshold = _route_threshold(route)

                if threshold is None:
                    continue

                crossed = (
                    previous <= threshold < current
                    if direction == 'above'
                    else previous >= threshold > current
                )

                if not crossed:
                    continue

                action_satisfied = (
                    _route_device_action_satisfied(
                        route
                    )
                )
                action_applied = (
                    _apply_route_action(
                        sensor_client,
                        route,
                        trigger,
                    )
                )

                if (
                    action_applied
                    or action_satisfied
                ):
                    _record_route_activity(
                        sensor_client,
                        route,
                        trigger,
                    )

                changed = (
                    action_applied
                    or changed
                )

        return changed

    def sync_arming_motion_detection():
        changed = False
        active_motion_routes = [
            route
            for route in get_routes()
            if _route_enabled_for_current_state(route)
            and _route_trigger(route) == 'motion'
            and _route_action_kind(route) in motion_route_actions
        ]
        active_motion_sources = {
            _route_source_device(route)
            for route in active_motion_routes
        }
        flashlight_sources = {
            _route_source_device(route)
            for route in active_motion_routes
            if _route_action_kind(route) in android_flashlight_actions
        }
        white_screen_sources = {
            _route_source_device(route)
            for route in active_motion_routes
            if _route_action_kind(route) in android_white_screen_actions
        }

        for client in clients.values():
            if not client.get('provisioned') or not client_has_role(client, client_role_cam):
                continue

            deviceID = client.get('deviceID')
            is_android_home_camera = not client_has_role(client, 'TAPO')
            desired_fields = (
                (
                    'motion_detection_enabled',
                    bool(deviceID and deviceID in active_motion_sources),
                    ('motionDetectionEnabled', 'motion_detection_enabled'),
                ),
                (
                    'motion_flashlight_enabled',
                    bool(is_android_home_camera and deviceID and deviceID in flashlight_sources),
                    ('motionFlashlightEnabled', 'motion_flashlight_enabled'),
                ),
                (
                    'motion_screen_enabled',
                    bool(is_android_home_camera and deviceID and deviceID in white_screen_sources),
                    ('motionScreenEnabled', 'motion_screen_enabled'),
                ),
            )
            pending = None

            for state_key, should_enable, command_keys in desired_fields:
                if _route_bool(client.get(state_key), False) == should_enable:
                    continue

                client[state_key] = should_enable
                pending = pending or client.setdefault(
                    'pending_command',
                    {}
                )

                for command_key in command_keys:
                    pending[command_key] = 1 if should_enable else 0

                changed = True

        if changed:
            save_state()
            broadcast_state()

        return changed

    def _route_scope(route):
        scope = str(route.get('scope') or '').strip().lower()

        if scope in ('automation', 'security'):
            return scope

        return 'security' if _route_arm_states(route) else 'automation'

    def _route_activity_target_name(route):
        target_id = _route_target_id(route)
        target_device_id = (
            _route_target_device(route)
        )

        if (
            not target_device_id
            and '|' in target_id
        ):
            target_device_id = (
                target_id.split('|', 1)[0]
                .strip()
            )

        target = clients.get(
            target_device_id
        )

        if isinstance(target, dict):
            child_id = ''

            if '|' in target_id:
                child_id = (
                    target_id.split('|', 1)[1]
                    .strip()
                )

            children = target.get(
                'tapo_children'
            )

            if (
                child_id
                and isinstance(children, list)
            ):
                for index, child in enumerate(
                    children
                ):
                    if not isinstance(
                        child,
                        dict,
                    ):
                        continue

                    identifiers = {
                        str(value).strip()
                        for value in (
                            child.get('id'),
                            child.get('device_id'),
                            child.get('deviceId'),
                            child.get('child_id'),
                            child.get('childId'),
                            child.get('position'),
                            child.get(
                                'slot_number'
                            ),
                            index + 1,
                        )
                        if str(
                            value or ''
                        ).strip()
                    }

                    if child_id not in identifiers:
                        continue

                    return str(
                        child.get('name')
                        or child.get('alias')
                        or child.get(
                            'display_name'
                        )
                        or child.get(
                            'child_name'
                        )
                        or child_id
                    ).strip()

            return str(
                target.get('clientName')
                or target.get('name')
                or target.get('tapo_alias')
                or target_device_id
                or 'Device'
            ).strip()

        return (
            target_device_id
            or target_id
            or 'Device'
        )

    def _route_activity_event(trigger):
        clean_trigger = _norm_route_value(
            trigger
        )
        labels = {
            'door_open': 'Door Opened',
            'door_close': 'Door Closed',
            'motion': 'Motion Detected',
            'sensor_clear': 'Sensor Clear',
            'temperature_above': (
                'Temperature Above Threshold'
            ),
            'temperature_below': (
                'Temperature Below Threshold'
            ),
            'humidity_above': (
                'Humidity Above Threshold'
            ),
            'humidity_below': (
                'Humidity Below Threshold'
            ),
            'on': 'Turned On',
            'off': 'Turned Off',
        }

        if clean_trigger in labels:
            return labels[clean_trigger]

        return (
            clean_trigger
            .replace('_', ' ')
            .title()
            or 'Automation Triggered'
        )

    def _route_activity_status(
        route,
        action_state='on'
    ):
        action_kind = _route_action_kind(
            route
        )

        if action_kind in (
            'sound',
            'wav',
            'audio',
            'play_sound',
        ):
            filename = (
                route.get('filename')
                or route.get('sound')
                or route.get('to_input')
            )

            return (
                f'Played '
                f'{Path(str(filename)).name}'
                if filename
                else 'Sound played'
            )

        if action_kind in (
            'notification',
            'notify',
            'push',
            'key_notification',
        ):
            return 'Notification sent'

        if action_kind in (
            'recording',
            'record',
            'video',
            'camera',
            'cam',
        ):
            return 'Recording started'

        if action_kind in android_flashlight_actions:
            return 'Camera flashlight activated'

        if action_kind in android_white_screen_actions:
            return 'White screen activated'

        if action_kind in (
            'device',
            'device_on',
            'turn_on_device',
            'turn_on',
            'power_on',
        ):
            verb = (
                'Turned off'
                if action_state == 'off'
                else 'Turned on'
            )

            return (
                f'{verb} '
                f'{_route_activity_target_name(route)}'
            )

        return 'Automation ran'

    def _record_route_activity(
        source_client,
        route,
        trigger,
        action_state='on'
    ):
        if not activity_log_can_record_event:
            return None

        source_client = source_client if isinstance(source_client, dict) else {}
        device_id = str(source_client.get('deviceID') or '').strip()

        if not device_id:
            return None

        category = _route_scope(route)

        try:
            return activity_log.record_event(
                deviceID=device_id,
                name=(
                    source_client.get('clientName')
                    or source_client.get('name')
                    or device_id
                ),
                kind=f'{category}_route',
                state=_route_activity_event(
                    trigger
                ),
                status=_route_activity_status(
                    route,
                    action_state
                ),
                icon=(
                    'security'
                    if category == 'security'
                    else 'auto_awesome'
                ),
                accent=(
                    'orange'
                    if category == 'security'
                    else 'purple'
                ),
                source=f'{category}-route',
                detail='',
                category=category,
            )
        except Exception:
            app.logger.exception('%s route activity recording failed', category.title())
            return None

    def _routes_for_scope(scope):
        return [route for route in get_routes() if _route_scope(route) == scope]

    def _automation_route_from_payload(data):
        trigger = _route_trigger(data)
        threshold = _route_threshold(data)

        if trigger in ('temperature_above', 'temperature_below', 'humidity_above', 'humidity_below'):
            if threshold is None:
                raise ValueError('Environmental routes require a numeric threshold.')

            if trigger.startswith('humidity_') and not 0 <= threshold <= 100:
                raise ValueError('Humidity threshold must be between 0 and 100.')

        return {
            'scope': 'automation',
            'from_deviceID': data.get('from_deviceID') or data.get('sourceDeviceID') or '',
            'from_output': data.get('from_output') or data.get('trigger') or '',
            'trigger': trigger,
            'threshold': threshold if threshold is not None else '',
            'threshold_unit': data.get('threshold_unit') or data.get('thresholdUnit') or '',
            'arm_states': [],
            'to_kind': data.get('to_kind') or data.get('action_type') or data.get('actionType') or '',
            'action_type': _route_action_kind(data),
            'to_deviceID': data.get('to_deviceID') or data.get('targetDeviceID') or '',
            'to_input': data.get('to_input') or data.get('message') or '',
            'targetID': data.get('targetID') or data.get('target_id') or '',
            'power_action': data.get('power_action') or data.get('powerAction') or '',
            'filename': data.get('filename') or data.get('sound') or '',
            'sound_volume': data.get('sound_volume', data.get('soundVolume', data.get('volume_percent', data.get('volumePercent', data.get('volume', ''))))),
            'target_key_deviceID': data.get('target_key_deviceID') or data.get('targetKeyDeviceID') or data.get('notification_target_deviceID') or data.get('notificationTargetDeviceID') or '',
            'title': data.get('title') or '',
            'message': data.get('message') or data.get('body') or '',
            'duration_seconds': data.get('duration_seconds', data.get('durationSeconds', '')),
            'minimum_duration_seconds': data.get('minimum_duration_seconds', data.get('minimumDurationSeconds', data.get('min_duration_seconds', data.get('minDurationSeconds', '')))),
            'repeat': data.get('repeat', data.get('repeatSound', '')),
            'timer_seconds': data.get('timer_seconds', data.get('timerSeconds', '')),
            'repeat_seconds': data.get('repeat_seconds', data.get('repeatSeconds', '')),
            'cooldown_seconds': data.get('cooldown_seconds', data.get('cooldownSeconds', '')),
            'auto_off': data.get('auto_off', data.get('autoOff', '')),
            'auto_off_seconds': data.get('auto_off_seconds', data.get('autoOffSeconds', '')),
            'retrigger': data.get('retrigger', data.get('retriggerTimer', '')),
        }

    def _security_route_from_payload(data):
        route = _automation_route_from_payload(data)
        arm_states = _clean_arm_states(
            data.get(
                'arm_states',
                data.get(
                    'armStates',
                    data.get('active_arm_states', data.get('activeArmStates'))
                )
            )
        )

        if not arm_states:
            arm_states = _clean_arm_states(data.get('arm_state', data.get('armState')))

        if not arm_states:
            raise ValueError('Security actions require at least one mode.')

        route['scope'] = 'security'
        route['arm_states'] = arm_states
        return route

    def _route_delete_value(route):
        return {
            key: value
            for key, value in route.items()
            if key != 'scope' and not str(key).startswith('last_')
        }

    @app.route('/api/routes', methods=['GET', 'POST', 'DELETE'])
    def api_security_routes():
        if request.method == 'GET':
            with state_lock:
                return jsonify({'ok': True, 'routes': _routes_for_scope('security')})

        data = request.get_json(silent=True) or {}

        if request.method == 'POST':
            try:
                payloads = data.get('routes') if isinstance(data.get('routes'), list) else [data]
                prepared = [
                    _security_route_from_payload(item)
                    for item in payloads
                    if isinstance(item, dict)
                ]
            except ValueError as error:
                return jsonify({'ok': False, 'error': str(error)}), 400

            if not prepared:
                return jsonify({'ok': False, 'error': 'Missing security action'}), 400

        with state_lock:
            routes = list(get_routes())

            if request.method == 'POST':
                existing = [_route_delete_value(route) for route in routes]

                for route in prepared:
                    value = _route_delete_value(route)

                    if value not in existing:
                        routes.append(route)
                        existing.append(value)
            else:
                if not isinstance(data, dict) or not data:
                    return jsonify({'ok': False, 'error': 'Missing security action'}), 400

                wanted = _route_delete_value(data)
                position = next(
                    (
                        index
                        for index, route in enumerate(routes)
                        if _route_scope(route) == 'security'
                        and _route_delete_value(route) == wanted
                    ),
                    -1
                )

                if position < 0:
                    return jsonify({'ok': False, 'error': 'Security action not found'}), 404

                removed_route = routes.pop(position)

                if _route_is_door_sound_repeat(removed_route):
                    cancel_door_sound_repeat(_route_source_device(removed_route))

            set_routes(routes)
            save_state()
            broadcast_state()
            sync_arming_motion_detection()

        return jsonify({'ok': True})

    def _automation_route_index(value):
        try:
            return int(str(value or '').rsplit(':', 1)[-1])
        except (TypeError, ValueError):
            return -1

    @app.route('/api/automation-routes', methods=['GET', 'POST', 'PUT', 'DELETE'])
    def api_automation_routes():
        if request.method == 'GET':
            with state_lock:
                return jsonify({'ok': True, 'routes': _routes_for_scope('automation')})

        data = request.get_json(silent=True) or {}

        prepared = []

        if request.method in ('POST', 'PUT'):
            try:
                payloads = data.get('routes') if isinstance(data.get('routes'), list) else [data]
                prepared = [_automation_route_from_payload(item) for item in payloads if isinstance(item, dict)]
            except ValueError as error:
                return jsonify({'ok': False, 'error': str(error)}), 400

            if not prepared:
                return jsonify({'ok': False, 'error': 'Missing automation'}), 400

        with state_lock:
            routes = list(get_routes())
            automation_positions = [
                index for index, route in enumerate(routes)
                if _route_scope(route) == 'automation'
            ]

            if request.method == 'POST':
                for route in prepared:
                    if route not in routes:
                        routes.append(route)

            else:
                index = _automation_route_index(data.get('automationID'))

                if index < 0 or index >= len(automation_positions):
                    return jsonify({'ok': False, 'error': 'Automation not found'}), 404

                position = automation_positions[index]
                removed_route = routes[position]

                if request.method == 'PUT':
                    routes[position:position + 1] = prepared
                else:
                    routes.pop(position)

                    if _route_is_door_sound_repeat(removed_route):
                        cancel_door_sound_repeat(_route_source_device(removed_route))

            set_routes(routes)
            save_state()
            broadcast_state()
            sync_arming_motion_detection()

        return jsonify({'ok': True})

    return {
        'fire_door_routes': fire_door_routes,
        'fire_camera_motion_routes': fire_camera_motion_routes,
        'fire_environment_routes': fire_environment_routes,
        'sync_device_automation_target_power': sync_device_automation_target_power,
        'sync_arming_motion_detection': sync_arming_motion_detection,
    }
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from threading import Lock

from flask import Response, jsonify, request, send_from_directory

from server_core.io import read_json, write_json_atomic

TAPO_LIGHTING_STATE_PATH = Path(__file__).resolve().parent / "tapo_lighting_state.json"
AUTOMATION_STATE_PATH = Path(__file__).resolve().parents[1] / "automations" / "automations_state.json"
AUTOMATION_TYPE_TAPO_RECHARGE = "tapo_recharge_android_battery"

from .tapo_extenders import (
    merge_outlet_extender_child_metadata,
    normalize_outlet_extender_children,
    outlet_extender_child_display_name,
)
from .tapo_energy import register_tapo_energy_routes

from .tapo_control import (
    TAPO_CAMERA_HLS_ROOT,
    debug_tapo_discovery_text,
    list_tapo_devices,
    prune_tapo_camera_streams,
    refresh_tapo_devices,
    run_async,
    set_tapo_device,
    set_tapo_device_from_info,
    start_tapo_camera_recording,
    start_tapo_camera_stream,
    stop_tapo_camera_recording,
    stop_tapo_camera_stream,
    tapo_brightness,
    tapo_off,
    tapo_on,
    tapo_stream_key,
    touch_tapo_camera_stream,
)

def register_tapo_routes(app, ctx):
    STATE_LOCK = ctx['state_lock']
    CLIENTS = ctx['clients']
    CLIENT_ROLE_TAPO = ctx['client_role_tapo']
    client_has_role = ctx['client_has_role']
    init_client = ctx['init_client']
    snapshot_client = ctx['snapshot_client']
    save_state = ctx['save_state']
    broadcast_state = ctx['broadcast_state']
    clean_zone_name = ctx['clean_zone_name']
    safe_int = ctx['safe_int']
    now_epoch = ctx['now_epoch']
    activity_log = ctx.get('activity_log')
    activity_log_can_record = activity_log is not None and hasattr(activity_log, 'record_state_change')
    tapo_watcher_stop = ctx.get('tapo_watcher_stop')
    device_power_changed = ctx.get('device_power_changed', lambda target_deviceID, target_id, is_on: False)
    tapo_refresh_lock = Lock()
    tapo_device_command_executor = ThreadPoolExecutor(max_workers=max(1, int(os.environ.get('KOTIBOT_TAPO_COMMAND_WORKERS', '8') or 8)))
    tapo_watcher_interval = float(os.environ.get('KOTIBOT_TAPO_WATCHER_SECONDS', '20') or 20)
    tapo_discovery_interval = max(
        0.0,
        float(os.environ.get('KOTIBOT_TAPO_DISCOVERY_SECONDS', '60') or 60)
    )

    def normalize_tapo_lighting_key(key):
        text = str(key or '').strip()

        if text == 'home':
            return 'home'

        if text.startswith('device:'):
            device_id = text.replace('device:', '', 1).strip()
            return f'device:{device_id}' if device_id else ''

        if text.startswith('room:'):
            device_ids = sorted(set(
                device_id.strip()
                for device_id in text.replace('room:', '', 1).split(',')
                if device_id.strip()
            ))
            return f"room:{','.join(device_ids)}" if device_ids else ''

        return ''

    def normalize_tapo_lighting_scheme(raw):
        if not isinstance(raw, dict):
            return None

        mode = str(raw.get('mode') or '').strip()
        if not mode:
            return None

        preset = raw.get('preset') if isinstance(raw.get('preset'), dict) else {}
        saved_at = raw.get('savedAt')

        try:
            saved_at = int(saved_at)
        except Exception:
            saved_at = int(time.time() * 1000)

        return {
            'favorite': raw.get('favorite') is True,
            'icon': str(raw.get('icon') or '').strip(),
            'label': str(raw.get('label') or '').strip() or mode,
            'mode': mode,
            'preset': preset,
            'savedAt': saved_at
        }

    def normalize_tapo_lighting_mode_choice(value):
        valid_presets = {'day', 'evening', 'movie', 'nightlight'}

        if isinstance(value, dict):
            power = str(value.get('power') or '').strip().lower()
            preset = str(value.get('preset') or '').strip().lower()
            power = power if power in {'off', 'on'} else ''
            preset = preset if preset in valid_presets else ''

            if power == 'off':
                return 'off'
            if power == 'on' and preset:
                return {'power': 'on', 'preset': preset}
            if power == 'on':
                return 'on'
            if preset:
                return preset
            return 'ignore'

        text = str(value or '').strip().lower()
        return text if text in {'ignore', 'off', 'on', *valid_presets} else 'ignore'

    def normalize_tapo_lighting_mode_config(data):
        if not isinstance(data, dict):
            return {}

        normalized = {}

        for raw_mode, raw_targets in data.items():
            mode = str(raw_mode or '').strip().lower()

            if mode not in {'day', 'evening', 'night', 'away'} or not isinstance(raw_targets, dict):
                continue

            clean_targets = {}

            for raw_key, raw_value in raw_targets.items():
                key = str(raw_key or '').strip()

                if key.startswith('room:'):
                    room = key.replace('room:', '', 1).strip()
                    key = f'room:{room}' if room else ''
                elif key.startswith('device:'):
                    device_id = key.replace('device:', '', 1).strip()
                    key = f'device:{device_id}' if device_id else ''
                else:
                    key = ''

                if key:
                    clean_targets[key] = normalize_tapo_lighting_mode_choice(raw_value)

            normalized[mode] = clean_targets

        return normalized

    def normalize_tapo_lighting_state(data):
        if not isinstance(data, dict):
            data = {}

        normalized_schemes = {}
        schemes = data.get('schemes') if isinstance(data.get('schemes'), dict) else {}

        for raw_key, raw_schemes in schemes.items():
            key = normalize_tapo_lighting_key(raw_key)
            if not key or not isinstance(raw_schemes, list):
                continue

            by_mode = {}

            for raw_scheme in raw_schemes:
                scheme = normalize_tapo_lighting_scheme(raw_scheme)
                if not scheme:
                    continue

                existing = by_mode.get(scheme['mode'])

                if not existing or scheme['savedAt'] >= existing.get('savedAt', 0):
                    if existing and existing.get('favorite'):
                        scheme['favorite'] = True
                    by_mode[scheme['mode']] = scheme
                elif scheme.get('favorite'):
                    existing['favorite'] = True

            if by_mode:
                normalized_schemes[key] = sorted(
                    by_mode.values(),
                    key=lambda item: (item.get('mode', ''), item.get('savedAt', 0))
                )

        normalized_active = {}
        active_schemes = data.get('activeSchemes') if isinstance(data.get('activeSchemes'), dict) else {}

        for raw_key, raw_mode in active_schemes.items():
            key = normalize_tapo_lighting_key(raw_key)
            mode = str(raw_mode or '').strip()

            if key and mode:
                normalized_active[key] = mode

        return {
            'schemes': normalized_schemes,
            'activeSchemes': normalized_active,
            'modeConfig': normalize_tapo_lighting_mode_config(data.get('modeConfig'))
        }

    def read_tapo_lighting_state():
        try:
            data = read_json(TAPO_LIGHTING_STATE_PATH)
        except Exception:
            data = {}

        return normalize_tapo_lighting_state(data)

    def write_tapo_lighting_state(data):
        state = normalize_tapo_lighting_state(data)

        write_json_atomic(TAPO_LIGHTING_STATE_PATH, state)

        return state

    app.config['KOTIBOT_TAPO_LIGHTING_STATE_SNAPSHOT'] = read_tapo_lighting_state

    def tapo_lighting_preset_mode(mode):
        mode = str(mode or '').strip().lower()
        return mode if mode in {'day', 'evening', 'movie', 'nightlight'} else ''

    def tapo_home_lighting_mode(mode):
        mode = str(mode or '').strip().lower()
        return mode if mode in {'day', 'evening', 'night', 'away'} else ''

    def tapo_builtin_lighting_preset(mode):
        mode = tapo_lighting_preset_mode(mode)

        if not mode:
            return None

        presets = {
            'day': {
                'brightness': 90,
                'colorTemperature': 3700,
                'whiteSaturation': 1,
                'hue': None,
                'saturation': None,
            },
            'evening': {
                'brightness': 80,
                'colorTemperature': 3200,
                'whiteSaturation': 1,
                'hue': None,
                'saturation': None,
            },
            'movie': {
                'brightness': 5,
                'colorTemperature': 2700,
                'whiteSaturation': 5,
                'hue': None,
                'saturation': None,
            },
            'nightlight': {
                'brightness': 1,
                'colorTemperature': 2700,
                'whiteSaturation': 1,
                'hue': None,
                'saturation': None,
            },
        }

        return dict(presets[mode])

    def normalize_tapo_white_saturation(value=1):
        parsed = safe_int(value)

        if parsed is None:
            parsed = 1

        return max(1, min(10, parsed))

    def tapo_white_hue_from_kelvin(kelvin):
        parsed = safe_int(kelvin)

        if parsed is None:
            parsed = 4200

        parsed = max(2500, min(6500, parsed))
        ratio = (parsed - 2500) / 4000

        return round(42 + ((210 - 42) * ratio))

    def tapo_lighting_key_device_ids(key):
        return sorted([
            device_id.strip()
            for device_id in str(key or '').replace('room:', '', 1).split(',')
            if device_id.strip()
        ])

    def tapo_lighting_scheme_for_key(state, key, mode):
        schemes = state.get('schemes') if isinstance(state.get('schemes'), dict) else {}
        target_schemes = schemes.get(key) if key else None

        if not isinstance(target_schemes, list):
            return None

        for scheme in target_schemes:
            if isinstance(scheme, dict) and scheme.get('mode') == mode:
                return scheme

        return None

    def tapo_lighting_room_key_for_client(c):
        room_name = clean_zone_name(c.get('zone_name') or c.get('room') or c.get('room_name') or '')
        room_key = room_name.lower()

        if not room_key:
            return ''

        device_ids = []

        for candidate in CLIENTS.values():
            if not isinstance(candidate, dict):
                continue

            if not candidate.get('provisioned'):
                continue

            if str(candidate.get('tapo_kind') or '').lower() not in {'bulb', 'lightstrip'}:
                continue

            if candidate.get('tapo_room_power') is not True:
                continue

            candidate_room = clean_zone_name(
                candidate.get('zone_name')
                or candidate.get('room')
                or candidate.get('room_name')
                or ''
            ).lower()

            if candidate_room != room_key:
                continue

            device_id = str(candidate.get('deviceID') or '').strip()

            if device_id:
                device_ids.append(device_id)

        return f"room:{','.join(sorted(set(device_ids)))}" if device_ids else ''

    def tapo_lighting_matching_room_key_for_device(state, deviceID, exact_room_key=''):
        active = state.get('activeSchemes') if isinstance(state.get('activeSchemes'), dict) else {}
        exact_ids = set(tapo_lighting_key_device_ids(exact_room_key)) if exact_room_key else set()
        candidates = []

        for key, mode in active.items():
            if not str(key or '').startswith('room:') or not mode:
                continue

            key_ids = set(tapo_lighting_key_device_ids(key))

            if deviceID not in key_ids:
                continue

            scheme = tapo_lighting_scheme_for_key(state, key, mode)
            saved_at = safe_int((scheme or {}).get('savedAt')) or 0

            candidates.append({
                'key': key,
                'mode': mode,
                'distance': abs(len(key_ids) - len(exact_ids)) if exact_ids else len(key_ids),
                'savedAt': saved_at,
            })

        candidates.sort(key=lambda item: (item['distance'], -item['savedAt']))

        return candidates[0] if candidates else None

    def tapo_lighting_desired_recovery_preset_for_client(c):
        deviceID = str(c.get('deviceID') or '').strip()

        if not deviceID:
            return None

        updated_at = safe_int(c.get('tapo_desired_lighting_updated_at')) or 0

        if updated_at <= 0:
            return None

        mode = tapo_lighting_preset_mode(c.get('tapo_desired_lighting_mode'))
        fallback = tapo_builtin_lighting_preset(mode) if mode else {}
        fallback = fallback if isinstance(fallback, dict) else {}
        brightness = safe_int(c.get('tapo_desired_brightness'))
        color_temperature = safe_int(c.get('tapo_desired_color_temperature'))
        hue = safe_int(c.get('tapo_desired_hue'))
        saturation = safe_int(c.get('tapo_desired_saturation'))
        white_saturation = safe_int(c.get('tapo_desired_white_saturation'))
        has_desired_value = any(value is not None for value in (brightness, color_temperature, hue, saturation, white_saturation))

        if not has_desired_value and not fallback:
            return None

        preset = {
            'brightness': brightness if brightness is not None else fallback.get('brightness'),
            'colorTemperature': color_temperature if color_temperature is not None else fallback.get('colorTemperature'),
            'whiteSaturation': white_saturation if white_saturation is not None else fallback.get('whiteSaturation'),
            'hue': hue if hue is not None else fallback.get('hue'),
            'saturation': saturation if saturation is not None else fallback.get('saturation'),
        }

        return {
            'mode': mode or 'desired',
            'key': f'device:{deviceID}:desired',
            'preset': preset,
            'updatedAt': updated_at,
            'desired': True,
        }

    def tapo_lighting_recovery_preset_for_client(c):
        desired_target = tapo_lighting_desired_recovery_preset_for_client(c)

        if desired_target:
            return desired_target

        deviceID = str(c.get('deviceID') or '').strip()

        if not deviceID:
            return None

        state = read_tapo_lighting_state()
        active = state.get('activeSchemes') if isinstance(state.get('activeSchemes'), dict) else {}
        device_key = f'device:{deviceID}'
        room_key = tapo_lighting_room_key_for_client(c)
        mode = ''
        scheme_key = ''

        if room_key and tapo_lighting_preset_mode(active.get(room_key)):
            scheme_key = room_key
            mode = tapo_lighting_preset_mode(active.get(room_key))
        else:
            room_match = tapo_lighting_matching_room_key_for_device(state, deviceID, room_key)

            if room_match and tapo_lighting_preset_mode(room_match.get('mode')):
                scheme_key = room_match.get('key') or ''
                mode = tapo_lighting_preset_mode(room_match.get('mode'))

        if not mode and tapo_lighting_preset_mode(active.get('home')):
            scheme_key = room_key
            mode = tapo_lighting_preset_mode(active.get('home'))

        if not mode and tapo_lighting_preset_mode(active.get(device_key)):
            scheme_key = device_key
            mode = tapo_lighting_preset_mode(active.get(device_key))

        if not mode:
            return None

        device_scheme = tapo_lighting_scheme_for_key(state, device_key, mode)
        room_scheme = tapo_lighting_scheme_for_key(state, scheme_key, mode) if scheme_key else None
        preset = (device_scheme or room_scheme or {}).get('preset')

        if not isinstance(preset, dict):
            preset = tapo_builtin_lighting_preset(mode)

        if not isinstance(preset, dict):
            return None

        return {
            'mode': mode,
            'key': scheme_key or device_key,
            'preset': preset,
        }

    def tapo_lighting_recovery_actions_for_client(c, preset, force=False):
        if not isinstance(preset, dict):
            return []

        actions = []
        brightness = safe_int(preset.get('brightness'))

        if brightness is not None and c.get('tapo_supports_brightness') is True:
            if force or safe_int(c.get('tapo_brightness')) != brightness:
                actions.append({
                    'action': 'brightness_no_power',
                    'value': brightness,
                })

        hue = safe_int(preset.get('hue'))
        saturation = safe_int(preset.get('saturation'))
        color_temperature = safe_int(preset.get('colorTemperature'))

        if hue is not None and c.get('tapo_supports_color') is True:
            target_saturation = saturation if saturation is not None else 100

            if (
                force
                or safe_int(c.get('tapo_hue')) != hue
                or safe_int(c.get('tapo_saturation')) != target_saturation
            ):
                actions.append({
                    'action': 'color_no_power',
                    'value': {
                        'hue': hue,
                        'saturation': target_saturation,
                    },
                })

        elif color_temperature is not None and c.get('tapo_supports_color') is True:
            target_hue = tapo_white_hue_from_kelvin(color_temperature)
            target_saturation = normalize_tapo_white_saturation(preset.get('whiteSaturation'))

            if (
                force
                or safe_int(c.get('tapo_hue')) != target_hue
                or safe_int(c.get('tapo_saturation')) != target_saturation
            ):
                actions.append({
                    'action': 'color_no_power',
                    'value': {
                        'hue': target_hue,
                        'saturation': target_saturation,
                    },
                })

        elif color_temperature is not None and c.get('tapo_supports_color_temp') is True:
            if force or safe_int(c.get('tapo_color_temperature')) != color_temperature:
                actions.append({
                    'action': 'color_temperature_no_power',
                    'value': color_temperature,
                })

        return actions
    
    def tapo_lighting_recovery_plan(
        c,
        desired_only=False,
        force_lighting=False,
        allow_off=False,
        allow_empty=False
    ):
        if str(c.get('tapo_kind') or '').lower() not in {'bulb', 'lightstrip'}:
            return None

        if c.get('tapo_control_ready') is not True:
            return None

        power_state = c.get('tapo_is_on')

        if power_state is not True and not (allow_off and power_state is False):
            return None

        target = (
            tapo_lighting_desired_recovery_preset_for_client(c)
            if desired_only
            else tapo_lighting_recovery_preset_for_client(c)
        )

        if not target:
            return None

        actions = tapo_lighting_recovery_actions_for_client(
            c,
            target.get('preset'),
            force=force_lighting
        )

        if not actions and not allow_empty:
            return None

        return {
            'deviceID': c.get('deviceID'),
            'item': tapo_client_refresh_item(c),
            'mode': target.get('mode'),
            'key': target.get('key'),
            'actions': actions,
        }

    def tapo_merge_recovery_device(c, device):
        if not isinstance(device, dict):
            return

        if 'control_ready' in device:
            c['tapo_control_ready'] = device.get('control_ready')

        if 'control_error' in device:
            c['tapo_control_error'] = str(device.get('control_error') or '')

        if 'is_on' in device:
            c['tapo_is_on'] = device.get('is_on')

        if 'brightness' in device:
            c['tapo_brightness'] = safe_int(device.get('brightness'))

        if 'color_temperature' in device:
            c['tapo_color_temperature'] = safe_int(device.get('color_temperature'))

        if 'hue' in device:
            c['tapo_hue'] = safe_int(device.get('hue'))

        if 'saturation' in device:
            c['tapo_saturation'] = safe_int(device.get('saturation'))

    def tapo_apply_lighting_desired_value_to_client(c, action, value, mode=''):
        lighting_actions = {
            'brightness', 'brightness_no_power',
            'color_temperature', 'color_temperature_no_power',
            'color', 'color_no_power',
        }

        if action not in lighting_actions:
            return

        c['tapo_desired_lighting_updated_at'] = int(time.time() * 1000)
        desired_mode = tapo_lighting_preset_mode(mode)

        if desired_mode:
            c['tapo_desired_lighting_mode'] = desired_mode

        if action in {'brightness', 'brightness_no_power'}:
            brightness = safe_int(value)

            if brightness is not None:
                c['tapo_brightness'] = brightness
                c['tapo_desired_brightness'] = brightness

        elif action in {'color_temperature', 'color_temperature_no_power'}:
            color_temperature = safe_int(value)

            if color_temperature is not None:
                c['tapo_color_temperature'] = color_temperature
                c['tapo_desired_color_temperature'] = color_temperature
                c['tapo_desired_hue'] = None
                c['tapo_desired_saturation'] = None

        elif action in {'color', 'color_no_power'} and isinstance(value, dict):
            hue = safe_int(value.get('hue'))
            saturation = safe_int(value.get('saturation'))
            color_temperature = safe_int(value.get('colorTemperature') or value.get('color_temperature'))
            white_saturation = safe_int(value.get('whiteSaturation') or value.get('white_saturation'))

            if hue is not None:
                c['tapo_hue'] = hue
                c['tapo_desired_hue'] = hue

            if saturation is not None:
                c['tapo_saturation'] = saturation
                c['tapo_desired_saturation'] = saturation

            if color_temperature is not None:
                c['tapo_color_temperature'] = color_temperature
                c['tapo_desired_color_temperature'] = color_temperature

            if white_saturation is not None:
                c['tapo_desired_white_saturation'] = white_saturation

    def tapo_pending_power_command_key(action, value=None):
        action = str(action or '').strip().lower()

        if action in {'on', 'off'}:
            return 'device'

        if action not in {'child_on', 'child_off'} or not isinstance(value, dict):
            return ''

        child_id = str(
            value.get('child_id')
            or value.get('childId')
            or value.get('outlet_id')
            or value.get('outletId')
            or ''
        ).strip()
        child_position = str(
            value.get('position')
            or value.get('child_position')
            or value.get('childPosition')
            or ''
        ).strip()
        child_index = str(
            value.get('child_index')
            or value.get('childIndex')
            or value.get('cli_index')
            or value.get('cliIndex')
            or ''
        ).strip()
        target = child_id or child_position or child_index

        return f'child:{target}' if target else ''

    def tapo_record_pending_power_command(c, action, value=None):
        key = tapo_pending_power_command_key(action, value)

        if not key:
            return False

        pending = c.get('tapo_pending_power_commands')

        if not isinstance(pending, dict):
            pending = {}
            c['tapo_pending_power_commands'] = pending

        pending[key] = {
            'action': str(action or '').strip().lower(),
            'value': value,
            'updatedAt': int(time.time() * 1000),
        }

        return True

    def tapo_clear_pending_power_command(c, action, value=None):
        key = tapo_pending_power_command_key(action, value)
        pending = c.get('tapo_pending_power_commands')

        if not key or not isinstance(pending, dict):
            return

        pending.pop(key, None)

        if not pending:
            c.pop('tapo_pending_power_commands', None)

    def tapo_apply_lighting_recovery_plan(target):
        item = target.get('item') if isinstance(target, dict) else None
        actions = target.get('actions') if isinstance(target, dict) else None

        if not isinstance(item, dict) or not isinstance(actions, list):
            return None

        device = item

        for command in actions:
            action = command.get('action')
            value = command.get('value')
            result = run_async(set_tapo_device_from_info(device, action, value))

            if isinstance(result.get('device'), dict):
                device = result.get('device')

        return {
            'deviceID': target.get('deviceID'),
            'mode': target.get('mode'),
            'key': target.get('key'),
            'device': device,
        }

    def tapo_recover_desired_lighting_for_device(
        deviceID,
        allow_off=False,
        desired_only=True,
        force_lighting=True
    ):
        with STATE_LOCK:
            c = CLIENTS.get(deviceID)
            target = tapo_lighting_recovery_plan(
                c,
                desired_only=desired_only,
                force_lighting=force_lighting,
                allow_off=allow_off,
                allow_empty=allow_off
            ) if c else None

        if not target:
            return None

        try:
            result = tapo_apply_lighting_recovery_plan(target)
        except Exception as e:
            with STATE_LOCK:
                c = CLIENTS.get(deviceID)

                if c:
                    c['tapo_control_ready'] = False
                    c['tapo_control_error'] = str(e)
                    c['tapo_is_on'] = None
                    save_state()

            app.logger.exception(
                'Tapo desired lighting recovery failed for %s',
                deviceID
            )
            return None

        if not result:
            return None

        with STATE_LOCK:
            c = CLIENTS.get(deviceID)

            if not c:
                return None

            tapo_merge_recovery_device(c, result.get('device'))
            save_state()

            return snapshot_client(c)

    app.config['KOTIBOT_TAPO_RECOVER_DESIRED_LIGHTING'] = (
        tapo_recover_desired_lighting_for_device
    )

    def tapo_bool_value(value):
        return value is True or str(value).strip().lower() in {'1', 'true', 'yes', 'on', 'enabled'}

    def tapo_power_state(value):
        if value is True or value == 1:
            return True

        if value is False or value == 0:
            return False

        clean = str(value or '').strip().lower()

        if clean in {'1', 'true', 'yes', 'on', 'enabled'}:
            return True

        if clean in {'0', 'false', 'no', 'off', 'disabled'}:
            return False

        return None

    def tapo_power_target_states(c):
        if not isinstance(c, dict):
            return {}

        deviceID = str(c.get('deviceID') or '').strip()

        if not deviceID:
            return {}

        states = {}
        parent_state = tapo_power_state(c.get('tapo_is_on'))

        if parent_state is not None:
            states[f'{deviceID}|'] = parent_state

        children = c.get('tapo_children') if isinstance(c.get('tapo_children'), list) else []

        for child in children:
            if not isinstance(child, dict):
                continue

            child_id = str(
                child.get('id')
                or child.get('device_id')
                or child.get('deviceId')
                or child.get('child_id')
                or child.get('childId')
                or child.get('original_device_id')
                or child.get('originalDeviceId')
                or ''
            ).strip()
            child_state = tapo_power_state(child.get('is_on'))

            if child_id and child_state is not None:
                states[f'{deviceID}|{child_id}'] = child_state

        return states

    def tapo_changed_power_targets(previous, current):
        return [
            (target_id, is_on)
            for target_id, is_on in current.items()
            if target_id in previous and previous.get(target_id) != is_on
        ]

    def tapo_publish_power_changes(deviceID, changes):
        for target_id, is_on in changes:
            try:
                device_power_changed(deviceID, target_id, is_on)
            except Exception:
                app.logger.exception(
                    'Tapo power change publication failed for target %s',
                    target_id,
                )

    def tapo_activity_name(c):
        return str(
            c.get('clientName')
            or c.get('tapo_child_name')
            or c.get('tapo_alias')
            or c.get('tapo_id')
            or c.get('deviceID')
            or 'Tapo Device'
        ).strip()

    def tapo_record_power_activity(c, is_on):
        power_state = tapo_power_state(is_on)

        if power_state is None:
            return None

        if not activity_log_can_record:
            return None

        if not isinstance(c, dict) or not c.get('provisioned'):
            return None

        device_id = str(c.get('deviceID') or '').strip()
        tapo_kind = str(c.get('tapo_kind') or '').strip().lower()

        if not device_id:
            return None

        if tapo_kind == 'outlet_extender':
            return None

        if tapo_kind not in {'bulb', 'lightstrip', 'plug'} and c.get('tapo_supports_power') is not True:
            return None

        if tapo_kind in {'bulb', 'lightstrip'}:
            kind = 'tapo_light_power'
            icon = 'emoji_objects'
            accent = 'yellow'
        else:
            kind = 'tapo_power'
            icon = 'power'
            accent = 'purple'

        try:
            return activity_log.record_state_change(
                deviceID=device_id,
                name=tapo_activity_name(c),
                kind=kind,
                state='on' if power_state else 'off',
                status='On' if power_state else 'Off',
                icon=icon,
                accent=accent,
                source='tapo'
            )
        except Exception:
            app.logger.exception('Tapo power activity recording failed')
            return None

    def tapo_child_activity_id(parent, child, index):
        child_id = str(
            child.get('id')
            or child.get('device_id')
            or child.get('deviceId')
            or child.get('child_id')
            or child.get('childId')
            or child.get('position')
            or child.get('slot_number')
            or index + 1
        ).strip()

        parent_id = str(parent.get('deviceID') or tapo_device_id(parent) or parent.get('tapo_id') or '').strip()
        return f"{parent_id}:child:{child_id}" if parent_id and child_id else ''

    def tapo_child_activity_name(parent, child, index):
        name = clean_zone_name(
            child.get('name')
            or child.get('alias')
            or child.get('display_name')
            or child.get('child_name')
            or ''
        )

        if name:
            return name

        return outlet_extender_child_display_name(
            parent.get('clientName') or parent.get('tapo_alias') or parent.get('alias') or 'Tapo Extender',
            child,
            index,
            parent.get('tapo_model') or parent.get('model') or ''
        )

    def tapo_record_child_power_activity(parent, child, index):
        if not activity_log_can_record:
            return None

        if not isinstance(parent, dict) or not isinstance(child, dict):
            return None

        if not parent.get('provisioned'):
            return None

        power_state = tapo_power_state(child.get('is_on'))

        if power_state is None:
            return None

        device_id = tapo_child_activity_id(parent, child, index)

        if not device_id:
            return None

        try:
            return activity_log.record_state_change(
                deviceID=device_id,
                name=tapo_child_activity_name(parent, child, index),
                kind='tapo_extender_child_power',
                state='on' if power_state else 'off',
                status='On' if power_state else 'Off',
                icon='power',
                accent='purple',
                source='tapo'
            )
        except Exception:
            app.logger.exception('Tapo child power activity recording failed')
            return None

    def tapo_record_child_power_activities(parent):
        children = parent.get('tapo_children') if isinstance(parent.get('tapo_children'), list) else []

        for index, child in enumerate(children):
            tapo_record_child_power_activity(parent, child, index)


    def normalize_tapo_identity_value(value):
        return str(value or '').strip().lower()

    def tapo_identity_token(value):
        clean = normalize_tapo_identity_value(value).replace(':', '_').replace('-', '_').strip().lower()

        if clean.startswith('tapo_'):
            clean = clean.replace('tapo_', '', 1)

        if clean.startswith('tapo:'):
            clean = clean.replace('tapo:', '', 1)

        return clean

    def tapo_device_identity_tokens(deviceID='', device=None):
        device = device if isinstance(device, dict) else {}
        tokens = []

        for value in (
            deviceID,
            str(deviceID or '').replace('tapo:', '', 1),
            device.get('id'),
            device.get('mac'),
            device.get('device_id_hash'),
            device.get('ip'),
        ):
            token = tapo_identity_token(value)

            if token and token not in tokens:
                tokens.append(token)

        return tokens

    def find_existing_tapo_client_for_device(deviceID, device):
        target_tokens = set(tapo_device_identity_tokens(deviceID, device))

        if not target_tokens:
            return None, None

        for existing_id, existing in CLIENTS.items():
            if not isinstance(existing, dict):
                continue

            existing_tokens = set(tapo_device_identity_tokens(
                existing.get('deviceID') or existing_id,
                {
                    'id': existing.get('tapo_id'),
                    'mac': existing.get('tapo_mac'),
                    'ip': existing.get('tapo_ip') or existing.get('ip'),
                }
            ))

            if target_tokens & existing_tokens:
                return existing_id, existing

        return None, None

    def tapo_extender_child_display_name(c, child, index=0):
        return outlet_extender_child_display_name(
            c.get('clientName') or c.get('tapo_alias') or c.get('name') or c.get('tapo_model') or 'Tapo Extender',
            child,
            index,
            c.get('tapo_model') or ''
        )

    def normalize_tapo_extender_child_names(c):
        if c.get('tapo_kind') != 'outlet_extender' or not isinstance(c.get('tapo_children'), list):
            return False

        before = json.dumps(c.get('tapo_children', []), sort_keys=True, default=str)
        c['tapo_children'] = normalize_outlet_extender_children(
            c.get('tapo_children', []),
            c.get('tapo_model') or '',
            c.get('tapo_device_type') or '',
            c.get('clientName') or c.get('tapo_alias') or c.get('tapo_model') or 'Tapo Extender'
        )
        after = json.dumps(c.get('tapo_children', []), sort_keys=True, default=str)

        return before != after
    
    def tapo_child_identity_keys(child):
        if not isinstance(child, dict):
            return set()

        keys = set()

        for field in ('id', 'device_id', 'deviceId', 'child_id', 'childId', 'original_device_id', 'originalDeviceId'):
            value = str(child.get(field) or '').strip()

            if value:
                keys.add(value)

        return keys

    def tapo_child_fallback_keys(child, index=0):
        if not isinstance(child, dict):
            return set()

        keys = set()

        for field in ('position', 'slot_number', 'index', 'cli_index'):
            value = str(child.get(field) or '').strip()

            if value:
                keys.add(f'{field}:{value}')

        if not keys:
            keys.add(f'ordinal:{index + 1}')

        return keys

    def tapo_child_keys(child, index=0):
        identity = tapo_child_identity_keys(child)

        if identity:
            return identity

        return tapo_child_fallback_keys(child, index)

    def merge_tapo_child_metadata(old_children, new_children, parent=None):
        parent = parent if isinstance(parent, dict) else {}

        return merge_outlet_extender_child_metadata(
            old_children,
            new_children,
            parent.get('tapo_model') or parent.get('model') or '',
            parent.get('tapo_device_type') or parent.get('device_type') or '',
            parent.get('clientName') or parent.get('tapo_alias') or parent.get('alias') or parent.get('model') or 'Tapo Extender'
        )

    def update_tapo_child_settings(c, data):
        child_id = str(
            data.get('child_id')
            or data.get('childId')
            or data.get('tapoChildId')
            or ''
        ).strip()
        child_position = str(
            data.get('child_position')
            or data.get('childPosition')
            or data.get('position')
            or ''
        ).strip()
        child_index = str(
            data.get('child_index')
            or data.get('childIndex')
            or data.get('cli_index')
            or ''
        ).strip()

        if not child_id and not child_position and not child_index:
            return False

        children = c.get('tapo_children') if isinstance(c.get('tapo_children'), list) else []

        for index, child in enumerate(children):
            if not isinstance(child, dict):
                continue

            keys = tapo_child_keys(child, index)
            requested_keys = {child_id}

            if child_position:
                requested_keys.add(child_position)
                requested_keys.add(f'position:{child_position}')

            if child_index:
                requested_keys.add(child_index)
                requested_keys.add(f'index:{child_index}')
                requested_keys.add(f'cli_index:{child_index}')

            requested_keys = {key for key in requested_keys if key}

            if not (requested_keys & keys):
                continue

            new_name = clean_zone_name(data.get('clientName', data.get('newName', '')))
            if new_name:
                child['alias'] = new_name
                child['name'] = new_name

            if 'zone_name' in data or 'zoneName' in data:
                zone_name = clean_zone_name(data.get('zone_name', data.get('zoneName', '')))
                c['zone_name'] = zone_name

                for sibling in children:
                    if isinstance(sibling, dict):
                        sibling['zone_name'] = zone_name

            if 'tapo_room_power' in data or 'tapoRoomPower' in data:
                raw_room_power = data.get('tapo_room_power', data.get('tapoRoomPower'))
                child['tapo_room_power'] = raw_room_power is True or str(raw_room_power).lower() in {'1', 'true', 'yes', 'on'}

            if 'tapo_hide_dashboard' in data or 'tapoHideDashboard' in data:
                raw_hide_dashboard = data.get('tapo_hide_dashboard', data.get('tapoHideDashboard'))
                child['tapo_hide_dashboard'] = raw_hide_dashboard is True or str(raw_hide_dashboard).lower() in {'1', 'true', 'yes', 'on'}

            return True

        return False

    def read_tapo_recharge_rules():
        try:
            state = read_json(AUTOMATION_STATE_PATH)
        except Exception:
            state = {}

        rules = state.get(AUTOMATION_TYPE_TAPO_RECHARGE) if isinstance(state, dict) else {}

        if not isinstance(rules, dict):
            return {}

        return {
            str(deviceID): dict(config)
            for deviceID, config in rules.items()
            if isinstance(deviceID, str) and isinstance(config, dict)
        }

    def write_tapo_recharge_rules(rules):
        try:
            state = read_json(AUTOMATION_STATE_PATH)
        except Exception:
            state = {}

        if not isinstance(state, dict):
            state = {}

        clean_rules = {
            str(deviceID): dict(config)
            for deviceID, config in (rules or {}).items()
            if isinstance(deviceID, str) and isinstance(config, dict)
        }

        if clean_rules:
            state[AUTOMATION_TYPE_TAPO_RECHARGE] = clean_rules
        else:
            state.pop(AUTOMATION_TYPE_TAPO_RECHARGE, None)

        write_json_atomic(AUTOMATION_STATE_PATH, state)

        return clean_rules

    def tapo_recharge_client_name(c, deviceID=''):
        clean_deviceID = str(deviceID or '').strip()

        return next((
            name
            for name in (
                str((c or {}).get('clientName') or '').strip(),
                str((c or {}).get('client_name') or '').strip(),
                str((c or {}).get('deviceName') or '').strip(),
                str((c or {}).get('device_name') or '').strip(),
                str((c or {}).get('name') or '').strip(),
                str((c or {}).get('display_name') or '').strip(),
            )
            if name and name != clean_deviceID
        ), '')

    def tapo_recharge_rules():
        rules = read_tapo_recharge_rules()
        changed = False

        for client_key, c in CLIENTS.items():
            if not isinstance(c, dict):
                continue

            deviceID = str(c.get('deviceID') or client_key or '').strip()

            if not deviceID:
                continue

            legacy = c.pop('tapo_recharge', None)

            if not isinstance(legacy, dict):
                store = c.get('automations') if isinstance(c.get('automations'), dict) else {}
                legacy = store.pop(AUTOMATION_TYPE_TAPO_RECHARGE, None)

                if isinstance(c.get('automations'), dict) and not c.get('automations'):
                    c.pop('automations', None)

            if isinstance(legacy, dict) and legacy and deviceID not in rules:
                item = dict(legacy)
                item['type'] = AUTOMATION_TYPE_TAPO_RECHARGE
                rules[deviceID] = item
                changed = True

            item = rules.get(deviceID)
            clientName = tapo_recharge_client_name(c, deviceID)

            if (
                isinstance(item, dict)
                and clientName
                and clientName != deviceID
                and item.get('clientName') != clientName
            ):
                item['clientName'] = clientName
                changed = True

        if changed:
            write_tapo_recharge_rules(rules)

        return rules

    def tapo_recharge_existing(c):
        deviceID = str((c or {}).get('deviceID') or '').strip()

        if not deviceID:
            return {}

        item = tapo_recharge_rules().get(deviceID)

        return item if isinstance(item, dict) else {}

    def save_tapo_recharge_rule(deviceID, rule):
        rules = tapo_recharge_rules()
        rules[deviceID] = dict(rule)
        rules[deviceID]['type'] = AUTOMATION_TYPE_TAPO_RECHARGE

        return write_tapo_recharge_rules(rules)[deviceID]

    def tapo_recharge_android_client(c):
        return (
            c.get('provisioned')
            and c.get('battery') is not None
            and not client_has_role(c, CLIENT_ROLE_TAPO)
        )

    def tapo_recharge_power_targets():
        targets = []

        for c in CLIENTS.values():
            if not client_has_role(c, CLIENT_ROLE_TAPO):
                continue

            if not c.get('tapo_supports_power'):
                continue

            deviceID = c.get('deviceID')
            base_name = clean_zone_name(
                c.get('clientName')
                or c.get('tapo_alias')
                or c.get('tapo_model')
                or deviceID
            )

            if c.get('tapo_kind') == 'outlet_extender':
                children = c.get('tapo_children') if isinstance(c.get('tapo_children'), list) else []

                for index, child in enumerate(children):
                    if not isinstance(child, dict):
                        continue

                    child_id = str(
                        child.get('id')
                        or child.get('child_id')
                        or child.get('childId')
                        or child.get('position')
                        or child.get('index')
                        or index + 1
                    ).strip()

                    child_name = tapo_extender_child_display_name(c, child, index)

                    targets.append({
                        'deviceID': deviceID,
                        'targetID': f"{deviceID}|{child_id}",
                        'label': f"{base_name} · {child_name}",
                        'kind': c.get('tapo_kind'),
                        'child_id': child_id,
                        'child_index': child.get('cli_index', child.get('index', index)),
                        'child_position': child.get('position', ''),
                    })

                continue

            if c.get('tapo_kind') == 'plug':
                targets.append({
                    'deviceID': deviceID,
                    'targetID': f"{deviceID}|",
                    'label': base_name,
                    'kind': c.get('tapo_kind'),
                    'child_id': '',
                    'child_index': '',
                    'child_position': '',
                })

        return targets

    def tapo_recharge_rows():
        rows = []

        for deviceID, item in tapo_recharge_rules().items():
            if not isinstance(item, dict):
                continue

            c = CLIENTS.get(deviceID)

            if not isinstance(c, dict):
                c = next((
                    client
                    for client in CLIENTS.values()
                    if str(client.get('deviceID') or '').strip() == deviceID
                ), {})

            clientName = (
                tapo_recharge_client_name(c, deviceID)
                or tapo_recharge_client_name(item, deviceID)
            )
            targetID = str(item.get('targetID') or '').strip()
            targetDeviceID = str(item.get('targetDeviceID') or '').strip()

            if not targetDeviceID and targetID:
                targetDeviceID = targetID.split('|', 1)[0]

            rows.append({
                'deviceID': deviceID,
                'clientName': clientName,
                'enabled': item.get('enabled') is not False,
                'targetDeviceID': targetDeviceID,
                'targetID': targetID,
                'lowBattery': item.get('lowBattery', 20),
                'fullBattery': item.get('fullBattery', 100),
            })

        return rows

    def tapo_device_id(device):
        raw = (
            device.get('id')
            or device.get('mac')
            or device.get('device_id_hash')
            or device.get('ip')
        )

        clean = normalize_tapo_identity_value(raw).replace(':', '_').replace('-', '_')
        return f"tapo:{clean}" if clean else ''

    def tapo_device_type_label(kind):
        clean_kind = str(kind or 'device').strip().lower()
        labels = {
            'bulb': 'Bulb',
            'lightstrip': 'Lightstrip',
            'plug': 'Plug',
            'outlet_extender': 'Extender',
            'hub': 'Hub',
            'camera': 'Camera',
            'vacuum': 'Vac',
        }

        return labels.get(clean_kind, clean_kind.replace('_', ' ').title() if clean_kind else 'Device')

    def tapo_default_client_name(model, kind):
        clean_model = str(model or '').strip()
        label = tapo_device_type_label(kind)

        return clean_zone_name(f"Tapo {clean_model} {label}" if clean_model else f"Tapo {label}")

    def tapo_client_name_is_generated(value, deviceID='', model='', kind=''):
        text = str(value or '').strip()

        if not text:
            return True

        if deviceID and text == deviceID:
            return True

        if text.startswith('tapo-child:') or text.startswith('tapo:'):
            return True

        clean_model = str(model or '').strip()
        label = tapo_device_type_label(kind)
        generated_names = {
            tapo_default_client_name(clean_model, kind),
            clean_zone_name(f"Tapo {clean_model}") if clean_model else '',
            clean_zone_name(f"Tapo {label}"),
            clean_zone_name(f"Tapo {clean_model} Outlet") if clean_model else '',
        }

        return text in {name for name in generated_names if name}

    def upsert_tapo_detected_device(device):
        if not isinstance(device, dict) or device.get('supported') is not True:
            return None

        deviceID = tapo_device_id(device)

        if not deviceID:
            return None

        c = CLIENTS.get(deviceID)

        if not c:
            existing_id, existing = find_existing_tapo_client_for_device(deviceID, device)

            if existing:
                c = existing

                if existing_id and existing_id != deviceID:
                    CLIENTS.pop(existing_id, None)
                    CLIENTS[deviceID] = c
            else:
                c = init_client(deviceID)
                CLIENTS[deviceID] = c

        c['deviceID'] = deviceID
        c['detectedRole'] = CLIENT_ROLE_TAPO
        c['source'] = 'tapo'
        c['tapo_id'] = str(device.get('id') or '')
        c['tapo_mac'] = str(device.get('mac') or '')
        c['tapo_model'] = str(device.get('model') or '')
        c['tapo_device_type'] = str(device.get('device_type') or '')
        c['tapo_ip'] = str(device.get('ip') or '')
        c['tapo_alias'] = clean_zone_name(device.get('alias') or device.get('model') or deviceID)
        tapo_kind = str(device.get('kind') or 'unknown').strip().lower()
        tapo_dashboard_section = str(device.get('dashboard_section') or 'control').strip().lower()
        default_device_name = tapo_default_client_name(c['tapo_model'], tapo_kind)

        c['tapo_control_ready'] = device.get('control_ready')
        c['tapo_control_error'] = str(device.get('control_error') or '')

        if 'is_on' in device:
            c['tapo_is_on'] = device.get('is_on')

        c['tapo_brightness'] = device.get('brightness')
        c['tapo_dimmable'] = bool(device.get('dimmable'))

        c['tapo_kind'] = tapo_kind
        c['tapo_dashboard_section'] = tapo_dashboard_section

        c['tapo_is_bulb'] = bool(device.get('is_bulb'))
        c['tapo_is_plug'] = bool(device.get('is_plug'))
        c['tapo_is_outlet_extender'] = bool(device.get('is_outlet_extender'))
        c['tapo_is_hub'] = bool(device.get('is_hub') or tapo_kind == 'hub')
        c['tapo_is_camera'] = bool(device.get('is_camera'))

        if 'tapo_room_power' not in c:
            c['tapo_room_power'] = bool(c.get('tapo_is_bulb'))

        if 'tapo_hide_dashboard' not in c:
            c['tapo_hide_dashboard'] = False

        color_temperature = safe_int(device.get('color_temperature'))
        hue = safe_int(device.get('hue'))
        saturation = safe_int(device.get('saturation'))

        c['tapo_color_temperature'] = color_temperature if color_temperature is not None else c.get('tapo_color_temperature') or 4200
        c['tapo_hue'] = hue if hue is not None else c.get('tapo_hue') or 45
        c['tapo_saturation'] = saturation if saturation is not None else c.get('tapo_saturation') or 100

        c['tapo_battery'] = safe_int(
            device.get('battery')
            or device.get('battery_level')
            or device.get('battery_percent')
            or device.get('tapo_battery')
            or device.get('tapo_battery_level')
            or device.get('tapo_battery_percent')
        ) or c.get('tapo_battery')

        c['tapo_supports_power'] = bool(device.get('supports_power'))
        c['tapo_supports_brightness'] = bool(device.get('supports_brightness'))
        c['tapo_supports_color_temp'] = bool(device.get('supports_color_temp'))
        c['tapo_supports_color'] = bool(device.get('supports_color'))
        c['tapo_supports_energy'] = bool(device.get('supports_energy'))
        c['tapo_supports_rtsp'] = bool(device.get('supports_rtsp'))
        c['tapo_supports_onvif'] = bool(device.get('supports_onvif'))

        energy_fields = {
            'energy_available': 'tapo_energy_available',
            'energy_error': 'tapo_energy_error',
            'energy_updated_at': 'tapo_energy_updated_at',
            'current_power_w': 'tapo_current_power_w',
            'today_energy_kwh': 'tapo_today_energy_kwh',
            'month_energy_kwh': 'tapo_month_energy_kwh',
            'today_runtime_minutes': 'tapo_today_runtime_minutes',
            'month_runtime_minutes': 'tapo_month_runtime_minutes',
        }

        for source_key, client_key in energy_fields.items():
            if source_key in device:
                c[client_key] = device.get(source_key)

        if c.get('tapo_is_hub'):
            c['tapo_hide_dashboard'] = True

        c['tapo_rtsp_url'] = str(device.get('rtsp_url') or c.get('tapo_rtsp_url') or '')
        c['tapo_onvif_port'] = safe_int(device.get('onvif_port')) or c.get('tapo_onvif_port') or 2020
        if c.get('tapo_is_outlet_extender') and isinstance(device.get('children'), list):
            existing_children = c.get('tapo_children') if isinstance(c.get('tapo_children'), list) else []
            should_initialize_children = not c.get('tapo_children_initialized') and not existing_children

            c['tapo_children'] = merge_tapo_child_metadata(existing_children, device.get('children'), c)

            if should_initialize_children:
                normalize_tapo_extender_child_names(c)
                c['tapo_children_initialized'] = True
            elif not c.get('tapo_children_initialized') and c.get('tapo_children'):
                c['tapo_children_initialized'] = True
        else:
            c['tapo_children'] = []
            c.pop('tapo_children_initialized', None)
        if c.get('tapo_control_ready') is False:
            # A transient parent refresh failure must not erase the extender
            # children’s last confirmed power states. The shared extender merge
            # replaces those values only when a later refresh supplies new ones.
            c['tapo_is_on'] = None

        elif c.get('tapo_is_outlet_extender') and c.get('tapo_children'):
            # Derive the parent’s aggregate power state only from confirmed
            # child values returned by a successful extender refresh.
            child_states = [
                child.get('is_on')
                for child in c.get('tapo_children', [])
                if isinstance(child, dict)
            ]

            if any(state is True for state in child_states):
                c['tapo_is_on'] = True
            elif child_states and all(state is False for state in child_states):
                c['tapo_is_on'] = False
            elif child_states:
                c['tapo_is_on'] = None
        c['ip'] = c['tapo_ip']
        c['last_seen'] = now_epoch()

        if not c.get('provisioned'):
            c['clientRole'] = 'UNP'
            c['clientName'] = default_device_name if tapo_client_name_is_generated(
                c.get('clientName'),
                c.get('deviceID') or deviceID,
                c.get('tapo_model'),
                tapo_kind
            ) else c.get('clientName')
        else:
            c['clientName'] = default_device_name if tapo_client_name_is_generated(
                c.get('clientName'),
                c.get('deviceID') or deviceID,
                c.get('tapo_model'),
                tapo_kind
            ) else c.get('clientName') or default_device_name

            if c.get('tapo_is_camera'):
                c['clientRole'] = ['CAM', CLIENT_ROLE_TAPO]
            elif client_has_role(c, CLIENT_ROLE_TAPO):
                c['clientRole'] = [CLIENT_ROLE_TAPO]

        tapo_record_power_activity(c, c.get('tapo_is_on'))
        tapo_record_child_power_activities(c)

        return c

    def detect_tapo_clients(
        persist=True,
        broadcast=False,
        skip_if_busy=False
    ):
        locked = tapo_refresh_lock.acquire(blocking=not skip_if_busy)

        if not locked:
            return {
                'ok': True,
                'clients': [],
                'count': 0,
                'busy': True
            }

        try:
            devices = run_async(list_tapo_devices(force=True))
            detected = []

            with STATE_LOCK:
                for device in devices:
                    c = upsert_tapo_detected_device(device)

                    if c:
                        detected.append(snapshot_client(c))

                if persist:
                    save_state()

                if broadcast and detected:
                    broadcast_state()

            return {
                'ok': True,
                'clients': detected,
                'count': len(detected)
            }

        except Exception as e:
            return {
                'ok': False,
                'clients': [],
                'count': 0,
                'error': str(e)
            }

        finally:
            tapo_refresh_lock.release()

    def tapo_client_refresh_item(c):
        deviceID = c.get('deviceID')

        return {
            '_client_deviceID': deviceID,
            'id': c.get('tapo_id') or str(deviceID or '').replace('tapo:', ''),
            'ip': c.get('tapo_ip') or c.get('ip'),
            'mac': c.get('tapo_mac', ''),
            'alias': c.get('tapo_alias') or c.get('clientName') or deviceID,
            'model': c.get('tapo_model'),
            'device_type': c.get('tapo_device_type'),

            'kind': c.get('tapo_kind', 'unknown'),
            'dashboard_section': c.get('tapo_dashboard_section', 'control'),

            'control_ready': c.get('tapo_control_ready'),
            'control_error': c.get('tapo_control_error', ''),
            'is_on': c.get('tapo_is_on'),
            'brightness': c.get('tapo_brightness'),
            'dimmable': bool(c.get('tapo_dimmable')),

            'is_bulb': bool(c.get('tapo_is_bulb')),
            'is_plug': bool(c.get('tapo_is_plug')),
            'is_outlet_extender': bool(c.get('tapo_is_outlet_extender')),
            'is_hub': bool(c.get('tapo_is_hub')),
            'is_camera': bool(c.get('tapo_is_camera')),

            'supports_power': bool(c.get('tapo_supports_power')),
            'supports_brightness': bool(c.get('tapo_supports_brightness')),
            'supports_color_temp': bool(c.get('tapo_supports_color_temp')),
            'supports_color': bool(c.get('tapo_supports_color')),
            'supports_energy': bool(c.get('tapo_supports_energy')),

            'color_temperature': c.get('tapo_color_temperature', 4200),
            'hue': c.get('tapo_hue', 45),
            'saturation': c.get('tapo_saturation', 100),
            'battery': c.get('tapo_battery'),
            'children': c.get('tapo_children') if isinstance(c.get('tapo_children'), list) else [],
            'energy_available': c.get('tapo_energy_available'),
            'energy_error': c.get('tapo_energy_error', ''),
            'energy_updated_at': c.get('tapo_energy_updated_at'),
            'current_power_w': c.get('tapo_current_power_w'),
            'today_energy_kwh': c.get('tapo_today_energy_kwh'),
            'month_energy_kwh': c.get('tapo_month_energy_kwh'),
            'today_runtime_minutes': c.get('tapo_today_runtime_minutes'),
            'month_runtime_minutes': c.get('tapo_month_runtime_minutes'),
        }

    def tapo_client_needs_refresh(c):
        is_tapo = (
            client_has_role(c, CLIENT_ROLE_TAPO)
            or c.get('detectedRole') == CLIENT_ROLE_TAPO
            or str(c.get('deviceID') or '').startswith('tapo:')
        )

        if not is_tapo:
            return False

        if c.get('tapo_dashboard_section') == 'camera':
            return False

        if c.get('tapo_kind') not in {'bulb', 'lightstrip', 'plug', 'outlet_extender'}:
            return False

        return bool(c.get('tapo_supports_power'))

    def refresh_tapo_clients(
        persist=True,
        broadcast=False,
        skip_if_busy=False,
        energy_force=False,
    ):
        locked = tapo_refresh_lock.acquire(blocking=not skip_if_busy)

        if not locked:
            return {'ok': True, 'clients': [], 'count': 0, 'busy': True}

        try:
            with STATE_LOCK:
                refresh_items = [
                    tapo_client_refresh_item(c)
                    for c in CLIENTS.values()
                    if tapo_client_needs_refresh(c)
                ]

            if not refresh_items:
                return {'ok': True, 'clients': [], 'count': 0}

            devices = run_async(refresh_tapo_devices(
                refresh_items,
                energy_force=energy_force,
            ))
            refreshed = []
            recovery_targets = []
            power_changes = []

            with STATE_LOCK:
                for device in devices:
                    deviceID = device.get('_client_deviceID') or tapo_device_id(device)
                    c = CLIENTS.get(deviceID)

                    if not c:
                        continue

                    was_stale = c.get('tapo_control_ready') is False
                    was_on = tapo_power_state(c.get('tapo_is_on'))
                    previous_power_states = tapo_power_target_states(c)
                    updated = upsert_tapo_detected_device(device)

                    if updated:
                        changed_targets = tapo_changed_power_targets(
                            previous_power_states,
                            tapo_power_target_states(updated)
                        )

                        if changed_targets:
                            power_changes.append((deviceID, changed_targets))

                        turned_on = (
                            was_on is False
                            and tapo_power_state(updated.get('tapo_is_on')) is True
                        )

                        if was_stale or turned_on:
                            recovery_target = tapo_lighting_recovery_plan(
                                updated,
                                desired_only=turned_on and not was_stale,
                                force_lighting=was_stale or turned_on
                            )

                            if recovery_target:
                                recovery_targets.append(recovery_target)

                        refreshed.append(snapshot_client(updated))

                if persist:
                    save_state()

                if broadcast and refreshed:
                    broadcast_state()

            for deviceID, changed_targets in power_changes:
                tapo_publish_power_changes(deviceID, changed_targets)

            if power_changes:
                wake_automations = app.config.get('KOTIBOT_AUTOMATIONS_WAKE')

                if callable(wake_automations):
                    wake_automations()

            recovered = []

            for target in recovery_targets:
                try:
                    recovered_device = tapo_apply_lighting_recovery_plan(target)
                except Exception:
                    app.logger.exception('Tapo lighting recovery failed')
                    continue

                if recovered_device:
                    recovered.append(recovered_device)

            if recovered:
                with STATE_LOCK:
                    for result in recovered:
                        deviceID = result.get('deviceID')
                        c = CLIENTS.get(deviceID)

                        if not c:
                            continue

                        tapo_merge_recovery_device(c, result.get('device'))

                        pending_power = c.get('tapo_pending_power_commands')

                        if isinstance(pending_power, dict):
                            for key in result.get('pendingPowerKeys') or []:
                                pending_power.pop(str(key), None)

                            if not pending_power:
                                c.pop('tapo_pending_power_commands', None)

                        refreshed.append(snapshot_client(c))

                    if persist:
                        save_state()

                    if broadcast:
                        broadcast_state()

            return {
                'ok': True,
                'clients': refreshed,
                'count': len(refreshed)
            }

        except Exception as e:
            return {'ok': False, 'error': str(e)}

        finally:
            tapo_refresh_lock.release()

    def tapo_state_watcher_loop():
        if tapo_watcher_interval <= 0:
            return

        last_discovery_at = 0.0
        last_error_at = 0.0

        while True:
            now = time.monotonic()
            discovery_due = (
                tapo_discovery_interval > 0
                and now - last_discovery_at >= tapo_discovery_interval
            )

            if discovery_due:
                last_discovery_at = now
                operation = 'discovery'
                result = detect_tapo_clients(
                    persist=True,
                    broadcast=True,
                    skip_if_busy=True
                )
            else:
                operation = 'refresh'
                result = refresh_tapo_clients(
                    persist=False,
                    broadcast=True,
                    skip_if_busy=True
                )

            if not result.get('ok'):
                current_time = time.monotonic()

                if current_time - last_error_at >= 60:
                    last_error_at = current_time
                    app.logger.error(
                        'Tapo watcher %s failed: %s',
                        operation,
                        result.get('error') or 'unknown error',
                    )

            if tapo_watcher_stop is not None:
                if tapo_watcher_stop.wait(tapo_watcher_interval):
                    break
            else:
                time.sleep(tapo_watcher_interval)

    def retired_tapo_control_client(c):
        if not isinstance(c, dict):
            return False

        source = str(c.get('source') or '').strip().lower()
        device_id = str(c.get('deviceID') or '').strip().lower()
        kind = str(c.get('tapo_kind') or c.get('tapo_child_kind') or '').strip().lower()
        is_tapo = (
            source in {'tapo', 'tapo_child'}
            or c.get('detectedRole') == CLIENT_ROLE_TAPO
            or client_has_role(c, CLIENT_ROLE_TAPO)
            or device_id.startswith('tapo:')
            or device_id.startswith('tapo-child:')
        )

        return is_tapo and (
            source == 'tapo_child'
            or c.get('tapo_is_hub_child') is True
            or (
                bool(kind)
                and kind not in {
                    'bulb',
                    'lightstrip',
                    'plug',
                    'outlet_extender',
                    'hub',
                    'camera',
                }
            )
        )

    def normalize_loaded_tapo_clients():
        changed = False

        with STATE_LOCK:
            retired_ids = [
                device_id
                for device_id, c in CLIENTS.items()
                if retired_tapo_control_client(c)
            ]

            for device_id in retired_ids:
                CLIENTS.pop(device_id, None)
                changed = True

            for c in CLIENTS.values():
                if not isinstance(c, dict):
                    continue

                if c.get('tapo_kind') != 'outlet_extender':
                    if c.get('tapo_children'):
                        c['tapo_children'] = []
                        changed = True

                    if 'tapo_children_initialized' in c:
                        c.pop('tapo_children_initialized', None)
                        changed = True

                    continue

                if not isinstance(c.get('tapo_children'), list):
                    continue

                if normalize_tapo_extender_child_names(c):
                    c['tapo_children_initialized'] = True
                    changed = True

            if changed:
                save_state()

        return changed

    app.config['KOTIBOT_TAPO_NORMALIZE_LOADED_CLIENTS'] = normalize_loaded_tapo_clients
    app.config['KOTIBOT_TAPO_STATE_WATCHER_LOOP'] = tapo_state_watcher_loop

    register_tapo_energy_routes(app, {
        'state_lock': STATE_LOCK,
        'clients': CLIENTS,
        'refresh_clients': refresh_tapo_clients,
    })

    @app.post('/api/tapo/detect')
    def api_tapo_detect():
        result = detect_tapo_clients(
            persist=True,
            broadcast=False,
            skip_if_busy=False
        )

        if not result.get('ok'):
            return jsonify(result), 500

        return jsonify(result)

    @app.post('/api/tapo/refresh')
    def api_tapo_refresh():
        result = refresh_tapo_clients(persist=True, skip_if_busy=True)

        if result.get('busy'):
            return jsonify(result)

        if not result.get('ok'):
            return jsonify(result), 500

        return jsonify(result)
    
    @app.get('/api/tapo/recharge')
    def api_tapo_recharge_status():
        with STATE_LOCK:
            android_clients = [
                snapshot_client(c)
                for c in CLIENTS.values()
                if tapo_recharge_android_client(c)
            ]

            power_targets = tapo_recharge_power_targets()
            recharge = tapo_recharge_rows()

        return jsonify({
            'ok': True,
            'loaded': True,
            'clients': android_clients,
            'targets': power_targets,
            'recharge': recharge,
        })

    @app.post('/api/tapo/recharge')
    def api_save_tapo_recharge():
        data = request.get_json(silent=True) or {}
        deviceID = str(data.get('deviceID') or '').strip()
        targetID = str(data.get('targetID') or '').strip()

        if not deviceID:
            return jsonify({'ok': False, 'error': 'Missing Android client'}), 400

        if not targetID:
            return jsonify({'ok': False, 'error': 'Missing Tapo power target'}), 400

        with STATE_LOCK:
            c = CLIENTS.get(deviceID)

            if not c or not tapo_recharge_android_client(c):
                return jsonify({'ok': False, 'error': 'Android client not found'}), 404

            targets = tapo_recharge_power_targets()
            target = next((item for item in targets if item.get('targetID') == targetID), None)

            if not target:
                return jsonify({'ok': False, 'error': 'Tapo power target not found'}), 404

            rule = save_tapo_recharge_rule(deviceID, {
                'clientName': tapo_recharge_client_name(c, deviceID),
                'enabled': data.get('enabled') is not False,
                'targetID': targetID,
                'targetDeviceID': target.get('deviceID', ''),
                'child_id': target.get('child_id', ''),
                'child_index': target.get('child_index', ''),
                'child_position': target.get('child_position', ''),
                'lowBattery': 20,
                'fullBattery': 100,
            })

            save_state()

            return jsonify({
                'ok': True,
                'recharge': rule,
                'rules': tapo_recharge_rows(),
            })

    @app.post('/api/tapo/remove-addon')
    def api_tapo_remove_addon():
        removed = []

        with STATE_LOCK:
            for deviceID, c in list(CLIENTS.items()):
                is_tapo = (
                    client_has_role(c, CLIENT_ROLE_TAPO)
                    or c.get('detectedRole') == CLIENT_ROLE_TAPO
                    or str(deviceID).startswith('tapo:')
                )

                if not is_tapo:
                    continue

                removed.append(deviceID)
                CLIENTS.pop(deviceID, None)

            save_state()

        return jsonify({'ok': True, 'removed': len(removed), 'deviceIDs': removed})
    
    @app.post('/api/tapo/remove-client')
    def api_tapo_remove_client():
        d = request.get_json(silent=True) or {}
        deviceID = str(d.get('deviceID') or '').strip()

        if not deviceID:
            return jsonify({'ok': False, 'error': 'Missing Tapo client deviceID'}), 400

        with STATE_LOCK:
            c = CLIENTS.get(deviceID)

            if not c:
                return jsonify({'ok': False, 'error': 'Tapo client not found'}), 404

            is_tapo = (
                client_has_role(c, CLIENT_ROLE_TAPO)
                or c.get('detectedRole') == CLIENT_ROLE_TAPO
                or str(deviceID).startswith('tapo:')
            )

            if not is_tapo:
                return jsonify({'ok': False, 'error': 'Client is not a Tapo device'}), 400

            removed = CLIENTS.pop(deviceID, None)

            save_state()

        if removed and removed.get('tapo_kind') == 'camera':
            stop_tapo_camera_recording(deviceID)
            stop_tapo_camera_stream(deviceID)

        return jsonify({
            'ok': True,
            'deviceID': deviceID,
            'removed': bool(removed)
        })
    
    def tapo_command_item_from_client(c, deviceID):
        return {
            'id': c.get('tapo_id') or str(deviceID).replace('tapo:', ''),
            'ip': c.get('tapo_ip') or c.get('ip'),
            'model': c.get('tapo_model'),
            'device_type': c.get('tapo_device_type'),

            'kind': c.get('tapo_kind', 'unknown'),
            'dashboard_section': c.get('tapo_dashboard_section', 'control'),

            'control_ready': c.get('tapo_control_ready'),
            'control_error': c.get('tapo_control_error', ''),
            'is_on': c.get('tapo_is_on'),
            'brightness': safe_int(c.get('tapo_brightness')),
            'color_temperature': safe_int(c.get('tapo_color_temperature')),
            'hue': safe_int(c.get('tapo_hue')),
            'saturation': safe_int(c.get('tapo_saturation')),

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

    def update_tapo_client_from_command_result(deviceID, result, action='', value=None, lighting_mode=''):
        power_changes = []

        with STATE_LOCK:
            c = CLIENTS.get(deviceID)

            if not c:
                return None

            previous_power_states = tapo_power_target_states(c)
            device = result.get('device') if isinstance(result.get('device'), dict) else {}

            if 'control_ready' in device:
                c['tapo_control_ready'] = device.get('control_ready')

            if 'control_error' in device:
                c['tapo_control_error'] = str(device.get('control_error') or '')

            if 'is_on' in device:
                c['tapo_is_on'] = device.get('is_on')

            if 'brightness' in device:
                c['tapo_brightness'] = safe_int(device.get('brightness'))

            if 'color_temperature' in device:
                c['tapo_color_temperature'] = safe_int(device.get('color_temperature'))

            if 'hue' in device:
                c['tapo_hue'] = safe_int(device.get('hue'))

            if 'saturation' in device:
                c['tapo_saturation'] = safe_int(device.get('saturation'))

            if c.get('tapo_is_outlet_extender') and isinstance(device.get('children'), list):
                existing_children = c.get('tapo_children') if isinstance(c.get('tapo_children'), list) else []
                should_initialize_children = not c.get('tapo_children_initialized') and not existing_children

                c['tapo_children'] = merge_tapo_child_metadata(existing_children, device.get('children'), c)

                if should_initialize_children:
                    normalize_tapo_extender_child_names(c)
                    c['tapo_children_initialized'] = True
                elif not c.get('tapo_children_initialized') and c.get('tapo_children'):
                    c['tapo_children_initialized'] = True

                if c.get('tapo_control_ready') is not False:
                    child_states = [
                        child.get('is_on')
                        for child in c.get('tapo_children', [])
                        if isinstance(child, dict)
                    ]

                    if any(state is True for state in child_states):
                        c['tapo_is_on'] = True
                    elif child_states and all(state is False for state in child_states):
                        c['tapo_is_on'] = False
                    elif child_states:
                        c['tapo_is_on'] = None

            if 'battery' in device:
                c['tapo_battery'] = safe_int(device.get('battery'))

            if 'battery_level' in device:
                c['tapo_battery_level'] = safe_int(device.get('battery_level'))

            if 'battery_percent' in device:
                c['tapo_battery_percent'] = safe_int(device.get('battery_percent'))

            tapo_apply_lighting_desired_value_to_client(c, action, value, lighting_mode)
            tapo_clear_pending_power_command(c, action, value)
            tapo_record_power_activity(c, c.get('tapo_is_on'))
            tapo_record_child_power_activities(c)

            save_state()
            updated_client = snapshot_client(c)
            power_changes = tapo_changed_power_targets(
                previous_power_states,
                tapo_power_target_states(c)
            )

        tapo_publish_power_changes(deviceID, power_changes)
        return updated_client

    def tapo_defer_failed_state_command(deviceID, action, value=None, lighting_mode='', error=''):
        lighting_actions = {
            'brightness', 'brightness_no_power',
            'color_temperature', 'color_temperature_no_power',
            'color', 'color_no_power',
        }
        action = str(action or '').strip().lower()

        with STATE_LOCK:
            c = CLIENTS.get(deviceID)

            if not c or not client_has_role(c, CLIENT_ROLE_TAPO):
                return None

            is_light = str(c.get('tapo_kind') or '').lower() in {'bulb', 'lightstrip'}
            queued = tapo_record_pending_power_command(c, action, value)

            if is_light and action in lighting_actions:
                tapo_apply_lighting_desired_value_to_client(c, action, value, lighting_mode)
                queued = True

            if not queued:
                return None

            c['tapo_control_ready'] = False
            c['tapo_control_error'] = str(error or 'Tapo command deferred')
            c['tapo_is_on'] = None
            save_state()

            return {
                'ok': True,
                'deferred': True,
                'deviceID': deviceID,
                'action': action,
                'error': str(error or ''),
                'client': snapshot_client(c),
            }

    @app.post('/api/tapo/client-command-batch')
    def api_tapo_client_command_batch():
        d = request.get_json(silent=True) or {}
        raw_active_home_mode = d.get('activeHomeMode')
        active_home_mode = tapo_home_lighting_mode(raw_active_home_mode)
        raw_commands = d.get('commands')
        commands = []

        if raw_active_home_mode is not None and not active_home_mode:
            return jsonify({'ok': False, 'error': 'Invalid home lighting mode'}), 400

        if isinstance(raw_commands, list):
            for raw in raw_commands:
                if not isinstance(raw, dict):
                    continue

                deviceID = str(raw.get('deviceID') or '').strip()
                action = str(raw.get('action') or '').strip().lower()
                value = raw.get('value', raw.get('brightness'))
                lighting_mode = tapo_lighting_preset_mode(raw.get('lightingMode') or raw.get('lighting_mode') or raw.get('mode'))

                if action == 'color_temp':
                    action = 'color_temperature'

                if deviceID and action:
                    commands.append({
                        'deviceID': deviceID,
                        'action': action,
                        'value': value,
                        'lightingMode': lighting_mode
                    })
        else:
            action = str(d.get('action') or '').strip().lower()
            value = d.get('value', d.get('brightness'))
            lighting_mode = tapo_lighting_preset_mode(d.get('lightingMode') or d.get('lighting_mode') or d.get('mode'))

            if action == 'color_temp':
                action = 'color_temperature'

            deviceIDs = d.get('deviceIDs') or d.get('device_ids') or []

            if isinstance(deviceIDs, str):
                deviceIDs = [
                    deviceID.strip()
                    for deviceID in deviceIDs.split(',')
                    if deviceID.strip()
                ]

            if isinstance(deviceIDs, list):
                for deviceID in deviceIDs:
                    deviceID = str(deviceID or '').strip()

                    if deviceID and action:
                        commands.append({
                            'deviceID': deviceID,
                            'action': action,
                            'value': value,
                            'lightingMode': lighting_mode
                        })

        if not commands and not active_home_mode:
            return jsonify({'ok': False, 'error': 'Missing Tapo batch commands'}), 400

        lighting_state = None

        if active_home_mode:
            with STATE_LOCK:
                lighting_state = read_tapo_lighting_state()
                lighting_state.setdefault('activeSchemes', {})['home'] = active_home_mode
                lighting_state = write_tapo_lighting_state(lighting_state)

        prepared = []

        with STATE_LOCK:
            for command in commands:
                deviceID = command.get('deviceID')
                c = CLIENTS.get(deviceID)

                if not c or not client_has_role(c, CLIENT_ROLE_TAPO):
                    prepared.append({
                        'deviceID': deviceID,
                        'ok': False,
                        'error': 'Tapo client not found'
                    })
                    continue

                prepared.append({
                    'deviceID': deviceID,
                    'action': command.get('action'),
                    'value': command.get('value'),
                    'lightingMode': command.get('lightingMode') or '',
                    'item': tapo_command_item_from_client(c, deviceID)
                })

        runnable = [
            command
            for command in prepared
            if command.get('item')
        ]

        results = [
            command
            for command in prepared
            if not command.get('item')
        ]

        def run_one(command):
            deviceID = command.get('deviceID')
            action = command.get('action')
            value = command.get('value')

            # IMPORTANT: Commands for each device run serially. Resolve a fresh
            # item before every command so an `on` command updates the power
            # state seen by the following `*_no_power` scene commands.
            #
            # Reusing command['item'] here preserves the bulb's pre-batch "off"
            # snapshot and makes Day/Evening require a second button click.
            with STATE_LOCK:
                c = CLIENTS.get(deviceID)
                item = (
                    tapo_command_item_from_client(c, deviceID)
                    if c and client_has_role(c, CLIENT_ROLE_TAPO)
                    else None
                )

            if not item:
                return {
                    'ok': False,
                    'retryable': False,
                    'deviceID': deviceID,
                    'action': action,
                    'error': 'Tapo client not found'
                }

            try:
                result = run_async(set_tapo_device_from_info(item, action, value))
                updated_client = update_tapo_client_from_command_result(
                    deviceID,
                    result,
                    action,
                    value,
                    command.get('lightingMode') or ''
                )
                lighting_recovered = False

                if action == 'on':
                    recovered_client = tapo_recover_desired_lighting_for_device(deviceID)

                    if recovered_client:
                        updated_client = recovered_client
                        lighting_recovered = True

                return {
                    'ok': True,
                    'deviceID': deviceID,
                    'action': action,
                    'device': result.get('device', {}),
                    'client': updated_client,
                    'lightingRecovered': lighting_recovered
                }
            except ValueError as e:
                deferred = tapo_defer_failed_state_command(
                    deviceID,
                    action,
                    value,
                    command.get('lightingMode') or '',
                    e
                )

                if deferred:
                    return deferred

                return {
                    'ok': False,
                    'retryable': False,
                    'deviceID': deviceID,
                    'action': action,
                    'error': str(e)
                }
            except Exception as e:
                deferred = tapo_defer_failed_state_command(
                    deviceID,
                    action,
                    value,
                    command.get('lightingMode') or '',
                    e
                )

                if deferred:
                    return deferred

                return {
                    'ok': False,
                    'retryable': True,
                    'deviceID': deviceID,
                    'action': action,
                    'error': str(e)
                }

        runnable_by_device = {}

        for command in runnable:
            runnable_by_device.setdefault(command.get('deviceID'), []).append(command)

        def run_device_commands(device_commands):
            device_results = []

            for command in device_commands:
                result = None

                for attempt in range(3):
                    result = run_one(command)

                    if result.get('ok') or result.get('retryable') is False:
                        break

                    if attempt < 2:
                        time.sleep(0.5 * (attempt + 1))

                result.pop('retryable', None)
                device_results.append(result)

            return device_results

        futures = [
            tapo_device_command_executor.submit(run_device_commands, device_commands)
            for device_commands in runnable_by_device.values()
        ]

        for future in as_completed(futures):
            results.extend(future.result())

        ok_count = sum(1 for result in results if result.get('ok'))
        response = {
            'ok': bool(active_home_mode) or ok_count > 0,
            'count': len(results),
            'okCount': ok_count,
            'failedCount': len(results) - ok_count,
            'results': results
        }

        if lighting_state:
            response.update(lighting_state)

        return jsonify(response)
    
    @app.post('/api/tapo/client-command')
    def api_tapo_client_command():
        d = request.get_json(silent=True) or {}
        deviceID = d.get('deviceID')
        tapo_id = str(d.get('id') or d.get('tapo_id') or '').strip()
        action = str(d.get('action') or '').strip()
        value = d.get('value', d.get('brightness'))
        lighting_mode = tapo_lighting_preset_mode(d.get('lightingMode') or d.get('lighting_mode') or d.get('mode'))

        action = action.lower()

        if action == 'color_temp':
            action = 'color_temperature'

        with STATE_LOCK:
            c = CLIENTS.get(deviceID) if deviceID else None

            if not c and tapo_id:
                c = next(
                    (
                        item for item in CLIENTS.values()
                        if (
                            client_has_role(item, CLIENT_ROLE_TAPO)
                            or item.get('detectedRole') == CLIENT_ROLE_TAPO
                            or str(item.get('deviceID') or '').startswith('tapo:')
                        )
                        and str(item.get('tapo_id') or '').strip() == tapo_id
                    ),
                    None
                )

            if action in {'remove', 'delete', 'remove_device'}:
                if not c:
                    return jsonify({'ok': False, 'error': 'Tapo client not found'}), 404

                deviceID = c.get('deviceID') or deviceID

                is_tapo = (
                    client_has_role(c, CLIENT_ROLE_TAPO)
                    or c.get('detectedRole') == CLIENT_ROLE_TAPO
                    or str(deviceID).startswith('tapo:')
                )

                if not is_tapo:
                    return jsonify({'ok': False, 'error': 'Client is not a Tapo device'}), 400

                if c.get('tapo_kind') == 'camera':
                    stop_tapo_camera_recording(deviceID)
                    stop_tapo_camera_stream(deviceID)

                removed = CLIENTS.pop(deviceID, None)
                save_state()

                return jsonify({
                    'ok': True,
                    'deviceID': deviceID,
                    'removed': bool(removed)
                })

            if not c or not client_has_role(c, CLIENT_ROLE_TAPO):
                return jsonify({'ok': False, 'error': 'Tapo client not found'}), 404

            deviceID = c.get('deviceID')

            child_settings_updated = update_tapo_child_settings(c, d)

            if not child_settings_updated:
                new_name = clean_zone_name(d.get('clientName', d.get('newName', '')))
                if new_name:
                    c['clientName'] = new_name
                    c['tapo_alias'] = new_name

                if 'zone_name' in d or 'zoneName' in d:
                    c['zone_name'] = clean_zone_name(d.get('zone_name', d.get('zoneName', '')))

                if 'tapo_room_power' in d or 'tapoRoomPower' in d:
                    raw_room_power = d.get('tapo_room_power', d.get('tapoRoomPower'))
                    c['tapo_room_power'] = raw_room_power is True or str(raw_room_power).lower() in {'1', 'true', 'yes', 'on'}

                if 'tapo_hide_dashboard' in d or 'tapoHideDashboard' in d:
                    raw_hide_dashboard = d.get('tapo_hide_dashboard', d.get('tapoHideDashboard'))
                    c['tapo_hide_dashboard'] = raw_hide_dashboard is True or str(raw_hide_dashboard).lower() in {'1', 'true', 'yes', 'on'}

            if 'tapo_room_power_children' in d or 'tapoRoomPowerChildren' in d:
                raw_room_power_children = d.get('tapo_room_power_children', d.get('tapoRoomPowerChildren'))

                if isinstance(raw_room_power_children, dict):
                    c['tapo_room_power_children'] = {
                        str(key).strip(): value is True or str(value).lower() in {'1', 'true', 'yes', 'on'}
                        for key, value in raw_room_power_children.items()
                        if str(key).strip()
                    }

            if action in ('preview', 'camera_preview', 'camera_viewer'):
                if c.get('tapo_kind') != 'camera':
                    return jsonify({'ok': False, 'error': 'Tapo preview is only available for cameras'}), 400

                active = d.get('active')
                active = active is True or str(active).lower() in {'1', 'true', 'yes', 'on'}

                viewers = c.setdefault('preview_viewers', {})
                viewer_id = str(d.get('viewerId') or 'dashboard').strip() or 'dashboard'

                was_requested = bool(c.get('preview_requested'))
                was_camera_enabled = bool(c.get('camera_enabled') or c.get('cameraEnabled'))
                previous_hls_url = c.get('tapo_hls_url') or ''

                if active:
                    viewers[viewer_id] = now_epoch()
                else:
                    viewers.pop(viewer_id, None)

                has_viewers = bool(viewers)
                hls_url = c.get('tapo_hls_url') or f"/api/tapo/camera-hls/{tapo_stream_key(deviceID)}/index.m3u8"

                if has_viewers:
                    try:
                        hls_url = start_tapo_camera_stream(c)
                    except Exception as e:
                        return jsonify({'ok': False, 'error': str(e)}), 500
                else:
                    stop_tapo_camera_stream(deviceID)

                prune_tapo_camera_streams()

                c['preview_requested'] = has_viewers
                c['camera_enabled'] = has_viewers
                c['cameraEnabled'] = 1 if has_viewers else 0
                c['tapo_hls_url'] = hls_url

                changed = (
                    was_requested != has_viewers
                    or was_camera_enabled != has_viewers
                    or previous_hls_url != hls_url
                )

                if changed:
                    save_state()

                return jsonify({
                    'ok': True,
                    'deviceID': deviceID,
                    'previewRequested': has_viewers,
                    'cameraEnabled': 1 if has_viewers else 0,
                    'tapo_hls_url': hls_url
                })

            if action in ('record', 'recording', 'camera_record'):
                if c.get('tapo_kind') != 'camera':
                    return jsonify({'ok': False, 'error': 'Tapo recording is only available for cameras'}), 400

                active = d.get('active', value)
                active = active is True or str(active).lower() in {'1', 'true', 'yes', 'on'}

                try:
                    if active:
                        recording_file = start_tapo_camera_recording(c)
                        c['tapo_recording'] = True
                        c['tapo_recording_enabled'] = True
                        c['tapo_recording_file'] = recording_file
                    else:
                        recording_file = stop_tapo_camera_recording(deviceID)
                        c['tapo_recording'] = False
                        c['tapo_recording_enabled'] = False

                        if recording_file:
                            c['tapo_recording_file'] = recording_file

                except Exception as e:
                    return jsonify({'ok': False, 'error': str(e)}), 500

                save_state()
                return jsonify({
                    'ok': True,
                    'deviceID': deviceID,
                    'recording': bool(c.get('tapo_recording')),
                    'recordingEnabled': bool(c.get('tapo_recording_enabled')),
                    'tapo_recording': bool(c.get('tapo_recording')),
                    'tapo_recording_enabled': bool(c.get('tapo_recording_enabled')),
                    'tapo_recording_file': c.get('tapo_recording_file', ''),
                    'client': snapshot_client(c)
                })

            if action == 'rotation':
                if c.get('tapo_kind') != 'camera':
                    return jsonify({'ok': False, 'error': 'Tapo rotation is only available for cameras'}), 400

                rotation = safe_int(value)

                if rotation is None:
                    rotation = 0

                rotation = rotation % 360
                c.setdefault('preview_by_lens', {}).setdefault('tapo', {})['rotation'] = rotation
                c['selected_camera'] = 'tapo'

                save_state()
                return jsonify({
                    'ok': True,
                    'deviceID': deviceID,
                    'previewRotation': rotation
                })

            item = {
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
                'is_on': c.get('tapo_is_on'),
                'brightness': c.get('tapo_brightness'),
                'color_temperature': c.get('tapo_color_temperature'),
                'hue': c.get('tapo_hue'),
                'saturation': c.get('tapo_saturation'),
                'children': c.get('tapo_children') if isinstance(c.get('tapo_children'), list) else [],
                'battery': c.get('tapo_battery'),
                'battery_level': c.get('tapo_battery_level'),
                'battery_percent': c.get('tapo_battery_percent'),
            }

            if not action:
                save_state()
                return jsonify({'ok': True, 'deviceID': deviceID, 'client': snapshot_client(c)})

        lighting_recovered = False

        if action == 'on':
            recovered_client = tapo_recover_desired_lighting_for_device(
                deviceID,
                allow_off=True,
                desired_only=False,
                force_lighting=False
            )

            if recovered_client:
                item = tapo_command_item_from_client(
                    recovered_client,
                    deviceID
                )
                lighting_recovered = True

        try:
            result = run_async(set_tapo_device_from_info(item, action, value))
        except ValueError as e:
            deferred = tapo_defer_failed_state_command(
                deviceID,
                action,
                value,
                lighting_mode,
                e
            )

            if deferred:
                return jsonify(deferred)

            return jsonify({'ok': False, 'error': str(e)}), 400
        except Exception as e:
            deferred = tapo_defer_failed_state_command(
                deviceID,
                action,
                value,
                lighting_mode,
                e
            )

            if deferred:
                return jsonify(deferred)

            return jsonify({'ok': False, 'error': str(e)}), 500

        updated_client = update_tapo_client_from_command_result(
            deviceID,
            result,
            action,
            value,
            lighting_mode
        )

        return jsonify({
            'ok': True,
            'device': result.get('device', {}),
            'deviceID': deviceID,
            'client': updated_client,
            'lightingRecovered': lighting_recovered
        })

    @app.get('/api/tapo/lighting-state')
    def api_tapo_lighting_state():
        with STATE_LOCK:
            state = read_tapo_lighting_state()

        return jsonify({
            'ok': True,
            **state
        })

    @app.post('/api/tapo/lighting-state')
    def api_tapo_save_lighting_state():
        d = request.get_json(silent=True) or {}

        with STATE_LOCK:
            current = read_tapo_lighting_state()
            merged = {
                'schemes': d.get('schemes') if isinstance(d.get('schemes'), dict) else current.get('schemes', {}),
                'activeSchemes': d.get('activeSchemes') if isinstance(d.get('activeSchemes'), dict) else current.get('activeSchemes', {}),
                'modeConfig': d.get('modeConfig') if isinstance(d.get('modeConfig'), dict) else current.get('modeConfig', {})
            }
            state = write_tapo_lighting_state(merged)

        return jsonify({
            'ok': True,
            **state
        })
    
    @app.get('/api/tapo/debug-discovery')
    def api_tapo_debug_discovery():
        started = time.time()

        try:
            raw = debug_tapo_discovery_text()
        except Exception as e:
            return jsonify({
                'ok': False,
                'stage': 'debug_tapo_discovery_text',
                'seconds': round(time.time() - started, 2),
                'error': str(e),
            }), 500

        return jsonify({
            'ok': True,
            'seconds': round(time.time() - started, 2),
            'raw': raw,
        })

    @app.get('/api/tapo/camera-hls/<stream_key>/<path:filename>')
    def api_tapo_camera_hls(stream_key, filename):
        safe_key = tapo_stream_key(stream_key)
        safe_name = str(filename or "").strip()

        if safe_name not in ("index.m3u8",) and not safe_name.endswith(".ts"):
            return jsonify({'ok': False, 'error': 'Invalid stream file'}), 400

        stream_dir = TAPO_CAMERA_HLS_ROOT / safe_key

        if not stream_dir.exists():
            return Response("", status=404, mimetype="application/vnd.apple.mpegurl")

        touch_tapo_camera_stream(safe_key)

        target = stream_dir / safe_name

        if safe_name.endswith(".m3u8") and not target.exists():
            ready_until = time.time() + 6.0

            while time.time() < ready_until:
                if target.exists():
                    break

                time.sleep(.1)

        if not target.exists():
            return Response("", status=404, mimetype="application/vnd.apple.mpegurl")

        if safe_name.endswith(".m3u8"):
            response = send_from_directory(
                stream_dir,
                safe_name,
                mimetype="application/vnd.apple.mpegurl",
                max_age=0
            )
        else:
            response = send_from_directory(
                stream_dir,
                safe_name,
                mimetype="video/mp2t",
                max_age=0
            )

        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"

        for header in (
            "Connection",
            "Keep-Alive",
            "Proxy-Authenticate",
            "Proxy-Authorization",
            "TE",
            "Trailer",
            "Transfer-Encoding",
            "Upgrade",
        ):
            response.headers.pop(header, None)

        return response
    
    @app.get('/api/tapo/devices')
    def api_tapo_devices():
        force = request.args.get('force') == '1'

        try:
            return jsonify({'ok': True, 'devices': run_async(list_tapo_devices(force=force))})
        except Exception as e:
            return jsonify({'ok': False, 'error': str(e)}), 500

    @app.post('/api/tapo/device')
    def api_tapo_device():
        data = request.get_json(silent=True) or {}

        device_id = data.get('id') or data.get('device_id') or data.get('deviceID')
        action = data.get('action')
        value = data.get('value', data.get('brightness'))

        if not device_id:
            return jsonify({'ok': False, 'error': 'missing device id'}), 400

        if not action:
            return jsonify({'ok': False, 'error': 'missing action'}), 400

        try:
            return jsonify(run_async(set_tapo_device(device_id, action, value)))
        except KeyError:
            return jsonify({'ok': False, 'error': 'unknown device'}), 404
        except ValueError as e:
            return jsonify({'ok': False, 'error': str(e)}), 400
        except TypeError as e:
            return jsonify({'ok': False, 'error': str(e)}), 400
        except Exception as e:
            return jsonify({'ok': False, 'error': str(e)}), 500

    @app.post('/api/tapo/<device_id>/on')
    def api_tapo_on(device_id):
        try:
            return jsonify(run_async(tapo_on(device_id)))
        except KeyError:
            return jsonify({'ok': False, 'error': 'unknown device'}), 404
        except Exception as e:
            return jsonify({'ok': False, 'error': str(e)}), 500

    @app.post('/api/tapo/<device_id>/off')
    def api_tapo_off(device_id):
        try:
            return jsonify(run_async(tapo_off(device_id)))
        except KeyError:
            return jsonify({'ok': False, 'error': 'unknown device'}), 404
        except Exception as e:
            return jsonify({'ok': False, 'error': str(e)}), 500

    @app.post('/api/tapo/<device_id>/brightness')
    def api_tapo_brightness(device_id):
        data = request.get_json(silent=True) or {}

        try:
            brightness = int(data.get('brightness', 0))
        except (TypeError, ValueError):
            return jsonify({'ok': False, 'error': 'brightness must be 1-100'}), 400

        try:
            return jsonify(run_async(tapo_brightness(device_id, brightness)))
        except KeyError:
            return jsonify({'ok': False, 'error': 'unknown device'}), 404
        except ValueError as e:
            return jsonify({'ok': False, 'error': str(e)}), 400
        except TypeError as e:
            return jsonify({'ok': False, 'error': str(e)}), 400
        except Exception as e:
            return jsonify({'ok': False, 'error': str(e)}), 500
"""Scheduled and battery-driven automation maintenance.

General flow:
1. Flask routes read and validate automation configuration.
2. Configuration is stored in automations_state.json.
3. Android battery telemetry wakes the maintenance loop immediately.
4. The loop snapshots required state while holding STATE_LOCK.
5. Tapo network operations run without STATE_LOCK.
6. Results are reconciled under STATE_LOCK and persisted once.
7. The daily reset runs once per date at or after its configured hour.

Event-driven door, motion, and environmental automations are handled separately
by trigger_routes.py.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from threading import Event
import os
import time
from flask import jsonify, request
import importlib.util
import sys
import types

from server_core.io import read_json, write_json_atomic


def _load_client_tapo_control():
    package_name = 'kotibot_client_tapo'
    module_name = f'{package_name}.tapo_control'
    package_dir = Path(__file__).resolve().parents[1] / 'client-tapo'
    module_path = package_dir / 'tapo_control.py'

    # tapo_routes.py normally imports this module first. Reuse that exact
    # module so discovery caches, device handles, camera state, and locks are
    # shared by interactive controls and automations.
    existing = sys.modules.get(module_name)
    if existing is not None:
        return existing

    package = sys.modules.get(package_name)
    if package is None:
        package = types.ModuleType(package_name)
        package.__path__ = [str(package_dir)]
        sys.modules[package_name] = package

    spec = importlib.util.spec_from_file_location(
        module_name,
        module_path
    )

    if not spec or not spec.loader:
        raise ImportError(f'Unable to load Tapo control module: {module_path}')

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module

_tapo_control = None

def _get_tapo_control():
    global _tapo_control

    if _tapo_control is None:
        _tapo_control = _load_client_tapo_control()

    return _tapo_control


def run_async(*args, **kwargs):
    return _get_tapo_control().run_async(*args, **kwargs)


def set_tapo_device_from_info(*args, **kwargs):
    return _get_tapo_control().set_tapo_device_from_info(*args, **kwargs)

AUTOMATION_TYPE_TAPO_RECHARGE = 'tapo_recharge_android_battery'
AUTOMATION_TYPE_TAPO_DAY_RESET = 'tapo_day_reset'
AUTOMATION_TYPE_DEVICE = 'device_automation'

TAPO_DAY_RESET_MODES = {
    'evening',
    'night',
    'nighttime',
    'nightlight',
    'movie',
    'movietime',
    'movie_time',
    'custom',
}

def register_automation_routes(app, ctx):
    automation_state_path = Path(ctx['automation_state_file'])
    tapo_lighting_state_path = Path(ctx['tapo_lighting_state_file'])
    STATE_LOCK = ctx['state_lock']
    CLIENTS = ctx['clients']
    CLIENT_ROLE_CAM = ctx['client_role_cam']
    CLIENT_ROLE_DSS = ctx['client_role_dss']
    CLIENT_ROLE_KEY = ctx['client_role_key']
    CLIENT_ROLE_TAPO = ctx['client_role_tapo']
    client_has_role = ctx['client_has_role']
    snapshot_client = ctx['snapshot_client']
    save_state = ctx['save_state']
    broadcast_state = ctx.get('broadcast_state', lambda: None)
    clean_zone_name = ctx['clean_zone_name']
    safe_int = ctx.get('safe_int', lambda value: None)
    now_epoch = ctx['now_epoch']
    activity_log = ctx.get('activity_log')
    activity_log_can_record_event = (
        activity_log is not None
        and hasattr(
            activity_log,
            'record_event',
        )
    )
    automation_wake = Event()

    # A failed daily reset may be retried after the configured hour, but not
    # on every maintenance-loop pass.
    day_reset_retry_not_before = 0.0

    def record_tapo_recharge_activity(item):
        if not activity_log_can_record_event:
            return None

        action = str(
            item.get('action') or ''
        ).strip().lower()

        if action not in ('on', 'off'):
            return None

        battery = safe_int(
            item.get('battery')
        )
        detail = (
            f'Battery {battery}%'
            if battery is not None
            else ''
        )

        try:
            return activity_log.record_event(
                deviceID=item.get(
                    'clientDeviceID'
                ),
                name=(
                    item.get('clientName')
                    or 'Android Client'
                ),
                kind='tapo_recharge',
                state=action,
                status=detail,
                icon='battery_charging_full',
                accent=(
                    'green'
                    if action == 'on'
                    else 'purple'
                ),
                source=(
                    'automation:'
                    'tapo-recharge'
                ),
                category='automation',
            )
        except Exception:
            app.logger.exception(
                'Tapo recharge activity '
                'recording failed'
            )
            return None

    def record_tapo_day_reset_activity(
        deviceID,
    ):
        if not activity_log_can_record_event:
            return None

        client = CLIENTS.get(deviceID)

        if not isinstance(client, dict):
            client = {}

        try:
            return activity_log.record_event(
                deviceID=deviceID,
                name=(
                    client.get('clientName')
                    or client.get('tapo_alias')
                    or deviceID
                ),
                kind='tapo_day_reset',
                state='Day lighting restored',
                status='',
                icon='light_mode',
                accent='yellow',
                source=(
                    'automation:'
                    'tapo-day-reset'
                ),
                category='automation',
            )
        except Exception:
            app.logger.exception(
                'Tapo day reset activity '
                'recording failed for %s',
                deviceID,
            )
            return None

    def read_tapo_recharge_rules():
        state = read_automation_state()
        rules = state.get(AUTOMATION_TYPE_TAPO_RECHARGE)

        if not isinstance(rules, dict):
            return {}

        return {
            str(deviceID): dict(config)
            for deviceID, config in rules.items()
            if isinstance(deviceID, str) and isinstance(config, dict)
        }

    def write_tapo_recharge_rules(rules):
        state = read_automation_state()
        clean_rules = {
            str(deviceID): dict(config)
            for deviceID, config in (rules or {}).items()
            if isinstance(deviceID, str) and isinstance(config, dict)
        }

        if clean_rules:
            state[AUTOMATION_TYPE_TAPO_RECHARGE] = clean_rules
        else:
            state.pop(AUTOMATION_TYPE_TAPO_RECHARGE, None)

        write_automation_state(state)

        return clean_rules

    def automation_value_references_device(value, deviceID):
        clean_value = str(value or '').strip()
        clean_deviceID = str(deviceID or '').strip()

        return bool(
            clean_value
            and clean_deviceID
            and (
                clean_value == clean_deviceID
                or clean_value.startswith(f'{clean_deviceID}|')
            )
        )

    def remove_tapo_recharge_rules_for_device(deviceID):
        """Remove rules using deviceID as either battery source or power target."""
        clean_deviceID = str(deviceID or '').strip()

        if not clean_deviceID:
            return 0

        rules = read_tapo_recharge_rules()
        kept_rules = {}
        removed_count = 0

        for source_deviceID, config in rules.items():
            target_deviceID = config.get('targetDeviceID')
            targetID = config.get('targetID')

            references_device = (
                automation_value_references_device(
                    source_deviceID,
                    clean_deviceID,
                )
                or automation_value_references_device(
                    target_deviceID,
                    clean_deviceID,
                )
                or automation_value_references_device(
                    targetID,
                    clean_deviceID,
                )
            )

            if references_device:
                removed_count += 1
            else:
                kept_rules[source_deviceID] = config

        if removed_count:
            write_tapo_recharge_rules(kept_rules)

        return removed_count

    app.config[
        'KOTIBOT_REMOVE_RECHARGE_AUTOMATIONS_FOR_DEVICE'
    ] = remove_tapo_recharge_rules_for_device

    def automation_client_device_id(client_key, c):
        return next((
            str(value).strip()
            for value in (
                c.get('deviceID'),
                c.get('device_id'),
                c.get('clientID'),
                c.get('client_id'),
                c.get('id'),
                client_key,
            )
            if str(value or '').strip()
        ), '')

    def automation_client_name(c, deviceID=''):
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
            if not isinstance(c, dict) or not is_android_client(c):
                continue

            deviceID = automation_client_device_id(client_key, c)

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

            clientName = automation_client_name(c, deviceID)
            item = rules.get(deviceID)

            if not isinstance(item, dict) and clientName:
                matching_clients = [
                    other
                    for other_key, other in CLIENTS.items()
                    if (
                        isinstance(other, dict)
                        and is_android_client(other)
                        and automation_client_name(
                            other,
                            automation_client_device_id(other_key, other)
                        ).casefold() == clientName.casefold()
                    )
                ]
                matching_rule_ids = [
                    rule_deviceID
                    for rule_deviceID, rule in rules.items()
                    if (
                        rule_deviceID != deviceID
                        and isinstance(rule, dict)
                        and automation_client_name(
                            rule,
                            rule_deviceID
                        ).casefold() == clientName.casefold()
                    )
                ]

                if len(matching_clients) == 1 and len(matching_rule_ids) == 1:
                    stale_deviceID = matching_rule_ids[0]
                    item = rules.pop(stale_deviceID)
                    rules[deviceID] = item
                    changed = True

            if (
                isinstance(item, dict)
                and clientName
                and item.get('clientName') != clientName
            ):
                item['clientName'] = clientName
                changed = True

        if changed:
            write_tapo_recharge_rules(rules)

        return rules

    def read_automation_state():
        try:
            data = read_json(automation_state_path)
        except Exception:
            data = {}

        return data if isinstance(data, dict) else {}

    def write_automation_state(data):
        write_json_atomic(
            automation_state_path,
            data if isinstance(data, dict) else {},
        )

    def read_lighting_state():
        try:
            data = read_json(tapo_lighting_state_path)
        except Exception:
            data = {}

        state = dict(data) if isinstance(data, dict) else {}

        if not isinstance(state.get('schemes'), dict):
            state['schemes'] = {}

        if not isinstance(state.get('activeSchemes'), dict):
            state['activeSchemes'] = {}

        if not isinstance(state.get('modeConfig'), dict):
            state['modeConfig'] = {}

        return state

    def write_lighting_state(data):
        state = dict(data) if isinstance(data, dict) else {}

        if not isinstance(state.get('schemes'), dict):
            state['schemes'] = {}

        if not isinstance(state.get('activeSchemes'), dict):
            state['activeSchemes'] = {}

        if not isinstance(state.get('modeConfig'), dict):
            state['modeConfig'] = {}

        write_json_atomic(tapo_lighting_state_path, state)

        return state

    def normalized_reset_hour(value, default=6):
        reset_hour = safe_int(value)

        if reset_hour is None:
            reset_hour = default

        return max(0, min(11, reset_hour))

    def day_reset_config():
        state = read_automation_state()
        config = state.get(AUTOMATION_TYPE_TAPO_DAY_RESET)

        if not isinstance(config, dict):
            config = {}

        return {
            'type': AUTOMATION_TYPE_TAPO_DAY_RESET,
            'enabled': config.get('enabled') is True,
            'resetHour': normalized_reset_hour(
                config.get('resetHour', 6)
            ),
            'lastRunDate': str(config.get('lastRunDate') or ''),
        }

    def write_day_reset_config(config):
        state = read_automation_state()
        reset_hour = normalized_reset_hour(
            config.get('resetHour', 6)
        )

        existing = state.get(AUTOMATION_TYPE_TAPO_DAY_RESET)

        if not isinstance(existing, dict):
            existing = {}

        existing.update({
            'type': AUTOMATION_TYPE_TAPO_DAY_RESET,
            'enabled': config.get('enabled') is not False,
            'resetHour': reset_hour,
            'lastRunDate': str(config.get('lastRunDate', existing.get('lastRunDate', '')) or ''),
        })

        state[AUTOMATION_TYPE_TAPO_DAY_RESET] = existing
        write_automation_state(state)

        return existing

    def is_android_client(c):
        if not isinstance(c, dict) or not c.get('provisioned'):
            return False

        if c.get('battery') is None:
            return False

        if str(c.get('source') or '').strip().lower() == 'matter':
            return False

        if client_has_role(c, CLIENT_ROLE_TAPO):
            return False

        return any(
            client_has_role(c, role)
            for role in (
                CLIENT_ROLE_CAM,
                CLIENT_ROLE_DSS,
                CLIENT_ROLE_KEY,
            )
        )

    def recharge_battery_is_current(c):
        """Reject persisted battery readings from disconnected Android clients."""
        try:
            last_seen = float(c.get('last_seen', 0) or 0)
        except (TypeError, ValueError):
            last_seen = 0.0

        if last_seen <= 0:
            return False

        heartbeat_ms = safe_int(c.get('heartbeat_interval_ms')) or 30000
        freshness_seconds = max(
            65.0,
            (max(1000, heartbeat_ms) / 1000.0) * 2.0 + 5.0,
        )

        return now_epoch() - last_seen <= freshness_seconds

    def tapo_power_targets():
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

                    child_name = clean_zone_name(
                        child.get('alias')
                        or child.get('name')
                        or f"Outlet {child.get('position') or child.get('index') or index + 1}"
                    )

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

    def installed_automation_rows():
        rows = []

        rules = tapo_recharge_rules()

        for c in CLIENTS.values():
            item = rules.get(str(c.get('deviceID') or '').strip())

            if not isinstance(item, dict):
                continue

            rows.append({
                'type': AUTOMATION_TYPE_TAPO_RECHARGE,
                'deviceID': c.get('deviceID'),
                'clientName': c.get('clientName'),
                'enabled': item.get('enabled') is not False,
                'targetDeviceID': item.get('targetDeviceID', ''),
                'targetID': item.get('targetID', ''),
                'lowBattery': item.get('lowBattery', 20),
                'fullBattery': item.get('fullBattery', 100),
            })

        state = read_automation_state()
        device_automations = state.get('device_automations')

        if isinstance(device_automations, list):
            for index, item in enumerate(device_automations):
                if not isinstance(item, dict):
                    continue

                source_deviceID = str(item.get('from_deviceID') or item.get('sourceDeviceID') or '').strip()
                target_deviceID = str(item.get('to_deviceID') or item.get('targetDeviceID') or '').strip()
                source_client = CLIENTS.get(source_deviceID) or {}
                target_client = CLIENTS.get(target_deviceID) or {}

                rows.append({
                    'type': AUTOMATION_TYPE_DEVICE,
                    'automationID': f"{AUTOMATION_TYPE_DEVICE}:{index}",
                    'enabled': item.get('enabled') is not False,
                    'deviceID': source_deviceID,
                    'clientName': source_client.get('clientName') or source_deviceID,
                    'targetDeviceID': target_deviceID,
                    'targetID': item.get('targetID') or item.get('to_input') or '',
                    'targetName': target_client.get('clientName') or target_deviceID,
                    'trigger': item.get('trigger') or item.get('from_output') or '',
                    'actionType': item.get('action_type') or item.get('to_kind') or '',
                    'filename': item.get('filename') or '',
                    'title': item.get('title') or '',
                    'message': item.get('message') or '',
                    'soundVolume': item.get('sound_volume', ''),
                    'targetKeyDeviceID': item.get('target_key_deviceID') or '',
                    'durationSeconds': item.get('duration_seconds') or '',
                    'minimumDurationSeconds': item.get('minimum_duration_seconds') or '',
                    'repeat': item.get('repeat'),
                    'repeatSeconds': item.get('repeat_seconds') or '',
                    'cooldownSeconds': item.get('cooldown_seconds') or '',
                    'retrigger': item.get('retrigger'),
                    'threshold': item.get('threshold'),
                    'thresholdUnit': item.get('threshold_unit') or '',
                    'autoOff': item.get('auto_off') is True,
                    'autoOffSeconds': item.get('auto_off_seconds') or item.get('timer_seconds') or '',
                })

        day_reset = state.get(AUTOMATION_TYPE_TAPO_DAY_RESET)

        if isinstance(day_reset, dict):
            rows.append({
                'type': AUTOMATION_TYPE_TAPO_DAY_RESET,
                'enabled': day_reset.get('enabled') is not False,
                'resetHour': int(day_reset.get('resetHour', 6) or 6),
                'lastRunDate': str(day_reset.get('lastRunDate') or ''),
            })

        return rows
    
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

    def update_tapo_client_from_command_result(deviceID, result):
        c = CLIENTS.get(deviceID)

        if not c:
            return

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

        if isinstance(device.get('children'), list):
            c['tapo_children'] = device.get('children')

    def _clean_optional_tapo_target_value(value):
        if value is None:
            return ''

        return str(value).strip()

    def recharge_target_from_config(config):
        target_id = _clean_optional_tapo_target_value(config.get('targetID'))
        target_device_id = _clean_optional_tapo_target_value(config.get('targetDeviceID'))

        if not target_device_id and '|' in target_id:
            target_device_id = target_id.split('|', 1)[0].strip()

        child_id = _clean_optional_tapo_target_value(config.get('child_id'))

        if not child_id and '|' in target_id:
            child_id = target_id.split('|', 1)[1].strip()

        return {
            'targetDeviceID': target_device_id,
            'child_id': child_id,
            'child_index': _clean_optional_tapo_target_value(config.get('child_index')),
            'child_position': _clean_optional_tapo_target_value(config.get('child_position')),
        }

    def tapo_target_is_on(c, target):
        child_id = _clean_optional_tapo_target_value(target.get('child_id'))
        child_index = _clean_optional_tapo_target_value(target.get('child_index'))
        child_position = _clean_optional_tapo_target_value(target.get('child_position'))

        if child_id or child_index or child_position:
            children = c.get('tapo_children') if isinstance(c.get('tapo_children'), list) else []

            for child in children:
                if not isinstance(child, dict):
                    continue

                child_keys = {
                    str(child.get('id') or '').strip(),
                    str(child.get('index') or '').strip(),
                    str(child.get('cli_index') or '').strip(),
                    str(child.get('position') or '').strip(),
                }

                if child_id in child_keys or child_index in child_keys or child_position in child_keys:
                    return child.get('is_on')

            return None

        return c.get('tapo_is_on')

    def key_device_ids(key):
        clean = str(key or '').strip()

        if clean.startswith('device:'):
            return [clean.replace('device:', '', 1)]

        if clean.startswith('room:'):
            return [
                deviceID.strip()
                for deviceID in clean.replace('room:', '', 1).split(',')
                if deviceID.strip()
            ]

        return []

    def day_scheme_for_key(schemes, key):
        items = schemes.get(key)

        if not isinstance(items, list):
            return None

        for scheme in items:
            if not isinstance(scheme, dict):
                continue

            if str(scheme.get('mode') or '').strip().lower() == 'day':
                return scheme

        return None

    def day_reset_commands_for_device(deviceID, preset):
        commands = []

        brightness = preset.get('brightness')
        color_temperature = preset.get('colorTemperature', preset.get('color_temperature'))
        hue = preset.get('hue')
        saturation = preset.get('saturation')

        if color_temperature is not None:
            commands.append({
                'deviceID': deviceID,
                'action': 'color_temperature_no_power',
                'value': color_temperature,
            })

        if hue is not None and saturation is not None:
            commands.append({
                'deviceID': deviceID,
                'action': 'color_no_power',
                'value': {
                    'hue': hue,
                    'saturation': saturation,
                },
            })

        if brightness is not None:
            commands.append({
                'deviceID': deviceID,
                'action': 'brightness_no_power',
                'value': brightness,
            })

        return commands

    def run_tapo_recharge_once():
        prepared = []

        with STATE_LOCK:
            rules = tapo_recharge_rules()

            for client_key, c in CLIENTS.items():
                if not is_android_client(c):
                    continue

                # Do not operate a charger from a battery value restored from
                # disk or left behind by a disconnected Android client.
                if not recharge_battery_is_current(c):
                    continue

                client_deviceID = automation_client_device_id(client_key, c)
                config = rules.get(client_deviceID)

                if not isinstance(config, dict) or config.get('enabled') is False:
                    continue

                battery = safe_int(c.get('battery'))

                if battery is None:
                    continue

                low_battery = safe_int(config.get('lowBattery'))
                full_battery = safe_int(config.get('fullBattery'))

                if low_battery is None:
                    low_battery = 20

                if full_battery is None:
                    full_battery = 100

                if battery <= low_battery:
                    action = 'on'
                elif battery >= full_battery:
                    action = 'off'
                else:
                    continue

                target = recharge_target_from_config(config)
                target_device_id = target.get('targetDeviceID')
                tapo_client = CLIENTS.get(target_device_id)

                if not tapo_client or not client_has_role(tapo_client, CLIENT_ROLE_TAPO):
                    continue

                if not tapo_client.get('tapo_supports_power'):
                    continue

                current_on = tapo_target_is_on(tapo_client, target)

                if action == 'on' and current_on is True:
                    continue

                if action == 'off' and current_on is False:
                    continue

                item = tapo_command_item_from_client(tapo_client, target_device_id)
                item.update(target)

                prepared.append({
                    'clientDeviceID': client_deviceID,
                    'clientName': c.get('clientName'),
                    'battery': battery,
                    'targetDeviceID': target_device_id,
                    'action': action,
                    'item': item,
                })

        command_results = []

        for prepared_item in prepared:
            try:
                item = prepared_item.get('item') if isinstance(prepared_item.get('item'), dict) else {}
                value = {
                    'child_id': item.get('child_id', ''),
                    'child_index': item.get('child_index', ''),
                    'child_position': item.get('child_position', ''),
                }

                result = run_async(set_tapo_device_from_info(
                    item,
                    prepared_item.get('action'),
                    value
                ))

                command_results.append({
                    'ok': True,
                    **prepared_item,
                    'result': result,
                })
            except Exception as e:
                command_results.append({
                    'ok': False,
                    **prepared_item,
                    'error': str(e),
                })

        if not command_results:
            return

        successful_items = []

        with STATE_LOCK:
            changed_clients = False

            for item in command_results:
                if not item.get('ok'):
                    app.logger.error(
                        'Tapo recharge failed for %s: %s',
                        item.get('clientName'),
                        item.get('error'),
                    )
                    continue

                update_tapo_client_from_command_result(item.get('targetDeviceID'), item.get('result') or {})
                successful_items.append(item)
                changed_clients = True

            if changed_clients:
                save_state()
            else:
                broadcast_state()

        for item in successful_items:
            record_tapo_recharge_activity(item)

    def run_tapo_day_reset_once():
        nonlocal day_reset_retry_not_before

        config = day_reset_config()

        if not config.get('enabled'):
            return

        now = datetime.now()
        reset_hour = normalized_reset_hour(
            config.get('resetHour', 6)
        )
        today = now.strftime('%Y-%m-%d')

        # Run once at or after the selected hour. Requiring minute == 0 can
        # miss the entire day when the loop is delayed by device I/O.
        if now.hour < reset_hour:
            return

        if config.get('lastRunDate') == today:
            return

        if time.monotonic() < day_reset_retry_not_before:
            return

        lighting_state = read_lighting_state()
        schemes = lighting_state.get('schemes') if isinstance(lighting_state.get('schemes'), dict) else {}
        active = lighting_state.get('activeSchemes') if isinstance(lighting_state.get('activeSchemes'), dict) else {}

        reset_keys = []

        for key, mode in active.items():
            mode = str(mode or '').strip().lower()

            if mode not in TAPO_DAY_RESET_MODES:
                continue

            day_scheme = day_scheme_for_key(schemes, key)

            if not day_scheme:
                continue

            preset = day_scheme.get('preset') if isinstance(day_scheme.get('preset'), dict) else {}

            if not preset:
                continue

            reset_keys.append({
                'key': key,
                'deviceIDs': key_device_ids(key),
                'preset': preset,
            })

        prepared = []

        with STATE_LOCK:
            for reset_item in reset_keys:
                for deviceID in reset_item.get('deviceIDs', []):
                    c = CLIENTS.get(deviceID)

                    if not c or not client_has_role(c, CLIENT_ROLE_TAPO):
                        continue

                    if c.get('tapo_is_on') is not True:
                        continue

                    if not c.get('tapo_supports_brightness') and not c.get('tapo_supports_color_temp') and not c.get('tapo_supports_color'):
                        continue

                    commands = day_reset_commands_for_device(deviceID, reset_item.get('preset') or {})

                    if not commands:
                        continue

                    prepared.append({
                        'deviceID': deviceID,
                        'item': tapo_command_item_from_client(c, deviceID),
                        'commands': commands,
                    })

        def run_device(prepared_item):
            deviceID = prepared_item.get('deviceID')
            item = prepared_item.get('item')
            results = []

            for command in prepared_item.get('commands', []):
                try:
                    result = run_async(set_tapo_device_from_info(
                        item,
                        command.get('action'),
                        command.get('value')
                    ))

                    results.append({
                        'ok': True,
                        'deviceID': deviceID,
                        'action': command.get('action'),
                        'result': result,
                    })
                except Exception as e:
                    results.append({
                        'ok': False,
                        'deviceID': deviceID,
                        'action': command.get('action'),
                        'error': str(e),
                    })

            return results

        command_results = []

        if prepared:
            with ThreadPoolExecutor(max_workers=min(8, max(1, len(prepared)))) as executor:
                futures = [
                    executor.submit(run_device, item)
                    for item in prepared
                ]

                for future in as_completed(futures):
                    command_results.extend(future.result())

        successful_device_ids = set()
        failed_device_ids = set()

        with STATE_LOCK:
            changed_clients = False

            for item in command_results:
                deviceID = str(
                    item.get('deviceID') or ''
                ).strip()

                if not item.get('ok'):
                    if deviceID:
                        failed_device_ids.add(deviceID)

                    app.logger.error(
                        'Tapo day reset failed for %s: %s',
                        deviceID,
                        item.get('error'),
                    )
                    continue

                update_tapo_client_from_command_result(
                    deviceID,
                    item.get('result') or {},
                )

                if deviceID:
                    successful_device_ids.add(deviceID)

                changed_clients = True

            # Do not advertise Day mode or suppress later retries when any
            # attempted device command failed. Successful commands are still
            # reconciled into CLIENTS before the retry.
            if not failed_device_ids:
                current_lighting_state = read_lighting_state()
                current_active = current_lighting_state.get('activeSchemes')

                if not isinstance(current_active, dict):
                    current_active = {}

                for reset_item in reset_keys:
                    current_active[reset_item.get('key')] = 'day'

                current_lighting_state['activeSchemes'] = current_active
                write_lighting_state(current_lighting_state)

                state = read_automation_state()
                stored = state.get(AUTOMATION_TYPE_TAPO_DAY_RESET)

                if not isinstance(stored, dict):
                    stored = {}

                stored.update({
                    'type': AUTOMATION_TYPE_TAPO_DAY_RESET,
                    'enabled': config.get('enabled') is True,
                    'resetHour': reset_hour,
                    'lastRunDate': today,
                })

                state[AUTOMATION_TYPE_TAPO_DAY_RESET] = stored
                write_automation_state(state)

            if changed_clients or not failed_device_ids:
                save_state()

        if failed_device_ids:
            # Retry after five minutes instead of retrying every maintenance
            # pass or incorrectly waiting until the following day.
            day_reset_retry_not_before = time.monotonic() + 300.0
            return

        day_reset_retry_not_before = 0.0

        for deviceID in sorted(successful_device_ids):
            record_tapo_day_reset_activity(deviceID)

    def automation_loop():
        interval = max(15.0, float(os.environ.get('KOTIBOT_AUTOMATIONS_SECONDS', '60') or 60))

        while True:
            automation_wake.clear()

            try:
                run_tapo_recharge_once()
            except Exception:
                app.logger.exception('Recharge automation loop failed')

            try:
                run_tapo_day_reset_once()
            except Exception:
                app.logger.exception('Day reset automation loop failed')

            automation_wake.wait(interval)

    app.config['KOTIBOT_AUTOMATIONS_LOOP'] = automation_loop
    app.config['KOTIBOT_AUTOMATIONS_WAKE'] = automation_wake.set

    @app.get('/api/automations')
    def api_automations_status():
        with STATE_LOCK:
            android_clients = [
                snapshot_client(c)
                for c in CLIENTS.values()
                if is_android_client(c)
            ]

            power_targets = tapo_power_targets()
            automations = installed_automation_rows()
            day_reset = day_reset_config()

        return jsonify({
            'ok': True,
            'loaded': True,
            'clients': android_clients,
            'targets': power_targets,
            'automations': automations,
            'installedTypes': sorted({item['type'] for item in automations}),
            'dayReset': day_reset,
        })

    @app.post('/api/automations/tapo-recharge')
    def api_save_tapo_recharge_automation():
        data = request.get_json(silent=True) or {}
        deviceID = str(data.get('deviceID') or '').strip()
        targetID = str(data.get('targetID') or '').strip()

        if not deviceID:
            return jsonify({'ok': False, 'error': 'Missing KotiBot client'}), 400

        if not targetID:
            return jsonify({'ok': False, 'error': 'Missing Tapo plug target'}), 400

        with STATE_LOCK:
            c = CLIENTS.get(deviceID)

            if not c or not is_android_client(c):
                return jsonify({'ok': False, 'error': 'KotiBot client not found'}), 404

            targets = tapo_power_targets()
            target = next((item for item in targets if item.get('targetID') == targetID), None)

            if not target:
                return jsonify({'ok': False, 'error': 'Tapo plug target not found'}), 404

            rules = tapo_recharge_rules()
            rules[deviceID] = {
                'type': AUTOMATION_TYPE_TAPO_RECHARGE,
                'clientName': automation_client_name(c, deviceID),
                'enabled': data.get('enabled') is not False,
                'targetID': targetID,
                'targetDeviceID': target.get('deviceID', ''),
                'child_id': target.get('child_id', ''),
                'child_index': target.get('child_index', ''),
                'child_position': target.get('child_position', ''),
                'lowBattery': 20,
                'fullBattery': 100,
            }

            write_tapo_recharge_rules(rules)
            save_state()

            return jsonify({
                'ok': True,
                'automation': rules[deviceID],
                'automations': installed_automation_rows(),
            })

    @app.post('/api/automations/tapo-day-reset')
    def api_save_tapo_day_reset_automation():
        data = request.get_json(silent=True) or {}
        reset_hour = safe_int(data.get('resetHour', 6))

        if reset_hour is None or reset_hour < 0 or reset_hour > 11:
            return jsonify({
                'ok': False,
                'error': 'Reset hour must be 12 AM through 11 AM'
            }), 400

        with STATE_LOCK:
            config = write_day_reset_config({
                'enabled': data.get('enabled') is not False,
                'resetHour': reset_hour,
            })
            automations = installed_automation_rows()

        return jsonify({
            'ok': True,
            'dayReset': config,
            'automations': automations,
        })
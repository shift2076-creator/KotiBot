"""Server persistence helpers for KotiBot.

This module owns server/subsystem state loading and persistence.

Automation flow:
1. Security actions are loaded from security_actions.json.
2. Ordinary device automations are loaded from automations_state.json.
3. Both are normalized into the shared in-memory ROUTES list.
4. save_state() separates the shared list back into its subsystem files.
5. Legacy client-embedded recharge rules are migrated into automations_state.json.

Callers hold the shared reentrant state lock while mutating CLIENTS or ROUTES.
Loading and saving also acquire it, so event callbacks may safely save after
releasing their mutation lock. A save accepts one complete logical snapshot;
dashboard publication is best-effort and cannot prevent persistence.
"""

import logging
from pathlib import Path
from threading import RLock

from server_core.io import (
    JsonStateInvalidError,
    JsonStateMissingError,
    json_backup_path,
    json_exists,
    read_json_object,
    write_json_batch_atomic,
)

LOGGER = logging.getLogger(__name__)


class StateSaveError(RuntimeError):
    """An authoritative state change could not be accepted for persistence."""

TAPO_DEVICE_STATE_KEYS = (
    'tapo_id', 'tapo_mac', 'tapo_model', 'tapo_device_type',
    'tapo_ip', 'tapo_alias', 'tapo_control_ready', 'tapo_control_error',
    'tapo_is_on', 'tapo_brightness', 'tapo_dimmable',
    'tapo_kind', 'tapo_dashboard_section',
    'tapo_is_bulb', 'tapo_is_plug', 'tapo_is_outlet_extender',
    'tapo_is_hub', 'tapo_is_camera',
    'tapo_room_power', 'tapo_hide_dashboard',
    'tapo_color_temperature', 'tapo_hue', 'tapo_saturation',
    'tapo_desired_lighting_mode', 'tapo_desired_lighting_updated_at',
    'tapo_desired_brightness', 'tapo_desired_color_temperature',
    'tapo_desired_hue', 'tapo_desired_saturation',
    'tapo_desired_white_saturation',
    'tapo_battery', 'tapo_battery_level', 'tapo_battery_percent',
    'tapo_battery_low', 'tapo_battery_state',
    'tapo_supports_power', 'tapo_supports_brightness',
    'tapo_supports_color_temp', 'tapo_supports_color',
    'tapo_supports_rtsp', 'tapo_supports_onvif',
    'tapo_onvif_port', 'tapo_children',
    'tapo_children_initialized',
)

# Tapo discovery can supply arbitrary vendor dictionaries for outlet-extender
# children. Persist only the fields KotiBot currently reads or deliberately
# owns. In particular, never persist the raw vendor payload or compatibility
# aliases that have already been normalized into these canonical fields.
TAPO_CHILD_STATE_KEYS = (
    'id', 'device_id', 'parent_device_id', 'mac',
    'index', 'cli_index', 'position', 'slot_number',
    'alias', 'name', 'clientName',
    'zone_name', 'room', 'room_name', 'zone',
    'model', 'category', 'avatar', 'type',
    'kind', 'tapo_kind', 'tapo_alias',
    'tapo_child_id', 'tapo_child_name',
    'tapo_child_position', 'tapo_child_index', 'tapo_child_kind',
    'tapo_room_power', 'tapo_hide_dashboard',
    'is_usb', 'is_light', 'is_outlet',
    'tapo_is_outlet_child', 'tapo_is_plug', 'tapo_is_bulb',
    'supports_power', 'supports_brightness',
    'supports_color_temp', 'supports_color',
    'tapo_supports_power',
    'status', 'rssi', 'signal_level',
    'battery', 'at_low_battery', 'battery_low', 'battery_state',
    'is_on',
)


def tapo_persisted_device_state(client):
    """Return the closed persisted Tapo snapshot for one client."""
    if not isinstance(client, dict):
        return {}

    state = {
        key: client.get(key)
        for key in TAPO_DEVICE_STATE_KEYS
        if key in client and key != 'tapo_children'
    }
    children = client.get('tapo_children')

    if isinstance(children, list):
        state['tapo_children'] = [
            {
                key: child.get(key)
                for key in TAPO_CHILD_STATE_KEYS
                if key in child
            }
            for child in children
            if isinstance(child, dict)
        ]

    return state


MATTER_DEVICE_STATE_KEYS = (
    'ip',
    'battery',
    'battery_low',
    'battery_state',
    'brand',
    'manufacturer',
    'model',
    'matter_node_id',
    'matter_endpoint',
    'matter_kind',
    'matter_kinds',
    'matter_device_type',
    'matter_cluster',
    'matter_last_sync_at',
    'matter_vendor_name',
    'matter_product_name',
    'matter_node_label',
    'matter_hardware_version',
    'matter_software_version',
    'matter_serial_number',
    'matter_reachable',
    'temperature_raw',
    'temperature_c',
    'humidity_raw',
    'humidity_percent',
    'contact_state_value',
    'contact_open',
    'occupancy_state_value',
    'motion_active',
    'last_motion_at',
    'matter_contact_open_when',
    'door_status',
    'openness_score',
    'door_angle',
    'door_event_ms',
    'last_transition_at',
    'calibrating',
    'doorbell_muted',
    'matter_onoff',
    'matter_switch_position',
    'matter_switch_positions',
    'matter_switch_multipress_max',
    'matter_button_position',
    'matter_button_event',
    'matter_button_event_at',
    'matter_button_press_count',
    'matter_battery_percent_remaining_raw',
    'matter_battery_percent',
    'matter_battery_charge_level',
    'matter_battery_charge_state',
    'matter_battery_replacement_needed',
    'matter_battery_low',
)

COMMON_CLIENT_STATE_KEYS = (
    'deviceID',
    'clientName',
    'clientRole',
    'provisioned',
    'zone_name',
)

TAPO_SERVER_STATE_KEYS = COMMON_CLIENT_STATE_KEYS + (
    'source',
)

ANDROID_SHARED_SERVER_STATE_KEYS = COMMON_CLIENT_STATE_KEYS + (
    'ip',
    'battery',
    'battery_low',
    'battery_state',
    'brand',
    'androidVersion',
    'version',
    'heartbeat_interval_ms',
)

ANDROID_HOME_SERVER_STATE_KEYS = ANDROID_SHARED_SERVER_STATE_KEYS + (
    'hasDSSHW',
)

ANDROID_KEY_SERVER_STATE_KEYS = ANDROID_SHARED_SERVER_STATE_KEYS

UNPROVISIONED_SERVER_STATE_KEYS = COMMON_CLIENT_STATE_KEYS + (
    'ip',
    'battery',
    'battery_low',
    'battery_state',
    'brand',
    'androidVersion',
    'hasDSSHW',
    'version',
    'heartbeat_interval_ms',
    'detectedRole',
    'source',
    'manufacturer',
    'model',
)

# Matter discovery, telemetry, reachability, battery state, and read diagnostics
# are runtime data rebuilt by the Matter subsystem. server_state.json stores
# only persistent identity and user configuration.
MATTER_SERVER_STATE_KEYS = COMMON_CLIENT_STATE_KEYS + (
    'source',
)

OTHER_SERVER_STATE_KEYS = COMMON_CLIENT_STATE_KEYS + (
    'ip',
    'battery',
    'battery_low',
    'battery_state',
    'brand',
    'version',
    'source',
    'manufacturer',
    'model',
)

SERVER_CLIENT_GROUP_ORDER = (
    'tapo',
    'matter',
    'android_home',
    'android_key',
    'unprovisioned',
    'other',
)

SERVER_CLIENT_STATE_KEYS_BY_GROUP = {
    'tapo': TAPO_SERVER_STATE_KEYS,
    'matter': MATTER_SERVER_STATE_KEYS,
    'android_home': ANDROID_HOME_SERVER_STATE_KEYS,
    'android_key': ANDROID_KEY_SERVER_STATE_KEYS,
    'unprovisioned': UNPROVISIONED_SERVER_STATE_KEYS,
    'other': OTHER_SERVER_STATE_KEYS,
}

ANDROID_CAMERA_STATE_KEYS = (
    'frame_seq', 'frame_last_seen', 'recording', 'recording_enabled',
    'motion_detection_enabled', 'motion_detection_threshold',
    'motion_active', 'motion_recording_active', 'last_motion_at',
    'last_motion_score', 'motion_flashlight_enabled',
    'motion_screen_enabled', 'selected_camera', 'available_cameras',
    'preview_by_lens', 'camera_auto_rotation', 'camera_auto_rotation_at',
    'camera_auto_rotation_lens', 'exposure_compensation',
    'camera_enabled', 'cameraEnabled', 'frame_captured_ms',
    'android_sensors',
)

ANDROID_DSS_STATE_KEYS = (
    'door_status', 'calibrating', 'open_angle_threshold',
    'close_angle_threshold', 'calibration_samples', 'smoothing_window',
    'doorbell_muted', 'last_chime_at', 'last_transition_at',
    'openness_score', 'door_angle', 'door_event_ms',
    'ignore_door_open_until_closed', 'android_sensors',
)

def build_state_runtime(ctx):
    clients = ctx['clients']
    routes = ctx['routes']
    state_lock = ctx.get('state_lock') or RLock()

    state_file = ctx['state_file']
    security_actions_file = ctx['security_actions_file']
    tapo_device_state_file = ctx['tapo_device_state_file']
    matter_device_state_file = ctx['matter_device_state_file']
    android_home_state_file = ctx['android_home_state_file']
    automation_state_file = ctx['automation_state_file']
    automation_type_tapo_recharge = ctx['automation_type_tapo_recharge']
    automation_type_device_routes = ctx['automation_type_device_routes']

    client_role_cam = ctx['client_role_cam']
    client_role_dss = ctx['client_role_dss']
    client_role_key = ctx['client_role_key']
    client_role_tapo = ctx['client_role_tapo']

    open_angle_threshold = ctx['open_angle_threshold']
    close_angle_threshold = ctx['close_angle_threshold']

    client_has_role = ctx['client_has_role']
    clean_arm_state = ctx['clean_arm_state']
    clean_zone_name = ctx['clean_zone_name']
    init_client = ctx['init_client']
    set_routes = ctx['set_routes']
    set_system_arm_state = ctx['set_system_arm_state']
    broadcast_state = ctx['broadcast_state']
    device_notification_credential = ctx.get(
        'device_notification_credential',
        lambda _device_id: {},
    )

    get_system_armed = ctx['system_armed']
    get_system_arm_state = ctx['system_arm_state']

    state_loaded = False

    def _state_values_for_keys(client, keys):
        return {
            key: client.get(key)
            for key in keys
            if key in client
        }

    def _read_subsystem_state_file(path, root_key):
        data = _read_json_object_file(path)
        if data and root_key not in data:
            raise JsonStateInvalidError(path)
        items = data.get(root_key, {})
        if not isinstance(items, dict) or any(
            not isinstance(device_id, str) or not device_id.strip()
            or not isinstance(item, dict)
            for device_id, item in items.items()
        ):
            raise JsonStateInvalidError(path)
        return items

    def _server_client_group(client):
        if not bool(client.get('provisioned')):
            return 'unprovisioned'

        source = str(client.get('source') or '').strip().lower()

        if source == 'matter':
            return 'matter'

        if source == 'tapo' or client_has_role(client, client_role_tapo):
            return 'tapo'

        if client_has_role(client, client_role_key):
            return 'android_key'

        if (
            client_has_role(client, client_role_cam)
            or client_has_role(client, client_role_dss)
        ):
            return 'android_home'

        return 'other'

    def _server_client_state(client):
        group = _server_client_group(client)
        keys = SERVER_CLIENT_STATE_KEYS_BY_GROUP[group]
        state = _state_values_for_keys(client, keys)

        state['deviceID'] = client.get('deviceID')
        state['clientName'] = client.get('clientName')
        state['clientRole'] = client.get('clientRole')
        state['provisioned'] = bool(client.get('provisioned'))

        if group == 'tapo':
            state['source'] = 'tapo'
        elif group == 'matter':
            state['source'] = 'matter'

        return group, state

    def _stored_server_client_items(data):
        stored_clients = data.get('clients', [])

        # Backward compatibility with the current flat list format.
        if isinstance(stored_clients, list):
            return _validated_client_items(stored_clients)

        if not isinstance(stored_clients, dict):
            raise JsonStateInvalidError(state_file)

        group_names = list(SERVER_CLIENT_GROUP_ORDER)
        group_names.extend(
            sorted(
                group_name
                for group_name in stored_clients
                if group_name not in group_names
            )
        )

        items = []

        for group_name in group_names:
            group_items = stored_clients.get(group_name, [])

            if not isinstance(group_items, list):
                raise JsonStateInvalidError(state_file)

            for raw_item in group_items:
                if not isinstance(raw_item, dict):
                    raise JsonStateInvalidError(state_file)
                items.append(raw_item)

        return _validated_client_items(items)

    def _validated_client_items(items):
        seen = set()
        validated = []
        for item in items:
            if not isinstance(item, dict):
                raise JsonStateInvalidError(state_file)
            device_id = item.get('deviceID')
            if (not isinstance(device_id, str) or not device_id.strip()
                    or device_id != device_id.strip() or device_id in seen):
                raise JsonStateInvalidError(state_file)
            roles = item.get('clientRole', [])
            if not isinstance(roles, (str, list)) or (
                isinstance(roles, list) and any(not isinstance(role, str) for role in roles)
            ):
                raise JsonStateInvalidError(state_file)
            if 'provisioned' in item and not isinstance(item['provisioned'], bool):
                raise JsonStateInvalidError(state_file)
            seen.add(device_id)
            validated.append(dict(item))
        return validated

    def _read_json_object_file(path):
        try:
            data = read_json_object(path)
        except JsonStateMissingError:
            if json_backup_path(path).exists():
                raise
            return {}

        return data

    def _route_is_device_automation(route):
        return str(route.get('scope') or '').strip().lower() == 'automation'

    def _stored_route(route):
        item = dict(route)
        item.pop('scope', None)
        return item
    
    def _automation_state_data(source_clients, source_routes, automation_state=None):
        if automation_state is None:
            automation_state = _read_json_object_file(automation_state_file)
        else:
            automation_state = dict(automation_state)
        recharge_rules = automation_state.get(automation_type_tapo_recharge)

        if recharge_rules is None:
            recharge_rules = {}
        elif not isinstance(recharge_rules, dict):
            raise JsonStateInvalidError(automation_state_file)
        else:
            recharge_rules = dict(recharge_rules)

        for deviceID, client in source_clients.items():
            if not isinstance(client, dict):
                continue

            clean_id = str(client.get('deviceID') or deviceID or '').strip()

            if not clean_id:
                continue

            legacy = client.get('tapo_recharge')

            if not isinstance(legacy, dict):
                store = client.get('automations') if isinstance(client.get('automations'), dict) else {}
                legacy = store.get(automation_type_tapo_recharge)

            if isinstance(legacy, dict) and legacy:
                item = dict(legacy)
                item['type'] = automation_type_tapo_recharge
                recharge_rules[clean_id] = item

        if recharge_rules:
            automation_state[automation_type_tapo_recharge] = recharge_rules
        else:
            automation_state.pop(automation_type_tapo_recharge, None)

        device_automations = [
            _stored_route(route)
            for route in source_routes
            if isinstance(route, dict) and _route_is_device_automation(route)
        ]

        if device_automations:
            automation_state[automation_type_device_routes] = device_automations
        else:
            automation_state.pop(automation_type_device_routes, None)

        return automation_state

    def _security_actions_data(source_routes):
        actions = [
            _stored_route(route)
            for route in source_routes
            if isinstance(route, dict) and not _route_is_device_automation(route)
        ]
        return {'actions': actions}

    def _subsystem_state_data(source_clients):
        tapo_devices = {}
        matter_devices = {}
        android_home_clients = {}

        for deviceID, client in source_clients.items():
            if not isinstance(client, dict):
                continue

            clean_id = str(client.get('deviceID') or deviceID or '').strip()

            if not clean_id:
                continue

            if _server_client_group(client) == 'matter':
                matter_state = _state_values_for_keys(
                    client,
                    MATTER_DEVICE_STATE_KEYS,
                )

                if matter_state:
                    matter_devices[clean_id] = matter_state

                continue

            if client_has_role(client, client_role_tapo):
                tapo_state = tapo_persisted_device_state(client)

                if tapo_state:
                    tapo_devices[clean_id] = tapo_state

            if client_has_role(client, client_role_tapo):
                continue

            android_home_state = {}

            if client_has_role(client, client_role_cam):
                android_home_state.update(_state_values_for_keys(client, ANDROID_CAMERA_STATE_KEYS))

            if client_has_role(client, client_role_dss):
                android_home_state.update(_state_values_for_keys(client, ANDROID_DSS_STATE_KEYS))

            if android_home_state:
                android_home_clients[clean_id] = android_home_state

        return {
            tapo_device_state_file: {'devices': tapo_devices},
            matter_device_state_file: {'devices': matter_devices},
            android_home_state_file: {'clients': android_home_clients},
        }

    def _system_state_values():
        system_armed = (
            bool(get_system_armed())
            if callable(get_system_armed)
            else bool(get_system_armed)
        )
        system_arm_state = (
            get_system_arm_state()
            if callable(get_system_arm_state)
            else get_system_arm_state
        )

        return system_armed, system_arm_state

    def _server_state_data(source_clients, system_values):
        system_armed, system_arm_state = system_values
        grouped_clients = {
            group_name: []
            for group_name in SERVER_CLIENT_GROUP_ORDER
        }

        for client in source_clients.values():
            if not isinstance(client, dict):
                continue

            group_name, state = _server_client_state(client)
            grouped_clients[group_name].append(state)

        for group_items in grouped_clients.values():
            group_items.sort(
                key=lambda item: (
                    str(item.get('zone_name') or '').casefold(),
                    str(item.get('clientName') or '').casefold(),
                    str(item.get('deviceID') or '').casefold(),
                )
            )

        return {
            'clients': grouped_clients,
            'system': {
                'armed': system_armed,
                'arm_state': system_arm_state,
                'armState': system_arm_state,
            }
        }

    def _state_documents(source_clients, source_routes, system_values, automation_state=None):
        return {
            automation_state_file: _automation_state_data(source_clients, source_routes, automation_state),
            security_actions_file: _security_actions_data(source_routes),
            **_subsystem_state_data(source_clients),
            state_file: _server_state_data(source_clients, system_values),
        }

    def _clear_migrated_recharge(source_clients):
        # Remove legacy memory fields only once their replacement was accepted.
        for client in source_clients.values():
            if not isinstance(client, dict):
                continue
            client.pop('tapo_recharge', None)
            store = client.get('automations')
            if isinstance(store, dict):
                store.pop(automation_type_tapo_recharge, None)
                if not store:
                    client.pop('automations', None)

    def save_state():
        try:
            with state_lock:
                documents = _state_documents(clients, routes, _system_state_values())
                write_json_batch_atomic(documents)
                _clear_migrated_recharge(clients)
        except Exception as error:
            LOGGER.error('Server state save rejected: file=%s reason=%s',
                         getattr(error, 'filename', Path(state_file).name),
                         getattr(error, 'reason', type(error).__name__))
            raise StateSaveError('Server state could not be saved; retry the change') from None
        try:
            broadcast_state()
        except Exception as error:
            LOGGER.error('State saved; dashboard publication failed: %s', type(error).__name__)
        return True

    def load_state():
        with state_lock:
            return _load_state_locked()

    def _load_state_locked():
        nonlocal state_loaded

        if state_loaded:
            return True

        try:
            data = _read_json_object_file(state_file)
            security_actions_state = _read_json_object_file(security_actions_file)
            security_actions = security_actions_state.get('actions', data.get('routes', []))
            if security_actions_state and 'actions' not in security_actions_state:
                raise JsonStateInvalidError(security_actions_file)
            if not isinstance(security_actions, list) or any(
                not isinstance(route, dict) for route in security_actions
            ):
                raise JsonStateInvalidError(security_actions_file)

            automation_state = _read_json_object_file(automation_state_file)
            device_automations = automation_state.get(automation_type_device_routes, [])

            if not isinstance(device_automations, list) or any(
                not isinstance(route, dict) for route in device_automations
            ):
                raise JsonStateInvalidError(automation_state_file)

            restored_routes = (
                [r for r in security_actions if isinstance(r, dict)]
                + [
                    {**route, 'scope': 'automation'}
                    for route in device_automations
                    if isinstance(route, dict)
                ]
            )
            system_state = data.get('system', {})
            if not isinstance(system_state, dict):
                raise JsonStateInvalidError(state_file)
            if 'armed' in system_state and not isinstance(system_state['armed'], bool):
                raise JsonStateInvalidError(state_file)
            raw_arm_state = system_state.get('arm_state', system_state.get('armState'))
            if raw_arm_state is not None and raw_arm_state not in ('day', 'night', 'away'):
                raise JsonStateInvalidError(state_file)
            system_armed = bool(system_state.get('armed', False))
            system_arm_state = clean_arm_state(
                system_state.get('arm_state', system_state.get('armState', 'night' if system_armed else 'day'))
            )
            tapo_device_state = _read_subsystem_state_file(
                tapo_device_state_file,
                'devices',
            )
            matter_device_state = _read_subsystem_state_file(
                matter_device_state_file,
                'devices',
            )
            android_home_state = _read_subsystem_state_file(
                android_home_state_file,
                'clients',
            )

            if 'clients' not in data and (
                json_exists(state_file) or security_actions
                or any(automation_state.values()) or tapo_device_state
                or matter_device_state or android_home_state
            ):
                raise JsonStateInvalidError(state_file)

            stored_items = _stored_server_client_items(data)
            known_ids = {item['deviceID'] for item in stored_items}
            for path, stored_subsystem in (
                (tapo_device_state_file, tapo_device_state),
                (matter_device_state_file, matter_device_state),
                (android_home_state_file, android_home_state),
            ):
                if stored_subsystem.keys() - known_ids:
                    raise JsonStateInvalidError(path)
            restored_clients = {}

            for item in stored_items:
                deviceID = item.get('deviceID')
                if not deviceID:
                    continue

                # SEC-004.3 migrates these legacy values before load. Never
                # allow ordinary server state to remain authoritative for a
                # notification credential.
                item.pop('fcm_token', None)
                item.pop('fcm_token_at', None)

                c = init_client(deviceID)
                c.update(item)

                if deviceID in tapo_device_state:
                    c.update(tapo_device_state[deviceID])

                if deviceID in matter_device_state:
                    c.update(matter_device_state[deviceID])

                if (
                    not client_has_role(c, client_role_tapo)
                    and deviceID not in matter_device_state
                    and deviceID in android_home_state
                ):
                    c.update(android_home_state[deviceID])

                notification_credential = (
                    device_notification_credential(deviceID)
                )

                if isinstance(notification_credential, dict):
                    c['fcm_token'] = str(
                        notification_credential.get('token') or ''
                    ).strip()
                    c['fcm_token_at'] = float(
                        notification_credential.get('updated_at') or 0
                    )

                # Outbound commands are transient. Never restore commands or
                # credentials from server_state.json after a restart.
                c['pending_command'] = {}

                c['last_seen'] = 0
                c['needs_heartbeat'] = False
                c['heartbeat_requested_at'] = 0
                c['heartbeat_pending'] = False
                c['zone_name'] = (
                    ''
                    if client_has_role(c, client_role_key)
                    else clean_zone_name(c.get('zone_name'))
                )

                if client_has_role(c, client_role_dss):
                    c['door_status'] = 'unknown'
                    c['openness_score'] = float(c.get('openness_score', 0.0) or 0.0)
                    c['calibrating'] = int(c.get('calibrating', 0) or 0)
                    c['open_angle_threshold'] = float(c.get('open_angle_threshold', open_angle_threshold))
                    c['close_angle_threshold'] = float(c.get('close_angle_threshold', close_angle_threshold))

                if client_has_role(c, client_role_tapo):
                    c['tapo_recording'] = False
                    c['tapo_recording_enabled'] = False

                if str(c.get('source') or '').strip().lower() == 'matter':
                    # Restored observations are not evidence of a live device.
                    # Unknown values also make the first report a baseline,
                    # rather than an automation/security transition.
                    for field in (
                        'matter_reachable', 'temperature_raw', 'temperature_c',
                        'humidity_raw', 'humidity_percent', 'contact_state_value',
                        'contact_open', 'occupancy_state_value', 'motion_active',
                        'matter_onoff', 'matter_switch_position',
                        'matter_button_position', 'matter_button_press_count',
                        'battery', 'battery_low', 'battery_state',
                        'matter_battery_percent_remaining_raw',
                        'matter_battery_percent', 'matter_battery_charge_level',
                        'matter_battery_charge_state',
                        'matter_battery_replacement_needed', 'matter_battery_low',
                    ):
                        c[field] = None
                    for field in (
                        'matter_last_sync_at', 'last_motion_at', 'door_event_ms',
                        'last_transition_at', 'matter_button_event_at',
                    ):
                        c[field] = 0
                    c['door_status'] = 'unknown'
                    c['matter_button_event'] = ''

                restored_clients[deviceID] = c

            documents = _state_documents(
                restored_clients, restored_routes,
                (system_armed, system_arm_state), automation_state,
            )

            previous_clients = dict(clients)
            previous_routes = list(routes)
            previous_system = _system_state_values()
            try:
                set_routes(restored_routes)
                set_system_arm_state(system_armed, system_arm_state)
                clients.clear()
                clients.update(restored_clients)
                write_json_batch_atomic(documents)
            except Exception:
                clients.clear()
                clients.update(previous_clients)
                routes[:] = previous_routes
                set_system_arm_state(*previous_system)
                raise
            _clear_migrated_recharge(clients)

        except Exception as error:
            LOGGER.error('Server state load rejected: file=%s reason=%s',
                         getattr(error, 'filename', Path(state_file).name),
                         getattr(error, 'reason', type(error).__name__))
            return False

        state_loaded = True
        return True

    return {
        'save_state': save_state,
        'load_state': load_state,
    }

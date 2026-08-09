"""Server persistence helpers for KotiBot.

This module owns server/subsystem state loading and persistence.

Automation flow:
1. Security actions are loaded from security_actions.json.
2. Ordinary device automations are loaded from automations_state.json.
3. Both are normalized into the shared in-memory ROUTES list.
4. save_state() separates the shared list back into its subsystem files.
5. Legacy client-embedded recharge rules are migrated into automations_state.json.

All callers must hold the shared state lock while mutating CLIENTS or ROUTES
before calling save_state().
"""

import logging

from server_core.io import (
    JsonStateReadError,
    read_json_object,
    write_json_atomic,
)

LOGGER = logging.getLogger(__name__)

TAPO_DEVICE_STATE_KEYS = (
    'tapo_id', 'tapo_mac', 'tapo_model', 'tapo_device_type',
    'tapo_ip', 'tapo_alias', 'tapo_control_ready', 'tapo_control_error',
    'tapo_is_on', 'tapo_brightness', 'tapo_dimmable',
    'tapo_kind', 'tapo_dashboard_section',
    'tapo_is_bulb', 'tapo_is_plug', 'tapo_is_outlet_extender',
    'tapo_is_hub', 'tapo_is_hub_child', 'tapo_is_camera',
    'tapo_is_button', 'tapo_is_switch',
    'tapo_trigger_log_supported',
    'tapo_last_trigger_event', 'tapo_last_trigger_id',
    'tapo_last_trigger_event_id', 'tapo_last_trigger_at',
    'tapo_room_power', 'tapo_hide_dashboard',
    'tapo_color_temperature', 'tapo_hue', 'tapo_saturation',
    'tapo_desired_lighting_mode', 'tapo_desired_lighting_updated_at',
    'tapo_desired_brightness', 'tapo_desired_color_temperature',
    'tapo_desired_hue', 'tapo_desired_saturation',
    'tapo_desired_white_saturation',
    'tapo_pending_power_commands',
    'tapo_battery', 'tapo_battery_level', 'tapo_battery_percent',
    'tapo_battery_low', 'tapo_battery_state',
    'tapo_child_id', 'tapo_child_name', 'tapo_child_kind',
    'tapo_child_model', 'tapo_child_category', 'tapo_child_avatar',
    'tapo_child_type', 'tapo_child_mac', 'tapo_child_status',
    'tapo_child_rssi', 'tapo_child_signal_level',
    'tapo_parent_device_id', 'tapo_parent_id', 'tapo_parent_model',
    'tapo_parent_alias', 'tapo_parent_ip',
    'tapo_supports_power', 'tapo_supports_brightness',
    'tapo_supports_color_temp', 'tapo_supports_color',
    'tapo_supports_rtsp', 'tapo_supports_onvif',
    'tapo_rtsp_url', 'tapo_onvif_port', 'tapo_children',
    'tapo_children_initialized',
)

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
    'fcm_token',
    'fcm_token_at',
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
    'fcm_token',
    'fcm_token_at',
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
        try:
            data = read_json_object(path)
        except JsonStateReadError:
            return {}

        items = data.get(root_key) if isinstance(data, dict) else None

        if not isinstance(items, dict):
            return {}

        return {
            str(deviceID): dict(state)
            for deviceID, state in items.items()
            if isinstance(deviceID, str) and isinstance(state, dict)
        }

    def _write_subsystem_state_file(path, root_key, items):
        write_json_atomic(path, {root_key: items})

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
            return [
                dict(item)
                for item in stored_clients
                if isinstance(item, dict)
            ]

        if not isinstance(stored_clients, dict):
            return []

        group_names = list(SERVER_CLIENT_GROUP_ORDER)
        group_names.extend(
            sorted(
                group_name
                for group_name in stored_clients
                if group_name not in group_names
            )
        )

        items = []
        seen_device_ids = set()

        for group_name in group_names:
            group_items = stored_clients.get(group_name, [])

            if not isinstance(group_items, list):
                continue

            for raw_item in group_items:
                if not isinstance(raw_item, dict):
                    continue

                item = dict(raw_item)
                deviceID = str(item.get('deviceID') or '').strip()

                if not deviceID or deviceID in seen_device_ids:
                    continue

                seen_device_ids.add(deviceID)
                items.append(item)

        return items

    def _read_json_object_file(path):
        try:
            data = read_json_object(path)
        except JsonStateReadError:
            return {}

        return data

    def _write_json_object_file(path, data):
        write_json_atomic(path, data if isinstance(data, dict) else {})

    def _route_is_device_automation(route):
        return str(route.get('scope') or '').strip().lower() == 'automation'

    def _stored_route(route):
        item = dict(route)
        item.pop('scope', None)
        return item
    
    def _save_automation_state_file():
        automation_state = _read_json_object_file(automation_state_file)
        recharge_rules = automation_state.get(automation_type_tapo_recharge)

        if not isinstance(recharge_rules, dict):
            recharge_rules = {}

        for deviceID, client in clients.items():
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

            client.pop('tapo_recharge', None)

            store = client.get('automations')

            if isinstance(store, dict):
                store.pop(automation_type_tapo_recharge, None)

                if not store:
                    client.pop('automations', None)

        if recharge_rules:
            automation_state[automation_type_tapo_recharge] = recharge_rules
        else:
            automation_state.pop(automation_type_tapo_recharge, None)

        device_automations = [
            _stored_route(route)
            for route in routes
            if isinstance(route, dict) and _route_is_device_automation(route)
        ]

        if device_automations:
            automation_state[automation_type_device_routes] = device_automations
        else:
            automation_state.pop(automation_type_device_routes, None)

        _write_json_object_file(automation_state_file, automation_state)

    def _save_security_actions_file():
        actions = [
            _stored_route(route)
            for route in routes
            if isinstance(route, dict) and not _route_is_device_automation(route)
        ]
        _write_json_object_file(security_actions_file, {'actions': actions})

    def _save_subsystem_state_files():
        tapo_devices = {}
        matter_devices = {}
        android_home_clients = {}

        for deviceID, client in clients.items():
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
                tapo_state = {}

                for key in TAPO_DEVICE_STATE_KEYS:
                    if key not in client:
                        continue

                    value = client.get(key)

                    if key == 'tapo_children' and isinstance(value, list):
                        value = [
                            {
                                child_key: child_value
                                for child_key, child_value in child.items()
                                if child_key != 'raw'
                            }
                            for child in value
                            if isinstance(child, dict)
                        ]

                    tapo_state[key] = value

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

        _write_subsystem_state_file(
            tapo_device_state_file,
            'devices',
            tapo_devices,
        )
        _write_subsystem_state_file(
            matter_device_state_file,
            'devices',
            matter_devices,
        )
        _write_subsystem_state_file(
            android_home_state_file,
            'clients',
            android_home_clients,
        )

    def _server_state_data():
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

        grouped_clients = {
            group_name: []
            for group_name in SERVER_CLIENT_GROUP_ORDER
        }

        for client in clients.values():
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

    def _write_current_state_files():
        _save_automation_state_file()
        _save_security_actions_file()
        _save_subsystem_state_files()
        write_json_atomic(state_file, _server_state_data())

    def save_state():
        try:
            broadcast_state()
            _write_current_state_files()
        except Exception:
            LOGGER.exception('Failed to save server state: %s', state_file)

    def load_state():
        nonlocal state_loaded

        if state_loaded:
            return

        try:
            data = _read_json_object_file(state_file)
            security_actions_state = _read_json_object_file(security_actions_file)
            security_actions = security_actions_state.get('actions')

            if not isinstance(security_actions, list):
                security_actions = data.get('routes', [])

            automation_state = _read_json_object_file(automation_state_file)
            device_automations = automation_state.get(automation_type_device_routes, [])

            if not isinstance(device_automations, list):
                device_automations = []

            set_routes(
                [r for r in security_actions if isinstance(r, dict)]
                + [
                    {**route, 'scope': 'automation'}
                    for route in device_automations
                    if isinstance(route, dict)
                ]
            )
            system_state = data.get('system') if isinstance(data.get('system'), dict) else {}
            system_armed = bool(system_state.get('armed', False))
            system_arm_state = clean_arm_state(
                system_state.get('arm_state', system_state.get('armState', 'night' if system_armed else 'day'))
            )
            set_system_arm_state(system_armed, system_arm_state)
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

            clients.clear()

            for item in _stored_server_client_items(data):
                deviceID = item.get('deviceID')
                if not deviceID:
                    continue

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

                clients[deviceID] = c

            _write_current_state_files()

        except Exception:
            set_routes([])
            LOGGER.exception('Failed to load server state: %s', state_file)

        state_loaded = True

    return {
        'save_state': save_state,
        'load_state': load_state,
    }

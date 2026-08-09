"""Security Action route helpers for KotiBot.

These helpers handle KotiBot Security Action routes, not Flask routes. Runtime
state and callbacks are supplied through ``ctx`` to avoid importing kotibot_server.py.
"""

MATTER_ENVIRONMENT_ROUTE_KINDS = {
    'temperature',
    'humidity',
    'environment',
    'battery',
    'power',
    'power_source',
    'powersource',
}

MATTER_MOTION_ROUTE_WORDS = (
    'motion',
    'occupancy',
    'presence',
)

MATTER_SECURITY_ROUTE_WORDS = (
    'contact',
    'motion',
    'occupancy',
    'presence',
    'tamper',
    'vibration',
    'glass',
    'break',
    'smoke',
    'carbon monoxide',
    'co alarm',
    'water',
    'leak',
    'flood',
    'door',
    'window',
    'security',
    'alarm',
)


def build_security_action_runtime(ctx):
    CLIENTS = ctx['clients']
    ROUTES = ctx['routes']
    client_has_role = ctx['client_has_role']
    CLIENT_ROLE_CAM = ctx['client_role_cam']
    CLIENT_ROLE_DSS = ctx['client_role_dss']
    CLIENT_ROLE_KEY = ctx['client_role_key']
    CLIENT_ROLE_TAPO = ctx['client_role_tapo']
    cancel_door_sound_repeat = ctx['cancel_door_sound_repeat']
    cancel_route_runtime = ctx.get(
        'cancel_route_runtime',
        lambda route: None,
    )
    system_arm_state = ctx['system_arm_state']

    def clean_arm_state(value):
        state = str(value or '').strip().lower()

        if state in ('day', 'night', 'away'):
            return state

        return 'day'

    def set_routes(new_routes):
        ROUTES.clear()
        ROUTES.extend([r for r in new_routes if isinstance(r, dict)])

    def _norm_route_value(value):
        return str(value or '').strip().lower().replace(' ', '_').replace('-', '_')

    def _route_source_device(route):
        return str(
            route.get('from_deviceID')
            or route.get('from_device_id')
            or route.get('sourceDeviceID')
            or route.get('source_deviceID')
            or route.get('source_device_id')
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

    def _route_target_device(route):
        return str(
            route.get('to_deviceID')
            or route.get('to_device_id')
            or route.get('targetDeviceID')
            or route.get('target_deviceID')
            or route.get('target_device_id')
            or ''
        ).strip()

    def _route_notification_target_device(route):
        return str(
            route.get('target_key_deviceID')
            or route.get('targetKeyDeviceID')
            or route.get('notification_target_deviceID')
            or route.get('notificationTargetDeviceID')
            or route.get('to_deviceID')
            or route.get('targetDeviceID')
            or route.get('targetID')
            or route.get('target_id')
            or ''
        ).strip()

    def _route_device_target_id(route):
        return str(
            route.get('targetID')
            or route.get('target_id')
            or route.get('to_input')
            or ''
        ).strip()

    def _route_field_matches_device(value, deviceID):
        clean_value = str(value or '').strip()
        clean_deviceID = str(deviceID or '').strip()

        if not clean_value or not clean_deviceID:
            return False

        return clean_value == clean_deviceID or clean_value.startswith(f'{clean_deviceID}|')

    def _route_references_device(route, deviceID):
        return (
            _route_field_matches_device(_route_source_device(route), deviceID)
            or _route_field_matches_device(_route_target_device(route), deviceID)
            or _route_field_matches_device(_route_notification_target_device(route), deviceID)
            or _route_field_matches_device(_route_device_target_id(route), deviceID)
        )

    def _route_removed_by_disabled_roles(route, deviceID, removed_roles):
        clean_removed_roles = set(removed_roles or [])
        trigger = _route_trigger(route)
        action = _route_action_kind(route)
        is_source = _route_field_matches_device(_route_source_device(route), deviceID)

        if is_source and CLIENT_ROLE_DSS in clean_removed_roles and trigger in ('door_open', 'door_close', 'open', 'close', 'closed', 'door_opened', 'door_closed'):
            return True

        if is_source and CLIENT_ROLE_CAM in clean_removed_roles and trigger in ('motion', 'camera_motion', 'motion_detected'):
            return True

        if CLIENT_ROLE_KEY in clean_removed_roles and action in ('notification', 'notify', 'push', 'key_notification'):
            return _route_field_matches_device(_route_notification_target_device(route), deviceID)

        if CLIENT_ROLE_CAM in clean_removed_roles and action in ('recording', 'record', 'video', 'camera', 'cam'):
            return _route_field_matches_device(_route_target_device(route), deviceID)

        if CLIENT_ROLE_TAPO in clean_removed_roles and action in ('device', 'device_on', 'turn_on_device', 'turn_on', 'power_on'):
            return (
                _route_field_matches_device(_route_target_device(route), deviceID)
                or _route_field_matches_device(_route_device_target_id(route), deviceID)
            )

        return False

    def prune_routes_for_client_change(deviceID, removed_roles=None, remove_all=False):
        clean_deviceID = str(deviceID or '').strip()

        if not clean_deviceID:
            return False

        routes = list(ROUTES)
        kept_routes = []
        removed_routes = []

        for route in routes:
            if not isinstance(route, dict):
                continue

            should_remove = (
                _route_references_device(route, clean_deviceID)
                if remove_all
                else _route_removed_by_disabled_roles(route, clean_deviceID, removed_roles)
            )

            if should_remove:
                removed_routes.append(route)
            else:
                kept_routes.append(route)

        if len(kept_routes) == len(routes):
            return False

        set_routes(kept_routes)

        for route in removed_routes:
            cancel_route_runtime(route)

        return True

    def _client_is_matter(client):
        return (
            str(client.get('source') or '').strip().lower() == 'matter'
            or str(client.get('deviceID') or '').startswith('matter:')
        )

    def _client_matter_kinds(client):
        raw = client.get('matter_kinds')

        if not isinstance(raw, (list, tuple, set)) or not raw:
            raw = [client.get('matter_kind')]

        return [
            str(kind or '').strip().lower()
            for kind in raw
            if str(kind or '').strip()
        ]

    def _client_security_text(client):
        values = [
            client.get('matter_kind'),
            *(_client_matter_kinds(client) if _client_is_matter(client) else []),
            client.get('matter_device_type'),
            client.get('matter_cluster'),
            client.get('tapo_kind'),
            client.get('tapo_child_kind'),
            client.get('tapo_device_type'),
            client.get('tapo_child_type'),
            client.get('tapo_child_category'),
            client.get('tapo_child_avatar'),
            client.get('model'),
            client.get('manufacturer'),
            client.get('clientName'),
        ]

        return ' '.join(
            str(value or '').strip().lower()
            for value in values
            if str(value or '').strip()
        )

    def _client_security_text_has_any(client, words):
        text = _client_security_text(client)

        return any(str(word or '').strip().lower() in text for word in words)

    def _client_is_matter_contact(client):
        if not _client_is_matter(client):
            return False

        kinds = _client_matter_kinds(client)

        return (
            'contact' in kinds
            or client.get('contact_open') is not None
            or client.get('contact_state_value') is not None
            or 'contact' in str(client.get('matter_device_type') or '').strip().lower()
        )

    def _client_is_matter_motion(client):
        return _client_is_matter(client) and _client_security_text_has_any(client, MATTER_MOTION_ROUTE_WORDS)

    def _client_is_matter_environment_only(client):
        if not _client_is_matter(client):
            return False

        if _client_is_matter_contact(client) or _client_is_matter_motion(client):
            return False

        kinds = _client_matter_kinds(client)

        return bool(kinds) and all(kind in MATTER_ENVIRONMENT_ROUTE_KINDS for kind in kinds)

    def _client_is_matter_environment(client):
        if not _client_is_matter(client):
            return False

        kinds = _client_matter_kinds(client)

        return (
            any(kind in ('temperature', 'humidity', 'environment') for kind in kinds)
            or client.get('temperature_c') is not None
            or client.get('humidity_percent') is not None
        )

    def _client_is_matter_security_sensor(client):
        if not _client_is_matter(client):
            return False

        if _client_is_matter_environment_only(client):
            return False

        if _client_is_matter_contact(client) or _client_is_matter_motion(client):
            return True

        return _client_security_text_has_any(client, MATTER_SECURITY_ROUTE_WORDS)

    def _client_is_tapo_camera(client):
        if not client_has_role(client, CLIENT_ROLE_TAPO):
            return False

        return str(client.get('tapo_kind') or client.get('tapo_device_type') or '').strip().lower() == 'camera'

    def _client_is_tapo_motion_source(client):
        if not client_has_role(client, CLIENT_ROLE_TAPO):
            return False

        return _client_is_tapo_camera(client) or _client_security_text_has_any(client, MATTER_MOTION_ROUTE_WORDS)

    def _client_is_security_trigger_source(client):
        return (
            isinstance(client, dict)
            and client.get('provisioned')
            and (
                client_has_role(client, CLIENT_ROLE_DSS)
                or client_has_role(client, CLIENT_ROLE_CAM)
                or _client_is_matter_security_sensor(client)
                or _client_is_matter_environment(client)
                or _client_is_tapo_motion_source(client)
            )
        )

    def _route_has_valid_source(route):
        source_deviceID = _route_source_device(route)
        source_client = CLIENTS.get(source_deviceID)

        if not _client_is_security_trigger_source(source_client):
            return False

        trigger = _route_trigger(route)

        if trigger in ('door_open', 'door_close', 'open', 'close', 'closed', 'door_opened', 'door_closed'):
            if _client_is_matter(source_client):
                return _client_is_matter_contact(source_client)

            return client_has_role(source_client, CLIENT_ROLE_DSS)

        if trigger in ('motion', 'camera_motion', 'motion_detected'):
            return (
                client_has_role(source_client, CLIENT_ROLE_CAM)
                or _client_is_tapo_motion_source(source_client)
                or _client_is_matter_motion(source_client)
                or (_client_is_matter_security_sensor(source_client) and not _client_is_matter_contact(source_client))
            )

        if trigger in ('temperature_above', 'temperature_below'):
            return _client_is_matter_environment(source_client) and (
                any(kind in ('temperature', 'environment') for kind in _client_matter_kinds(source_client))
                or source_client.get('temperature_c') is not None
            )

        if trigger in ('humidity_above', 'humidity_below'):
            return _client_is_matter_environment(source_client) and (
                any(kind in ('humidity', 'environment') for kind in _client_matter_kinds(source_client))
                or source_client.get('humidity_percent') is not None
            )

        return False

    def _route_target_client_from_value(value):
        clean_value = str(value or '').strip()

        if not clean_value:
            return None

        return CLIENTS.get(clean_value.split('|', 1)[0])

    def _route_has_valid_target(route):
        action = _route_action_kind(route)

        if action in ('sound', 'wav', 'audio', 'play_sound'):
            return True

        if action in ('notification', 'notify', 'push', 'key_notification'):
            target_deviceID = _route_notification_target_device(route)

            if not target_deviceID or target_deviceID == '__all_key_clients__':
                return True

            target_client = _route_target_client_from_value(target_deviceID)
            return isinstance(target_client, dict) and target_client.get('provisioned') and client_has_role(target_client, CLIENT_ROLE_KEY)

        if action in ('recording', 'record', 'video', 'camera', 'cam'):
            target_client = _route_target_client_from_value(
                _route_target_device(route)
            )

            return (
                isinstance(target_client, dict)
                and target_client.get('provisioned')
                and (
                    client_has_role(
                        target_client,
                        CLIENT_ROLE_CAM,
                    )
                    or _client_is_tapo_camera(
                        target_client
                    )
                )
            )

        if action in ('device', 'device_on', 'turn_on_device', 'turn_on', 'power_on'):
            target_client = _route_target_client_from_value(_route_target_device(route) or _route_device_target_id(route))
            return isinstance(target_client, dict) and target_client.get('provisioned') and client_has_role(target_client, CLIENT_ROLE_TAPO)

        return True

    def prune_invalid_routes_for_clients():
        routes = list(ROUTES)
        kept_routes = [
            route for route in routes
            if isinstance(route, dict)
            and _route_has_valid_source(route)
            and _route_has_valid_target(route)
        ]

        if len(kept_routes) == len(routes):
            return False

        set_routes(kept_routes)
        return True

    def _route_sound_filename(route):
        return str(route.get('filename') or route.get('sound') or route.get('to_input') or '').strip()

    def _route_bool(value, default=False):
        if value in (None, ''):
            return bool(default)

        if isinstance(value, bool):
            return value

        if isinstance(value, (int, float)):
            return value != 0

        return str(value).strip().lower() not in ('0', 'false', 'no', 'off', 'disabled')

    def _route_arm_states(route):
        raw = route.get('arm_states', route.get('armStates', route.get('active_arm_states', route.get('activeArmStates'))))

        if raw in (None, ''):
            raw = route.get('arm_state', route.get('armState'))

        if raw in (None, ''):
            return []

        if isinstance(raw, str):
            raw = raw.replace('+', ',').split(',')

        if not isinstance(raw, (list, tuple, set)):
            return []

        states = []

        for item in raw:
            state = clean_arm_state(item)

            if state not in states:
                states.append(state)

        return states

    def _route_enabled_for_current_arm_state(route):
        states = _route_arm_states(route)

        if not states:
            return True

        return clean_arm_state(system_arm_state()) in states

    def door_sound_repeat_allowed(deviceID, filename):
        clean_deviceID = str(deviceID or '').strip()
        clean_filename = str(filename or '').strip()

        if not clean_deviceID:
            return False

        for route in list(ROUTES):
            if not isinstance(route, dict):
                continue

            if _route_source_device(route) != clean_deviceID:
                continue

            if _route_trigger(route) != 'door_open':
                continue

            if _route_action_kind(route) not in ('sound', 'wav', 'audio', 'play_sound'):
                continue

            if not _route_bool(route.get('repeat', route.get('repeatSound')), True):
                continue

            route_filename = _route_sound_filename(route)

            if clean_filename and route_filename and route_filename != clean_filename:
                continue

            if _route_enabled_for_current_arm_state(route):
                return True

        return False

    return {
        'clean_arm_state': clean_arm_state,
        'set_routes': set_routes,
        'prune_routes_for_client_change': prune_routes_for_client_change,
        'prune_invalid_routes_for_clients': prune_invalid_routes_for_clients,
        'door_sound_repeat_allowed': door_sound_repeat_allowed,
    }
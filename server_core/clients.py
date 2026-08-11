"""Client identity and role helpers for KotiBot.

This module receives live state and callbacks through ``ctx`` so it does not
import ``kotibot_server.py``.
"""

CLIENT_ROLE_UNP = 'UNP'
CLIENT_ROLE_DSS = 'DSS'
CLIENT_ROLE_CAM = 'CAM'
CLIENT_ROLE_KEY = 'KEY'
CLIENT_ROLE_TAPO = 'TAPO'


def build_client_runtime(ctx):
    CLIENTS = ctx['clients']
    request_json = ctx['request_json']
    request_ip = ctx['request_ip']
    request_header = ctx.get('request_header', lambda name: '')
    now_epoch = ctx['now_epoch']
    clean_zone_name = ctx['clean_zone_name']
    cancel_door_sound_repeat = ctx['cancel_door_sound_repeat']
    prune_routes_for_client_change = ctx['prune_routes_for_client_change']
    get_system_armed = ctx['system_armed']
    get_android_home_apply_seen_client = ctx['android_home_apply_seen_client']

    CLIENT_ROLE_CAM_LOCAL = ctx.get('client_role_cam', CLIENT_ROLE_CAM)
    CLIENT_ROLE_DSS_LOCAL = ctx.get('client_role_dss', CLIENT_ROLE_DSS)
    CLIENT_ROLE_KEY_LOCAL = ctx.get('client_role_key', CLIENT_ROLE_KEY)
    CLIENT_ROLE_TAPO_LOCAL = ctx.get('client_role_tapo', CLIENT_ROLE_TAPO)
    CLIENT_ROLE_UNP_LOCAL = ctx.get('client_role_unp', CLIENT_ROLE_UNP)
    DOOR_RECALIBRATION_COMMAND_TIMEOUT_SECONDS = ctx['door_recalibration_command_timeout_seconds']

    def client_has_role(client, role):
        clientRole = client.get('clientRole') if isinstance(client, dict) else None

        if isinstance(clientRole, list):
            return role in clientRole

        if isinstance(clientRole, str):
            return clientRole == role or role in normalize_client_roles(clientRole)

        return False

    def normalize_client_roles(value):
        if value is None:
            return []

        if isinstance(value, str):
            value = value.replace("+", ",").split(",")

        roles = []

        for item in value:
            if not isinstance(item, str):
                continue

            normalized = item.strip().lower()

            if not normalized:
                continue

            if normalized in ('camera', 'cam', 'c'):
                role = CLIENT_ROLE_CAM_LOCAL
            elif normalized in ('door', 'dss', 'doorbell', 'sensor'):
                role = CLIENT_ROLE_DSS_LOCAL
            elif normalized in ('both', 'all'):
                if CLIENT_ROLE_CAM_LOCAL not in roles:
                    roles.append(CLIENT_ROLE_CAM_LOCAL)
                if CLIENT_ROLE_DSS_LOCAL not in roles:
                    roles.append(CLIENT_ROLE_DSS_LOCAL)
                continue
            elif normalized in ('key', 'presence', 'user', 'controller'):
                role = CLIENT_ROLE_KEY_LOCAL
            elif normalized in ('tapo', 'smart', 'smart_home', 'light', 'bulb', 'plug', 'outlet'):
                role = CLIENT_ROLE_TAPO_LOCAL
            elif normalized in ('unp', 'unprovisioned', 'waiting'):
                role = CLIENT_ROLE_UNP_LOCAL
            else:
                continue

            if role not in roles:
                roles.append(role)

        if CLIENT_ROLE_KEY_LOCAL in roles:
            return [CLIENT_ROLE_KEY_LOCAL]

        if CLIENT_ROLE_TAPO_LOCAL in roles:
            if CLIENT_ROLE_CAM_LOCAL in roles:
                return [CLIENT_ROLE_CAM_LOCAL, CLIENT_ROLE_TAPO_LOCAL]

            return [CLIENT_ROLE_TAPO_LOCAL]

        return roles

    def incoming_detected_roles(data, inc_type=''):
        message_type = str(
            inc_type
            or data.get('type')
            or ''
        ).strip().lower()

        if message_type in ('key_telemetry', 'presence_telemetry'):
            return [CLIENT_ROLE_KEY_LOCAL]

        if message_type in ('door_telemetry', 'doormonitor'):
            return [CLIENT_ROLE_DSS_LOCAL]

        if message_type in ('camera_ping', 'camera_motion'):
            return [CLIENT_ROLE_CAM_LOCAL]

        reported_roles = (
            data.get('clientRole')
            or data.get('client_role')
            or data.get('role')
            or request_header('X-Client-Role')
            or ''
        )

        return [
            role
            for role in normalize_client_roles(reported_roles)
            if role != CLIENT_ROLE_UNP_LOCAL
        ]

    def record_detected_roles(client, incoming_roles):
        if not isinstance(client, dict) or client.get('provisioned'):
            return False

        incoming = normalize_client_roles(incoming_roles)

        if not incoming:
            return False

        existing = normalize_client_roles(client.get('detectedRole'))

        if CLIENT_ROLE_KEY_LOCAL in incoming:
            detected = [CLIENT_ROLE_KEY_LOCAL]
        elif CLIENT_ROLE_TAPO_LOCAL in incoming:
            detected = [CLIENT_ROLE_TAPO_LOCAL]
        elif CLIENT_ROLE_KEY_LOCAL in existing:
            detected = [CLIENT_ROLE_KEY_LOCAL]
        elif CLIENT_ROLE_TAPO_LOCAL in existing:
            detected = [CLIENT_ROLE_TAPO_LOCAL]
        else:
            combined = set(existing + incoming)
            detected = [
                role
                for role in (CLIENT_ROLE_CAM_LOCAL, CLIENT_ROLE_DSS_LOCAL)
                if role in combined
            ]

        if not detected:
            return False

        detected_value = ','.join(detected)

        if client.get('detectedRole') == detected_value:
            return False

        client['detectedRole'] = detected_value
        return True

    def apply_enabled_roles(c, roles):
        normalized = normalize_client_roles(roles)

        if not normalized:
            return False, 'At least one service must remain enabled'

        if CLIENT_ROLE_KEY_LOCAL in normalized and len(normalized) > 1:
            normalized = [CLIENT_ROLE_KEY_LOCAL]

        old_roles = normalize_client_roles(c.get('clientRole'))

        if old_roles == normalized:
            return True, ''

        if CLIENT_ROLE_CAM_LOCAL in old_roles and CLIENT_ROLE_CAM_LOCAL not in normalized:
            c['recording_enabled'] = False
            c['recording'] = False
            c['preview_viewers'] = {}
            c['pending_command'] = {}
            c['frame'] = None
            c['frame_seq'] = 0
            c['frame_last_seen'] = 0
            c['camera_auto_rotation'] = None
            c['camera_auto_rotation_at'] = 0
            c['camera_auto_rotation_lens'] = ''

        if CLIENT_ROLE_DSS_LOCAL in old_roles and CLIENT_ROLE_DSS_LOCAL not in normalized:
            cancel_door_sound_repeat(c.get('deviceID'))
            c['door_status'] = 'unknown'
            c['calibrating'] = 0

        removed_roles = [role for role in old_roles if role not in normalized]

        if removed_roles:
            prune_routes_for_client_change(c.get('deviceID'), removed_roles=removed_roles)

        c['clientRole'] = normalized
        c['provisioned'] = True

        pending = c.setdefault('pending_command', {})
        pending['clientRole'] = normalized

        if CLIENT_ROLE_CAM_LOCAL not in normalized:
            pending['recordingEnabled'] = 0
            pending['cameraEnabled'] = 0

        return True, ''

    def init_client(deviceID):
        return {
            'deviceID': deviceID,
            'clientName': deviceID,
            'clientRole': CLIENT_ROLE_UNP_LOCAL,
            'ip': '',
            'last_seen': 0,
            'needs_heartbeat': False,
            'heartbeat_requested_at': 0,
            'heartbeat_pending': False,
            'provisioned': False,
            'battery': None,
            'armed': 0,
            'brand': '',
            'androidVersion': '',
            'hasDSSHW': None,
            'telemetry_count': 0,
            'pending_command': {},
            'version': 'unknown',
            'zone_name': '',
            'heartbeat_interval_ms': 30000,
            'fcm_token': '',
            'fcm_token_at': 0,
            'detectedRole': '',
        }

    def get_unprovisioned_client(deviceID):
        data = request_json()

        c = CLIENTS.get(deviceID)
        if not c:
            c = init_client(deviceID)
            CLIENTS[deviceID] = c

        c['deviceID'] = deviceID
        c['clientRole'] = CLIENT_ROLE_UNP_LOCAL
        c['provisioned'] = False
        c['clientName'] = c.get('clientName') or deviceID
        c['battery'] = data.get('battery', c.get('battery'))
        c['ip'] = request_ip()
        c['brand'] = data.get('brand', c.get('brand', ''))
        c['androidVersion'] = data.get('androidVersion', c.get('androidVersion', ''))
        c['version'] = str(data.get('version', c.get('version', 'unknown')) or 'unknown')
        c['hasDSSHW'] = data.get('hasDSSHW', c.get('hasDSSHW'))
        c['last_seen'] = now_epoch()
        c['telemetry_count'] = c.get('telemetry_count', 0) + 1

        return c

    def get_clients_for_device(deviceID):
        direct = CLIENTS.get(deviceID)

        if direct and direct.get('deviceID') == deviceID:
            return [direct]

        return [c for c in CLIENTS.values() if c.get('deviceID') == deviceID]

    def door_recalibration_command_keys():
        return ('triggerRecalibrate', 'recalibrateSeq', 'recalibrate_seq', 'recalibrate')

    def queue_door_recalibration(c):
        now = now_epoch()
        recal_seq = max(
            int(c.get('recalibrate_seq', 0) or 0) + 1,
            int(now * 1000)
        )

        c['recalibrate_seq'] = recal_seq
        c['recalibration_phase'] = 'requested'
        c['recalibration_requested_at'] = now
        c['recalibration_ignore_until'] = now + DOOR_RECALIBRATION_COMMAND_TIMEOUT_SECONDS
        c['door_status'] = 'closed'
        c['openness_score'] = 0.0
        c['door_angle'] = 0.0
        c['ignore_door_open_until_closed'] = False
        c['calibrating'] = 1
        c['calibration_samples'] = 0

        pending = c.setdefault('pending_command', {})
        pending['triggerRecalibrate'] = recal_seq
        pending['recalibrateSeq'] = recal_seq
        pending['recalibrate_seq'] = recal_seq
        pending.pop('recalibrate', None)

        return recal_seq

    def register_seen_client(c, data, path, inc_type=''):
        changed = False

        c['ip'] = request_ip()
        c['last_seen'] = now_epoch()
        c['heartbeat_pending'] = False
        c['heartbeat_requested_at'] = 0
        c['needs_heartbeat'] = False

        battery = data.get('battery', c.get('battery'))

        if battery != c.get('battery'):
            c['battery'] = battery
            changed = True

        c['armed'] = 1 if bool(get_system_armed()) else 0
        c['telemetry_count'] = c.get('telemetry_count', 0) + 1

        targets = [c]
        deviceID = c.get('deviceID')
        clients = get_clients_for_device(deviceID)
        unp_client = next((x for x in clients if client_has_role(x, CLIENT_ROLE_UNP_LOCAL)), None)
        detected_roles = incoming_detected_roles(data, inc_type)

        if unp_client and unp_client is not c:
            targets.append(unp_client)

        for target in targets:
            if record_detected_roles(target, detected_roles):
                changed = True

            if 'version' in data:
                target['version'] = str(data['version'] or '')

            if 'brand' in data:
                target['brand'] = str(data['brand'])

            if 'androidVersion' in data:
                target['androidVersion'] = str(data['androidVersion'])

        apply_android_seen_client = get_android_home_apply_seen_client()

        if (
            callable(apply_android_seen_client)
            and (
                client_has_role(c, CLIENT_ROLE_CAM_LOCAL)
                or client_has_role(c, CLIENT_ROLE_DSS_LOCAL)
            )
        ):
            return bool(apply_android_seen_client(c, data, path, inc_type)) or changed

        return changed

    def used_room_names():
        rooms = set()

        for c in CLIENTS.values():
            if not isinstance(c, dict):
                continue

            if not c.get('provisioned'):
                continue

            if client_has_role(c, CLIENT_ROLE_KEY_LOCAL):
                continue

            room = clean_zone_name(c.get('zone_name'))

            if room:
                rooms.add(room)

        return sorted(rooms, key=lambda name: name.lower())

    return {
        'client_has_role': client_has_role,
        'normalize_client_roles': normalize_client_roles,
        'apply_enabled_roles': apply_enabled_roles,
        'init_client': init_client,
        'get_unprovisioned_client': get_unprovisioned_client,
        'get_clients_for_device': get_clients_for_device,
        'door_recalibration_command_keys': door_recalibration_command_keys,
        'queue_door_recalibration': queue_door_recalibration,
        'register_seen_client': register_seen_client,
        'used_room_names': used_room_names,
    }
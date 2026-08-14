"""Dashboard status payload builders for KotiBot.

This module intentionally receives all runtime dependencies through ``ctx`` so it
can build dashboard status payloads without importing ``kotibot_server.py``.
"""


def build_status_runtime(ctx):
    CLIENTS = ctx['clients']
    CLIENT_ROLE_CAM = ctx['client_role_cam']
    CLIENT_ROLE_DSS = ctx['client_role_dss']
    CLIENT_ROLE_KEY = ctx['client_role_key']
    CLIENT_ROLE_TAPO = ctx['client_role_tapo']
    CLIENT_ROLE_UNP = ctx['client_role_unp']
    PREVIEW_VIEWER_TTL_SECONDS = ctx['preview_viewer_ttl_seconds']
    STALE_CLIENT_SECONDS = ctx['stale_client_seconds']
    MATTER_STALE_CLIENT_SECONDS = ctx['matter_stale_client_seconds']
    SERVER_START_EPOCH = ctx['server_start_epoch']
    state_lock = ctx.get('state_lock')

    age_text = ctx['age_text']
    clean_filename_part = ctx['clean_filename_part']
    clean_zone_name = ctx['clean_zone_name']
    client_has_role = ctx['client_has_role']
    android_client_profile = ctx.get(
        'android_client_profile',
        lambda client: {'clientClass': 'unclassified', 'capabilities': []},
    )
    device_has_key = ctx.get('device_has_key')
    duration_text = ctx['duration_text']
    now_epoch = ctx['now_epoch']
    now_local = ctx['now_local']
    voice_talk_active_for_target = ctx['voice_talk_active_for_target']

    def get_system_armed():
        getter = ctx.get('system_armed')
        return bool(getter()) if callable(getter) else bool(getter)

    def get_system_arm_state():
        getter = ctx.get('system_arm_state')
        value = getter() if callable(getter) else getter
        return str(value or 'day')

    def get_environment_snapshot():
        getter = ctx.get('environment_snapshot')
        return getter() if callable(getter) else None

    def get_tapo_lighting_state_snapshot():
        getter = ctx.get('tapo_lighting_state_snapshot')

        if not callable(getter):
            return None

        try:
            snapshot = getter()
        except Exception:
            return None

        return snapshot if isinstance(snapshot, dict) else None

    def get_matter_settings_snapshot():
        getter = ctx.get('matter_settings_snapshot')

        if not callable(getter):
            return {}

        try:
            snapshot = getter()
        except Exception:
            return {}

        return snapshot if isinstance(snapshot, dict) else {}

    def dashboard_auth_status_payload():
        getter = ctx.get('dashboard_auth_status')

        if not callable(getter):
            return {'ok': False, 'dashboard_authenticated': False}

        try:
            status = getter()
        except Exception:
            return {'ok': False, 'dashboard_authenticated': False}

        if isinstance(status, dict):
            payload = dict(status)
        else:
            payload = {'ok': True, 'dashboard_authenticated': bool(status)}

        payload['dashboard_authenticated'] = bool(payload.get('dashboard_authenticated'))
        payload.setdefault('ok', True)
        return payload

    def preview_requested_for_client(c):
        viewers = c.setdefault('preview_viewers', {})
        now = now_epoch()

        for viewer_id, seen_at in list(viewers.items()):
            if now - float(seen_at or 0) > PREVIEW_VIEWER_TTL_SECONDS:
                viewers.pop(viewer_id, None)

        c['preview_requested'] = bool(viewers)
        return c['preview_requested']

    def snapshot_tapo_children(c):
        children = c.get('tapo_children')

        if not isinstance(children, list):
            return []

        allowed_fields = (
            'id',
            'device_id',
            'deviceId',
            'child_id',
            'childId',
            'tapo_child_id',
            'position',
            'index',
            'cli_index',
            'tapo_child_position',
            'tapo_child_index',
            'alias',
            'nickname',
            'name',
            'tapo_child_name',
            'kind',
            'type',
            'category',
            'component',
            'tapo_child_kind',
            'is_on',
            'device_on',
            'on',
            'state',
            'tapo_room_power',
            'room_power',
            'include_in_room_power',
            'tapo_hide_dashboard',
            'tapoHideDashboard',
            'tapo_dashboard_hidden',
            'dashboard_hidden',
            'hide_dashboard',
            'zone_name',
            'room',
            'room_name',
            'zone',
        )

        return [
            {
                field: child.get(field)
                for field in allowed_fields
                if field in child
            }
            for child in children
            if isinstance(child, dict)
        ]

    def _is_client_stale(c, now=None):
        if client_has_role(c, CLIENT_ROLE_TAPO):
            return False

        current_time = now_epoch() if now is None else now

        if str(c.get('source') or '').strip().lower() == 'matter':
            last_seen = float(c.get('matter_last_sync_at', 0) or c.get('last_seen', 0) or 0)
            node_id = str(c.get('matter_node_id') or '').strip()

            if node_id:
                last_seen = max(
                    [last_seen] + [
                        float(peer.get('matter_last_sync_at', 0) or peer.get('last_seen', 0) or 0)
                        for peer in CLIENTS.values()
                        if isinstance(peer, dict)
                        and str(peer.get('source') or '').strip().lower() == 'matter'
                        and str(peer.get('matter_node_id') or '').strip() == node_id
                    ]
                )

            return last_seen == 0 or (current_time - last_seen) > MATTER_STALE_CLIENT_SECONDS

        last_seen = float(c.get('last_seen', 0) or 0)

        if client_has_role(c, CLIENT_ROLE_KEY):
            return False

        return last_seen == 0 or (current_time - last_seen) > STALE_CLIENT_SECONDS

    def snapshot_client(c):
        current_time = now_epoch()
        stale = _is_client_stale(c, current_time)
        android_profile = android_client_profile(c)
        selected_camera = c.get('selected_camera', 'back')

        if client_has_role(c, CLIENT_ROLE_TAPO) and c.get('tapo_kind') == 'camera':
            selected_camera = 'tapo'

        lens_state = (c.get('preview_by_lens') or {}).get(selected_camera, {})
        frame_last_seen = float(c.get('frame_last_seen', 0) or 0)
        frame_age = (current_time - frame_last_seen) if frame_last_seen else None
        frame_live = bool(frame_age is not None and frame_age <= 6.5)

        base = {
            'deviceID': c['deviceID'],
            'clientName': c['clientName'],
            'version': c.get('version', 'unknown'),
            'provisioned': c['provisioned'],
            'stale': stale,
            'battery': c.get('battery'),
            'battery_low': c.get('battery_low'),
            'battery_state': c.get('battery_state'),
            'zone_name': clean_zone_name(c.get('zone_name')),
            'last_update': age_text(c.get('last_seen', 0)),
            'androidClientClass': android_profile['clientClass'],
            'androidCapabilities': list(android_profile['capabilities']),
            'matter_action_settings': c.get('matter_action_settings') if isinstance(c.get('matter_action_settings'), dict) else {}
        }

        if (
            c.get('provisioned')
            and android_profile['clientClass'] in ('control', 'monitor')
            and callable(device_has_key)
        ):
            try:
                base['deviceKeyProvisioned'] = bool(
                    device_has_key(c['deviceID'])
                )
            except Exception:
                # Omit an uncertain state so the dashboard cannot expose a
                # recovery action unless key absence was proven explicitly.
                pass

        is_camera = client_has_role(c, CLIENT_ROLE_CAM)
        is_door = client_has_role(c, CLIENT_ROLE_DSS)
        is_key = client_has_role(c, CLIENT_ROLE_KEY)
        is_tapo = client_has_role(c, CLIENT_ROLE_TAPO)
        camera_talk_available = bool(c.get('provisioned') and is_camera and not is_tapo and not stale)
        camera_talk_active = voice_talk_active_for_target(c.get('deviceID')) if camera_talk_available else False

        base.update({
            'camera_talk_available': camera_talk_available,
            'cameraTalkAvailable': camera_talk_available,
            'camera_talk_active': camera_talk_active,
            'cameraTalkActive': camera_talk_active,
        })

        if str(c.get('source') or '').strip().lower() == 'matter':
            base.update({
                'source': 'matter',
                'manufacturer': c.get('manufacturer', ''),
                'model': c.get('model', ''),
                'matter_node_id': c.get('matter_node_id', ''),
                'matter_endpoint': c.get('matter_endpoint', ''),
                'matter_kind': c.get('matter_kind', ''),
                'matter_kinds': c.get('matter_kinds', []),
                'matter_device_type': c.get('matter_device_type', ''),
                'matter_cluster': c.get('matter_cluster', ''),
                'matter_last_sync_at': c.get('matter_last_sync_at', 0),
                'matter_vendor_name': c.get('matter_vendor_name', ''),
                'matter_product_name': c.get('matter_product_name', ''),
                'matter_node_label': c.get('matter_node_label', ''),
                'matter_hardware_version': c.get('matter_hardware_version', ''),
                'matter_software_version': c.get('matter_software_version', ''),
                'matter_reachable': c.get('matter_reachable'),

                'temperature_raw': c.get('temperature_raw'),
                'temperature_c': c.get('temperature_c'),
                'humidity_raw': c.get('humidity_raw'),
                'humidity_percent': c.get('humidity_percent'),
                'contact_state_value': c.get('contact_state_value'),
                'contact_open': c.get('contact_open'),
                'matter_contact_open_when': c.get('matter_contact_open_when'),
                'occupancy_state_value': c.get('occupancy_state_value'),
                'motion_active': c.get('motion_active'),
                'last_motion_at': c.get('last_motion_at', 0),

                'matter_onoff': c.get('matter_onoff'),
                'matter_switch_position': c.get('matter_switch_position'),
                'matter_switch_positions': c.get('matter_switch_positions'),
                'matter_switch_multipress_max': c.get('matter_switch_multipress_max'),
                'matter_button_event': c.get('matter_button_event', ''),
                'matter_button_event_at': c.get('matter_button_event_at', 0),
                'matter_button_position': c.get('matter_button_position'),
                'matter_button_press_count': c.get('matter_button_press_count'),
                'matter_battery_percent_remaining_raw': c.get('matter_battery_percent_remaining_raw'),
                'matter_battery_percent': c.get('matter_battery_percent'),
                'matter_battery_charge_level': c.get('matter_battery_charge_level'),
                'matter_battery_charge_state': c.get('matter_battery_charge_state'),
                'matter_battery_replacement_needed': c.get('matter_battery_replacement_needed'),
                'matter_battery_low': c.get('matter_battery_low'),
            })

        if not c.get('provisioned'):
            base.update({
                'clientRole': CLIENT_ROLE_UNP,
                'detectedRole': c.get('detectedRole', ''),
                'brand': str(c.get('brand') or '').capitalize(),
                'androidVersion': c.get('androidVersion'),
                'hasDSSHW': c.get('hasDSSHW')
            })
        else:
            base['clientRole'] = c.get('clientRole')
            if is_camera:
                last_motion_at = float(c.get('last_motion_at', 0) or 0)
                motion_recent = bool(last_motion_at and current_time - last_motion_at <= 8.0)

                base.update({
                    'frame_live': frame_live,
                    'frame_age': round(frame_age, 2) if frame_age is not None else None,
                    'recording_enabled': c.get('recording_enabled', False),
                    'motion_detection_enabled': bool(c.get('motion_detection_enabled', False)),
                    'motionDetectionEnabled': bool(c.get('motion_detection_enabled', False)),
                    'motion_detection_threshold': float(c.get('motion_detection_threshold', 18.0) or 18.0),
                    'motionDetectionThreshold': float(c.get('motion_detection_threshold', 18.0) or 18.0),
                    'motion_flashlight_enabled': bool(c.get('motion_flashlight_enabled', False)),
                    'motionFlashlightEnabled': bool(c.get('motion_flashlight_enabled', False)),
                    'motion_screen_enabled': bool(c.get('motion_screen_enabled', False)),
                    'motionScreenEnabled': bool(c.get('motion_screen_enabled', False)),
                    'motion_active': motion_recent,
                    'motionActive': motion_recent,
                    'visual_motion_active': motion_recent,
                    'last_motion_at': last_motion_at,
                    'last_motion_score': c.get('last_motion_score'),
                    'selected_camera': selected_camera,
                    'preview_aspect': lens_state.get('aspect_ratio', '16:9'),
                    'camera_auto_rotation': c.get('camera_auto_rotation'),
                    'camera_auto_rotation_at': c.get('camera_auto_rotation_at', 0),
                    'camera_auto_rotation_lens': c.get('camera_auto_rotation_lens', ''),
                    'preview_requested': preview_requested_for_client(c),
                    'latest_frame_url': f"/video_feed/{c['deviceID']}?t={c.get('frame_seq', 0)}" if c.get('frame') else None
                })
            if is_door:
                base.update({
                    'door_status': c.get('door_status', 'unknown'),
                    'calibrating': int(c.get('calibrating', 0) or 0),
                    'openness_score': c.get('openness_score', 0.0),
                    'doorbell_muted': bool(c.get('doorbell_muted', False))
                })
            if is_key:
                last_key_state_at = c.get('last_key_state_at', 0) or c.get('last_seen', 0)

                base['zone_name'] = ''
                base['zoneName'] = ''

                base.update({
                    'key_status': 'Offline' if stale else 'Online',
                    'heartbeat_interval_ms': int(c.get('heartbeat_interval_ms', 30000) or 30000),
                    'last_key_state': age_text(last_key_state_at)
                })
            if is_tapo:
                tapo_children = snapshot_tapo_children(c)

                base.update({
                    'tapo_model': c.get('tapo_model', ''),
                    'tapo_device_type': c.get('tapo_device_type', ''),
                    'tapo_alias': c.get('tapo_alias', ''),
                    'tapo_is_on': c.get('tapo_is_on'),
                    'tapo_brightness': c.get('tapo_brightness'),
                    'tapo_dimmable': bool(c.get('tapo_dimmable')),

                    'tapo_kind': c.get('tapo_kind', 'unknown'),
                    'tapo_dashboard_section': c.get('tapo_dashboard_section', 'control'),

                    'source': c.get('source') or 'tapo',
                    'manufacturer': c.get('manufacturer') or 'Tapo',
                    'brand': c.get('brand') or 'Tapo',

                    'tapo_is_bulb': bool(c.get('tapo_is_bulb')),
                    'tapo_is_plug': bool(c.get('tapo_is_plug')),
                    'tapo_is_outlet_extender': bool(c.get('tapo_is_outlet_extender')),
                    'tapo_is_hub': bool(c.get('tapo_is_hub')),
                    'tapo_is_hub_child': bool(c.get('tapo_is_hub_child')),
                    'tapo_is_camera': bool(c.get('tapo_is_camera')),
                    'tapo_is_button': bool(c.get('tapo_is_button')),
                    'tapo_is_switch': bool(c.get('tapo_is_switch')),

                    'tapo_control_ready': c.get('tapo_control_ready'),
                    'tapo_control_error': c.get('tapo_control_error', ''),
                    'control_ready': c.get('tapo_control_ready'),
                    'control_error': c.get('tapo_control_error', ''),

                    'tapo_room_power': bool(c.get('tapo_room_power')),
                    'tapoRoomPower': bool(c.get('tapo_room_power')),
                    'tapo_hide_dashboard': bool(c.get('tapo_hide_dashboard')),
                    'tapoHideDashboard': bool(c.get('tapo_hide_dashboard')),

                    'tapo_supports_power': bool(c.get('tapo_supports_power')),
                    'tapo_supports_brightness': bool(c.get('tapo_supports_brightness')),
                    'tapo_supports_color_temp': bool(c.get('tapo_supports_color_temp')),
                    'tapo_supports_color': bool(c.get('tapo_supports_color')),
                    'tapo_supports_rtsp': bool(c.get('tapo_supports_rtsp')),
                    'tapo_supports_onvif': bool(c.get('tapo_supports_onvif')),

                    'tapo_color_temperature': c.get('tapo_color_temperature', 4000),
                    'tapo_hue': c.get('tapo_hue', 45),
                    'tapo_saturation': c.get('tapo_saturation', 100),

                    'tapo_hls_url': (
                        c.get('tapo_hls_url')
                        or (
                            f"/api/tapo/camera-hls/{clean_filename_part(c.get('deviceID'))}/index.m3u8"
                            if c.get('tapo_kind') == 'camera'
                            else ''
                        )
                    ),
                    'tapo_recording': bool(c.get('tapo_recording')),
                    'tapo_recording_enabled': bool(c.get('tapo_recording_enabled')),
                    'tapo_onvif_port': c.get('tapo_onvif_port', 2020),

                    'tapo_battery': c.get('tapo_battery'),
                    'tapo_battery_level': c.get('tapo_battery_level'),
                    'tapo_battery_percent': c.get('tapo_battery_percent'),
                    'tapo_battery_low': c.get('tapo_battery_low'),
                    'tapo_battery_state': c.get('tapo_battery_state'),

                    'tapo_child_id': c.get('tapo_child_id', ''),
                    'tapo_child_name': c.get('tapo_child_name', ''),
                    'tapo_child_kind': c.get('tapo_child_kind', ''),
                    'tapo_child_model': c.get('tapo_child_model', ''),
                    'tapo_child_category': c.get('tapo_child_category', ''),
                    'tapo_child_avatar': c.get('tapo_child_avatar', ''),
                    'tapo_child_type': c.get('tapo_child_type', ''),
                    'tapo_child_status': c.get('tapo_child_status', ''),
                    'tapo_child_rssi': c.get('tapo_child_rssi'),
                    'tapo_child_signal_level': c.get('tapo_child_signal_level'),
                    'tapo_parent_device_id': c.get('tapo_parent_device_id', ''),
                    'tapo_parent_model': c.get('tapo_parent_model', ''),
                    'tapo_parent_alias': c.get('tapo_parent_alias', ''),

                    'tapo_children': tapo_children,
                    'children': tapo_children
                })
        return base

    def client_status_sort_key(c):
        return (
            str(c.get('deviceID') or ''),
            0 if client_has_role(c, CLIENT_ROLE_UNP) else 1,
            -float(c.get('last_seen', 0) or 0)
        )

    def current_status_payload():
        clients = []
        seen_keys = set()
        used_zones = set()

        for c in sorted(CLIENTS.values(), key=client_status_sort_key):
            if c.get('provisioned') and not client_has_role(c, CLIENT_ROLE_KEY):
                room = clean_zone_name(c.get('zone_name'))

                if room:
                    used_zones.add(room)

            snap = snapshot_client(c)
            key = snap.get('deviceID')

            if key not in seen_keys:
                seen_keys.add(key)
                clients.append(snap)

        uptime_seconds = max(0, int(now_epoch() - SERVER_START_EPOCH))

        uptime_text = duration_text(uptime_seconds)
        environment_snapshot = get_environment_snapshot()
        environment = environment_snapshot(clients) if callable(environment_snapshot) else {}

        system_armed = get_system_armed()
        arm_state = get_system_arm_state()

        return {
            'server_time': now_local(),
            'uptime_seconds': uptime_seconds,
            'server_uptime_seconds': uptime_seconds,
            'uptime_text': uptime_text,
            'server_uptime_text': uptime_text,
            'server': {
                'armed': system_armed,
                'arm_state': arm_state,
                'armState': arm_state,
                'uptime_seconds': uptime_seconds,
                'server_uptime_seconds': uptime_seconds,
                'uptime_text': uptime_text,
                'server_uptime_text': uptime_text,
            },
            'clients': clients,
            'environment': environment,
            'matter_settings': get_matter_settings_snapshot(),
            'used_zones': sorted(used_zones, key=lambda name: name.lower())
        }

    def build_dashboard_bootstrap():
        generated_at = now_epoch()
        auth_status = dashboard_auth_status_payload()
        authenticated = bool(auth_status.get('dashboard_authenticated'))
        bootstrap = {
            'ok': auth_status.get('ok') is not False,
            'generated_at': generated_at,
            'generated_at_ms': int(generated_at * 1000),
            'dashboard_authenticated': authenticated,
            'auth': auth_status,
        }

        if authenticated and bootstrap['ok']:
            if state_lock is not None:
                # current_status_payload() calls snapshot_client(), which explicitly
                # expires preview viewers. Keep that side effect under the shared
                # state lock just like /api/status and /api/status/stream.
                with state_lock:
                    bootstrap['status'] = current_status_payload()
            else:
                bootstrap['status'] = current_status_payload()

            tapo_lighting_state = get_tapo_lighting_state_snapshot()

            if tapo_lighting_state is not None:
                bootstrap['tapo_lighting_state'] = tapo_lighting_state

        return bootstrap

    return {
        'preview_requested_for_client': preview_requested_for_client,
        'is_client_stale': _is_client_stale,
        'snapshot_client': snapshot_client,
        'client_status_sort_key': client_status_sort_key,
        'current_status_payload': current_status_payload,
        'build_dashboard_bootstrap': build_dashboard_bootstrap,
    }

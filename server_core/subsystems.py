"""Subsystem discovery, registration, and background startup wiring for KotiBot.

This module receives live server state and callbacks through ``ctx`` so it does
not import ``kotibot_server.py``.
"""

import importlib.util
import logging
import sys
import types
from pathlib import Path
from threading import Thread


LOGGER = logging.getLogger(__name__)


def load_subsystem_module(package_name, package_dir, module_name, filename):
    package_dir = Path(package_dir)
    module_path = package_dir / filename

    package = sys.modules.get(package_name)
    if package is None:
        package = types.ModuleType(package_name)
        package.__path__ = [str(package_dir)]
        sys.modules[package_name] = package

    spec = importlib.util.spec_from_file_location(
        f'{package_name}.{module_name}',
        module_path
    )

    if not spec or not spec.loader:
        raise ImportError(f'Unable to load subsystem module: {module_path}')

    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module

def build_subsystem_runtime(ctx):
    app = ctx['app']

    base_dir = ctx['base_dir']
    activity_state_file = Path(ctx['activity_state_file'])
    controller_apk_dir = Path(ctx['controller_apk_dir'])
    monitor_apk_dir = Path(ctx['monitor_apk_dir'])
    file_server_dir = ctx['file_server_dir']
    environment_dir = ctx['environment_dir']
    environment_state_file = Path(ctx['environment_state_file'])
    matter_controller_state_file = Path(
        ctx['matter_controller_state_file']
    )
    matter_dir = Path(ctx['matter_dir'])
    matter_controller_storage_dir = Path(
        ctx['matter_controller_storage_dir']
    )
    matter_subscription_storage_dir = Path(
        ctx['matter_subscription_storage_dir']
    )
    client_tapo_dir = ctx['client_tapo_dir']
    client_android_home_dir = ctx['client_android_home_dir']
    client_android_key_dir = ctx['client_android_key_dir']
    tapo_config_file = ctx['tapo_config_file']
    tapo_camera_hls_dir = Path(ctx['tapo_camera_hls_dir'])
    recording_dir = Path(ctx['recording_dir'])
    video_transcode_dir = Path(ctx['video_transcode_dir'])
    automation_state_file = ctx['automation_state_file']
    tapo_lighting_state_file = ctx['tapo_lighting_state_file']

    state_lock = ctx['state_lock']
    clients = ctx['clients']
    routes = ctx['routes']

    runtime = {
        'activity_log': None,
        'tapo_routes_loaded': False,
        'tapo_import_error': '',
        'play_wav_file': ctx['play_wav_file'],
        'schedule_door_sound_repeat': ctx['schedule_door_sound_repeat'],
        'cancel_door_sound_repeat': ctx['cancel_door_sound_repeat'],
        'cancel_motion_recording_stop': ctx['cancel_motion_recording_stop'],
        'external_ip_check_loop': ctx['external_ip_check_loop'],
        'fire_door_routes': ctx['fire_door_routes'],
        'fire_camera_motion_routes': ctx['fire_camera_motion_routes'],
        'fire_environment_routes': ctx['fire_environment_routes'],
        'sync_arming_motion_detection': ctx['sync_arming_motion_detection'],
    }

    def _runtime_call(name, *args, **kwargs):
        func = runtime.get(name)

        if not callable(func):
            return None

        return func(*args, **kwargs)

    def register_core_subsystems():
        from subsystems.security.security_routes import register_security_routes
        from subsystems.video.video_routes import register_video_routes
        from subsystems.automations.automations_routes import register_automation_routes
        from subsystems.automations.trigger_routes import register_trigger_routes
        from subsystems.activities.activity_log import KotiBotActivityLog
        from subsystems.activities.activity_routes import register_activity_routes
        from subsystems.voice.voice_routes import register_voice_routes
        from subsystems.notifications.notification_routes import register_notification_routes
        from subsystems.soundboard.soundboard_routes import register_soundboard_routes
        from subsystems.network.external_ip import register_external_ip_checker
        from subsystems.bluetooth.bluetooth_routes import register_bluetooth_routes
        from subsystems.matter.matter_routes import register_matter_routes

        activity_log = KotiBotActivityLog(
            activity_state_file,
            clients=clients,
        )
        runtime['activity_log'] = activity_log

        register_activity_routes(app, {
            'activity_log': activity_log,
            'age_text': ctx['age_text'],
        })

        app.config['KOTIBOT_ACTIVITY_LOG'] = activity_log

        file_server_routes = load_subsystem_module(
            'kotibot_file_server',
            file_server_dir,
            'file_server_routes',
            'file_server_routes.py'
        )

        file_server_routes.register_file_server_routes(app, {
            'controller_apk_dir': controller_apk_dir,
            'monitor_apk_dir': monitor_apk_dir,
        })

        environment_routes = load_subsystem_module(
            'kotibot_environment',
            environment_dir,
            'environment_routes',
            'environment_routes.py'
        )

        environment_runtime = environment_routes.register_environment_routes(app, {
            'state_file': environment_state_file,
            'matter_state_file': matter_controller_state_file,
            'state_lock': state_lock,
            'clients': clients,
            'now_epoch': ctx['now_epoch'],
            'broadcast_state': ctx['broadcast_state'],
        })

        app.config['KOTIBOT_ENVIRONMENT_SNAPSHOT'] = environment_runtime['snapshot']
        app.config['KOTIBOT_ENVIRONMENT_LOOP'] = environment_runtime['loop']

        register_security_routes(app, {
            'security': ctx['security'],
        })

        register_matter_routes(app, {
            'base_dir': base_dir,
            'matter_dir': matter_dir,
            'matter_controller_storage_dir': matter_controller_storage_dir,
            'matter_subscription_storage_dir': matter_subscription_storage_dir,
            'state_lock': state_lock,
            'clients': clients,
            'client_has_role': ctx['client_has_role'],
            'client_role_dss': ctx['client_role_dss'],
            'save_state': ctx['save_state'],
            'broadcast_state': ctx['broadcast_state'],
            'now_epoch': ctx['now_epoch'],
            'fire_door_routes': lambda door_client, output: _runtime_call('fire_door_routes', door_client, output),
            'fire_camera_motion_routes': lambda motion_client, output='motion': _runtime_call('fire_camera_motion_routes', motion_client, output),
            'fire_environment_routes': lambda sensor_client, kind, value, previous_value: _runtime_call('fire_environment_routes', sensor_client, kind, value, previous_value),
            'prune_invalid_routes_for_clients': ctx['prune_invalid_routes_for_clients'],
            'activity_log': activity_log,
            'matter_sync_stop': ctx['matter_sync_stop'],
        })

        tapo_admin_routes = load_subsystem_module(
            'kotibot_client_tapo',
            client_tapo_dir,
            'tapo_admin_routes',
            'tapo_admin_routes.py'
        )

        tapo_admin_routes.register_tapo_admin_routes(app, {
            'base_dir': base_dir,
            'tapo_config_file': tapo_config_file,
            'tapo_enabled': ctx['tapo_enabled'],
            'tapo_routes_loaded': lambda: runtime['tapo_routes_loaded'],
            'tapo_import_error': lambda: runtime['tapo_import_error'],
            'state_lock': state_lock,
            'clients': clients,
            'get_routes': lambda: routes,
            'set_routes': ctx['set_routes'],
            'client_role_tapo': ctx['client_role_tapo'],
            'client_has_role': ctx['client_has_role'],
            'save_state': ctx['save_state'],
        })

        soundboard_runtime = register_soundboard_routes(app, {
            'base_dir': base_dir,
            'state_lock': state_lock,
            'clients': clients,
            'door_sound_repeat_allowed': ctx['door_sound_repeat_allowed'],
        })

        runtime['play_wav_file'] = soundboard_runtime['play_wav_file']
        runtime['schedule_door_sound_repeat'] = soundboard_runtime['schedule_door_sound_repeat']
        runtime['cancel_door_sound_repeat'] = soundboard_runtime['cancel_door_sound_repeat']

        trigger_runtime = register_trigger_routes(app, {
            'state_lock': state_lock,
            'clients': clients,
            'get_routes': lambda: routes,
            'set_routes': ctx['set_routes'],
            'client_role_cam': ctx['client_role_cam'],
            'client_role_key': ctx['client_role_key'],
            'client_has_role': ctx['client_has_role'],
            'get_clients_for_device': ctx['get_clients_for_device'],
            'play_wav_file': runtime['play_wav_file'],
            'schedule_door_sound_repeat': runtime['schedule_door_sound_repeat'],
            'cancel_door_sound_repeat': runtime['cancel_door_sound_repeat'],
            'save_state': ctx['save_state'],
            'broadcast_state': ctx['broadcast_state'],
            'push_queue': ctx['push_queue'],
            'system_arm_state': ctx['system_arm_state'],
            'now_epoch': ctx['now_epoch'],
            'now_local': ctx['now_local'],
            'activity_log': activity_log,
        })

        runtime['fire_door_routes'] = trigger_runtime['fire_door_routes']
        runtime['fire_camera_motion_routes'] = trigger_runtime['fire_camera_motion_routes']
        runtime['fire_environment_routes'] = trigger_runtime['fire_environment_routes']
        runtime['sync_device_automation_target_power'] = trigger_runtime['sync_device_automation_target_power']
        runtime['sync_arming_motion_detection'] = trigger_runtime['sync_arming_motion_detection']

        runtime['external_ip_check_loop'] = register_external_ip_checker(app)

        register_bluetooth_routes(app, {
            'safe_int': ctx['safe_int'],
            'request_json': ctx['request_json'],
            'json_dumps': ctx['json_dumps'],
        })

        register_voice_routes(app, {
            'state_lock': state_lock,
            'clients': clients,
            'client_role_cam': ctx['client_role_cam'],
            'client_role_key': ctx['client_role_key'],
            'client_role_tapo': ctx['client_role_tapo'],
            'client_has_role': ctx['client_has_role'],
            'is_client_stale': ctx['is_client_stale'],
            'now_epoch': ctx['now_epoch'],
            'push_queue': ctx['push_queue'],
        })

        register_notification_routes(app, {
            'state_lock': state_lock,
            'clients': clients,
            'push_queue': ctx['push_queue'],
            'now_epoch': ctx['now_epoch'],
            'save_state': ctx['save_state'],
        })

        register_video_routes(app, {
            'recording_dir': recording_dir,
            'video_transcode_dir': video_transcode_dir,
            'state_lock': state_lock,
            'clients': clients,
            'client_role_cam': ctx['client_role_cam'],
            'client_has_role': ctx['client_has_role'],
            'save_state': ctx['save_state'],
            'broadcast_state': ctx['broadcast_state'],
            'clean_zone_name': ctx['clean_zone_name'],
            'safe_int': ctx['safe_int'],
            'now_epoch': ctx['now_epoch'],
        })

        register_automation_routes(app, {
            'state_lock': state_lock,
            'clients': clients,
            'client_role_cam': ctx['client_role_cam'],
            'client_role_dss': ctx['client_role_dss'],
            'client_role_key': ctx['client_role_key'],
            'client_role_tapo': ctx['client_role_tapo'],
            'client_has_role': ctx['client_has_role'],
            'snapshot_client': ctx['snapshot_client'],
            'save_state': ctx['save_state'],
            'broadcast_state': ctx['broadcast_state'],
            'clean_zone_name': ctx['clean_zone_name'],
            'safe_int': ctx['safe_int'],
            'now_epoch': ctx['now_epoch'],
            'activity_log': activity_log,
            'automation_state_file': automation_state_file,
            'tapo_lighting_state_file': tapo_lighting_state_file,
        })

        android_home_routes = load_subsystem_module(
            'kotibot_client_android_home',
            client_android_home_dir,
            'client_android_home_routes',
            'client_android_home_routes.py'
        )

        android_key_routes = load_subsystem_module(
            'kotibot_client_android_key',
            client_android_key_dir,
            'client_android_key_routes',
            'client_android_key_routes.py'
        )

        android_home_telemetry = load_subsystem_module(
            'kotibot_client_android_home',
            client_android_home_dir,
            'client_android_home_telemetry',
            'client_android_home_telemetry.py'
        )

        android_key_telemetry = load_subsystem_module(
            'kotibot_client_android_key',
            client_android_key_dir,
            'client_android_key_telemetry',
            'client_android_key_telemetry.py'
        )

        key_telemetry_runtime = android_key_telemetry.register_android_key_telemetry({
            'safe_int': ctx['safe_int'],
            'now_epoch': ctx['now_epoch'],
        })

        home_telemetry_runtime = android_home_telemetry.register_android_home_telemetry(app, {
            'state_lock': state_lock,
            'clients': clients,
            'client_role_cam': ctx['client_role_cam'],
            'client_role_dss': ctx['client_role_dss'],
            'client_role_key': ctx['client_role_key'],
            'client_role_tapo': ctx['client_role_tapo'],
            'client_has_role': ctx['client_has_role'],
            'normalize_client_roles': ctx['normalize_client_roles'],
            'get_unprovisioned_client': ctx['get_unprovisioned_client'],
            'get_clients_for_device': ctx['get_clients_for_device'],
            'register_seen_client': ctx['register_seen_client'],
            'snapshot_client': ctx['snapshot_client'],
            'preview_requested_for_client': ctx['preview_requested_for_client'],
            'handle_key_telemetry': key_telemetry_runtime['handle_key_telemetry'],
            'fire_door_routes': lambda door_client, output: _runtime_call('fire_door_routes', door_client, output),
            'fire_camera_motion_routes': lambda camera_client, output='motion': _runtime_call('fire_camera_motion_routes', camera_client, output),
            'activity_log': activity_log,
            'cancel_door_sound_repeat': lambda deviceID: _runtime_call('cancel_door_sound_repeat', deviceID),
            'push_queue': ctx['push_queue'],
            'system_armed': ctx['system_armed'],
            'save_state': ctx['save_state'],
            'broadcast_state': ctx['broadcast_state'],
            'safe_int': ctx['safe_int'],
            'safe_float': ctx['safe_float'],
            'now_epoch': ctx['now_epoch'],
            'now_local': ctx['now_local'],
        })

        runtime['cancel_motion_recording_stop'] = home_telemetry_runtime['cancel_motion_recording_stop']

        android_home_routes.register_android_home_routes(app, {
            'state_lock': state_lock,
            'clients': clients,
            'routes': routes,
            'client_role_cam': ctx['client_role_cam'],
            'client_role_dss': ctx['client_role_dss'],
            'client_role_key': ctx['client_role_key'],
            'client_has_role': ctx['client_has_role'],
            'get_clients_for_device': ctx['get_clients_for_device'],
            'normalize_client_roles': ctx['normalize_client_roles'],
            'apply_enabled_roles': ctx['apply_enabled_roles'],
            'cancel_motion_recording_stop': runtime['cancel_motion_recording_stop'],
            'save_state': ctx['save_state'],
            'broadcast_state': ctx['broadcast_state'],
            'clean_zone_name': ctx['clean_zone_name'],
            'safe_int': ctx['safe_int'],
            'safe_float': ctx['safe_float'],
            'now_epoch': ctx['now_epoch'],
            'queue_door_recalibration': ctx['queue_door_recalibration'],
            'cancel_door_sound_repeat': lambda deviceID: _runtime_call('cancel_door_sound_repeat', deviceID),
            'system_armed': ctx['system_armed'],
            'preview_requested_for_client': ctx['preview_requested_for_client'],
            'push_queue': ctx['push_queue'],
        })

        android_key_routes.register_android_key_routes(app, {
            'state_lock': state_lock,
            'clients': clients,
            'client_role_key': ctx['client_role_key'],
            'client_has_role': ctx['client_has_role'],
            'safe_int': ctx['safe_int'],
            'push_queue': ctx['push_queue'],
        })

        return runtime

    def register_enabled_subsystems():
        if not ctx['tapo_enabled']():
            runtime['tapo_routes_loaded'] = False
            runtime['tapo_import_error'] = ''
            return runtime

        try:
            tapo_routes = load_subsystem_module(
                'kotibot_client_tapo',
                client_tapo_dir,
                'tapo_routes',
                'tapo_routes.py'
            )
            register_tapo_routes = tapo_routes.register_tapo_routes

            register_tapo_routes(app, {
                'state_lock': state_lock,
                'clients': clients,
                'client_role_tapo': ctx['client_role_tapo'],
                'client_has_role': ctx['client_has_role'],
                'init_client': ctx['init_client'],
                'snapshot_client': ctx['snapshot_client'],
                'save_state': ctx['save_state'],
                'broadcast_state': ctx['broadcast_state'],
                'clean_zone_name': ctx['clean_zone_name'],
                'safe_int': ctx['safe_int'],
                'now_epoch': ctx['now_epoch'],
                'activity_log': runtime['activity_log'],
                'tapo_watcher_stop': ctx['tapo_watcher_stop'],
                'prune_routes_for_client_change': ctx['prune_routes_for_client_change'],
                'device_power_changed': lambda target_deviceID, target_id, is_on: _runtime_call(
                    'sync_device_automation_target_power',
                    target_deviceID,
                    target_id,
                    is_on
                ),
                'automation_state_file': automation_state_file,
                'tapo_lighting_state_file': tapo_lighting_state_file,
                'tapo_camera_hls_dir': tapo_camera_hls_dir,
                'recording_dir': recording_dir,
            })

            runtime['tapo_routes_loaded'] = True
            runtime['tapo_import_error'] = ''

        except Exception as e:
            runtime['tapo_import_error'] = str(e)
            runtime['tapo_routes_loaded'] = False
            LOGGER.exception('Tapo subsystem failed to load')

        return runtime

    def normalize_after_state_load():
        normalize_tapo_loaded_clients = app.config.get('KOTIBOT_TAPO_NORMALIZE_LOADED_CLIENTS')

        if callable(normalize_tapo_loaded_clients):
            normalize_tapo_loaded_clients()

    def start_registered_subsystem_loops():
        matter_sync_loop = app.config.get(
            'KOTIBOT_MATTER_SYNC_LOOP'
        )

        if callable(matter_sync_loop):
            Thread(
                target=matter_sync_loop,
                daemon=True,
            ).start()

        matter_sensor_subscribe_loop = app.config.get(
            'KOTIBOT_MATTER_SENSOR_SUBSCRIBE_LOOP'
        )

        if callable(matter_sensor_subscribe_loop):
            Thread(
                target=matter_sensor_subscribe_loop,
                daemon=True,
            ).start()

        environment_loop = app.config.get(
            'KOTIBOT_ENVIRONMENT_LOOP'
        )

        if callable(environment_loop):
            Thread(
                target=environment_loop,
                daemon=True,
            ).start()

        if runtime['tapo_routes_loaded']:
            tapo_watcher_loop = app.config.get(
                'KOTIBOT_TAPO_STATE_WATCHER_LOOP'
            )

            if callable(tapo_watcher_loop):
                Thread(
                    target=tapo_watcher_loop,
                    daemon=True,
                ).start()

        automation_loop = app.config.get(
            'KOTIBOT_AUTOMATIONS_LOOP'
        )

        if callable(automation_loop):
            Thread(
                target=automation_loop,
                daemon=True,
            ).start()

    def start_external_ip_loop():
        external_ip_check_loop = runtime.get('external_ip_check_loop')

        if callable(external_ip_check_loop):
            Thread(target=external_ip_check_loop, daemon=True).start()

    return {
        'runtime': runtime,
        'register_core_subsystems': register_core_subsystems,
        'register_enabled_subsystems': register_enabled_subsystems,
        'normalize_after_state_load': normalize_after_state_load,
        'start_registered_subsystem_loops': start_registered_subsystem_loops,
        'start_external_ip_loop': start_external_ip_loop,
    }

from base64 import b64encode
from pathlib import Path
import socket
import json
import os
import signal
import time
from datetime import datetime, timezone
from threading import Lock, Thread, Event
from queue import Empty, Full

BASE_DIR = Path(__file__).resolve().parent
SUBSYSTEMS_DIR = BASE_DIR / 'subsystems'
AUTOMATIONS_DIR = SUBSYSTEMS_DIR / 'automations'
ACTIVITIES_DIR = SUBSYSTEMS_DIR / 'activities'
CLIENT_TAPO_DIR = SUBSYSTEMS_DIR / 'client-tapo'
CLIENT_ANDROID_HOME_DIR = SUBSYSTEMS_DIR / 'client-android-home'
CLIENT_ANDROID_KEY_DIR = SUBSYSTEMS_DIR / 'client-android-key'
NOTIFICATIONS_DIR = SUBSYSTEMS_DIR / 'notifications'
SECURITY_DIR = SUBSYSTEMS_DIR / 'security'
BLUETOOTH_DIR = SUBSYSTEMS_DIR / 'bluetooth'
MATTER_DIR = SUBSYSTEMS_DIR / 'matter'
ENVIRONMENT_DIR = SUBSYSTEMS_DIR / 'environment'
FILE_SERVER_DIR = SUBSYSTEMS_DIR / 'file-server'
DASHBOARD_ICON_DIR = BASE_DIR / 'static' / 'img' / 'dashboard-icons'
DASHBOARD_ICON_CSS_FILE = DASHBOARD_ICON_DIR / 'kotibot-icons.css'
DASHBOARD_THEME_CSS_FILES = {
    'dark': BASE_DIR / 'static' / 'css' / 'theme-dark.css',
    'light': BASE_DIR / 'static' / 'css' / 'theme-light.css',
}
DASHBOARD_STRIPE_IMAGE_FILES = {
    'dark': BASE_DIR / 'static' / 'img' / 'bg_stripe_dark.png',
    'light': BASE_DIR / 'static' / 'img' / 'bg_stripe_light.png',
}

from flask import Flask, Response, request, jsonify, g

from server_core.clients import CLIENT_ROLE_CAM, CLIENT_ROLE_DSS, CLIENT_ROLE_KEY, CLIENT_ROLE_TAPO, CLIENT_ROLE_UNP, build_client_runtime
from server_core.io import flush_json_writes, stop_json_writer
from server_core.routes import register_server_routes
from server_core.security_actions import build_security_action_runtime
from server_core.state import build_state_runtime
from server_core.status import build_status_runtime
from server_core.subsystems import build_subsystem_runtime

from subsystems.security.kotibot_security import make_security
from subsystems.notifications.kotibot_push import KotiBotPushQueue

def dashboard_asset_data_uri(path, content_type):
    encoded_data = b64encode(path.read_bytes()).decode('ascii')
    return f'data:{content_type};base64,{encoded_data}'

def load_dashboard_icon_stylesheet():
    stylesheet = DASHBOARD_ICON_CSS_FILE.read_text(encoding='utf-8')

    for svg_path in sorted(DASHBOARD_ICON_DIR.glob('*.svg')):
        stylesheet = stylesheet.replace(
            f'url("./{svg_path.name}")',
            f'url("{dashboard_asset_data_uri(svg_path, "image/svg+xml")}")'
        )

    kotibot_logo_path = DASHBOARD_ICON_DIR.parent / 'KotiBot.svg'
    stylesheet = stylesheet.replace(
        'url("../KotiBot.svg")',
        f'url("{dashboard_asset_data_uri(kotibot_logo_path, "image/svg+xml")}")'
    )

    return stylesheet

def load_dashboard_theme_stylesheets():
    stylesheets = {}

    for theme, stylesheet_path in DASHBOARD_THEME_CSS_FILES.items():
        stripe_path = DASHBOARD_STRIPE_IMAGE_FILES[theme]
        stylesheet = stylesheet_path.read_text(encoding='utf-8')
        stylesheet = stylesheet.replace(
            f'url("/static/img/{stripe_path.name}")',
            f'url("{dashboard_asset_data_uri(stripe_path, "image/png")}")'
        )
        stylesheets[theme] = stylesheet

    return stylesheets

TAPO_CONFIG_FILE = CLIENT_TAPO_DIR / 'tapo_config.json'
TAPO_LIGHTING_STATE_FILE = CLIENT_TAPO_DIR / 'tapo_lighting_state.json'

def tapo_config_enabled():
    if str(os.environ.get('KOTIBOT_TAPO_ENABLED', '')).strip().lower() in ('1', 'true', 'yes', 'on'):
        return True

    try:
        data = json.loads(TAPO_CONFIG_FILE.read_text(encoding='utf-8'))
        return bool(data.get('enabled'))
    except Exception:
        return False

TAPO_ENABLED = tapo_config_enabled()
TAPO_IMPORT_ERROR = ''
TAPO_ROUTES_LOADED = False

STATE_FILE = BASE_DIR / 'server_state.json'
SECURITY_ACTIONS_FILE = AUTOMATIONS_DIR / 'security_actions.json'
TAPO_DEVICE_STATE_FILE = CLIENT_TAPO_DIR / 'tapo_device_state.json'
MATTER_DEVICE_STATE_FILE = MATTER_DIR / 'matter_device_state.json'
ANDROID_HOME_STATE_FILE = CLIENT_ANDROID_HOME_DIR / 'android_home_state.json'
AUTOMATION_STATE_FILE = AUTOMATIONS_DIR / 'automations_state.json'
FIREBASE_SERVICE_ACCOUNT_FILE = NOTIFICATIONS_DIR / 'firebase-service-account.json'
SECURITY_STATE_FILE = SECURITY_DIR / 'security_state.json'
AUTOMATION_TYPE_TAPO_RECHARGE = 'tapo_recharge_android_battery'
AUTOMATION_TYPE_DEVICE_ROUTES = 'device_automations'

STATE_LOCK = Lock()
CLIENTS = {}
ROUTES = []
ACTIVITY_LOG = None

SYSTEM_ARMED = False
SYSTEM_ARM_STATE = 'day'
SERVER_START_EPOCH = datetime.now(timezone.utc).timestamp()
DEV_STATIC_NO_CACHE = str(
    os.environ.get('KOTIBOT_DEV_STATIC_NO_CACHE', '1')
).strip().lower() in ('1', 'true', 'yes', 'on')

OPEN_ANGLE_THRESHOLD = 15.0
CLOSE_ANGLE_THRESHOLD = 10.0
CALIBRATION_REQUIRED_SAMPLES = 40
SMOOTHING_WINDOW = 24
DOOR_RECALIBRATION_COMMAND_TIMEOUT_SECONDS = 18.0
DOOR_RECALIBRATION_ACTIVE_TIMEOUT_SECONDS = 12.0

STALE_CLIENT_SECONDS = 65.0
MATTER_STALE_CLIENT_SECONDS = 375.0
HEARTBEAT_CHECK_INTERVAL_SECONDS = 30
HEARTBEAT_CHECK_STOP = Event()
PREVIEW_VIEWER_TTL_SECONDS = max(10.0, float(os.environ.get('KOTIBOT_PREVIEW_VIEWER_TTL_SECONDS', '30') or 30))

TAPO_WATCHER_STOP = Event()
MATTER_SYNC_STOP = Event()

def play_wav_file(filename):
    return None

def _schedule_door_sound_repeat(client, filename):
    return None

def _cancel_door_sound_repeat(deviceID):
    return None

def external_ip_check_loop():
    return None

def _cancel_motion_recording_stop(deviceID):
    return None

def fire_door_routes(door_client, output):
    return False

def fire_camera_motion_routes(camera_client, output='motion'):
    return False

def fire_environment_routes(sensor_client, kind, value, previous_value):
    return False

def sync_arming_motion_detection():
    return False

# SSE Broadcasting
SSE_LISTENERS = []

app = Flask(__name__, static_folder='static', template_folder='templates')

@app.get('/static/img/dashboard-icons/kotibot-icons.css')
def dashboard_icon_stylesheet():
    return Response(
        load_dashboard_icon_stylesheet(),
        content_type='text/css; charset=utf-8'
    )

@app.get('/static/css/theme-<theme>.css')
def dashboard_theme_stylesheet(theme):
    stylesheet = load_dashboard_theme_stylesheets().get(theme)

    if stylesheet is None:
        return Response(status=404)

    return Response(
        stylesheet,
        content_type='text/css; charset=utf-8'
    )

def _kotibot_should_time_request():
    return (
        request.path == '/' or
        request.path.startswith('/api/') or
        request.path.startswith('/static/') or
        (request.path.startswith('/subsystems/') and '/static/' in request.path)
    )

@app.before_request
def _kotibot_request_timer_start():
    if _kotibot_should_time_request():
        g.kotibot_request_started_at = time.perf_counter()

@app.after_request
def _kotibot_request_timer_finish(response):
    started_at = getattr(g, 'kotibot_request_started_at', None)

    if started_at is not None:
        elapsed_ms = (time.perf_counter() - started_at) * 1000.0
        elapsed_text = f'{elapsed_ms:.1f}'
        response.headers['X-KotiBot-Route-Ms'] = elapsed_text
        response.headers['Server-Timing'] = f'kotibot;dur={elapsed_text}'

    static_asset_request = (
        request.path.startswith('/static/') or
        (request.path.startswith('/subsystems/') and '/static/' in request.path)
    )
    development_asset_request = (
        static_asset_request and
        request.path.lower().endswith(('.js', '.mjs', '.css'))
    )

    if request.path == '/':
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
    elif DEV_STATIC_NO_CACHE and development_asset_request:
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
    elif static_asset_request and request.args.get('v'):
        response.headers['Cache-Control'] = 'public, max-age=31536000, immutable'

    return response

SECURITY = make_security(SECURITY_DIR)
SECURITY.init_app(app)

PUSH_QUEUE = KotiBotPushQueue(NOTIFICATIONS_DIR)

def now_local(): return datetime.now().strftime('%Y-%m-%d %H:%M:%S')
def now_epoch(): return datetime.now(timezone.utc).timestamp()

def age_text(epoch_value):
    try:
        epoch = float(epoch_value or 0)
    except:
        epoch = 0

    if epoch <= 0:
        return '—'

    seconds = max(0, int(now_epoch() - epoch))

    if seconds < 2:
        return 'now'
    if seconds < 60:
        return f'{seconds}s ago'
    if seconds < 3600:
        return f'{seconds // 60}m ago'
    if seconds < 86400:
        return f'{seconds // 3600}h ago'

    return f'{seconds // 86400}d ago'

def duration_text(seconds_value):
    try:
        seconds = max(0, int(float(seconds_value or 0)))
    except Exception:
        seconds = 0

    days = seconds // 86400
    hours = (seconds % 86400) // 3600
    minutes = (seconds % 3600) // 60

    if days > 0:
        return f'{days}d {hours}h'
    if hours > 0:
        return f'{hours}h {minutes}m'

    return f'{max(1, minutes)}m'

def current_server_ip():
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(('8.8.8.8', 80))
            ip = s.getsockname()[0]

            if ip and not ip.startswith('127.'):
                return ip
    except Exception:
        pass

    try:
        ip = socket.gethostbyname(socket.gethostname())

        if ip and not ip.startswith('127.'):
            return ip
    except Exception:
        pass

    return '—'

def safe_float(v):
    try: return float(v)
    except: return None

def safe_int(v):
    try: return int(v)
    except: return None

def safe_bool(v, fallback=False):
    if isinstance(v, bool):
        return v

    if isinstance(v, (int, float)):
        return v != 0

    if isinstance(v, str):
        value = v.strip().lower()
        if value in ('1', 'true', 'yes', 'on', 'moving'):
            return True
        if value in ('0', 'false', 'no', 'off', 'placed', ''):
            return False

    return fallback

def clean_filename_part(value):
    safe = ''.join(ch for ch in str(value or '') if ch.isalnum() or ch in ('-', '_', '.'))
    return safe.strip('._')[:80] or 'unknown'

def clean_zone_name(value):
    return " ".join(str(value or "").replace("\r", " ").replace("\n", " ").split())[:40]

def cancel_automation_route_runtime(route):
    cancel_route = app.config.get(
        'KOTIBOT_CANCEL_AUTOMATION_ROUTE_RUNTIME'
    )

    if callable(cancel_route):
        return cancel_route(route)

    return None

_SECURITY_ACTION_RUNTIME = build_security_action_runtime({
    'clients': CLIENTS,
    'routes': ROUTES,
    'client_has_role': lambda client, role: client_has_role(client, role),
    'client_role_cam': CLIENT_ROLE_CAM,
    'client_role_dss': CLIENT_ROLE_DSS,
    'client_role_key': CLIENT_ROLE_KEY,
    'client_role_tapo': CLIENT_ROLE_TAPO,
    'cancel_door_sound_repeat': lambda deviceID: _cancel_door_sound_repeat(deviceID),
    'cancel_route_runtime': cancel_automation_route_runtime,
    'system_arm_state': lambda: SYSTEM_ARM_STATE,
})

clean_arm_state = _SECURITY_ACTION_RUNTIME['clean_arm_state']
set_routes = _SECURITY_ACTION_RUNTIME['set_routes']
prune_routes_for_client_change = _SECURITY_ACTION_RUNTIME['prune_routes_for_client_change']
prune_invalid_routes_for_clients = _SECURITY_ACTION_RUNTIME['prune_invalid_routes_for_clients']
door_sound_repeat_allowed = _SECURITY_ACTION_RUNTIME['door_sound_repeat_allowed']

def set_system_arm_state(armed, arm_state):
    global SYSTEM_ARMED, SYSTEM_ARM_STATE

    SYSTEM_ARMED = bool(armed)
    SYSTEM_ARM_STATE = clean_arm_state(arm_state)
    return SYSTEM_ARMED, SYSTEM_ARM_STATE

_CLIENT_RUNTIME = build_client_runtime({
    'clients': CLIENTS,
    'request_json': lambda: request.get_json(silent=True) or {},
    'request_ip': lambda: request.headers.get('X-Forwarded-For', request.remote_addr or ''),
    'now_epoch': now_epoch,
    'client_role_cam': CLIENT_ROLE_CAM,
    'client_role_dss': CLIENT_ROLE_DSS,
    'client_role_key': CLIENT_ROLE_KEY,
    'client_role_tapo': CLIENT_ROLE_TAPO,
    'client_role_unp': CLIENT_ROLE_UNP,
    'door_recalibration_command_timeout_seconds': DOOR_RECALIBRATION_COMMAND_TIMEOUT_SECONDS,
    'cancel_door_sound_repeat': lambda deviceID: _cancel_door_sound_repeat(deviceID),
    'prune_routes_for_client_change': prune_routes_for_client_change,
    'clean_zone_name': clean_zone_name,
    'system_armed': lambda: SYSTEM_ARMED,
    'android_home_apply_seen_client': lambda: app.config.get('KOTIBOT_ANDROID_HOME_APPLY_SEEN_CLIENT'),
})

client_has_role = _CLIENT_RUNTIME['client_has_role']
normalize_client_roles = _CLIENT_RUNTIME['normalize_client_roles']
apply_enabled_roles = _CLIENT_RUNTIME['apply_enabled_roles']
init_client = _CLIENT_RUNTIME['init_client']
get_unprovisioned_client = _CLIENT_RUNTIME['get_unprovisioned_client']
get_clients_for_device = _CLIENT_RUNTIME['get_clients_for_device']
door_recalibration_command_keys = _CLIENT_RUNTIME['door_recalibration_command_keys']
queue_door_recalibration = _CLIENT_RUNTIME['queue_door_recalibration']
register_seen_client = _CLIENT_RUNTIME['register_seen_client']
used_room_names = _CLIENT_RUNTIME['used_room_names']

@app.route('/', methods=['POST'])
@app.route('/handshake', methods=['POST'])
@app.route('/api/handshake', methods=['POST'])
@app.route('/client-handshake', methods=['POST'])
def handshake():
    data = request.get_json(silent=True) or {}
    deviceID = data.get('deviceID') or request.headers.get('X-Device-ID')

    if not deviceID: return jsonify({'error': 'Missing deviceID'}), 400

    with STATE_LOCK:
        existing = CLIENTS.get(deviceID)

        if existing and existing.get('provisioned'):
            register_seen_client(existing, data, request.path)
            res = snapshot_client(existing)
            res['ok'] = True
            res['serverPort'] = 5000

            issued = SECURITY.issue_device_key(deviceID, rotate=True)
            res['kotiKeyID'] = issued.get('keyID', '')
            res['kotiKeySecret'] = issued.get('secret', '')
            res['armed'] = 1 if SYSTEM_ARMED else 0
            res['systemArmed'] = 1 if SYSTEM_ARMED else 0

            pending = dict(existing.get('pending_command', {}))
            if pending:
                request_roles = normalize_client_roles(data.get('clientRole') or request.headers.get('X-Client-Role') or '')

                if CLIENT_ROLE_DSS not in request_roles:
                    for key in door_recalibration_command_keys():
                        pending.pop(key, None)

                if pending:
                    res.update(pending)

                    for key in pending:
                        existing.get('pending_command', {}).pop(key, None)

                    save_state()

            return jsonify(res)

        c = get_unprovisioned_client(deviceID)
        register_seen_client(c, data, request.path)

        requested_name = clean_zone_name(data.get('clientName', ''))
        requested_roles = normalize_client_roles(
            data.get('clientRole') or request.headers.get('X-Client-Role') or ''
        )

        can_self_provision = (
            requested_name and
            requested_roles and
            CLIENT_ROLE_UNP not in requested_roles
        )

        c['hasDSSHW'] = data.get('hasDSSHW', c.get('hasDSSHW'))

        if can_self_provision:
            c['clientName'] = requested_name
            c['clientRole'] = requested_roles
            c['provisioned'] = True

            if CLIENT_ROLE_KEY in requested_roles:
                c['zone_name'] = c.get('zone_name', '')
            else:
                c['zone_name'] = clean_zone_name(data.get('zoneName', data.get('zone_name', c.get('zone_name', ''))))

            issued = SECURITY.issue_device_key(deviceID, rotate=True)

            save_state()

            res = snapshot_client(c)
            res['ok'] = True
            res['serverPort'] = 5000
            res['kotiKeyID'] = issued.get('keyID', '')
            res['kotiKeySecret'] = issued.get('secret', '')
            res['armed'] = 1 if SYSTEM_ARMED else 0
            res['systemArmed'] = 1 if SYSTEM_ARMED else 0

            return jsonify(res)

        c['clientRole'] = CLIENT_ROLE_UNP
        c['provisioned'] = False

        save_state()

        res = snapshot_client(c)
        res['clientRole'] = CLIENT_ROLE_UNP
        res['hasDSSHW'] = c.get('hasDSSHW')
        res['ok'] = True
        res['serverPort'] = 5000
        res['armed'] = 1 if SYSTEM_ARMED else 0
        res['systemArmed'] = 1 if SYSTEM_ARMED else 0
        return jsonify(res)

@app.route('/provision', methods=['POST'])
@app.route('/api/provision-client', methods=['POST'])
def provision():
    d = request.get_json() or {}
    deviceID = d.get('deviceID')
    if not deviceID: return jsonify({'error': 'Missing deviceID'}), 400

    with STATE_LOCK:
        c = get_unprovisioned_client(deviceID)
        c['clientName'] = clean_zone_name(d.get('clientName', c['clientName']))

        roles = normalize_client_roles(d.get('clientRole'))
        if not roles:
            return jsonify({'error': 'Invalid clientRole'}), 400

        zone_name = clean_zone_name(d.get('zoneName', d.get('zone_name', '')))

        if CLIENT_ROLE_KEY not in roles and not zone_name:
            return jsonify({'error': 'Choose a room / zone / area for this client'}), 400

        c['clientRole'] = roles
        c['zone_name'] = '' if CLIENT_ROLE_KEY in roles else zone_name
        c['provisioned'] = True

        pending = c.setdefault('pending_command', {})

        if CLIENT_ROLE_CAM in roles:
            c['motion_detection_enabled'] = False
            pending['motionDetectionEnabled'] = 0
            pending['motion_detection_enabled'] = 0

        # The next handshake issues fresh credentials directly in its response.
        # Credentials must never be placed in pending_command or persisted state.
        save_state()

    return jsonify({'ok': True})

@app.route('/api/remove-client', methods=['POST'])
def remove_client():
    d = request.get_json(silent=True) or {}
    deviceID = d.get('deviceID')

    if not deviceID:
        return jsonify({'ok': False, 'error': 'Missing deviceID'}), 400

    with STATE_LOCK:
        if deviceID not in CLIENTS:
            return jsonify({'ok': False, 'error': 'Client not found'}), 404

        remove_recharge_automations = app.config.get(
            'KOTIBOT_REMOVE_RECHARGE_AUTOMATIONS_FOR_DEVICE'
        )
        removed_automations = 0

        if callable(remove_recharge_automations):
            removed_automations = remove_recharge_automations(
                deviceID
            )

        CLIENTS.pop(deviceID, None)
        prune_routes_for_client_change(deviceID, remove_all=True)

        save_state()

    return jsonify({
        'ok': True,
        'removedAutomations': removed_automations,
    })

def voice_talk_active_for_target(deviceID):
    active_for_target = app.config.get('KOTIBOT_VOICE_TALK_ACTIVE_FOR_TARGET')

    if not callable(active_for_target):
        return False

    return bool(active_for_target(deviceID))

def broadcast_state():
    """Notifies all SSE listeners that the state has changed."""
    listeners = list(SSE_LISTENERS)

    if not listeners:
        return

    payload = json.dumps(current_status_payload())

    for q in listeners:
        try:
            q.put_nowait(payload)
        except Full:
            try:
                q.get_nowait()
            except Empty:
                pass

            try:
                q.put_nowait(payload)
            except Full:
                pass

_STATE_RUNTIME = build_state_runtime({
    'clients': CLIENTS,
    'routes': ROUTES,
    'state_file': STATE_FILE,
    'security_actions_file': SECURITY_ACTIONS_FILE,
    'tapo_device_state_file': TAPO_DEVICE_STATE_FILE,
    'matter_device_state_file': MATTER_DEVICE_STATE_FILE,
    'android_home_state_file': ANDROID_HOME_STATE_FILE,
    'automation_state_file': AUTOMATION_STATE_FILE,
    'automation_type_tapo_recharge': AUTOMATION_TYPE_TAPO_RECHARGE,
    'automation_type_device_routes': AUTOMATION_TYPE_DEVICE_ROUTES,
    'client_role_cam': CLIENT_ROLE_CAM,
    'client_role_dss': CLIENT_ROLE_DSS,
    'client_role_key': CLIENT_ROLE_KEY,
    'client_role_tapo': CLIENT_ROLE_TAPO,
    'open_angle_threshold': OPEN_ANGLE_THRESHOLD,
    'close_angle_threshold': CLOSE_ANGLE_THRESHOLD,
    'broadcast_state': broadcast_state,
    'clean_arm_state': clean_arm_state,
    'clean_zone_name': clean_zone_name,
    'client_has_role': client_has_role,
    'init_client': init_client,
    'prune_invalid_routes_for_clients': prune_invalid_routes_for_clients,
    'set_routes': set_routes,
    'set_system_arm_state': set_system_arm_state,
    'system_armed': lambda: SYSTEM_ARMED,
    'system_arm_state': lambda: SYSTEM_ARM_STATE,
})

save_state = _STATE_RUNTIME['save_state']
load_state = _STATE_RUNTIME['load_state']

def _dashboard_security_status_payload():
    try:
        status_rule = next(
            (
                rule for rule in app.url_map.iter_rules()
                if rule.rule == '/api/security/status' and 'GET' in rule.methods
            ),
            None
        )

        if status_rule is not None:
            view = app.view_functions.get(status_rule.endpoint)

            if callable(view):
                result = app.ensure_sync(view)()
                response = result[0] if isinstance(result, tuple) else result

                if isinstance(response, dict):
                    payload = dict(response)
                    payload.setdefault('ok', True)
                    payload['dashboard_authenticated'] = bool(payload.get('dashboard_authenticated'))
                    return payload

                if hasattr(response, 'get_json'):
                    payload = response.get_json(silent=True) or {}

                    if isinstance(payload, dict):
                        payload.setdefault('ok', True)
                        payload['dashboard_authenticated'] = bool(payload.get('dashboard_authenticated'))
                        return payload

        for attr in (
            'dashboard_status',
            'dashboard_session_status',
            'get_dashboard_status',
        ):
            status_fn = getattr(SECURITY, attr, None)

            if callable(status_fn):
                payload = status_fn()

                if isinstance(payload, dict):
                    payload = dict(payload)
                    payload.setdefault('ok', True)
                    payload['dashboard_authenticated'] = bool(payload.get('dashboard_authenticated'))
                    return payload

        for attr in (
            'dashboard_authenticated',
            'is_dashboard_authenticated',
            'is_dashboard_session_authenticated',
            'check_dashboard_session',
        ):
            auth_fn = getattr(SECURITY, attr, None)

            if callable(auth_fn):
                return {
                    'ok': True,
                    'dashboard_authenticated': bool(auth_fn()),
                }
    except Exception:
        app.logger.exception('Dashboard bootstrap authentication failed')

    return {'ok': False, 'dashboard_authenticated': False}

_STATUS_RUNTIME = build_status_runtime({
    'clients': CLIENTS,
    'state_lock': STATE_LOCK,
    'client_role_cam': CLIENT_ROLE_CAM,
    'client_role_dss': CLIENT_ROLE_DSS,
    'client_role_key': CLIENT_ROLE_KEY,
    'client_role_tapo': CLIENT_ROLE_TAPO,
    'client_role_unp': CLIENT_ROLE_UNP,
    'preview_viewer_ttl_seconds': PREVIEW_VIEWER_TTL_SECONDS,
    'stale_client_seconds': STALE_CLIENT_SECONDS,
    'matter_stale_client_seconds': MATTER_STALE_CLIENT_SECONDS,
    'server_start_epoch': SERVER_START_EPOCH,
    'age_text': age_text,
    'clean_filename_part': clean_filename_part,
    'clean_zone_name': clean_zone_name,
    'client_has_role': client_has_role,
    'current_server_ip': current_server_ip,
    'duration_text': duration_text,
    'now_epoch': now_epoch,
    'now_local': now_local,
    'voice_talk_active_for_target': voice_talk_active_for_target,
    'system_armed': lambda: SYSTEM_ARMED,
    'system_arm_state': lambda: SYSTEM_ARM_STATE,
    'environment_snapshot': lambda: app.config.get('KOTIBOT_ENVIRONMENT_SNAPSHOT'),
    'tapo_lighting_state_snapshot': lambda: (
        app.config['KOTIBOT_TAPO_LIGHTING_STATE_SNAPSHOT']()
        if callable(app.config.get('KOTIBOT_TAPO_LIGHTING_STATE_SNAPSHOT'))
        else None
    ),
    'matter_settings_snapshot': lambda: (
        app.config['KOTIBOT_MATTER_SETTINGS_SNAPSHOT']()
        if callable(app.config.get('KOTIBOT_MATTER_SETTINGS_SNAPSHOT'))
        else None
    ),
    'dashboard_auth_status': _dashboard_security_status_payload,
})

preview_requested_for_client = _STATUS_RUNTIME['preview_requested_for_client']
_is_client_stale = _STATUS_RUNTIME['is_client_stale']
snapshot_client = _STATUS_RUNTIME['snapshot_client']
client_status_sort_key = _STATUS_RUNTIME['client_status_sort_key']
current_status_payload = _STATUS_RUNTIME['current_status_payload']
build_dashboard_bootstrap = _STATUS_RUNTIME['build_dashboard_bootstrap']

register_server_routes(app, {
    'base_dir': BASE_DIR,
    'subsystems_dir': SUBSYSTEMS_DIR,
    'state_lock': STATE_LOCK,
    'sse_listeners': SSE_LISTENERS,
    'current_status_payload': current_status_payload,
    'build_dashboard_bootstrap': build_dashboard_bootstrap,
    'used_room_names': used_room_names,
    'clean_filename_part': clean_filename_part,
    'tapo_enabled': TAPO_ENABLED,
    'static_version': int(SERVER_START_EPOCH),
    'flush_json_writes': flush_json_writes,
    'clients': CLIENTS,
    'client_has_role': client_has_role,
    'client_role_dss': CLIENT_ROLE_DSS,
    'client_role_tapo': CLIENT_ROLE_TAPO,
    'clean_arm_state': clean_arm_state,
    'set_system_arm_state': set_system_arm_state,
    'cancel_door_sound_repeat': lambda deviceID: _cancel_door_sound_repeat(deviceID),
    'queue_door_recalibration': queue_door_recalibration,
    'save_state': save_state,
    'broadcast_state': broadcast_state,
    'sync_arming_motion_detection': lambda: sync_arming_motion_detection(),
})

def health_check_loop():
    while not HEARTBEAT_CHECK_STOP.wait(HEARTBEAT_CHECK_INTERVAL_SECONDS):
        changed = False
        with STATE_LOCK:
            for c in CLIENTS.values():
                if client_has_role(c, CLIENT_ROLE_TAPO):
                    continue

                if c.get('provisioned') and _is_client_stale(c) and not c.get('needs_heartbeat'):
                    c['needs_heartbeat'] = True; changed = True
        if changed: broadcast_state()

_SUBSYSTEM_RUNTIME = build_subsystem_runtime({
    'app': app,
    'base_dir': BASE_DIR,
    'activities_dir': ACTIVITIES_DIR,
    'file_server_dir': FILE_SERVER_DIR,
    'environment_dir': ENVIRONMENT_DIR,
    'matter_dir': MATTER_DIR,
    'client_tapo_dir': CLIENT_TAPO_DIR,
    'client_android_home_dir': CLIENT_ANDROID_HOME_DIR,
    'client_android_key_dir': CLIENT_ANDROID_KEY_DIR,
    'tapo_config_file': TAPO_CONFIG_FILE,
    'state_lock': STATE_LOCK,
    'clients': CLIENTS,
    'routes': ROUTES,
    'security': SECURITY,
    'push_queue': PUSH_QUEUE,
    'client_role_cam': CLIENT_ROLE_CAM,
    'client_role_dss': CLIENT_ROLE_DSS,
    'client_role_key': CLIENT_ROLE_KEY,
    'client_role_tapo': CLIENT_ROLE_TAPO,
    'tapo_enabled': lambda: TAPO_ENABLED,
    'tapo_watcher_stop': TAPO_WATCHER_STOP,
    'matter_sync_stop': MATTER_SYNC_STOP,
    'set_routes': set_routes,
    'client_has_role': client_has_role,
    'normalize_client_roles': normalize_client_roles,
    'apply_enabled_roles': apply_enabled_roles,
    'init_client': init_client,
    'get_unprovisioned_client': get_unprovisioned_client,
    'get_clients_for_device': get_clients_for_device,
    'register_seen_client': register_seen_client,
    'queue_door_recalibration': queue_door_recalibration,
    'prune_routes_for_client_change': prune_routes_for_client_change,
    'prune_invalid_routes_for_clients': prune_invalid_routes_for_clients,
    'snapshot_client': snapshot_client,
    'preview_requested_for_client': preview_requested_for_client,
    'is_client_stale': _is_client_stale,
    'door_sound_repeat_allowed': door_sound_repeat_allowed,
    'save_state': save_state,
    'broadcast_state': broadcast_state,
    'clean_zone_name': clean_zone_name,
    'safe_bool': safe_bool,
    'safe_float': safe_float,
    'safe_int': safe_int,
    'request_json': lambda: request.get_json(silent=True) or {},
    'json_dumps': lambda payload: json.dumps(payload),
    'now_epoch': now_epoch,
    'now_local': now_local,
    'system_armed': lambda: SYSTEM_ARMED,
    'system_arm_state': lambda: SYSTEM_ARM_STATE,
    'door_recalibration_command_timeout_seconds': DOOR_RECALIBRATION_COMMAND_TIMEOUT_SECONDS,
    'door_recalibration_active_timeout_seconds': DOOR_RECALIBRATION_ACTIVE_TIMEOUT_SECONDS,
    'play_wav_file': play_wav_file,
    'schedule_door_sound_repeat': _schedule_door_sound_repeat,
    'cancel_door_sound_repeat': _cancel_door_sound_repeat,
    'cancel_motion_recording_stop': _cancel_motion_recording_stop,
    'external_ip_check_loop': external_ip_check_loop,
    'fire_door_routes': fire_door_routes,
    'fire_camera_motion_routes': fire_camera_motion_routes,
    'fire_environment_routes': fire_environment_routes,
    'sync_arming_motion_detection': sync_arming_motion_detection,
    'age_text': age_text,
})

def apply_subsystem_runtime_updates():
    global play_wav_file, _schedule_door_sound_repeat, _cancel_door_sound_repeat, _cancel_motion_recording_stop, external_ip_check_loop, fire_door_routes, fire_camera_motion_routes, fire_environment_routes, sync_arming_motion_detection, ACTIVITY_LOG, TAPO_IMPORT_ERROR, TAPO_ROUTES_LOADED

    runtime = _SUBSYSTEM_RUNTIME['runtime']
    play_wav_file = runtime['play_wav_file']
    _schedule_door_sound_repeat = runtime['schedule_door_sound_repeat']
    _cancel_door_sound_repeat = runtime['cancel_door_sound_repeat']
    _cancel_motion_recording_stop = runtime['cancel_motion_recording_stop']
    external_ip_check_loop = runtime['external_ip_check_loop']
    fire_door_routes = runtime['fire_door_routes']
    fire_camera_motion_routes = runtime['fire_camera_motion_routes']
    fire_environment_routes = runtime['fire_environment_routes']
    sync_arming_motion_detection = runtime['sync_arming_motion_detection']
    ACTIVITY_LOG = runtime['activity_log']
    TAPO_IMPORT_ERROR = runtime['tapo_import_error']
    TAPO_ROUTES_LOADED = runtime['tapo_routes_loaded']

_SUBSYSTEM_RUNTIME['register_core_subsystems']()
apply_subsystem_runtime_updates()
_SUBSYSTEM_RUNTIME['register_enabled_subsystems']()
apply_subsystem_runtime_updates()
load_state()
_SUBSYSTEM_RUNTIME['normalize_after_state_load']()

# Remove persisted routes whose source or target no longer exists. This runs
# after all persistent clients have been restored and Tapo clients normalized.
with STATE_LOCK:
    if prune_invalid_routes_for_clients():
        save_state()

sync_arming_motion_detection()

_SUBSYSTEM_RUNTIME['start_registered_subsystem_loops']()
Thread(target=health_check_loop, daemon=True).start()
_SUBSYSTEM_RUNTIME['start_external_ip_loop']()

def _handle_exit_signal(signum, _frame):
    stop_json_writer()
    raise SystemExit(128 + signum)

for _exit_signal in (signal.SIGINT, signal.SIGTERM):
    try:
        signal.signal(_exit_signal, _handle_exit_signal)
    except ValueError:
        pass

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, threaded=True)
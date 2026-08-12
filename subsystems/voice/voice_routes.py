import json
import os
from threading import Lock
from uuid import uuid4

from flask import jsonify, request


VOICE_TALK_SESSIONS = {}
VOICE_TALK_LOCK = Lock()
VOICE_TALK_PENDING_TTL_SECONDS = float(os.environ.get('KOTIBOT_CAMERA_TALK_PENDING_TTL_SECONDS', '30') or 30)
VOICE_TALK_CONNECTED_TTL_SECONDS = float(os.environ.get('KOTIBOT_CAMERA_TALK_CONNECTED_TTL_SECONDS', '120') or 120)
VOICE_TALK_ENDED_TTL_SECONDS = float(os.environ.get('KOTIBOT_CAMERA_TALK_ENDED_TTL_SECONDS', '10') or 10)
VOICE_TALK_PENDING_IDLE_POLL_MS = int(os.environ.get('KOTIBOT_CAMERA_TALK_PENDING_IDLE_POLL_MS', '5000') or 5000)
VOICE_TALK_PENDING_ACTIVE_POLL_MS = int(os.environ.get('KOTIBOT_CAMERA_TALK_PENDING_ACTIVE_POLL_MS', '500') or 500)
VOICE_TALK_DEFAULT_STUN_URLS = (
    'stun:stun.l.google.com:19302',
    'stun:stun1.l.google.com:19302',
)

def _clean_sdp(value):
    if not isinstance(value, str):
        return ''

    sdp = value.strip()

    if not sdp or sdp.lower() == 'null':
        return ''

    sdp = (
        sdp
        .replace('\\r\\n', '\n')
        .replace('\\n', '\n')
        .replace('\r\n', '\n')
        .replace('\r', '\n')
    )

    lines = [line.rstrip() for line in sdp.split('\n') if line.strip()]

    if not lines:
        return ''

    return '\r\n'.join(lines) + '\r\n'


def _valid_sdp(sdp, expected_type):
    if not sdp or not sdp.startswith('v=0'):
        return False

    if '\r\nm=audio ' not in sdp and '\nm=audio ' not in sdp:
        return False

    if expected_type in ('offer', 'answer'):
        return True

    return False


def _normalize_description(description, expected_type):
    if not isinstance(description, dict):
        return None

    desc_type = str(description.get('type') or '').strip().lower()

    if desc_type != expected_type:
        return None

    sdp = _clean_sdp(description.get('sdp'))

    if not _valid_sdp(sdp, expected_type):
        return None

    return {
        'type': expected_type,
        'sdp': sdp,
    }


def register_voice_routes(app, context):
    state_lock = context['state_lock']
    clients = context['clients']
    client_role_cam = context['client_role_cam']
    client_role_key = context['client_role_key']
    client_role_tapo = context['client_role_tapo']
    client_has_role = context['client_has_role']
    is_client_stale = context['is_client_stale']
    now_epoch = context['now_epoch']
    push_queue = context.get('push_queue')
    integration_credentials = context['integration_credentials']

    voice_talk_cached_ice_servers = None

    def voice_talk_ice_servers():
        nonlocal voice_talk_cached_ice_servers

        if voice_talk_cached_ice_servers is not None:
            return voice_talk_cached_ice_servers

        protected_ice_servers = (
            integration_credentials.camera_talk_ice_servers()
        )

        if protected_ice_servers:
            voice_talk_cached_ice_servers = protected_ice_servers
            return voice_talk_cached_ice_servers

        servers = []
        raw_stun_urls = os.environ.get('KOTIBOT_CAMERA_TALK_STUN_URLS', '').strip()
        stun_urls = [
            item.strip()
            for item in raw_stun_urls.split(',')
            if item.strip()
        ]
        turn_urls = [
            item.strip()
            for item in os.environ.get('KOTIBOT_CAMERA_TALK_TURN_URLS', '').split(',')
            if item.strip()
        ]

        if not stun_urls and os.environ.get('KOTIBOT_CAMERA_TALK_DISABLE_DEFAULT_STUN', '').strip().lower() not in ('1', 'true', 'yes', 'on'):
            stun_urls = list(VOICE_TALK_DEFAULT_STUN_URLS)

        if stun_urls:
            servers.append({'urls': stun_urls[0] if len(stun_urls) == 1 else stun_urls})

        if turn_urls:
            turn_server = {'urls': turn_urls[0] if len(turn_urls) == 1 else turn_urls}
            username = (
                integration_credentials.camera_talk_turn_username
            )
            credential = (
                integration_credentials.camera_talk_turn_credential
            )

            if username:
                turn_server['username'] = username

            if credential:
                turn_server['credential'] = credential

            servers.append(turn_server)

        voice_talk_cached_ice_servers = servers
        return voice_talk_cached_ice_servers

    def prune_voice_talk_sessions(now=None):
        now = now or now_epoch()

        for sessionID, session in list(VOICE_TALK_SESSIONS.items()):
            state = str(session.get('state') or '')
            updated_at = float(session.get('updated_at', session.get('created_at', 0)) or 0)
            created_at = float(session.get('created_at', updated_at) or updated_at)

            if state in ('ended', 'failed', 'expired'):
                if now - updated_at > VOICE_TALK_ENDED_TTL_SECONDS:
                    VOICE_TALK_SESSIONS.pop(sessionID, None)

                continue

            ttl = VOICE_TALK_CONNECTED_TTL_SECONDS if state in ('answered', 'connected') else VOICE_TALK_PENDING_TTL_SECONDS
            baseline = created_at if state in ('answered', 'connected') else updated_at

            if now - baseline > ttl:
                session['state'] = 'expired'
                session['error'] = 'voice_talk_timeout'
                session['updated_at'] = now

    def voice_talk_session_public(session, viewer):
        base = {
            'sessionID': session.get('id'),
            'targetDeviceID': session.get('targetDeviceID'),
            'sourceDeviceID': session.get('sourceDeviceID', ''),
            'state': session.get('state', 'requested'),
            'createdAt': session.get('created_at', 0),
            'updatedAt': session.get('updated_at', 0),
            'endedBy': session.get('ended_by', ''),
            'error': session.get('error', ''),
        }

        if viewer == 'dashboard':
            base.update({
                'offer': session.get('offer'),
                'answer': session.get('answer'),
                'dashboardCandidates': [item.get('candidate') for item in session.get('dashboard_candidates', []) if item.get('candidate')],
                'clientCandidates': [item.get('candidate') for item in session.get('client_candidates', []) if item.get('candidate')],
            })
        elif viewer == 'client':
            base.update({
                'offer': session.get('offer'),
                'dashboardCandidates': [item.get('candidate') for item in session.get('dashboard_candidates', []) if item.get('candidate')],
            })

        return base

    def voice_talk_active_for_target(deviceID):
        targetID = str(deviceID or '').strip()

        if not targetID:
            return False

        with VOICE_TALK_LOCK:
            prune_voice_talk_sessions()

            return any(
                str(session.get('targetDeviceID') or '') == targetID
                and session.get('state') not in ('ended', 'failed', 'expired')
                for session in VOICE_TALK_SESSIONS.values()
            )

    def voice_talk_find_android_camera(deviceID):
        targetID = str(deviceID or '').strip()

        if not targetID:
            return None, ('missing_target_deviceID', 400)

        c = clients.get(targetID)

        if not c:
            return None, ('camera_not_found', 404)

        if (
            not c.get('provisioned')
            or not client_has_role(c, client_role_cam)
            or client_has_role(c, client_role_tapo)
            or c.get('tapo_kind') == 'camera'
        ):
            return None, ('android_camera_required', 403)

        if is_client_stale(c):
            return None, ('camera_stale', 409)

        return c, None

    def voice_talk_validate_source_key(sourceDeviceID):
        sourceID = str(sourceDeviceID or '').strip()

        if not sourceID:
            return '', None

        c = clients.get(sourceID)

        if not c:
            return '', ('source_key_not_found', 404)

        if not c.get('provisioned') or not client_has_role(c, client_role_key):
            return '', ('source_key_required', 403)

        return sourceID, None

    def voice_talk_fcm_token_for_target(deviceID):
        targetID = str(deviceID or '').strip()

        if not targetID:
            return ''

        c = clients.get(targetID)
        return str((c or {}).get('fcm_token') or '').strip()

    def voice_talk_send_fcm(targetID, event_type, payload):
        if push_queue is None:
            return {'ok': False, 'skipped': True, 'reason': 'missing_push_queue'}

        token = voice_talk_fcm_token_for_target(targetID)

        if not token:
            return {'ok': False, 'skipped': True, 'reason': 'missing_fcm_token'}

        clean_event_type = str(event_type or '')
        persist_history = clean_event_type != 'camera_talk_candidate'

        data = {
            'type': clean_event_type,
            'action_type': clean_event_type.upper(),
            'targetDeviceID': str(targetID or ''),
            **{
                str(k): '' if v is None else str(v)
                for k, v in (payload or {}).items()
            },
        }

        item = push_queue.enqueue_data(
            event_type=clean_event_type,
            deviceID=targetID,
            fcm_token=token,
            data=data,
            persist_history=persist_history,
        )

        if not persist_history:
            return {
                'ok': True,
                'queued': True,
                'historyPersisted': False,
            }

        return {'ok': True, 'queued': item}

    def voice_talk_notify_request_ready(session):
        return voice_talk_send_fcm(
            session.get('targetDeviceID'),
            'camera_talk_request',
            {
                'sessionID': session.get('id', ''),
                'sourceDeviceID': session.get('sourceDeviceID', ''),
                'state': session.get('state', ''),
                'createdAt': str(session.get('created_at', 0)),
                'updatedAt': str(session.get('updated_at', 0)),
            },
        )

    def voice_talk_notify_dashboard_candidate(session, candidate):
        return voice_talk_send_fcm(
            session.get('targetDeviceID'),
            'camera_talk_candidate',
            {
                'sessionID': session.get('id', ''),
                'candidate': json.dumps(candidate, separators=(',', ':')),
            },
        )

    def voice_talk_notify_end(session, reason):
        return voice_talk_send_fcm(
            session.get('targetDeviceID'),
            'camera_talk_end',
            {
                'sessionID': session.get('id', ''),
                'reason': reason or '',
            },
        )

    def voice_talk_session_for_client(sessionID, deviceID):
        session = VOICE_TALK_SESSIONS.get(str(sessionID or '').strip())

        if not session:
            return None, ('session_not_found', 404)

        if str(session.get('targetDeviceID') or '') != str(deviceID or '').strip():
            return None, ('session_target_mismatch', 403)

        return session, None

    app.config['KOTIBOT_VOICE_TALK_ACTIVE_FOR_TARGET'] = voice_talk_active_for_target

    @app.post('/api/camera-talk/session')
    @app.post('/api/voice/session')
    def api_voice_talk_create_session():
        data = request.get_json(silent=True) or {}
        targetID = str(data.get('targetDeviceID') or data.get('deviceID') or '').strip()
        sourceID = str(data.get('sourceDeviceID') or request.headers.get('X-Device-ID') or '').strip()

        with state_lock:
            _, target_error = voice_talk_find_android_camera(targetID)

            if target_error:
                error, status = target_error
                return jsonify({'ok': False, 'error': error}), status

            sourceID, source_error = voice_talk_validate_source_key(sourceID)

            if source_error:
                error, status = source_error
                return jsonify({'ok': False, 'error': error}), status

        now = now_epoch()
        sessionID = uuid4().hex

        with VOICE_TALK_LOCK:
            prune_voice_talk_sessions(now)
            VOICE_TALK_SESSIONS[sessionID] = {
                'id': sessionID,
                'targetDeviceID': targetID,
                'sourceDeviceID': sourceID,
                'state': 'requested',
                'created_at': now,
                'updated_at': now,
                'offer': None,
                'answer': None,
                'dashboard_candidates': [],
                'client_candidates': [],
                'ended_by': '',
                'error': '',
            }

        return jsonify({
            'ok': True,
            'sessionID': sessionID,
            'targetDeviceID': targetID,
            'sourceDeviceID': sourceID,
            'state': 'requested',
            'iceServers': voice_talk_ice_servers(),
        })

    @app.get('/api/camera-talk/session/<sessionID>')
    @app.get('/api/voice/session/<sessionID>')
    def api_voice_talk_get_session(sessionID):
        with VOICE_TALK_LOCK:
            prune_voice_talk_sessions()
            session = VOICE_TALK_SESSIONS.get(str(sessionID or '').strip())

            if not session:
                return jsonify({'ok': False, 'error': 'session_not_found'}), 404

            return jsonify({
                'ok': True,
                'session': voice_talk_session_public(session, 'dashboard'),
            })

    @app.post('/api/camera-talk/session/<sessionID>/offer')
    @app.post('/api/voice/session/<sessionID>/offer')
    def api_voice_talk_offer(sessionID):
        data = request.get_json(silent=True) or {}
        offer = _normalize_description(data.get('offer'), 'offer')

        if not offer:
            return jsonify({'ok': False, 'error': 'invalid_offer_sdp'}), 400

        now = now_epoch()

        with VOICE_TALK_LOCK:
            prune_voice_talk_sessions(now)
            session = VOICE_TALK_SESSIONS.get(str(sessionID or '').strip())

            if not session:
                return jsonify({'ok': False, 'error': 'session_not_found'}), 404

            if session.get('state') in ('ended', 'failed', 'expired'):
                return jsonify({'ok': False, 'error': f"session_{session.get('state')}"}), 409

            session['offer'] = offer
            session['state'] = 'offered'
            session['updated_at'] = now
            session_public = voice_talk_session_public(session, 'dashboard')

        fcm_result = voice_talk_notify_request_ready(session)

        return jsonify({
            'ok': True,
            'session': session_public,
            'fcm': fcm_result,
        })

    @app.post('/api/camera-talk/session/<sessionID>/candidate')
    @app.post('/api/voice/session/<sessionID>/candidate')
    def api_voice_talk_dashboard_candidate(sessionID):
        data = request.get_json(silent=True) or {}
        candidate = data.get('candidate')

        if not isinstance(candidate, dict):
            return jsonify({'ok': False, 'error': 'invalid_candidate'}), 400

        now = now_epoch()

        with VOICE_TALK_LOCK:
            prune_voice_talk_sessions(now)
            session = VOICE_TALK_SESSIONS.get(str(sessionID or '').strip())

            if not session:
                return jsonify({'ok': False, 'error': 'session_not_found'}), 404

            if session.get('state') in ('ended', 'failed', 'expired'):
                return jsonify({'ok': False, 'error': f"session_{session.get('state')}"}), 409

            session.setdefault('dashboard_candidates', []).append({
                'candidate': candidate,
                'at': now,
            })
            session['updated_at'] = now
            fcm_session = dict(session)

        fcm_result = voice_talk_notify_dashboard_candidate(fcm_session, candidate)

        return jsonify({'ok': True, 'fcm': fcm_result})

    @app.post('/api/camera-talk/session/<sessionID>/end')
    @app.post('/api/voice/session/<sessionID>/end')
    def api_voice_talk_dashboard_end(sessionID):
        data = request.get_json(silent=True) or {}
        reason = str(data.get('reason') or '').strip()[:120]
        now = now_epoch()

        with VOICE_TALK_LOCK:
            session = VOICE_TALK_SESSIONS.get(str(sessionID or '').strip())

            if not session:
                return jsonify({'ok': True, 'ended': False})

            session['state'] = 'ended'
            session['ended_by'] = 'dashboard'
            session['error'] = reason
            session['updated_at'] = now
            fcm_session = dict(session)

        voice_talk_notify_end(fcm_session, reason)

        return jsonify({'ok': True, 'ended': True})

    @app.post('/api/camera-talk/client/session/<sessionID>/claim')
    @app.post('/api/voice/client/session/<sessionID>/claim')
    def api_voice_talk_client_claim(sessionID):
        data = request.get_json(silent=True) or {}
        deviceID = str(data.get('deviceID') or request.headers.get('X-Device-ID') or '').strip()

        if not deviceID:
            return jsonify({'ok': False, 'error': 'missing_deviceID'}), 400

        now = now_epoch()

        with state_lock:
            _, target_error = voice_talk_find_android_camera(deviceID)

            if target_error:
                error, status = target_error
                return jsonify({'ok': False, 'error': error}), status

        with VOICE_TALK_LOCK:
            prune_voice_talk_sessions(now)
            session, session_error = voice_talk_session_for_client(sessionID, deviceID)

            if session_error:
                error, status = session_error
                return jsonify({'ok': False, 'error': error}), status

            if session.get('state') in ('ended', 'failed', 'expired'):
                return jsonify({'ok': False, 'error': f"session_{session.get('state')}"}), 409

            if not session.get('offer'):
                return jsonify({'ok': False, 'error': 'offer_not_ready'}), 409

            session['client_claimed_at'] = now
            session['updated_at'] = now

            return jsonify({
                'ok': True,
                'session': voice_talk_session_public(session, 'client'),
                'iceServers': voice_talk_ice_servers(),
            })
        
    @app.post('/api/camera-talk/client/pending')
    @app.post('/api/voice/client/pending')
    def api_voice_talk_client_pending():
        data = request.get_json(silent=True) or {}
        deviceID = str(data.get('deviceID') or request.headers.get('X-Device-ID') or '').strip()

        if not deviceID:
            return jsonify({
                'ok': False,
                'error': 'missing_deviceID',
                'pollAfterMs': VOICE_TALK_PENDING_IDLE_POLL_MS,
            }), 400

        with state_lock:
            _, target_error = voice_talk_find_android_camera(deviceID)

            if target_error:
                error, status = target_error
                return jsonify({
                    'ok': False,
                    'error': error,
                    'pollAfterMs': VOICE_TALK_PENDING_IDLE_POLL_MS,
                }), status

        with VOICE_TALK_LOCK:
            prune_voice_talk_sessions()
            sessions = [
                voice_talk_session_public(session, 'client')
                for session in VOICE_TALK_SESSIONS.values()
                if str(session.get('targetDeviceID') or '') == deviceID
                and session.get('state') not in ('requested', 'ended', 'failed', 'expired')
                and session.get('offer')
            ]

        poll_after_ms = VOICE_TALK_PENDING_ACTIVE_POLL_MS if sessions else VOICE_TALK_PENDING_IDLE_POLL_MS

        return jsonify({
            'ok': True,
            'sessions': sessions,
            'iceServers': voice_talk_ice_servers() if sessions else [],
            'pollAfterMs': poll_after_ms,
        })

    @app.post('/api/camera-talk/client/session/<sessionID>/answer')
    @app.post('/api/voice/client/session/<sessionID>/answer')
    def api_voice_talk_client_answer(sessionID):
        data = request.get_json(silent=True) or {}
        deviceID = str(data.get('deviceID') or request.headers.get('X-Device-ID') or '').strip()
        answer = _normalize_description(data.get('answer'), 'answer')

        if not deviceID:
            return jsonify({'ok': False, 'error': 'missing_deviceID'}), 400

        if not answer:
            return jsonify({'ok': False, 'error': 'invalid_answer_sdp'}), 400

        now = now_epoch()

        with VOICE_TALK_LOCK:
            prune_voice_talk_sessions(now)
            session, session_error = voice_talk_session_for_client(sessionID, deviceID)

            if session_error:
                error, status = session_error
                return jsonify({'ok': False, 'error': error}), status

            if session.get('state') in ('ended', 'failed', 'expired'):
                return jsonify({'ok': False, 'error': f"session_{session.get('state')}"}), 409

            session['answer'] = answer
            session['state'] = 'answered'
            session['updated_at'] = now

            return jsonify({'ok': True})

    @app.post('/api/camera-talk/client/session/<sessionID>/candidate')
    @app.post('/api/voice/client/session/<sessionID>/candidate')
    def api_voice_talk_client_candidate(sessionID):
        data = request.get_json(silent=True) or {}
        deviceID = str(data.get('deviceID') or request.headers.get('X-Device-ID') or '').strip()
        candidate = data.get('candidate')

        if not deviceID:
            return jsonify({'ok': False, 'error': 'missing_deviceID'}), 400

        if not isinstance(candidate, dict):
            return jsonify({'ok': False, 'error': 'invalid_candidate'}), 400

        now = now_epoch()

        with VOICE_TALK_LOCK:
            prune_voice_talk_sessions(now)
            session, session_error = voice_talk_session_for_client(sessionID, deviceID)

            if session_error:
                error, status = session_error
                return jsonify({'ok': False, 'error': error}), status

            if session.get('state') in ('ended', 'failed', 'expired'):
                return jsonify({'ok': False, 'error': f"session_{session.get('state')}"}), 409

            session.setdefault('client_candidates', []).append({
                'candidate': candidate,
                'at': now,
            })
            session['updated_at'] = now

            return jsonify({'ok': True})

    @app.post('/api/camera-talk/client/session/<sessionID>/state')
    @app.post('/api/voice/client/session/<sessionID>/state')
    def api_voice_talk_client_state(sessionID):
        data = request.get_json(silent=True) or {}
        deviceID = str(data.get('deviceID') or request.headers.get('X-Device-ID') or '').strip()
        state = str(data.get('state') or '').strip().lower()
        error = str(data.get('error') or '').strip()[:180]

        if not deviceID:
            return jsonify({'ok': False, 'error': 'missing_deviceID'}), 400

        if state not in ('connected', 'failed', 'ended'):
            return jsonify({'ok': False, 'error': 'invalid_state'}), 400

        now = now_epoch()

        with VOICE_TALK_LOCK:
            session, session_error = voice_talk_session_for_client(sessionID, deviceID)

            if session_error:
                error_code, status = session_error
                return jsonify({'ok': False, 'error': error_code}), status

            session['state'] = state
            session['updated_at'] = now

            if error:
                session['error'] = error

            if state == 'ended':
                session['ended_by'] = 'client'

        return jsonify({'ok': True})

    @app.post('/api/camera-talk/client/session/<sessionID>/end')
    @app.post('/api/voice/client/session/<sessionID>/end')
    def api_voice_talk_client_end(sessionID):
        data = request.get_json(silent=True) or {}
        deviceID = str(data.get('deviceID') or request.headers.get('X-Device-ID') or '').strip()
        reason = str(data.get('reason') or '').strip()[:180]

        if not deviceID:
            return jsonify({'ok': False, 'error': 'missing_deviceID'}), 400

        now = now_epoch()

        with VOICE_TALK_LOCK:
            session, session_error = voice_talk_session_for_client(sessionID, deviceID)

            if session_error:
                error, status = session_error
                return jsonify({'ok': False, 'error': error}), status

            session['state'] = 'ended'
            session['ended_by'] = 'client'
            session['error'] = reason
            session['updated_at'] = now

        return jsonify({'ok': True})

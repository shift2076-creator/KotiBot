import json
import os
import subprocess
import sys
from queue import Queue, Empty
from threading import Timer

from flask import Response, jsonify, render_template, request, send_from_directory


def register_server_routes(app, ctx):
    state_lock = ctx['state_lock']
    sse_listeners = ctx['sse_listeners']

    @app.get('/client-rooms')
    def client_rooms():
        with state_lock:
            return jsonify({
                'ok': True,
                'rooms': ctx['used_room_names']()
            })

    @app.get('/subsystems/<subsystem_name>/static/<path:filename>')
    def subsystem_static(subsystem_name, filename):
        root = ctx['subsystems_dir'] / ctx['clean_filename_part'](subsystem_name) / 'static'
        return send_from_directory(root, filename)

    @app.route('/api/status/stream')
    def status_stream():
        def stream():
            q = Queue(maxsize=1)
            sse_listeners.append(q)

            try:
                with state_lock:
                    initial_payload = json.dumps(ctx['current_status_payload']())

                yield f"data: {initial_payload}\n\n"

                while True:
                    try:
                        data = q.get(timeout=15)
                        yield f"data: {data}\n\n"
                    except Empty:
                        yield "event: heartbeat\ndata: {}\n\n"

            finally:
                if q in sse_listeners:
                    sse_listeners.remove(q)

        response = Response(stream(), mimetype="text/event-stream")
        response.headers["Cache-Control"] = "no-cache, no-transform"
        response.headers["X-Accel-Buffering"] = "no"
        return response

    @app.route('/api/status')
    def status():
        with state_lock:
            response = jsonify(ctx['current_status_payload']())

        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response

    @app.route('/api/recalibrate', methods=['POST'])
    def api_recalibrate():
        d = request.get_json(silent=True) or {}
        deviceID = str(d.get('deviceID') or '').strip()

        if not deviceID:
            return jsonify({'ok': False, 'error': 'Missing deviceID'}), 400

        with state_lock:
            c = ctx['clients'].get(deviceID)

            if not c or not ctx['client_has_role'](c, ctx['client_role_dss']):
                return jsonify({'ok': False, 'error': 'Door sensor not found'}), 404

            ctx['cancel_door_sound_repeat'](deviceID)
            recal_seq = ctx['queue_door_recalibration'](c)

            ctx['save_state']()

        return jsonify({'ok': True, 'recalibrateSeq': recal_seq})

    @app.route('/api/system-arm', methods=['POST'])
    def api_system_arm():
        d = request.get_json(silent=True) or {}
        requested_state = d.get('armState', d.get('arm_state', d.get('state', d.get('mode'))))

        if requested_state is None:
            armed = bool(int(d.get('armed', 0) or 0))
            arm_state = 'night' if armed else 'day'
        else:
            arm_state = ctx['clean_arm_state'](requested_state)
            armed = arm_state in ('night', 'away')

        with state_lock:
            ctx['set_system_arm_state'](armed, arm_state)

            for c in ctx['clients'].values():
                if not c.get('provisioned') or ctx['client_has_role'](c, ctx['client_role_tapo']):
                    continue

                c['armed'] = 1 if armed else 0
                c['arm_state'] = arm_state
                c['armState'] = arm_state
                pending = c.setdefault('pending_command', {})
                pending['armed'] = 1 if armed else 0
                pending['systemArmed'] = 1 if armed else 0
                pending['armState'] = arm_state
                pending['arm_state'] = arm_state

            ctx['sync_arming_motion_detection']()
            ctx['save_state']()
            status_payload = ctx['current_status_payload']()

        activity_log = app.config.get('KOTIBOT_ACTIVITY_LOG')

        if activity_log is not None and hasattr(activity_log, 'record_state_change'):
            try:
                activity_log.record_state_change(
                    deviceID='dashboard:security',
                    name='Security',
                    kind='system_arm',
                    state=arm_state,
                    status=f'{arm_state.title()} mode',
                    icon='security',
                    accent='purple',
                    source='dashboard',
                    category='users',
                    record_initial=True,
                )
            except Exception:
                app.logger.exception('Dashboard security activity recording failed')

        return jsonify(status_payload)

    @app.route('/')
    def dashboard():
        dashboard_bootstrap = {'ok': False, 'dashboard_authenticated': False}
        build_dashboard_bootstrap = ctx.get('build_dashboard_bootstrap')

        if callable(build_dashboard_bootstrap):
            try:
                dashboard_bootstrap = build_dashboard_bootstrap()
            except Exception:
                app.logger.exception('Dashboard bootstrap failed')

        return render_template(
            'index.html',
            tapo_enabled=ctx['tapo_enabled'],
            static_version=ctx['static_version'],
            dashboard_bootstrap=dashboard_bootstrap,
        )

    @app.route('/api/restart-server', methods=['POST'])
    def api_restart_server():
        def _restart():
            try:
                ctx['flush_json_writes']()

                if os.name == 'nt':
                    subprocess.Popen([sys.executable] + sys.argv, cwd=str(ctx['base_dir']))
                    os._exit(0)

                subprocess.Popen(
                    ['sudo', 'systemctl', 'restart', 'kotibot'],
                    cwd=str(ctx['base_dir']),
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )

            except Exception:
                app.logger.exception('Server restart failed')

        Timer(0.5, _restart).start()

        return jsonify({'ok': True, 'message': 'Restarting KotiBot service'})
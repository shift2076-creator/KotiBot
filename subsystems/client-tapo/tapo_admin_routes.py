import json
import os
import subprocess
import sys
from threading import Timer
from flask import jsonify
from server_core.io import flush_json_writes

def register_tapo_admin_routes(app, context):
    base_dir = context['base_dir']
    tapo_config_file = context['tapo_config_file']
    tapo_enabled = context['tapo_enabled']
    tapo_routes_loaded = context['tapo_routes_loaded']
    tapo_import_error = context['tapo_import_error']
    state_lock = context['state_lock']
    clients = context['clients']
    get_routes = context['get_routes']
    set_routes = context['set_routes']
    client_role_tapo = context['client_role_tapo']
    client_has_role = context['client_has_role']
    save_state = context['save_state']

    def _restart_service():
        flush_json_writes()

        if os.name == 'nt':
            subprocess.Popen([sys.executable] + sys.argv, cwd=str(base_dir))
            os._exit(0)

        subprocess.Popen(
            ['sudo', 'systemctl', 'restart', 'kotibot'],
            cwd=str(base_dir),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

    @app.route('/api/tapo/status')
    def tapo_status():
        return jsonify({
            'ok': True,
            'enabled': bool(tapo_enabled()),
            'loaded': bool(tapo_routes_loaded()),
            'error': tapo_import_error()
        })

    @app.route('/api/tapo/enable', methods=['POST'])
    def tapo_enable():
        tapo_config_file.parent.mkdir(parents=True, exist_ok=True)
        tapo_config_file.write_text(json.dumps({'enabled': True}, indent=2), encoding='utf-8')

        Timer(0.5, _restart_service).start()

        return jsonify({'ok': True, 'enabled': True, 'restarting': True})

    @app.route('/api/tapo/disable', methods=['POST'])
    def tapo_disable():
        tapo_config_file.parent.mkdir(parents=True, exist_ok=True)
        tapo_config_file.write_text(json.dumps({'enabled': False}, indent=2), encoding='utf-8')

        with state_lock:
            tapo_ids = {
                deviceID
                for deviceID, c in clients.items()
                if client_has_role(c, client_role_tapo) or c.get('detectedRole') == client_role_tapo
            }

            for deviceID in tapo_ids:
                clients.pop(deviceID, None)

            set_routes([
                r for r in get_routes()
                if r.get('from_deviceID') not in tapo_ids
                and r.get('to_deviceID') not in tapo_ids
            ])

            save_state()

        Timer(0.5, _restart_service).start()

        return jsonify({'ok': True, 'enabled': False, 'restarting': True})

    return {
        'tapo_status': tapo_status,
        'tapo_enable': tapo_enable,
        'tapo_disable': tapo_disable,
    }

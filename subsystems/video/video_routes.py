from pathlib import Path
from datetime import datetime
from flask import request, jsonify, send_file, abort
import json
import shutil
import subprocess

def register_video_routes(app, ctx):
    base_dir = Path(ctx['base_dir'])
    video_dir = base_dir / 'subsystems' / 'video' / 'videos'
    video_dir.mkdir(parents=True, exist_ok=True)

    state_lock = ctx['state_lock']
    clients = ctx['clients']
    save_state = ctx['save_state']
    broadcast_state = ctx['broadcast_state']
    clean_zone_name = ctx['clean_zone_name']
    safe_int = ctx['safe_int']
    now_epoch = ctx['now_epoch']
    client_role_cam = ctx['client_role_cam']

    def clean_video_label(value):
        raw = " ".join(str(value or "").replace("\r", " ").replace("\n", " ").split())
        safe = ''.join(ch for ch in raw if ch.isalnum() or ch in (' ', '-', '_', '.', '(', ')'))
        return " ".join(safe.split()).strip(' ._')[:80] or 'unknown'

    def video_extension(upload):
        filename = str(upload.filename or '').strip()
        suffix = Path(filename).suffix.lower()

        if suffix and len(suffix) <= 10:
            return suffix

        mimetype = str(upload.mimetype or '').lower()

        if 'webm' in mimetype:
            return '.webm'

        if 'quicktime' in mimetype or 'mov' in mimetype:
            return '.mov'

        if 'matroska' in mimetype or 'mkv' in mimetype:
            return '.mkv'

        return '.mp4'

    def available_video_path(folder, stem, suffix):
        candidate = folder / f"{stem}{suffix}"

        if not candidate.exists():
            return candidate

        index = 1

        while True:
            candidate = folder / f"{stem} {index:06d}{suffix}"

            if not candidate.exists():
                return candidate

            index += 1

    def probe_video_rotation(path):
        ffprobe = shutil.which('ffprobe')

        if not ffprobe:
            return None

        completed = subprocess.run(
            [
                ffprobe,
                '-v', 'error',
                '-select_streams', 'v:0',
                '-show_entries', 'stream_tags=rotate:stream_side_data=rotation',
                '-of', 'json',
                str(path),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=15,
        )

        if completed.returncode != 0:
            return None

        try:
            data = json.loads(completed.stdout or '{}')
        except Exception:
            return None

        streams = data.get('streams')

        if not isinstance(streams, list) or not streams:
            return None

        stream = streams[0]

        tags = stream.get('tags')
        if isinstance(tags, dict):
            rotation = safe_int(tags.get('rotate'))

            if rotation is not None:
                return rotation % 360

        side_data = stream.get('side_data_list')
        if isinstance(side_data, list):
            for item in side_data:
                if not isinstance(item, dict):
                    continue

                rotation = safe_int(item.get('rotation'))

                if rotation is not None:
                    return rotation % 360

        return None

    def clean_relative_video_path(value):
        raw = str(value or '').replace('\\', '/').strip().lstrip('/')
        parts = [part for part in raw.split('/') if part and part not in ('.', '..')]

        if not parts:
            return ''

        return '/'.join(parts)
    
    def normalize_video_rotation(path, applied_rotation, source_rotation=None):
        applied_rotation = safe_int(applied_rotation)

        if applied_rotation is None:
            applied_rotation = 0

        applied_rotation = applied_rotation % 360

        source_rotation = safe_int(source_rotation)

        if source_rotation is not None:
            source_rotation = source_rotation % 360

        should_transcode = bool(applied_rotation or source_rotation)

        if not should_transcode:
            return False

        ffmpeg = shutil.which('ffmpeg')

        if not ffmpeg:
            raise RuntimeError('ffmpeg not found')

        temp_path = path.with_name(f"{path.stem}.rotating{path.suffix}")

        cmd = [
            ffmpeg,
            '-hide_banner',
            '-loglevel', 'error',
            '-y',
            '-noautorotate',
            '-i', str(path),
        ]

        if applied_rotation == 90:
            video_filter = 'transpose=1'
        elif applied_rotation == 180:
            video_filter = 'hflip,vflip'
        elif applied_rotation == 270:
            video_filter = 'transpose=2'
        else:
            video_filter = ''

        if video_filter:
            cmd += ['-vf', video_filter]

        cmd += [
            '-metadata:s:v:0', 'rotate=0',
            '-c:v', 'libx264',
            '-preset', 'veryfast',
            '-crf', '23',
            '-c:a', 'copy',
            '-movflags', '+faststart',
            str(temp_path),
        ]

        completed = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=90,
        )

        if completed.returncode != 0:
            if temp_path.exists():
                temp_path.unlink()

            raise RuntimeError(completed.stdout.strip() or 'video rotation failed')

        temp_path.replace(path)
        return True
    
    @app.route('/api/video-file/<path:relative_path>', methods=['GET'])
    def video_file(relative_path):
        clean_path = clean_relative_video_path(relative_path)

        if not clean_path:
            abort(404)

        path = (video_dir / clean_path).resolve()
        root = video_dir.resolve()

        if root not in path.parents:
            abort(404)

        if not path.exists() or not path.is_file():
            abort(404)

        response = send_file(path, conditional=True)

        for header in (
            "Connection",
            "Keep-Alive",
            "Proxy-Authenticate",
            "Proxy-Authorization",
            "TE",
            "Trailer",
            "Transfer-Encoding",
            "Upgrade",
        ):
            response.headers.pop(header, None)

        return response
    
    @app.route('/upload_video', methods=['POST'])
    def upload_video():
        deviceID = (
            request.form.get('deviceID')
            or request.headers.get('X-Device-ID')
            or ''
        ).strip()

        clientRole = (
            request.form.get('clientRole')
            or request.headers.get('X-Client-Role')
            or client_role_cam
        ).strip()

        if not deviceID:
            return jsonify({'ok': False, 'error': 'missing_deviceID'}), 400

        file = request.files.get('video')
        if not file:
            return jsonify({'ok': False, 'error': 'missing_video'}), 400

        segmentIndex = safe_int(request.form.get('segmentIndex'))
        segmentStartMs = safe_int(request.form.get('segmentStartMs'))

        if segmentIndex is None:
            segmentIndex = 0

        now = datetime.now()
        day_label = now.strftime('%Y-%m-%d')
        date_label = now.strftime('%Y-%m-%d %H-%M-%S')
        recording_dir = video_dir / day_label
        recording_dir.mkdir(parents=True, exist_ok=True)

        with state_lock:
            c = clients.get(deviceID)
            selected_camera = str((c or {}).get('selected_camera') or 'back').strip().lower() or 'back'
            auto_video_rotation = None
            state_video_rotation = None
            state_video_rotation_source = ''

            zone_name = clean_zone_name(
                request.form.get('zoneName')
                or request.form.get('zone_name')
                or (c or {}).get('zone_name')
                or ''
            )
            client_name = clean_video_label(
                request.form.get('clientName')
                or request.form.get('client_name')
                or (c or {}).get('clientName')
                or deviceID
            )

        zone_part = clean_video_label(zone_name) if zone_name else 'Unknown Zone'
        stem = clean_video_label(f"{date_label} {zone_part} {client_name}")
        suffix = video_extension(file)
        path = available_video_path(recording_dir, stem, suffix)
        file.save(path)

        probed_video_rotation = probe_video_rotation(path)

        requested_video_correction = safe_int(
            request.form.get('videoCorrectionDegrees')
            or request.form.get('video_correction_degrees')
        )

        if requested_video_correction is not None:
            video_rotation = (-requested_video_correction) % 360
            video_rotation_source = 'client_correction'
            state_video_rotation = video_rotation
            state_video_rotation_source = 'client_correction'
        elif probed_video_rotation is not None:
            video_rotation = probed_video_rotation % 360
            video_rotation_source = 'ffprobe'
            state_video_rotation = video_rotation
            state_video_rotation_source = 'ffprobe'
        else:
            video_rotation = 0
            video_rotation_source = 'none'
            state_video_rotation = 0
            state_video_rotation_source = 'none'

        rotation_applied = False
        rotation_error = ''

        try:
            source_rotation = None if video_rotation_source == 'client_correction' else probed_video_rotation
            rotation_applied = normalize_video_rotation(path, video_rotation, source_rotation)
        except Exception as e:
            rotation_error = str(e)

        relative_path = str(path.relative_to(video_dir)).replace('\\', '/')

        with state_lock:
            c = clients.get(deviceID)

            if c:
                c['last_seen'] = now_epoch()
                c['last_video_at'] = now_epoch()
                c['last_video_file'] = path.name
                c['last_video_path'] = relative_path
                c['last_video_lens'] = selected_camera
                c['last_video_rotation'] = video_rotation
                c['last_video_rotation_source'] = video_rotation_source
                c['last_video_state_rotation'] = state_video_rotation
                c['last_video_state_rotation_source'] = state_video_rotation_source
                c['last_video_auto_rotation'] = auto_video_rotation
                c['last_video_client_correction'] = requested_video_correction
                c['last_video_probed_rotation'] = probed_video_rotation
                c['last_video_effective_rotation'] = video_rotation
                c['last_video_rotation_applied'] = rotation_applied
                c['last_video_rotation_error'] = rotation_error
                c['clientRole'] = c.get('clientRole') or clientRole
                save_state()

        broadcast_state()

        return jsonify({
            'ok': True,
            'deviceID': deviceID,
            'filename': path.name,
            'path': relative_path,
            'segmentIndex': segmentIndex,
            'segmentStartMs': segmentStartMs,
            'selectedCamera': selected_camera,
            'rotation': video_rotation,
            'rotationSource': video_rotation_source,
            'stateRotation': state_video_rotation,
            'stateRotationSource': state_video_rotation_source,
            'autoRotation': auto_video_rotation,
            'clientCorrection': requested_video_correction,
            'probedRotation': probed_video_rotation,
            'effectiveRotation': video_rotation,
            'rotationApplied': rotation_applied,
            'rotationError': rotation_error,
        })
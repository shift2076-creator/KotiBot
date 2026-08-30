from pathlib import Path
from datetime import datetime
from flask import g, request, jsonify, send_file, abort
import errno
import json
import os
import shutil
import subprocess
import tempfile

from server_core.private_paths import (
    PRIVATE_FILE_MODE,
    ensure_private_directory,
    ensure_private_file,
    verify_private_descriptor,
)

def register_video_routes(app, ctx):
    video_dir = Path(ctx['recording_dir'])
    video_transcode_dir = Path(ctx['video_transcode_dir'])

    state_lock = ctx['state_lock']
    clients = ctx['clients']
    save_state = ctx['save_state']
    broadcast_state = ctx['broadcast_state']
    clean_zone_name = ctx['clean_zone_name']
    safe_int = ctx['safe_int']
    now_epoch = ctx['now_epoch']
    client_role_cam = ctx['client_role_cam']
    client_has_role = ctx['client_has_role']

    def clean_video_label(value):
        raw = " ".join(str(value or "").replace("\r", " ").replace("\n", " ").split())
        safe = ''.join(ch for ch in raw if ch.isalnum() or ch in (' ', '-', '_', '.', '(', ')'))
        return " ".join(safe.split()).strip(' ._')[:80] or 'unknown'

    VIDEO_MIME_TYPES = {
        'video/mp4': '.mp4',
        'video/webm': '.webm',
        'video/quicktime': '.mov',
        'video/x-matroska': '.mkv',
        'application/octet-stream': '.mp4',
    }

    def video_extension(upload):
        """Return an extension only when the container signature is valid."""
        claimed_type = str(
            upload.mimetype or ''
        ).lower()

        header = upload.stream.read(64)
        upload.stream.seek(0)

        # ISO Base Media File Format: MP4 or QuickTime.
        if len(header) >= 12 and header[4:8] == b'ftyp':
            if header[8:12] == b'qt  ':
                return '.mov'

            return '.mp4'

        # Matroska and WebM share the EBML signature.
        if header.startswith(b'\x1a\x45\xdf\xa3'):
            if claimed_type == 'video/webm':
                return '.webm'

            if claimed_type == 'video/x-matroska':
                return '.mkv'

        return ''

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

    def replace_staged_video(staged_path, destination):
        staged_path = Path(staged_path)
        destination = Path(destination)
        ensure_private_directory(destination.parent)
        ensure_private_file(staged_path)

        try:
            staged_path.replace(destination)
            ensure_private_file(destination)
            return
        except OSError as exc:
            if exc.errno != errno.EXDEV:
                raise

        descriptor, local_name = tempfile.mkstemp(
            prefix=f'.{destination.stem}.',
            suffix=f'.staging{destination.suffix}',
            dir=destination.parent,
        )
        local_path = Path(local_name)

        try:
            with os.fdopen(descriptor, 'wb') as output:
                verify_private_descriptor(
                    output.fileno(),
                    directory=False,
                )

                with staged_path.open('rb') as source:
                    shutil.copyfileobj(
                        source,
                        output,
                        length=1024 * 1024,
                    )

                output.flush()
                os.fsync(output.fileno())

            ensure_private_file(local_path)
            local_path.replace(destination)
            ensure_private_file(destination)
        except Exception:
            local_path.unlink(missing_ok=True)
            raise
        finally:
            staged_path.unlink(missing_ok=True)

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

        ensure_private_directory(video_transcode_dir)

        descriptor, temp_name = tempfile.mkstemp(
            prefix=f'{path.stem}.',
            suffix=f'.rotating{path.suffix}',
            dir=video_transcode_dir,
        )
        os.close(descriptor)
        temp_path = Path(temp_name)
        ensure_private_file(temp_path)

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

        try:
            completed = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=90,
            )

            if completed.returncode != 0:
                raise RuntimeError(
                    completed.stdout.strip()
                    or 'video rotation failed'
                )

            ensure_private_file(temp_path)
            replace_staged_video(temp_path, path)
            return True
        finally:
            temp_path.unlink(missing_ok=True)

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
        deviceID = str(
            getattr(g, 'kotibot_device_id', '')
        ).strip()
        form_deviceID = str(
            request.form.get('deviceID') or ''
        ).strip()

        if form_deviceID and form_deviceID != deviceID:
            return jsonify({
                'ok': False,
                'error': 'device_identity_mismatch',
            }), 403

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

        with state_lock:
            c = clients.get(deviceID)

            if (
                not c
                or not c.get('provisioned')
                or not client_has_role(c, client_role_cam)
            ):
                return jsonify({
                    'ok': False,
                    'error': 'camera_role_required',
                }), 403

            selected_camera = str(
                c.get('selected_camera') or 'back'
            ).strip().lower() or 'back'
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

        if not suffix:
            return jsonify({
                'ok': False,
                'error': 'unsupported_video_container',
            }), 415

        ensure_private_directory(recording_dir)

        # Reserve a unique destination atomically so concurrent uploads
        # cannot overwrite one another.
        while True:
            path = available_video_path(
                recording_dir,
                stem,
                suffix,
            )

            try:
                fd = os.open(
                    path,
                    (
                        os.O_WRONLY
                        | os.O_CREAT
                        | os.O_EXCL
                        | getattr(os, 'O_CLOEXEC', 0)
                    ),
                    PRIVATE_FILE_MODE,
                )
                break
            except FileExistsError:
                continue

        try:
            with os.fdopen(fd, 'wb') as destination:
                verify_private_descriptor(
                    destination.fileno(),
                    directory=False,
                )
                shutil.copyfileobj(
                    file.stream,
                    destination,
                    length=1024 * 1024,
                )

            ensure_private_file(path)
        except Exception:
            path.unlink(missing_ok=True)
            raise

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
                c['clientRole'] = c.get('clientRole') or client_role_cam
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
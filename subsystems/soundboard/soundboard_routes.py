from pathlib import Path
import os
import subprocess
from threading import Thread, Timer
from shutil import which

from flask import jsonify, request


WAV_CATEGORY_VOLUME = {
    'alarms': 1.0,
    'alarm': 1.0,
    'buzzers': 0.5,
    'buzzer': 0.5,
    'bells': 0.25,
    'bell': 0.25,
}

DOOR_SOUND_REPEAT_SECONDS = 10.0

_DOOR_SOUND_REPEAT_TIMERS = {}

def _coerce_wav_volume(value, default):
    if value in (None, ''):
        value = default

    try:
        volume = float(value)
    except Exception:
        volume = float(default or 1.0)

    if volume > 1.0:
        volume = volume / 100.0

    return max(0.0, min(volume, 1.0))

def register_soundboard_routes(app, context):
    base_dir = Path(context['base_dir'])
    wav_dir = Path(context.get('wav_dir') or (base_dir / 'subsystems' / 'soundboard' / 'wavs'))
    wav_dir.mkdir(parents=True, exist_ok=True)

    state_lock = context['state_lock']
    clients = context['clients']
    door_sound_repeat_allowed = context.get('door_sound_repeat_allowed', lambda deviceID, filename: True)

    def list_wav_files_by_category():
        if not wav_dir.exists():
            return []

        grouped = {}

        for wav_path in sorted(wav_dir.rglob('*.wav'), key=lambda p: str(p.relative_to(wav_dir)).lower()):
            if not wav_path.is_file():
                continue

            rel_path = wav_path.relative_to(wav_dir)
            parts = rel_path.parts
            category = parts[0] if len(parts) > 1 else 'Sounds'
            filename = rel_path.as_posix()

            grouped.setdefault(category, []).append({
                'filename': filename,
                'display_name': wav_path.name,
            })

        return [
            {
                'category': category,
                'files': files,
            }
            for category, files in sorted(grouped.items(), key=lambda item: item[0].lower())
        ]

    def play_wav_file(filename, volume=None):
        if not filename:
            return

        clean_name = str(filename).strip()

        if clean_name.startswith('wav:'):
            clean_name = clean_name.split(':', 1)[1]

        category = Path(clean_name).parts[0].strip().lower() if Path(clean_name).parts else ''
        volume = _coerce_wav_volume(volume, WAV_CATEGORY_VOLUME.get(category, 1.0))
        wav_path = (wav_dir / clean_name).resolve()

        try:
            wav_path.relative_to(wav_dir.resolve())
        except ValueError:
            return

        if not wav_path.exists() or not wav_path.is_file():
            return

        def _play():
            try:
                if os.name == 'nt':
                    import winsound
                    winsound.PlaySound(str(wav_path), winsound.SND_FILENAME | winsound.SND_ASYNC)
                    return

                players = (
                    [
                        'ffplay',
                        '-nodisp',
                        '-autoexit',
                        '-loglevel', 'quiet',
                        '-volume', str(round(volume * 100)),
                        str(wav_path),
                    ],
                    ['aplay', '-q', str(wav_path)],
                    ['paplay', str(wav_path)],
                )
                last_error = ''

                for cmd in players:
                    if not which(cmd[0]):
                        continue

                    completed = subprocess.run(
                        cmd,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.PIPE,
                        text=True,
                        timeout=10,
                    )

                    if completed.returncode == 0:
                        return

                    last_error = f'{cmd[0]}: {completed.stderr.strip() or completed.returncode}'

                if last_error:
                    app.logger.error('Sound playback failed for %s: %s', clean_name, last_error)
                else:
                    app.logger.error('No supported audio player found for %s', clean_name)
            except Exception:
                app.logger.exception('Sound playback failed for %s', clean_name)
                
        Thread(target=_play, daemon=True).start()

    def schedule_door_sound_repeat(client, filename, volume=None):
        deviceID = client.get('deviceID')

        if not deviceID:
            return

        def _repeat():
            with state_lock:
                current = clients.get(deviceID)

                calibrating = int(current.get('calibrating', 0) or 0) if current else 0

                if (
                    not current
                    or current.get('door_status') != 'open'
                    or calibrating > 0
                    or not door_sound_repeat_allowed(deviceID, filename)
                ):
                    _DOOR_SOUND_REPEAT_TIMERS.pop(deviceID, None)

                    return

                play_wav_file(filename, volume=volume)

                timer = Timer(DOOR_SOUND_REPEAT_SECONDS, _repeat)
                timer.daemon = True
                _DOOR_SOUND_REPEAT_TIMERS[deviceID] = timer
                timer.start()

        existing = _DOOR_SOUND_REPEAT_TIMERS.get(deviceID)

        if existing:
            existing.cancel()

        timer = Timer(DOOR_SOUND_REPEAT_SECONDS, _repeat)
        timer.daemon = True
        _DOOR_SOUND_REPEAT_TIMERS[deviceID] = timer
        timer.start()

    def cancel_door_sound_repeat(deviceID):
        timer = _DOOR_SOUND_REPEAT_TIMERS.pop(deviceID, None)

        if timer:
            timer.cancel()

    @app.route('/api/wavs')
    def api_wavs():
        categories = list_wav_files_by_category()
        files = [
            item['filename']
            for category in categories
            for item in category.get('files', [])
            if item.get('filename')
        ]

        return jsonify({
            'ok': True,
            'files': files,
            'categories': categories,
            'wavs': categories,
        })

    @app.route('/api/test-sound', methods=['POST'])
    def api_test_sound():
        data = request.get_json(silent=True) or {}
        filename = data.get('filename') or 'Bells/bell.wav'
        volume = data.get('volume', data.get('volume_percent'))

        play_wav_file(filename, volume=volume)
        return jsonify({'ok': True, 'filename': filename, 'volume': _coerce_wav_volume(volume, 1.0)})

    app.config['KOTIBOT_SOUNDBOARD_PLAY_WAV_FILE'] = play_wav_file
    app.config['KOTIBOT_SOUNDBOARD_SCHEDULE_DOOR_REPEAT'] = schedule_door_sound_repeat
    app.config['KOTIBOT_SOUNDBOARD_CANCEL_DOOR_REPEAT'] = cancel_door_sound_repeat

    return {
        'play_wav_file': play_wav_file,
        'schedule_door_sound_repeat': schedule_door_sound_repeat,
        'cancel_door_sound_repeat': cancel_door_sound_repeat,
    }

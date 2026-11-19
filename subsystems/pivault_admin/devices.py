"""Android device registry and the sync helper's token API, ported from the PiVault portal.

The helper runs on the computer a phone is plugged into and signs in with a
short-lived token issued to a signed-in dashboard user. The token is an HMAC
over its expiry using a key kept in the admin folder, so nothing secret per
token is stored. ADB keys never reach KotiBot.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
import secrets
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from . import store
from .client_packages import CLIENTS, _releases, download_filename, release_path

# Android package ids for the apps a phone can receive. Firefox is a browser add-on, not an Android app.
DEVICE_PACKAGES = {'android': 'com.x8bit.bitwarden', 'fdroid': 'org.fdroid.fdroid', 'adaway': 'org.adaway',
                   'davx5': 'at.bitfire.davdroid', 'jellyfin': 'org.jellyfin.mobile',
                   'organicmaps': 'app.organicmaps', 'vibrdrome': 'com.vibrdrome.app'}
DEVICE_DESCRIPTIONS = {
    'android': ('Bitwarden', 'Password manager for your Vaultwarden server'),
    'fdroid': ('F-Droid', 'Open-source app store for the local repo'),
    'adaway': ('AdAway', 'Blocks ads and trackers system-wide'),
    'davx5': ('DAVx⁵', 'Syncs contacts and calendars with your server'),
    'jellyfin': ('Jellyfin', 'Client for your Jellyfin media server'),
    'organicmaps': ('Organic Maps', 'Offline maps and navigation'),
    'vibrdrome': ('Vibrdrome', 'Client for your Navidrome music server'),
}
TOKEN_SECONDS = 2 * 60 * 60
ANDROID_ID = re.compile(r'[0-9a-f]{8,64}')
APP_STATES = {'enabled', 'disabled', 'missing', 'error', 'unknown'}
HELPER = Path(__file__).resolve().parent / 'pivault_android_sync.py'


class DeviceError(ValueError):
    pass


def _now():
    return datetime.now(timezone.utc).isoformat()


def _key(path=None):
    folder = store.root(path)
    target = folder / 'helper.key'
    if not target.is_file():
        folder.mkdir(mode=0o700, parents=True, exist_ok=True)
        descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(secrets.token_bytes(32))
    return target.read_bytes()


def issue_token(path=None, now=None):
    expiry = str(int((now or time.time()) + TOKEN_SECONDS))
    nonce = secrets.token_hex(8)
    body = expiry + '.' + nonce
    signature = hmac.new(_key(path), body.encode(), hashlib.sha256).hexdigest()
    return base64.urlsafe_b64encode((body + '.' + signature).encode()).decode()


def token_valid(token, path=None, now=None):
    try:
        expiry, nonce, signature = base64.urlsafe_b64decode(token.encode()).decode().split('.')
        expected = hmac.new(_key(path), (expiry + '.' + nonce).encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(signature, expected) and int(expiry) >= (now or time.time())
    except (ValueError, UnicodeError):
        return False


def helper_script(origin, path=None):
    # Placeholders are replaced here; the source keeps them, so it cannot be run with a stale token.
    return HELPER.read_text(encoding='utf-8').replace('__PIVAULT_BASE__', origin).replace('__PIVAULT_TOKEN__', issue_token(path))


def _identity(android_id, path=None):
    return hmac.new(_key(path), ('pivault-device:' + android_id).encode(), hashlib.sha256).hexdigest()


def _text(value, limit):
    return value.strip()[:limit] if isinstance(value, str) else ''


def _device_json(db, device_id):
    device = db.execute('SELECT * FROM devices WHERE id = ?', (device_id,)).fetchone()
    apps = {row['client']: {'enabled': bool(row['enabled']), 'package': DEVICE_PACKAGES[row['client']]}
            for row in db.execute('SELECT * FROM device_apps WHERE device_id = ?', (device_id,))
            if row['client'] in DEVICE_PACKAGES}
    return {'id': device['id'], 'name': device['name'], 'apps': apps}


def identify(body, path=None):
    android_id = body.get('android_id') if isinstance(body, dict) else None
    if not isinstance(android_id, str) or not ANDROID_ID.fullmatch(android_id):
        raise DeviceError('A valid Android ID is required.')
    model = _text(body.get('model'), 80)
    release = _text(body.get('android_release'), 16)
    identity = _identity(android_id, path)
    with store.connect(path) as db:
        row = db.execute('SELECT id FROM devices WHERE identity = ?', (identity,)).fetchone()
        if row is None:
            device_id = str(uuid.uuid4())
            db.execute('INSERT INTO devices (id, identity, name, model, android_release, first_seen, last_seen) '
                       'VALUES (?,?,?,?,?,?,?)', (device_id, identity, model or 'Android device', model, release, _now(), _now()))
        else:
            device_id = row['id']
            db.execute('UPDATE devices SET model = CASE WHEN ? != \'\' THEN ? ELSE model END, '
                       'android_release = CASE WHEN ? != \'\' THEN ? ELSE android_release END, last_seen = ? WHERE id = ?',
                       (model, model, release, release, _now(), device_id))
        for client in DEVICE_PACKAGES:
            db.execute('INSERT OR IGNORE INTO device_apps (device_id, client) VALUES (?,?)', (device_id, client))
        return _device_json(db, device_id)


def report(device_id, body, path=None):
    apps = body.get('apps') if isinstance(body, dict) else None
    if not isinstance(apps, dict) or any(client not in DEVICE_PACKAGES for client in apps):
        raise DeviceError('Unknown app in report.')
    if any(not isinstance(value, dict) or value.get('state') not in APP_STATES for value in apps.values()):
        raise DeviceError('Invalid app state in report.')
    with store.connect(path) as db:
        if db.execute('SELECT 1 FROM devices WHERE id = ?', (device_id,)).fetchone() is None:
            raise LookupError('No such device.')
        for client, value in apps.items():
            db.execute('UPDATE device_apps SET observed_state = ?, observed_version = ?, observed_at = ? '
                       'WHERE device_id = ? AND client = ?',
                       (value['state'], _text(value.get('version'), 64), _now(), device_id, client))
        db.execute('UPDATE devices SET last_seen = ? WHERE id = ?', (_now(), device_id))


def manifest(path=None):
    apps = {}
    releases = _releases(path, 'current_id')
    with store.connect(path) as db:
        rows = db.execute('SELECT client, current_id FROM client_packages WHERE current_id IS NOT NULL').fetchall()
    for row in rows:
        release = releases[row['current_id']]
        if row['client'] in DEVICE_PACKAGES and release_path(release).is_file():
            apps[row['client']] = {'version': release['version'], 'sha256': release['sha256'], 'size': release['size'],
                                   'url': '/api/pivault/devices/helper/apk/' + row['client']}
    return {'apps': apps}


def apk(client, path=None):
    """(file path, download name, mimetype) for the current copy, or None."""
    if client not in DEVICE_PACKAGES:
        return None
    releases = _releases(path, 'current_id')
    with store.connect(path) as db:
        row = db.execute('SELECT current_id FROM client_packages WHERE client = ?', (client,)).fetchone()
    if not row or not row['current_id']:
        return None
    release = releases[row['current_id']]
    target = release_path(release)
    if not target.is_file() or target.is_symlink():
        return None
    return target, download_filename(client, release['version']), CLIENTS[client][2]


def overview(path=None):
    releases = _releases(path, 'current_id')
    with store.connect(path) as db:
        pinned = {row['client']: row['current_id'] for row in db.execute('SELECT client, current_id FROM client_packages')}
        options = {}
        for row in db.execute('SELECT * FROM client_releases ORDER BY discovered_at DESC'):
            if row['client'] in DEVICE_PACKAGES and release_path(dict(row)).is_file() and not release_path(dict(row)).is_symlink():
                options.setdefault(row['client'], []).append({'id': row['id'], 'version': row['version']})
        devices = []
        for device in db.execute('SELECT * FROM devices ORDER BY name, first_seen'):
            apps = {row['client']: row for row in db.execute('SELECT * FROM device_apps WHERE device_id = ?', (device['id'],))}
            devices.append({
                'id': device['id'], 'name': device['name'], 'android_release': device['android_release'],
                'last_seen': device['last_seen'],
                'apps': [{'client': client, 'name': DEVICE_DESCRIPTIONS[client][0],
                          'description': DEVICE_DESCRIPTIONS[client][1],
                          'enabled': bool(apps[client]['enabled']) if client in apps else True,
                          'state': apps[client]['observed_state'] if client in apps else 'unknown',
                          'on_phone': apps[client]['observed_version'] if client in apps else '',
                          'versions': options.get(client, []), 'pinned': pinned.get(client)}
                         for client in DEVICE_PACKAGES]})
    return {'devices': devices}


def rename(device_id, name, path=None):
    name = (name or '').strip() if isinstance(name, str) else ''
    if not 1 <= len(name) <= 80:
        raise DeviceError('The name must be 1 to 80 characters.')
    with store.connect(path) as db:
        if not db.execute('UPDATE devices SET name = ? WHERE id = ?', (name, device_id)).rowcount:
            raise LookupError('No such device.')


def set_app(device_id, client, enabled, path=None):
    if client not in DEVICE_PACKAGES or not isinstance(enabled, bool):
        raise DeviceError('Unknown app or value.')
    with store.connect(path) as db:
        if not db.execute('UPDATE device_apps SET enabled = ? WHERE device_id = ? AND client = ?',
                          (int(enabled), device_id, client)).rowcount:
            raise LookupError('No such device app.')


def set_version(client, release_id, path=None):
    """Choosing an older local release is how an app is reverted."""
    if client not in DEVICE_PACKAGES:
        raise DeviceError('Unknown app.')
    with store.connect(path) as db:
        row = db.execute('SELECT * FROM client_releases WHERE id = ? AND client = ?', (release_id, client)).fetchone()
        if row is None:
            raise LookupError('No such release.')
        target = release_path(dict(row))
        if not target.is_file() or target.is_symlink():
            raise DeviceError('That release has no local copy.')
        db.execute('INSERT OR IGNORE INTO client_packages (client) VALUES (?)', (client,))
        current = db.execute('SELECT current_id FROM client_packages WHERE client = ?', (client,)).fetchone()['current_id']
        if current != release_id:
            db.execute('UPDATE client_packages SET previous_id = current_id, current_id = ? WHERE client = ?', (release_id, client))
            db.execute("UPDATE device_apps SET observed_state = 'unknown' WHERE client = ?", (client,))

"""Discover official client releases, download them, and verify them before anything is offered.

Ported from the PiVault portal. Discovery and validation are unchanged; storage is the
KotiBot admin database.
"""
import fcntl
import functools
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener
import zipfile
from datetime import datetime, timezone
from packaging.version import Version, InvalidVersion
from . import notifications, store
from subsystems.network import site_settings


class ValidationError(ValueError):
    pass

CLIENTS = {'android': ('Android app', '.apk', 'application/vnd.android.package-archive'),
           'firefox': ('Firefox extension', '.xpi', 'application/x-xpinstall'),
           'fdroid': ('F-Droid app', '.apk', 'application/vnd.android.package-archive'),
           'adaway': ('AdAway app', '.apk', 'application/vnd.android.package-archive'),
           'davx5': ('DAVx5 app', '.apk', 'application/vnd.android.package-archive'),
           'jellyfin': ('Jellyfin app', '.apk', 'application/vnd.android.package-archive'),
           'organicmaps': ('Organic Maps app', '.apk', 'application/vnd.android.package-archive'),
           'vibrdrome': ('Vibrdrome app', '.apk', 'application/vnd.android.package-archive')}
# Prefix for the file name a vault user downloads, e.g. Bitwarden-2026.10.0.apk.
DOWNLOAD_NAMES = {'android': 'Bitwarden', 'firefox': 'Bitwarden', 'fdroid': 'F-Droid', 'adaway': 'AdAway', 'davx5': 'DAVx5', 'jellyfin': 'Jellyfin', 'organicmaps': 'OrganicMaps', 'vibrdrome': 'Vibrdrome'}
FIREFOX_ID = '{446900e4-71c2-419f-a6a7-df9c091e268b}'
MAX_SIZE = 256 * 1024 * 1024


def cache_root():
    return Path(os.environ.get('KOTIBOT_PIVAULT_CLIENTS', '/data/pivault-clients'))


def safe_url(url, *, download=False):
    p = urlsplit(url)
    if p.scheme != 'https' or p.username or p.password or p.port not in (None, 443) or p.fragment:
        raise ValidationError('Invalid official client URL.')
    hosts = ('api.github.com', 'github.com', 'release-assets.githubusercontent.com',
        'objects.githubusercontent.com', 'github-releases.githubusercontent.com',
        'addons.mozilla.org', 'addons.cdn.mozilla.net', 'addons.mozilla.net', 'f-droid.org')
    if p.hostname not in hosts:
        raise ValidationError('Unexpected official client download host.')
    return url


class OfficialRedirects(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, url):
        safe_url(url, download=True)
        return super().redirect_request(request, fp, code, message, headers, url)


def http_open(url):
    safe_url(url)
    return build_opener(ProxyHandler({}), OfficialRedirects()).open(Request(url, headers={
        'User-Agent': 'PiVault-client-check/1', 'Accept-Encoding': 'identity',
        'Accept': 'application/json,application/octet-stream;q=0.9'}), timeout=30)


def read_json(url, limit=2 * 1024 * 1024):
    with http_open(url) as response:
        data = response.read(limit + 1)
        if len(data) > limit:
            raise ValidationError('Official release metadata was too large.')
        return json.loads(data)


def _github_artifact_rule(repo, asset, url):
    p = urlsplit(url)
    if p.hostname != 'github.com' or not p.path.startswith('/%s/releases/download/' % repo) or not asset.fullmatch(p.path.rsplit('/', 1)[-1]):
        raise ValidationError('Unexpected Android release artifact.')


def _firefox_artifact_rule(url):
    p = urlsplit(url)
    if p.hostname != 'addons.mozilla.org' or not p.path.startswith('/firefox/downloads/file/') or not p.path.endswith('.xpi'):
        raise ValidationError('Unexpected Firefox release artifact.')


# Each client in CLIENTS needs one entry in ARTIFACT_RULES, DISCOVERERS and ARCHIVE_CHECKS.
def _fdroid_artifact_rule(package_id, url):
    p = urlsplit(url)
    name = p.path.rsplit('/', 1)[-1]
    if p.hostname != 'f-droid.org' or not p.path.startswith('/repo/') or not name.startswith(package_id + '_') or not name.endswith('.apk'):
        raise ValidationError('Unexpected F-Droid release artifact.')


ARTIFACT_RULES = {'android': functools.partial(_github_artifact_rule, 'bitwarden/android', re.compile(r'com\.x8bit\.bitwarden\.apk')), 'firefox': _firefox_artifact_rule, 'fdroid': functools.partial(_fdroid_artifact_rule, 'org.fdroid.fdroid'), 'adaway': functools.partial(_fdroid_artifact_rule, 'org.adaway'), 'davx5': functools.partial(_fdroid_artifact_rule, 'at.bitfire.davdroid'), 'jellyfin': functools.partial(_fdroid_artifact_rule, 'org.jellyfin.mobile'), 'organicmaps': functools.partial(_fdroid_artifact_rule, 'app.organicmaps'), 'vibrdrome': functools.partial(_github_artifact_rule, 'ddmoney420/vibrdrome-android', re.compile(r'.+\.apk'))}


def validate_release(client, data):
    if client not in CLIENTS or set(data) != {'version', 'sha256', 'size', 'url', 'release_url'}:
        raise ValidationError('Invalid client release metadata.')
    try:
        version = Version(data['version'])
    except (InvalidVersion, TypeError):
        raise ValidationError('Invalid client version.') from None
    if version.is_prerelease or version.is_devrelease or len(data['version']) > 64:
        raise ValidationError('Only stable client releases can be offered.')
    if not re.fullmatch('[a-f0-9]{64}', data['sha256']):
        raise ValidationError('The official release has no valid SHA-256 digest.')
    if type(data['size']) is not int or not 0 < data['size'] <= MAX_SIZE:
        raise ValidationError('The official client package exceeds the allowed size.')
    safe_url(data['url']); safe_url(data['release_url'])
    ARTIFACT_RULES[client](data['url'])
    return data


def _discover_firefox():
    value = read_json('https://addons.mozilla.org/api/v5/addons/addon/bitwarden-password-manager/')
    if value.get('guid') != FIREFOX_ID:
        raise ValidationError('The Firefox add-on identity did not match Bitwarden.')
    current = value['current_version']; file = current['file']
    if file.get('status') != 'public':
        raise ValidationError('The Firefox package is not a published release.')
    return {'version': current['version'], 'sha256': file['hash'].removeprefix('sha256:'),
        'size': file['size'], 'url': file['url'],
        'release_url': 'https://addons.mozilla.org/en-US/firefox/addon/bitwarden-password-manager/'}


def _discover_github(repo, tag_suffix, asset):
    releases = read_json('https://api.github.com/repos/%s/releases?per_page=20' % repo)
    # Newest stable release that ships the APK. A newer release without it (Bitwarden's 2026.11.0
    # ships only the F-Droid build) is skipped; the Play build stays on the newest release that has it.
    for release in releases:
        if release.get('draft') or release.get('prerelease') or not release['tag_name'].endswith(tag_suffix):
            continue
        matches = [a for a in release['assets'] if asset.fullmatch(a['name'])]
        if not matches:
            continue
        if len(matches) != 1:
            raise ValidationError('The Android release must have exactly one matching APK.')
        found = matches[0]
        digest = found.get('digest', '')
        if not digest.startswith('sha256:'):
            raise ValidationError('The Android release has no upstream SHA-256 digest.')
        return {'version': release['tag_name'].removeprefix('v').removesuffix(tag_suffix),
            'sha256': digest[7:], 'size': found['size'], 'url': found['browser_download_url'],
            'release_url': release['html_url']}
    raise ValidationError('No recent stable release has the Android APK.')


FDROID_INDEX_URL = 'https://f-droid.org/repo/index-v2.json'
FDROID_INDEX_LIMIT = 128 * 1024 * 1024
_INDEX_CACHE = {}


def fdroid_index():
    # One index read serves every F-Droid client in a maintenance run; maintain() clears the cache.
    if 'index' not in _INDEX_CACHE:
        _INDEX_CACHE['index'] = read_json(FDROID_INDEX_URL, limit=FDROID_INDEX_LIMIT)
    return _INDEX_CACHE['index']


FDROID_BUILD_SUFFIX = re.compile(r'-(ose|FDroid)$')


def _discover_fdroid(package_id):
    package = fdroid_index().get('packages', {}).get(package_id)
    if not package:
        raise ValidationError('The F-Droid index does not list ' + package_id + '.')
    versions = sorted(package.get('versions', {}).values(),
        key=lambda value: value.get('manifest', {}).get('versionCode', 0), reverse=True)
    for version in versions:
        try:
            name = FDROID_BUILD_SUFFIX.sub('', version['manifest']['versionName']); parsed = Version(name)
        except (InvalidVersion, TypeError, KeyError):
            continue
        if parsed.is_prerelease or parsed.is_devrelease:
            continue
        file = version['file']
        return {'version': name, 'sha256': file['sha256'], 'size': file['size'],
            'url': 'https://f-droid.org/repo/' + file['name'].lstrip('/'),
            'release_url': 'https://f-droid.org/packages/' + package_id + '/'}
    raise ValidationError('The F-Droid index has no stable release of ' + package_id + '.')


DISCOVERERS = {'android': functools.partial(_discover_github, 'bitwarden/android', '-bwpm', re.compile(r'com\.x8bit\.bitwarden\.apk')), 'firefox': _discover_firefox, 'fdroid': functools.partial(_discover_fdroid, 'org.fdroid.fdroid'), 'adaway': functools.partial(_discover_fdroid, 'org.adaway'), 'davx5': functools.partial(_discover_fdroid, 'at.bitfire.davdroid'), 'jellyfin': functools.partial(_discover_fdroid, 'org.jellyfin.mobile'), 'organicmaps': functools.partial(_discover_fdroid, 'app.organicmaps'), 'vibrdrome': functools.partial(_discover_github, 'ddmoney420/vibrdrome-android', '', re.compile(r'.+\.apk'))}


def discover(client):
    return validate_release(client, DISCOVERERS[client]())


def _now():
    return datetime.now(timezone.utc).isoformat()


def offline():
    # Offline mode (Settings > Network) pauses every job that needs the internet.
    path = os.environ.get('KOTIBOT_SITE_SETTINGS', '').strip()
    return bool(path) and site_settings.load(path)['jobs'] == 'paused'


def discover(client):
    return validate_release(client, DISCOVERERS[client]())


def record_release(client, data, path=None):
    validate_release(client, data)
    identity = hashlib.sha256(json.dumps({'client': client, **data}, sort_keys=True).encode()).hexdigest()
    with store.connect(path) as db:
        db.execute('INSERT OR IGNORE INTO client_packages (client) VALUES (?)', (client,))
        row = db.execute('SELECT p.*, r.version AS current_version FROM client_packages p '
                         'LEFT JOIN client_releases r ON r.id = p.current_id WHERE p.client = ?', (client,)).fetchone()
        if row['current_version'] and Version(data['version']) < Version(row['current_version']):
            db.execute("UPDATE client_packages SET checked_at = ?, last_error = '' WHERE client = ?", (_now(), client))
            return
        db.execute('INSERT OR IGNORE INTO client_releases (id, client, version, sha256, size, url, release_url, discovered_at) '
                   'VALUES (?,?,?,?,?,?,?,?)', (identity, client, data['version'], data['sha256'], data['size'],
                                                 data['url'], data['release_url'], _now()))
        db.execute("UPDATE client_packages SET latest_id = ?, checked_at = ?, last_error = '' WHERE client = ?",
                   (identity, _now(), client))


def release_path(release):
    if release['client'] not in CLIENTS or not re.fullmatch('[a-f0-9]{64}', release['sha256']):
        raise ValidationError('Invalid cached release identity.')
    return cache_root() / (release['client'] + '-' + release['sha256'] + CLIENTS[release['client']][1])


def download_filename(client, version):
    return DOWNLOAD_NAMES[client] + '-' + version + CLIENTS[client][1]


def _is_cache_blob(name):
    return any(re.fullmatch(re.escape(client) + '-[a-f0-9]{64}' + re.escape(extension), name)
               for client, (_, extension, _) in CLIENTS.items())


def _check_firefox_archive(archive, release):
    if archive.getinfo('manifest.json').file_size > 1024 * 1024:
        raise ValidationError('Invalid Firefox manifest.')
    manifest = json.loads(archive.read('manifest.json'))
    gecko = manifest.get('browser_specific_settings', manifest.get('applications', {})).get('gecko', {})
    if gecko.get('id') != FIREFOX_ID or manifest.get('version') != release['version']:
        raise ValidationError('The Firefox package identity or version did not match.')
    names = [name.lower() for name in archive.namelist()]
    if not any(name.startswith('meta-inf/') and name.endswith(('.rsa', '.sig')) for name in names):
        raise ValidationError('The Firefox package has no retained signing data.')


def _check_android_archive(archive, release):
    if 'AndroidManifest.xml' not in archive.namelist():
        raise ValidationError('The Android package is not an APK.')


ARCHIVE_CHECKS = {client: (_check_firefox_archive if client == 'firefox' else _check_android_archive) for client in CLIENTS}


def verify_package(path, release):
    if path.stat().st_size != release['size']:
        raise ValidationError('Client package size does not match the release.')
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    if digest.hexdigest() != release['sha256']:
        raise ValidationError('Client package checksum does not match the release.')
    try:
        with zipfile.ZipFile(path) as archive:
            ARCHIVE_CHECKS[release['client']](archive, release)
    except zipfile.BadZipFile:
        raise ValidationError('The client package is not a valid archive.') from None


def _quiet(message):
    pass


def fetch(release, progress=_quiet):
    # Download and verify a discovered release into the local cache.
    destination = release_path(release)
    if destination.is_file() and not destination.is_symlink():
        try:
            verify_package(destination, release)
            return destination
        except ValidationError:
            destination.unlink(missing_ok=True)
    validate_release(release['client'], {key: release[key] for key in ('version', 'sha256', 'size', 'url', 'release_url')})
    cache_root().mkdir(mode=0o750, parents=True, exist_ok=True)
    if shutil.disk_usage(cache_root()).free < release['size'] * 2 + 32 * 1024 * 1024:
        raise ValidationError('Insufficient space for a verified client download.')
    fd, temporary = tempfile.mkstemp(prefix='.client-', dir=cache_root())
    try:
        progress('Downloading ' + CLIENTS[release['client']][0] + ' ' + release['version'] + ': '
                 + str(release['size'] // (1024 * 1024)) + ' MB')
        with os.fdopen(fd, 'wb') as output, http_open(release['url']) as response:
            written = 0
            while chunk := response.read(1024 * 1024):
                written += len(chunk)
                if written > release['size']:
                    raise ValidationError('Client download exceeded the expected size.')
                output.write(chunk)
            output.flush(); os.fsync(output.fileno())
        verify_package(Path(temporary), release)
        os.chmod(temporary, 0o444)
        os.replace(temporary, destination)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return destination


def _releases(path, *columns):
    with store.connect(path) as db:
        rows = db.execute('SELECT * FROM client_packages').fetchall()
        wanted = {row[column] for row in rows for column in columns if row[column]}
        return {identity: dict(db.execute('SELECT * FROM client_releases WHERE id = ?', (identity,)).fetchone())
                for identity in wanted}


def prune_cache(path=None):
    # Keep the in-use copies and the newest discovered copy; remove only this cache's other blobs.
    releases = _releases(path, 'current_id', 'previous_id', 'latest_id')
    keep = {str(release_path(value)) for value in releases.values()}
    if not cache_root().is_dir():
        return
    for blob in cache_root().iterdir():
        if _is_cache_blob(blob.name) and str(blob) not in keep:
            blob.unlink(missing_ok=True)


def _publish(client, release, path=None):
    with store.connect(path) as db:
        row = db.execute('SELECT p.current_id, r.version FROM client_packages p '
                         'LEFT JOIN client_releases r ON r.id = p.current_id WHERE p.client = ?', (client,)).fetchone()
        if row['version'] and Version(row['version']) > Version(release['version']):
            return False
        if row['current_id'] != release['id']:
            db.execute('UPDATE client_packages SET previous_id = current_id, current_id = ? WHERE client = ?',
                       (release['id'], client))
    return True


class ClientRunBusy(Exception):
    """Raised when another client maintenance run already holds the lock."""


def maintain(check_only=False, progress=_quiet, path=None):
    if offline():
        return []
    cache_root().mkdir(mode=0o750, parents=True, exist_ok=True)
    _INDEX_CACHE.clear()
    with (cache_root() / '.maintenance.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ClientRunBusy() from None
        errors = []
        today = datetime.now(timezone.utc).date().isoformat()
        for client in CLIENTS:
            progress('Checking ' + CLIENTS[client][0])
            try:
                record_release(client, discover(client), path)
                progress('  checked')
            except Exception:
                progress('  check failed')
                errors.append(client)
                message = 'The official release could not be checked. The previous copy is retained.'
                with store.connect(path) as db:
                    db.execute('INSERT OR IGNORE INTO client_packages (client) VALUES (?)', (client,))
                    db.execute('UPDATE client_packages SET last_error = ? WHERE client = ?', (message, client))
                notifications.notify('clients', 'check-' + client + '-' + today,
                                     CLIENTS[client][0] + ' release check failed', message, level='warning', path=path)
        if not check_only:
            # Downloads are automatic: each verified newest release becomes the version phones sync.
            latest = _releases(path, 'latest_id')
            with store.connect(path) as db:
                rows = db.execute('SELECT client, latest_id FROM client_packages WHERE latest_id IS NOT NULL').fetchall()
            for row in rows:
                release = latest[row['latest_id']]
                try:
                    fetch(release, progress)
                    _publish(row['client'], release, path)
                except Exception:
                    errors.append(row['client'])
                    notifications.notify('clients', 'fetch-' + row['client'] + '-' + today,
                                         CLIENTS[row['client']][0] + ' download failed',
                                         'The latest release could not be downloaded or verified. Nothing is offered from it.',
                                         level='warning', path=path)
            prune_cache(path)
        if not errors:
            notifications.resolve_matching("source = 'clients' AND level = 'warning'", path=path)
        return sorted(set(errors))


def client_rows(path=None):
    releases = _releases(path, 'current_id', 'latest_id')
    with store.connect(path) as db:
        packages = {row['client']: row for row in db.execute('SELECT * FROM client_packages')}
    rows = []
    for client, (label, _, _) in CLIENTS.items():
        package = packages.get(client)
        current = releases.get(package['current_id']) if package else None
        latest = releases.get(package['latest_id']) if package else None
        available = bool(current and release_path(current).is_file())
        pending = bool(latest and current and latest['id'] != current['id'])
        status = 'Up to date' if available and not pending else 'Not downloaded'
        if pending:
            status = 'Download pending · retries at 2:00 AM'
        if package and package['last_error']:
            status = 'Check failed · local copy retained' if available else 'Check failed'
        rows.append({'key': client, 'label': label, 'current': current['version'] if current else '—',
                     'latest': latest['version'] if latest else '—',
                     'checked_at': package['checked_at'] if package else None,
                     'error': package['last_error'] if package else '', 'status': status, 'available': available})
    return rows

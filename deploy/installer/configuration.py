"""Pure configuration transformations used by the installer and its tests."""
import copy
import fnmatch
import re

BEGIN = '# BEGIN PIVAULT USERS INSTALLER'
END = '# END PIVAULT USERS INSTALLER'
JS_BEGIN = '/* BEGIN PIVAULT USERS INSTALLER */'
JS_END = '/* END PIVAULT USERS INSTALLER */'
# The PiVault launcher and portal are the root address; Vaultwarden has its own HTTPS port.
PORTAL_HOST = '192.168.4.90'
PORTAL_PORT = 443
PORTAL_SITE = f'https://{PORTAL_HOST}'
# The launcher used to live on 8443. That address now only redirects to the root.
OLD_LAUNCHER_PORT = 8443
OLD_LAUNCHER_SITE = f'https://{PORTAL_HOST}:{OLD_LAUNCHER_PORT}'
VAULT_PORT = 8448
VAULT_SITE = f'https://{PORTAL_HOST}:{VAULT_PORT}'
SERVICE = 'pivault-users'
# The launcher is retired. The root address sends visitors to KotiBot's own address, which needs no name lookup.
KOTIBOT_HOME = f'https://{PORTAL_HOST}:8449/'
# Radicale's config folder on the Pi. The portal mounts it read-only; it no longer writes here.
RADICALE_CONFIG_FOLDER = '/home/snx/radicale/config'
MUSIC_PRIVATE_FOLDER = '/srv/disk3/music-private'
# The Admin switches (network roles, Internet jobs) are one small JSON file that KotiBot and the portal share.
SITE_FOLDER = '/srv/pi-server/config/site'
SITE_SETTINGS_FILE = '/site/site-settings.json'

PORTAL = '''
    # BEGIN PIVAULT USERS INSTALLER
    redir / https://192.168.4.90:8449/ 302
    @pivault_users_installer path /join /join/* /users /users/* /notifications /notifications/* /certificate /certificate/* /network /devices /devices/* /services /services/* /internal /internal/* /favicon.ico /apple-touch-icon.png /manifest.webmanifest
    handle @pivault_users_installer {
        @pivault_users_internal path /internal /internal/*
        respond @pivault_users_internal 404
        reverse_proxy pivault-users:8000 {
            header_up X-Forwarded-Proto https
            header_up X-PiVault-Client-IP {remote_host}
        }
    }
    # END PIVAULT USERS INSTALLER
'''
# The launcher sign-in gate is gone with the launcher. Its markers stay so that an older install's block is removed.
LAUNCHER_BEGIN = '# BEGIN PIVAULT LAUNCHER AUTH'
LAUNCHER_END = '# END PIVAULT LAUNCHER AUTH'


# HTTPS sites for the apps that were plain HTTP on the LAN. Each keeps its port number.
APPS_BEGIN = '# BEGIN PIVAULT APP HTTPS SITES'
APPS_END = '# END PIVAULT APP HTTPS SITES'
APP_SITES = [
    (5232, '    reverse_proxy radicale:5232\n'),
    (8000, '    reverse_proxy pivault-arcade:8000\n'),
    (8083, '    reverse_proxy calibre-web:8083\n'),
    # Kiwix serves under /wiki (its --urlRootLocation), so its own port opens there.
    (8084, '    redir / /wiki/\n    reverse_proxy pivault-kiwix:8080\n'),
    (8085, '    reverse_proxy pivault-paperless:8000\n'),
    (8096, '    reverse_proxy jellyfin:8096\n'),
    # Lychee serves under /photos (APP_DIR). Caddy strips the prefix before the request reaches it, and these two
    # ports open at the path. Anything else on them (old bookmarks, share links) is sent to the same address under it.
    (8446, '    request_body {\n        max_size 2048MB\n    }\n'
           '    redir / /photos/\n'
           '    handle_path /photos/* {\n'
           '        reverse_proxy lychee:8000 {\n            header_up X-Forwarded-Proto https\n        }\n'
           '    }\n'
           '    handle {\n        redir /photos{uri} 302\n    }\n'),
    (8447, '    redir / /photos/\n'
           '    handle_path /photos/* {\n        reverse_proxy lychee:8000\n    }\n'
           '    handle {\n        redir /photos{uri} 302\n    }\n'),
    # KotiBot runs on the host network and listens on the Compose bridge gateway (deploy/stack/kotibot/README.md).
    (8449, '    reverse_proxy 172.18.0.1:5000\n'),
]
APP_PORTS = {port for port, _ in APP_SITES}
# Further names that reach the same app (kotibot.lan names, 2026-11-20). They share the port's site block, so
# rebuilding that block here must keep them, or the names stop working and the TLS check below refuses the change.
APP_EXTRA_NAMES = {
    5232: ('calendar.kotibot.lan',),
    8000: ('arcade.kotibot.lan',),
    8083: ('library.kotibot.lan',),
    8084: ('wiki.kotibot.lan',),
    8085: ('kotibot.lan:8085', 'paperless.kotibot.lan'),
    8096: ('jellyfin.kotibot.lan',),
    8446: ('photos.kotibot.lan',),
}

# Sites that Caddy serves by name on the root HTTPS port (443), alongside the IP-address sites. Caddy chooses the
# site from the name the browser asks for, so the port stays 443. The name must resolve to the Pi on the LAN
# (router or Pi-hole), and a device that trusts the PiVault certificate trusts these names too.
# kotibot.lan is the machine's own front door: one name, one path per role (/wiki, /library, ...). A path names a
# role, not a product, so the app behind it can be replaced without changing the address. Each app is told its own
# prefix (see deploy/stack/kotibot/PATHS.md); paths not listed here yet are added one app at a time.
KOTIBOT_LAN_BODY = (
    '    redir /wiki /wiki/\n'
    '    redir /library /library/\n'
    '    redir /photos /photos/\n'
    '    # KotiBot is the root of this name, so the old /smarthome role path goes there.\n'
    '    redir /smarthome /\n'
    '    redir /smarthome/* /\n'
    '    handle /wiki/* {\n'
    '        reverse_proxy pivault-kiwix:8080\n'
    '    }\n'
    '    handle /library/* {\n'
    '        reverse_proxy calibre-web:8083 {\n'
    '            header_up X-Script-Name /library\n'
    '        }\n'
    '    }\n'
    '    handle_path /photos/* {\n'
    '        request_body {\n            max_size 2048MB\n        }\n'
    '        reverse_proxy lychee:8000\n'
    '    }\n'
    '    # KotiBot is the home page of this name. It runs on the host network and listens on the Compose bridge\n'
    '    # gateway, the same upstream as its port 8449 site.\n'
    '    handle {\n'
    '        reverse_proxy 172.18.0.1:5000\n'
    '    }\n'
)
NAMED_SITES = [
    ('kotibot.lan', KOTIBOT_LAN_BODY),
]
NAMED_HOSTS = {name for name, _ in NAMED_SITES}


def replace_managed(text, begin, end, replacement=''):
    if begin not in text and end not in text:
        return text
    if text.count(begin) != 1 or text.count(end) != 1:
        raise ValueError('The existing managed block is incomplete or duplicated.')
    start = text.index(begin)
    finish = text.index(end, start) + len(end)
    line_start = text.rfind('\n', 0, start) + 1
    if not text[line_start:start].strip():
        start = max(0, line_start - 1)
    line_end = text.find('\n', finish)
    if line_end != -1 and not text[finish:line_end].strip():
        finish = line_end + 1
    return text[:start] + replacement + text[finish:]


def tokens(text):
    # Caddy placeholders are single tokens, not block braces. Comments and
    # quoted strings cannot open or close a site block.
    pattern = r'#[^\n]*|"(?:\\.|[^"\\])*"|`[^`]*`|[^\s]+'
    for match in re.finditer(pattern, text):
        value = match.group()
        if not value.startswith('#'):
            yield value, match.start(), match.end()


VAULT_ROUTE = 'reverse_proxy vaultwarden:80'
LAUNCHER_ROUTE = 'reverse_proxy homepage:3000'
ROOT_NAMES = {PORTAL_SITE, f'{PORTAL_HOST}:{PORTAL_PORT}'}
OLD_LAUNCHER_NAMES = {OLD_LAUNCHER_SITE, f'{PORTAL_HOST}:{OLD_LAUNCHER_PORT}'}
VAULT_NAMES = {VAULT_SITE, f'{PORTAL_HOST}:{VAULT_PORT}'}


def site_blocks(text):
    # Top-level Caddy site blocks, each with its address names and character positions.
    depth = 0
    header = []
    header_start = None
    opened = None
    blocks = []
    for value, start, finish in tokens(text):
        if value == '{':
            if depth == 0:
                names = [x.strip(',').strip('"`') for x in header]
                opened = (names, header_start, finish)
                header = []
            depth += 1
        elif value == '}':
            depth -= 1
            if depth < 0:
                raise ValueError('Caddyfile has unbalanced blocks.')
            if depth == 0:
                names, begin, body = opened
                blocks.append({'names': names, 'start': begin, 'body': text[body:start], 'end': finish})
                header = []
        elif depth == 0:
            if not header:
                header_start = start
            header.append(value)
    if depth:
        raise ValueError('Caddyfile has unbalanced blocks.')
    return blocks


def move_vault_to_own_port(text):
    # Live layout: Vaultwarden on the root address, the launcher on 8443.
    # Target layout: the launcher on the root address, Vaultwarden on VAULT_PORT,
    # and 8443 redirects to the root so old bookmarks still work.
    blocks = site_blocks(text)
    if any(set(block['names']) & VAULT_NAMES for block in blocks):
        return text
    roots = [block for block in blocks if set(block['names']) & ROOT_NAMES]
    launchers = [block for block in blocks if set(block['names']) & OLD_LAUNCHER_NAMES]
    if (len(roots) != 1 or len(launchers) != 1 or VAULT_ROUTE not in roots[0]['body']
            or LAUNCHER_ROUTE not in launchers[0]['body']):
        raise ValueError('Expected Vaultwarden on ' + PORTAL_SITE + ' and the launcher on ' + OLD_LAUNCHER_SITE + '.')
    root, launcher = roots[0], launchers[0]
    redirect = ('%s {\n    tls internal\n    redir %s{uri} 302\n}\n' % (OLD_LAUNCHER_SITE, PORTAL_SITE))
    vault = VAULT_SITE + ' {' + root['body'] + '}\n'
    edits = [
        (root['start'], root['end'], PORTAL_SITE + ' {' + launcher['body'] + '}'),
        (launcher['start'], launcher['end'], redirect + vault),
    ]
    for start, finish, replacement in sorted(edits, reverse=True):
        text = text[:start] + replacement + text[finish:]
    return text


def portal_caddyfile(text):
    clean = replace_managed(text, BEGIN, END)
    clean = replace_managed(clean, LAUNCHER_BEGIN, LAUNCHER_END)
    clean = move_vault_to_own_port(clean)
    if '@pivault_users_installer' in clean:
        raise ValueError('The portal matcher already exists outside its managed block.')
    depth = 0
    header = []
    matches = []
    for value, start, finish in tokens(clean):
        if value == '{':
            if depth == 0:
                names = [x.strip(',').strip('"`') for x in header]
                target = any(x in (f'{PORTAL_HOST}:{PORTAL_PORT}', PORTAL_SITE) for x in names)
                if target:
                    matches.append(finish)
                header = []
            depth += 1
        elif value == '}':
            depth -= 1
            if depth < 0:
                raise ValueError('Caddyfile has unbalanced blocks.')
            if depth == 0:
                header = []
        elif depth == 0:
            header.append(value)
    if depth or len(matches) != 1:
        raise ValueError('Expected one explicit ' + PORTAL_SITE + ' site block in the active Caddyfile.')
    position = matches[0]
    return clean[:position] + PORTAL + clean[position:]


def remove_site_blocks(text, ports, names=()):
    targets = {f'https://{PORTAL_HOST}:{port}' for port in ports} | {f'https://{name}' for name in names}
    depth = 0
    header = []
    header_start = None
    block_start = None
    removals = []
    for value, start, finish in tokens(text):
        if value == '{':
            if depth == 0:
                names = [x.strip(',').strip('"`') for x in header]
                block_start = header_start if any(name in targets for name in names) else None
                header = []
            depth += 1
        elif value == '}':
            depth -= 1
            if depth == 0:
                if block_start is not None:
                    removals.append((block_start, finish))
                    block_start = None
                header = []
        elif depth == 0:
            if not header:
                header_start = start
            header.append(value)
    for start, finish in reversed(removals):
        text = text[:start] + text[finish:]
    return text


def apps_caddyfile(text):
    clean = replace_managed(text, APPS_BEGIN, APPS_END)
    clean = remove_site_blocks(clean, APP_PORTS, NAMED_HOSTS)
    sites = []
    for port, body in APP_SITES:
        addresses = ', '.join([f'https://{PORTAL_HOST}:{port}'] + [f'https://{name}' for name in APP_EXTRA_NAMES.get(port, ())])
        sites.append('%s {\n    tls internal\n    encode zstd gzip\n%s}\n' % (addresses, body))
    for name, body in NAMED_SITES:
        sites.append('https://%s {\n    tls internal\n    encode zstd gzip\n%s}\n' % (name, body))
    block = APPS_BEGIN + '\n' + '\n'.join(sites) + APPS_END
    return clean.rstrip('\n') + '\n\n' + block + '\n'


def private_vault_admin(text, site=VAULT_SITE):
    begin = '# BEGIN PIVAULT PRIVATE VAULT ADMIN'
    end = '# END PIVAULT PRIVATE VAULT ADMIN'
    clean = replace_managed(text, begin, end)
    depth = 0; header = []; positions = []
    for value, start, finish in tokens(clean):
        if value == '{':
            if depth == 0:
                names = [x.strip(',').strip('"`') for x in header]
                if any(name in (site, site[len('https://'):]) for name in names):
                    positions.append(finish)
                header = []
            depth += 1
        elif value == '}':
            depth -= 1
            if depth == 0: header = []
        elif depth == 0:
            header.append(value)
    if len(positions) != 1:
        raise ValueError('Expected one explicit vault HTTPS site before enabling private enrollment.')
    block = '\n    ' + begin + '\n    @pivault_private_vault_admin path /admin /admin/*\n    respond @pivault_private_vault_admin 404\n    ' + end + '\n'
    position = positions[0]
    return clean[:position] + block + clean[position:]


def homepage_js(original, addon):
    clean = replace_managed(original, JS_BEGIN, JS_END).rstrip('\n')
    return clean + '\n\n' + JS_BEGIN + '\n' + addon.rstrip() + '\n' + JS_END + '\n'


def compose_configuration(original, *, image, uid, gid, network_names, radicale_config=False, music_private=False):
    result = copy.deepcopy(original)
    services = result.setdefault('services', {})
    existing = services.get(SERVICE)
    if existing and existing.get('labels', {}).get('org.pivault.managed') != 'users-installer':
        raise ValueError('An unmanaged pivault-users Compose service already exists.')
    volumes = [
        '/srv/pi-server/config/users/data:/data',
        '/srv/pi-server/config/notifications:/notifications',
        '/srv/pi-server/config/users/native.json:/native.json:ro',
        SITE_FOLDER + ':/site',
    ]
    if radicale_config:
        # The portal no longer writes Radicale's login file (owner decision, todo 1.5), so the mount is read-only.
        volumes.append(RADICALE_CONFIG_FOLDER + ':/radicale-config:ro')
    if music_private:
        # Per-user Music folders are created by the portal, so the private root is mounted read-write.
        volumes.append(MUSIC_PRIVATE_FOLDER + ':/music-private')
    service = {
        'image': image, 'container_name': SERVICE, 'restart': 'unless-stopped',
        'user': f'{uid}:{gid}', 'read_only': True,
        'cap_drop': ['ALL'], 'security_opt': ['no-new-privileges:true'],
        'tmpfs': ['/tmp:rw,noexec,nosuid,size=64m'],
        'mem_limit': '1g',
        'env_file': ['/srv/pi-server/config/users/users.env'],
        'environment': {'PIVAULT_NATIVE_CONFIG': '/native.json', 'PIVAULT_SITE_SETTINGS': SITE_SETTINGS_FILE},
        'volumes': volumes,
        'labels': {'org.pivault.managed': 'users-installer'},
    }
    if network_names:
        service['networks'] = list(network_names)
    services[SERVICE] = service
    return result


def front_door_compose(original, caddy_service):
    # Caddy publishes Vaultwarden's own port, and the homepage accepts the root address.
    result = copy.deepcopy(original)
    services = result.get('services', {})
    caddy = services.get(caddy_service)
    homepage = services.get('homepage')
    if caddy is None or homepage is None:
        raise ValueError('The Caddy or homepage Compose service is missing.')
    published = f'{PORTAL_HOST}:{VAULT_PORT}:{VAULT_PORT}'
    ports = caddy.setdefault('ports', [])
    if not any(str(item).split('/')[0] == published for item in ports):
        ports.append(published)
    environment = homepage.setdefault('environment', {})
    if not isinstance(environment, dict):
        raise ValueError('The homepage Compose environment must be a mapping.')
    environment['HOMEPAGE_ALLOWED_HOSTS'] = f'{PORTAL_HOST}:8086,{PORTAL_HOST}'
    return result


def _matches(match, host, path):
    for name, value in match.items():
        if name == 'host':
            if not any(fnmatch.fnmatchcase(host, item) for item in value):
                return False
        elif name == 'path':
            if not any(fnmatch.fnmatchcase(path, item) for item in value):
                return False
        elif name == 'method':
            if 'GET' not in value:
                return False
        elif name == 'protocol':
            if value != 'https':
                return False
        elif name == 'not':
            if any(_matches(item, host, path) for item in value):
                return False
        else:
            raise ValueError('Cannot verify portal precedence with the existing Caddy matcher: ' + name)
    return True


def terminal_handler(config, host, path, port=443):
    def walk(routes):
        for route in routes:
            if route.get('match') and not any(_matches(item, host, path) for item in route['match']):
                continue
            for handler in route.get('handle', []):
                kind = handler.get('handler')
                if kind == 'subroute':
                    found = walk(handler.get('routes', []))
                    if found:
                        return found
                elif kind in ('reverse_proxy', 'static_response'):
                    return handler
                elif kind not in ('headers', 'vars', 'encode'):
                    raise ValueError('Cannot verify portal routing with the existing Caddy handler: ' + str(kind))
        return None
    for server in config.get('apps', {}).get('http', {}).get('servers', {}).values():
        if any(address.endswith(f':{port}') for address in server.get('listen', [])):
            found = walk(server.get('routes', []))
            if found:
                return found
    return None


def _current_handler(before, *ports):
    # A service that has moved leaves a 302 redirect on its old port, so read it from the first port that proxies.
    for port in ports:
        handler = terminal_handler(before, PORTAL_HOST, '/', port)
        if handler and handler.get('handler') == 'reverse_proxy':
            return handler
    return None


def _tls_without_names(tls, names):
    # A new named site adds its name to the internal-CA policy. Every other TLS setting must stay as it was.
    value = copy.deepcopy(tls)
    if isinstance(value, dict):
        for policy in value.get('automation', {}).get('policies', []):
            if 'subjects' in policy:
                # Caddy lists the names in no fixed order, so compare them as a sorted set.
                policy['subjects'] = sorted(name for name in policy['subjects'] if name not in names)
    return value


def verify_routes(before, after, vault_host=None):
    for path in ('/join', '/users/add', '/users/sign-in', '/users/session', '/notifications', '/notifications/api',
                 '/certificate', '/devices'):
        value = terminal_handler(after, PORTAL_HOST, path, PORTAL_PORT)
        if not value or value.get('handler') != 'reverse_proxy' or value.get('upstreams') != [{'dial': 'pivault-users:8000'}]:
            raise ValueError('The candidate Caddy routes do not reach the portal before the existing handlers.')
        request_headers = value.get('headers', {}).get('request', {}).get('set', {})
        if request_headers.get('X-Forwarded-Proto') != ['https'] or request_headers.get('X-Pivault-Client-Ip') != ['{http.request.remote.host}']:
            raise ValueError('The candidate proxy does not overwrite the trusted HTTPS/client address headers.')
    for path in ('/internal', '/internal/gate'):
        value = terminal_handler(after, PORTAL_HOST, path, PORTAL_PORT)
        if not value or value.get('handler') != 'static_response' or value.get('status_code') != 404:
            raise ValueError('The private authentication endpoint would be publicly reachable.')
    root = terminal_handler(after, PORTAL_HOST, '/', PORTAL_PORT)
    if (not root or root.get('handler') != 'static_response' or root.get('status_code') != 302
            or root.get('headers', {}).get('Location') != [KOTIBOT_HOME]):
        raise ValueError('The candidate configuration does not send the root address to KotiBot.')
    if _current_handler(before, VAULT_PORT, PORTAL_PORT) != terminal_handler(after, PORTAL_HOST, '/', VAULT_PORT):
        raise ValueError('The candidate configuration changes the existing Vaultwarden route.')
    if (_tls_without_names(before.get('apps', {}).get('tls'), NAMED_HOSTS)
            != _tls_without_names(after.get('apps', {}).get('tls'), NAMED_HOSTS)):
        raise ValueError('The candidate configuration changes TLS settings.')
    if vault_host:
        for path in ('/admin', '/admin/users'):
            value = terminal_handler(after, vault_host, path, VAULT_PORT)
            if not value or value.get('handler') != 'static_response' or value.get('status_code') != 404:
                raise ValueError('Vault administration must remain private to the enrollment backend.')

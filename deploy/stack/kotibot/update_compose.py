#!/usr/bin/env python3
"""Bring the live compose file's kotibot service up to a KotiBot image tag.

The installer does not carry deploy/stack/docker-compose.yml, so this is the one place the by-hand edits live:
the image tag, the environment entries and the volume mounts the KotiBot features need. It edits only
the kotibot service, adds only what is missing, and can be run again safely.

    python3 update_compose.py /home/snx/pi-services/docker-compose.yml 78bd1c602b79
"""
import re
import sys

ENVIRONMENT = [
    ('KOTIBOT_PIVAULT_ROOT_CERT', '/opt/pivault-pki/pivault-root.crt'),
    ('KOTIBOT_SITE_SETTINGS', '/site/site-settings.json'),
    ('KOTIBOT_PIVAULT_NOTIFICATIONS', '/notifications'),
    ('KOTIBOT_PIVAULT_ADMIN_DIR', '/data/pivault-admin'),
    ('KOTIBOT_PIVAULT_CLIENTS', '/data/pivault-clients'),
    ('KOTIBOT_MEDIA_DIR', '/media'),
]
VOLUMES = [
    '/srv/pi-server/config/kotibot/pki:/opt/pivault-pki:ro',
    '/srv/pi-server/config/site:/site',
    '/srv/pi-server/config/notifications:/notifications',
    # Recordings go to the data disk, not the SD card. The folder must exist and belong to uid 1000.
    '/srv/disk3/kotibot-recordings:/media',
]


def service_range(lines):
    start = next((i for i, line in enumerate(lines) if line.rstrip() == '  kotibot:'), None)
    if start is None:
        raise SystemExit('No kotibot service found in the compose file.')
    end = next((i for i in range(start + 1, len(lines)) if re.match(r'  \S', lines[i])), len(lines))
    return start, end


def section_end(lines, start, end, name):
    """Index just after the last entry of a service key such as 'environment:' (4-space indent)."""
    head = next((i for i in range(start, end) if lines[i].rstrip() == '    ' + name + ':'), None)
    if head is None:
        raise SystemExit('The kotibot service has no ' + name + ' section.')
    index = head + 1
    while index < end and (lines[index].startswith('      ') or lines[index].startswith('    - ')):
        index += 1
    return head, index


def update(text, tag):
    if not re.fullmatch('[0-9a-f]{12}', tag):
        raise SystemExit('The image tag must be 12 hex characters.')
    lines = text.split('\n')
    start, end = service_range(lines)
    image = next(i for i in range(start, end) if lines[i].startswith('    image: pivault-kotibot:'))
    lines[image] = '    image: pivault-kotibot:' + tag
    for key, value in ENVIRONMENT:
        start, end = service_range(lines)
        head, stop = section_end(lines, start, end, 'environment')
        if not any(re.match(r'\s+' + key + ':', line) for line in lines[head:stop]):
            lines.insert(stop, '      ' + key + ': ' + value)
    for mount in VOLUMES:
        start, end = service_range(lines)
        head, stop = section_end(lines, start, end, 'volumes')
        if not any(line.strip() == '- ' + mount for line in lines[head:stop]):
            lines.insert(stop, '    - ' + mount)
    return '\n'.join(lines)


def main(argv):
    if len(argv) != 3:
        raise SystemExit(__doc__)
    path, tag = argv[1], argv[2]
    with open(path) as stream:
        original = stream.read()
    changed = update(original, tag)
    if changed != original:
        with open(path, 'w') as stream:
            stream.write(changed)
    print('compose: image ' + tag + ('' if changed != original else ' (already current)'))


if __name__ == '__main__':
    main(sys.argv)

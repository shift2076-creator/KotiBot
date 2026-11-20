#!/usr/bin/env python3
"""Turn candidates.txt (title|year|reason per line) into queue rows using Internet Archive metadata.

A candidate becomes a row only when its archive item has a Creative Commons or public-domain
license and an MP4 with a size and MD5 in the item's file list. Anything else is reported on
stderr and left out; nothing is guessed.
"""
import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ALLOWED_LICENSES = (
    'creativecommons.org/licenses/by/3.0/',
    'creativecommons.org/publicdomain/zero/',
    'creativecommons.org/publicdomain/mark/',
    'creativecommons.org/licenses/publicdomain/',
)
MAX_BYTES = 2 * 1024 ** 3
SEARCH = 'https://archive.org/advancedsearch.php?'
METADATA = 'https://archive.org/metadata/'
RECORDS = 'candidate-records.json'  # written beside the queue; read by cinema-rights.py


def slug(title, year):
    return re.sub(r'[^a-z0-9]+', '-', f'{title} {year}'.lower()).strip('-')


def search_url(title, year):
    query = f'title:("{title}") AND year:{year} AND mediatype:movies'
    return SEARCH + urllib.parse.urlencode({'q': query, 'fl[]': 'identifier', 'rows': 5, 'output': 'json'}, doseq=True)


def minutes_from(length):
    try:
        return round(float(length) / 60, 1)
    except (TypeError, ValueError):
        pass
    parts = str(length or '').split(':')
    try:
        seconds = sum(int(p) * 60 ** i for i, p in enumerate(reversed(parts)))
        return round(seconds / 60, 1)
    except ValueError:
        return 0


def pick_file(metadata):
    """Return (name, size, md5, height, minutes, license) for the largest eligible MP4, or None."""
    license_url = str(metadata.get('metadata', {}).get('licenseurl', ''))
    if not any(allowed in license_url for allowed in ALLOWED_LICENSES):
        return None
    best = None
    for item in metadata.get('files', []):
        name = item.get('name', '')
        size = int(item.get('size', 0) or 0)
        md5 = item.get('md5', '')
        if not name.lower().endswith('.mp4') or not 0 < size <= MAX_BYTES or not re.fullmatch('[0-9a-f]{32}', md5):
            continue
        if best is None or size > best[1]:
            best = (name, size, md5, int(float(item.get('height', 0) or 0)), minutes_from(item.get('length')), license_url)
    return best


def row(candidate, identifier, picked):
    title, year, reason = candidate
    name, size, md5, height, minutes, license_url = picked
    url = f'https://archive.org/download/{identifier}/{urllib.parse.quote(name)}'
    rights = f'Archive license: {license_url}'
    fields = [str(f) for f in ['film', slug(title, year), title, year, url, size, md5, '-', reason, rights, minutes, height]]
    if any('\t' in f or '\n' in f for f in fields):
        raise ValueError(f'tab or newline in {title}')
    return '\t'.join(fields)


def get_json(url):
    if not url.startswith('https://archive.org/'):
        raise ValueError('only archive.org metadata is read here')
    with urllib.request.urlopen(url, timeout=40) as response:
        return json.loads(response.read(8 * 1024 * 1024))


def dossier(candidate, identifier, metadata, picked):
    """Rights entry for one resolved film, in the shape cinema-rights.py reads beside catalogue.json."""
    title, year, reason = candidate
    license_url = picked[5]
    return {'key': slug(title, year), 'title': title, 'year': year, 'reason': reason,
            'item': f'https://archive.org/details/{identifier}', 'license': license_url,
            'creator': metadata.get('metadata', {}).get('creator', ''),
            'rights': f'Archive license: {license_url}', 'loc': '-', 'archive_metadata': metadata}


def resolve(candidate, fetch=get_json, records=None):
    """Return the queue row for the first eligible item; if records is a list, append the rights entry."""
    title, year, _ = candidate
    docs = fetch(search_url(title, year)).get('response', {}).get('docs', [])
    for doc in docs:
        identifier = doc.get('identifier', '')
        if not identifier:
            continue
        metadata = fetch(METADATA + urllib.parse.quote(identifier))
        picked = pick_file(metadata)
        if picked:
            if records is not None:
                records.append(dossier(candidate, identifier, metadata, picked))
            return row(candidate, identifier, picked)
    return None


def read_candidates(path):
    rows = []
    for line in Path(path).read_text(encoding='utf-8').splitlines():
        if not line.strip() or line.startswith('#'):
            continue
        title, year, reason = line.split('|', 2)
        rows.append((title.strip(), int(year), reason.strip()))
    return rows


def main(argv):
    if len(argv) != 3:
        print('usage: cinema-candidates.py candidates.txt queue.tsv', file=sys.stderr)
        return 2
    rows, records, misses = [], [], []
    for candidate in read_candidates(argv[1]):
        found = []
        try:
            resolved = resolve(candidate, records=found)
        except (OSError, ValueError) as error:
            resolved = None
            print(f'lookup failed: {candidate[0]} ({candidate[1]}): {error}', file=sys.stderr)
        if resolved:
            rows.append(resolved)
            records.extend(found)
        else:
            misses.append(f'{candidate[0]} ({candidate[1]})')
    print(f'{len(rows)} candidates resolved; {len(misses)} left out:', file=sys.stderr)
    for miss in misses:
        print('  ' + miss, file=sys.stderr)
    if not rows:
        # Keep the previous queue: an empty result usually means the archive was unreachable.
        return 1
    queue = Path(argv[2])
    queue.write_text(''.join(r + '\n' for r in rows), encoding='utf-8')
    # Rights entries for exactly these rows; cinema-rights.py reads them when a candidate is transferred.
    queue.with_name(RECORDS).write_text(json.dumps(records, indent=1, sort_keys=True) + '\n', encoding='utf-8')
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv))

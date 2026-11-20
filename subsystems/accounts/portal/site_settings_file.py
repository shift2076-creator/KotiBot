"""Admin switches kept in one small JSON file that KotiBot also reads and writes.

KotiBot's Settings window owns the Network page (port roles and the Internet
jobs switch). Both containers mount the same folder, so the portal's nightly
jobs, which ask the portal whether offline mode is on, see what the Admin set
in KotiBot. The file holds no secrets. A missing or unreadable file means the
defaults, and it is created by the first save.

Used only when PIVAULT_SITE_SETTINGS names the file; otherwise the database
row is used (tests, and installs without KotiBot).
"""
import json
import os
import tempfile
from pathlib import Path

ENVIRONMENT = 'PIVAULT_SITE_SETTINGS'


def path():
    value = os.environ.get(ENVIRONMENT, '').strip()
    return Path(value) if value else None


def read():
    """The stored values, or an empty dict when the file is missing or not a JSON object."""
    target = path()
    if target is None:
        return {}
    try:
        value = json.loads(target.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def write(changes):
    """Merge ``changes`` into the file and replace it atomically."""
    target = path()
    merged = read()
    merged.update(changes)
    handle, name = tempfile.mkstemp(dir=target.parent, prefix='.site-settings-')
    try:
        with os.fdopen(handle, 'w', encoding='utf-8') as out:
            json.dump(merged, out, indent=2, sort_keys=True)
            out.write('\n')
        os.chmod(name, 0o644)
        os.replace(name, target)
    except BaseException:
        try:
            os.unlink(name)
        except OSError:
            pass
        raise

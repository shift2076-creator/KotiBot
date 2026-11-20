"""The portal's side of the network host helper (subsystems/network/network_helper.py).

The portal never changes the network. It drops a request file, and later a confirm file, into a folder shared with the root-owned
helper, and reads the helper's state and result files back. When PIVAULT_NETWORK_DIR is not set (today, on every install), nothing
here does anything and the Network page only records the choice.
"""
import json
import os
from pathlib import Path


def directory():
    value = os.environ.get('PIVAULT_NETWORK_DIR')
    return Path(value) if value else None


def enabled():
    return directory() is not None


def _write(name, data):
    path = directory() / name
    tmp = path.with_name(name + '.new')
    tmp.write_text(data)
    os.replace(tmp, path)


def request(ethernet, wifi):
    _write('request.json', json.dumps({'ethernet': ethernet, 'wifi': wifi}))


def confirm():
    _write('confirm', '')


def _read(name):
    try:
        return json.loads((directory() / name).read_text())
    except (OSError, ValueError):
        return None


def status(now):
    """{'waiting': bool, 'seconds_left': int, 'result': dict or None}. Safe to call when the helper never ran."""
    state = _read('state.json') or {}
    change = state.get('change')
    waiting = bool(change) and not change.get('confirmed')
    return {
        'waiting': waiting,
        'seconds_left': max(0, int(change['deadline'] - now)) if waiting else 0,
        'result': _read('result.json'),
        'current': tuple(state['current']) if state.get('current') else None,
    }

import atexit
import copy
import json
import logging
import os
import time
from pathlib import Path
from threading import Event, Lock, Thread

def _json_flush_interval():
    try:
        interval = float(os.environ.get('KOTIBOT_JSON_FLUSH_SECONDS', '30') or 30)
    except (TypeError, ValueError):
        interval = 30.0

    return max(1.0, interval)

JSON_FLUSH_INTERVAL_SECONDS = _json_flush_interval()

_LOGGER = logging.getLogger('kotibot.persistence')
_PENDING_WRITES = {}
_FLUSHING_WRITES = {}
_PENDING_LOCK = Lock()
_FLUSH_LOCK = Lock()
_WRITER_LOCK = Lock()
_WRITER_STOP = Event()
_WRITER_SHUTTING_DOWN = Event()
_WRITER_THREAD = None
_MISSING = object()

class JsonStateReadError(Exception):
    reason = 'unreadable'

    def __init__(self, path):
        self.filename = Path(path).name or 'state.json'
        super().__init__(
            f'JSON state {self.reason}: {self.filename}'
        )

class JsonStateMissingError(JsonStateReadError):
    reason = 'missing'

class JsonStateInvalidError(JsonStateReadError):
    reason = 'invalid'

class JsonStateUnreadableError(JsonStateReadError):
    reason = 'unreadable'

def _log_json_read_error(error):
    _LOGGER.warning(
        'JSON state read failed: file=%s reason=%s',
        error.filename,
        error.reason,
    )

def _normalized_path(path):
    return Path(path).resolve()

def _write_json_atomic_now(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(data, indent=2, sort_keys=True) + '\n'

    try:
        if path.read_text(encoding='utf-8') == encoded:
            return False
    except (FileNotFoundError, OSError, UnicodeError):
        pass

    tmp_path = path.with_name(
        f".{path.name}.{os.getpid()}.{id(data)}.{time.time_ns()}.tmp"
    )

    try:
        with tmp_path.open('w', encoding='utf-8') as f:
            os.fchmod(f.fileno(), 0o600)
            f.write(encoded)
            f.flush()
            os.fsync(f.fileno())

        tmp_path.replace(path)
        os.chmod(path, 0o600)
        return True
    finally:
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except OSError:
            pass

def read_json(path):
    try:
        path = _normalized_path(path)
    except OSError:
        error = JsonStateUnreadableError(path)
        _log_json_read_error(error)
        raise error from None

    with _PENDING_LOCK:
        if path in _PENDING_WRITES:
            data = _PENDING_WRITES[path]
        elif path in _FLUSHING_WRITES:
            data = _FLUSHING_WRITES[path]
        else:
            data = _MISSING

    if data is not _MISSING:
        return copy.deepcopy(data)

    try:
        encoded = path.read_text(encoding='utf-8')
    except FileNotFoundError:
        raise JsonStateMissingError(path) from None
    except UnicodeError:
        error = JsonStateInvalidError(path)
        _log_json_read_error(error)
        raise error from None
    except OSError:
        error = JsonStateUnreadableError(path)
        _log_json_read_error(error)
        raise error from None

    try:
        data = json.loads(encoded)
    except (json.JSONDecodeError, RecursionError):
        error = JsonStateInvalidError(path)
        _log_json_read_error(error)
        raise error from None

    if not isinstance(data, dict):
        error = JsonStateInvalidError(path)
        _log_json_read_error(error)
        raise error from None

    return data

def read_json_object(path):
    return read_json(path)

def json_exists(path):
    path = _normalized_path(path)

    with _PENDING_LOCK:
        if path in _PENDING_WRITES or path in _FLUSHING_WRITES:
            return True

    return path.exists()

def write_json_atomic(path, data):
    path = _normalized_path(path)
    snapshot = copy.deepcopy(data)

    with _PENDING_LOCK:
        if not _WRITER_SHUTTING_DOWN.is_set():
            _PENDING_WRITES[path] = snapshot
            queued = True
        else:
            queued = False

    if queued:
        start_json_writer()
        return

    with _FLUSH_LOCK:
        with _PENDING_LOCK:
            _PENDING_WRITES.pop(path, None)
            _FLUSHING_WRITES.pop(path, None)

        _write_json_atomic_now(path, snapshot)

def flush_json_writes():
    with _FLUSH_LOCK:
        with _PENDING_LOCK:
            pending = dict(_PENDING_WRITES)
            _PENDING_WRITES.clear()
            _FLUSHING_WRITES.update(pending)

        failed = {}
        written = 0

        for path, data in pending.items():
            try:
                if _write_json_atomic_now(path, data):
                    written += 1
            except Exception:
                failed[path] = data
                _LOGGER.exception('JSON state flush failed: %s', path)
            finally:
                with _PENDING_LOCK:
                    _FLUSHING_WRITES.pop(path, None)

        if failed:
            with _PENDING_LOCK:
                for path, data in failed.items():
                    _PENDING_WRITES.setdefault(path, data)

        return written

def _json_writer_loop():
    while not _WRITER_STOP.wait(JSON_FLUSH_INTERVAL_SECONDS):
        flush_json_writes()

def start_json_writer():
    global _WRITER_THREAD

    with _WRITER_LOCK:
        if _WRITER_SHUTTING_DOWN.is_set():
            return

        if _WRITER_THREAD is not None and _WRITER_THREAD.is_alive():
            return

        _WRITER_STOP.clear()
        _WRITER_THREAD = Thread(
            target=_json_writer_loop,
            name='kotibot-json-writer',
            daemon=True,
        )
        _WRITER_THREAD.start()

def stop_json_writer():
    global _WRITER_THREAD

    with _PENDING_LOCK:
        _WRITER_SHUTTING_DOWN.set()

    with _WRITER_LOCK:
        thread = _WRITER_THREAD
        _WRITER_STOP.set()

    if thread is not None and thread.is_alive():
        thread.join(timeout=5)

    flush_json_writes()

    with _WRITER_LOCK:
        if _WRITER_THREAD is thread:
            _WRITER_THREAD = None

atexit.register(stop_json_writer)
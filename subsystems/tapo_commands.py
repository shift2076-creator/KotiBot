"""Per-application Tapo command ordering; never hold the shared state lock to wait."""
from collections import deque
from contextlib import contextmanager
from threading import Condition, get_ident


class TapoCommandQueue:
    def __init__(self, timeout=30.0, limit=32):
        self.timeout = timeout
        self.limit = limit
        self._condition = Condition()
        self._entries = {}

    @staticmethod
    def key(device_id):
        return str(device_id).strip().lower().removeprefix('tapo:').replace(':', '_').replace('-', '_')

    def _entry(self, key):
        return self._entries.setdefault(key, dict(queue=deque(), owner=None, version=0, observers=0))

    def _prune(self, key, entry):
        if not entry['queue'] and entry['owner'] is None and not entry['observers']:
            self._entries.pop(key, None)

    def reserve(self, device_id, *, timeout=None):
        """Reserve before handing work to an executor, so queued batches cannot overtake."""
        key = self.key(device_id)
        with self._condition:
            entry = self._entry(key)
            if len(entry['queue']) >= self.limit:
                raise TimeoutError('Tapo device command queue is full')
            ticket = object()
            entry['queue'].append(ticket)
            entry['version'] += 1
        return _Reservation(self, key, entry, ticket, self.timeout if timeout is None else timeout)

    @contextmanager
    def hold(self, device_id, *, timeout=None):
        key = self.key(device_id)
        with self._condition:
            entry = self._entries.get(key)
            nested = entry is not None and entry['owner'] == get_ident()
        if nested:
            # Lighting recovery is part of the command that already owns this slot.
            yield
        else:
            with self.reserve(device_id, timeout=timeout):
                yield

    @contextmanager
    def observe(self, device_ids):
        """Retain only in-flight read versions, including command ABA transitions."""
        with self._condition:
            observed = {}
            for key in {self.key(value) for value in device_ids}:
                entry = self._entry(key)
                entry['observers'] += 1
                observed[key] = (entry, entry['version'], bool(entry['queue']))

        def unchanged(device_id):
            with self._condition:
                record = observed.get(self.key(device_id))
                if record is None:
                    return False
                entry, version, was_busy = record
                return not was_busy and not entry['queue'] and entry['version'] == version

        try:
            yield unchanged
        finally:
            with self._condition:
                for key, (entry, _, _) in observed.items():
                    entry['observers'] -= 1
                    self._prune(key, entry)


class _Reservation:
    def __init__(self, queue, key, entry, ticket, timeout):
        self.queue, self.key, self.entry, self.ticket = queue, key, entry, ticket
        self.entered = False
        self.timeout = timeout

    def __enter__(self):
        queue, entry = self.queue, self.entry
        with queue._condition:
            try:
                ready = queue._condition.wait_for(
                    lambda: entry['queue'] and entry['queue'][0] is self.ticket
                    and entry['owner'] is None,
                    timeout=self.timeout,
                )
                if not ready:
                    raise TimeoutError('Timed out waiting for this Tapo device')
                entry['owner'] = get_ident()
                self.entered = True
            except BaseException:
                self.cancel()
                raise
        return self

    def cancel(self):
        with self.queue._condition:
            if self.ticket in self.entry['queue']:
                self.entry['queue'].remove(self.ticket)
                if self.entered:
                    self.entry['owner'] = None
                self.entry['version'] += 1
                self.queue._prune(self.key, self.entry)
                self.queue._condition.notify_all()

    def __exit__(self, *_):
        self.cancel()


def tapo_commands_for_app(app):
    # Route registration is single-threaded; both integrations share this owner.
    return app.extensions.setdefault('kotibot.tapo_commands', TapoCommandQueue())

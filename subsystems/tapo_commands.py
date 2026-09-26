"""Per-application Tapo command ordering; never hold the shared state lock to wait."""
import asyncio
from concurrent.futures import Future
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
        return self._entries.setdefault(key, dict(queue=deque(), owner=None, version=0, observers=0, async_waiters={}))

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
    def try_hold(self, device_id):
        """Optional recovery never queues behind user commands."""
        key = self.key(device_id)
        with self._condition:
            entry = self._entries.get(key)
            nested = entry is not None and entry['owner'] == get_ident()
            busy = entry is not None and bool(entry['queue']) and not nested
            reservation = None if busy or nested else self.reserve(device_id)
        if busy:
            yield False
        elif nested:
            yield True
        else:
            with reservation:
                yield True

    def has_waiters(self, device_id):
        """Let the current background owner yield between network actions."""
        with self._condition:
            entry = self._entries.get(self.key(device_id))
            return bool(entry and len(entry['queue']) > (1 if entry['owner'] is not None else 0))

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

    async def __aenter__(self):
        # Waiting Scenes use futures, never parked executor threads or polling.
        queue, entry = self.queue, self.entry
        with queue._condition:
            if entry['queue'][0] is self.ticket and entry['owner'] is None:
                entry['owner'] = self
                self.entered = True
                return self
            ready = Future()
            entry['async_waiters'][self.ticket] = ready
        try:
            await asyncio.wait_for(asyncio.wrap_future(ready), timeout=self.timeout)
            with queue._condition:
                entry['async_waiters'].pop(self.ticket, None)
                entry['owner'] = self
                self.entered = True
            return self
        except BaseException:
            self.cancel()
            raise

    async def __aexit__(self, *_):
        self.cancel()

    def cancel(self):
        with self.queue._condition:
            if self.ticket in self.entry['queue']:
                self.entry['queue'].remove(self.ticket)
                waiter = self.entry['async_waiters'].pop(self.ticket, None)
                if waiter is not None:
                    waiter.cancel()
                if self.entered:
                    self.entry['owner'] = None
                self.entry['version'] += 1
                self.queue._prune(self.key, self.entry)
                self.queue._condition.notify_all()
                if self.entry['queue'] and self.entry['owner'] is None:
                    following = self.entry['async_waiters'].get(self.entry['queue'][0])
                    if following is not None and not following.done():
                        following.set_result(None)

    def __exit__(self, *_):
        self.cancel()


def tapo_commands_for_app(app):
    # Route registration is single-threaded; both integrations share this owner.
    return app.extensions.setdefault('kotibot.tapo_commands', TapoCommandQueue())

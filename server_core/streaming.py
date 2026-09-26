"""Bound long-lived status requests independently of the state lock."""
import os
from threading import BoundedSemaphore, Lock


class StatusStreamSlots:
    def __init__(self, limit=None):
        if limit is None:
            limit = os.environ.get('KOTIBOT_STATUS_STREAM_LIMIT', '2')
        try:
            value = int(limit)
        except (TypeError, ValueError):
            raise ValueError('KOTIBOT_STATUS_STREAM_LIMIT must be a positive integer') from None
        if isinstance(limit, bool) or str(value) != str(limit) or value < 1:
            raise ValueError('KOTIBOT_STATUS_STREAM_LIMIT must be a positive integer')
        self._slots = BoundedSemaphore(value)

    def acquire(self):
        """Return an idempotent release callback, or None without waiting."""
        if not self._slots.acquire(blocking=False):
            return None
        lock = Lock()
        released = False

        def release():
            nonlocal released
            with lock:
                if not released:
                    released = True
                    self._slots.release()

        return release

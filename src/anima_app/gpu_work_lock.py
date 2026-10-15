"""Serialize GPU work and release an idle encoder before another GPU task."""
import threading


class GPUWorkLock:
    def __init__(self):
        self._lock = threading.Lock()
        self._idle = {}

    def register_idle(self, owner, release):
        self._idle[owner] = release

    def acquire(self, blocking=True, timeout=-1, *, owner=None):
        acquired = self._lock.acquire(blocking, timeout)
        if acquired:
            try:
                for resource, release in tuple(self._idle.items()):
                    if resource is not owner:
                        release()
            except BaseException:
                self._lock.release()
                raise
        return acquired

    def release(self):
        self._lock.release()

    def locked(self):
        return self._lock.locked()

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, *args):
        self.release()

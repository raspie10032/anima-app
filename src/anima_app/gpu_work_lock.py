"""Serialize GPU work and release an idle encoder before another GPU task."""
import threading
from contextlib import contextmanager

from anima_app.runtime.model_cache import LOCAL_RUNTIME_OWNER, clear as clear_local_models


class GPUWorkLock:
    def __init__(self):
        self._lock = threading.Lock()
        self._idle = {LOCAL_RUNTIME_OWNER: clear_local_models}

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

    @contextmanager
    def for_owner(self, owner):
        self.acquire(owner=owner)
        try:
            yield self
        finally:
            self.release()

    def __enter__(self):
        self.acquire(owner=LOCAL_RUNTIME_OWNER)
        return self

    def __exit__(self, *args):
        self.release()

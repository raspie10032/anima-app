"""Bounded worker reuse around the unchanged, fingerprinted numerical worker."""
from contextlib import contextmanager
import threading

from anima_app.library_vrs import VRSAdapter


class CachedVRSAdapter(VRSAdapter):
    def __init__(self, model_root, idle_seconds=60):
        super().__init__(model_root)
        self._persistent = True
        self._lock = threading.RLock()
        self._timer = None
        self._worker_contract = None
        self.idle_seconds = idle_seconds

    def _stop_timer(self):
        if self._timer:
            self._timer.cancel()
            self._timer = None

    def _close(self):
        self._stop_timer()
        if self._worker_state:
            self._finish(self._worker_state)
        self._worker_state = None
        self._worker_contract = None

    def close(self):
        with self._lock:
            self._close()

    def _expire(self, timer):
        with self._lock:
            if self._timer is timer:
                self._close()

    @contextmanager
    def session(self):
        # Indexing holds the same lock through its committed batches.
        with self._lock:
            self._stop_timer()
            try:
                yield
            finally:
                self._close()

    def encode(self, paths, scratch, cancelled=lambda: False):
        with self._lock:
            self._stop_timer()
            contract = self.contract
            if (self._worker_contract != contract or
                    self._worker_state and self._worker_state[0].poll() is not None):
                self._close()
            try:
                result = super().encode(paths, scratch, cancelled)
                self._worker_contract = contract
            except BaseException:
                self._close()
                raise
            timer = threading.Timer(self.idle_seconds, lambda: self._expire(timer))
            timer.daemon = True
            self._timer = timer
            timer.start()
            return result

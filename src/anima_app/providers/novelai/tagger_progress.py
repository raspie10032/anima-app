# SPDX-License-Identifier: GPL-3.0-only
"""Request-local Hub HTTP/Xet byte progress, adapted from RS NAI 2.4.6."""

import time

from anima_app.providers.novelai.client import _check_cancelled


class TaggerProgress:
    def __init__(self, callback=None, cancelled=lambda: False):
        self.callback = callback
        self.cancelled = cancelled
        self._last_update = 0

    def report(self, text, fraction=0, *, force=False, failed=False, **details):
        if not failed:
            _check_cancelled(self.cancelled)
        now = time.monotonic()
        if not force and now - self._last_update < .2:
            return
        self._last_update = now
        if self.callback:
            self.callback({"text": text, "fraction": max(0, min(1, fraction)), "failed": failed, **details})

    def download_bar(self, filename):
        from tqdm.auto import tqdm

        reporter = self

        class DownloadBar(tqdm):
            def __init__(self, *args, **kwargs):
                kwargs.pop("name", None)
                kwargs["disable"] = True
                super().__init__(*args, **kwargs)
                self._transferred = self.n
                self._report(force=True)

            def _report(self, force=False):
                received = max(self.n, self._transferred)
                mib = received / 1024**2
                fraction = min(1, received / self.total) if self.total else 0
                size = f"{mib:.1f} / {self.total / 1024**2:.1f} MiB" if self.total else f"{mib:.1f} MiB"
                reporter.report(f"Downloading {filename}: {fraction:.0%} ({size})", min(fraction, .999),
                                force=force, filename=filename, received_bytes=received, total_bytes=self.total)

            def update(self, n=1):
                self.n += n
                self._report()

            def update_transfer(self, n):
                self._transferred += n
                self._report()

            def set_transfer_postfix_str(self, *args, **kwargs):
                pass

        return DownloadBar

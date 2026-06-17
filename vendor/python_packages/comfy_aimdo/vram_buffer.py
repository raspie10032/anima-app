"""VRAM buffer fallback for the GemmAnima no-aimdo shim."""

from __future__ import annotations

import torch


class VRAMBuffer:
    def __init__(self, max_size, device):
        self.max_size = int(max_size)
        self.device = torch.device("cuda", int(device)) if device is not None and torch.cuda.is_available() else torch.device("cpu")
        self._buffer = None

    def size(self):
        return 0 if self._buffer is None else int(self._buffer.numel())

    def get(self, size, offset=0):
        size = int(size)
        required = size + int(offset)
        if self._buffer is None or self._buffer.numel() < required:
            self._buffer = torch.empty((required,), dtype=torch.uint8, device=self.device)
        return self._buffer[int(offset):int(offset) + size]

"""Pinned host-buffer fallback for the GemmAnima no-aimdo shim."""

from __future__ import annotations

import torch


class HostBuffer:
    def __init__(self, size):
        self.size = int(size)
        self.tensor = torch.empty((self.size,), dtype=torch.uint8, device="cpu")

    def get_raw_address(self):
        return int(self.tensor.data_ptr())

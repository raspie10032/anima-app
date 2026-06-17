"""File mmap fallback for the GemmAnima no-aimdo shim."""

from __future__ import annotations

import ctypes


class ModelMMAP:
    def __init__(self, filepath):
        with open(filepath, "rb") as handle:
            data = handle.read()
        self._buffer = ctypes.create_string_buffer(data)

    def get(self):
        return ctypes.addressof(self._buffer)

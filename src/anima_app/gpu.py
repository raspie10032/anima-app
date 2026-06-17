from __future__ import annotations

import os


def ensure_default_cuda_visible_devices(default: str = "0") -> str:
    if not os.environ.get("CUDA_VISIBLE_DEVICES"):
        os.environ["CUDA_VISIBLE_DEVICES"] = default
    return os.environ["CUDA_VISIBLE_DEVICES"]


def configure_default_cuda_device(default: str = "0") -> str:
    return ensure_default_cuda_visible_devices(default)

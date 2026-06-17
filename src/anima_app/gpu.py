from __future__ import annotations

import os

APP_CUDA_VISIBLE_DEVICES_ENV = "ANIMA_APP_CUDA_VISIBLE_DEVICES"
CUDA_VISIBLE_DEVICES_ENV = "CUDA_VISIBLE_DEVICES"


def ensure_default_cuda_visible_devices(default: str = "0") -> str:
    app_configured_device = os.environ.get(APP_CUDA_VISIBLE_DEVICES_ENV)
    if app_configured_device:
        os.environ[CUDA_VISIBLE_DEVICES_ENV] = app_configured_device
    elif not os.environ.get(CUDA_VISIBLE_DEVICES_ENV):
        os.environ[CUDA_VISIBLE_DEVICES_ENV] = default
    return os.environ[CUDA_VISIBLE_DEVICES_ENV]


def configure_default_cuda_device(default: str = "0") -> str:
    return ensure_default_cuda_visible_devices(default)

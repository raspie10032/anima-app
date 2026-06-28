from __future__ import annotations

import json
import os
import time
from dataclasses import replace
from typing import Any, Callable

from anima_app.config import AppPaths
from anima_app.gpu import CUDA_VISIBLE_DEVICES_ENV
from anima_app.requests import LOW_VRAM_HIGHRES_PROFILE, T2IRequest


RUNTIME_PROFILE_CACHE_VERSION = 1
BALANCED_PROFILE = "balanced"
AUTO_PROFILE = "auto"
LOW_VRAM_HIGHRES_MAX_VRAM_MB = 8704

RuntimeProbe = Callable[[], dict[str, object]]


def resolve_auto_memory_profile(
    request: T2IRequest,
    *,
    paths: AppPaths,
    probe: RuntimeProbe | None = None,
) -> T2IRequest:
    if request.memory_profile != AUTO_PROFILE:
        return request
    decision = cached_runtime_profile_decision(paths, probe=probe)
    return replace(request, memory_profile=str(decision["profile"]))


def cached_runtime_profile_decision(
    paths: AppPaths,
    *,
    probe: RuntimeProbe | None = None,
) -> dict[str, object]:
    cached = _read_runtime_profile_cache(paths)
    cache_key = _runtime_cache_key()
    if _cache_is_usable(cached, cache_key):
        return cached["decision"]  # type: ignore[index]

    environment = (probe or probe_runtime_environment)()
    decision = {
        "profile": recommend_memory_profile(environment),
        "reason": _recommendation_reason(environment),
        "environment": environment,
        "cache_key": cache_key,
        "created_at": time.time(),
    }
    _write_runtime_profile_cache(paths, decision)
    return decision


def probe_runtime_environment() -> dict[str, object]:
    environment: dict[str, object] = {
        "cuda_visible_devices": os.environ.get(CUDA_VISIBLE_DEVICES_ENV, ""),
        "cuda_available": False,
        "gpu_name": "",
        "total_vram_mb": None,
        "system_ram_mb": _system_ram_mb(),
    }
    try:
        import torch

        if torch.cuda.is_available():
            device = torch.cuda.current_device()
            properties = torch.cuda.get_device_properties(device)
            environment.update(
                {
                    "cuda_available": True,
                    "gpu_name": properties.name,
                    "total_vram_mb": round(properties.total_memory / (1024 * 1024)),
                }
            )
    except Exception as exc:
        environment["probe_error"] = str(exc)
    return environment


def recommend_memory_profile(environment: dict[str, object]) -> str:
    total_vram_mb = _optional_int(environment.get("total_vram_mb"))
    if total_vram_mb is None:
        return LOW_VRAM_HIGHRES_PROFILE
    if total_vram_mb <= LOW_VRAM_HIGHRES_MAX_VRAM_MB:
        return LOW_VRAM_HIGHRES_PROFILE
    return BALANCED_PROFILE


def _recommendation_reason(environment: dict[str, object]) -> str:
    total_vram_mb = _optional_int(environment.get("total_vram_mb"))
    if total_vram_mb is None:
        return "vram_unknown"
    if total_vram_mb <= LOW_VRAM_HIGHRES_MAX_VRAM_MB:
        return "vram_at_or_below_8gb_class"
    return "vram_above_8gb_class"


def _system_ram_mb() -> int | None:
    try:
        import psutil

        return round(psutil.virtual_memory().total / (1024 * 1024))
    except Exception:
        return None


def _runtime_cache_key() -> dict[str, object]:
    return {
        "version": RUNTIME_PROFILE_CACHE_VERSION,
        "cuda_visible_devices": os.environ.get(CUDA_VISIBLE_DEVICES_ENV, ""),
    }


def _read_runtime_profile_cache(paths: AppPaths) -> dict[str, Any] | None:
    path = paths.runtime_profile_cache_path
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _write_runtime_profile_cache(paths: AppPaths, decision: dict[str, object]) -> None:
    path = paths.runtime_profile_cache_path
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": RUNTIME_PROFILE_CACHE_VERSION,
        "cache_key": _runtime_cache_key(),
        "decision": decision,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _cache_is_usable(payload: dict[str, Any] | None, cache_key: dict[str, object]) -> bool:
    if not payload:
        return False
    if payload.get("version") != RUNTIME_PROFILE_CACHE_VERSION:
        return False
    if payload.get("cache_key") != cache_key:
        return False
    decision = payload.get("decision")
    return isinstance(decision, dict) and decision.get("profile") in {BALANCED_PROFILE, LOW_VRAM_HIGHRES_PROFILE}


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None

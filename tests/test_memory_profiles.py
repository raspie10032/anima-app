import json

from anima_app.config import AppPaths
from anima_app.memory_profiles import cached_runtime_profile_decision, resolve_auto_memory_profile
from anima_app.requests import T2IRequest


def test_auto_memory_profile_uses_low_vram_highres_for_8gb_class_gpu(tmp_path):
    paths = AppPaths(project_root=tmp_path)
    request = T2IRequest(prompt="portrait")

    resolved = resolve_auto_memory_profile(
        request,
        paths=paths,
        probe=lambda: {
            "cuda_available": True,
            "gpu_name": "8GB GPU",
            "total_vram_mb": 8192,
            "system_ram_mb": 16384,
        },
    )

    assert resolved.memory_profile == "low_vram_highres"
    assert resolved.upscale.enabled is True
    assert resolved.upscale.tiled is True
    assert resolved.upscale.steps == 10
    assert resolved.vae_decode.mode == "tiled"


def test_auto_memory_profile_uses_balanced_for_larger_gpu(tmp_path):
    paths = AppPaths(project_root=tmp_path)
    request = T2IRequest(prompt="portrait")

    resolved = resolve_auto_memory_profile(
        request,
        paths=paths,
        probe=lambda: {
            "cuda_available": True,
            "gpu_name": "large GPU",
            "total_vram_mb": 16384,
            "system_ram_mb": 32768,
        },
    )

    assert resolved.memory_profile == "balanced"
    assert resolved.upscale.enabled is False
    assert resolved.vae_decode.mode == "auto"


def test_runtime_profile_decision_is_cached(tmp_path):
    paths = AppPaths(project_root=tmp_path)
    calls = {"count": 0}

    def probe():
        calls["count"] += 1
        return {"total_vram_mb": 8192, "cuda_available": True}

    first = cached_runtime_profile_decision(paths, probe=probe)
    second = cached_runtime_profile_decision(paths, probe=probe)
    cached_payload = json.loads(paths.runtime_profile_cache_path.read_text(encoding="utf-8"))

    assert calls["count"] == 1
    assert first["profile"] == "low_vram_highres"
    assert second["profile"] == "low_vram_highres"
    assert cached_payload["decision"]["profile"] == "low_vram_highres"

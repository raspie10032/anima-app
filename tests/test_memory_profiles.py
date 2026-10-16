import json
from dataclasses import replace

import pytest

from anima_app.config import AppPaths
from anima_app.memory_profiles import cached_runtime_profile_decision, resolve_auto_memory_profile
from anima_app.requests import FaceDetailerSettings, I2ISettings, T2IRequest


def test_auto_memory_profile_tunes_memory_without_enabling_upscale(tmp_path):
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

    assert resolved.memory_profile == "low_vram"
    assert resolved.upscale.enabled is False
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


@pytest.mark.parametrize("total_vram_mb", [None, 8192])
@pytest.mark.parametrize("memory_profile", ["auto", "low_vram_highres"])
def test_detail_only_keeps_its_operation_with_low_memory_profile(
    tmp_path, total_vram_mb, memory_profile
):
    request = T2IRequest(
        prompt="portrait", memory_profile=memory_profile, operation="detail",
        i2i=I2ISettings(enabled=True, image_path="inputs/references/source.png", denoise=0),
        face_detailer=FaceDetailerSettings(enabled=True),
    )
    resolved = resolve_auto_memory_profile(
        request, paths=AppPaths(project_root=tmp_path),
        probe=lambda: {"cuda_available": total_vram_mb is not None, "total_vram_mb": total_vram_mb},
    )

    assert resolved.memory_profile == ("low_vram" if memory_profile == "auto" else memory_profile)
    assert resolved.face_detailer.enabled is True
    assert resolved.upscale.enabled is False
    assert resolved.vae_decode.mode == "tiled"
    assert (resolved.width, resolved.height) == (request.width, request.height)
    # Prompt routing and wildcard expansion reconstruct the request downstream.
    assert replace(resolved, prompt="updated portrait").operation == "detail"


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
    assert first["profile"] == "low_vram"
    assert second["profile"] == "low_vram"
    assert cached_payload["decision"]["profile"] == "low_vram"


@pytest.mark.parametrize("vram", [None, 8192, 16384])
@pytest.mark.parametrize("enabled", [False, True])
def test_auto_preserves_requested_work_and_survives_reconstruction(tmp_path, vram, enabled):
    from anima_app.requests import UpscaleSettings
    request = T2IRequest(prompt="portrait", width=1024, height=1024,
                         upscale=UpscaleSettings(enabled=enabled, steps=17, scale=1.25))
    resolved = resolve_auto_memory_profile(request, paths=AppPaths(tmp_path), probe=lambda: {"total_vram_mb": vram})
    resolved = replace(resolved, prompt="new portrait")
    assert (resolved.width, resolved.height, resolved.steps) == (1024, 1024, request.steps)
    assert (resolved.upscale.enabled, resolved.upscale.steps, resolved.upscale.scale) == (enabled, 17, 1.25)

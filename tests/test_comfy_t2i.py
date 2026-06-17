import sys
from pathlib import Path
from types import ModuleType

import torch
from PIL import Image

from anima_app.config import AppPaths
from anima_app.requests import FaceDetailerSettings, I2ISettings, T2ILoraConfig, T2IRequest, UpscaleSettings, VaeDecodeSettings
from anima_app.runtime.comfy_t2i import (
    _build_renderer_stages,
    _decode_samples,
    _load_image_tensor,
    _make_initial_latent,
    _resolve_i2i_image_path,
    _upscale_latent_samples,
    default_model_paths,
    model_paths_for_request,
)


def test_default_model_paths_use_project_local_copied_assets(tmp_path):
    paths = AppPaths(project_root=tmp_path)

    model_paths = default_model_paths(paths)

    assert model_paths.diffusion_model == paths.model_root / "diffusion_models" / "anima-base-v1.0.safetensors"
    assert model_paths.text_encoder == paths.model_root / "text_encoders" / "qwen_3_06b_base.safetensors"
    assert model_paths.vae == paths.model_root / "vae" / "qwen_image_vae.safetensors"
    assert not str(model_paths.diffusion_model).startswith(r"E:\ComfyUI_sage")


def test_model_paths_for_request_uses_selected_diffusion_checkpoint(tmp_path):
    paths = AppPaths(project_root=tmp_path)
    request = T2IRequest(prompt="alternate", checkpoint="variants/anima-alt.safetensors")

    model_paths = model_paths_for_request(request, paths)

    assert model_paths.diffusion_model == paths.model_root / "diffusion_models" / "variants" / "anima-alt.safetensors"
    assert model_paths.text_encoder == paths.model_root / "text_encoders" / "qwen_3_06b_base.safetensors"
    assert model_paths.vae == paths.model_root / "vae" / "qwen_image_vae.safetensors"


def test_i2i_image_path_resolves_project_relative_only(tmp_path):
    paths = AppPaths(project_root=tmp_path)
    image_path = tmp_path / "inputs" / "source.png"
    image_path.parent.mkdir(parents=True)
    image_path.write_bytes(b"png")

    assert _resolve_i2i_image_path("inputs/source.png", paths) == image_path


def test_load_image_tensor_uses_comfy_image_layout(tmp_path):
    image_path = tmp_path / "source.png"
    Image.new("RGB", (32, 48), color=(255, 128, 0)).save(image_path)

    tensor = _load_image_tensor(image_path, width=32, height=48)

    assert tuple(tensor.shape) == (1, 48, 32, 3)
    assert tensor.dtype == torch.float32
    assert float(tensor.max()) <= 1.0


def test_make_initial_latent_encodes_i2i_source(tmp_path):
    paths = AppPaths(project_root=tmp_path)
    image_path = tmp_path / "source.png"
    Image.new("RGB", (16, 16), color=(0, 128, 255)).save(image_path)
    seen = {}

    class FakeVAE:
        def encode(self, pixels):
            seen["shape"] = tuple(pixels.shape)
            return torch.zeros((1, 16, 2, 2))

    request = T2IRequest(
        prompt="i2i",
        width=16,
        height=16,
        i2i=I2ISettings(enabled=True, image_path="source.png", denoise=0.42),
    )

    latent, denoise = _make_initial_latent(request, FakeVAE(), paths)

    assert seen["shape"] == (1, 16, 16, 3)
    assert tuple(latent["samples"].shape) == (1, 16, 2, 2)
    assert denoise == 0.42


def test_upscale_latent_samples_uses_scaled_latent_dimensions(monkeypatch):
    fake_comfy = ModuleType("comfy")
    fake_utils = ModuleType("comfy.utils")
    calls = {}

    def fake_common_upscale(samples, width, height, method, crop):
        calls.update(width=width, height=height, method=method, crop=crop)
        return torch.zeros((1, 16, height, width))

    fake_utils.common_upscale = fake_common_upscale
    fake_comfy.utils = fake_utils
    monkeypatch.setitem(sys.modules, "comfy", fake_comfy)
    monkeypatch.setitem(sys.modules, "comfy.utils", fake_utils)

    result = _upscale_latent_samples(
        {"samples": torch.zeros((1, 16, 8, 10))},
        scale=1.5,
        method="bicubic",
        tiled=False,
        tile_size=64,
        overlap=8,
    )

    assert calls == {"width": 15, "height": 12, "method": "bicubic", "crop": "disabled"}
    assert tuple(result["samples"].shape) == (1, 16, 12, 15)


def test_tiled_upscale_latent_samples_processes_overlapping_tiles(monkeypatch):
    fake_comfy = ModuleType("comfy")
    fake_utils = ModuleType("comfy.utils")
    calls = []

    def fake_common_upscale(samples, width, height, method, crop):
        calls.append({"shape": tuple(samples.shape), "width": width, "height": height, "method": method, "crop": crop})
        return torch.ones((samples.shape[0], samples.shape[1], height, width))

    fake_utils.common_upscale = fake_common_upscale
    fake_comfy.utils = fake_utils
    monkeypatch.setitem(sys.modules, "comfy", fake_comfy)
    monkeypatch.setitem(sys.modules, "comfy.utils", fake_utils)

    result = _upscale_latent_samples(
        {"samples": torch.zeros((1, 2, 6, 6))},
        scale=2.0,
        method="bicubic",
        tiled=True,
        tile_size=4,
        overlap=2,
    )

    assert tuple(result["samples"].shape) == (1, 2, 12, 12)
    assert len(calls) == 4
    assert {call["crop"] for call in calls} == {"disabled"}
    assert {call["method"] for call in calls} == {"bicubic"}


def test_decode_samples_honors_tiled_vae_modes():
    calls = []

    class FakeVAE:
        def decode_tiled(self, samples, *, tile_x, tile_y, overlap):
            calls.append(("tiled", tile_x, tile_y, overlap))
            return samples + 1

        def decode(self, samples):
            calls.append(("standard",))
            return samples + 2

    samples = torch.zeros((1, 1, 2, 2))

    decoded, method = _decode_samples(FakeVAE(), samples, VaeDecodeSettings(mode="auto", tile_size=96, overlap=16))
    assert method == "tiled"
    assert float(decoded.max()) == 1.0
    decoded, method = _decode_samples(FakeVAE(), samples, VaeDecodeSettings(mode="standard", tile_size=96, overlap=16))
    assert method == "standard"
    assert float(decoded.max()) == 2.0
    assert calls == [("tiled", 96, 96, 16), ("standard",)]


def test_decode_samples_requires_tiled_runtime_when_forced():
    class StandardOnlyVAE:
        def decode(self, samples):
            return samples

    try:
        _decode_samples(StandardOnlyVAE(), torch.zeros((1, 1, 2, 2)), VaeDecodeSettings(mode="tiled"))
    except ValueError as exc:
        assert "tiled VAE decode requested" in str(exc)
    else:
        raise AssertionError("expected tiled VAE decode failure")


def test_build_renderer_stages_records_execution_evidence():
    request = T2IRequest(
        prompt="staged",
        checkpoint="variants/anima-alt.safetensors",
        width=512,
        height=768,
        steps=4,
        cfg=3.5,
        loras=(T2ILoraConfig(path="style.safetensors", model_strength=0.8, clip_strength=0.7),),
        i2i=I2ISettings(enabled=True, image_path="inputs/source.png", denoise=0.42),
        upscale=UpscaleSettings(
            enabled=True,
            scale=1.5,
            steps=2,
            denoise=0.25,
            method="bicubic",
            tiled=True,
            tile_size=64,
            overlap=8,
        ),
        face_detailer=FaceDetailerSettings(enabled=True, detector="bbox/face_yolov8m.pt"),
        vae_decode=VaeDecodeSettings(mode="tiled", tile_size=96, overlap=16),
    )

    stages = _build_renderer_stages(
        request,
        resolved_loras=[Path("models/loras/style.safetensors")],
        vae_decode_method="tiled",
        face_detailer_stage={
            "enabled": True,
            "status": "completed",
            "detector": "anime-eyes",
            "boxes": [[24.0, 32.0, 96.0, 104.0]],
            "crop_box": [8, 16, 112, 120],
            "output_path": "outputs/images/face_detail.png",
        },
    )

    assert stages["base_t2i"]["status"] == "completed"
    assert stages["base_t2i"]["checkpoint"] == "variants/anima-alt.safetensors"
    assert stages["base_t2i"]["steps"] == 4
    assert stages["base_t2i"]["cfg"] == 3.5
    assert stages["i2i"]["status"] == "completed"
    assert stages["i2i"]["image_path"] == "inputs/source.png"
    assert stages["loras"]["count"] == 1
    assert stages["loras"]["resolved_paths"] == [str(Path("models/loras/style.safetensors"))]
    assert stages["high_res_fix"]["status"] == "completed"
    assert stages["high_res_fix"]["tiled"] is True
    assert stages["high_res_fix"]["tile_size"] == 64
    assert stages["high_res_fix"]["overlap"] == 8
    assert stages["high_res_fix"]["output_width"] == 768
    assert stages["high_res_fix"]["output_height"] == 1152
    assert stages["vae_decode"] == {
        "status": "completed",
        "mode": "tiled",
        "tile_size": 96,
        "overlap": 16,
        "method": "tiled",
    }
    assert stages["face_detailer"]["status"] == "completed"
    assert stages["face_detailer"]["reason"] == ""
    assert stages["face_detailer"]["detector"] == "anime-eyes"
    assert stages["face_detailer"]["boxes"] == [[24.0, 32.0, 96.0, 104.0]]
    assert stages["face_detailer"]["crop_box"] == [8, 16, 112, 120]
    assert stages["face_detailer"]["output_path"] == "outputs/images/face_detail.png"
    assert stages["face_detailer"]["steps"] == 12
    assert stages["face_detailer"]["denoise"] == 0.28

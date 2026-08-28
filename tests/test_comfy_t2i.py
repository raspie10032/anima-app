import sys
from pathlib import Path
from types import ModuleType

import pytest
import torch
from PIL import Image

from anima_app.config import AppPaths
from anima_app.comfy_runtime import bootstrap_comfy_runtime
from anima_app.requests import FaceDetailerSettings, I2ISettings, T2ILoraConfig, T2IRequest, UpscaleSettings, VaeDecodeSettings
from anima_app.runtime import comfy_t2i as comfy_t2i_module
from anima_app.runtime.comfy_t2i import (
    _build_renderer_stages,
    _decode_samples,
    _detailer_pass_specs,
    _face_detailer_render_size,
    _load_image_tensor,
    _make_initial_latent,
    _resolve_i2i_image_path,
    _resolve_lora_path,
    _upscale_latent_samples,
    default_model_paths,
    model_paths_for_request,
    resolve_managed_lora_path,
    resolve_managed_reference_path,
)
from anima_app.runtime.pipeline import ModelsNotReadyError


def test_face_detailer_render_size_targets_1536_long_edge_without_downscaling():
    assert _face_detailer_render_size((344, 312)) == (1536, 1392)
    assert _face_detailer_render_size((2048, 1024)) == (2048, 1024)


def test_default_model_paths_use_project_local_copied_assets(tmp_path):
    paths = AppPaths(project_root=tmp_path)

    model_paths = default_model_paths(paths)

    assert model_paths.diffusion_model == paths.model_root / "diffusion_models" / "anima-base-v1.0.safetensors"
    assert model_paths.text_encoder == paths.model_root / "text_encoders" / "qwen_3_06b_base.safetensors"
    assert model_paths.vae == paths.model_root / "vae" / "qwen_image_vae.safetensors"
    assert model_paths.diffusion_model.is_relative_to(paths.model_root)


def test_model_paths_for_request_uses_selected_diffusion_checkpoint(tmp_path):
    paths = AppPaths(project_root=tmp_path)
    request = T2IRequest(prompt="alternate", checkpoint="variants/anima-alt.safetensors")

    model_paths = model_paths_for_request(request, paths)

    assert model_paths.diffusion_model == paths.model_root / "diffusion_models" / "variants" / "anima-alt.safetensors"
    assert model_paths.text_encoder == paths.model_root / "text_encoders" / "qwen_3_06b_base.safetensors"
    assert model_paths.vae == paths.model_root / "vae" / "qwen_image_vae.safetensors"


def test_render_checks_required_models_before_comfy_bootstrap(monkeypatch, tmp_path):
    paths = AppPaths(project_root=tmp_path)
    bootstrap_called = False

    def unexpected_bootstrap(active_paths):
        nonlocal bootstrap_called
        bootstrap_called = True

    monkeypatch.setattr(comfy_t2i_module, "bootstrap_comfy_runtime", unexpected_bootstrap)

    with pytest.raises(ModelsNotReadyError) as error:
        comfy_t2i_module.render_t2i(T2IRequest(prompt="missing models"), paths)

    assert bootstrap_called is False
    assert error.value.missing == (
        paths.model_root / "diffusion_models" / "anima-base-v1.0.safetensors",
        paths.model_root / "text_encoders" / "qwen_3_06b_base.safetensors",
        paths.model_root / "vae" / "qwen_image_vae.safetensors",
    )


def test_render_rejects_corrupt_models_before_comfy_bootstrap(monkeypatch, tmp_path):
    paths = AppPaths(project_root=tmp_path)
    model_paths = default_model_paths(paths)
    bootstrap_called = False
    for path in (model_paths.diffusion_model, model_paths.text_encoder, model_paths.vae):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"corrupt")

    def unexpected_bootstrap(active_paths):
        nonlocal bootstrap_called
        bootstrap_called = True

    monkeypatch.setattr(comfy_t2i_module, "bootstrap_comfy_runtime", unexpected_bootstrap)

    with pytest.raises(ModelsNotReadyError) as error:
        comfy_t2i_module.render_t2i(T2IRequest(prompt="corrupt models"), paths)

    assert bootstrap_called is False
    assert error.value.missing == (
        model_paths.diffusion_model,
        model_paths.text_encoder,
        model_paths.vae,
    )


def test_qwen_image_tokenizer_uses_comfy_prompt_weights(monkeypatch):
    bootstrap_comfy_runtime(AppPaths())

    from comfy.cli_args import args

    if not torch.cuda.is_available():
        monkeypatch.setattr(args, "cpu", True)

    from comfy.text_encoders.qwen_image import QwenImageTokenizer

    tokenizer = QwenImageTokenizer()
    tokens = tokenizer.tokenize_with_weights("(long hair:1.4), blue eyes")
    weights = {round(float(item[1]), 3) for row in tokens["qwen25_7b"] for item in row}

    assert 1.4 in weights


def test_i2i_image_path_resolves_project_relative_only(tmp_path):
    paths = AppPaths(project_root=tmp_path)
    image_path = tmp_path / "inputs" / "source.png"
    image_path.parent.mkdir(parents=True)
    image_path.write_bytes(b"png")

    assert _resolve_i2i_image_path("inputs/source.png", paths) == image_path


def test_cli_i2i_image_path_preserves_absolute_path_support(tmp_path):
    paths = AppPaths(project_root=tmp_path / "project")
    image_path = tmp_path / "external.png"
    image_path.write_bytes(b"png")

    assert _resolve_i2i_image_path(str(image_path), paths) == image_path


def test_cli_lora_path_preserves_absolute_path_support(tmp_path):
    lora_path = tmp_path / "external.safetensors"
    lora_path.write_bytes(b"lora")

    resolved = _resolve_lora_path(
        T2ILoraConfig(path=str(lora_path)),
        [tmp_path / "managed-loras"],
    )

    assert resolved == lora_path


@pytest.mark.parametrize("relative_path", ["inputs/references/source.png", "outputs/images/source.png"])
def test_managed_reference_path_accepts_only_managed_roots(tmp_path, relative_path):
    paths = AppPaths(project_root=tmp_path)
    image_path = tmp_path / Path(relative_path)
    image_path.parent.mkdir(parents=True)
    Image.new("RGB", (16, 16), "white").save(image_path)

    assert resolve_managed_reference_path(relative_path, paths) == image_path.resolve()


@pytest.mark.parametrize(
    "reference_path",
    [
        "inputs/source.png",
        "inputs/references/../source.png",
        "outputs/images/../../source.png",
        "/outputs/images/source.png",
        r"C:\outside\source.png",
    ],
)
def test_managed_reference_path_rejects_unmanaged_or_escaping_paths(tmp_path, reference_path):
    with pytest.raises(ValueError, match="managed reference"):
        resolve_managed_reference_path(reference_path, AppPaths(project_root=tmp_path))


def test_managed_reference_path_rejects_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError, match="managed reference"):
        resolve_managed_reference_path(
            "inputs/references/missing.png",
            AppPaths(project_root=tmp_path),
        )


def test_managed_reference_path_rejects_symlink_escape(tmp_path, monkeypatch):
    paths = AppPaths(project_root=tmp_path / "project")
    outside = tmp_path / "outside.png"
    Image.new("RGB", (8, 8), "white").save(outside)
    link = paths.input_root / "references" / "link.png"
    link.parent.mkdir(parents=True)
    link.write_bytes(b"placeholder")
    escaped = outside.resolve()
    real_resolve = Path.resolve

    def resolve_symlink(path, *args, **kwargs):
        return escaped if path == link else real_resolve(path, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", resolve_symlink)

    with pytest.raises(ValueError, match="managed reference"):
        resolve_managed_reference_path("inputs/references/link.png", paths)


def test_managed_reference_path_rejects_unsupported_image(tmp_path):
    paths = AppPaths(project_root=tmp_path)
    image_path = paths.input_root / "references" / "animated.gif"
    image_path.parent.mkdir(parents=True)
    Image.new("RGB", (8, 8), "white").save(image_path, format="GIF")

    with pytest.raises(ValueError, match="unsupported managed reference image format"):
        resolve_managed_reference_path("inputs/references/animated.gif", paths)


def test_managed_reference_path_rejects_oversized_header_before_decode(tmp_path, monkeypatch):
    paths = AppPaths(project_root=tmp_path)
    image_path = paths.input_root / "references" / "oversized.png"
    image_path.parent.mkdir(parents=True)
    image_path.write_bytes(b"placeholder")

    class OversizedImage:
        format = "PNG"
        size = (10**9, 10**9)

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def load(self):
            raise AssertionError("oversized image must not be decoded")

        def convert(self, _mode):
            raise AssertionError("oversized image must not be decoded")

    monkeypatch.setattr("anima_app.runtime.comfy_t2i.Image.open", lambda _path: OversizedImage())

    with pytest.raises(ValueError, match="managed reference image"):
        resolve_managed_reference_path("inputs/references/oversized.png", paths)


@pytest.mark.parametrize(
    ("limit_name", "limit_value", "message"),
    [
        ("MAX_REFERENCE_UPLOAD_BYTES", 1, "size"),
        ("MAX_REFERENCE_IMAGE_DIMENSION", 8, "dimension"),
        ("MAX_REFERENCE_IMAGE_PIXELS", 19, "pixel count"),
    ],
)
def test_managed_reference_path_reuses_upload_limits(tmp_path, monkeypatch, limit_name, limit_value, message):
    paths = AppPaths(project_root=tmp_path)
    image_path = paths.input_root / "references" / "bounded.png"
    image_path.parent.mkdir(parents=True)
    Image.new("RGB", (10, 2), "white").save(image_path)
    monkeypatch.setattr(comfy_t2i_module, limit_name, limit_value)

    with pytest.raises(ValueError, match=message):
        resolve_managed_reference_path("inputs/references/bounded.png", paths)


def test_managed_lora_path_accepts_nested_relative_file(tmp_path):
    paths = AppPaths(project_root=tmp_path)
    lora_path = paths.model_root / "loras" / "styles" / "soft.safetensors"
    lora_path.parent.mkdir(parents=True)
    lora_path.write_bytes(b"lora")

    assert resolve_managed_lora_path("styles/soft.safetensors", paths) == lora_path.resolve()


@pytest.mark.parametrize(
    "lora_path",
    [
        "../outside.safetensors",
        "styles/../../outside.safetensors",
        "/models/loras/style.safetensors",
        r"C:\outside\style.safetensors",
        "style.ckpt",
    ],
)
def test_managed_lora_path_rejects_unsafe_or_unsupported_paths(tmp_path, lora_path):
    with pytest.raises(ValueError, match="managed LoRA"):
        resolve_managed_lora_path(lora_path, AppPaths(project_root=tmp_path))


def test_managed_lora_path_rejects_missing_file_and_symlink_escape(tmp_path, monkeypatch):
    paths = AppPaths(project_root=tmp_path / "project")
    with pytest.raises(FileNotFoundError, match="managed LoRA"):
        resolve_managed_lora_path("missing.safetensors", paths)

    outside = tmp_path / "outside.safetensors"
    outside.write_bytes(b"lora")
    link = paths.model_root / "loras" / "link.safetensors"
    link.parent.mkdir(parents=True)
    link.write_bytes(b"placeholder")
    escaped = outside.resolve()
    real_resolve = Path.resolve

    def resolve_symlink(path, *args, **kwargs):
        return escaped if path == link else real_resolve(path, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", resolve_symlink)

    with pytest.raises(ValueError, match="managed LoRA"):
        resolve_managed_lora_path("link.safetensors", paths)


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
        runtime_metrics={
            "status": "completed",
            "elapsed_sec": 3.25,
            "cuda_available": True,
            "cuda_peak_reserved_mb": 7450.0,
            "stages": {"base_sample": {"elapsed_sec": 1.5, "cuda_peak_reserved_mb": 6400.0}},
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
    assert stages["face_detailer"]["steps"] == 10
    assert stages["face_detailer"]["denoise"] == 0.28
    assert stages["runtime_metrics"] == {
        "status": "completed",
        "elapsed_sec": 3.25,
        "cuda_available": True,
        "cuda_peak_reserved_mb": 7450.0,
        "stages": {"base_sample": {"elapsed_sec": 1.5, "cuda_peak_reserved_mb": 6400.0}},
    }


def test_sam3_detailer_passes_are_ordered_face_then_hands():
    settings = FaceDetailerSettings(
        enabled=True,
        mask_backend="sam3",
        sam3_face_eyes=True,
        sam3_hands=True,
        denoise=0.28,
        hand_denoise=0.36,
    )

    passes = _detailer_pass_specs(settings)

    assert [item[0] for item in passes] == ["face_eye_detailer", "hand_detailer"]
    assert passes[0][2] == ("face", "eyes")
    assert passes[0][4].denoise == 0.28
    assert passes[1][2] == ("hand", "hands")
    assert passes[1][4].denoise == 0.36
    assert passes[1][4].exclude_forehead_ratio == 0


def test_build_renderer_stages_includes_sam3_pass_results():
    request = T2IRequest(
        prompt="detail passes",
        face_detailer=FaceDetailerSettings(enabled=True, mask_backend="sam3", sam3_hands=True),
    )
    pass_stages = {
        "face_eye_detailer": {"status": "completed", "concepts": ["face", "eyes"]},
        "hand_detailer": {"status": "skipped", "reason": "no_detections", "concepts": ["hands"]},
    }

    stages = _build_renderer_stages(
        request,
        resolved_loras=[],
        vae_decode_method="standard",
        face_detailer_stage={"enabled": True, "status": "completed", "passes": pass_stages},
        detailer_stages=pass_stages,
    )

    assert stages["face_detailer"]["status"] == "completed"
    assert stages["face_eye_detailer"]["concepts"] == ["face", "eyes"]
    assert stages["hand_detailer"]["reason"] == "no_detections"

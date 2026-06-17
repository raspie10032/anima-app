import json
from pathlib import Path

from PIL import Image
import pytest

from anima_app.config import AppPaths
from anima_app.manifests import read_manifest, read_t2i_history
from anima_app.requests import FaceDetailerSettings, I2ISettings, T2IRequest, UpscaleSettings, VaeDecodeSettings
from anima_app.runtime.pipeline import T2IRenderOutput, latent_shape_for_request, run_t2i


def test_t2i_request_rejects_empty_prompt():
    with pytest.raises(ValueError, match="prompt is required"):
        T2IRequest(prompt="   ")


def test_t2i_request_requires_latent_grid_resolution():
    with pytest.raises(ValueError, match="divisible by 8"):
        T2IRequest(prompt="anime portrait", width=513, height=768)


def test_t2i_request_validates_tiled_vae_and_upscale_settings():
    with pytest.raises(ValueError, match="vae decode mode"):
        T2IRequest(prompt="anime portrait", vae_decode=VaeDecodeSettings(mode="bad"))
    with pytest.raises(ValueError, match="vae tile size"):
        T2IRequest(prompt="anime portrait", vae_decode=VaeDecodeSettings(tile_size=0))
    with pytest.raises(ValueError, match="upscale tile size"):
        T2IRequest(prompt="anime portrait", upscale=UpscaleSettings(enabled=True, tiled=True, tile_size=0))
    with pytest.raises(ValueError, match="upscale overlap"):
        T2IRequest(prompt="anime portrait", upscale=UpscaleSettings(enabled=True, tiled=True, tile_size=16, overlap=16))


def test_t2i_request_normalizes_and_validates_checkpoint():
    request = T2IRequest(prompt="anime portrait", checkpoint=r"variants\anima-alt.safetensors")

    assert request.checkpoint == "variants/anima-alt.safetensors"
    with pytest.raises(ValueError, match="checkpoint"):
        T2IRequest(prompt="anime portrait", checkpoint="")
    with pytest.raises(ValueError, match="checkpoint"):
        T2IRequest(prompt="anime portrait", checkpoint="../escape.safetensors")
    with pytest.raises(ValueError, match=".safetensors"):
        T2IRequest(prompt="anime portrait", checkpoint="anima-alt.ckpt")


def test_latent_shape_matches_anima_downscale_contract():
    request = T2IRequest(prompt="anime portrait", width=512, height=768)

    assert latent_shape_for_request(request) == {
        "batch": 1,
        "channels": 16,
        "height": 96,
        "width": 64,
        "source_width": 512,
        "source_height": 768,
        "downscale_factor": 8,
    }


def test_dry_run_writes_manifest_without_output_path(tmp_path):
    paths = AppPaths(project_root=tmp_path)
    request = T2IRequest(
        prompt="anime portrait, clean lineart",
        negative_prompt="low quality",
        width=512,
        height=768,
        steps=1,
        cfg=1.0,
        seed=52,
        checkpoint="variants/anima-alt.safetensors",
        i2i=I2ISettings(enabled=True, image_path="inputs/reference.png", denoise=0.4),
        upscale=UpscaleSettings(enabled=True, scale=1.5, steps=2, denoise=0.35, tiled=True, tile_size=64, overlap=8),
        vae_decode=VaeDecodeSettings(mode="tiled", tile_size=96, overlap=16),
    )

    result = run_t2i(request, paths=paths, dry_run=True)
    payload = read_manifest(result.manifest_path)

    assert result.status == "dry_run"
    assert result.output_path is None
    assert result.manifest_path.parent == tmp_path / "outputs" / "manifests"
    assert payload["prompt"] == "anime portrait, clean lineart"
    assert payload["negative_prompt"] == "low quality"
    assert payload["status"] == "dry_run"
    assert payload["checkpoint"] == "variants/anima-alt.safetensors"
    assert payload["output_path"] is None
    assert payload["model_root"] == str(tmp_path / "models")
    assert payload["pipeline"] == ["tokenize", "text_encode", "base_t2i", "high_res_fix", "vae_decode", "face_detailer"]
    assert payload["latent"]["channels"] == 16
    assert payload["i2i"]["enabled"] is True
    assert payload["upscale"]["enabled"] is True
    assert payload["upscale"]["tiled"] is True
    assert payload["upscale"]["tile_size"] == 64
    assert payload["upscale"]["overlap"] == 8
    assert payload["vae_decode"] == {"mode": "tiled", "tile_size": 96, "overlap": 16}
    assert payload["stages"]["vae_decode"] == {
        "status": "configured",
        "mode": "tiled",
        "tile_size": 96,
        "overlap": 16,
        "method": "not_run",
    }
    assert payload["provenance"]["app"] == "anima-app"


def test_dry_run_records_face_detailer_skipped_reason_when_enabled(tmp_path):
    paths = AppPaths(project_root=tmp_path)
    request = T2IRequest(
        prompt="face detailer",
        width=512,
        height=768,
        face_detailer=FaceDetailerSettings(
            enabled=True,
            detector="bbox/face_yolov8m.pt",
            exclude_forehead_ratio=0.25,
        ),
    )

    result = run_t2i(request, paths=paths, dry_run=True)
    payload = read_manifest(result.manifest_path)

    assert payload["stages"]["face_detailer"] == {
        "status": "skipped",
        "reason": "dry_run_not_executed",
        "detector": "bbox/face_yolov8m.pt",
        "threshold": 0.5,
        "crop_scale": 1.5,
        "padding": 32,
        "feather": 24,
        "exclude_forehead_ratio": 0.25,
        "steps": 12,
        "denoise": 0.28,
    }


def test_history_reads_newest_manifest_first(tmp_path):
    paths = AppPaths(project_root=tmp_path)
    first = T2IRequest(prompt="first prompt", seed=1)
    second = T2IRequest(prompt="second prompt", seed=2)

    run_t2i(first, paths=paths, dry_run=True)
    run_t2i(second, paths=paths, dry_run=True)

    prompts = [item["prompt"] for item in read_t2i_history(paths, limit=2)]

    assert prompts == ["second prompt", "first prompt"]


def test_manifest_reader_rejects_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        read_manifest(tmp_path / "missing.json")


def test_manifest_json_is_written_as_utf8(tmp_path):
    paths = AppPaths(project_root=tmp_path)
    result = run_t2i(T2IRequest(prompt="아니마 portrait"), paths=paths, dry_run=True)

    raw = result.manifest_path.read_text(encoding="utf-8")

    assert json.loads(raw)["prompt"] == "아니마 portrait"


def test_real_renderer_output_is_validated_and_recorded(tmp_path):
    paths = AppPaths(project_root=tmp_path)
    request = T2IRequest(prompt="real render", width=32, height=48, steps=1)

    def fake_renderer(_request, active_paths):
        output_path = active_paths.image_root / "sample.png"
        output_path.parent.mkdir(parents=True)
        Image.new("RGB", (32, 48), "white").save(output_path)
        return T2IRenderOutput(output_path=output_path, stages={"base_t2i": {"status": "completed"}})

    result = run_t2i(request, paths=paths, dry_run=False, renderer=fake_renderer)
    payload = read_manifest(result.manifest_path)

    assert result.status == "generated"
    assert result.output_path == paths.image_root / "sample.png"
    assert payload["status"] == "generated"
    assert payload["output_path"] == str(paths.image_root / "sample.png")
    assert payload["stages"]["base_t2i"]["status"] == "completed"
    assert payload["provenance"]["comfyui_runtime"] == "renderer"


def test_real_renderer_warnings_are_recorded(tmp_path):
    paths = AppPaths(project_root=tmp_path)
    request = T2IRequest(prompt="real render", width=32, height=48, steps=1)

    def fake_renderer(_request, active_paths):
        output_path = active_paths.image_root / "sample.png"
        output_path.parent.mkdir(parents=True)
        Image.new("RGB", (32, 48), "white").save(output_path)
        return T2IRenderOutput(
            output_path=output_path,
            stages={"face_detailer": {"status": "skipped", "reason": "no_detections"}},
            warnings=("face detailer skipped: no_detections",),
        )

    result = run_t2i(request, paths=paths, dry_run=False, renderer=fake_renderer)
    payload = read_manifest(result.manifest_path)

    assert result.warnings == ("face detailer skipped: no_detections",)
    assert payload["warnings"] == ["face detailer skipped: no_detections"]


def test_real_renderer_output_must_stay_under_image_root(tmp_path):
    paths = AppPaths(project_root=tmp_path)

    def fake_renderer(_request, active_paths):
        output_path = active_paths.project_root / "outside.png"
        Image.new("RGB", (8, 8), "white").save(output_path)
        return T2IRenderOutput(output_path=output_path)

    with pytest.raises(ValueError, match="under image_root"):
        run_t2i(T2IRequest(prompt="bad output"), paths=paths, dry_run=False, renderer=fake_renderer)

import json
import re
from datetime import datetime

from PIL import Image

from anima_app.config import AppPaths
from anima_app.manifests import read_manifest
from anima_app.output_names import allocate_output_path, build_output_stem
from anima_app.requests import I2ISettings, T2ILoraConfig, T2IRequest, UpscaleSettings
from anima_app.runtime.pipeline import T2IRenderOutput, run_t2i


def test_output_stem_includes_default_searchable_parts():
    request = T2IRequest(
        prompt="Anime portrait, soft lineart!!",
        negative_prompt="low quality",
        width=512,
        height=768,
        steps=12,
        cfg=3.5,
        seed=101,
        loras=(T2ILoraConfig(path="style.safetensors", model_strength=0.5, clip_strength=0.25),),
    )
    created_at = datetime(2026, 6, 16, 23, 30, 12).timestamp()

    stem = build_output_stem(request, status="generated", created_at=created_at)

    assert re.fullmatch(
        r"20260616-233012_s101_512x768_lora_anime-portrait-soft-lineart_[0-9a-f]{6}",
        stem,
    )


def test_allocate_output_path_uses_numeric_suffix_for_collisions(tmp_path):
    paths = AppPaths(project_root=tmp_path)
    request = T2IRequest(prompt="anime portrait", width=512, height=768, seed=101)
    created_at = datetime(2026, 6, 16, 23, 30, 12).timestamp()
    first = allocate_output_path(request, paths=paths, status="generated", created_at=created_at)
    first.parent.mkdir(parents=True)
    first.write_bytes(b"existing")

    second = allocate_output_path(request, paths=paths, status="generated", created_at=created_at)

    assert re.fullmatch(r"20260616-233012_s101_512x768_t2i_anime-portrait_[0-9a-f]{6}\.png", first.name)
    assert second.name == f"{first.stem}_02.png"


def test_dry_run_manifest_uses_default_name_and_records_a1111_metadata_preview(tmp_path):
    paths = AppPaths(project_root=tmp_path)
    request = T2IRequest(
        prompt="anime portrait, soft lineart",
        negative_prompt="low quality",
        width=512,
        height=768,
        steps=7,
        cfg=1.5,
        seed=123,
        i2i=I2ISettings(enabled=True, image_path="inputs/reference.png", denoise=0.42),
        upscale=UpscaleSettings(enabled=True, scale=1.5, steps=2, denoise=0.25),
    )

    result = run_t2i(request, paths=paths, dry_run=True)
    payload = read_manifest(result.manifest_path)

    assert result.manifest_path.name.startswith("20")
    assert "_s123_512x768_i2i_dry_anime-portrait-soft-lineart_" in result.manifest_path.name
    assert payload["png_metadata"]["parameters"].startswith("anime portrait, soft lineart\n")
    assert "Negative prompt: low quality" in payload["png_metadata"]["parameters"]
    assert "Steps: 7" in payload["png_metadata"]["parameters"]
    assert "CFG scale: 1.5" in payload["png_metadata"]["parameters"]
    assert "Seed: 123" in payload["png_metadata"]["parameters"]
    assert "Size: 512x768" in payload["png_metadata"]["parameters"]
    assert "Model: anima-base-v1.0.safetensors" in payload["png_metadata"]["parameters"]
    assert "Denoising strength: 0.42" in payload["png_metadata"]["parameters"]
    assert "Anima upscale: 1.5x" in payload["png_metadata"]["parameters"]


def test_generated_png_embeds_a1111_parameters_and_manifest_records_same_text(tmp_path):
    paths = AppPaths(project_root=tmp_path)
    request = T2IRequest(
        prompt="api portrait",
        negative_prompt="bad hands",
        width=32,
        height=48,
        steps=3,
        cfg=2.0,
        seed=77,
    )

    def fake_renderer(_request, active_paths):
        output_path = active_paths.image_root / "plain.png"
        output_path.parent.mkdir(parents=True)
        Image.new("RGB", (32, 48), "white").save(output_path)
        return T2IRenderOutput(output_path=output_path, stages={"base_t2i": {"status": "completed"}})

    result = run_t2i(request, paths=paths, dry_run=False, renderer=fake_renderer)
    payload = json.loads(result.manifest_path.read_text(encoding="utf-8"))

    with Image.open(result.output_path) as image:
        parameters = image.text["parameters"]

    assert parameters == payload["png_metadata"]["parameters"]
    assert parameters.startswith("api portrait\nNegative prompt: bad hands\n")
    assert "Steps: 3" in parameters
    assert "Sampler: euler" in parameters
    assert "CFG scale: 2" in parameters
    assert "Seed: 77" in parameters
    assert "Size: 32x48" in parameters
    assert "Model: anima-base-v1.0.safetensors" in parameters

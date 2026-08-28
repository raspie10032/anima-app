import json
from pathlib import Path

from PIL import Image
import pytest

from anima_app import manifests as manifests_module
from anima_app import requests as requests_module
from anima_app.config import AppPaths
from anima_app.manifests import read_manifest, read_t2i_history
from anima_app.requests import (
    FaceDetailerSettings,
    I2ISettings,
    T2ILoraConfig,
    T2IRequest,
    UpscaleSettings,
    VaeDecodeSettings,
)
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
    with pytest.raises(ValueError, match="memory profile"):
        T2IRequest(prompt="anime portrait", memory_profile="tiny")
    with pytest.raises(ValueError, match="CFG\\+\\+ sampler"):
        T2IRequest(prompt="anime portrait", sampler="euler")
    with pytest.raises(ValueError, match="vae tile size"):
        T2IRequest(prompt="anime portrait", vae_decode=VaeDecodeSettings(tile_size=0))
    with pytest.raises(ValueError, match="upscale tile size"):
        T2IRequest(prompt="anime portrait", upscale=UpscaleSettings(enabled=True, tiled=True, tile_size=0))
    with pytest.raises(ValueError, match="upscale overlap"):
        T2IRequest(prompt="anime portrait", upscale=UpscaleSettings(enabled=True, tiled=True, tile_size=64, overlap=17))
    with pytest.raises(ValueError, match="mask backend"):
        T2IRequest(prompt="anime portrait", face_detailer=FaceDetailerSettings(mask_backend="bad"))


def test_t2i_request_enforces_prompt_character_boundaries():
    max_characters = requests_module.MAX_PROMPT_CHARACTERS
    boundary = T2IRequest(
        prompt="p" * max_characters,
        negative_prompt="n" * max_characters,
    )

    assert len(boundary.prompt) == max_characters
    assert len(boundary.negative_prompt) == max_characters
    with pytest.raises(ValueError, match="prompt must not exceed"):
        T2IRequest(prompt="p" * (max_characters + 1))
    with pytest.raises(ValueError, match="negative prompt must not exceed"):
        T2IRequest(prompt="valid", negative_prompt="n" * (max_characters + 1))


def test_t2i_request_enforces_seed_boundaries():
    max_seed = requests_module.MAX_SEED

    assert T2IRequest(prompt="minimum seed", seed=0).seed == 0
    assert T2IRequest(prompt="maximum seed", seed=max_seed).seed == max_seed

    for invalid_seed in (-1, max_seed + 1, True, False, 1.0, "1"):
        with pytest.raises(ValueError, match="seed must be an integer between"):
            T2IRequest(prompt="invalid seed", seed=invalid_seed)


def test_t2i_request_enforces_tile_stride_boundaries():
    min_tile_size = requests_module.MIN_TILE_SIZE
    max_tile_size = requests_module.MAX_TILE_SIZE
    max_overlap = min_tile_size // 4

    boundary = T2IRequest(
        prompt="allowed tiles",
        upscale=UpscaleSettings(
            enabled=True,
            tiled=True,
            tile_size=min_tile_size,
            overlap=max_overlap,
        ),
        vae_decode=VaeDecodeSettings(
            mode="tiled",
            tile_size=max_tile_size,
            overlap=max_tile_size // 4,
        ),
    )

    assert boundary.upscale.tile_size == min_tile_size
    with pytest.raises(ValueError, match="tile size must be between"):
        T2IRequest(
            prompt="undersized tile",
            vae_decode=VaeDecodeSettings(mode="tiled", tile_size=min_tile_size - 1),
        )
    with pytest.raises(ValueError, match="overlap must be between"):
        T2IRequest(
            prompt="excessive overlap",
            vae_decode=VaeDecodeSettings(
                mode="tiled",
                tile_size=min_tile_size,
                overlap=max_overlap + 1,
            ),
        )


def test_t2i_request_enforces_named_resource_limits():
    max_dimension = requests_module.MAX_GENERATION_DIMENSION
    max_base_pixels = requests_module.MAX_BASE_IMAGE_PIXELS
    max_output_pixels = requests_module.MAX_OUTPUT_IMAGE_PIXELS
    max_steps = requests_module.MAX_SAMPLING_STEPS
    max_cfg = requests_module.MAX_CFG
    max_scale = requests_module.MAX_UPSCALE_SCALE
    max_tile_size = requests_module.MAX_TILE_SIZE

    with pytest.raises(ValueError, match="width and height must be <="):
        T2IRequest(prompt="too wide", width=max_dimension + 8)
    assert max_dimension * max_dimension > max_base_pixels
    with pytest.raises(ValueError, match="base image must not exceed"):
        T2IRequest(prompt="too many base pixels", width=max_dimension, height=max_dimension)
    with pytest.raises(ValueError, match="steps must be between"):
        T2IRequest(prompt="too many steps", steps=max_steps + 1)
    with pytest.raises(ValueError, match="cfg must be finite and between"):
        T2IRequest(prompt="bad cfg", cfg=max_cfg + 0.1)
    with pytest.raises(ValueError, match="upscale scale must be finite and between"):
        T2IRequest(prompt="too much upscale", upscale=UpscaleSettings(enabled=True, scale=max_scale + 0.1))
    with pytest.raises(ValueError, match="upscaled image must not exceed"):
        T2IRequest(
            prompt="too many output pixels",
            width=1024,
            height=1536,
            upscale=UpscaleSettings(enabled=True, scale=max_scale),
        )
    with pytest.raises(ValueError, match="vae tile size must be between"):
        T2IRequest(prompt="oversized tile", vae_decode=VaeDecodeSettings(tile_size=max_tile_size + 1))

    boundary = T2IRequest(
        prompt="allowed boundary",
        width=512,
        height=512,
        steps=max_steps,
        cfg=max_cfg,
        upscale=UpscaleSettings(enabled=True, scale=max_scale),
        vae_decode=VaeDecodeSettings(tile_size=max_tile_size, overlap=0),
    )
    output_width = round((boundary.width // 8) * boundary.upscale.scale) * 8
    output_height = round((boundary.height // 8) * boundary.upscale.scale) * 8
    assert output_width * output_height == max_output_pixels


def test_t2i_request_uses_runtime_latent_rounding_for_output_pixel_limit():
    width = 136
    height = 1992
    scale = 3.9347381043608793
    direct_pixel_count = round(width * scale) * round(height * scale)
    latent_pixel_count = round((width // 8) * scale) * 8 * round((height // 8) * scale) * 8

    assert direct_pixel_count <= requests_module.MAX_OUTPUT_IMAGE_PIXELS
    assert latent_pixel_count > requests_module.MAX_OUTPUT_IMAGE_PIXELS
    with pytest.raises(ValueError, match="upscaled image must not exceed"):
        T2IRequest(
            prompt="latent-rounded output",
            width=width,
            height=height,
            upscale=UpscaleSettings(enabled=True, scale=scale),
        )


def test_t2i_request_enforces_component_resource_limits():
    max_steps = requests_module.MAX_SAMPLING_STEPS

    with pytest.raises(ValueError, match="upscale steps must be between"):
        T2IRequest(prompt="upscale steps", upscale=UpscaleSettings(steps=max_steps + 1))
    with pytest.raises(ValueError, match="face detailer steps must be between"):
        T2IRequest(prompt="face steps", face_detailer=FaceDetailerSettings(steps=max_steps + 1))
    with pytest.raises(ValueError, match="face detailer crop scale must be finite and between"):
        T2IRequest(
            prompt="face crop scale",
            face_detailer=FaceDetailerSettings(crop_scale=requests_module.MAX_FACE_CROP_SCALE + 0.1),
        )
    with pytest.raises(ValueError, match="face detailer padding must be between"):
        T2IRequest(
            prompt="face padding",
            face_detailer=FaceDetailerSettings(padding=requests_module.MAX_FACE_PADDING + 1),
        )
    with pytest.raises(ValueError, match="face detailer feather must be between"):
        T2IRequest(
            prompt="face feather",
            face_detailer=FaceDetailerSettings(feather=requests_module.MAX_FACE_FEATHER + 1),
        )
    with pytest.raises(ValueError, match="no more than .* LoRAs"):
        T2IRequest(
            prompt="too many loras",
            loras=tuple(
                T2ILoraConfig(path=f"lora-{index}.safetensors")
                for index in range(requests_module.MAX_LORA_COUNT + 1)
            ),
        )
    with pytest.raises(ValueError, match="lora model strength must be finite and between"):
        T2IRequest(
            prompt="lora strength",
            loras=(
                T2ILoraConfig(path="lora.safetensors", model_strength=requests_module.MAX_LORA_STRENGTH + 0.1),
            ),
        )


@pytest.mark.parametrize(
    ("factory", "message"),
    [
        (T2IRequest, "cfg must be finite"),
        (
            lambda **kwargs: T2IRequest(
                loras=(T2ILoraConfig(path="lora.safetensors", model_strength=float("inf")),),
                **kwargs,
            ),
            "lora model strength must be finite",
        ),
        (
            lambda **kwargs: T2IRequest(
                loras=(T2ILoraConfig(path="lora.safetensors", clip_strength=float("nan")),),
                **kwargs,
            ),
            "lora clip strength must be finite",
        ),
        (lambda **kwargs: T2IRequest(upscale=UpscaleSettings(scale=float("inf")), **kwargs), "upscale scale must be finite"),
        (
            lambda **kwargs: T2IRequest(upscale=UpscaleSettings(denoise=float("nan")), **kwargs),
            "upscale denoise must be finite",
        ),
        (lambda **kwargs: T2IRequest(i2i=I2ISettings(denoise=float("nan")), **kwargs), "i2i denoise must be finite"),
        (
            lambda **kwargs: T2IRequest(
                face_detailer=FaceDetailerSettings(threshold=float("inf")),
                **kwargs,
            ),
            "face detailer threshold must be finite",
        ),
        (
            lambda **kwargs: T2IRequest(
                face_detailer=FaceDetailerSettings(crop_scale=float("nan")),
                **kwargs,
            ),
            "face detailer crop scale must be finite",
        ),
        (
            lambda **kwargs: T2IRequest(
                face_detailer=FaceDetailerSettings(exclude_forehead_ratio=float("nan")),
                **kwargs,
            ),
            "face detailer forehead exclusion must be finite",
        ),
        (
            lambda **kwargs: T2IRequest(
                face_detailer=FaceDetailerSettings(denoise=float("nan")),
                **kwargs,
            ),
            "face detailer denoise must be finite",
        ),
        (
            lambda **kwargs: T2IRequest(
                face_detailer=FaceDetailerSettings(hand_denoise=float("inf")),
                **kwargs,
            ),
            "hand detailer denoise must be finite",
        ),
    ],
)
def test_t2i_request_rejects_non_finite_numbers(factory, message):
    kwargs = {"prompt": "finite values only"}
    if factory is T2IRequest:
        kwargs["cfg"] = float("nan")
    with pytest.raises(ValueError, match=message):
        factory(**kwargs)


def test_low_vram_highres_profile_enables_tiled_highres_path():
    request = T2IRequest(prompt="anime portrait", memory_profile="low_vram_highres")

    assert request.memory_profile == "low_vram_highres"
    assert request.upscale.enabled is True
    assert request.upscale.tiled is True
    assert request.upscale.steps == 10
    assert request.vae_decode.mode == "tiled"


def test_low_vram_highres_profile_fixes_upscale_steps():
    request = T2IRequest(
        prompt="anime portrait",
        memory_profile="low_vram_highres",
        upscale=UpscaleSettings(enabled=True, steps=4),
    )

    assert request.upscale.steps == 10


def test_t2i_request_normalizes_and_validates_checkpoint():
    request = T2IRequest(prompt="anime portrait", checkpoint=r"variants\anima-alt.safetensors")

    assert request.checkpoint == "variants/anima-alt.safetensors"
    with pytest.raises(ValueError, match="checkpoint"):
        T2IRequest(prompt="anime portrait", checkpoint="")
    with pytest.raises(ValueError, match="checkpoint"):
        T2IRequest(prompt="anime portrait", checkpoint="../escape.safetensors")
    with pytest.raises(ValueError, match=".safetensors"):
        T2IRequest(prompt="anime portrait", checkpoint="anima-alt.ckpt")


@pytest.mark.parametrize(
    "checkpoint",
    [
        "C:/escape.safetensors",
        r"C:\escape.safetensors",
        r"C:escape.safetensors",
        r"\\server\share\escape.safetensors",
        r"variant:stream.safetensors",
    ],
)
def test_t2i_request_rejects_windows_checkpoint_paths_outside_model_root(checkpoint):
    with pytest.raises(ValueError, match="relative path under diffusion_models"):
        T2IRequest(prompt="anime portrait", checkpoint=checkpoint)


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
    assert payload["pipeline"] == [
        "tokenize",
        "text_encode",
        "base_t2i",
        "high_res_fix",
        "vae_decode",
        "face_detailer",
        "face_eye_detailer",
        "hand_detailer",
    ]
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
    assert payload["stages"]["memory_profile"]["profile"] == "auto"
    assert payload["provenance"]["app"] == "anima-app"


def test_low_vram_highres_profile_is_recorded_in_dry_run_manifest(tmp_path):
    paths = AppPaths(project_root=tmp_path)
    request = T2IRequest(prompt="low vram highres", memory_profile="low_vram_highres", width=512, height=768)

    result = run_t2i(request, paths=paths, dry_run=True)
    payload = read_manifest(result.manifest_path)

    assert payload["memory_profile"] == "low_vram_highres"
    assert payload["upscale"]["enabled"] is True
    assert payload["upscale"]["tiled"] is True
    assert payload["upscale"]["steps"] == 10
    assert payload["vae_decode"]["mode"] == "tiled"
    assert payload["stages"]["memory_profile"] == {
        "status": "configured",
        "profile": "low_vram_highres",
        "upscale_tiled": True,
        "vae_decode_mode": "tiled",
        "output_width": 768,
        "output_height": 1152,
    }


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
        "mask_backend": "sam_b",
        "threshold": 0.5,
        "crop_scale": 1.5,
        "padding": 32,
        "feather": 24,
        "exclude_forehead_ratio": 0.25,
        "steps": 10,
        "denoise": 0.28,
        "sam3_face_eyes": True,
        "sam3_hands": False,
        "hand_denoise": 0.35,
    }


def test_history_reads_newest_manifest_first(tmp_path):
    paths = AppPaths(project_root=tmp_path)
    first = T2IRequest(prompt="first prompt", seed=1)
    second = T2IRequest(prompt="second prompt", seed=2)

    run_t2i(first, paths=paths, dry_run=True)
    run_t2i(second, paths=paths, dry_run=True)

    prompts = [item["prompt"] for item in read_t2i_history(paths, limit=2)]
    all_prompts = [item["prompt"] for item in read_t2i_history(paths, limit=None)]

    assert prompts == ["second prompt", "first prompt"]
    assert all_prompts == ["second prompt", "first prompt"]


def test_history_skips_corrupt_manifests_without_consuming_limit(tmp_path):
    paths = AppPaths(project_root=tmp_path)
    run_t2i(T2IRequest(prompt="older valid", seed=1), paths=paths, dry_run=True)
    run_t2i(T2IRequest(prompt="newer valid", seed=2), paths=paths, dry_run=True)
    corrupt = paths.manifest_root / "99999999-999999_corrupt.json"
    corrupt.write_text('{"created_at":', encoding="utf-8")

    prompts = [item["prompt"] for item in read_t2i_history(paths, limit=2)]

    assert prompts == ["newer valid", "older valid"]


@pytest.mark.parametrize(
    "query",
    ["BLUE", "BLURRY", "ANIMEV1", "4242", "SPECIAL_RECORD", "PORTRAIT_STYLE"],
)
def test_history_searches_supported_manifest_fields_case_insensitively(tmp_path, query):
    paths = AppPaths(project_root=tmp_path)
    paths.manifest_root.mkdir(parents=True)
    manifest_path = paths.manifest_root / "000001_special_record.json"
    manifest_path.write_text(
        json.dumps(
            {
                "created_at": 1,
                "prompt": "Blue heroine",
                "negative_prompt": "blurry",
                "checkpoint": "AnimeV1.safetensors",
                "seed": 4242,
                "loras": [{"path": "styles/portrait_style.safetensors"}],
                "manifest_path": "untrusted-name.json",
            }
        ),
        encoding="utf-8",
    )

    results = read_t2i_history(paths, query=query)

    assert [item["_history_filename"] for item in results] == [manifest_path.name]


def test_history_searches_all_tokens_before_applying_limit(tmp_path):
    paths = AppPaths(project_root=tmp_path)
    paths.manifest_root.mkdir(parents=True)
    (paths.manifest_root / "000002_newer.json").write_text(
        json.dumps({"created_at": 2, "prompt": "newer unrelated"}),
        encoding="utf-8",
    )
    matching_path = paths.manifest_root / "000001_special_record.json"
    matching_path.write_text(
        json.dumps(
            {
                "created_at": 1,
                "prompt": "Blue heroine",
                "negative_prompt": "blurry",
                "checkpoint": "AnimeV1.safetensors",
                "seed": 4242,
                "loras": [{"path": "styles/portrait_style.safetensors"}],
            }
        ),
        encoding="utf-8",
    )

    results = read_t2i_history(
        paths,
        limit=1,
        query="BLUE blurry animev1 4242 special_record portrait_style",
    )

    assert [item["_history_filename"] for item in results] == [matching_path.name]
    assert read_t2i_history(paths, query="blue missing-token") == []


def test_history_kind_filter_classifies_only_managed_regular_non_symlink_images(
    tmp_path,
    monkeypatch,
):
    paths = AppPaths(project_root=tmp_path)
    paths.manifest_root.mkdir(parents=True)
    paths.image_root.mkdir(parents=True)
    managed_image = paths.image_root / "managed.png"
    managed_image.write_bytes(b"image")
    symlink_like_image = paths.image_root / "linked.png"
    symlink_like_image.write_bytes(b"image")
    outside_image = tmp_path / "outside.png"
    outside_image.write_bytes(b"image")
    manifests = [
        ("000004_dry_run.json", 4, None),
        ("000003_outside.json", 3, str(outside_image)),
        ("000002_symlink.json", 2, str(symlink_like_image)),
        ("000001_image.json", 1, str(managed_image)),
    ]
    for filename, created_at, output_path in manifests:
        (paths.manifest_root / filename).write_text(
            json.dumps(
                {
                    "created_at": created_at,
                    "prompt": filename,
                    "output_path": output_path,
                }
            ),
            encoding="utf-8",
        )
    original_is_symlink = Path.is_symlink
    monkeypatch.setattr(
        Path,
        "is_symlink",
        lambda path: path == symlink_like_image or original_is_symlink(path),
    )

    images = read_t2i_history(paths, limit=1, kind="images")
    dry_runs = read_t2i_history(paths, kind="dry-run")

    assert [item["_history_filename"] for item in images] == ["000001_image.json"]
    assert [item["_history_filename"] for item in dry_runs] == [
        "000004_dry_run.json",
        "000003_outside.json",
        "000002_symlink.json",
    ]


def test_history_rejects_unknown_kind(tmp_path):
    with pytest.raises(ValueError, match="history kind"):
        read_t2i_history(AppPaths(project_root=tmp_path), kind="video")


@pytest.mark.parametrize("linked_name", ["manifest-root", "manifest-file"])
def test_history_skips_linked_manifest_boundaries(tmp_path, monkeypatch, linked_name):
    paths = AppPaths(project_root=tmp_path)
    paths.manifest_root.mkdir(parents=True)
    manifest_path = paths.manifest_root / "linked-boundary.json"
    manifest_path.write_text(json.dumps({"prompt": "must not read", "created_at": 1}), encoding="utf-8")
    linked_path = paths.manifest_root if linked_name == "manifest-root" else manifest_path
    original_is_junction = getattr(Path, "is_junction", lambda path: False)
    monkeypatch.setattr(
        Path,
        "is_junction",
        lambda path: path == linked_path or original_is_junction(path),
        raising=False,
    )

    assert read_t2i_history(paths) == []


def test_manifest_write_leaves_no_partial_temp_file(tmp_path):
    paths = AppPaths(project_root=tmp_path)

    result = run_t2i(T2IRequest(prompt="atomic manifest"), paths=paths, dry_run=True)

    assert result.manifest_path.is_file()
    assert not list(paths.manifest_root.glob("*.tmp"))


def test_manifest_write_failure_leaves_no_partial_json_or_temp_file(tmp_path, monkeypatch):
    paths = AppPaths(project_root=tmp_path)

    def interrupted_dump(payload, stream, **kwargs):
        stream.write('{"partial":')
        raise OSError("write interrupted")

    monkeypatch.setattr(manifests_module.json, "dump", interrupted_dump)

    with pytest.raises(OSError, match="write interrupted"):
        run_t2i(T2IRequest(prompt="interrupted manifest"), paths=paths, dry_run=True)

    assert not list(paths.manifest_root.glob("*.json"))
    assert not list(paths.manifest_root.glob("*.tmp"))


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

import json
from pathlib import Path

from PIL import Image
from PIL.PngImagePlugin import PngInfo

from anima_app.requests import T2IRequest, UpscaleSettings
from anima_app.runtime.pipeline import T2IRenderOutput, T2IResult
from scripts.smoke_anima_app import (
    build_parser,
    build_smoke_checks,
    expected_output_size,
    main,
    request_from_args,
    smoke_checks_pass,
)


def test_smoke_request_accepts_simple_and_stage_options():
    args = build_parser().parse_args(
        [
            "--prompt",
            "anime portrait",
            "--negative",
            "low quality",
            "--width",
            "832",
            "--height",
            "1216",
            "--steps",
            "4",
            "--cfg",
            "3.5",
            "--checkpoint",
            "variants/anima-alt.safetensors",
            "--lora",
            "style.safetensors|0.8|0.7",
            "--image",
            "input.png",
            "--denoise",
            "0.42",
            "--upscale",
            "--upscale-scale",
            "1.5",
            "--upscale-steps",
            "2",
            "--upscale-denoise",
            "0.25",
            "--upscale-tiled",
            "--upscale-tile-size",
            "64",
            "--upscale-overlap",
            "8",
            "--vae-decode",
            "tiled",
            "--vae-tile-size",
            "96",
            "--vae-overlap",
            "16",
            "--face-detailer",
            "--face-detector",
            "bbox/face_yolov8m.pt",
            "--face-threshold",
            "0.45",
        ]
    )

    request = request_from_args(args)

    assert request.prompt == "anime portrait"
    assert request.negative_prompt == "low quality"
    assert request.width == 832
    assert request.height == 1216
    assert request.steps == 4
    assert request.cfg == 3.5
    assert request.checkpoint == "variants/anima-alt.safetensors"
    assert request.loras[0].path == "style.safetensors"
    assert request.loras[0].model_strength == 0.8
    assert request.loras[0].clip_strength == 0.7
    assert request.i2i.enabled is True
    assert request.i2i.image_path == "input.png"
    assert request.i2i.denoise == 0.42
    assert request.upscale.enabled is True
    assert request.upscale.scale == 1.5
    assert request.upscale.steps == 2
    assert request.upscale.denoise == 0.25
    assert request.upscale.tiled is True
    assert request.upscale.tile_size == 64
    assert request.upscale.overlap == 8
    assert request.vae_decode.mode == "tiled"
    assert request.vae_decode.tile_size == 96
    assert request.vae_decode.overlap == 16
    assert request.face_detailer.enabled is True
    assert request.face_detailer.detector == "bbox/face_yolov8m.pt"
    assert request.face_detailer.threshold == 0.45


def test_smoke_script_writes_dry_run_manifest(tmp_path, capsys):
    code = main(
        [
            "--project-root",
            str(tmp_path),
            "--prompt",
            "smoke",
            "--negative",
            "low quality",
            "--width",
            "832",
            "--height",
            "1216",
            "--dry-run",
            "--upscale",
        ]
    )

    assert code == 0
    result = json.loads(capsys.readouterr().out)
    manifest = json.loads(Path(result["manifest_path"]).read_text(encoding="utf-8"))
    assert result["status"] == "dry_run"
    assert result["checks"]["manifest_exists"] is True
    assert result["checks"]["output_exists"] is None
    assert result["warnings"] == []
    assert result["stages"]["vae_decode"] == {
        "status": "configured",
        "mode": "auto",
        "tile_size": 64,
        "overlap": 8,
        "method": "not_run",
    }
    assert manifest["prompt"] == "smoke"
    assert manifest["upscale"]["enabled"] is True


def test_smoke_script_real_run_uses_default_renderer(tmp_path, capsys, monkeypatch):
    def fake_renderer(request, active_paths):
        output_path = active_paths.image_root / "smoke-real.png"
        output_path.parent.mkdir(parents=True)
        Image.new("RGB", (request.width, request.height), "white").save(output_path)
        return T2IRenderOutput(output_path=output_path, stages={"base_t2i": {"status": "completed"}})

    monkeypatch.setattr("scripts.smoke_anima_app.default_t2i_renderer", fake_renderer)

    code = main(
        [
            "--project-root",
            str(tmp_path),
            "--prompt",
            "smoke real",
            "--width",
            "32",
            "--height",
            "48",
            "--steps",
            "1",
            "--require-checks",
        ]
    )

    assert code == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "generated"
    assert result["checks"]["output_exists"] is True
    assert result["checks"]["output_is_png"] is True
    assert result["checks"]["output_matches_request"] is True


def test_build_smoke_checks_validates_real_png_output(tmp_path):
    output = tmp_path / "outputs" / "images" / "sample.png"
    manifest_path = tmp_path / "outputs" / "manifests" / "sample.json"
    output.parent.mkdir(parents=True)
    manifest_path.parent.mkdir(parents=True)
    pnginfo = PngInfo()
    pnginfo.add_text("parameters", "prompt\nSteps: 1")
    Image.new("RGB", (32, 48), "white").save(output, pnginfo=pnginfo)
    manifest = {
        "output_path": str(output),
        "pipeline": ["tokenize", "text_encode", "base_t2i", "high_res_fix", "face_detailer"],
        "stages": {"base_t2i": {"status": "completed"}},
        "png_metadata": {"parameters": "prompt\nSteps: 1"},
    }
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    result = T2IResult(status="generated", manifest_path=manifest_path, output_path=output)

    checks = build_smoke_checks(result=result, manifest=manifest, expected_width=32, expected_height=48)

    assert checks["manifest_exists"] is True
    assert checks["output_exists"] is True
    assert checks["manifest_output_matches"] is True
    assert checks["output_is_png"] is True
    assert checks["output_width"] == 32
    assert checks["output_height"] == 48
    assert checks["output_matches_request"] is True
    assert checks["png_parameters_present"] is True
    assert checks["png_parameters_matches_manifest"] is True
    assert checks["pipeline"] == manifest["pipeline"]


def test_expected_output_size_accounts_for_upscale():
    request = T2IRequest(
        prompt="upscale",
        width=512,
        height=768,
        upscale=UpscaleSettings(enabled=True, scale=1.5),
    )

    assert expected_output_size(request) == (768, 1152)


def test_smoke_checks_pass_requires_real_output_when_requested():
    checks = {
        "manifest_exists": True,
        "output_exists": True,
        "manifest_output_matches": True,
        "output_is_png": True,
        "output_matches_request": True,
        "png_parameters_present": True,
        "png_parameters_matches_manifest": True,
    }

    assert smoke_checks_pass(checks, require_output=True) is True
    assert smoke_checks_pass({**checks, "png_parameters_matches_manifest": False}, require_output=True) is False
    assert smoke_checks_pass({**checks, "output_is_png": False}, require_output=True) is False
    assert smoke_checks_pass({"manifest_exists": True, "output_exists": None}, require_output=False) is True

import http.client
import io
import json
import os
import re
import shutil
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np
import pytest
from PIL import Image
from safetensors.numpy import save_file

from anima_app import __version__
from anima_app.assets import ANIMA_T2I_ASSET_PROFILE, FACE_DETAILER_DETECTOR_ASSET_PROFILE, required_t2i_model_files
from anima_app import requests as requests_module
from anima_app import server as server_module
from anima_app import path_safety as path_safety_module
from anima_app.config import AppPaths
from anima_app.runtime.pipeline import ModelsNotReadyError, T2IRenderOutput
from anima_app.server import (
    APP_JS,
    INDEX_HTML as INDEX_DOCUMENT,
    NAI_I18N_JS,
    NAI_ERRORS_JS,
    ProgressStore,
    create_http_server,
    handle_checkpoints,
    handle_generate,
    handle_history,
    handle_model_prepare,
    handle_readiness,
    handle_wildcard_preview,
    request_from_payload,
)


INDEX_HTML = INDEX_DOCUMENT + APP_JS


def _paths(tmp_path: Path) -> AppPaths:
    return AppPaths(
        project_root=tmp_path / "app",
        development_model_source=tmp_path / "source",
        face_detailer_detector_source=tmp_path / "detectors",
        autocomplete_source=tmp_path / "app" / "autocomplete.txt",
    )


def _write_face_detector_sources(paths: AppPaths) -> None:
    for relative_path in FACE_DETAILER_DETECTOR_ASSET_PROFILE.files:
        source = paths.face_detailer_detector_source / relative_path.name
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes((relative_path.name + "-detector").encode("utf-8") * 80)


def _write_safetensors(path: Path, *, value: float = 1.0) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    save_file({"weight": np.asarray([value], dtype=np.float32)}, str(path))


def _png_bytes(size: tuple[int, int] = (16, 12)) -> bytes:
    output = io.BytesIO()
    Image.new("RGB", size, "white").save(output, format="PNG")
    return output.getvalue()


def _write_generation_models(paths: AppPaths, checkpoint: str = "anima-base-v1.0.safetensors") -> None:
    for path in required_t2i_model_files(paths, checkpoint):
        _write_safetensors(path)


def _post_json(url: str, payload: dict[str, object], *, timeout: float = 5) -> tuple[int, dict[str, object]]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.status, json.loads(response.read().decode("utf-8"))


def _get_json(url: str, *, timeout: float = 5) -> tuple[int, dict[str, object]]:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return response.status, json.loads(response.read().decode("utf-8"))


def _raw_http_request(
    port: int,
    method: str,
    path: str,
    *,
    body: bytes | None = None,
    headers: dict[str, str] | None = None,
    shutdown_write: bool = False,
) -> tuple[int, dict[str, object]]:
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        connection.request(method, path, body=body, headers=headers or {})
        if shutdown_write:
            assert connection.sock is not None
            try:
                connection.sock.shutdown(socket.SHUT_WR)
            except OSError:
                pass
        response = connection.getresponse()
        return response.status, json.loads(response.read().decode("utf-8"))
    finally:
        connection.close()


def _input_number_attribute(document: str, element_id: str, attribute: str) -> float:
    tag = re.search(rf'<input\b[^>]*\bid="{re.escape(element_id)}"[^>]*>', document)
    assert tag is not None, f"missing input #{element_id}"
    value = re.search(rf'\b{re.escape(attribute)}="([^"]+)"', tag.group(0))
    assert value is not None, f"missing {attribute} on input #{element_id}"
    return float(value.group(1))


def test_path_link_detection_falls_back_to_windows_reparse_attributes(tmp_path, monkeypatch):
    candidate = tmp_path / "junction-like"
    candidate.mkdir()
    reparse_flag = 1024
    original_lstat = Path.lstat
    monkeypatch.setattr(Path, "is_symlink", lambda path: False)
    monkeypatch.setattr(Path, "is_junction", lambda path: False, raising=False)
    monkeypatch.setattr(path_safety_module.stat, "FILE_ATTRIBUTE_REPARSE_POINT", reparse_flag, raising=False)

    def fake_lstat(path, *args, **kwargs):
        if path == candidate:
            return type("ReparseStat", (), {"st_file_attributes": reparse_flag})()
        return original_lstat(path, *args, **kwargs)

    monkeypatch.setattr(Path, "lstat", fake_lstat)

    assert path_safety_module.path_is_link(candidate) is True


def _wait_for(condition, *, timeout: float = 5) -> dict[str, object]:
    import time

    deadline = time.time() + timeout
    last: dict[str, object] = {}
    while time.time() < deadline:
        last = condition()
        if last.get("ready"):
            return last
        time.sleep(0.05)
    raise AssertionError(f"condition was not ready before timeout: {last}")


def test_request_from_payload_accepts_gui_fields():
    request = request_from_payload(
        {
            "prompt": "anime portrait",
            "negative_prompt": "low quality",
            "memory_profile": "low_vram_highres",
            "width": 512,
            "height": 768,
            "steps": 2,
            "cfg": 1.5,
            "sampler": "euler_ancestral_cfg_pp",
            "scheduler": "sgm_uniform",
            "seed": 123,
            "checkpoint": "variants/anima-alt.safetensors",
            "loras": [{"path": "style.safetensors", "model_strength": 0.5, "clip_strength": 0.25}],
            "i2i": {"enabled": True, "image_path": "inputs/reference.png", "denoise": 0.4},
            "upscale": {
                "enabled": True,
                "scale": 1.5,
                "steps": 2,
                "denoise": 0.25,
                "method": "bicubic",
                "tiled": True,
                "tile_size": 64,
                "overlap": 8,
            },
            "vae_decode": {"mode": "tiled", "tile_size": 96, "overlap": 16},
            "face_detailer": {
                "enabled": True,
                "detector": "bbox/face_yolov8m.pt",
                "mask_backend": "sam3",
                "threshold": 0.45,
                "crop_scale": 1.6,
                "padding": 40,
                "feather": 20,
                "exclude_forehead_ratio": 0.25,
                "steps": 3,
                "denoise": 0.22,
                "sam3_face_eyes": True,
                "sam3_hands": True,
                "hand_denoise": 0.36,
            },
        }
    )

    assert request.prompt == "anime portrait"
    assert request.negative_prompt == "low quality"
    assert request.memory_profile == "low_vram_highres"
    assert request.width == 512
    assert request.height == 768
    assert request.sampler == "euler_ancestral_cfg_pp"
    assert request.scheduler == "sgm_uniform"
    assert request.checkpoint == "variants/anima-alt.safetensors"
    assert request.loras[0].path == "style.safetensors"
    assert request.i2i.enabled is True
    assert request.upscale.enabled is True
    assert request.upscale.tiled is True
    assert request.upscale.tile_size == 64
    assert request.upscale.overlap == 8
    assert request.vae_decode.mode == "tiled"
    assert request.vae_decode.tile_size == 96
    assert request.vae_decode.overlap == 16
    assert request.face_detailer.enabled is True
    assert request.face_detailer.detector == "bbox/face_yolov8m.pt"
    assert request.face_detailer.mask_backend == "sam3"
    assert request.face_detailer.threshold == 0.45
    assert request.face_detailer.exclude_forehead_ratio == 0.25
    assert request.face_detailer.sam3_face_eyes is True
    assert request.face_detailer.sam3_hands is True
    assert request.face_detailer.hand_denoise == 0.36


@pytest.mark.parametrize(
    "settings",
    [
        {"i2i": {"enabled": "false", "image_path": "inputs/references/example.png"}},
        {"upscale": {"enabled": "false"}},
        {"upscale": {"tiled": "false"}},
        {"face_detailer": {"enabled": "false"}},
        {"face_detailer": {"sam3_face_eyes": "false"}},
        {"face_detailer": {"sam3_hands": "false"}},
    ],
)
def test_request_from_payload_rejects_non_boolean_feature_flags(settings):
    with pytest.raises(ValueError, match="boolean"):
        request_from_payload({"prompt": "strict flags", **settings})


@pytest.mark.parametrize(
    "settings",
    [
        {"width": 512.9},
        {"height": True},
        {"steps": 1.9},
        {"cfg": True},
        {"loras": [{"path": "style.safetensors", "model_strength": True}]},
        {"i2i": {"denoise": True}},
        {"upscale": {"steps": 1.9}},
        {"upscale": {"tile_size": 64.9}},
        {"upscale": {"overlap": True}},
        {"vae_decode": {"tile_size": 64.9}},
        {"face_detailer": {"padding": 32.9}},
        {"face_detailer": {"threshold": True}},
    ],
)
def test_request_from_payload_rejects_lossy_numeric_coercions(settings):
    with pytest.raises(ValueError, match="must be"):
        request_from_payload({"prompt": "strict numbers", **settings})


def test_request_from_payload_uses_default_generation_settings():
    request = request_from_payload({"prompt": "anime portrait"})

    assert request.width == 832
    assert request.height == 1216
    assert request.steps == 20
    assert request.cfg == 3.5
    assert request.sampler == "euler_ancestral_cfg_pp"
    assert request.scheduler == "sgm_uniform"
    assert request.memory_profile == "auto"


def test_handle_generate_dry_run_returns_manifest_without_gpu(tmp_path):
    paths = _paths(tmp_path)

    status, payload = handle_generate(
        {
            "prompt": "anime portrait",
            "width": 512,
            "height": 768,
            "checkpoint": "variants/anima-alt.safetensors",
            "dry_run": True,
        },
        paths=paths,
    )
    manifest = json.loads(Path(payload["manifest_path"]).read_text(encoding="utf-8"))

    assert status == 200
    assert payload["status"] == "dry_run"
    assert payload["checkpoint"] == "variants/anima-alt.safetensors"
    assert manifest["checkpoint"] == "variants/anima-alt.safetensors"
    assert payload["output_path"] is None
    assert payload["output_url"] is None
    assert Path(payload["manifest_path"]).is_file()


def test_handle_generate_expands_wildcards_and_returns_manifest_metadata(tmp_path):
    paths = _paths(tmp_path)
    wildcard_file = paths.project_root / "wildcards" / "style.txt"
    wildcard_file.parent.mkdir(parents=True)
    wildcard_file.write_text("soft lineart\n", encoding="utf-8")

    status, payload = handle_generate(
        {
            "prompt": "anime portrait, __style__",
            "width": 512,
            "height": 768,
            "seed": 52,
            "wildcard_mode": "random",
            "dry_run": True,
        },
        paths=paths,
    )
    manifest = json.loads(Path(payload["manifest_path"]).read_text(encoding="utf-8"))

    assert status == 200
    assert payload["wildcards"]["mode"] == "random"
    assert manifest["prompt"] == "anime portrait, soft lineart"
    assert manifest["wildcards"]["original_prompt"] == "anime portrait, __style__"


def test_handle_generate_expands_prompt_preset_wildcard(tmp_path):
    paths = _paths(tmp_path)
    preset_file = paths.project_root / "wildcards" / "presets" / "portrait_clean.txt"
    preset_file.parent.mkdir(parents=True)
    preset_file.write_text("clean portrait preset\n", encoding="utf-8")

    status, payload = handle_generate(
        {
            "prompt": "anime portrait, __presets/portrait_clean__",
            "width": 512,
            "height": 768,
            "seed": 52,
            "wildcard_mode": "random",
            "dry_run": True,
        },
        paths=paths,
    )
    manifest = json.loads(Path(payload["manifest_path"]).read_text(encoding="utf-8"))

    assert status == 200
    assert manifest["prompt"] == "anime portrait, clean portrait preset"
    assert manifest["wildcards"]["selections"] == [
        {
            "token": "__presets/portrait_clean__",
            "wildcard": "presets/portrait_clean",
            "file": str(preset_file),
            "mode": "random",
            "index": 0,
            "value": "clean portrait preset",
        }
    ]


def test_handle_generate_expands_unicode_prompt_preset_wildcard(tmp_path):
    paths = _paths(tmp_path)
    preset_file = paths.project_root / "wildcards" / "presets" / "프리셋예시.txt"
    preset_file.parent.mkdir(parents=True)
    preset_file.write_text("soft anime preset\n", encoding="utf-8")

    status, payload = handle_generate(
        {
            "prompt": "anime portrait, __presets/프리셋예시__",
            "width": 512,
            "height": 768,
            "seed": 52,
            "wildcard_mode": "random",
            "dry_run": True,
        },
        paths=paths,
    )
    manifest = json.loads(Path(payload["manifest_path"]).read_text(encoding="utf-8"))

    assert status == 200
    assert manifest["prompt"] == "anime portrait, soft anime preset"
    assert manifest["wildcards"]["selections"][0]["wildcard"] == "presets/프리셋예시"


def test_handle_generate_rejects_wildcard_path_traversal(tmp_path):
    paths = _paths(tmp_path)
    outside = paths.project_root / "secret.txt"
    outside.parent.mkdir(parents=True)
    outside.write_text("should not expand\n", encoding="utf-8")

    status, payload = handle_generate(
        {
            "prompt": "anime portrait, __presets/../secret__",
            "width": 512,
            "height": 768,
            "dry_run": True,
        },
        paths=paths,
    )

    assert status == 400
    assert "invalid wildcard name" in payload["error"]


def test_handle_wildcard_preview_expands_nested_and_inline_random(tmp_path):
    paths = _paths(tmp_path)
    wildcard_dir = paths.project_root / "wildcards"
    wildcard_dir.mkdir(parents=True)
    (wildcard_dir / "character.txt").write_text("qiqi, __hair__, {soft smile|serious expression}\n", encoding="utf-8")
    (wildcard_dir / "hair.txt").write_text("purple hair\n", encoding="utf-8")

    status, payload = handle_wildcard_preview(
        {
            "prompt": "__character__",
            "negative_prompt": "{low quality|bad anatomy}",
            "seed": 12,
            "wildcard_mode": "random",
        },
        paths=paths,
    )

    assert status == 200
    assert payload["enabled"] is True
    assert payload["prompt"] in {
        "qiqi, purple hair, soft smile",
        "qiqi, purple hair, serious expression",
    }
    assert payload["negative_prompt"] in {"low quality", "bad anatomy"}
    assert payload["selection_count"] == 4
    assert payload["error"] == ""


def test_handle_wildcard_preview_returns_400_for_invalid_tokens(tmp_path):
    status, payload = handle_wildcard_preview(
        {"prompt": "__missing__", "wildcard_mode": "random"},
        paths=_paths(tmp_path),
    )

    assert status == 400
    assert payload["prompt"] == "__missing__"
    assert "wildcard file not found" in payload["error"]


def test_handle_generate_real_run_exposes_output_url(tmp_path):
    paths = _paths(tmp_path)

    def fake_renderer(request, active_paths):
        output_path = active_paths.image_root / "api-real.png"
        output_path.parent.mkdir(parents=True)
        Image.new("RGB", (request.width, request.height), "white").save(output_path)
        return T2IRenderOutput(output_path=output_path, stages={"base_t2i": {"status": "completed"}})

    status, payload = handle_generate(
        {"prompt": "anime portrait", "width": 32, "height": 48, "steps": 1, "dry_run": False},
        paths=paths,
        renderer=fake_renderer,
    )

    assert status == 200
    assert payload["status"] == "generated"
    assert payload["output_url"] == "/outputs/images/api-real.png"
    assert Path(payload["output_path"]).is_file()
    assert payload["stages"]["base_t2i"]["status"] == "completed"


def test_handle_generate_real_run_exposes_compare_variants(tmp_path):
    paths = _paths(tmp_path)

    def fake_renderer(request, active_paths):
        variants = {
            "original": active_paths.image_root / "compare-original.png",
            "upscale": active_paths.image_root / "compare-upscale.png",
            "face_detailer": active_paths.image_root / "compare-face.png",
        }
        colors = {"original": "white", "upscale": "gray", "face_detailer": "black"}
        for name, output_path in variants.items():
            output_path.parent.mkdir(parents=True, exist_ok=True)
            Image.new("RGB", (request.width, request.height), colors[name]).save(output_path)
        return T2IRenderOutput(
            output_path=variants["face_detailer"],
            stages={
                "base_t2i": {"status": "completed"},
                "high_res_fix": {"status": "completed"},
                "face_detailer": {"status": "completed"},
            },
            variants=variants,
        )

    status, payload = handle_generate(
        {
            "prompt": "anime portrait",
            "width": 32,
            "height": 48,
            "steps": 1,
            "upscale": {"enabled": True, "scale": 1.5},
            "face_detailer": {"enabled": True},
            "dry_run": False,
        },
        paths=paths,
        renderer=fake_renderer,
    )

    manifest = json.loads(Path(payload["manifest_path"]).read_text(encoding="utf-8"))

    assert status == 200
    assert payload["output_url"] == "/outputs/images/compare-face.png"
    assert payload["variants"]["original"]["output_url"] == "/outputs/images/compare-original.png"
    assert payload["variants"]["upscale"]["output_url"] == "/outputs/images/compare-upscale.png"
    assert payload["variants"]["face_detailer"]["output_url"] == "/outputs/images/compare-face.png"
    assert manifest["variants"]["original"]["output_path"].endswith("compare-original.png")
    assert manifest["variants"]["upscale"]["output_path"].endswith("compare-upscale.png")
    assert manifest["variants"]["face_detailer"]["output_path"].endswith("compare-face.png")


def test_handle_generate_invalid_request_returns_400(tmp_path):
    status, payload = handle_generate({"prompt": "", "width": 512, "height": 768, "dry_run": True}, paths=_paths(tmp_path))

    assert status == 400
    assert "prompt is required" in payload["error"]


def test_handle_generate_rejects_resource_limit_before_renderer(tmp_path):
    paths = _paths(tmp_path)
    _write_generation_models(paths)
    render_calls = 0

    def renderer(request, active_paths):
        nonlocal render_calls
        render_calls += 1
        output_path = active_paths.image_root / "resource-limit-should-not-render.png"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (1, 1), "white").save(output_path)
        return T2IRenderOutput(output_path=output_path, stages={"base_t2i": {"status": "completed"}})

    status, payload = handle_generate(
        {
            "prompt": "too wide",
            "width": requests_module.MAX_GENERATION_DIMENSION + 8,
            "height": 8,
            "steps": 1,
            "dry_run": False,
        },
        paths=paths,
        renderer=renderer,
    )

    assert status == 400
    assert payload["error_code"] == "generation_invalid_request"
    assert render_calls == 0


def test_handle_generate_missing_file_returns_structured_error(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    paths = AppPaths(project_root=Path("app"))
    missing_model = (paths.model_root / "diffusion_models" / "model.safetensors").resolve()
    progress_store = ProgressStore()

    def missing_file_renderer(request, active_paths):
        raise ModelsNotReadyError((missing_model,))

    status, payload = handle_generate(
        {
            "prompt": "anime portrait",
            "width": 32,
            "height": 48,
            "steps": 1,
            "dry_run": False,
            "memory_profile": "balanced",
            "progress_id": "missing-model",
        },
        paths=paths,
        renderer=missing_file_renderer,
        progress_store=progress_store,
    )

    assert status == 409
    assert payload == {
        "error_code": "models_not_ready",
        "error": "필수 모델 파일이 없거나 손상되었습니다.",
        "missing_files": ["diffusion_models/model.safetensors"],
        "invalid_files": [],
    }
    progress = progress_store.get("missing-model")
    assert progress["status"] == "failed"
    assert progress["error"] == payload["error"]
    assert progress["summary"] == f"실패: {payload['error']}"


def test_handle_generate_missing_input_returns_400(tmp_path):
    def missing_input_renderer(request, active_paths):
        raise FileNotFoundError("missing i2i source image: inputs/missing.png")

    status, payload = handle_generate(
        {"prompt": "anime portrait", "width": 32, "height": 48, "steps": 1, "dry_run": False},
        paths=_paths(tmp_path),
        renderer=missing_input_renderer,
    )

    assert status == 400
    assert payload == {
        "error_code": "generation_input_missing",
        "error": "생성에 필요한 입력 파일을 찾을 수 없습니다: missing i2i source image: inputs/missing.png",
    }


def test_handle_generate_runtime_failure_returns_structured_error(tmp_path):
    def failing_renderer(request, active_paths):
        raise RuntimeError("CUDA out of memory")

    status, payload = handle_generate(
        {"prompt": "anime portrait", "width": 32, "height": 48, "steps": 1, "dry_run": False},
        paths=_paths(tmp_path),
        renderer=failing_renderer,
    )

    assert status == 500
    assert payload == {
        "error_code": "generation_failed",
        "error": "이미지 생성 중 오류가 발생했습니다: CUDA out of memory",
    }


def test_handle_generate_os_failure_returns_structured_error_and_failed_progress(tmp_path):
    progress_store = ProgressStore()

    def failing_renderer(request, active_paths):
        raise OSError("disk full")

    status, payload = handle_generate(
        {
            "prompt": "anime portrait",
            "width": 32,
            "height": 48,
            "steps": 1,
            "dry_run": False,
            "progress_id": "disk-error",
        },
        paths=_paths(tmp_path),
        renderer=failing_renderer,
        progress_store=progress_store,
    )

    assert status == 500
    assert payload == {
        "error_code": "generation_failed",
        "error": "이미지 생성 중 오류가 발생했습니다: disk full",
    }
    assert progress_store.get("disk-error")["status"] == "failed"


def test_handle_model_prepare_os_failure_returns_structured_error(tmp_path, monkeypatch):
    def failing_copy(profile, paths, *, source):
        raise OSError("network unavailable")

    monkeypatch.setattr("anima_app.server.copy_asset_profile", failing_copy)

    status, payload = handle_model_prepare(
        {"profile": "anima-t2i", "source": "auto"},
        paths=_paths(tmp_path),
    )

    assert status == 500
    assert payload == {
        "error_code": "model_prepare_failed",
        "error": "모델 준비 중 오류가 발생했습니다: network unavailable",
    }


def test_readiness_rejects_zero_byte_model_files(tmp_path):
    paths = _paths(tmp_path)
    for relative_path in ANIMA_T2I_ASSET_PROFILE.files:
        destination = paths.model_root / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"")

    payload = handle_readiness(paths=paths)
    profile = next(item for item in payload["profiles"] if item["name"] == "anima-t2i")

    assert profile["ready"] is False
    assert profile["missing_count"] == 0
    assert profile["invalid_count"] == 3
    assert all(item["exists"] is True for item in profile["files"])
    assert all(item["valid"] is False for item in profile["files"])
    assert {item["status"] for item in profile["files"]} == {"invalid"}


def test_readiness_separates_install_roles_from_selected_checkpoint_gate(tmp_path):
    paths = _paths(tmp_path)
    custom_checkpoint = paths.model_root / "diffusion_models" / "variants" / "custom.safetensors"
    text_encoder = paths.model_root / "text_encoders" / "qwen_3_06b_base.safetensors"
    vae = paths.model_root / "vae" / "qwen_image_vae.safetensors"
    for path in (custom_checkpoint, text_encoder, vae):
        _write_safetensors(path)

    payload = handle_readiness(paths=paths, checkpoint="variants/custom.safetensors")
    requirements = {item["name"]: item["requirement"] for item in payload["profiles"]}

    assert payload["ready"] is False
    assert payload["required_ready"] is False
    assert requirements == {
        "anima-t2i": "required",
        "anima-aesthetic-v1.1": "recommended",
        "face-detailer-detectors": "optional",
        "sam3-detector": "optional",
    }
    assert payload["generation"] == {
        "ready": True,
        "checkpoint": "variants/custom.safetensors",
        "dry_run": False,
        "missing_files": [],
        "invalid_files": [],
    }

    missing = handle_readiness(paths=paths, checkpoint="variants/missing.safetensors")["generation"]
    assert missing["ready"] is False
    assert missing["missing_files"] == ["diffusion_models/variants/missing.safetensors"]


def test_checkpoints_defaults_to_available_custom_checkpoint(tmp_path):
    paths = _paths(tmp_path)
    checkpoint = paths.model_root / "diffusion_models" / "variants" / "custom.safetensors"
    _write_safetensors(checkpoint)

    payload = handle_checkpoints(paths=paths)

    assert payload["default"] == "variants/custom.safetensors"


def test_checkpoints_skip_corrupt_preferred_default_when_base_is_valid(tmp_path):
    paths = _paths(tmp_path)
    preferred = paths.model_root / "diffusion_models" / "anima-aesthetic-v1.1.safetensors"
    preferred.parent.mkdir(parents=True, exist_ok=True)
    preferred.write_bytes(b"not a safetensors file")
    _write_safetensors(paths.model_root / "diffusion_models" / "anima-base-v1.0.safetensors")

    payload = handle_checkpoints(paths=paths)

    assert payload["default"] == "anima-base-v1.0.safetensors"


def test_handle_generate_uses_available_custom_checkpoint_when_request_omits_one(tmp_path):
    paths = _paths(tmp_path)
    checkpoint = paths.model_root / "diffusion_models" / "variants" / "custom.safetensors"
    _write_safetensors(checkpoint)

    status, payload = handle_generate(
        {"prompt": "custom default", "width": 32, "height": 48, "steps": 1, "dry_run": True},
        paths=paths,
    )

    assert status == 200
    assert payload["checkpoint"] == "variants/custom.safetensors"


def test_http_model_prepare_failure_returns_json_instead_of_closing_connection(tmp_path, monkeypatch):
    def failing_copy(profile, paths, *, source):
        raise OSError("network unavailable")

    monkeypatch.setattr("anima_app.server.copy_asset_profile", failing_copy)
    server = create_http_server("127.0.0.1", 0, paths=_paths(tmp_path), default_dry_run=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        request = urllib.request.Request(
            f"http://127.0.0.1:{server.server_address[1]}/api/models/prepare",
            data=json.dumps({"profile": "anima-t2i", "source": "auto"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with pytest.raises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(request, timeout=5)

        assert caught.value.code == 500
        assert caught.value.headers.get_content_type() == "application/json"
        payload = json.loads(caught.value.read().decode("utf-8"))
        assert payload["error_code"] == "model_prepare_failed"
        assert "network unavailable" in payload["error"]
    finally:
        server.shutdown()
        server.server_close()


def test_http_server_serves_index_and_dry_run_generate(tmp_path):
    server = create_http_server("127.0.0.1", 0, paths=_paths(tmp_path), default_dry_run=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        index_body = urllib.request.urlopen(base_url, timeout=5).read().decode("utf-8")
        assert "Anima APP" in index_body
        assert '<script src="/app.js"></script>' in index_body
        assert index_body.index('src="/nai-i18n.js"') < index_body.index('src="/app.js"')
        assert index_body.index('src="/nai-i18n.js"') < index_body.index('src="/nai-errors.js"') < index_body.index('src="/app.js"')
        with urllib.request.urlopen(f"{base_url}/nai-errors.js", timeout=5) as response:
            assert response.status == 200
            assert response.headers.get_content_type() == "text/javascript"
            assert response.read().decode("utf-8") == NAI_ERRORS_JS
        with urllib.request.urlopen(f"{base_url}/nai-i18n.js", timeout=5) as response:
            assert response.status == 200
            assert response.headers.get_content_type() == "text/javascript"
            assert response.read().decode("utf-8") == NAI_I18N_JS
        with urllib.request.urlopen(f"{base_url}/app.js", timeout=5) as response:
            assert response.status == 200
            assert response.headers.get_content_type() == "text/javascript"
            assert "const animaDefaults" in response.read().decode("utf-8")
        with urllib.request.urlopen(f"{base_url}/favicon.ico", timeout=5) as response:
            assert response.status == 204

        request = urllib.request.Request(
            f"{base_url}/api/generate",
            data=json.dumps({"prompt": "anime portrait", "width": 512, "height": 768}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))

        assert response.status == 200
        assert payload["status"] == "dry_run"
        assert Path(payload["manifest_path"]).is_file()
    finally:
        server.shutdown()
        server.server_close()


def test_http_server_rejects_untrusted_host_header(tmp_path):
    server = create_http_server("127.0.0.1", 0, paths=_paths(tmp_path), default_dry_run=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status, payload = _raw_http_request(
            server.server_address[1],
            "GET",
            "/api/health",
            headers={"Host": "evil.example"},
        )

        assert status == 403
        assert payload["error_code"] == "request_host_untrusted"
    finally:
        server.shutdown()
        server.server_close()


def test_http_server_rejects_host_header_without_active_port(tmp_path):
    server = create_http_server("127.0.0.1", 0, paths=_paths(tmp_path), default_dry_run=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status, payload = _raw_http_request(
            server.server_address[1],
            "GET",
            "/api/health",
            headers={"Host": "127.0.0.1"},
        )

        assert status == 403
        assert payload["error_code"] == "request_host_untrusted"
    finally:
        server.shutdown()
        server.server_close()


def test_create_http_server_rejects_ipv6_loopback_bind(tmp_path):
    with pytest.raises(ValueError, match="IPv4 loopback"):
        create_http_server("::1", 0, paths=_paths(tmp_path), default_dry_run=True)


def test_create_http_server_closes_job_queue_when_bind_fails(tmp_path, monkeypatch):
    close_calls = []
    original_close = server_module.JobQueue.close

    def tracked_close(queue):
        close_calls.append(queue)
        original_close(queue)

    monkeypatch.setattr(server_module.JobQueue, "close", tracked_close)
    blocker = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    blocker.bind(("127.0.0.1", 0))
    blocker.listen()
    try:
        with pytest.raises(OSError):
            create_http_server(
                "127.0.0.1",
                blocker.getsockname()[1],
                paths=_paths(tmp_path),
                default_dry_run=True,
            )
    finally:
        blocker.close()

    assert len(close_calls) == 1


def test_http_server_rejects_cross_origin_mutation_and_allows_same_origin(tmp_path):
    server = create_http_server("127.0.0.1", 0, paths=_paths(tmp_path), default_dry_run=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        port = server.server_address[1]
        body = json.dumps({"prompt": "plain portrait"}).encode("utf-8")
        cross_status, cross_payload = _raw_http_request(
            port,
            "POST",
            "/api/wildcards/preview",
            body=body,
            headers={"Content-Type": "application/json", "Origin": "https://evil.example"},
        )
        same_status, same_payload = _raw_http_request(
            port,
            "POST",
            "/api/wildcards/preview",
            body=body,
            headers={"Content-Type": "application/json", "Origin": f"http://127.0.0.1:{port}"},
        )

        assert cross_status == 403
        assert cross_payload["error_code"] == "request_origin_untrusted"
        assert same_status == 200
        assert same_payload["prompt"] == "plain portrait"
    finally:
        server.shutdown()
        server.server_close()


def test_http_server_requires_application_json_for_mutation(tmp_path):
    server = create_http_server("127.0.0.1", 0, paths=_paths(tmp_path), default_dry_run=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status, payload = _raw_http_request(
            server.server_address[1],
            "POST",
            "/api/wildcards/preview",
            body=b'{"prompt":"plain portrait"}',
            headers={"Content-Type": "text/plain"},
        )

        assert status == 415
        assert "error" in payload
    finally:
        server.shutdown()
        server.server_close()


def test_http_server_rejects_non_object_json_body(tmp_path):
    server = create_http_server("127.0.0.1", 0, paths=_paths(tmp_path), default_dry_run=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status, payload = _raw_http_request(
            server.server_address[1],
            "POST",
            "/api/wildcards/preview",
            body=b"[]",
            headers={"Content-Type": "application/json"},
        )

        assert status == 400
        assert "error" in payload
    finally:
        server.shutdown()
        server.server_close()


def test_http_server_rejects_overflowing_json_number_without_closing_connection(tmp_path):
    server = create_http_server("127.0.0.1", 0, paths=_paths(tmp_path), default_dry_run=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status, payload = _raw_http_request(
            server.server_address[1],
            "POST",
            "/api/wildcards/preview",
            body=b'{"prompt":"portrait","seed":1e999}',
            headers={"Content-Type": "application/json"},
        )

        assert status == 400
        assert payload["error_code"] == "request_json_invalid"
    finally:
        server.shutdown()
        server.server_close()


def test_http_server_rejects_excessive_json_nesting_without_closing_connection(tmp_path):
    server = create_http_server("127.0.0.1", 0, paths=_paths(tmp_path), default_dry_run=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        depth = server_module.MAX_JSON_NESTING_DEPTH + 1
        body = (b'{"nested":' * depth) + b"{}" + (b"}" * depth)
        status, payload = _raw_http_request(
            server.server_address[1],
            "POST",
            "/api/jobs",
            body=body,
            headers={"Content-Type": "application/json"},
        )

        assert status == 400
        assert payload["error_code"] == "request_json_invalid"
    finally:
        server.shutdown()
        server.server_close()


@pytest.mark.parametrize("escaped_surrogate", [b"\\ud800", b"\\udfff"])
def test_http_server_rejects_unpaired_json_surrogate_without_poisoning_queue(tmp_path, escaped_surrogate):
    server = create_http_server("127.0.0.1", 0, paths=_paths(tmp_path), default_dry_run=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        body = (
            b'{"request":{"prompt":"'
            + escaped_surrogate
            + b'","width":32,"height":48,"steps":1,"dry_run":true}}'
        )
        status, payload = _raw_http_request(
            server.server_address[1],
            "POST",
            "/api/jobs",
            body=body,
            headers={"Content-Type": "application/json"},
        )
        jobs_status, jobs = _get_json(f"http://127.0.0.1:{server.server_address[1]}/api/jobs")

        assert status == 400
        assert payload["error_code"] == "request_json_invalid"
        assert jobs_status == 200
        assert jobs["count"] == 0
    finally:
        server.shutdown()
        server.server_close()


@pytest.mark.parametrize("content_length", ["not-a-number", "-1"])
def test_http_server_rejects_malformed_or_negative_content_length(tmp_path, content_length):
    server = create_http_server("127.0.0.1", 0, paths=_paths(tmp_path), default_dry_run=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status, payload = _raw_http_request(
            server.server_address[1],
            "POST",
            "/api/wildcards/preview",
            body=b'{}',
            headers={"Content-Type": "application/json", "Content-Length": content_length},
            shutdown_write=True,
        )

        assert status == 400
        assert "error" in payload
    finally:
        server.shutdown()
        server.server_close()


def test_http_server_rejects_json_body_over_limit(tmp_path):
    server = create_http_server("127.0.0.1", 0, paths=_paths(tmp_path), default_dry_run=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status, payload = _raw_http_request(
            server.server_address[1],
            "POST",
            "/api/wildcards/preview",
            headers={
                "Content-Type": "application/json",
                "Content-Length": str(server_module.MAX_JSON_BODY_BYTES + 1),
            },
            shutdown_write=True,
        )

        assert status == 413
        assert "error" in payload
    finally:
        server.shutdown()
        server.server_close()


def test_create_http_server_rejects_non_loopback_bind(tmp_path):
    server = None
    try:
        with pytest.raises(ValueError, match="loopback"):
            server = create_http_server("0.0.0.0", 0, paths=_paths(tmp_path), default_dry_run=True)
    finally:
        if server is not None:
            server.server_close()


def test_http_server_returns_structured_model_error(tmp_path):
    paths = _paths(tmp_path)
    missing_model = paths.model_root / "diffusion_models" / "model.safetensors"

    def missing_model_renderer(request, active_paths):
        raise ModelsNotReadyError((missing_model,))

    server = create_http_server("127.0.0.1", 0, paths=paths, renderer=missing_model_renderer)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        request = urllib.request.Request(
            f"{base_url}/api/generate",
            data=json.dumps(
                {
                    "prompt": "missing model",
                    "width": 32,
                    "height": 48,
                    "steps": 1,
                    "dry_run": False,
                    "memory_profile": "balanced",
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            urllib.request.urlopen(request, timeout=5)
        except urllib.error.HTTPError as exc:
            assert exc.code == 409
            payload = json.loads(exc.read().decode("utf-8"))
        else:
            raise AssertionError("expected HTTP 409 for missing required models")

        assert payload == {
            "error_code": "models_not_ready",
            "error": "필수 모델 파일이 없거나 손상되었습니다.",
            "missing_files": ["diffusion_models/model.safetensors"],
            "invalid_files": [],
        }
    finally:
        server.shutdown()
        server.server_close()


def test_http_server_exposes_generation_progress_while_request_runs(tmp_path):
    paths = _paths(tmp_path)
    renderer_started = threading.Event()
    finish_render = threading.Event()

    def slow_renderer(request, active_paths):
        renderer_started.set()
        assert finish_render.wait(timeout=5)
        output_path = active_paths.image_root / "progress-real.png"
        output_path.parent.mkdir(parents=True)
        Image.new("RGB", (request.width, request.height), "white").save(output_path)
        return T2IRenderOutput(output_path=output_path, stages={"base_t2i": {"status": "completed"}})

    server = create_http_server("127.0.0.1", 0, paths=paths, renderer=slow_renderer)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    post_result: dict[str, object] = {}

    def post_generate() -> None:
        request = urllib.request.Request(
            f"http://127.0.0.1:{server.server_address[1]}/api/generate",
            data=json.dumps(
                {
                    "prompt": "anime portrait",
                    "width": 32,
                    "height": 48,
                    "steps": 1,
                    "dry_run": False,
                    "progress_id": "progress-job",
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            post_result["status"] = response.status
            post_result["payload"] = json.loads(response.read().decode("utf-8"))

    post_thread = threading.Thread(target=post_generate, daemon=True)
    post_thread.start()
    try:
        assert renderer_started.wait(timeout=5)
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        with urllib.request.urlopen(f"{base_url}/api/progress/progress-job", timeout=5) as response:
            running = json.loads(response.read().decode("utf-8"))

        assert response.status == 200
        assert running["progress_id"] == "progress-job"
        assert running["status"] == "running"
        assert running["stages"]["request"]["status"] == "completed"
        assert running["stages"]["base_t2i"]["status"] == "active"

        finish_render.set()
        post_thread.join(timeout=5)
        assert not post_thread.is_alive()
        assert post_result["status"] == 200

        with urllib.request.urlopen(f"{base_url}/api/progress/progress-job", timeout=5) as response:
            completed = json.loads(response.read().decode("utf-8"))

        assert completed["status"] == "completed"
        assert completed["stages"]["base_t2i"]["status"] == "completed"
        assert completed["stages"]["metadata"]["status"] == "completed"
        assert completed["result"]["status"] == "generated"
    finally:
        finish_render.set()
        server.shutdown()
        server.server_close()


def test_http_server_enqueues_and_completes_server_jobs(tmp_path):
    server = create_http_server("127.0.0.1", 0, paths=_paths(tmp_path), default_dry_run=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        status, queued = _post_json(
            f"{base_url}/api/jobs",
            {
                "count": 2,
                "request": {"prompt": "anime portrait", "width": 32, "height": 48, "dry_run": True},
            },
        )

        assert status == 202
        assert queued["status"] == "queued"
        assert queued["count"] == 2
        assert len(queued["jobs"]) == 2
        assert queued["jobs"][0]["status"] == "queued"

        def jobs_complete() -> dict[str, object]:
            _, payload = _get_json(f"{base_url}/api/jobs")
            completed = [item for item in payload["items"] if item["status"] == "completed"]
            return {"ready": len(completed) == 2, "payload": payload}

        completed = _wait_for(jobs_complete)
        payload = completed["payload"]
        assert payload["summary"]["completed"] == 2
        assert payload["summary"]["queued"] == 0
        assert all(item["result"]["status"] == "dry_run" for item in payload["items"])
    finally:
        server.shutdown()
        server.server_close()


def test_http_server_rejects_invalid_job_request_before_enqueuing(tmp_path):
    server = create_http_server("127.0.0.1", 0, paths=_paths(tmp_path), default_dry_run=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        status, payload = _raw_http_request(
            server.server_address[1],
            "POST",
            "/api/jobs",
            body=json.dumps(
                {
                    "request": {
                        "prompt": "too wide",
                        "width": requests_module.MAX_GENERATION_DIMENSION + 8,
                        "height": 8,
                        "steps": 1,
                        "dry_run": True,
                    }
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        _, jobs = _get_json(f"{base_url}/api/jobs")

        assert status == 400
        assert payload["error_code"] == "generation_invalid_request"
        assert jobs["count"] == 0
    finally:
        server.shutdown()
        server.server_close()


@pytest.mark.parametrize("endpoint", ["/api/generate", "/api/jobs"])
@pytest.mark.parametrize("seed", [True, 1.5, requests_module.MAX_SEED + 1])
def test_http_generation_endpoints_reject_invalid_seed_types_and_range(tmp_path, endpoint, seed):
    server = create_http_server("127.0.0.1", 0, paths=_paths(tmp_path), default_dry_run=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        generation = {
            "prompt": "strict seed",
            "width": 32,
            "height": 48,
            "steps": 1,
            "seed": seed,
            "dry_run": True,
        }
        body = {"request": generation} if endpoint == "/api/jobs" else generation
        status, payload = _raw_http_request(
            server.server_address[1],
            "POST",
            endpoint,
            body=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )

        assert status == 400
        assert payload["error_code"] == "generation_invalid_request"
        assert "seed" in payload["error"]
    finally:
        server.shutdown()
        server.server_close()


@pytest.mark.parametrize("endpoint", ["/api/generate", "/api/jobs"])
def test_http_generation_endpoints_reject_non_boolean_dry_run(tmp_path, endpoint):
    server = create_http_server("127.0.0.1", 0, paths=_paths(tmp_path), default_dry_run=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        generation = {"prompt": "strict dry run", "width": 32, "height": 48, "steps": 1, "dry_run": "false"}
        body = {"request": generation} if endpoint == "/api/jobs" else generation
        status, payload = _raw_http_request(
            server.server_address[1],
            "POST",
            endpoint,
            body=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )

        assert status == 400
        assert payload["error_code"] == "generation_invalid_request"
        assert "dry_run must be a boolean" in payload["error"]
    finally:
        server.shutdown()
        server.server_close()


def test_http_server_rejects_non_boolean_infinite_flag(tmp_path):
    server = create_http_server("127.0.0.1", 0, paths=_paths(tmp_path), default_dry_run=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        port = server.server_address[1]
        status, payload = _raw_http_request(
            port,
            "POST",
            "/api/jobs",
            body=json.dumps(
                {
                    "infinite": "false",
                    "request": {"prompt": "must stay finite", "width": 32, "height": 48, "dry_run": True},
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        _, jobs = _get_json(f"http://127.0.0.1:{port}/api/jobs")

        assert status == 400
        assert payload["error_code"] == "queue_invalid_request"
        assert jobs["count"] == 0
    finally:
        server.shutdown()
        server.server_close()


def test_http_server_rejects_unready_finite_queue_before_enqueuing_jobs(tmp_path):
    server = create_http_server("127.0.0.1", 0, paths=_paths(tmp_path), default_dry_run=False)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        request = urllib.request.Request(
            f"{base_url}/api/jobs",
            data=json.dumps(
                {
                    "count": 99,
                    "request": {
                        "prompt": "missing models",
                        "width": 32,
                        "height": 48,
                        "steps": 1,
                        "dry_run": False,
                    },
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with pytest.raises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(request, timeout=5)

        assert caught.value.code == 409
        payload = json.loads(caught.value.read().decode("utf-8"))
        assert payload["error_code"] == "models_not_ready"
        _, jobs = _get_json(f"{base_url}/api/jobs")
        assert jobs["count"] == 0
    finally:
        server.shutdown()
        server.server_close()


def test_http_server_rejects_jobs_over_active_queue_capacity(tmp_path):
    paths = _paths(tmp_path)
    _write_generation_models(paths)
    renderer_started = threading.Event()
    finish_render = threading.Event()

    def slow_renderer(request, active_paths):
        renderer_started.set()
        assert finish_render.wait(timeout=10)
        output_path = active_paths.image_root / "queue-capacity.png"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (request.width, request.height), "white").save(output_path)
        return T2IRenderOutput(output_path=output_path, stages={"base_t2i": {"status": "completed"}})

    server = create_http_server("127.0.0.1", 0, paths=paths, renderer=slow_renderer)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        status, queued = _post_json(
            f"{base_url}/api/jobs",
            {
                "count": server_module.MAX_QUEUE_JOBS,
                "request": {
                    "prompt": "fill queue",
                    "width": 32,
                    "height": 48,
                    "steps": 1,
                    "dry_run": False,
                },
            },
        )

        assert status == 202
        assert len(queued["jobs"]) == server_module.MAX_QUEUE_JOBS
        assert renderer_started.wait(timeout=5)

        overflow_status, overflow = _raw_http_request(
            server.server_address[1],
            "POST",
            "/api/jobs",
            body=json.dumps(
                {
                    "request": {
                        "prompt": "one too many",
                        "width": 32,
                        "height": 48,
                        "steps": 1,
                        "dry_run": False,
                    }
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )

        assert overflow_status == 429
        assert overflow["error_code"] == "queue_full"
    finally:
        server.shutdown()
        server.server_close()
        finish_render.set()
        thread.join(timeout=5)


@pytest.mark.parametrize("count", [True, 1.0, 1.5, 0, server_module.MAX_QUEUE_JOBS + 1, "invalid"])
def test_queue_count_requires_integer_within_active_capacity(count):
    with pytest.raises(ValueError, match="count must"):
        server_module._bounded_job_count(count)


@pytest.mark.parametrize("delay", [True, -0.1, 60.1, float("nan"), float("inf"), "1", "invalid"])
def test_queue_delay_requires_finite_number_within_limit(delay):
    with pytest.raises(ValueError, match="delay_seconds must"):
        server_module._bounded_queue_delay(delay)


def test_queue_increment_wraps_seed_at_supported_max():
    queued = server_module._request_for_queue_index(
        {"prompt": "wrapped seed", "seed": requests_module.MAX_SEED},
        index=1,
        seed_mode="increment",
        base_seed=requests_module.MAX_SEED,
        base_seed_provided=True,
    )

    assert queued["seed"] == 0


def test_job_queue_prunes_finished_batch_metadata(tmp_path):
    queue = server_module.JobQueue(
        paths=_paths(tmp_path),
        renderer=None,
        default_dry_run=True,
        progress_store=ProgressStore(),
        generation_lock=threading.Lock(),
    )
    try:
        status, queued = queue.enqueue(
            {"request": {"prompt": "prune batch", "width": 32, "height": 48, "steps": 1, "dry_run": True}}
        )
        job_id = queued["jobs"][0]["id"]

        assert status == 202

        def job_finished() -> dict[str, object]:
            _, payload = queue.get(job_id)
            return {"ready": payload["status"] == "completed", "payload": payload}

        _wait_for(job_finished)
        assert queue._batches == {}
    finally:
        queue.close()


def test_job_queue_retains_active_job_in_order_then_prunes_it_after_finish(tmp_path):
    paths = _paths(tmp_path)
    _write_generation_models(paths)
    first_started = threading.Event()
    release_first = threading.Event()

    def blocking_renderer(request, active_paths):
        if not first_started.is_set():
            first_started.set()
            assert release_first.wait(timeout=10)
        output = active_paths.image_root / f"queue-prune-{request.seed}.png"
        output.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (request.width, request.height), "white").save(output)
        return T2IRenderOutput(output_path=output, stages={"base_t2i": {"status": "completed"}})

    queue = server_module.JobQueue(
        paths=paths,
        renderer=blocking_renderer,
        default_dry_run=False,
        progress_store=ProgressStore(),
        generation_lock=threading.Lock(),
        max_entries=1,
    )
    try:
        _, first = queue.enqueue(
            {"request": {"prompt": "first", "width": 32, "height": 48, "steps": 1, "seed": 1}}
        )
        assert first_started.wait(timeout=5)
        _, second = queue.enqueue(
            {"request": {"prompt": "second", "width": 32, "height": 48, "steps": 1, "seed": 2}}
        )
        first_id = first["jobs"][0]["id"]
        second_id = second["jobs"][0]["id"]
        assert first_id in queue._order

        release_first.set()

        def second_finished() -> dict[str, object]:
            _, payload = queue.get(second_id)
            return {"ready": payload["status"] == "completed"}

        _wait_for(second_finished)
        assert first_id not in queue._jobs
        assert queue._order == [second_id]
    finally:
        release_first.set()
        queue.close()


def test_infinite_queue_stops_after_generation_failure(tmp_path):
    paths = _paths(tmp_path)
    _write_generation_models(paths)
    missing_model = paths.model_root / "diffusion_models" / "model.safetensors"
    render_calls = 0

    def missing_model_renderer(request, active_paths):
        nonlocal render_calls
        render_calls += 1
        raise ModelsNotReadyError((missing_model,))

    server = create_http_server("127.0.0.1", 0, paths=paths, renderer=missing_model_renderer)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        status, queued = _post_json(
            f"{base_url}/api/jobs",
            {
                "infinite": True,
                "request": {"prompt": "missing model", "width": 32, "height": 48, "steps": 1, "dry_run": False},
            },
        )

        assert status == 202
        assert queued["infinite"] is True

        def job_failed() -> dict[str, object]:
            _, payload = _get_json(f"{base_url}/api/jobs")
            failed = [item for item in payload["items"] if item["status"] == "failed"]
            return {"ready": len(failed) == 1, "payload": payload}

        failed = _wait_for(job_failed)
        assert failed["payload"]["summary"]["failed"] == 1
        assert failed["payload"]["count"] == 1
        assert failed["payload"]["items"][0]["http_status"] == 409
        assert failed["payload"]["items"][0]["result"]["error_code"] == "models_not_ready"
        assert render_calls == 1
    finally:
        server.shutdown()
        server.server_close()


def test_queue_fallback_marks_progress_failed_for_base_exception(tmp_path):
    class FatalRender(BaseException):
        pass

    def fatal_renderer(request, active_paths):
        raise FatalRender("renderer aborted")

    paths = _paths(tmp_path)
    _write_generation_models(paths)
    server = create_http_server("127.0.0.1", 0, paths=paths, renderer=fatal_renderer)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        status, queued = _post_json(
            f"{base_url}/api/jobs",
            {"request": {"prompt": "fatal", "width": 32, "height": 48, "steps": 1, "dry_run": False}},
        )
        job_id = queued["jobs"][0]["id"]

        assert status == 202

        def job_failed() -> dict[str, object]:
            _, payload = _get_json(f"{base_url}/api/jobs/{job_id}")
            return {"ready": payload["status"] == "failed", "payload": payload}

        failed = _wait_for(job_failed)["payload"]
        _, progress = _get_json(f"{base_url}/api/progress/{job_id}")

        assert failed["http_status"] == 500
        assert failed["result"]["error_code"] == "generation_failed"
        assert progress["status"] == "failed"
        assert "renderer aborted" in progress["error"]
    finally:
        server.shutdown()
        server.server_close()


def test_http_server_cancels_queued_job_and_requests_active_stop(tmp_path):
    paths = _paths(tmp_path)
    _write_generation_models(paths)
    renderer_started = threading.Event()
    finish_render = threading.Event()

    def slow_renderer(request, active_paths):
        renderer_started.set()
        assert finish_render.wait(timeout=5)
        output_path = active_paths.image_root / f"{request.prompt}.png"
        output_path.parent.mkdir(parents=True)
        Image.new("RGB", (request.width, request.height), "white").save(output_path)
        return T2IRenderOutput(output_path=output_path, stages={"base_t2i": {"status": "completed"}})

    server = create_http_server("127.0.0.1", 0, paths=paths, renderer=slow_renderer)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        status, queued = _post_json(
            f"{base_url}/api/jobs",
            {
                "count": 2,
                "request": {"prompt": "queued-job", "width": 32, "height": 48, "steps": 1, "dry_run": False},
            },
        )
        first_id = queued["jobs"][0]["id"]
        second_id = queued["jobs"][1]["id"]

        assert status == 202
        assert renderer_started.wait(timeout=5)

        cancel_second_status, cancelled = _post_json(f"{base_url}/api/jobs/{second_id}/cancel", {})
        assert cancel_second_status == 200
        assert cancelled["job"]["status"] == "cancelled"

        cancel_first_status, cancel_requested = _post_json(f"{base_url}/api/jobs/{first_id}/cancel", {})
        assert cancel_first_status == 200
        assert cancel_requested["job"]["status"] == "running"
        assert cancel_requested["job"]["cancel_requested"] is True

        finish_render.set()

        def first_completed() -> dict[str, object]:
            _, payload = _get_json(f"{base_url}/api/jobs/{first_id}")
            return {"ready": payload["status"] == "completed", "payload": payload}

        completed = _wait_for(first_completed)
        assert completed["payload"]["cancel_requested"] is True

        _, second = _get_json(f"{base_url}/api/jobs/{second_id}")
        assert second["status"] == "cancelled"
        assert second["result"] is None
    finally:
        finish_render.set()
        server.shutdown()
        server.server_close()


def test_cancelled_queue_job_waiting_for_generation_lock_never_runs(tmp_path):
    paths = _paths(tmp_path)
    _write_generation_models(paths)
    direct_started = threading.Event()
    finish_direct = threading.Event()
    rendered_prompts: list[str] = []

    def locked_renderer(request, active_paths):
        rendered_prompts.append(request.prompt)
        if request.prompt == "direct-job":
            direct_started.set()
            assert finish_direct.wait(timeout=5)
        output_path = active_paths.image_root / f"{request.prompt}.png"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (request.width, request.height), "white").save(output_path)
        return T2IRenderOutput(output_path=output_path, stages={"base_t2i": {"status": "completed"}})

    server = create_http_server("127.0.0.1", 0, paths=paths, renderer=locked_renderer)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    direct_result: dict[str, object] = {}
    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"

        def run_direct_generation() -> None:
            direct_result["status"], direct_result["payload"] = _post_json(
                f"{base_url}/api/generate",
                {"prompt": "direct-job", "width": 32, "height": 48, "steps": 1, "dry_run": False},
            )

        direct_thread = threading.Thread(target=run_direct_generation, daemon=True)
        direct_thread.start()
        assert direct_started.wait(timeout=5)

        status, queued = _post_json(
            f"{base_url}/api/jobs",
            {"request": {"prompt": "queued-job", "width": 32, "height": 48, "steps": 1, "dry_run": False}},
        )
        job_id = queued["jobs"][0]["id"]
        assert status == 202

        def job_claimed() -> dict[str, object]:
            _, payload = _get_json(f"{base_url}/api/jobs/{job_id}")
            return {"ready": payload["status"] in {"waiting", "running"}, "payload": payload}

        waiting = _wait_for(job_claimed)["payload"]
        assert waiting["status"] == "waiting"

        cancel_status, cancelled = _post_json(f"{base_url}/api/jobs/{job_id}/cancel", {})
        assert cancel_status == 200
        assert cancelled["job"]["status"] == "cancelled"
        assert cancelled["job"]["interrupt_requested"] is False

        finish_direct.set()
        direct_thread.join(timeout=5)
        assert not direct_thread.is_alive()
        assert direct_result["status"] == 200

        _, final_job = _get_json(f"{base_url}/api/jobs/{job_id}")
        assert final_job["status"] == "cancelled"
        assert rendered_prompts == ["direct-job"]
    finally:
        finish_direct.set()
        server.shutdown()
        server.server_close()


def test_interrupt_exception_marks_queue_job_and_progress_cancelled(tmp_path):
    class InterruptProcessingException(BaseException):
        pass

    paths = _paths(tmp_path)
    _write_generation_models(paths)
    renderer_started = threading.Event()
    raise_interrupt = threading.Event()

    def interrupted_renderer(request, active_paths):
        renderer_started.set()
        assert raise_interrupt.wait(timeout=5)
        raise InterruptProcessingException()

    server = create_http_server("127.0.0.1", 0, paths=paths, renderer=interrupted_renderer)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        status, queued = _post_json(
            f"{base_url}/api/jobs",
            {"request": {"prompt": "cancel-me", "width": 32, "height": 48, "steps": 1, "dry_run": False}},
        )
        job_id = queued["jobs"][0]["id"]

        assert status == 202
        assert renderer_started.wait(timeout=5)
        cancel_status, cancel_requested = _post_json(f"{base_url}/api/jobs/{job_id}/cancel", {})
        assert cancel_status == 200
        assert cancel_requested["job"]["cancel_requested"] is True
        raise_interrupt.set()

        def job_cancelled() -> dict[str, object]:
            _, payload = _get_json(f"{base_url}/api/jobs/{job_id}")
            return {"ready": payload["status"] in {"cancelled", "failed"}, "payload": payload}

        cancelled = _wait_for(job_cancelled)["payload"]
        _, progress = _get_json(f"{base_url}/api/progress/{job_id}")

        assert cancelled["status"] == "cancelled"
        assert cancelled["http_status"] == 499
        assert cancelled["result"]["error_code"] == "generation_cancelled"
        assert progress["status"] == "cancelled"
        assert progress["summary"] == "취소됨"
    finally:
        raise_interrupt.set()
        server.shutdown()
        server.server_close()


def test_queue_cancel_during_finish_does_not_leave_stale_interrupt(tmp_path, monkeypatch):
    finish_entered = threading.Event()
    allow_finish = threading.Event()
    interrupt_states: list[bool] = []
    original_finish = server_module.JobQueue._finish_job

    def record_interrupt(value):
        interrupt_states.append(bool(value))
        return True

    def paused_finish(queue, job_id, http_status, response):
        finish_entered.set()
        assert allow_finish.wait(timeout=10)
        return original_finish(queue, job_id, http_status, response)

    monkeypatch.setattr(server_module, "_set_runtime_interrupt", record_interrupt)
    monkeypatch.setattr(server_module.JobQueue, "_finish_job", paused_finish)
    server = create_http_server("127.0.0.1", 0, paths=_paths(tmp_path), default_dry_run=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        status, queued = _post_json(
            f"{base_url}/api/jobs",
            {"request": {"prompt": "finish race", "width": 32, "height": 48, "steps": 1, "dry_run": True}},
        )
        job_id = queued["jobs"][0]["id"]

        assert status == 202
        assert finish_entered.wait(timeout=5)
        cancel_status, cancel_requested = _post_json(f"{base_url}/api/jobs/{job_id}/cancel", {})
        assert cancel_status == 200
        assert cancel_requested["job"]["status"] == "running"
        assert interrupt_states[-1] is True

        allow_finish.set()

        def job_finished() -> dict[str, object]:
            _, payload = _get_json(f"{base_url}/api/jobs/{job_id}")
            return {"ready": payload["status"] != "running", "payload": payload}

        finished = _wait_for(job_finished)["payload"]
        assert finished["status"] == "completed"
        assert interrupt_states[-1] is False
    finally:
        allow_finish.set()
        server.shutdown()
        server.server_close()


def test_http_server_rejects_unknown_job_post_route(tmp_path):
    paths = _paths(tmp_path)
    server = create_http_server("127.0.0.1", 0, paths=paths, default_dry_run=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        request = urllib.request.Request(
            f"{base_url}/api/jobs/not-a-real-action",
            data=json.dumps({"prompt": "must not generate"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            urllib.request.urlopen(request, timeout=5)
        except urllib.error.HTTPError as exc:
            assert exc.code == 404
            payload = json.loads(exc.read().decode("utf-8"))
        else:
            raise AssertionError("expected HTTP 404 for unknown job POST route")

        assert payload["error"] == "not found"
        assert not list(paths.manifest_root.glob("*.json"))
    finally:
        server.shutdown()
        server.server_close()


def test_http_server_rejects_overlapping_generate_requests(tmp_path):
    paths = _paths(tmp_path)
    renderer_started = threading.Event()
    finish_render = threading.Event()

    def slow_renderer(request, active_paths):
        renderer_started.set()
        assert finish_render.wait(timeout=5)
        output_path = active_paths.image_root / "locked-real.png"
        output_path.parent.mkdir(parents=True)
        Image.new("RGB", (request.width, request.height), "white").save(output_path)
        return T2IRenderOutput(output_path=output_path, stages={"base_t2i": {"status": "completed"}})

    server = create_http_server("127.0.0.1", 0, paths=paths, renderer=slow_renderer)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    first_result: dict[str, object] = {}

    def post_first_generate() -> None:
        request = urllib.request.Request(
            f"http://127.0.0.1:{server.server_address[1]}/api/generate",
            data=json.dumps({"prompt": "first", "width": 32, "height": 48, "steps": 1, "dry_run": False}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            first_result["status"] = response.status
            first_result["payload"] = json.loads(response.read().decode("utf-8"))

    post_thread = threading.Thread(target=post_first_generate, daemon=True)
    post_thread.start()
    try:
        assert renderer_started.wait(timeout=5)
        second_request = urllib.request.Request(
            f"http://127.0.0.1:{server.server_address[1]}/api/generate",
            data=json.dumps({"prompt": "second", "width": 32, "height": 48, "steps": 1, "dry_run": False}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            urllib.request.urlopen(second_request, timeout=5)
        except urllib.error.HTTPError as exc:
            assert exc.code == 409
            second_payload = json.loads(exc.read().decode("utf-8"))
        else:
            raise AssertionError("expected HTTP 409 for overlapping generation")

        assert "generation already running" in second_payload["error"]
        finish_render.set()
        post_thread.join(timeout=5)
        assert not post_thread.is_alive()
        assert first_result["status"] == 200
        assert first_result["payload"]["status"] == "generated"
    finally:
        finish_render.set()
        server.shutdown()
        server.server_close()


def test_http_server_blocks_generation_while_model_profile_is_preparing(tmp_path, monkeypatch):
    prepare_started = threading.Event()
    finish_prepare = threading.Event()

    def slow_copy(profile, paths, *, source):
        prepare_started.set()
        assert finish_prepare.wait(timeout=5)
        return "local", []

    monkeypatch.setattr("anima_app.server.copy_asset_profile", slow_copy)
    server = create_http_server("127.0.0.1", 0, paths=_paths(tmp_path), default_dry_run=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    prepare_result: dict[str, object] = {}

    def post_prepare() -> None:
        request = urllib.request.Request(
            f"http://127.0.0.1:{server.server_address[1]}/api/models/prepare",
            data=json.dumps({"profile": "anima-t2i", "source": "local"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            prepare_result["status"] = response.status

    prepare_thread = threading.Thread(target=post_prepare, daemon=True)
    prepare_thread.start()
    try:
        assert prepare_started.wait(timeout=5)
        request = urllib.request.Request(
            f"http://127.0.0.1:{server.server_address[1]}/api/generate",
            data=json.dumps({"prompt": "blocked", "width": 32, "height": 48, "dry_run": True}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with pytest.raises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(request, timeout=5)

        assert caught.value.code == 409
        payload = json.loads(caught.value.read().decode("utf-8"))
        assert payload["error_code"] == "generation_busy"
        assert "model preparation" in payload["error"]
    finally:
        finish_prepare.set()
        prepare_thread.join(timeout=5)
        server.shutdown()
        server.server_close()

    assert not prepare_thread.is_alive()
    assert prepare_result["status"] == 200


def test_http_server_serves_history_newest_first(tmp_path):
    server = create_http_server("127.0.0.1", 0, paths=_paths(tmp_path), default_dry_run=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        for prompt in ("first portrait", "second portrait"):
            request = urllib.request.Request(
                f"{base_url}/api/generate",
                data=json.dumps({"prompt": prompt, "width": 512, "height": 768}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            urllib.request.urlopen(request, timeout=5).read()

        with urllib.request.urlopen(f"{base_url}/api/history?limit=2", timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))

        assert response.status == 200
        assert payload["count"] == 2
        assert [item["prompt"] for item in payload["items"]] == ["second portrait", "first portrait"]
        assert payload["items"][0]["status"] == "dry_run"
        assert payload["items"][0]["output_url"] is None
        assert Path(payload["items"][0]["manifest_path"]).is_file()
        assert payload["has_more"] is False
        assert payload["next_cursor"] is None
    finally:
        server.shutdown()
        server.server_close()


def test_http_server_paginates_history_with_stable_cursor(tmp_path):
    paths = _paths(tmp_path)
    for index in range(5):
        status, _ = handle_generate(
            {"prompt": f"history {index}", "width": 32, "height": 48, "steps": 1, "dry_run": True},
            paths=paths,
        )
        assert status == 200
    server = create_http_server("127.0.0.1", 0, paths=paths, default_dry_run=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        _, first = _get_json(f"{base_url}/api/history?limit=2")
        Path(first["items"][-1]["manifest_path"]).unlink()
        _, second = _get_json(
            f"{base_url}/api/history?limit=2&cursor={urllib.parse.quote(str(first['next_cursor']))}"
        )

        first_paths = {item["manifest_path"] for item in first["items"]}
        second_paths = {item["manifest_path"] for item in second["items"]}
        assert first["count"] == 2
        assert first["has_more"] is True
        assert first["next_cursor"]
        assert second["count"] == 2
        assert first_paths.isdisjoint(second_paths)
        assert second["has_more"] is True

        with pytest.raises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(f"{base_url}/api/history?limit=2&cursor=not-a-cursor", timeout=5)
        assert caught.value.code == 400
        assert json.loads(caught.value.read().decode("utf-8"))["error_code"] == "history_cursor_invalid"

        nonfinite = urllib.parse.quote(server_module._encode_history_cursor((float("nan"), "bad")))
        with pytest.raises(urllib.error.HTTPError) as caught_nonfinite:
            urllib.request.urlopen(f"{base_url}/api/history?limit=2&cursor={nonfinite}", timeout=5)
        assert caught_nonfinite.value.code == 400
        assert json.loads(caught_nonfinite.value.read().decode("utf-8"))["error_code"] == "history_cursor_invalid"

        invalid_types = server_module.base64.urlsafe_b64encode(
            json.dumps(["1", 123], separators=(",", ":")).encode("utf-8")
        ).decode("ascii").rstrip("=")
        with pytest.raises(urllib.error.HTTPError) as caught_types:
            urllib.request.urlopen(f"{base_url}/api/history?limit=2&cursor={invalid_types}", timeout=5)
        assert caught_types.value.code == 400
        assert json.loads(caught_types.value.read().decode("utf-8"))["error_code"] == "history_cursor_invalid"
    finally:
        server.shutdown()
        server.server_close()


def test_http_history_filtered_cursor_handles_equal_timestamps_without_gaps(tmp_path):
    paths = _paths(tmp_path)
    paths.image_root.mkdir(parents=True)
    paths.manifest_root.mkdir(parents=True)
    expected_names = []
    for index in range(5):
        output_path = paths.image_root / f"equal-{index}.png"
        output_path.write_bytes(_png_bytes())
        manifest_path = paths.manifest_root / f"equal-{index}.json"
        manifest_path.write_text(
            json.dumps(
                {
                    "prompt": "equal match",
                    "created_at": 10,
                    "output_path": str(output_path),
                }
            ),
            encoding="utf-8",
        )
        expected_names.append(manifest_path.name)

    server = create_http_server("127.0.0.1", 0, paths=paths, default_dry_run=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    seen = []
    cursor = ""
    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        while True:
            url = f"{base_url}/api/history?limit=2&q=equal&type=images"
            if cursor:
                url += "&cursor=" + urllib.parse.quote(cursor)
            _, page = _get_json(url)
            assert page["total_count"] == 5
            seen.extend(item["manifest_name"] for item in page["items"])
            if not page["has_more"]:
                break
            cursor = page["next_cursor"]
    finally:
        server.shutdown()
        server.server_close()

    assert seen == sorted(expected_names, reverse=True)
    assert len(seen) == len(set(seen)) == 5


def test_history_keeps_listing_when_manifest_output_is_outside_managed_root(tmp_path):
    paths = _paths(tmp_path)
    paths.manifest_root.mkdir(parents=True)
    manifest = paths.manifest_root / "outside-output.json"
    manifest.write_text(
        json.dumps(
            {
                "prompt": "external output",
                "status": "generated",
                "created_at": 1,
                "output_path": str(tmp_path / "outside.png"),
            }
        ),
        encoding="utf-8",
    )

    payload = handle_history(paths=paths, limit=8)

    assert payload["count"] == 1
    assert payload["items"][0]["prompt"] == "external output"
    assert payload["items"][0]["output_url"] is None


def test_http_history_searches_and_filters_before_pagination(tmp_path):
    paths = _paths(tmp_path)
    paths.manifest_root.mkdir(parents=True)
    paths.image_root.mkdir(parents=True)
    image_path = paths.image_root / "newer-image.png"
    Image.new("RGB", (32, 24), "navy").save(image_path)
    records = (
        (4, "newer image", image_path),
        (3, "newer dry run", None),
        (2, "Blue Comet portrait", None),
    )
    for created_at, prompt, output_path in records:
        manifest_path = paths.manifest_root / f"history-{created_at}.json"
        manifest_path.write_text(
            json.dumps(
                {
                    "prompt": prompt,
                    "status": "generated" if output_path else "dry_run",
                    "created_at": created_at,
                    "output_path": str(output_path) if output_path else None,
                }
            ),
            encoding="utf-8",
        )

    server = create_http_server("127.0.0.1", 0, paths=paths, default_dry_run=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        _, searched = _get_json(f"{base_url}/api/history?limit=1&q=blue&type=dry-run")
        _, images = _get_json(f"{base_url}/api/history?limit=1&type=images")

        assert searched["count"] == 1
        assert searched["total_count"] == 1
        assert searched["query"] == "blue"
        assert searched["type"] == "dry-run"
        assert searched["items"][0]["prompt"] == "Blue Comet portrait"
        assert searched["items"][0]["kind"] == "dry-run"
        assert searched["items"][0]["manifest_name"] == "history-2.json"
        assert images["total_count"] == 1
        assert images["items"][0]["kind"] == "images"
    finally:
        server.shutdown()
        server.server_close()


def test_http_history_rejects_unknown_type_and_overlong_query(tmp_path):
    server = create_http_server("127.0.0.1", 0, paths=_paths(tmp_path), default_dry_run=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        with pytest.raises(urllib.error.HTTPError) as caught_type:
            urllib.request.urlopen(f"{base_url}/api/history?type=unknown", timeout=5)
        with pytest.raises(urllib.error.HTTPError) as caught_query:
            urllib.request.urlopen(f"{base_url}/api/history?q={'x' * 257}", timeout=5)

        assert caught_type.value.code == 400
        assert json.loads(caught_type.value.read().decode("utf-8"))["error_code"] == "history_type_invalid"
        assert caught_query.value.code == 400
        assert json.loads(caught_query.value.read().decode("utf-8"))["error_code"] == "history_query_invalid"
    finally:
        server.shutdown()
        server.server_close()


def test_http_history_uses_bounded_in_memory_thumbnails(tmp_path):
    paths = _paths(tmp_path)
    paths.image_root.mkdir(parents=True)
    paths.manifest_root.mkdir(parents=True)
    output_path = paths.image_root / "large-history.png"
    Image.new("RGB", (1600, 800), "purple").save(output_path)
    original_bytes = output_path.read_bytes()
    original_mtime = output_path.stat().st_mtime_ns
    manifest_path = paths.manifest_root / "large-history.json"
    manifest_path.write_text(
        json.dumps(
            {
                "prompt": "thumbnail portrait",
                "status": "generated",
                "created_at": 1,
                "output_path": str(output_path),
            }
        ),
        encoding="utf-8",
    )
    files_before = {path.relative_to(paths.project_root) for path in paths.project_root.rglob("*") if path.is_file()}

    server = create_http_server("127.0.0.1", 0, paths=paths, default_dry_run=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        _, history = _get_json(f"{base_url}/api/history")
        item = history["items"][0]
        assert item["manifest_name"] == manifest_path.name
        assert item["output_size_bytes"] == len(original_bytes)
        assert item["thumbnail_url"]

        with urllib.request.urlopen(base_url + item["thumbnail_url"], timeout=5) as response:
            thumbnail_bytes = response.read()
            content_type = response.headers["Content-Type"]

        with Image.open(io.BytesIO(thumbnail_bytes)) as thumbnail:
            assert thumbnail.format == "JPEG"
            assert max(thumbnail.size) <= 320
        assert content_type == "image/jpeg"
        assert len(thumbnail_bytes) < len(original_bytes)
    finally:
        server.shutdown()
        server.server_close()

    files_after = {path.relative_to(paths.project_root) for path in paths.project_root.rglob("*") if path.is_file()}
    assert files_after == files_before
    assert output_path.read_bytes() == original_bytes
    assert output_path.stat().st_mtime_ns == original_mtime


def test_http_thumbnail_rejects_missing_and_encoded_traversal(tmp_path):
    paths = _paths(tmp_path)
    paths.image_root.mkdir(parents=True)
    outside = tmp_path / "outside.png"
    Image.new("RGB", (16, 16), "red").save(outside)
    server = create_http_server("127.0.0.1", 0, paths=paths, default_dry_run=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        port = server.server_address[1]
        missing_status, _ = _raw_http_request(port, "GET", "/api/thumbnails/missing.png")
        traversal_status, _ = _raw_http_request(port, "GET", "/api/thumbnails/..%2Foutside.png")

        assert missing_status == 404
        assert traversal_status == 400
        assert outside.is_file()
    finally:
        server.shutdown()
        server.server_close()


def test_http_thumbnail_rejects_corrupt_and_linked_sources(tmp_path, monkeypatch):
    paths = _paths(tmp_path)
    paths.image_root.mkdir(parents=True)
    corrupt = paths.image_root / "corrupt.png"
    linked_like = paths.image_root / "linked.png"
    corrupt.write_bytes(b"not an image")
    linked_like.write_bytes(_png_bytes())
    original_is_symlink = Path.is_symlink
    monkeypatch.setattr(
        Path,
        "is_symlink",
        lambda path: path == linked_like or original_is_symlink(path),
    )
    server = create_http_server("127.0.0.1", 0, paths=paths, default_dry_run=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        port = server.server_address[1]
        corrupt_status, corrupt_payload = _raw_http_request(port, "GET", "/api/thumbnails/corrupt.png")
        linked_status, linked_payload = _raw_http_request(port, "GET", "/api/thumbnails/linked.png")

        assert corrupt_status == 400
        assert corrupt_payload["error_code"] == "thumbnail_invalid"
        assert linked_status == 400
        assert linked_payload["error_code"] == "thumbnail_unavailable"
        assert linked_like.is_file()
    finally:
        server.shutdown()
        server.server_close()


def test_http_thumbnail_enforces_byte_limit_before_decode(tmp_path, monkeypatch):
    paths = _paths(tmp_path)
    paths.image_root.mkdir(parents=True)
    source = paths.image_root / "bounded.png"
    source.write_bytes(_png_bytes())
    opened = False

    def must_not_open(*args, **kwargs):
        nonlocal opened
        opened = True
        raise AssertionError("oversized thumbnail source must not be decoded")

    monkeypatch.setattr(server_module, "MAX_HISTORY_THUMBNAIL_SOURCE_BYTES", 1)
    monkeypatch.setattr(server_module.Image, "open", must_not_open)
    server = create_http_server("127.0.0.1", 0, paths=paths, default_dry_run=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status, payload = _raw_http_request(server.server_address[1], "GET", "/api/thumbnails/bounded.png")
    finally:
        server.shutdown()
        server.server_close()

    assert status == 400
    assert payload["error_code"] == "thumbnail_invalid"
    assert opened is False


def test_http_thumbnail_enforces_pixel_limit_before_transform(tmp_path, monkeypatch):
    paths = _paths(tmp_path)
    paths.image_root.mkdir(parents=True)
    source = paths.image_root / "too-many-pixels.png"
    source.write_bytes(_png_bytes((16, 16)))
    transformed = False

    def must_not_transform(*args, **kwargs):
        nonlocal transformed
        transformed = True
        raise AssertionError("oversized thumbnail source must not be transformed")

    monkeypatch.setattr(server_module, "MAX_OUTPUT_IMAGE_PIXELS", 4)
    monkeypatch.setattr(server_module.ImageOps, "exif_transpose", must_not_transform)
    server = create_http_server("127.0.0.1", 0, paths=paths, default_dry_run=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status, payload = _raw_http_request(
            server.server_address[1],
            "GET",
            "/api/thumbnails/too-many-pixels.png",
        )
    finally:
        server.shutdown()
        server.server_close()

    assert status == 400
    assert payload["error_code"] == "thumbnail_invalid"
    assert transformed is False


def test_http_thumbnail_caps_concurrent_decodes_and_reuses_open_handle(tmp_path, monkeypatch):
    paths = _paths(tmp_path)
    paths.image_root.mkdir(parents=True)
    source = paths.image_root / "concurrent.png"
    source.write_bytes(_png_bytes((96, 64)))
    original_open = server_module.Image.open
    original_fstat = server_module.os.fstat
    original_transpose = server_module.ImageOps.exif_transpose
    lock = threading.Lock()
    first_pair = threading.Barrier(2)
    active = 0
    entered = 0
    peak = 0
    opened_fds = []
    fstat_fds = []

    def observed_open(file, *args, **kwargs):
        opened_fds.append(file.fileno())
        return original_open(file, *args, **kwargs)

    def observed_fstat(file_descriptor):
        fstat_fds.append(file_descriptor)
        return original_fstat(file_descriptor)

    def slow_transpose(image):
        nonlocal active, entered, peak
        with lock:
            active += 1
            entered += 1
            position = entered
            peak = max(peak, active)
        try:
            if position <= 2:
                first_pair.wait(timeout=2)
            time.sleep(0.05)
            return original_transpose(image)
        finally:
            with lock:
                active -= 1

    monkeypatch.setattr(server_module.Image, "open", observed_open)
    monkeypatch.setattr(server_module.os, "fstat", observed_fstat)
    monkeypatch.setattr(server_module.ImageOps, "exif_transpose", slow_transpose)
    server = create_http_server("127.0.0.1", 0, paths=paths, default_dry_run=True)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    statuses = []

    def fetch_thumbnail():
        with urllib.request.urlopen(
            f"http://127.0.0.1:{server.server_address[1]}/api/thumbnails/{source.name}",
            timeout=5,
        ) as response:
            statuses.append(response.status)
            response.read()

    workers = [threading.Thread(target=fetch_thumbnail) for _ in range(3)]
    try:
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(timeout=5)
    finally:
        server.shutdown()
        server.server_close()

    assert all(not worker.is_alive() for worker in workers)
    assert statuses == [200, 200, 200]
    assert peak == server_module.MAX_CONCURRENT_HISTORY_THUMBNAILS
    assert opened_fds
    assert set(opened_fds).issubset(fstat_fds)


def test_health_reports_managed_output_counts_bytes_and_free_space(tmp_path):
    paths = _paths(tmp_path)
    paths.image_root.mkdir(parents=True)
    paths.manifest_root.mkdir(parents=True)
    (paths.image_root / "one.png").write_bytes(b"one")
    nested = paths.image_root / "nested"
    nested.mkdir()
    (nested / "two.png").write_bytes(b"twotwo")
    (paths.manifest_root / "one.json").write_bytes(b"{}")

    server = create_http_server("127.0.0.1", 0, paths=paths, default_dry_run=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        _, health = _get_json(f"http://127.0.0.1:{server.server_address[1]}/api/health")
    finally:
        server.shutdown()
        server.server_close()

    outputs = health["outputs"]
    assert outputs["image_count"] == 2
    assert outputs["image_bytes"] == 9
    assert outputs["manifest_count"] == 1
    assert outputs["manifest_bytes"] == 2
    assert outputs["managed_bytes"] == 11
    assert outputs["disk_free_bytes"] > 0
    assert outputs["disk_total_bytes"] >= outputs["disk_free_bytes"]


def test_health_skips_descendant_junctions(tmp_path, monkeypatch):
    paths = _paths(tmp_path)
    paths.image_root.mkdir(parents=True)
    safe = paths.image_root / "safe.png"
    safe.write_bytes(b"safe")
    linked_directory = paths.image_root / "linked-directory"
    linked_directory.mkdir()
    (linked_directory / "external-like.png").write_bytes(b"must-not-count")
    original_is_junction = getattr(Path, "is_junction", lambda path: False)
    monkeypatch.setattr(
        Path,
        "is_junction",
        lambda path: path == linked_directory or original_is_junction(path),
        raising=False,
    )

    payload = server_module.build_health_payload(paths)

    assert payload["outputs"]["image_count"] == 1
    assert payload["outputs"]["image_bytes"] == len(b"safe")


def test_http_server_serves_readiness_and_prepares_detector_profile(tmp_path):
    paths = _paths(tmp_path)
    _write_face_detector_sources(paths)
    server = create_http_server("127.0.0.1", 0, paths=paths, default_dry_run=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        with urllib.request.urlopen(f"{base_url}/api/readiness", timeout=5) as response:
            initial = json.loads(response.read().decode("utf-8"))

        profiles = {item["name"]: item for item in initial["profiles"]}
        assert response.status == 200
        assert initial["generation"]["ready"] is True
        assert initial["generation"]["dry_run"] is True
        assert len(initial["generation"]["missing_files"]) == 3
        assert profiles["anima-t2i"]["ready"] is False
        assert profiles["anima-t2i"]["missing_count"] == 3
        assert profiles["anima-t2i"]["invalid_count"] == 0
        assert profiles["anima-t2i"]["prepare_source"] == "huggingface"
        assert profiles["anima-t2i"]["prepare_size_bytes"] is None
        assert profiles["anima-aesthetic-v1.1"]["ready"] is False
        assert profiles["anima-aesthetic-v1.1"]["missing_count"] == 1
        assert profiles["face-detailer-detectors"]["ready"] is False
        assert profiles["face-detailer-detectors"]["missing_count"] == 3
        assert profiles["face-detailer-detectors"]["prepare_source"] == "local"
        assert profiles["face-detailer-detectors"]["prepare_size_bytes"] == sum(
            (paths.face_detailer_detector_source / relative_path.name).stat().st_size
            for relative_path in FACE_DETAILER_DETECTOR_ASSET_PROFILE.files
        )
        assert profiles["sam3-detector"]["ready"] is False
        assert profiles["sam3-detector"]["missing_count"] == 1

        request = urllib.request.Request(
            f"{base_url}/api/models/prepare",
            data=json.dumps({"profile": "face-detailer-detectors"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            prepared = json.loads(response.read().decode("utf-8"))

        assert response.status == 200
        assert prepared["profile"] == "face-detailer-detectors"
        assert prepared["source"] == "local"
        assert len(prepared["copied"]) == 3
        assert (paths.model_root / "detectors" / "face_yolov8n.pt").is_file()

        with urllib.request.urlopen(f"{base_url}/api/readiness", timeout=5) as response:
            after = json.loads(response.read().decode("utf-8"))

        after_profiles = {item["name"]: item for item in after["profiles"]}
        assert after_profiles["face-detailer-detectors"]["ready"] is True
        assert after_profiles["face-detailer-detectors"]["missing_count"] == 0
        assert after_profiles["sam3-detector"]["ready"] is False
    finally:
        server.shutdown()
        server.server_close()


def test_http_server_prepares_detector_profile_by_download_when_local_assets_are_missing(
    tmp_path,
    monkeypatch,
):
    paths = _paths(tmp_path)
    downloaded: list[Path] = []

    def fake_download(dest_root, relative_path):
        target = dest_root / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(relative_path.name.encode("utf-8") * 128)
        downloaded.append(relative_path)
        return target

    monkeypatch.setattr("anima_app.assets.download_asset_file_from_remote", fake_download)

    server = create_http_server("127.0.0.1", 0, paths=paths, default_dry_run=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        request = urllib.request.Request(
            f"{base_url}/api/models/prepare",
            data=json.dumps({"profile": "face-detailer-detectors"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            prepared = json.loads(response.read().decode("utf-8"))

        assert response.status == 200
        assert prepared["profile"] == "face-detailer-detectors"
        assert prepared["source"] == "download"
        assert prepared["readiness"]["ready"] is True
        assert len(downloaded) == 3
        assert (paths.model_root / "detectors" / "full_eyes_detect_v1.pt").is_file()
    finally:
        server.shutdown()
        server.server_close()


def test_http_server_prepares_sam3_detector_profile_by_download(tmp_path, monkeypatch):
    paths = _paths(tmp_path)
    downloaded: list[Path] = []

    def fake_download(dest_root, relative_path):
        target = dest_root / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"sam3" * 512)
        downloaded.append(relative_path)
        return target

    monkeypatch.setattr("anima_app.assets.download_asset_file_from_remote", fake_download)

    server = create_http_server("127.0.0.1", 0, paths=paths, default_dry_run=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        request = urllib.request.Request(
            f"{base_url}/api/models/prepare",
            data=json.dumps({"profile": "sam3-detector"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            prepared = json.loads(response.read().decode("utf-8"))

        assert response.status == 200
        assert prepared["profile"] == "sam3-detector"
        assert prepared["source"] == "download"
        assert prepared["readiness"]["ready"] is True
        assert downloaded == [Path("detectors") / "sam3.pt"]
        assert (paths.model_root / "detectors" / "sam3.pt").is_file()
    finally:
        server.shutdown()
        server.server_close()


def test_http_server_segments_current_image_with_sam3(tmp_path, monkeypatch):
    paths = _paths(tmp_path)
    source = paths.image_root / "source.png"
    mask = paths.image_root / "source_clothes_sam3_mask.png"
    overlay = paths.image_root / "source_clothes_sam3_overlay.png"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(b"png")
    mask.write_bytes(b"mask")
    overlay.write_bytes(b"overlay")

    def fake_segment(image_path, *, prompt, paths, threshold):
        from anima_app.runtime.sam3_segment import Sam3SegmentResult

        assert image_path == "/outputs/images/source.png"
        assert prompt == "clothes"
        assert threshold == 0.25
        return Sam3SegmentResult(
            prompt=prompt,
            source_path=source,
            mask_path=mask,
            overlay_path=overlay,
            boxes=((1.0, 2.0, 3.0, 4.0),),
            scores=(0.9,),
        )

    monkeypatch.setattr("anima_app.server.segment_image_concept", fake_segment)

    server = create_http_server("127.0.0.1", 0, paths=paths, default_dry_run=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        request = urllib.request.Request(
            f"{base_url}/api/sam3/segment",
            data=json.dumps({"image_path": "/outputs/images/source.png", "prompt": "clothes"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))

        assert response.status == 200
        assert payload["status"] == "sam3_segmented"
        assert payload["mask_url"] == "/outputs/images/source_clothes_sam3_mask.png"
        assert payload["overlay_url"] == "/outputs/images/source_clothes_sam3_overlay.png"
        assert payload["boxes"] == [[1.0, 2.0, 3.0, 4.0]]
        assert payload["scores"] == [0.9]
    finally:
        server.shutdown()
        server.server_close()


def test_http_server_blocks_generation_while_sam3_owns_gpu_lock(tmp_path, monkeypatch):
    from anima_app.runtime.sam3_segment import Sam3SegmentResult

    paths = _paths(tmp_path)
    source = paths.image_root / "source.png"
    mask = paths.image_root / "source_mask.png"
    overlay = paths.image_root / "source_overlay.png"
    source.parent.mkdir(parents=True, exist_ok=True)
    for path in (source, mask, overlay):
        path.write_bytes(path.name.encode("utf-8"))
    sam3_started = threading.Event()
    finish_sam3 = threading.Event()

    def slow_segment(image_path, *, prompt, paths, threshold):
        sam3_started.set()
        assert finish_sam3.wait(timeout=10)
        return Sam3SegmentResult(
            prompt=prompt,
            source_path=source,
            mask_path=mask,
            overlay_path=overlay,
            boxes=(),
            scores=(),
        )

    monkeypatch.setattr("anima_app.server.segment_image_concept", slow_segment)
    server = create_http_server("127.0.0.1", 0, paths=paths, default_dry_run=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    sam3_result: dict[str, object] = {}

    def post_sam3() -> None:
        try:
            sam3_result["status"], sam3_result["payload"] = _post_json(
                f"http://127.0.0.1:{server.server_address[1]}/api/sam3/segment",
                {"image_path": "/outputs/images/source.png", "prompt": "clothes"},
                timeout=10,
            )
        except BaseException as exc:
            sam3_result["error"] = exc

    sam3_thread = threading.Thread(target=post_sam3, daemon=True)
    sam3_thread.start()
    try:
        assert sam3_started.wait(timeout=5)
        status, payload = _raw_http_request(
            server.server_address[1],
            "POST",
            "/api/generate",
            body=json.dumps({"prompt": "blocked", "width": 32, "height": 48, "dry_run": True}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )

        assert status == 409
        assert payload["error_code"] == "generation_busy"

        finish_sam3.set()
        sam3_thread.join(timeout=5)
        assert not sam3_thread.is_alive()
        assert "error" not in sam3_result
        assert sam3_result["status"] == 200
    finally:
        finish_sam3.set()
        sam3_thread.join(timeout=5)
        server.shutdown()
        server.server_close()


def test_http_server_compares_sam3_prompt_candidates(tmp_path, monkeypatch):
    paths = _paths(tmp_path)
    source = paths.image_root / "source.png"
    mask = paths.image_root / "source_mask.png"
    overlay = paths.image_root / "source_overlay.png"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(b"png")
    mask.write_bytes(b"mask")
    overlay.write_bytes(b"overlay")

    def fake_compare(image_path, *, prompts, paths, threshold):
        from anima_app.runtime.sam3_segment import Sam3SegmentResult

        assert image_path == "/outputs/images/source.png"
        assert prompts == ["white dress", "upper body clothing"]
        assert threshold == 0.25
        return (
            Sam3SegmentResult(
                prompt="white dress",
                source_path=source,
                mask_path=mask,
                overlay_path=overlay,
                boxes=(),
                scores=(),
            ),
            Sam3SegmentResult(
                prompt="upper body clothing",
                source_path=source,
                mask_path=mask,
                overlay_path=overlay,
                boxes=((1.0, 2.0, 3.0, 4.0),),
                scores=(0.75,),
            ),
        )

    monkeypatch.setattr("anima_app.server.segment_image_concepts", fake_compare)

    server = create_http_server("127.0.0.1", 0, paths=paths, default_dry_run=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        request = urllib.request.Request(
            f"{base_url}/api/sam3/compare",
            data=json.dumps(
                {
                    "image_path": "/outputs/images/source.png",
                    "prompts": ["white dress", "upper body clothing"],
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))

        assert response.status == 200
        assert payload["status"] == "sam3_compared"
        assert payload["count"] == 2
        assert payload["best"]["prompt"] == "upper body clothing"
        assert payload["results"][0]["prompt"] == "white dress"
    finally:
        server.shutdown()
        server.server_close()


def test_http_server_adjusts_mask(tmp_path, monkeypatch):
    paths = _paths(tmp_path)
    source = paths.image_root / "source.png"
    mask = paths.image_root / "source_mask.png"
    overlay = paths.image_root / "source_overlay.png"
    crop = paths.image_root / "source_crop.png"
    crop_mask = paths.image_root / "source_crop_mask.png"
    source.parent.mkdir(parents=True, exist_ok=True)
    for path in (source, mask, overlay, crop, crop_mask):
        path.write_bytes(path.name.encode("utf-8"))

    def fake_adjust(image_path, *, mask_path, paths, dilation, feather, threshold):
        from anima_app.runtime.sam3_segment import Sam3MaskAdjustmentResult

        assert image_path == "/outputs/images/source.png"
        assert mask_path == "/outputs/images/source_mask.png"
        assert dilation == 24
        assert feather == 8
        assert threshold == 8
        return Sam3MaskAdjustmentResult(
            source_path=source,
            mask_path=mask,
            overlay_path=overlay,
            crop_path=crop,
            crop_mask_path=crop_mask,
            crop_box=(1, 2, 30, 40),
            dilation=dilation,
            feather=feather,
        )

    monkeypatch.setattr("anima_app.server.adjust_segment_mask", fake_adjust)

    server = create_http_server("127.0.0.1", 0, paths=paths, default_dry_run=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        status, payload = _post_json(
            f"{base_url}/api/masks/adjust",
            {
                "image_path": "/outputs/images/source.png",
                "mask_path": "/outputs/images/source_mask.png",
                "dilation": 24,
                "feather": 8,
            },
        )

        assert status == 200
        assert payload["status"] == "mask_adjusted"
        assert payload["mask_url"] == "/outputs/images/source_mask.png"
        assert payload["overlay_url"] == "/outputs/images/source_overlay.png"
        assert payload["crop_box"] == [1, 2, 30, 40]
    finally:
        server.shutdown()
        server.server_close()


def test_http_server_runs_masked_inpaint(tmp_path, monkeypatch):
    paths = _paths(tmp_path)
    lora = paths.model_root / "loras" / "merged_style.safetensors"
    lora.parent.mkdir(parents=True, exist_ok=True)
    lora.write_bytes(b"lora")
    output = paths.image_root / "source_inpaint.png"
    crop = paths.image_root / "source_inpaint_crop.png"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(b"output")
    crop.write_bytes(b"crop")

    def fake_run(settings, *, paths):
        from anima_app.runtime.masked_inpaint import MaskedInpaintResult

        assert settings.image_path == "/outputs/images/source.png"
        assert settings.mask_path == "/outputs/images/source_mask.png"
        assert settings.prompt == "yellow sundress"
        assert settings.checkpoint == "anima-aesthetic-v1.1.safetensors"
        assert settings.loras[0].path == "merged_style.safetensors"
        assert settings.loras[0].model_strength == 1.0
        assert settings.loras[0].clip_strength == 1.0
        assert settings.method == "noise_mask"
        assert settings.denoise == 0.7
        assert settings.steps == 20
        assert settings.cfg == 3.5
        assert settings.seed == 123
        return MaskedInpaintResult(
            output_path=output,
            crop_path=crop,
            crop_box=(4, 5, 64, 96),
            method=settings.method,
            seed=settings.seed or 0,
        )

    monkeypatch.setattr("anima_app.server.run_masked_inpaint", fake_run)

    server = create_http_server("127.0.0.1", 0, paths=paths, default_dry_run=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        status, payload = _post_json(
            f"{base_url}/api/inpaint/masked",
            {
                "image_path": "/outputs/images/source.png",
                "mask_path": "/outputs/images/source_mask.png",
                "prompt": "yellow sundress",
                "checkpoint": "anima-aesthetic-v1.1.safetensors",
                "loras": [{"path": "merged_style.safetensors", "model_strength": 1.0, "clip_strength": 1.0}],
                "method": "noise_mask",
                "denoise": 0.7,
                "steps": 20,
                "cfg": 3.5,
                "seed": 123,
            },
        )

        assert status == 200
        assert payload["status"] == "masked_inpainted"
        assert payload["output_url"] == "/outputs/images/source_inpaint.png"
        assert payload["crop_url"] == "/outputs/images/source_inpaint_crop.png"
        assert payload["crop_box"] == [4, 5, 64, 96]
    finally:
        server.shutdown()
        server.server_close()


@pytest.mark.parametrize("lora_path", ["../outside.safetensors", r"C:\outside\style.safetensors"])
def test_http_masked_inpaint_rejects_unmanaged_lora_before_runtime(tmp_path, monkeypatch, lora_path):
    def must_not_run(*_args, **_kwargs):
        raise AssertionError("masked inpaint runtime must not run")

    monkeypatch.setattr("anima_app.server.run_masked_inpaint", must_not_run)
    server = create_http_server("127.0.0.1", 0, paths=_paths(tmp_path), default_dry_run=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status, payload = _raw_http_request(
            server.server_address[1],
            "POST",
            "/api/inpaint/masked",
            body=json.dumps(
                {
                    "image_path": "missing.png",
                    "mask_path": "missing-mask.png",
                    "prompt": "repair",
                    "loras": [{"path": lora_path}],
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )

        assert status == 400
        assert "managed LoRA" in payload["error"]
    finally:
        server.shutdown()
        server.server_close()


@pytest.mark.parametrize("loras", ["x" * 1000, [{"path": f"style-{index}.safetensors"} for index in range(9)]])
def test_masked_inpaint_rejects_invalid_lora_collection_before_runtime(tmp_path, monkeypatch, loras):
    called = False

    def must_not_run(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("masked inpaint runtime must not run")

    monkeypatch.setattr("anima_app.server.run_masked_inpaint", must_not_run)
    status, payload = server_module.handle_masked_inpaint(
        {
            "image_path": "missing.png",
            "mask_path": "missing-mask.png",
            "prompt": "repair",
            "checkpoint": "anima-base-v1.0.safetensors",
            "loras": loras,
        },
        paths=_paths(tmp_path),
    )

    assert status == 400
    assert "LoRA" in payload["error"] or "loras" in payload["error"]
    assert called is False


@pytest.mark.parametrize(
    "field,value",
    [
        ("denoise", True),
        ("steps", 1.9),
        ("cfg", True),
        ("width", 64.5),
        ("height", True),
    ],
)
def test_masked_inpaint_rejects_lossy_numeric_coercions_before_runtime(tmp_path, monkeypatch, field, value):
    called = False

    def must_not_run(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("masked inpaint runtime must not run")

    monkeypatch.setattr("anima_app.server.run_masked_inpaint", must_not_run)
    request = {
        "image_path": "missing.png",
        "mask_path": "missing-mask.png",
        "prompt": "repair",
        "checkpoint": "anima-base-v1.0.safetensors",
        field: value,
    }
    status, payload = server_module.handle_masked_inpaint(request, paths=_paths(tmp_path))

    assert status == 400
    assert "must be" in payload["error"]
    assert called is False


def test_http_server_rejects_nonfinite_sam_and_inpaint_strings_before_model_work(tmp_path):
    server = create_http_server("127.0.0.1", 0, paths=_paths(tmp_path), default_dry_run=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        port = server.server_address[1]
        sam_status, sam_payload = _raw_http_request(
            port,
            "POST",
            "/api/sam3/segment",
            body=json.dumps({"image_path": "missing.png", "prompt": "clothes", "threshold": "NaN"}).encode(
                "utf-8"
            ),
            headers={"Content-Type": "application/json"},
        )
        inpaint_status, inpaint_payload = _raw_http_request(
            port,
            "POST",
            "/api/inpaint/masked",
            body=json.dumps(
                {
                    "image_path": "missing.png",
                    "mask_path": "missing-mask.png",
                    "prompt": "repair",
                    "denoise": "Infinity",
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )

        assert sam_status == 400
        assert "finite" in sam_payload["error"]
        assert inpaint_status == 400
        assert "finite" in inpaint_payload["error"]
    finally:
        server.shutdown()
        server.server_close()


def test_http_server_serves_manifest_detail_by_name(tmp_path):
    server = create_http_server("127.0.0.1", 0, paths=_paths(tmp_path), default_dry_run=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        request = urllib.request.Request(
            f"{base_url}/api/generate",
            data=json.dumps({"prompt": "detail portrait", "width": 512, "height": 768}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            generated = json.loads(response.read().decode("utf-8"))
        manifest_name = Path(generated["manifest_path"]).name

        with urllib.request.urlopen(f"{base_url}/api/manifests/{manifest_name}", timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))

        assert response.status == 200
        assert payload["prompt"] == "detail portrait"
        assert payload["status"] == "dry_run"
        assert payload["manifest_path"] == generated["manifest_path"]
        assert payload["output_url"] is None
    finally:
        server.shutdown()
        server.server_close()


def test_http_server_deletes_manifest_and_managed_output(tmp_path):
    paths = _paths(tmp_path)

    def fake_renderer(request, active_paths):
        output_path = active_paths.image_root / "delete-me.png"
        original_path = active_paths.image_root / "delete-me-original.png"
        output_path.parent.mkdir(parents=True)
        Image.new("RGB", (request.width, request.height), "gray").save(original_path)
        Image.new("RGB", (request.width, request.height), "white").save(output_path)
        return T2IRenderOutput(
            output_path=output_path,
            stages={"base_t2i": {"status": "completed"}},
            variants={"original": original_path, "face_detailer": output_path},
        )

    server = create_http_server("127.0.0.1", 0, paths=paths, renderer=fake_renderer, default_dry_run=False)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        request = urllib.request.Request(
            f"{base_url}/api/generate",
            data=json.dumps({"prompt": "delete portrait", "width": 512, "height": 768}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            generated = json.loads(response.read().decode("utf-8"))

        manifest_path = Path(generated["manifest_path"])
        output_path = Path(generated["output_path"])
        original_path = paths.image_root / "delete-me-original.png"
        manifest_name = manifest_path.name
        assert manifest_path.is_file()
        assert output_path.is_file()
        assert original_path.is_file()

        delete_request = urllib.request.Request(f"{base_url}/api/manifests/{manifest_name}", method="DELETE")
        with urllib.request.urlopen(delete_request, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))

        assert response.status == 200
        assert payload["status"] == "deleted"
        assert payload["deleted_manifest"] is True
        assert payload["deleted_output"] is True
        assert not manifest_path.exists()
        assert not output_path.exists()
        assert not original_path.exists()

        with urllib.request.urlopen(f"{base_url}/api/history?limit=8", timeout=5) as response:
            history = json.loads(response.read().decode("utf-8"))

        assert history["count"] == 0
    finally:
        server.shutdown()
        server.server_close()


def test_http_server_delete_manifest_rejects_bad_name(tmp_path):
    server = create_http_server("127.0.0.1", 0, paths=_paths(tmp_path), default_dry_run=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        request = urllib.request.Request(f"{base_url}/api/manifests/not-a-manifest.txt", method="DELETE")
        try:
            urllib.request.urlopen(request, timeout=5)
        except urllib.error.HTTPError as exc:
            assert exc.code == 400
            payload = json.loads(exc.read().decode("utf-8"))
        else:
            raise AssertionError("expected HTTP 400")

        assert payload["error"] == "manifest name must end with .json"
    finally:
        server.shutdown()
        server.server_close()


def test_manifest_delete_preflights_malformed_variants_without_deleting(tmp_path):
    paths = _paths(tmp_path)
    paths.image_root.mkdir(parents=True)
    paths.manifest_root.mkdir(parents=True)
    output_path = paths.image_root / "must-stay.png"
    output_path.write_bytes(_png_bytes())
    manifest_path = paths.manifest_root / "malformed.json"
    manifest_path.write_text(
        json.dumps({"output_path": str(output_path), "variants": ["not", "an", "object"]}),
        encoding="utf-8",
    )

    status, payload = server_module.handle_manifest_delete(manifest_path.name, paths=paths)

    assert status == 400
    assert payload["error_code"] == "manifest_invalid"
    assert manifest_path.is_file()
    assert output_path.is_file()


def test_manifest_delete_preserves_output_referenced_by_another_manifest(tmp_path):
    paths = _paths(tmp_path)
    paths.image_root.mkdir(parents=True)
    paths.manifest_root.mkdir(parents=True)
    shared_path = paths.image_root / "shared.png"
    shared_path.write_bytes(_png_bytes())
    first = paths.manifest_root / "first.json"
    second = paths.manifest_root / "second.json"
    first.write_text(json.dumps({"output_path": str(shared_path), "variants": {}}), encoding="utf-8")
    second.write_text(json.dumps({"output_path": str(shared_path), "variants": {}}), encoding="utf-8")

    first_status, first_payload = server_module.handle_manifest_delete(first.name, paths=paths)

    assert first_status == 200
    assert first_payload["deleted_manifest"] is True
    assert first_payload["deleted_output"] is False
    assert first_payload["deleted_files"] == []
    assert any(item["reason"] == "referenced_by_another_manifest" for item in first_payload["retained_files"])
    assert not first.exists()
    assert second.is_file()
    assert shared_path.is_file()

    second_status, second_payload = server_module.handle_manifest_delete(second.name, paths=paths)

    assert second_status == 200
    assert second_payload["deleted_output"] is True
    assert second_payload["deleted_bytes"] == len(_png_bytes())
    assert not second.exists()
    assert not shared_path.exists()


@pytest.mark.parametrize(
    "reference_kind",
    ["variant", "i2i-input"],
    ids=["variant", "i2i-input"],
)
def test_manifest_delete_preserves_variant_and_i2i_references(tmp_path, reference_kind):
    paths = _paths(tmp_path)
    paths.image_root.mkdir(parents=True)
    paths.manifest_root.mkdir(parents=True)
    shared_path = paths.image_root / "shared-reference.png"
    shared_path.write_bytes(_png_bytes())
    owner = paths.manifest_root / "owner.json"
    reference = paths.manifest_root / "reference.json"
    owner.write_text(json.dumps({"output_path": str(shared_path), "variants": {}}), encoding="utf-8")
    reference_payload = {"output_path": None, "variants": {}}
    if reference_kind == "variant":
        reference_payload["variants"] = {"shared": {"output_path": str(shared_path)}}
    else:
        reference_payload["i2i"] = {"image_path": str(shared_path)}
    reference.write_text(json.dumps(reference_payload), encoding="utf-8")

    status, payload = server_module.handle_manifest_delete(owner.name, paths=paths)

    assert status == 200
    assert payload["deleted_output"] is False
    assert any(item["reason"] == "referenced_by_another_manifest" for item in payload["retained_files"])
    assert not owner.exists()
    assert reference.is_file()
    assert shared_path.is_file()


def test_manifest_delete_rolls_back_when_a_later_unlink_fails(tmp_path, monkeypatch):
    paths = _paths(tmp_path)
    paths.image_root.mkdir(parents=True)
    paths.manifest_root.mkdir(parents=True)
    main_path = paths.image_root / "main.png"
    variant_path = paths.image_root / "variant.png"
    main_bytes = _png_bytes((20, 16))
    variant_bytes = _png_bytes((12, 10))
    main_path.write_bytes(main_bytes)
    variant_path.write_bytes(variant_bytes)
    manifest_path = paths.manifest_root / "rollback.json"
    manifest_path.write_text(
        json.dumps(
            {
                "output_path": str(main_path),
                "variants": {"original": {"output_path": str(variant_path)}},
            }
        ),
        encoding="utf-8",
    )
    original_unlink = Path.unlink

    def fail_variant_unlink(path, *args, **kwargs):
        if path == variant_path:
            raise OSError("injected variant unlink failure")
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fail_variant_unlink)

    status, payload = server_module.handle_manifest_delete(manifest_path.name, paths=paths)

    assert status == 400
    assert payload["error_code"] == "manifest_delete_failed"
    assert "injected variant unlink failure" in payload["error"]
    assert main_path.read_bytes() == main_bytes
    assert variant_path.read_bytes() == variant_bytes
    assert manifest_path.is_file()
    assert not list(paths.output_root.glob(".anima-delete-*"))


def test_manifest_delete_preserves_recovery_file_when_rollback_cannot_restore(tmp_path, monkeypatch):
    paths = _paths(tmp_path)
    paths.image_root.mkdir(parents=True)
    paths.manifest_root.mkdir(parents=True)
    main_path = paths.image_root / "rollback-main.png"
    variant_path = paths.image_root / "rollback-variant.png"
    main_bytes = _png_bytes((18, 14))
    main_path.write_bytes(main_bytes)
    variant_path.write_bytes(_png_bytes((10, 8)))
    manifest_path = paths.manifest_root / "rollback-recovery.json"
    manifest_path.write_text(
        json.dumps(
            {
                "output_path": str(main_path),
                "variants": {"original": {"output_path": str(variant_path)}},
            }
        ),
        encoding="utf-8",
    )
    original_unlink = Path.unlink
    original_link = server_module.os.link
    original_replace = server_module.os.replace

    def fail_variant_unlink(path, *args, **kwargs):
        if path == variant_path:
            raise OSError("injected later unlink failure")
        return original_unlink(path, *args, **kwargs)

    def fail_restore_link(source, destination, *args, **kwargs):
        if Path(source).parent.name.startswith(".anima-delete-") and Path(destination) == main_path:
            raise OSError("injected hardlink restore failure")
        return original_link(source, destination, *args, **kwargs)

    def fail_restore_replace(source, destination, *args, **kwargs):
        if Path(source).parent.name.startswith(".anima-delete-") and Path(destination) == main_path:
            raise OSError("injected replace restore failure")
        return original_replace(source, destination, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fail_variant_unlink)
    monkeypatch.setattr(server_module.os, "link", fail_restore_link)
    monkeypatch.setattr(server_module.os, "replace", fail_restore_replace)

    status, payload = server_module.handle_manifest_delete(manifest_path.name, paths=paths)
    recovery_files = list(paths.output_root.glob(".anima-delete-*/*.backup"))

    assert status == 400
    assert payload["error_code"] == "manifest_delete_failed"
    assert "recovery files retained" in payload["error"]
    assert not main_path.exists()
    assert variant_path.is_file()
    assert manifest_path.is_file()
    assert len(recovery_files) == 1
    assert recovery_files[0].read_bytes() == main_bytes


def test_manifest_delete_reports_staging_cleanup_failure(tmp_path, monkeypatch):
    paths = _paths(tmp_path)
    paths.image_root.mkdir(parents=True)
    paths.manifest_root.mkdir(parents=True)
    output_path = paths.image_root / "cleanup-warning.png"
    output_path.write_bytes(_png_bytes())
    manifest_path = paths.manifest_root / "cleanup-warning.json"
    manifest_path.write_text(json.dumps({"output_path": str(output_path), "variants": {}}), encoding="utf-8")
    original_os_unlink = server_module.os.unlink

    def fail_staging_cleanup(path, *args, **kwargs):
        if Path(path).parent.name.startswith(".anima-delete-"):
            raise OSError("injected staging cleanup failure")
        return original_os_unlink(path, *args, **kwargs)

    monkeypatch.setattr(server_module.os, "unlink", fail_staging_cleanup)

    status, payload = server_module.handle_manifest_delete(manifest_path.name, paths=paths)

    assert status == 200
    assert payload["deleted_output"] is True
    assert payload["cleanup_warning"] == "delete staging cleanup was incomplete"
    assert payload["recovery_files"]
    assert all(Path(path).is_file() for path in payload["recovery_files"])
    assert not output_path.exists()
    assert not manifest_path.exists()


def test_manifest_delete_never_follows_output_symlink(tmp_path):
    paths = _paths(tmp_path)
    paths.image_root.mkdir(parents=True)
    paths.manifest_root.mkdir(parents=True)
    outside = tmp_path / "outside.png"
    outside.write_bytes(_png_bytes())
    linked = paths.image_root / "linked.png"
    try:
        linked.symlink_to(outside)
    except OSError as exc:
        pytest.skip(f"symlinks are unavailable: {exc}")
    manifest_path = paths.manifest_root / "linked.json"
    manifest_path.write_text(json.dumps({"output_path": str(linked), "variants": {}}), encoding="utf-8")

    status, payload = server_module.handle_manifest_delete(manifest_path.name, paths=paths)

    assert status == 200
    assert payload["deleted_output"] is False
    assert any(item["reason"] == "symbolic_link" for item in payload["retained_files"])
    assert not manifest_path.exists()
    assert linked.is_symlink()
    assert outside.is_file()


def test_manifest_routes_reject_encoded_traversal_without_aliasing_basename(tmp_path):
    paths = _paths(tmp_path)
    paths.manifest_root.mkdir(parents=True)
    victim = paths.manifest_root / "victim.json"
    victim.write_text("{}", encoding="utf-8")
    server = create_http_server("127.0.0.1", 0, paths=paths, default_dry_run=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        port = server.server_address[1]
        get_status, _ = _raw_http_request(port, "GET", "/api/manifests/..%2Fvictim.json")
        delete_status, _ = _raw_http_request(port, "DELETE", "/api/manifests/..%2Fvictim.json")

        assert get_status == 400
        assert delete_status == 400
        assert victim.is_file()
    finally:
        server.shutdown()
        server.server_close()


@pytest.mark.parametrize("linked_root_name", ["output_root", "manifest_root"])
def test_manifest_delete_rejects_linked_managed_roots_without_deleting(
    tmp_path,
    monkeypatch,
    linked_root_name,
):
    paths = _paths(tmp_path)
    paths.image_root.mkdir(parents=True)
    paths.manifest_root.mkdir(parents=True)
    output_path = paths.image_root / "stay.png"
    output_path.write_bytes(_png_bytes())
    manifest_path = paths.manifest_root / "stay.json"
    manifest_path.write_text(json.dumps({"output_path": str(output_path), "variants": {}}), encoding="utf-8")
    linked_root = getattr(paths, linked_root_name)
    original_is_symlink = Path.is_symlink
    monkeypatch.setattr(
        Path,
        "is_symlink",
        lambda path: path == linked_root or original_is_symlink(path),
    )

    status, payload = server_module.handle_manifest_delete(manifest_path.name, paths=paths)

    assert status == 403
    assert payload["error"] == "forbidden"
    assert manifest_path.is_file()
    assert output_path.is_file()


def test_manifest_delete_and_health_reject_junction_output_root(tmp_path, monkeypatch):
    paths = _paths(tmp_path)
    paths.image_root.mkdir(parents=True)
    paths.manifest_root.mkdir(parents=True)
    output_path = paths.image_root / "junction-stay.png"
    output_path.write_bytes(_png_bytes())
    manifest_path = paths.manifest_root / "junction-stay.json"
    manifest_path.write_text(json.dumps({"output_path": str(output_path), "variants": {}}), encoding="utf-8")
    original_is_junction = getattr(Path, "is_junction", lambda path: False)
    monkeypatch.setattr(
        Path,
        "is_junction",
        lambda path: path == paths.output_root or original_is_junction(path),
        raising=False,
    )

    status, payload = server_module.handle_manifest_delete(manifest_path.name, paths=paths)
    health = server_module.build_health_payload(paths)

    assert status == 403
    assert payload["error"] == "forbidden"
    assert health["outputs"]["image_count"] == 0
    assert health["outputs"]["manifest_count"] == 0
    assert manifest_path.is_file()
    assert output_path.is_file()


def test_http_server_saves_and_lists_generation_presets(tmp_path):
    server = create_http_server("127.0.0.1", 0, paths=_paths(tmp_path), default_dry_run=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        preset_payload = {
            "name": "portrait draft",
            "request": {
                "prompt": "preset portrait",
                "negative_prompt": "low quality",
                "width": 512,
                "height": 768,
                "steps": 1,
                "cfg": 1.0,
                "seed": 77,
                "upscale": {"enabled": True, "scale": 1.5},
                "loras": [{"path": "style.safetensors", "model_strength": 0.5, "clip_strength": 0.5}],
            },
        }
        request = urllib.request.Request(
            f"{base_url}/api/presets",
            data=json.dumps(preset_payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            saved = json.loads(response.read().decode("utf-8"))

        with urllib.request.urlopen(f"{base_url}/api/presets", timeout=5) as response:
            listed = json.loads(response.read().decode("utf-8"))

        assert response.status == 200
        assert saved["name"] == "portrait draft"
        assert saved["slug"] == "portrait-draft"
        assert saved["request"]["prompt"] == "preset portrait"
        assert listed["count"] == 1
        assert listed["items"][0]["slug"] == "portrait-draft"
        assert listed["items"][0]["request"]["upscale"]["enabled"] is True
        assert listed["items"][0]["request"]["upscale"]["scale"] == 1.5
    finally:
        server.shutdown()
        server.server_close()


def test_http_server_rejects_overflowing_preset_value_without_closing_connection(tmp_path):
    server = create_http_server("127.0.0.1", 0, paths=_paths(tmp_path), default_dry_run=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status, payload = _raw_http_request(
            server.server_address[1],
            "POST",
            "/api/presets",
            body=json.dumps(
                {
                    "name": "overflow",
                    "request": {"prompt": "portrait", "cfg": 10**400},
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )

        assert status == 400
        assert "error" in payload
    finally:
        server.shutdown()
        server.server_close()


def test_http_server_exports_and_imports_generation_presets(tmp_path):
    source_paths = _paths(tmp_path / "source")
    source_server = create_http_server("127.0.0.1", 0, paths=source_paths, default_dry_run=True)
    source_thread = threading.Thread(target=source_server.serve_forever, daemon=True)
    source_thread.start()
    try:
        source_url = f"http://127.0.0.1:{source_server.server_address[1]}"
        save_request = urllib.request.Request(
            f"{source_url}/api/presets",
            data=json.dumps(
                {
                    "name": "portable preset",
                    "request": {
                        "prompt": "portable portrait",
                        "negative_prompt": "low quality",
                        "width": 512,
                        "height": 768,
                        "steps": 1,
                        "cfg": 1.0,
                    },
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(save_request, timeout=5).read()

        with urllib.request.urlopen(f"{source_url}/api/presets/export", timeout=5) as response:
            bundle = json.loads(response.read().decode("utf-8"))

        assert response.status == 200
        assert bundle["schema"] == "anima-app/presets.v1"
        assert bundle["count"] == 1
        assert bundle["items"][0]["name"] == "portable preset"
    finally:
        source_server.shutdown()
        source_server.server_close()

    target_paths = _paths(tmp_path / "target")
    target_server = create_http_server("127.0.0.1", 0, paths=target_paths, default_dry_run=True)
    target_thread = threading.Thread(target=target_server.serve_forever, daemon=True)
    target_thread.start()
    try:
        target_url = f"http://127.0.0.1:{target_server.server_address[1]}"
        import_request = urllib.request.Request(
            f"{target_url}/api/presets/import",
            data=json.dumps(bundle).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(import_request, timeout=5) as response:
            imported = json.loads(response.read().decode("utf-8"))

        assert response.status == 200
        assert imported["imported_count"] == 1
        assert imported["items"][0]["name"] == "portable preset"

        with urllib.request.urlopen(f"{target_url}/api/presets", timeout=5) as response:
            listed = json.loads(response.read().decode("utf-8"))

        assert listed["count"] == 1
        assert listed["items"][0]["request"]["prompt"] == "portable portrait"
    finally:
        target_server.shutdown()
        target_server.server_close()


def test_http_server_import_presets_rejects_invalid_bundle(tmp_path):
    server = create_http_server("127.0.0.1", 0, paths=_paths(tmp_path), default_dry_run=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        request = urllib.request.Request(
            f"{base_url}/api/presets/import",
            data=json.dumps({"items": [{"name": "", "request": {}}]}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            urllib.request.urlopen(request, timeout=5)
        except urllib.error.HTTPError as exc:
            assert exc.code == 400
            payload = json.loads(exc.read().decode("utf-8"))
        else:
            raise AssertionError("expected HTTP 400")

        assert payload["imported_count"] == 0
        assert payload["errors"][0]["error"] == "preset name is required"
    finally:
        server.shutdown()
        server.server_close()


def test_preset_listing_keeps_valid_items_when_one_file_is_malformed(tmp_path):
    paths = _paths(tmp_path)
    status, saved = server_module.handle_preset_save(
        {"name": "valid preset", "request": {"prompt": "valid portrait"}},
        paths=paths,
    )
    assert status == 200
    preset_root = paths.output_root / "presets"
    (preset_root / "broken.json").write_text("{not-json", encoding="utf-8")

    payload = server_module.handle_presets(paths=paths)

    assert payload["count"] == 1
    assert payload["items"][0]["slug"] == saved["slug"]
    assert payload["invalid_count"] == 1
    assert payload["errors"][0]["filename"] == "broken.json"


def test_preset_listing_skips_excessively_nested_json_and_save_stays_structured(tmp_path):
    paths = _paths(tmp_path)
    status, _ = server_module.handle_preset_save(
        {"name": "valid preset", "request": {"prompt": "valid portrait"}},
        paths=paths,
    )
    assert status == 200
    preset_root = paths.output_root / "presets"
    depth = 1_100
    nested = (
        '{"name":"deep","slug":"deep","request":{"prompt":"portrait","extra":'
        + "[" * depth
        + "0"
        + "]" * depth
        + "}}"
    )
    (preset_root / "deep.json").write_text(nested, encoding="utf-8")

    listed = server_module.handle_presets(paths=paths)
    save_status, save_payload = server_module.handle_preset_save(
        {"name": "deep", "request": {"prompt": "replacement"}},
        paths=paths,
    )

    assert listed["count"] == 1
    assert listed["invalid_count"] == 1
    assert listed["errors"][0]["filename"] == "deep.json"
    assert save_status == 409
    assert save_payload["error_code"] == "preset_slug_conflict"


def test_preset_save_is_atomic_when_replace_fails(tmp_path, monkeypatch):
    paths = _paths(tmp_path)
    status, _ = server_module.handle_preset_save(
        {"name": "atomic preset", "request": {"prompt": "original"}},
        paths=paths,
    )
    assert status == 200
    target = paths.output_root / "presets" / "atomic-preset.json"
    original_bytes = target.read_bytes()
    original_replace = Path.replace

    def fail_target_replace(source, destination):
        if Path(destination) == target:
            raise OSError("replace failed")
        return original_replace(source, destination)

    monkeypatch.setattr(Path, "replace", fail_target_replace)

    status, payload = server_module.handle_preset_save(
        {"name": "atomic preset", "request": {"prompt": "replacement"}},
        paths=paths,
    )

    assert status == 500
    assert payload["error_code"] == "preset_write_failed"
    assert target.read_bytes() == original_bytes
    assert not list(target.parent.glob("*.tmp"))


def test_preset_save_rejects_linked_root_and_target(tmp_path, monkeypatch):
    paths = _paths(tmp_path)
    preset_root = paths.output_root / "presets"
    original_path_is_link = server_module._path_is_link
    monkeypatch.setattr(
        server_module,
        "_path_is_link",
        lambda path: Path(path) == preset_root or original_path_is_link(path),
    )

    status, payload = server_module.handle_preset_save(
        {"name": "linked root", "request": {"prompt": "portrait"}},
        paths=paths,
    )

    assert status == 403
    assert payload["error_code"] == "preset_storage_unsafe"
    monkeypatch.setattr(server_module, "_path_is_link", original_path_is_link)

    status, _ = server_module.handle_preset_save(
        {"name": "linked target", "request": {"prompt": "original"}},
        paths=paths,
    )
    assert status == 200
    target = preset_root / "linked-target.json"
    original_bytes = target.read_bytes()
    monkeypatch.setattr(
        server_module,
        "_path_is_link",
        lambda path: Path(path) == target or original_path_is_link(path),
    )

    status, payload = server_module.handle_preset_save(
        {"name": "linked target", "request": {"prompt": "replacement"}},
        paths=paths,
    )

    assert status == 403
    assert payload["error_code"] == "preset_storage_unsafe"
    assert target.read_bytes() == original_bytes


def test_preset_save_canonicalizes_validated_request(tmp_path):
    paths = _paths(tmp_path)

    status, payload = server_module.handle_preset_save(
        {
            "name": "canonical",
            "request": {
                "prompt": "portrait",
                "negative": "low quality",
                "wildcard_mode": "off",
                "loras": ["style.safetensors|0.4|0.6"],
            },
        },
        paths=paths,
    )

    assert status == 200
    assert payload["request"]["negative_prompt"] == "low quality"
    assert "negative" not in payload["request"]
    assert payload["request"]["wildcard_mode"] == "random"
    assert payload["request"]["loras"] == [
        {"path": "style.safetensors", "model_strength": 0.4, "clip_strength": 0.6}
    ]


def test_preset_import_rejects_foreign_schema_before_writing(tmp_path):
    paths = _paths(tmp_path)

    status, payload = server_module.handle_preset_import(
        {
            "schema": "another-app/presets.v9",
            "items": [{"name": "foreign", "request": {"prompt": "portrait"}}],
        },
        paths=paths,
    )

    assert status == 400
    assert payload["error_code"] == "preset_import_schema_invalid"
    assert not (paths.output_root / "presets").exists()


@pytest.mark.parametrize(
    "items",
    [
        [
            {"name": "valid first", "request": {"prompt": "portrait"}},
            {"name": "invalid second", "request": {"prompt": ""}},
        ],
        [
            {"name": "same slug", "request": {"prompt": "one"}},
            {"name": "same-slug", "request": {"prompt": "two"}},
        ],
    ],
)
def test_preset_import_prevalidates_entire_bundle_before_writing(tmp_path, items):
    paths = _paths(tmp_path)

    status, payload = server_module.handle_preset_import(
        {"schema": "anima-app/presets.v1", "items": items},
        paths=paths,
    )

    assert status == 400
    assert payload["imported_count"] == 0
    assert payload["errors"]
    assert not list((paths.output_root / "presets").glob("*.json"))


def test_preset_import_rolls_back_earlier_files_when_a_later_write_fails(tmp_path, monkeypatch):
    paths = _paths(tmp_path)
    save_status, _ = server_module.handle_preset_save(
        {"name": "existing", "request": {"prompt": "original prompt"}},
        paths=paths,
    )
    assert save_status == 200
    existing_path = paths.output_root / "presets" / "existing.json"
    original_bytes = existing_path.read_bytes()
    real_write = server_module._write_json_atomically
    call_count = 0

    def fail_second_write(path, payload):
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            raise OSError("simulated second preset write failure")
        real_write(path, payload)

    monkeypatch.setattr(server_module, "_write_json_atomically", fail_second_write)

    status, payload = server_module.handle_preset_import(
        {
            "schema": "anima-app/presets.v1",
            "items": [
                {"name": "existing", "request": {"prompt": "replacement prompt"}},
                {"name": "new second", "request": {"prompt": "second prompt"}},
            ],
        },
        paths=paths,
    )

    assert status == 500
    assert payload["imported_count"] == 0
    assert existing_path.read_bytes() == original_bytes
    assert not (paths.output_root / "presets" / "new-second.json").exists()


def test_preset_import_preserves_recovery_copy_when_rollback_replace_fails(tmp_path, monkeypatch):
    paths = _paths(tmp_path)
    save_status, _ = server_module.handle_preset_save(
        {"name": "existing", "request": {"prompt": "original prompt"}},
        paths=paths,
    )
    assert save_status == 200
    preset_root = paths.output_root / "presets"
    existing_path = preset_root / "existing.json"
    original_bytes = existing_path.read_bytes()
    real_write = server_module._write_json_atomically
    real_replace = Path.replace
    call_count = 0

    def fail_second_write(path, payload):
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            raise OSError("simulated second preset write failure")
        real_write(path, payload)

    def fail_recovery_replace(path, target):
        if path.name.endswith(".restore.tmp"):
            raise OSError("simulated preset recovery replace failure")
        return real_replace(path, target)

    monkeypatch.setattr(server_module, "_write_json_atomically", fail_second_write)
    monkeypatch.setattr(Path, "replace", fail_recovery_replace)

    status, payload = server_module.handle_preset_import(
        {
            "schema": "anima-app/presets.v1",
            "items": [
                {"name": "existing", "request": {"prompt": "replacement prompt"}},
                {"name": "new second", "request": {"prompt": "second prompt"}},
            ],
        },
        paths=paths,
    )
    recovery_files = list(preset_root.glob("existing.json.*.restore.tmp"))

    assert status == 500
    assert payload["imported_count"] == 0
    assert "recovery file retained" in payload["errors"][0]["error"]
    assert len(recovery_files) == 1
    assert recovery_files[0].read_bytes() == original_bytes
    assert json.loads(existing_path.read_text(encoding="utf-8"))["request"]["prompt"] == "replacement prompt"


def test_preset_timestamp_sorts_new_save_ahead_of_legacy_file(tmp_path):
    paths = _paths(tmp_path)
    preset_root = paths.output_root / "presets"
    preset_root.mkdir(parents=True)
    legacy = preset_root / "legacy.json"
    legacy.write_text(
        json.dumps({"name": "legacy", "slug": "legacy", "request": {"prompt": "old"}}),
        encoding="utf-8",
    )
    os.utime(legacy, (1, 1))

    status, saved = server_module.handle_preset_save(
        {"name": "new preset", "request": {"prompt": "new"}},
        paths=paths,
    )
    listed = server_module.handle_presets(paths=paths)

    assert status == 200
    assert isinstance(saved["updated_at"], (int, float))
    assert [item["slug"] for item in listed["items"]] == ["new-preset", "legacy"]
    assert all(isinstance(item["updated_at"], (int, float)) for item in listed["items"])


@pytest.mark.parametrize("name", ["CON", "A" * 121])
def test_preset_save_rejects_unsafe_or_overlong_name(tmp_path, name):
    paths = _paths(tmp_path)

    status, payload = server_module.handle_preset_save(
        {"name": name, "request": {"prompt": "portrait"}},
        paths=paths,
    )

    assert status == 400
    assert payload["error_code"] == "preset_name_invalid"
    assert not list((paths.output_root / "presets").glob("*.json"))


def test_preset_save_rejects_different_name_with_same_slug(tmp_path):
    paths = _paths(tmp_path)
    status, original = server_module.handle_preset_save(
        {"name": "portrait draft", "request": {"prompt": "original"}},
        paths=paths,
    )
    assert status == 200

    status, payload = server_module.handle_preset_save(
        {"name": "portrait-draft", "request": {"prompt": "replacement"}},
        paths=paths,
    )
    listed = server_module.handle_presets(paths=paths)

    assert status == 409
    assert payload["error_code"] == "preset_slug_conflict"
    assert listed["items"][0]["name"] == original["name"]
    assert listed["items"][0]["request"]["prompt"] == "original"


def test_http_server_serves_lora_inventory(tmp_path):
    paths = _paths(tmp_path)
    lora = paths.model_root / "loras" / "style.safetensors"
    lora.parent.mkdir(parents=True)
    lora.write_bytes(b"lora")
    server = create_http_server("127.0.0.1", 0, paths=paths, default_dry_run=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        with urllib.request.urlopen(f"{base_url}/api/loras", timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))

        assert response.status == 200
        assert payload == {"count": 1, "items": [{"relative_path": "style.safetensors", "size_bytes": 4}]}
    finally:
        server.shutdown()
        server.server_close()


def test_http_server_serves_wildcard_inventory(tmp_path):
    paths = _paths(tmp_path)
    wildcard_file = paths.project_root / "wildcards" / "style.txt"
    preset_file = paths.project_root / "wildcards" / "presets" / "portrait_clean.txt"
    wildcard_file.parent.mkdir(parents=True)
    wildcard_file.write_text("soft lineart\nbold shadows\n", encoding="utf-8")
    preset_file.parent.mkdir(parents=True)
    preset_file.write_text("clean portrait preset\n", encoding="utf-8")
    server = create_http_server("127.0.0.1", 0, paths=paths, default_dry_run=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        with urllib.request.urlopen(f"{base_url}/api/wildcards", timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))

        assert response.status == 200
        assert payload == {
            "count": 1,
            "items": [{"name": "style", "token": "__style__", "relative_path": "style.txt", "value_count": 2}],
            "preset_count": 1,
            "presets": [
                {
                    "name": "portrait_clean",
                    "token": "__presets/portrait_clean__",
                    "relative_path": "presets/portrait_clean.txt",
                    "value_count": 1,
                }
            ],
        }
    finally:
        server.shutdown()
        server.server_close()


def test_http_server_serves_autocomplete_items(tmp_path):
    paths = _paths(tmp_path)
    paths.autocomplete_source.parent.mkdir(parents=True)
    paths.autocomplete_source.write_text(
        "solo,8949083\n1girl,7397900\nlong_hair,5792347\nlooking_at_viewer,5350130\n",
        encoding="utf-8",
    )
    server = create_http_server("127.0.0.1", 0, paths=paths, default_dry_run=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        with urllib.request.urlopen(f"{base_url}/api/autocomplete?q=lo&limit=2", timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))

        assert response.status == 200
        assert payload["ready"] is True
        assert payload["count"] == 4
        assert [item["value"] for item in payload["items"]] == ["long_hair", "looking_at_viewer"]
    finally:
        server.shutdown()
        server.server_close()


def test_http_server_serves_wildcard_preview(tmp_path):
    paths = _paths(tmp_path)
    wildcard_file = paths.project_root / "wildcards" / "style.txt"
    wildcard_file.parent.mkdir(parents=True)
    wildcard_file.write_text("soft lineart\n", encoding="utf-8")
    server = create_http_server("127.0.0.1", 0, paths=paths, default_dry_run=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        status, payload = _post_json(
            f"{base_url}/api/wildcards/preview",
            {"prompt": "anime portrait, __style__", "wildcard_mode": "random", "seed": 1},
        )

        assert status == 200
        assert payload["prompt"] == "anime portrait, soft lineart"
        assert payload["selection_count"] == 1
    finally:
        server.shutdown()
        server.server_close()


def test_http_server_dry_run_generate_records_lora_payload(tmp_path):
    paths = _paths(tmp_path)
    lora = paths.model_root / "loras" / "style.safetensors"
    lora.parent.mkdir(parents=True)
    lora.write_bytes(b"lora")
    server = create_http_server("127.0.0.1", 0, paths=paths, default_dry_run=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        request = urllib.request.Request(
            f"{base_url}/api/generate",
            data=json.dumps(
                {
                    "prompt": "anime portrait",
                    "width": 512,
                    "height": 768,
                    "loras": [{"path": "style.safetensors", "model_strength": 0.75, "clip_strength": 0.75}],
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
        manifest = json.loads(Path(payload["manifest_path"]).read_text(encoding="utf-8"))

        assert response.status == 200
        assert manifest["loras"] == [{"path": "style.safetensors", "model_strength": 0.75, "clip_strength": 0.75}]
    finally:
        server.shutdown()
        server.server_close()


def test_http_server_dry_run_generate_records_stage_payloads(tmp_path):
    paths = _paths(tmp_path)
    reference = paths.input_root / "references" / "reference.png"
    reference.parent.mkdir(parents=True)
    Image.new("RGB", (16, 16), "white").save(reference)
    server = create_http_server("127.0.0.1", 0, paths=paths, default_dry_run=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        request = urllib.request.Request(
            f"{base_url}/api/generate",
            data=json.dumps(
                {
                    "prompt": "anime portrait",
                    "width": 512,
                    "height": 768,
                    "i2i": {"enabled": True, "image_path": "inputs/references/reference.png", "denoise": 0.42},
                    "upscale": {"enabled": True, "scale": 1.5, "tiled": True, "tile_size": 64, "overlap": 8},
                    "vae_decode": {"mode": "tiled", "tile_size": 96, "overlap": 16},
                    "face_detailer": {"enabled": True, "detector": "bbox/face_yolov8m.pt"},
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
        manifest = json.loads(Path(payload["manifest_path"]).read_text(encoding="utf-8"))

        assert response.status == 200
        assert manifest["i2i"] == {
            "enabled": True,
            "image_path": "inputs/references/reference.png",
            "denoise": 0.42,
        }
        assert manifest["upscale"]["enabled"] is True
        assert manifest["upscale"]["scale"] == 1.5
        assert manifest["upscale"]["tiled"] is True
        assert manifest["upscale"]["tile_size"] == 64
        assert manifest["upscale"]["overlap"] == 8
        assert manifest["vae_decode"] == {"mode": "tiled", "tile_size": 96, "overlap": 16}
        assert manifest["stages"]["vae_decode"]["method"] == "not_run"
        assert manifest["face_detailer"]["enabled"] is True
        assert manifest["face_detailer"]["detector"] == "bbox/face_yolov8m.pt"
        assert manifest["stages"]["face_detailer"]["status"] == "skipped"
    finally:
        server.shutdown()
        server.server_close()


def test_http_server_imports_lora_from_local_path(tmp_path):
    paths = _paths(tmp_path)
    source = tmp_path / "external" / "new_style.safetensors"
    _write_safetensors(source)
    server = create_http_server("127.0.0.1", 0, paths=paths, default_dry_run=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        request = urllib.request.Request(
            f"{base_url}/api/loras/import",
            data=json.dumps({"path": str(source)}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))

        assert response.status == 200
        assert payload["imported"] == str(paths.model_root / "loras" / "new_style.safetensors")
        assert payload["loras"] == {
            "count": 1,
            "items": [{"relative_path": "new_style.safetensors", "size_bytes": source.stat().st_size}],
        }
        assert (paths.model_root / "loras" / "new_style.safetensors").read_bytes() == source.read_bytes()
    finally:
        server.shutdown()
        server.server_close()


def test_http_server_serves_checkpoint_inventory(tmp_path):
    paths = _paths(tmp_path)
    checkpoint = paths.model_root / "diffusion_models" / "variants" / "anima-alt.safetensors"
    checkpoint.parent.mkdir(parents=True)
    checkpoint.write_bytes(b"alternate")
    preferred = paths.model_root / "diffusion_models" / "anima-aesthetic-v1.1.safetensors"
    preferred.write_bytes(b"aesthetic")
    server = create_http_server("127.0.0.1", 0, paths=paths, default_dry_run=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        with urllib.request.urlopen(f"{base_url}/api/checkpoints", timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))

        assert response.status == 200
        assert payload == {
            "count": 2,
            "default": "anima-aesthetic-v1.1.safetensors",
            "items": [
                {"relative_path": "anima-aesthetic-v1.1.safetensors", "size_bytes": 9},
                {"relative_path": "variants/anima-alt.safetensors", "size_bytes": 9},
            ],
        }
    finally:
        server.shutdown()
        server.server_close()


def test_http_server_serves_version_metadata(tmp_path):
    server = create_http_server("127.0.0.1", 0, paths=_paths(tmp_path), default_dry_run=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        with urllib.request.urlopen(f"{base_url}/api/version", timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))

        assert response.status == 200
        assert payload["version"] == __version__
        assert payload["repository"] == "raspie10032/anima-app"
        assert payload["repository_url"] == "https://github.com/raspie10032/anima-app"
        assert response.headers["Server"].startswith(f"AnimaAPP/{__version__}")
    finally:
        server.shutdown()
        server.server_close()


def test_http_server_reports_unconfigured_llm_runtime(tmp_path):
    server = create_http_server("127.0.0.1", 0, paths=_paths(tmp_path), default_dry_run=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        status, payload = _get_json(f"{base_url}/api/llm/status")

        assert status == 200
        assert payload["configured"] is False
        assert payload["ok"] is False
    finally:
        server.shutdown()
        server.server_close()


def test_http_server_proxies_llm_generate_completion_text(tmp_path):
    class FakeLlmClient:
        def health(self):
            return {
                "ok": True,
                "active_prompt_tokens": 1214,
                "target_system_ram_guard": {"process_ram_mb": 2177},
                "cuda_memory": {"reserved_mb": 7453.3},
            }

        def generate(self, payload):
            assert payload["prompt_suffix"] == "\nAnswer briefly."
            return {
                "ok": True,
                "completion_text": "prompt answer",
                "prompt_context": {"prompt_tokens": 1214},
                "requested_new_tokens": 8,
                "generation_elapsed_sec": 4.1,
            }

    server = create_http_server(
        "127.0.0.1",
        0,
        paths=_paths(tmp_path),
        default_dry_run=True,
        llm_client=FakeLlmClient(),
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        status, payload = _post_json(
            f"{base_url}/api/llm/generate",
            {"prompt_suffix": "\nAnswer briefly.", "max_new_tokens": 8},
        )

        assert status == 200
        assert payload["ok"] is True
        assert payload["configured"] is True
        assert payload["completion_text"] == "prompt answer"
        assert payload["metrics"]["prompt_tokens"] == 1214
        assert payload["metrics"]["requested_new_tokens"] == 8
    finally:
        server.shutdown()
        server.server_close()


def test_http_server_serves_update_check_payload(tmp_path, monkeypatch):
    def fake_check():
        return {
            "status": "update_available",
            "current_version": "0.1.0",
            "latest_version": "v0.1.1",
            "latest_url": "https://github.com/raspie10032/anima-app/releases/tag/v0.1.1",
        }

    monkeypatch.setattr("anima_app.server.check_github_update", fake_check)
    server = create_http_server("127.0.0.1", 0, paths=_paths(tmp_path), default_dry_run=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        with urllib.request.urlopen(f"{base_url}/api/update-check", timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))

        assert response.status == 200
        assert payload["status"] == "update_available"
        assert payload["latest_version"] == "v0.1.1"
        assert payload["latest_url"].endswith("/v0.1.1")
    finally:
        server.shutdown()
        server.server_close()


def test_http_server_import_lora_rejects_bad_path(tmp_path):
    server = create_http_server("127.0.0.1", 0, paths=_paths(tmp_path), default_dry_run=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        request = urllib.request.Request(
            f"{base_url}/api/loras/import",
            data=json.dumps({"path": str(tmp_path / "missing.safetensors")}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            urllib.request.urlopen(request, timeout=5)
        except urllib.error.HTTPError as exc:
            assert exc.code == 400
            payload = json.loads(exc.read().decode("utf-8"))
        else:
            raise AssertionError("expected HTTP 400")

        assert "missing.safetensors" in payload["error"]
    finally:
        server.shutdown()
        server.server_close()


def test_http_reference_upload_streams_raw_image_to_managed_inputs(tmp_path):
    paths = _paths(tmp_path)
    server = create_http_server("127.0.0.1", 0, paths=paths, default_dry_run=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        body = _png_bytes((18, 14))
        status, payload = _raw_http_request(
            server.server_address[1],
            "POST",
            "/api/inputs/reference?filename=portrait.png",
            body=body,
            headers={"Content-Type": "image/png"},
        )

        assert status == 201
        assert payload["status"] == "reference_uploaded"
        assert re.fullmatch(r"inputs/references/[0-9a-f]{64}\.png", payload["relative_path"])
        assert payload["width"] == 18
        assert payload["height"] == 14
        assert (paths.project_root / payload["relative_path"]).read_bytes() == body

        repeated_status, repeated = _raw_http_request(
            server.server_address[1],
            "POST",
            "/api/inputs/reference?filename=portrait.png",
            body=body,
            headers={"Content-Type": "application/octet-stream"},
        )
        assert repeated_status == 201
        assert repeated["relative_path"] == payload["relative_path"]
        assert repeated["deduplicated"] is True
    finally:
        server.shutdown()
        server.server_close()


def test_http_lora_upload_streams_raw_safetensors_and_never_overwrites_collision(tmp_path):
    paths = _paths(tmp_path)
    first_source = tmp_path / "first.safetensors"
    second_source = tmp_path / "second.safetensors"
    _write_safetensors(first_source, value=1.0)
    _write_safetensors(second_source, value=2.0)
    first_bytes = first_source.read_bytes()
    server = create_http_server("127.0.0.1", 0, paths=paths, default_dry_run=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        first_status, first = _raw_http_request(
            server.server_address[1],
            "POST",
            "/api/loras/upload?filename=style.safetensors",
            body=first_bytes,
            headers={"Content-Type": "application/octet-stream"},
        )
        second_status, second = _raw_http_request(
            server.server_address[1],
            "POST",
            "/api/loras/upload?filename=style.safetensors",
            body=second_source.read_bytes(),
            headers={"Content-Type": "application/octet-stream"},
        )

        assert first_status == 201
        assert second_status == 201
        assert first["relative_path"] == "style.safetensors"
        assert re.fullmatch(r"style-[0-9a-f]{12}\.safetensors", second["relative_path"])
        assert (paths.model_root / "loras" / "style.safetensors").read_bytes() == first_bytes
        assert (paths.model_root / "loras" / second["relative_path"]).is_file()
        _, inventory = _get_json(f"http://127.0.0.1:{server.server_address[1]}/api/loras")
        assert {item["relative_path"] for item in inventory["items"]} == {
            first["relative_path"],
            second["relative_path"],
        }
    finally:
        server.shutdown()
        server.server_close()


@pytest.mark.parametrize(
    "path,headers,body,expected_status",
    [
        ("/api/inputs/reference", {"Content-Type": "image/png"}, b"x", 400),
        (
            "/api/inputs/reference?filename=portrait.png",
            {"Content-Type": "text/plain"},
            b"x",
            415,
        ),
        (
            "/api/inputs/reference?filename=portrait.png",
            {"Content-Type": "image/png", "Content-Length": "10"},
            b"x",
            400,
        ),
        (
            "/api/inputs/reference?filename=portrait.png",
            {"Content-Type": "image/png", "Content-Length": str(64 * 1024 * 1024 + 1)},
            None,
            413,
        ),
        (
            "/api/loras/upload?filename=style.txt",
            {
                "Content-Type": "application/octet-stream",
                "Content-Length": str(server_module.MAX_LORA_UPLOAD_BYTES + 1),
            },
            None,
            400,
        ),
    ],
)
def test_http_upload_rejects_invalid_metadata_and_cleans_temporary_files(
    tmp_path,
    path,
    headers,
    body,
    expected_status,
):
    paths = _paths(tmp_path)
    server = create_http_server("127.0.0.1", 0, paths=paths, default_dry_run=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status, payload = _raw_http_request(
            server.server_address[1],
            "POST",
            path,
            body=body,
            headers=headers,
            shutdown_write=True,
        )

        assert status == expected_status
        assert "error" in payload
        assert not list(paths.project_root.rglob("*.upload"))
    finally:
        server.shutdown()
        server.server_close()


@pytest.mark.parametrize("endpoint", ["/api/generate", "/api/jobs"])
@pytest.mark.parametrize("input_kind", ["absolute_reference", "escaping_lora"])
def test_http_generation_rejects_unmanaged_input_paths_before_work_starts(tmp_path, endpoint, input_kind):
    paths = _paths(tmp_path)
    outside_reference = tmp_path / "outside.png"
    Image.new("RGB", (8, 8), "white").save(outside_reference)
    generation = {"prompt": "managed only", "width": 32, "height": 48, "steps": 1, "dry_run": True}
    if input_kind == "absolute_reference":
        generation["i2i"] = {"enabled": True, "image_path": str(outside_reference), "denoise": 0.4}
    else:
        generation["loras"] = [{"path": "../outside.safetensors"}]

    server = create_http_server("127.0.0.1", 0, paths=paths, default_dry_run=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        body = {"request": generation} if endpoint == "/api/jobs" else generation
        status, payload = _raw_http_request(
            server.server_address[1],
            "POST",
            endpoint,
            body=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )

        assert status == 400
        assert payload["error_code"] == "generation_invalid_request"
        assert "managed" in payload["error"]
        if endpoint == "/api/jobs":
            _, jobs = _get_json(f"http://127.0.0.1:{server.server_address[1]}/api/jobs")
            assert jobs["count"] == 0
    finally:
        server.shutdown()
        server.server_close()


def test_http_generate_accepts_uploaded_managed_reference_and_lora(tmp_path):
    paths = _paths(tmp_path)
    lora_source = tmp_path / "style.safetensors"
    _write_safetensors(lora_source)
    server = create_http_server("127.0.0.1", 0, paths=paths, default_dry_run=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        reference_status, reference = _raw_http_request(
            server.server_address[1],
            "POST",
            "/api/inputs/reference?filename=portrait.png",
            body=_png_bytes(),
            headers={"Content-Type": "image/png"},
        )
        lora_status, lora = _raw_http_request(
            server.server_address[1],
            "POST",
            "/api/loras/upload?filename=style.safetensors",
            body=lora_source.read_bytes(),
            headers={"Content-Type": "application/octet-stream"},
        )
        generate_status, generated = _raw_http_request(
            server.server_address[1],
            "POST",
            "/api/generate",
            body=json.dumps(
                {
                    "prompt": "managed assets",
                    "width": 32,
                    "height": 48,
                    "steps": 1,
                    "dry_run": True,
                    "i2i": {"enabled": True, "image_path": reference["relative_path"], "denoise": 0.4},
                    "loras": [{"path": lora["relative_path"]}],
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )

        assert reference_status == 201
        assert lora_status == 201
        assert generate_status == 200
        manifest = json.loads(Path(generated["manifest_path"]).read_text(encoding="utf-8"))
        assert manifest["i2i"]["image_path"] == reference["relative_path"]
        assert manifest["loras"][0]["path"] == lora["relative_path"]
    finally:
        server.shutdown()
        server.server_close()


def test_index_html_max_attributes_match_server_resource_limits():
    expected_maxima = {
        "queue-count": server_module.MAX_QUEUE_JOBS,
        "seed": server_module.MAX_BROWSER_SAFE_SEED,
        "width": requests_module.MAX_GENERATION_DIMENSION,
        "height": requests_module.MAX_GENERATION_DIMENSION,
        "steps": requests_module.MAX_SAMPLING_STEPS,
        "cfg": requests_module.MAX_CFG,
        "upscale-scale": requests_module.MAX_UPSCALE_SCALE,
        "upscale-steps": requests_module.MAX_SAMPLING_STEPS,
        "upscale-tile-size": requests_module.MAX_TILE_SIZE,
        "vae-tile-size": requests_module.MAX_TILE_SIZE,
        "face-steps": requests_module.MAX_SAMPLING_STEPS,
        "face-crop-scale": requests_module.MAX_FACE_CROP_SCALE,
        "face-padding": requests_module.MAX_FACE_PADDING,
        "face-feather": requests_module.MAX_FACE_FEATHER,
    }

    for element_id, expected in expected_maxima.items():
        assert _input_number_attribute(INDEX_DOCUMENT, element_id, "max") == float(expected)


def test_browser_resource_guards_share_server_limits_and_validate_all_submit_paths():
    defaults_match = re.search(
        r'<script id="anima-defaults" type="application/json">(.*?)</script>',
        INDEX_DOCUMENT,
    )
    assert defaults_match is not None
    defaults = json.loads(defaults_match.group(1))

    assert defaults["limits"]["max_seed_safe"] == server_module.MAX_BROWSER_SAFE_SEED
    assert defaults["limits"]["max_base_image_pixels"] == requests_module.MAX_BASE_IMAGE_PIXELS
    assert defaults["limits"]["max_output_image_pixels"] == requests_module.MAX_OUTPUT_IMAGE_PIXELS
    assert defaults["limits"]["max_reference_upload_bytes"] == server_module.MAX_REFERENCE_UPLOAD_BYTES
    assert defaults["limits"]["max_lora_upload_bytes"] == server_module.MAX_LORA_UPLOAD_BYTES
    assert f'id="sam3-prompt" maxlength="{requests_module.MAX_PROMPT_CHARACTERS}"' in INDEX_DOCUMENT
    assert f'id="inpaint-prompt" maxlength="{requests_module.MAX_PROMPT_CHARACTERS}"' in INDEX_DOCUMENT
    assert f'id="inpaint-negative" maxlength="{requests_module.MAX_PROMPT_CHARACTERS}"' in INDEX_DOCUMENT
    assert 'id="upscale-overlap" name="upscale_overlap" type="number" min="0" max="32"' in INDEX_DOCUMENT
    assert 'id="vae-overlap" name="vae_overlap" type="number" min="0" max="32"' in INDEX_DOCUMENT
    assert "8 * Math.round((width / 8) * scale)" in APP_JS
    assert "overlapInput.max = String(Math.floor(tileSize / 4))" in APP_JS
    assert APP_JS.count("generationFormIsValid({report: true})") >= 3
    assert "function seedNumberFromElement" in APP_JS
    assert "seed: seedValue ? Number(seedValue) : null" not in APP_JS


def test_index_exposes_managed_reference_and_lora_file_inputs_without_visible_paths():
    assert 'id="i2i-image" name="i2i_image" type="hidden"' in INDEX_DOCUMENT
    assert 'id="reference-file" type="file" accept="image/png,image/jpeg,image/webp"' in INDEX_DOCUMENT
    assert 'id="reference-drop-zone" class="file-drop-zone"' in INDEX_DOCUMENT
    assert 'id="reference-preview" class="reference-preview"' in INDEX_DOCUMENT
    assert 'id="reference-upload-status" class="upload-status" aria-live="polite"' in INDEX_DOCUMENT
    assert 'id="remove-reference"' in INDEX_DOCUMENT
    assert 'id="lora-file" type="file" accept=".safetensors,application/octet-stream"' in INDEX_DOCUMENT
    assert 'id="lora-drop-zone" class="file-drop-zone"' in INDEX_DOCUMENT
    assert 'id="lora-upload-status" class="upload-status" aria-live="polite"' in INDEX_DOCUMENT
    assert 'id="lora-path"' not in INDEX_DOCUMENT
    assert 'id="reference-drop-zone" class="file-drop-zone" tabindex=' not in INDEX_DOCUMENT
    assert 'id="lora-drop-zone" class="file-drop-zone" tabindex=' not in INDEX_DOCUMENT
    assert 'aria-describedby="reference-file-hint reference-upload-status"' in INDEX_DOCUMENT
    assert 'aria-describedby="lora-file-hint lora-upload-status"' in INDEX_DOCUMENT
    assert f"최대 {server_module.MAX_REFERENCE_UPLOAD_BYTES // (1024 * 1024)} MiB" in INDEX_DOCUMENT
    assert f"최대 {server_module.MAX_LORA_UPLOAD_BYTES // (1024 * 1024 * 1024)} GiB" in INDEX_DOCUMENT
    assert ".reference-preview {\n      display: block;\n      max-width: 100%;" in INDEX_DOCUMENT


def test_app_js_uses_raw_single_file_uploads_and_revokes_reference_preview_urls():
    upload_start = APP_JS.index("async function uploadFile")
    upload_end = APP_JS.index("function revokeReferencePreviewUrl", upload_start)
    uploader = APP_JS[upload_start:upload_end]

    assert 'method: "POST"' in uploader
    assert 'headers: {"Content-Type": uploadContentType(file, kind)}' in uploader
    assert "body: file" in uploader
    assert "signal" in uploader
    assert "FormData" not in uploader
    assert "multipart" not in uploader
    assert "base64" not in uploader
    assert 'uploadFile("/api/inputs/reference", file, "reference", {signal: controller.signal})' in APP_JS
    assert 'uploadFile("/api/loras/upload", file, "lora")' in APP_JS
    assert 'return "application/octet-stream"' in APP_JS
    assert 'jpg: "image/jpeg"' in APP_JS
    assert "files.length !== 1" in APP_JS
    assert "URL.createObjectURL(file)" in APP_JS
    assert "URL.revokeObjectURL(referencePreviewUrl)" in APP_JS
    assert 'window.addEventListener("beforeunload", revokeReferencePreviewUrl)' in APP_JS
    assert "setSelectValue(targetSelect, payload.relative_path)" in APP_JS


def test_app_js_serializes_reference_state_and_preflights_lora_capacity():
    reference_start = APP_JS.index("async function uploadReferenceFile")
    reference_end = APP_JS.index("function reserveLoraUploadRow", reference_start)
    reference_uploader = APP_JS[reference_start:reference_end]
    lora_start = APP_JS.index("async function uploadLoraFile")
    lora_end = APP_JS.index("function setupSingleFileDropZone", lora_start)
    lora_uploader = APP_JS[lora_start:lora_end]

    assert "cancelPendingReferenceUpload()" in reference_uploader
    assert "const revision = ++referenceUploadRevision" in reference_uploader
    assert "const controller = new AbortController()" in reference_uploader
    assert "revision !== referenceUploadRevision" in reference_uploader
    assert "setManagedReferencePath(\"\")" in reference_uploader
    assert "referenceFileInput.value = \"\"" in APP_JS
    assert "activeUploadCount" in APP_JS
    assert "uploadsAreIdle({report: true})" in APP_JS
    assert lora_uploader.index("const targetRow = reserveLoraUploadRow()") < lora_uploader.index(
        'uploadFile("/api/loras/upload"'
    )
    assert 'targetRow.dataset.uploadReserved = "true"' in lora_uploader
    assert "targetSelect.disabled = true" in lora_uploader
    assert "targetRemove.disabled = true" in lora_uploader
    assert "addLoraButton.disabled = true" in lora_uploader
    assert 'row.dataset.uploadReserved === "true"' in APP_JS
    assert "addLoraButton.disabled = loraUploadInFlight ||" in APP_JS
    assert "if (loraUploadInFlight) {" in APP_JS
    assert "await loadStatus()" not in lora_uploader
    assert 'fetch("/api/loras", {cache: "no-store"})' in lora_uploader
    assert "setSelectValue(targetSelect, payload.relative_path)" in lora_uploader
    assert 'zone.addEventListener("keydown"' not in APP_JS


def test_index_html_loads_history_panel():
    assert '<script id="anima-defaults" type="application/json">' in INDEX_DOCUMENT
    assert '<script src="/app.js"></script>' in INDEX_DOCUMENT
    assert "const animaDefaults" not in INDEX_DOCUMENT
    assert 'id="status-panel"' in INDEX_HTML
    assert 'id="readiness-panel"' in INDEX_HTML
    assert 'id="update-panel"' in INDEX_HTML
    assert 'id="check-update"' in INDEX_HTML
    assert 'id="update-link"' in INDEX_HTML
    assert 'id="generation-stages"' in INDEX_HTML
    assert 'aria-label="현재 결과"' in INDEX_HTML
    assert 'id="result-title"' in INDEX_HTML
    assert 'id="result-status"' in INDEX_HTML
    assert 'id="result-summary"' in INDEX_HTML
    assert 'id="compare-toolbar"' in INDEX_HTML
    assert 'id="toggle-compare"' in INDEX_HTML
    assert 'id="compare-grid"' in INDEX_HTML
    assert 'id="output-link"' in INDEX_HTML
    assert "상세 생성 정보" in INDEX_HTML
    assert 'id="starting-square"' in INDEX_HTML
    assert 'id="starting-portrait-2x3"' in INDEX_HTML
    assert 'id="starting-portrait-3x4"' in INDEX_HTML
    assert 'id="orientation-portrait"' in INDEX_HTML
    assert 'id="orientation-landscape"' in INDEX_HTML
    assert 'id="generate-button" class="primary-action" type="submit"' in INDEX_HTML
    assert 'aria-live="polite"' in INDEX_HTML
    assert 'id="lora-import-form"' in INDEX_HTML
    assert 'id="generate-form"></form>' in INDEX_HTML
    assert 'class="app-shell"' in INDEX_HTML
    assert 'class="control-frame"' in INDEX_HTML
    assert 'class="workspace-frame"' in INDEX_HTML
    assert 'class="history-frame"' in INDEX_HTML
    assert "grid-template-columns: minmax(280px, 320px) minmax(0, 1fr) minmax(280px, 340px)" in INDEX_HTML
    assert "padding: 9px 11px" in INDEX_HTML
    assert ".control-frame button" in INDEX_HTML
    assert "padding: 5px 7px" in INDEX_HTML
    assert 'id="top-status-strip"' not in INDEX_HTML
    assert 'id="side-status-panel"' in INDEX_HTML
    assert 'class="side-status-panel"' in INDEX_HTML
    assert '<summary>런타임 상태</summary>' in INDEX_HTML
    assert 'id="control-groups"' in INDEX_HTML
    assert 'class="control-group"' in INDEX_HTML
    assert 'form="generate-form"' in INDEX_HTML
    for group_key in (
        "prompt-generate",
        "model-style",
        "image-settings",
        "enhance",
        "settings",
    ):
        assert f'data-control-group="{group_key}"' in INDEX_HTML
    assert 'data-control-group="prompt-tools"' not in INDEX_HTML
    assert 'class="prompt-tools-block"' in INDEX_HTML
    assert ".prompt-tools-block .row" in INDEX_HTML
    assert 'id="llm-refine-prompt"' in INDEX_HTML
    assert 'id="llm-refine-priority"' in INDEX_HTML
    assert '<option value="tag" selected>태그 우선</option>' in INDEX_HTML
    assert '<option value="natural">자연어 우선</option>' in INDEX_HTML
    assert 'id="llm-prompt-status"' in INDEX_HTML
    assert 'fetch("/api/llm/generate"' in INDEX_HTML
    assert "refinePromptWithLlm" in INDEX_HTML
    assert "grid-template-columns: minmax(0, 1fr) 64px" in INDEX_HTML
    assert "anima.sidebar.order.v1" not in INDEX_HTML
    assert "function applySidebarOrder" not in INDEX_HTML
    assert "function setupSidebarReorder" not in INDEX_HTML
    assert (
        f'id="width" name="width" type="number" min="8" max="{requests_module.MAX_GENERATION_DIMENSION}" '
        'step="8" value="832"'
    ) in INDEX_HTML
    assert (
        f'id="height" name="height" type="number" min="8" max="{requests_module.MAX_GENERATION_DIMENSION}" '
        'step="8" value="1216"'
    ) in INDEX_HTML
    assert (
        f'id="steps" name="steps" type="number" min="1" max="{requests_module.MAX_SAMPLING_STEPS}" '
        'value="20"'
    ) in INDEX_HTML
    assert (
        f'id="cfg" name="cfg" type="number" min="0" max="{requests_module.MAX_CFG}" '
        'step="0.1" value="3.5"'
    ) in INDEX_HTML
    assert (
        f'id="prompt" name="prompt" maxlength="{requests_module.MAX_PROMPT_CHARACTERS}"'
    ) in INDEX_HTML
    assert (
        f'id="negative" name="negative_prompt" maxlength="{requests_module.MAX_PROMPT_CHARACTERS}"'
    ) in INDEX_HTML
    assert 'id="sampler" name="sampler"' in INDEX_HTML
    assert '<option value="euler_ancestral_cfg_pp" selected>Euler Ancestral CFG++</option>' in INDEX_HTML
    assert 'id="scheduler" name="scheduler"' in INDEX_HTML
    assert '<option value="sgm_uniform" selected>SGM Uniform</option>' in INDEX_HTML
    assert 'id="checkpoint-select" name="checkpoint"' in INDEX_HTML
    assert '<option value="">불러오는 중...</option>' in INDEX_HTML
    assert "이미지 설정" in INDEX_HTML
    assert "와일드카드와 프리셋" in INDEX_HTML
    assert "모델과 스타일" in INDEX_HTML
    assert "<summary>참조 이미지와 업스케일</summary>" in INDEX_HTML
    assert "<summary>페이스 디테일러</summary>" in INDEX_HTML
    assert 'id="reference-image-section"' in INDEX_HTML
    assert 'id="face-detailer-section"' in INDEX_HTML
    assert 'const referenceImageSection = document.getElementById("reference-image-section")' in INDEX_HTML
    assert "referenceImageSection.open = Boolean" in INDEX_HTML
    assert "faceDetailerSection.open = Boolean" in INDEX_HTML
    assert "<h2>저장된 설정</h2>" in INDEX_HTML
    assert "<h2>LoRA 가져오기</h2>" in INDEX_HTML
    assert "시작 설정" in INDEX_HTML
    assert "1024x1024" in INDEX_HTML
    assert "832x1216" in INDEX_HTML
    assert "896x1152" in INDEX_HTML
    assert "세로" in INDEX_HTML
    assert "가로" in INDEX_HTML
    assert "LoRA 스택" in INDEX_HTML
    assert "LoRA 추가" in INDEX_HTML
    assert "참조 이미지 선택" in INDEX_HTML
    assert "이미지 디노이즈" in INDEX_HTML
    assert "업스케일 사용" in INDEX_HTML
    assert "타일 업스케일" in INDEX_HTML
    assert "페이스 디테일러 사용" in INDEX_HTML
    assert "설정 저장" in INDEX_HTML
    assert "설정 불러오기" in INDEX_HTML
    assert "설정 내보내기" in INDEX_HTML
    assert "설정 가져오기" in INDEX_HTML
    assert 'id="preset-import-file"' in INDEX_HTML
    assert "앱으로 LoRA 업로드" in INDEX_HTML
    assert "이 결과 설정 불러오기" in INDEX_HTML
    assert "단계 비교" in INDEX_HTML
    assert "primary-action" in INDEX_HTML
    assert "request.width || animaDefaults.width" in INDEX_HTML
    assert "request.height || animaDefaults.height" in INDEX_HTML
    assert "request.steps || animaDefaults.steps" in INDEX_HTML
    assert "request.cfg ?? animaDefaults.cfg" in INDEX_HTML
    assert "form.elements.sampler.value = request.sampler || animaDefaults.sampler" in INDEX_HTML
    assert "form.elements.scheduler.value = request.scheduler || animaDefaults.scheduler" in INDEX_HTML
    assert "setSelectValue(checkpointSelect, request.checkpoint || animaDefaults.checkpoint)" in INDEX_HTML
    assert "const startingSizePresets = {" in INDEX_HTML
    assert "square: {width: 1024, height: 1024}" in INDEX_HTML
    assert "portrait_2x3: {width: 832, height: 1216}" in INDEX_HTML
    assert "portrait_3x4: {width: 896, height: 1152}" in INDEX_HTML
    assert "function applyStartingSizePreset" in INDEX_HTML
    assert "function applyStartingOrientation" in INDEX_HTML
    assert "syncStartingPointButtons" in INDEX_HTML
    assert "startingSizeButtons.forEach" in INDEX_HTML
    assert "orientationButtons.forEach" in INDEX_HTML
    assert 'id="i2i-image"' in INDEX_HTML
    assert 'id="i2i-denoise"' in INDEX_HTML
    assert 'id="memory-profile"' in INDEX_HTML
    assert 'id="low-vram-highres-preset"' in INDEX_HTML
    assert "function applyLowVramHighresPreset" in INDEX_HTML
    assert 'form.elements.memory_profile.value = "low_vram_highres"' in INDEX_HTML

    assert "form.elements.upscale_steps.value = 10" in INDEX_HTML
    assert 'id="upscale-enabled"' in INDEX_HTML
    assert 'id="upscale-scale"' in INDEX_HTML
    assert 'id="upscale-steps"' in INDEX_HTML
    assert 'id="upscale-denoise"' in INDEX_HTML
    assert 'id="upscale-method"' in INDEX_HTML
    assert 'id="upscale-tiled"' in INDEX_HTML
    assert 'id="upscale-tile-size"' in INDEX_HTML
    assert (
        f'id="upscale-tile-size" name="upscale_tile_size" type="number" min="{requests_module.MIN_TILE_SIZE}" '
        f'max="{requests_module.MAX_TILE_SIZE}" value="128"'
    ) in INDEX_HTML
    assert 'id="upscale-overlap"' in INDEX_HTML
    assert 'id="vae-decode-mode"' in INDEX_HTML
    assert 'id="vae-tile-size"' in INDEX_HTML
    assert (
        f'id="vae-tile-size" name="vae_tile_size" type="number" min="{requests_module.MIN_TILE_SIZE}" '
        f'max="{requests_module.MAX_TILE_SIZE}" value="128"'
    ) in INDEX_HTML
    assert 'id="vae-overlap"' in INDEX_HTML
    assert 'id="face-detailer-enabled"' in INDEX_HTML
    assert 'id="face-detector"' in INDEX_HTML
    assert 'id="face-mask-backend"' in INDEX_HTML
    assert 'id="face-sam3-face-eyes"' in INDEX_HTML
    assert 'id="face-sam3-hands"' in INDEX_HTML
    assert 'id="hand-denoise"' in INDEX_HTML
    assert 'id="face-threshold"' in INDEX_HTML
    assert 'id="face-steps"' in INDEX_HTML
    assert 'id="face-denoise"' in INDEX_HTML
    assert 'id="face-crop-scale"' in INDEX_HTML
    assert 'id="face-padding"' in INDEX_HTML
    assert 'id="face-feather"' in INDEX_HTML
    assert 'id="face-exclude-forehead"' in INDEX_HTML
    assert 'id="lora-list"' in INDEX_HTML
    assert 'id="add-lora"' in INDEX_HTML
    assert "const checkpointSelect = document.getElementById(\"checkpoint-select\")" in INDEX_HTML
    assert 'id="wildcard-mode"' in INDEX_HTML
    assert '<option value="random" selected>랜덤</option>' in INDEX_HTML
    assert '<option value="off">Off</option>' not in INDEX_HTML
    assert 'id="wildcard-select"' in INDEX_HTML
    assert 'id="insert-wildcard"' in INDEX_HTML
    assert 'id="preset-wildcard-select"' in INDEX_HTML
    assert 'id="insert-preset-wildcard"' in INDEX_HTML
    assert 'id="preview-wildcards"' in INDEX_HTML
    assert 'id="wildcard-preview"' in INDEX_HTML
    assert "const loras = selectedLoras();" in INDEX_HTML
    assert "data.loras = loras;" in INDEX_HTML
    assert "data.checkpoint = data.checkpoint || animaDefaults.checkpoint" in INDEX_HTML
    assert 'name="wildcard_mode"' in INDEX_HTML
    assert 'fetch("/api/wildcards")' in INDEX_HTML
    assert 'fetch("/api/wildcards/preview"' in INDEX_HTML
    assert 'id="autocomplete-menu"' in INDEX_HTML
    assert 'fetch(`/api/autocomplete?q=${encodeURIComponent(fragment.query)}&limit=24`)' in INDEX_HTML
    assert "function setupAutocomplete" in INDEX_HTML
    assert 'before.lastIndexOf("\\n")' in INDEX_HTML
    assert '\\"cleaned_prompt\\"' in INDEX_HTML
    assert '.split(/([,\\n])/' in INDEX_HTML
    assert 'chunk === "," || chunk === "\\n"' in INDEX_HTML
    assert "autocompleteTargets().forEach" in INDEX_HTML
    assert "insertWildcard" in INDEX_HTML
    assert "insertPresetWildcard" in INDEX_HTML
    assert "previewWildcardsButton.addEventListener" in INDEX_HTML
    assert "renderWildcardPreview" in INDEX_HTML
    assert 'lines.join("\\n")' in INDEX_HTML
    assert "payload.presets || []" in INDEX_HTML
    assert "formatWildcardInsertion" in INDEX_HTML
    assert 'return `${prefix}${token}${suffix}`;' in INDEX_HTML
    assert "data.i2i = {" in INDEX_HTML
    assert "data.upscale = {" in INDEX_HTML
    assert "steps: Number(data.upscale_steps || 10)" in INDEX_HTML
    assert "steps: Number(data.face_steps || 10)" in INDEX_HTML
    assert "denoise: Number(data.upscale_denoise || 0.35)" in INDEX_HTML
    assert "method: data.upscale_method || \"bicubic\"" in INDEX_HTML
    assert "data.vae_decode = {" in INDEX_HTML
    assert "data.face_detailer = {" in INDEX_HTML
    assert "mask_backend: data.face_mask_backend || \"sam_b\"" in INDEX_HTML
    assert "sam3_face_eyes: Boolean(data.face_sam3_face_eyes)" in INDEX_HTML
    assert "sam3_hands: Boolean(data.face_sam3_hands)" in INDEX_HTML
    assert "hand_denoise: Number(data.hand_denoise || 0.35)" in INDEX_HTML
    assert '{key: "face_eye_detailer", label: tr("얼굴 + 눈 보정")' in INDEX_HTML
    assert '{key: "hand_detailer", label: tr("손 보정")' in INDEX_HTML
    assert "threshold: Number(data.face_threshold || 0.5)" in INDEX_HTML
    assert "denoise: Number(data.face_denoise || 0.28)" in INDEX_HTML
    assert "exclude_forehead_ratio: Number(data.face_exclude_forehead || 0)" in INDEX_HTML
    assert 'uploadFile("/api/loras/upload", file, "lora")' in INDEX_HTML
    assert 'fetch("/api/health")' in INDEX_HTML
    assert 'fetch(`/api/readiness?checkpoint=${encodeURIComponent(checkpoint)}`' in INDEX_HTML
    assert 'fetch("/api/version")' in INDEX_HTML
    assert 'fetch("/api/update-check")' in INDEX_HTML
    assert "checkUpdateButton.addEventListener" in INDEX_HTML
    assert 'fetch("/api/models/prepare"' in INDEX_HTML
    assert "function renderReadiness" in INDEX_HTML
    assert "prepareModelProfile" in INDEX_HTML
    assert "data-profile" in INDEX_HTML
    assert "Copy Detectors" not in INDEX_HTML
    assert "로컬에서 복사" in INDEX_HTML
    assert 'return profile.prepare_source === "local" ? tr("로컬에서 복사") : tr("다운로드");' in INDEX_HTML
    assert 'fetch("/api/loras")' in INDEX_HTML
    assert 'fetch("/api/checkpoints")' in INDEX_HTML
    assert "function renderCheckpointOptions" in INDEX_HTML
    assert 'statusCard(tr("체크포인트")' in INDEX_HTML
    assert ".status-item" in INDEX_HTML
    assert "overflow-wrap: anywhere" in INDEX_HTML
    assert "showOutputPreview(payload.output_url)" in INDEX_HTML
    assert "outputLink.href = url" in INDEX_HTML
    assert "outputLink.hidden = false" in INDEX_HTML
    assert 'id="sam3-prompt"' in INDEX_HTML
    assert 'id="sam3-segment"' in INDEX_HTML
    assert 'id="sam3-compare"' in INDEX_HTML
    assert 'id="sam3-presets"' in INDEX_HTML
    assert 'id="sam3-results"' in INDEX_HTML
    assert 'id="mask-dilation"' in INDEX_HTML
    assert 'id="mask-feather"' in INDEX_HTML
    assert 'id="mask-adjust"' in INDEX_HTML
    assert 'id="inpaint-method"' in INDEX_HTML
    assert 'id="masked-inpaint"' in INDEX_HTML
    assert 'fetch("/api/sam3/segment"' in INDEX_HTML
    assert 'fetch("/api/sam3/compare"' in INDEX_HTML
    assert 'fetch("/api/masks/adjust"' in INDEX_HTML
    assert 'fetch("/api/inpaint/masked"' in INDEX_HTML
    assert "checkpoint: checkpointSelect.value" in INDEX_HTML
    assert "loras: selectedLoras()" in INDEX_HTML
    assert "sam3ClothingComparePrompts" in INDEX_HTML
    assert "renderSam3CompareResults" in INDEX_HTML
    assert "#output-link[hidden]" in INDEX_HTML
    assert "function renderResultSummary" in INDEX_HTML
    assert "function setResultPayload" in INDEX_HTML
    assert "function setResultMessage" in INDEX_HTML
    assert 'summaryItem(tr("상태"), resultMode(payload))' in INDEX_HTML
    assert "summaryItem(\"Output\", payload.output_url || payload.output_path || \"manifest only\")" not in INDEX_HTML
    assert "function variantEntries" in INDEX_HTML
    assert "variants.face_detailer && !variants.face_eye_detailer && !variants.hand_detailer" in INDEX_HTML
    assert "function renderCompareGrid" in INDEX_HTML
    assert "function syncCompareControls" in INDEX_HTML
    assert "toggleCompareButton.hidden" in INDEX_HTML
    assert "toggleCompareButton.addEventListener" in INDEX_HTML
    assert "function clearOutputPreview()" in INDEX_HTML
    assert 'preview.removeAttribute("src")' in INDEX_HTML
    assert 'outputLink.removeAttribute("href")' in INDEX_HTML
    assert "clearOutputPreview();" in INDEX_HTML
    assert "function startSingleGeneration" in INDEX_HTML
    assert "await startSingleGeneration();" in INDEX_HTML
    assert "setResultPayload(payload)" in INDEX_HTML
    assert "currentManifest = null" in INDEX_HTML
    assert "latest.result.manifest_path.split" in INDEX_HTML
    assert "await openManifest(manifestName)" in INDEX_HTML
    assert 'id="history"' in INDEX_HTML
    assert 'id="history-count"' in INDEX_HTML
    assert 'id="history-load-more"' in INDEX_HTML
    assert 'data-history-filter="all"' in INDEX_HTML
    assert 'data-history-filter="images"' in INDEX_HTML
    assert 'data-history-filter="dry-run"' in INDEX_HTML
    assert "function historyType" in INDEX_HTML
    assert "function renderHistory" in INDEX_HTML
    assert "history-thumb" in INDEX_HTML
    assert "history-empty" in INDEX_HTML
    assert "historyFilters.forEach" in INDEX_HTML
    assert 'const query = new URLSearchParams({limit: "8"})' in INDEX_HTML
    assert 'fetch("/api/manifests/" + encodeURIComponent(name))' in INDEX_HTML
    assert "function deleteHistoryItem" in INDEX_HTML
    assert "function exportManifest" in INDEX_HTML
    assert 'fetch("/api/manifests/" + encodeURIComponent(name), {method: "DELETE"})' in INDEX_HTML
    assert 'download = name' in INDEX_HTML
    assert "history-actions" in INDEX_HTML
    assert "history-action danger" in INDEX_HTML
    assert "openManifest" in INDEX_HTML
    assert 'card.addEventListener("click", () => openManifest(manifestName, {showCompare: false}))' in INDEX_HTML
    assert 'id="preset-select"' in INDEX_HTML
    assert 'fetch("/api/presets")' in INDEX_HTML
    assert 'fetch("/api/presets/export")' in INDEX_HTML
    assert 'fetch("/api/presets/import"' in INDEX_HTML
    assert "function exportPresets" in INDEX_HTML
    assert "function importPresetsFromFile" in INDEX_HTML
    assert "savePreset" in INDEX_HTML
    assert "applyPreset" in INDEX_HTML
    assert 'id="apply-manifest"' in INDEX_HTML
    assert "applyManifest" in INDEX_HTML
    assert "wildcardInfo.original_prompt" in INDEX_HTML
    assert "setLoraRows(request.loras || [])" in INDEX_HTML


def test_history_load_more_appends_cursor_page():
    start = APP_JS.index("async function loadHistory")
    end = APP_JS.index("async function openManifest", start)
    loader = APP_JS[start:end]

    assert "historyNextCursor" in loader
    assert 'query.set("cursor", historyNextCursor)' in loader
    assert "historyItems = append ? [...historyItems, ...items] : items;" in loader
    assert "historyLoadMore.hidden = !historyHasMore;" in loader
    assert 'historyLoadMore.addEventListener("click"' in APP_JS


def test_history_ui_searches_server_and_uses_accessible_lazy_thumbnails():
    loader_start = APP_JS.index("async function loadHistory")
    loader_end = APP_JS.index("async function openManifest", loader_start)
    loader = APP_JS[loader_start:loader_end]
    card_start = APP_JS.index("function historyCard")
    card_end = APP_JS.index("function renderHistory", card_start)
    card = APP_JS[card_start:card_end]

    assert 'id="history-search-form" class="history-search" role="search"' in INDEX_DOCUMENT
    assert (
        f'id="history-search" type="search" maxlength="{server_module.MAX_HISTORY_QUERY_CHARACTERS}"'
        in INDEX_DOCUMENT
    )
    assert 'id="history-count" aria-live="polite"' in INDEX_DOCUMENT
    assert 'id="history-storage" class="history-storage" aria-live="polite"' in INDEX_DOCUMENT
    assert 'data-history-filter="all" aria-pressed="true"' in INDEX_DOCUMENT
    assert 'data-history-filter="images" aria-pressed="false"' in INDEX_DOCUMENT
    assert 'query.set("q",' in loader
    assert "rawQuery.slice(0, historySearchInput.maxLength)" in loader
    assert ".slice(0, 256)" not in loader
    assert 'query.set("type", historyFilter)' in loader
    assert "historyRequestRevision" in loader
    assert "requestRevision !== historyRequestRevision" in loader
    assert "historyTotalCount" in loader
    assert "item.manifest_name" in card
    assert "item.thumbnail_url" in card
    assert 'image.loading = "lazy"' in card
    assert 'image.decoding = "async"' in card
    assert 'historyThumbnailPlaceholder(tr("미리보기 없음"))' in card
    assert card.index('image.addEventListener("error"') < card.index("image.src = item.thumbnail_url")
    assert 'button.setAttribute("aria-pressed", String(active))' in APP_JS
    assert "renderHistoryStorage(health.outputs)" in APP_JS
    assert "currentManifest?.manifest_name" in APP_JS


def test_history_search_debounce_and_filter_reset_server_pagination():
    schedule_start = APP_JS.index("function scheduleHistorySearch")
    schedule_end = APP_JS.index("async function openManifest", schedule_start)
    schedule = APP_JS[schedule_start:schedule_end]
    events_start = APP_JS.index("historyFilters.forEach((button) => {")
    events_end = APP_JS.index("readinessPanel.addEventListener", events_start)
    events = APP_JS[events_start:events_end]

    assert "window.clearTimeout(historySearchTimer);" in schedule
    assert "historyRequestRevision += 1;" in schedule
    assert 'historyNextCursor = "";' in schedule
    assert "historyItems = [];" in schedule
    assert "}, 250);" in schedule
    assert "historySearchInput?.addEventListener(\"input\", scheduleHistorySearch);" in events
    assert "historyFilter = nextFilter;" in events
    assert "loadHistory().catch" in events


def test_index_html_keeps_medium_width_history_reachable():
    medium_width_css = INDEX_DOCUMENT.split("@media (max-width: 1180px)", 1)[1].split(
        "@media (max-width: 780px)", 1
    )[0]

    assert "body {" in medium_width_css
    assert "overflow: auto;" in medium_width_css


def test_index_html_hides_sam3_tools_until_an_output_is_selected():
    clear_preview = APP_JS.split("function clearOutputPreview()", 1)[1].split(
        "function showOutputPreview", 1
    )[0]
    show_preview = APP_JS.split("function showOutputPreview(url)", 1)[1].split(
        "function setCurrentMaskFromPayload", 1
    )[0]

    assert '<section class="sam3-tools" id="sam3-tools" hidden>' in INDEX_DOCUMENT
    assert ".sam3-tools[hidden]" in INDEX_DOCUMENT
    assert 'const sam3Tools = document.getElementById("sam3-tools")' in APP_JS
    assert "sam3Tools.hidden = true;" in clear_preview
    assert 'sam3Tools.hidden = providerSelect.value === "novelai" || currentManifest?.provider === "novelai";' in show_preview


def test_masked_inpaint_success_refreshes_history_with_existing_loader():
    start = APP_JS.index("async function runMaskedInpaint")
    end = APP_JS.index("function setSelectValue", start)
    inpaint_handler = APP_JS[start:end]

    assert "loadHistory().catch(() => {});" in inpaint_handler
    assert "loadHistoryStorage().catch(() => {});" in inpaint_handler
    assert "refreshHistory(" not in inpaint_handler


@pytest.mark.parametrize(
    ("function_name", "next_function"),
    [
        ("segmentCurrentImageWithSam3", "renderSam3Presets"),
        ("compareCurrentImageWithSam3", "adjustCurrentMask"),
        ("adjustCurrentMask", "runMaskedInpaint"),
    ],
)
def test_output_creating_tools_refresh_history_storage(function_name, next_function):
    start = APP_JS.index(f"async function {function_name}")
    end = APP_JS.index(f"function {next_function}", start)
    handler = APP_JS[start:end]

    assert "loadHistoryStorage().catch(() => {});" in handler


def test_history_storage_refresh_is_independent_from_readiness():
    storage_start = APP_JS.index("async function loadHistoryStorage")
    status_start = APP_JS.index("async function loadStatus", storage_start)
    storage_loader = APP_JS[storage_start:status_start]
    status_end = APP_JS.index("function historyType", status_start)
    status_loader = APP_JS[status_start:status_end]

    assert 'fetch("/api/health", {cache: "no-store"})' in storage_loader
    assert "renderHistoryStorage(payload.outputs);" in storage_loader
    assert status_loader.index("renderHistoryStorage(health.outputs);") < status_loader.index("await loadReadiness()")


def test_missing_required_file_error_opens_runtime_status_panel():
    start = APP_JS.index("function setResultPayload")
    end = APP_JS.index("function setResultMessage", start)
    result_handler = APP_JS[start:end]

    queue_start = APP_JS.index("function showLatestQueueResult")
    queue_end = APP_JS.index("async function pollServerQueue", queue_start)
    queue_handler = APP_JS[queue_start:queue_end]

    assert 'const sideStatusPanel = document.getElementById("side-status-panel")' in APP_JS
    assert 'payload?.error_code === "models_not_ready"' in result_handler
    assert "sideStatusPanel.open = true;" in result_handler
    assert 'sideStatusPanel.querySelector("summary")?.focus();' in result_handler
    assert "loadStatus().catch(() => {});" in result_handler
    assert 'id="result-summary" class="result-summary" aria-live="polite" aria-atomic="true"' in INDEX_DOCUMENT
    assert "latest.id === lastQueueResultJobId" in queue_handler
    assert "lastQueueResultJobId = latest.id" in queue_handler


def test_mobile_interactions_use_44px_touch_targets():
    mobile_css = INDEX_DOCUMENT.split("@media (max-width: 780px)", 1)[1].split("</style>", 1)[0]

    for selector in (
        "input:not([type=\"checkbox\"]):not([type=\"radio\"]):not([type=\"hidden\"])",
        ".control-frame button",
        ".readiness-panel.compact .readiness-action",
        ".history-action",
        ".toggle-switch",
        ".control-group > summary",
        ".form-section summary",
        ".side-status-panel > summary",
        ".result-json summary",
        "#update-link",
    ):
        assert selector in mobile_css
    assert mobile_css.count("min-height: 44px") >= 4


def test_model_prepare_confirms_and_uses_the_displayed_source():
    render_start = APP_JS.index("function renderReadiness")
    render_end = APP_JS.index("async function prepareModelProfile", render_start)
    readiness_renderer = APP_JS[render_start:render_end]
    prepare_start = render_end
    prepare_end = APP_JS.index("function summaryItem", prepare_start)
    prepare_handler = APP_JS[prepare_start:prepare_end]

    assert 'action.dataset.source = profile.prepare_source || "auto";' in readiness_renderer
    assert "action.dataset.sizeBytes = profile.prepare_size_bytes" in readiness_renderer
    assert "window.confirm" in prepare_handler
    assert 'const source = button.dataset.source || "auto";' in prepare_handler
    assert "body: JSON.stringify({profile, source})" in prepare_handler
    assert 'body: JSON.stringify({profile, source: "auto"})' not in prepare_handler


def test_selected_checkpoint_readiness_controls_generate_and_queue_actions():
    readiness_start = APP_JS.index("async function loadReadiness")
    readiness_end = APP_JS.index("async function loadStatus", readiness_start)
    readiness_loader = APP_JS[readiness_start:readiness_end]
    controls_start = APP_JS.index("function syncGenerationControls")
    controls_end = APP_JS.index("function renderReadiness", controls_start)
    controls = APP_JS[controls_start:controls_end]

    assert "/api/readiness?checkpoint=" in readiness_loader
    assert "encodeURIComponent(checkpoint)" in readiness_loader
    assert "generationReadiness && !generationReadiness.ready" in controls
    assert "generateButton.disabled = queueRunning || blocked || uploadBlocked;" in controls
    assert "startQueueButton.disabled = queueRunning || blocked || uploadBlocked;" in controls
    assert "파일 업로드가 끝날 때까지 기다려 주세요." in controls
    assert 'checkpointSelect.addEventListener("change"' in APP_JS
    assert "generationReadinessCard(payload.generation)" in APP_JS
    assert 'required: tr("필수"), recommended: tr("권장"), optional: tr("선택")' in APP_JS


def test_result_summary_surfaces_generation_warnings():
    start = APP_JS.index("function renderResultSummary")
    end = APP_JS.index("function variantEntries", start)
    renderer = APP_JS[start:end]

    assert "payload.warnings" in renderer
    assert 'summaryItem(tr("경고")' in renderer
    assert "warnings.length" in renderer


def test_autocomplete_preserves_textarea_role_and_exposes_single_line_combobox_state():
    setup_start = APP_JS.index("function setupAutocomplete")
    setup_end = APP_JS.index("function renderWildcardPreview", setup_start)
    setup = APP_JS[setup_start:setup_end]
    render_start = APP_JS.index("function renderAutocomplete")
    render_end = APP_JS.index("async function requestAutocomplete", render_start)
    render = APP_JS[render_start:render_end]

    assert 'if (input.tagName === "INPUT")' in setup
    assert 'input.setAttribute("role", "combobox")' in setup
    assert 'input.setAttribute("aria-controls", autocompleteMenu.id)' in setup
    assert 'input.setAttribute("aria-autocomplete", "list")' in setup
    assert "setAutocompleteExpanded(input, true)" in render
    assert 'role="combobox"' not in INDEX_DOCUMENT.split('<textarea id="prompt"', 1)[1].split("</textarea>", 1)[0]
    assert 'button.setAttribute("aria-selected"' in APP_JS
    assert 'setAttribute("aria-activedescendant"' in APP_JS
    assert 'autocompleteActiveInput !== input' in APP_JS
    assert "setAutocompleteExpanded(autocompleteActiveInput, false)" in APP_JS
    assert "autocompleteActiveInput = null" in APP_JS
    assert 'id="autocomplete-status"' in INDEX_DOCUMENT
    assert 'aria-label="자동완성 제안"' in INDEX_DOCUMENT


def test_autocomplete_fragment_replaces_the_whole_token_at_the_cursor():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is not installed")
    start = APP_JS.index("function currentAutocompleteFragment")
    end = APP_JS.index("function hideAutocomplete", start)
    function_source = APP_JS[start:end]
    script = (
        function_source
        + '\nconst input = {value: "portrait, long_hair, blue eyes", selectionStart: 14};'
        + "\nconsole.log(JSON.stringify(currentAutocompleteFragment(input)));"
    )

    completed = subprocess.run([node, "-"], input=script, text=True, capture_output=True, check=True)

    assert json.loads(completed.stdout) == {"start": 10, "end": 19, "query": "long"}


def test_autocomplete_rejects_stale_responses_and_stays_closed_after_selection():
    request_start = APP_JS.index("async function requestAutocomplete")
    request_end = APP_JS.index("function scheduleAutocomplete", request_start)
    request = APP_JS[request_start:request_end]
    schedule_start = request_end
    schedule_end = APP_JS.index("function applyAutocompleteItem", schedule_start)
    schedule = APP_JS[schedule_start:schedule_end]
    apply_start = schedule_end
    apply_end = APP_JS.index("function handleAutocompleteKeydown", apply_start)
    apply_item = APP_JS[apply_start:apply_end]

    assert "let autocompleteRequestRevision = 0;" in APP_JS
    assert "requestRevision !== autocompleteRequestRevision" in request
    assert "requestAutocomplete(input, requestRevision)" in schedule
    assert "const requestRevision = ++autocompleteRequestRevision;" in schedule
    assert "autocompleteReplacement(input.value, item.value, fragment)" in apply_item
    assert "autocompleteRequestRevision += 1;" in APP_JS


def test_autocomplete_replacement_keeps_no_stale_menu_window_and_moves_past_delimiter():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is not installed")
    replacement_start = APP_JS.index("function autocompleteReplacement")
    replacement_end = APP_JS.index("function applyAutocompleteItem", replacement_start)
    replacement_source = APP_JS[replacement_start:replacement_end]
    script = (
        replacement_source
        + '\nconst result = autocompleteReplacement("portrait, long_hair, blue eyes", "long_hair", {start: 10, end: 19});'
        + '\nconst sameFragment = autocompleteFragmentMatches({start: 10, end: 19, query: "long"}, {start: 10, end: 19, query: "long"});'
        + '\nconst movedFragment = autocompleteFragmentMatches({start: 0, end: 8, query: "po"}, {start: 10, end: 19, query: "long"});'
        + "\nconsole.log(JSON.stringify({result, sameFragment, movedFragment}));"
    )
    completed = subprocess.run([node, "-"], input=script, text=True, capture_output=True, check=True)
    outcome = json.loads(completed.stdout)
    schedule_start = APP_JS.index("function scheduleAutocomplete")
    schedule_end = APP_JS.index("function autocompleteReplacement", schedule_start)
    schedule = APP_JS[schedule_start:schedule_end]

    assert outcome["result"] == {"value": "portrait, long_hair, blue eyes", "cursor": 21}
    assert outcome["sameFragment"] is True
    assert outcome["movedFragment"] is False
    assert schedule.index("hideAutocomplete();") < schedule.index("autocompleteActiveInput = input;")
    apply_start = APP_JS.index("function applyAutocompleteItem")
    apply_end = APP_JS.index("function handleAutocompleteKeydown", apply_start)
    assert "autocompleteFragmentMatches(fragment, autocompleteFragment)" in APP_JS[apply_start:apply_end]


def test_autocomplete_keeps_active_option_visible_and_clickable_without_moving_focus():
    index_start = APP_JS.index("function setAutocompleteIndex")
    index_end = APP_JS.index("function renderAutocomplete", index_start)
    indexer = APP_JS[index_start:index_end]
    render_start = index_end
    render_end = APP_JS.index("async function requestAutocomplete", render_start)
    render = APP_JS[render_start:render_end]

    assert 'scrollIntoView({block: "nearest"})' in indexer
    assert "button.tabIndex = -1;" in render
    assert 'button.addEventListener("click"' in render


def test_autocomplete_tab_closes_and_preserves_native_focus_navigation():
    start = APP_JS.index("function handleAutocompleteKeydown")
    end = APP_JS.index("function setupAutocomplete", start)
    handler = APP_JS[start:end]
    tab_branch = handler.split('event.key === "Tab"', 1)[1].split("} else if", 1)[0]

    assert "hideAutocomplete();" in tab_branch
    assert "event.preventDefault();" not in tab_branch
    assert "applyAutocompleteItem();" not in tab_branch


def test_autocomplete_does_not_hijack_ime_composition_enter():
    start = APP_JS.index("function handleAutocompleteKeydown")
    end = APP_JS.index("function setupAutocomplete", start)
    handler = APP_JS[start:end]

    assert "event.isComposing || event.keyCode === 229" in handler
    assert handler.index("event.isComposing") < handler.index("autocompleteMenu.hidden")


def test_accessibility_contract_covers_results_presets_motion_and_selected_states():
    assert 'id="preview" alt="생성 결과 이미지"' in INDEX_DOCUMENT
    assert 'label for="inpaint-seed"' in INDEX_DOCUMENT
    assert 'id="sam3-status" class="sam3-status" role="status" aria-live="polite" aria-atomic="true"' in INDEX_DOCUMENT
    assert '@media (prefers-reduced-motion: reduce)' in INDEX_DOCUMENT
    assert 'window.matchMedia("(prefers-reduced-motion: reduce)").matches' in APP_JS
    assert 'data-size-preset="portrait_2x3" aria-pressed="true"' in INDEX_DOCUMENT
    assert 'data-orientation="portrait" aria-pressed="true"' in INDEX_DOCUMENT
    sync_start = APP_JS.index("function syncStartingPointButtons")
    sync_end = APP_JS.index("function applyManifest", sync_start)
    sync = APP_JS[sync_start:sync_end]
    assert 'button.setAttribute("aria-pressed", String(selected))' in sync
    selection_start = APP_JS.index("function syncStartingPointSelectionFromInputs")
    selection_end = APP_JS.index("function applyStartingSizePreset", selection_start)
    selection = APP_JS[selection_start:selection_end]
    assert 'selectedStartingSize = matchingSize?.[0] || "";' in selection
    assert 'startingOrientation = width > height ? "landscape" : "portrait";' in selection
    assert "syncStartingPointSelectionFromInputs();" in APP_JS
    assert '["width", "height"].forEach' in APP_JS
    assert 'window.AppI18n.setProperty(preview, "alt", () => tr("생성 결과 이미지"))' in APP_JS
    assert 'window.AppI18n.setProperty(preview, "alt", () => tr("선택 영역이 표시된 생성 결과 이미지"))' in APP_JS


def test_lora_controls_preserve_validation_and_keyboard_focus_during_refresh():
    add_start = APP_JS.index("function addLoraRow")
    add_end = APP_JS.index("function loraRowConfigs", add_start)
    add_row = APP_JS[add_start:add_end]
    status_start = APP_JS.index("async function loadStatus")
    status_end = APP_JS.index("function historyType", status_start)
    load_status = APP_JS[status_start:status_end]

    assert 'strength.setAttribute("form", form.id)' in add_row
    assert "select.focus();" in add_row
    assert "focusTarget" in add_row
    assert "setLoraRows(" not in load_status
    assert "renderLoraSelectOptions(select, select.value)" in load_status
    apply_start = APP_JS.index("function applyPreset")
    apply_end = APP_JS.index("function applyStartingSizePreset", apply_start)
    apply_preset = APP_JS[apply_start:apply_end]
    assert "return false;" in apply_preset
    assert "return true;" in apply_preset
    assert "item && applyPreset(item)" in APP_JS


def test_preset_apply_control_tracks_a_real_selection():
    sync_start = APP_JS.index("function syncPresetSelectionControls")
    sync_end = APP_JS.index("async function loadPresets", sync_start)
    sync = APP_JS[sync_start:sync_end]

    assert "applyPresetButton.disabled = !presetSelect.value;" in sync
    assert 'presetSelect.addEventListener("change", syncPresetSelectionControls);' in APP_JS
    assert "presetSelect.value = payload.slug || \"\";\n      syncPresetSelectionControls();" in APP_JS


def test_readiness_and_queue_status_ignore_stale_or_duplicate_updates():
    readiness_start = APP_JS.index("async function loadReadiness")
    readiness_end = APP_JS.index("async function loadHistoryStorage", readiness_start)
    readiness = APP_JS[readiness_start:readiness_end]
    queue_start = APP_JS.index("function setQueueStatus")
    queue_end = APP_JS.index("function setQueueControlsRunning", queue_start)
    queue_status = APP_JS[queue_start:queue_end]

    assert "let readinessRequestRevision = 0;" in APP_JS
    assert "const requestRevision = ++readinessRequestRevision;" in readiness
    assert "requestRevision !== readinessRequestRevision" in readiness
    assert "checkpoint !== checkpointSelect.value" in readiness
    assert readiness.index("requestRevision !== readinessRequestRevision") < readiness.index("if (!response.ok)")
    assert "queueStatus.textContent !== message" in queue_status


def test_preset_controls_report_failures_and_bound_names():
    assert f'id="preset-name" maxlength="{server_module.MAX_PRESET_NAME_CHARACTERS}"' in INDEX_DOCUMENT
    assert 'id="preset-status"' in INDEX_DOCUMENT
    load_start = APP_JS.index("async function loadPresets")
    load_end = APP_JS.index("async function exportPresets", load_start)
    load_presets = APP_JS[load_start:load_end]
    save_start = APP_JS.index('savePresetButton.addEventListener("click"')
    save_end = APP_JS.index('applyPresetButton.addEventListener("click"', save_start)
    save_preset = APP_JS[save_start:save_end]

    assert "if (!response.ok || payload.error)" in load_presets
    assert "if (!response.ok || payload.error)" in save_preset
    assert "setPresetStatus" in save_preset


def test_history_card_keeps_native_actions_as_its_keyboard_path():
    start = APP_JS.index("function historyCard")
    end = APP_JS.index("function renderHistory", start)
    card = APP_JS[start:end]

    assert "card.tabIndex" not in card
    assert 'card.addEventListener("keydown"' not in card
    assert 'window.AppI18n.setText(manifestButton, () => tr("상세"))' in card
    assert 'manifestButton.addEventListener("click"' in card


@pytest.mark.parametrize("script", [APP_JS, NAI_I18N_JS, NAI_ERRORS_JS], ids=["app", "nai-i18n", "nai-errors"])
def test_app_js_has_valid_syntax(script):
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is not installed")

    subprocess.run(
        [node, "--check", "-"],
        input=script,
        text=True,
        capture_output=True,
        check=True,
    )


@pytest.mark.parametrize(
    "needle",
    [
        "Detect contradictions and remove or rewrite the weaker side",
        "full body vs portrait",
        "Priority: ",
        "cleaned_prompt",
        "natural_language_prompt",
        "resolved_conflicts",
        "parseLlmPromptRefinement(completion, prompt, refinePriority)",
        "stripJsonCodeFence",
        "removeNonEnglishPromptParts(prompt)",
        "containsNonEnglishText",
        'status: "llm_prompt_appended"',
    ],
)
def test_index_html_contains_llm_refine_contract(needle):
    assert needle in INDEX_HTML


def test_index_html_renders_binary_options_as_color_toggles():
    assert INDEX_HTML.count('class="toggle-switch"') == 9
    assert "toggle-switch:has(input:checked)" in INDEX_HTML
    assert "background: #a9444f" in INDEX_HTML
    assert "background: #2f9f55" in INDEX_HTML
    assert 'class="toggle-track" aria-hidden="true"' in INDEX_HTML
    assert 'class="toggle-state" aria-hidden="true"' in INDEX_HTML
    assert 'class="check-label"' not in INDEX_HTML
    for field_id in (
        "upscale-enabled",
        "upscale-tiled",
        "face-detailer-enabled",
        "face-sam3-face-eyes",
        "face-sam3-hands",
        "queue-infinite",
    ):
        assert f'<label class="toggle-switch" for="{field_id}">' in INDEX_HTML
        assert f'id="{field_id}"' in INDEX_HTML
        assert 'type="checkbox" value="1"' in INDEX_HTML


def test_index_html_exposes_generation_stage_progress():
    assert "buildGenerationStages" in INDEX_HTML
    assert "startStageProgress" in INDEX_HTML
    assert "finishGenerationStages" in INDEX_HTML
    assert "startProgressPolling" in INDEX_HTML
    assert "pollGenerationProgress" in INDEX_HTML
    assert "stopProgressPolling" in INDEX_HTML
    assert "/api/progress/" in INDEX_HTML
    assert "progress_id" in INDEX_HTML
    assert "renderGenerationStages" in INDEX_HTML
    assert "scheduleGenerationStageHide" in INDEX_HTML
    assert "stageVisibleStateLabels" in INDEX_HTML
    assert 'pending: ""' in INDEX_HTML
    assert 'completed: ""' in INDEX_HTML
    assert 'skipped: ""' in INDEX_HTML
    assert 'window.AppI18n.setText(status, () => stageVisibleStateLabels[state] ?? stageStateLabels[state] ?? state)' in INDEX_HTML
    assert 'window.AppI18n.setAttribute(row, "aria-label", () => `${item.label}: ${stageStateLabels[state] || state}`)' in INDEX_HTML
    assert "기본 렌더" in INDEX_HTML
    assert "고해상도 / 업스케일" in INDEX_HTML
    assert "VAE 디코드" in INDEX_HTML
    assert "페이스 디테일러" in INDEX_HTML
    assert "position: sticky" in INDEX_HTML
    assert "generationStages.scrollIntoView" in INDEX_HTML
    assert "data-stage-key" in INDEX_HTML
    assert "payload.stages || {}" in INDEX_HTML
    assert 'message ? tr`실패: ${message}` : tr("실패")' in INDEX_HTML
    assert 'finalState === "cancelled"' in INDEX_HTML
    assert 'message || tr("취소됨")' in INDEX_HTML


def test_index_html_exposes_auto_queue_controls():
    assert 'id="auto-queue-panel"' in INDEX_HTML
    assert 'id="queue-count"' in INDEX_HTML
    assert 'name="queue_count"' in INDEX_HTML
    assert 'id="queue-infinite"' in INDEX_HTML
    assert 'name="queue_infinite"' in INDEX_HTML
    assert 'id="queue-seed-mode"' in INDEX_HTML
    assert '<option value="fixed">고정</option>' in INDEX_HTML
    assert '<option value="increment" selected>증가</option>' in INDEX_HTML
    assert '<option value="random">랜덤</option>' in INDEX_HTML
    assert 'id="queue-delay"' in INDEX_HTML
    assert 'id="start-queue"' in INDEX_HTML
    assert 'id="stop-queue"' in INDEX_HTML
    assert 'id="queue-status"' in INDEX_HTML
    assert "const autoQueuePanel = document.getElementById(\"auto-queue-panel\")" in INDEX_HTML
    assert "const queueCountInput = document.getElementById(\"queue-count\")" in INDEX_HTML
    assert "const queueInfiniteInput = document.getElementById(\"queue-infinite\")" in INDEX_HTML
    assert "const queueSeedMode = document.getElementById(\"queue-seed-mode\")" in INDEX_HTML
    assert "const queueDelayInput = document.getElementById(\"queue-delay\")" in INDEX_HTML
    assert "function queueIsInfinite" in INDEX_HTML
    assert "let serverQueuePollTimer = null" in INDEX_HTML
    assert "async function enqueueServerJobs" in INDEX_HTML
    assert 'fetch("/api/jobs", {' in INDEX_HTML
    assert 'fetch("/api/jobs", {cache: "no-store"})' in INDEX_HTML
    assert 'fetch("/api/jobs/" + encodeURIComponent(jobId) + "/cancel"' in INDEX_HTML
    assert "function renderServerQueueStatus" in INDEX_HTML
    assert "async function startAutoQueue" in INDEX_HTML
    assert "function stopAutoQueue" in INDEX_HTML
    assert "queueSeedMode.value" in INDEX_HTML


def test_app_restores_live_server_queue_on_startup():
    start = APP_JS.index("async function restoreServerQueue")
    end = APP_JS.index("async function enqueueServerJobs", start)
    restore_handler = APP_JS[start:end]

    assert 'fetch("/api/jobs", {cache: "no-store"})' in restore_handler
    assert '["running", "waiting", "queued"].includes(item.status)' in restore_handler
    assert "activeQueueBatchId = activeJob.batch_id || \"\";" in restore_handler
    assert "setQueueControlsRunning(true);" in restore_handler
    assert "renderServerQueueStatus(payload);" in restore_handler
    assert "startServerQueuePolling();" in restore_handler
    assert 'restoreServerQueue().catch((error) => setQueueStatus(tr`큐 상태 복구 실패: ${String(error)}`));' in APP_JS


def test_single_generation_uses_cancelable_server_queue():
    start = APP_JS.index("async function startSingleGeneration")
    end = APP_JS.index("async function startAutoQueue", start)
    single_handler = APP_JS[start:end]
    submit_start = APP_JS.index('form.addEventListener("submit"')
    submit_end = APP_JS.index("savePresetButton.addEventListener", submit_start)
    submit_handler = APP_JS[submit_start:submit_end]

    assert 'enqueueServerJobs(baseData, 1, false, "fixed", 0)' in single_handler
    assert "startServerQueuePolling();" in single_handler
    assert "await startSingleGeneration();" in submit_handler
    assert 'fetch("/api/generate"' not in APP_JS


def test_stop_queue_recovers_after_cancel_request_failure():
    cancel_start = APP_JS.index("async function cancelServerJob")
    cancel_end = APP_JS.index("async function startSingleGeneration", cancel_start)
    cancel_handler = APP_JS[cancel_start:cancel_end]
    stop_start = APP_JS.index("async function stopAutoQueue")
    stop_end = APP_JS.index('form.addEventListener("submit"', stop_start)
    stop_handler = APP_JS[stop_start:stop_end]

    assert "if (!response.ok || payload.error)" in cancel_handler
    assert 'throw new Error(payload.error || tr("작업 취소 실패"));' in cancel_handler
    assert "stopQueueButton.disabled = false;" in stop_handler
    assert stop_handler.index("stopQueueButton.disabled = false;") > stop_handler.index("} catch (error) {")


def test_index_html_exposes_multi_lora_controls():
    assert 'id="lora-list"' in INDEX_HTML
    assert 'id="add-lora"' in INDEX_HTML
    assert "let loraCatalog = []" in INDEX_HTML
    assert "function addLoraRow" in INDEX_HTML
    assert "function selectedLoras" in INDEX_HTML
    assert "function setLoraRows" in INDEX_HTML
    assert "loraCatalog = loras.items || []" in INDEX_HTML
    assert 'addLoraButton.addEventListener("click", () => addLoraRow({}, {focus: true}))' in INDEX_HTML

import json
import threading
import urllib.error
import urllib.request
from pathlib import Path

from PIL import Image

from anima_app.assets import FACE_DETAILER_DETECTOR_ASSET_PROFILE
from anima_app.config import AppPaths
from anima_app.runtime.pipeline import T2IRenderOutput
from anima_app.server import INDEX_HTML, create_http_server, handle_generate, handle_wildcard_preview, request_from_payload


def _paths(tmp_path: Path) -> AppPaths:
    return AppPaths(
        project_root=tmp_path / "app",
        development_model_source=tmp_path / "source",
        face_detailer_detector_source=tmp_path / "detectors",
    )


def _write_face_detector_sources(paths: AppPaths) -> None:
    for relative_path in FACE_DETAILER_DETECTOR_ASSET_PROFILE.files:
        source = paths.face_detailer_detector_source / relative_path.name
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes((relative_path.name + "-detector").encode("utf-8") * 80)


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
                "threshold": 0.45,
                "crop_scale": 1.6,
                "padding": 40,
                "feather": 20,
                "exclude_forehead_ratio": 0.25,
                "steps": 3,
                "denoise": 0.22,
            },
        }
    )

    assert request.prompt == "anime portrait"
    assert request.negative_prompt == "low quality"
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
    assert request.face_detailer.threshold == 0.45
    assert request.face_detailer.exclude_forehead_ratio == 0.25


def test_request_from_payload_uses_default_generation_settings():
    request = request_from_payload({"prompt": "anime portrait"})

    assert request.width == 832
    assert request.height == 1216
    assert request.steps == 20
    assert request.cfg == 3.5
    assert request.sampler == "euler_ancestral_cfg_pp"
    assert request.scheduler == "sgm_uniform"


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


def test_http_server_serves_index_and_dry_run_generate(tmp_path):
    server = create_http_server("127.0.0.1", 0, paths=_paths(tmp_path), default_dry_run=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        index_body = urllib.request.urlopen(base_url, timeout=5).read().decode("utf-8")
        assert "Anima APP" in index_body
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


def test_http_server_cancels_queued_job_and_requests_active_stop(tmp_path):
    paths = _paths(tmp_path)
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
    finally:
        server.shutdown()
        server.server_close()


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
        assert profiles["anima-t2i"]["ready"] is False
        assert profiles["anima-t2i"]["missing_count"] == 3
        assert profiles["face-detailer-detectors"]["ready"] is False
        assert profiles["face-detailer-detectors"]["missing_count"] == 3

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
        assert listed["items"][0]["request"]["upscale"] == {"enabled": True, "scale": 1.5}
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
                    "i2i": {"enabled": True, "image_path": "inputs/reference.png", "denoise": 0.42},
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
        assert manifest["i2i"] == {"enabled": True, "image_path": "inputs/reference.png", "denoise": 0.42}
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
    source.parent.mkdir()
    source.write_bytes(b"new lora")
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
        assert payload["imported"].endswith("models\\loras\\new_style.safetensors")
        assert payload["loras"] == {"count": 1, "items": [{"relative_path": "new_style.safetensors", "size_bytes": 8}]}
        assert (paths.model_root / "loras" / "new_style.safetensors").read_bytes() == b"new lora"
    finally:
        server.shutdown()
        server.server_close()


def test_http_server_serves_checkpoint_inventory(tmp_path):
    paths = _paths(tmp_path)
    checkpoint = paths.model_root / "diffusion_models" / "variants" / "anima-alt.safetensors"
    checkpoint.parent.mkdir(parents=True)
    checkpoint.write_bytes(b"alternate")
    server = create_http_server("127.0.0.1", 0, paths=paths, default_dry_run=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        with urllib.request.urlopen(f"{base_url}/api/checkpoints", timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))

        assert response.status == 200
        assert payload == {
            "count": 1,
            "default": "anima-base-v1.0.safetensors",
            "items": [{"relative_path": "variants/anima-alt.safetensors", "size_bytes": 9}],
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
        assert payload["version"] == "0.2.0"
        assert payload["repository"] == "raspie10032/anima-app"
        assert payload["repository_url"] == "https://github.com/raspie10032/anima-app"
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


def test_index_html_loads_history_panel():
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
    assert "grid-template-columns: minmax(0, 1fr) 64px" in INDEX_HTML
    assert "anima.sidebar.order.v1" not in INDEX_HTML
    assert "function applySidebarOrder" not in INDEX_HTML
    assert "function setupSidebarReorder" not in INDEX_HTML
    assert 'id="width" name="width" type="number" min="8" step="8" value="832"' in INDEX_HTML
    assert 'id="height" name="height" type="number" min="8" step="8" value="1216"' in INDEX_HTML
    assert 'id="steps" name="steps" type="number" min="1" value="20"' in INDEX_HTML
    assert 'id="cfg" name="cfg" type="number" min="0" step="0.1" value="3.5"' in INDEX_HTML
    assert 'id="sampler" name="sampler"' in INDEX_HTML
    assert '<option value="euler_ancestral_cfg_pp" selected>Euler Ancestral CFG++</option>' in INDEX_HTML
    assert 'id="scheduler" name="scheduler"' in INDEX_HTML
    assert '<option value="sgm_uniform" selected>SGM Uniform</option>' in INDEX_HTML
    assert 'id="checkpoint-select" name="checkpoint"' in INDEX_HTML
    assert '<option value="anima-base-v1.0.safetensors">anima-base-v1.0.safetensors</option>' in INDEX_HTML
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
    assert "참조 이미지 경로" in INDEX_HTML
    assert "이미지 디노이즈" in INDEX_HTML
    assert "업스케일 사용" in INDEX_HTML
    assert "타일 업스케일" in INDEX_HTML
    assert "페이스 디테일러 사용" in INDEX_HTML
    assert "설정 저장" in INDEX_HTML
    assert "설정 불러오기" in INDEX_HTML
    assert "설정 내보내기" in INDEX_HTML
    assert "설정 가져오기" in INDEX_HTML
    assert 'id="preset-import-file"' in INDEX_HTML
    assert "앱으로 LoRA 복사" in INDEX_HTML
    assert "이 결과 설정 불러오기" in INDEX_HTML
    assert "단계 비교" in INDEX_HTML
    assert "primary-action" in INDEX_HTML
    assert "request.width || 832" in INDEX_HTML
    assert "request.height || 1216" in INDEX_HTML
    assert "request.steps || 20" in INDEX_HTML
    assert "request.cfg || 3.5" in INDEX_HTML
    assert 'form.elements.sampler.value = request.sampler || "euler_ancestral_cfg_pp"' in INDEX_HTML
    assert 'form.elements.scheduler.value = request.scheduler || "sgm_uniform"' in INDEX_HTML
    assert 'setSelectValue(checkpointSelect, request.checkpoint || "anima-base-v1.0.safetensors")' in INDEX_HTML
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
    assert 'id="upscale-enabled"' in INDEX_HTML
    assert 'id="upscale-scale"' in INDEX_HTML
    assert 'id="upscale-steps"' in INDEX_HTML
    assert 'id="upscale-denoise"' in INDEX_HTML
    assert 'id="upscale-method"' in INDEX_HTML
    assert 'id="upscale-tiled"' in INDEX_HTML
    assert 'id="upscale-tile-size"' in INDEX_HTML
    assert 'id="upscale-overlap"' in INDEX_HTML
    assert 'id="vae-decode-mode"' in INDEX_HTML
    assert 'id="vae-tile-size"' in INDEX_HTML
    assert 'id="vae-overlap"' in INDEX_HTML
    assert 'id="face-detailer-enabled"' in INDEX_HTML
    assert 'id="face-detector"' in INDEX_HTML
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
    assert 'data.checkpoint = data.checkpoint || "anima-base-v1.0.safetensors"' in INDEX_HTML
    assert 'name="wildcard_mode"' in INDEX_HTML
    assert 'fetch("/api/wildcards")' in INDEX_HTML
    assert 'fetch("/api/wildcards/preview"' in INDEX_HTML
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
    assert "steps: Number(data.upscale_steps || 12)" in INDEX_HTML
    assert "denoise: Number(data.upscale_denoise || 0.35)" in INDEX_HTML
    assert "method: data.upscale_method || \"bicubic\"" in INDEX_HTML
    assert "data.vae_decode = {" in INDEX_HTML
    assert "data.face_detailer = {" in INDEX_HTML
    assert "threshold: Number(data.face_threshold || 0.5)" in INDEX_HTML
    assert "denoise: Number(data.face_denoise || 0.28)" in INDEX_HTML
    assert "exclude_forehead_ratio: Number(data.face_exclude_forehead || 0)" in INDEX_HTML
    assert 'fetch("/api/loras/import"' in INDEX_HTML
    assert 'fetch("/api/health")' in INDEX_HTML
    assert 'fetch("/api/readiness")' in INDEX_HTML
    assert 'fetch("/api/version")' in INDEX_HTML
    assert 'fetch("/api/update-check")' in INDEX_HTML
    assert "checkUpdateButton.addEventListener" in INDEX_HTML
    assert 'fetch("/api/models/prepare"' in INDEX_HTML
    assert "function renderReadiness" in INDEX_HTML
    assert "prepareModelProfile" in INDEX_HTML
    assert "data-profile" in INDEX_HTML
    assert "Copy Detectors" not in INDEX_HTML
    assert "복사 / 다운로드" in INDEX_HTML
    assert 'fetch("/api/loras")' in INDEX_HTML
    assert 'fetch("/api/checkpoints")' in INDEX_HTML
    assert "function renderCheckpointOptions" in INDEX_HTML
    assert "statusCard(\"체크포인트\"" in INDEX_HTML
    assert ".status-item" in INDEX_HTML
    assert "overflow-wrap: anywhere" in INDEX_HTML
    assert "showOutputPreview(payload.output_url)" in INDEX_HTML
    assert "outputLink.href = url" in INDEX_HTML
    assert "outputLink.hidden = false" in INDEX_HTML
    assert "#output-link[hidden]" in INDEX_HTML
    assert "function renderResultSummary" in INDEX_HTML
    assert "function setResultPayload" in INDEX_HTML
    assert "function setResultMessage" in INDEX_HTML
    assert "summaryItem(\"상태\", resultMode(payload))" in INDEX_HTML
    assert "summaryItem(\"Output\", payload.output_url || payload.output_path || \"manifest only\")" not in INDEX_HTML
    assert "function variantEntries" in INDEX_HTML
    assert "function renderCompareGrid" in INDEX_HTML
    assert "function syncCompareControls" in INDEX_HTML
    assert "toggleCompareButton.hidden" in INDEX_HTML
    assert "toggleCompareButton.addEventListener" in INDEX_HTML
    assert "function clearOutputPreview()" in INDEX_HTML
    assert 'preview.removeAttribute("src")' in INDEX_HTML
    assert 'outputLink.removeAttribute("href")' in INDEX_HTML
    assert "clearOutputPreview();" in INDEX_HTML
    assert "function submitGenerateRequest" in INDEX_HTML
    assert 'submitGenerateRequest(buildRequestData(), "생성 중...")' in INDEX_HTML
    assert "setResultPayload(payload)" in INDEX_HTML
    assert "currentManifest = null" in INDEX_HTML
    assert "payload.manifest_path.split" in INDEX_HTML
    assert "await openManifest(manifestName)" in INDEX_HTML
    assert 'id="history"' in INDEX_HTML
    assert 'id="history-count"' in INDEX_HTML
    assert 'data-history-filter="all"' in INDEX_HTML
    assert 'data-history-filter="images"' in INDEX_HTML
    assert 'data-history-filter="dry-run"' in INDEX_HTML
    assert "function historyType" in INDEX_HTML
    assert "function renderHistory" in INDEX_HTML
    assert "history-thumb" in INDEX_HTML
    assert "history-empty" in INDEX_HTML
    assert "historyFilters.forEach" in INDEX_HTML
    assert 'fetch("/api/history?limit=8")' in INDEX_HTML
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


def test_index_html_renders_binary_options_as_color_toggles():
    assert INDEX_HTML.count('class="toggle-switch"') == 4
    assert "toggle-switch:has(input:checked)" in INDEX_HTML
    assert "background: #a9444f" in INDEX_HTML
    assert "background: #2f9f55" in INDEX_HTML
    assert 'class="toggle-track" aria-hidden="true"' in INDEX_HTML
    assert 'class="toggle-state" aria-hidden="true"' in INDEX_HTML
    assert 'class="check-label"' not in INDEX_HTML
    for field_id in ("upscale-enabled", "upscale-tiled", "face-detailer-enabled", "queue-infinite"):
        assert f'<label class="toggle-switch" for="{field_id}">' in INDEX_HTML
        assert f'id="{field_id}"' in INDEX_HTML
        assert 'type="checkbox" value="1"' in INDEX_HTML


def test_index_html_exposes_generation_stage_progress():
    assert "buildGenerationStages" in INDEX_HTML
    assert "startStageProgress" in INDEX_HTML
    assert "finishGenerationStages" in INDEX_HTML
    assert "createProgressId" in INDEX_HTML
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
    assert 'status.textContent = stageVisibleStateLabels[state] ?? stageStateLabels[state] ?? state' in INDEX_HTML
    assert 'row.setAttribute("aria-label", `${item.label}: ${stageStateLabels[state] || state}`)' in INDEX_HTML
    assert "기본 렌더" in INDEX_HTML
    assert "고해상도 / 업스케일" in INDEX_HTML
    assert "VAE 디코드" in INDEX_HTML
    assert "페이스 디테일러" in INDEX_HTML
    assert "position: sticky" in INDEX_HTML
    assert "generationStages.scrollIntoView" in INDEX_HTML
    assert "data-stage-key" in INDEX_HTML
    assert "payload.stages || {}" in INDEX_HTML
    assert 'message ? `실패: ${message}` : "실패"' in INDEX_HTML
    assert 'generationStageSummary.textContent = finalState === "running" ? "작업 중" : (finalState === "failed" ? (message ? `실패: ${message}` : "실패") : "")' in INDEX_HTML


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


def test_index_html_exposes_multi_lora_controls():
    assert 'id="lora-list"' in INDEX_HTML
    assert 'id="add-lora"' in INDEX_HTML
    assert "let loraCatalog = []" in INDEX_HTML
    assert "function addLoraRow" in INDEX_HTML
    assert "function selectedLoras" in INDEX_HTML
    assert "function setLoraRows" in INDEX_HTML
    assert "loraCatalog = loras.items || []" in INDEX_HTML
    assert "addLoraButton.addEventListener(\"click\", () => addLoraRow())" in INDEX_HTML

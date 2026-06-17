import json
import threading
import urllib.error
import urllib.request
from pathlib import Path

from PIL import Image

from anima_app.assets import FACE_DETAILER_DETECTOR_ASSET_PROFILE
from anima_app.config import AppPaths
from anima_app.runtime.pipeline import T2IRenderOutput
from anima_app.server import INDEX_HTML, create_http_server, handle_generate, request_from_payload


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
        output_path.parent.mkdir(parents=True)
        Image.new("RGB", (request.width, request.height), "white").save(output_path)
        return T2IRenderOutput(output_path=output_path, stages={"base_t2i": {"status": "completed"}})

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
        manifest_name = manifest_path.name
        assert manifest_path.is_file()
        assert output_path.is_file()

        delete_request = urllib.request.Request(f"{base_url}/api/manifests/{manifest_name}", method="DELETE")
        with urllib.request.urlopen(delete_request, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))

        assert response.status == 200
        assert payload["status"] == "deleted"
        assert payload["deleted_manifest"] is True
        assert payload["deleted_output"] is True
        assert not manifest_path.exists()
        assert not output_path.exists()

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
    wildcard_file.parent.mkdir(parents=True)
    wildcard_file.write_text("soft lineart\nbold shadows\n", encoding="utf-8")
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
        }
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
    assert 'id="generation-stages"' in INDEX_HTML
    assert 'aria-label="Current result"' in INDEX_HTML
    assert 'id="result-title"' in INDEX_HTML
    assert 'id="result-status"' in INDEX_HTML
    assert 'id="result-summary"' in INDEX_HTML
    assert 'id="output-link"' in INDEX_HTML
    assert "Manifest JSON" in INDEX_HTML
    assert 'id="preset-standard"' in INDEX_HTML
    assert 'id="preset-reference"' in INDEX_HTML
    assert 'id="generate-button" class="primary-action" type="submit"' in INDEX_HTML
    assert 'aria-live="polite"' in INDEX_HTML
    assert 'id="lora-import-form"' in INDEX_HTML
    assert 'id="generate-form"></form>' in INDEX_HTML
    assert 'class="app-shell"' in INDEX_HTML
    assert 'class="control-frame"' in INDEX_HTML
    assert 'class="workspace-frame"' in INDEX_HTML
    assert 'class="history-frame"' in INDEX_HTML
    assert 'id="top-status-strip"' not in INDEX_HTML
    assert 'id="side-status-panel"' in INDEX_HTML
    assert 'class="side-status-panel"' in INDEX_HTML
    assert '<summary>Runtime Status</summary>' in INDEX_HTML
    assert 'id="control-groups"' in INDEX_HTML
    assert 'class="control-group"' in INDEX_HTML
    assert 'form="generate-form"' in INDEX_HTML
    for group_key in (
        "prompt-generate",
        "model-style",
        "image-settings",
        "enhance",
        "prompt-tools",
        "settings",
    ):
        assert f'data-control-group="{group_key}"' in INDEX_HTML
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
    assert "Image Settings" in INDEX_HTML
    assert "Prompt Tools" in INDEX_HTML
    assert "Model & Style" in INDEX_HTML
    assert "<summary>Reference Image and Upscale</summary>" in INDEX_HTML
    assert "<summary>Face Detailer</summary>" in INDEX_HTML
    assert 'id="reference-image-section"' in INDEX_HTML
    assert 'id="face-detailer-section"' in INDEX_HTML
    assert 'const referenceImageSection = document.getElementById("reference-image-section")' in INDEX_HTML
    assert "referenceImageSection.open = Boolean" in INDEX_HTML
    assert "faceDetailerSection.open = Boolean" in INDEX_HTML
    assert "<h2>Saved Settings</h2>" in INDEX_HTML
    assert "<h2>Import LoRA</h2>" in INDEX_HTML
    assert "Starting Point" in INDEX_HTML
    assert "Selected LoRA" in INDEX_HTML
    assert "LoRA Strength" in INDEX_HTML
    assert "Reference Image Path" in INDEX_HTML
    assert "Image Denoise" in INDEX_HTML
    assert "Enable Upscale" in INDEX_HTML
    assert "Tile Upscale" in INDEX_HTML
    assert "Enable Face Detailer" in INDEX_HTML
    assert "Save Settings" in INDEX_HTML
    assert "Load Settings" in INDEX_HTML
    assert "Export Settings" in INDEX_HTML
    assert "Import Settings" in INDEX_HTML
    assert 'id="preset-import-file"' in INDEX_HTML
    assert "Copy LoRA into App" in INDEX_HTML
    assert "Use Current Manifest" in INDEX_HTML
    assert "primary-action" in INDEX_HTML
    assert "request.width || 832" in INDEX_HTML
    assert "request.height || 1216" in INDEX_HTML
    assert "request.steps || 20" in INDEX_HTML
    assert "request.cfg || 3.5" in INDEX_HTML
    assert 'form.elements.sampler.value = request.sampler || "euler_ancestral_cfg_pp"' in INDEX_HTML
    assert 'form.elements.scheduler.value = request.scheduler || "sgm_uniform"' in INDEX_HTML
    assert 'setSelectValue(checkpointSelect, request.checkpoint || "anima-base-v1.0.safetensors")' in INDEX_HTML
    assert "const quickPresets = {" in INDEX_HTML
    assert "reference_quality: {" in INDEX_HTML
    assert "width: 768" in INDEX_HTML
    assert "height: 1152" in INDEX_HTML
    assert "steps: 24" in INDEX_HTML
    assert 'sampler: "euler_ancestral_cfg_pp"' in INDEX_HTML
    assert 'scheduler: "sgm_uniform"' in INDEX_HTML
    assert 'vae_decode: {mode: "tiled", tile_size: 96, overlap: 16}' in INDEX_HTML
    assert "referencePresetButton.addEventListener" in INDEX_HTML
    assert "const button = generateButton" in INDEX_HTML
    assert "const fallbackPrompt = form.elements.prompt.defaultValue" in INDEX_HTML
    assert "current.prompt.trim() ? current.prompt : fallbackPrompt" in INDEX_HTML
    assert "const fallbackNegativePrompt = form.elements.negative_prompt.defaultValue" in INDEX_HTML
    assert "current.negative_prompt.trim() ? current.negative_prompt : fallbackNegativePrompt" in INDEX_HTML
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
    assert 'id="lora-select"' in INDEX_HTML
    assert 'id="lora-strength"' in INDEX_HTML
    assert 'id="lora-strength" name="lora_strength" type="number" min="0" step="0.05" value="1"' in INDEX_HTML
    assert "const checkpointSelect = document.getElementById(\"checkpoint-select\")" in INDEX_HTML
    assert 'id="wildcard-mode"' in INDEX_HTML
    assert '<option value="random" selected>Random</option>' in INDEX_HTML
    assert '<option value="off">Off</option>' not in INDEX_HTML
    assert 'id="wildcard-select"' in INDEX_HTML
    assert 'id="insert-wildcard"' in INDEX_HTML
    assert "data.loras = [" in INDEX_HTML
    assert 'data.checkpoint = data.checkpoint || "anima-base-v1.0.safetensors"' in INDEX_HTML
    assert 'name="wildcard_mode"' in INDEX_HTML
    assert 'fetch("/api/wildcards")' in INDEX_HTML
    assert "insertWildcard" in INDEX_HTML
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
    assert 'fetch("/api/models/prepare"' in INDEX_HTML
    assert "function renderReadiness" in INDEX_HTML
    assert "prepareModelProfile" in INDEX_HTML
    assert "data-profile" in INDEX_HTML
    assert 'fetch("/api/loras")' in INDEX_HTML
    assert 'fetch("/api/checkpoints")' in INDEX_HTML
    assert "function renderCheckpointOptions" in INDEX_HTML
    assert "statusCard(\"Checkpoints\"" in INDEX_HTML
    assert ".status-item" in INDEX_HTML
    assert "overflow-wrap: anywhere" in INDEX_HTML
    assert "showOutputPreview(payload.output_url)" in INDEX_HTML
    assert "outputLink.href = url" in INDEX_HTML
    assert "outputLink.hidden = false" in INDEX_HTML
    assert "#output-link[hidden]" in INDEX_HTML
    assert "function renderResultSummary" in INDEX_HTML
    assert "function setResultPayload" in INDEX_HTML
    assert "function setResultMessage" in INDEX_HTML
    assert "summaryItem(\"Status\", resultMode(payload))" in INDEX_HTML
    assert "summaryItem(\"Output\", payload.output_url || payload.output_path || \"manifest only\")" not in INDEX_HTML
    assert "function clearOutputPreview()" in INDEX_HTML
    assert 'preview.removeAttribute("src")' in INDEX_HTML
    assert 'outputLink.removeAttribute("href")' in INDEX_HTML
    assert "clearOutputPreview();" in INDEX_HTML
    assert "function submitGenerateRequest" in INDEX_HTML
    assert 'submitGenerateRequest(buildRequestData(), "Generating...")' in INDEX_HTML
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
    assert "form.elements.lora_strength.value = lora.model_strength ?? 1" in INDEX_HTML


def test_index_html_renders_binary_options_as_color_toggles():
    assert INDEX_HTML.count('class="toggle-switch"') == 3
    assert "toggle-switch:has(input:checked)" in INDEX_HTML
    assert "background: #a9444f" in INDEX_HTML
    assert "background: #2f9f55" in INDEX_HTML
    assert 'class="toggle-track" aria-hidden="true"' in INDEX_HTML
    assert 'class="toggle-state" aria-hidden="true"' in INDEX_HTML
    assert 'class="check-label"' not in INDEX_HTML
    for field_id in ("upscale-enabled", "upscale-tiled", "face-detailer-enabled"):
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
    assert "Base Render" in INDEX_HTML
    assert "High-res / Upscale" in INDEX_HTML
    assert "VAE Decode" in INDEX_HTML
    assert "Face Detailer" in INDEX_HTML
    assert "position: sticky" in INDEX_HTML
    assert "generationStages.scrollIntoView" in INDEX_HTML
    assert "data-stage-key" in INDEX_HTML
    assert "payload.stages || {}" in INDEX_HTML
    assert 'message ? `Failed: ${message}` : "Failed"' in INDEX_HTML
    assert 'generationStageSummary.textContent = finalState === "running" ? "Working" : (finalState === "failed" ? (message ? `Failed: ${message}` : "Failed") : "")' in INDEX_HTML


def test_index_html_exposes_auto_queue_controls():
    assert 'id="auto-queue-panel"' in INDEX_HTML
    assert 'id="queue-count"' in INDEX_HTML
    assert 'name="queue_count"' in INDEX_HTML
    assert 'id="queue-seed-mode"' in INDEX_HTML
    assert '<option value="fixed">Fixed</option>' in INDEX_HTML
    assert '<option value="increment" selected>Increment</option>' in INDEX_HTML
    assert '<option value="random">Random</option>' in INDEX_HTML
    assert 'id="queue-delay"' in INDEX_HTML
    assert 'id="start-queue"' in INDEX_HTML
    assert 'id="stop-queue"' in INDEX_HTML
    assert 'id="queue-status"' in INDEX_HTML
    assert "const autoQueuePanel = document.getElementById(\"auto-queue-panel\")" in INDEX_HTML
    assert "const queueCountInput = document.getElementById(\"queue-count\")" in INDEX_HTML
    assert "const queueSeedMode = document.getElementById(\"queue-seed-mode\")" in INDEX_HTML
    assert "const queueDelayInput = document.getElementById(\"queue-delay\")" in INDEX_HTML
    assert "function queueSeedForIndex" in INDEX_HTML
    assert "async function runQueuedGenerate" in INDEX_HTML
    assert "async function startAutoQueue" in INDEX_HTML
    assert "function stopAutoQueue" in INDEX_HTML
    assert "queueSeedMode.value" in INDEX_HTML
    assert "queueStopRequested" in INDEX_HTML

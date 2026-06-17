import json
from pathlib import Path

from PIL import Image

from anima_app.cli import main
from anima_app.config import AppPaths
from anima_app.runtime.pipeline import T2IRenderOutput


def _paths(tmp_path: Path) -> AppPaths:
    return AppPaths(
        project_root=tmp_path / "app",
        development_model_source=tmp_path / "source",
        face_detailer_detector_source=tmp_path / "detectors",
    )


def _write_profile_sources(paths: AppPaths) -> None:
    for relative_path in (
        Path("diffusion_models") / "anima-base-v1.0.safetensors",
        Path("text_encoders") / "qwen_3_06b_base.safetensors",
        Path("vae") / "qwen_image_vae.safetensors",
    ):
        source = paths.development_model_source / relative_path
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes(relative_path.name.encode("utf-8"))


def _write_face_detector_sources(paths: AppPaths) -> None:
    for name in ("face_yolov8n.pt", "full_eyes_detect_v1.pt", "sam_b.pt"):
        source = paths.face_detailer_detector_source / name
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes(name.encode("utf-8") * 128)


def test_health_json_reports_missing_anima_profile(tmp_path, capsys):
    exit_code = main(["health", "--json"], paths=_paths(tmp_path))
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["models"]["ready"] is False
    assert payload["models"]["profile"] == "anima-t2i"
    assert len(payload["models"]["missing"]) == 3
    assert payload["model_root"] == str(tmp_path / "app" / "models")


def test_models_inventory_outputs_development_source_files(tmp_path, capsys):
    paths = _paths(tmp_path)
    source_file = paths.development_model_source / "diffusion_models" / "model.safetensors"
    source_file.parent.mkdir(parents=True)
    source_file.write_bytes(b"model")

    exit_code = main(["models", "inventory"], paths=paths)
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["source_root"] == str(paths.development_model_source.resolve())
    assert payload["model_root"] == str(paths.model_root)
    assert payload["files"] == [{"relative_path": str(Path("diffusion_models") / "model.safetensors"), "size_bytes": 5}]


def test_models_copy_profile_copies_anima_t2i_assets(tmp_path, capsys):
    paths = _paths(tmp_path)
    _write_profile_sources(paths)

    exit_code = main(["models", "copy-profile", "anima-t2i"], paths=paths)
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["profile"] == "anima-t2i"
    assert len(payload["copied"]) == 3
    assert (paths.model_root / "diffusion_models" / "anima-base-v1.0.safetensors").read_bytes() == b"anima-base-v1.0.safetensors"
    assert (paths.model_root / "text_encoders" / "qwen_3_06b_base.safetensors").is_file()
    assert (paths.model_root / "vae" / "qwen_image_vae.safetensors").is_file()


def test_models_copy_profile_downloads_anima_t2i_assets_from_huggingface(tmp_path, capsys, monkeypatch):
    paths = _paths(tmp_path)
    downloaded: list[Path] = []

    def fake_download(dest_root, relative_path):
        target = dest_root / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(relative_path.name.encode("utf-8"))
        downloaded.append(relative_path)
        return target

    monkeypatch.setattr("anima_app.assets.download_asset_file_from_huggingface", fake_download)

    exit_code = main(["models", "copy-profile", "anima-t2i", "--source", "huggingface"], paths=paths)
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["profile"] == "anima-t2i"
    assert payload["source"] == "huggingface"
    assert downloaded == [
        Path("diffusion_models") / "anima-base-v1.0.safetensors",
        Path("text_encoders") / "qwen_3_06b_base.safetensors",
        Path("vae") / "qwen_image_vae.safetensors",
    ]
    assert (paths.model_root / "diffusion_models" / "anima-base-v1.0.safetensors").is_file()


def test_models_copy_profile_auto_uses_huggingface_when_local_anima_assets_are_missing(tmp_path, capsys, monkeypatch):
    paths = _paths(tmp_path)
    downloaded: list[Path] = []

    def fake_download(dest_root, relative_path):
        target = dest_root / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"downloaded")
        downloaded.append(relative_path)
        return target

    monkeypatch.setattr("anima_app.assets.download_asset_file_from_huggingface", fake_download)

    exit_code = main(["models", "copy-profile", "anima-t2i"], paths=paths)
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["source"] == "huggingface"
    assert len(downloaded) == 3


def test_models_copy_profile_copies_face_detailer_detectors(tmp_path, capsys):
    paths = _paths(tmp_path)
    _write_face_detector_sources(paths)

    exit_code = main(["models", "copy-profile", "face-detailer-detectors"], paths=paths)
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["profile"] == "face-detailer-detectors"
    assert len(payload["copied"]) == 3
    assert (paths.model_root / "detectors" / "face_yolov8n.pt").read_bytes().startswith(b"face_yolov8n.pt")
    assert (paths.model_root / "detectors" / "full_eyes_detect_v1.pt").is_file()
    assert (paths.model_root / "detectors" / "sam_b.pt").is_file()


def test_models_copy_profile_uses_valid_face_detailer_detector_fallback(tmp_path, capsys):
    primary = tmp_path / "placeholder_detectors"
    fallback = tmp_path / "real_detectors"
    paths = AppPaths(
        project_root=tmp_path / "app",
        development_model_source=tmp_path / "source",
        face_detailer_detector_source=primary,
        face_detailer_detector_fallback_sources=(fallback,),
    )
    for name in ("face_yolov8n.pt", "full_eyes_detect_v1.pt", "sam_b.pt"):
        primary.mkdir(parents=True, exist_ok=True)
        (primary / name).write_bytes(b"placeholder")
        fallback.mkdir(parents=True, exist_ok=True)
        (fallback / name).write_bytes((name + "-real").encode("utf-8") * 128)

    exit_code = main(["models", "copy-profile", "face-detailer-detectors"], paths=paths)
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["profile"] == "face-detailer-detectors"
    assert (paths.model_root / "detectors" / "face_yolov8n.pt").read_bytes().startswith(b"face_yolov8n.pt-real")
    assert (paths.model_root / "detectors" / "sam_b.pt").read_bytes().startswith(b"sam_b.pt-real")


def test_models_import_lora_and_list_loras(tmp_path, capsys):
    paths = _paths(tmp_path)
    source = tmp_path / "style.safetensors"
    source.write_bytes(b"lora")

    import_code = main(["models", "import-lora", str(source)], paths=paths)
    import_payload = json.loads(capsys.readouterr().out)
    list_code = main(["models", "loras"], paths=paths)
    list_payload = json.loads(capsys.readouterr().out)

    assert import_code == 0
    assert import_payload["imported"] == str(paths.model_root / "loras" / "style.safetensors")
    assert list_code == 0
    assert list_payload["items"] == [{"relative_path": "style.safetensors", "size_bytes": 4}]


def test_models_checkpoints_lists_local_diffusion_models(tmp_path, capsys):
    paths = _paths(tmp_path)
    checkpoint = paths.model_root / "diffusion_models" / "variants" / "anima-alt.safetensors"
    checkpoint.parent.mkdir(parents=True)
    checkpoint.write_bytes(b"alternate")

    exit_code = main(["models", "checkpoints"], paths=paths)
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload == {"count": 1, "items": [{"relative_path": "variants/anima-alt.safetensors", "size_bytes": 9}]}


def test_t2i_dry_run_outputs_manifest_payload(tmp_path, capsys):
    paths = _paths(tmp_path)

    exit_code = main(
        [
            "t2i",
            "--prompt",
            "anime portrait",
            "--negative",
            "low quality",
            "--width",
            "512",
            "--height",
            "768",
            "--steps",
            "1",
            "--cfg",
            "1.0",
            "--seed",
            "52",
            "--checkpoint",
            "variants/anima-alt.safetensors",
            "--lora",
            "style.safetensors|0.5|0.25",
            "--image",
            "inputs/reference.png",
            "--denoise",
            "0.42",
            "--upscale",
            "--upscale-scale",
            "1.5",
            "--upscale-steps",
            "2",
            "--upscale-denoise",
            "0.25",
            "--upscale-method",
            "bicubic",
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
            "--face-crop-scale",
            "1.6",
            "--face-padding",
            "40",
            "--face-feather",
            "20",
            "--face-exclude-forehead",
            "0.25",
            "--face-steps",
            "3",
            "--face-denoise",
            "0.22",
            "--dry-run",
        ],
        paths=paths,
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["status"] == "dry_run"
    assert payload["output_path"] is None
    assert Path(payload["manifest_path"]).is_file()
    assert payload["stages"]["face_detailer"]["status"] == "skipped"
    assert payload["stages"]["face_detailer"]["reason"] == "dry_run_not_executed"
    manifest = json.loads(Path(payload["manifest_path"]).read_text(encoding="utf-8"))
    assert manifest["checkpoint"] == "variants/anima-alt.safetensors"
    assert manifest["loras"] == [{"path": "style.safetensors", "model_strength": 0.5, "clip_strength": 0.25}]
    assert manifest["i2i"] == {"enabled": True, "image_path": "inputs/reference.png", "denoise": 0.42}
    assert manifest["upscale"] == {
        "enabled": True,
        "scale": 1.5,
        "steps": 2,
        "denoise": 0.25,
        "method": "bicubic",
        "tiled": True,
        "tile_size": 64,
        "overlap": 8,
    }
    assert manifest["vae_decode"] == {"mode": "tiled", "tile_size": 96, "overlap": 16}
    assert manifest["stages"]["vae_decode"]["method"] == "not_run"
    assert manifest["face_detailer"] == {
        "enabled": True,
        "detector": "bbox/face_yolov8m.pt",
        "threshold": 0.45,
        "crop_scale": 1.6,
        "padding": 40,
        "feather": 20,
        "exclude_forehead_ratio": 0.25,
        "steps": 3,
        "denoise": 0.22,
    }


def test_t2i_dry_run_expands_wildcards_and_records_manifest(tmp_path, capsys):
    paths = _paths(tmp_path)
    wildcard_file = paths.project_root / "wildcards" / "style.txt"
    wildcard_file.parent.mkdir(parents=True)
    wildcard_file.write_text("soft lineart\n", encoding="utf-8")

    exit_code = main(
        [
            "t2i",
            "--prompt",
            "anime portrait, __style__",
            "--width",
            "512",
            "--height",
            "768",
            "--steps",
            "1",
            "--seed",
            "52",
            "--wildcards",
            "random",
            "--dry-run",
        ],
        paths=paths,
    )
    payload = json.loads(capsys.readouterr().out)
    manifest = json.loads(Path(payload["manifest_path"]).read_text(encoding="utf-8"))

    assert exit_code == 0
    assert manifest["prompt"] == "anime portrait, soft lineart"
    assert manifest["wildcards"]["mode"] == "random"
    assert manifest["wildcards"]["original_prompt"] == "anime portrait, __style__"
    assert manifest["wildcards"]["selections"][0]["wildcard"] == "style"


def test_t2i_real_run_uses_default_renderer_hook(tmp_path, capsys, monkeypatch):
    paths = _paths(tmp_path)
    captured = {}

    def fake_default_renderer(request, active_paths):
        captured["width"] = request.width
        captured["height"] = request.height
        captured["steps"] = request.steps
        captured["cfg"] = request.cfg
        output_path = active_paths.image_root / "cli-real.png"
        output_path.parent.mkdir(parents=True)
        Image.new("RGB", (request.width, request.height), "white").save(output_path)
        return T2IRenderOutput(output_path=output_path, stages={"base_t2i": {"status": "completed"}})

    monkeypatch.setattr("anima_app.cli.default_t2i_renderer", fake_default_renderer)

    exit_code = main(
        [
            "t2i",
            "--prompt",
            "anime portrait",
        ],
        paths=paths,
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["status"] == "generated"
    assert Path(payload["output_path"]).is_file()
    assert payload["stages"]["base_t2i"]["status"] == "completed"
    assert captured == {"width": 832, "height": 1216, "steps": 20, "cfg": 3.5}


def test_serve_supports_dynamic_port_and_open(tmp_path, capsys, monkeypatch):
    paths = _paths(tmp_path)
    opened_urls: list[str] = []
    captured: dict[str, object] = {}

    class FakeServer:
        server_address = ("127.0.0.1", 43210)

        def serve_forever(self):
            raise KeyboardInterrupt

        def server_close(self):
            captured["closed"] = True

    def fake_create_http_server(host, port, **kwargs):
        captured["host"] = host
        captured["port"] = port
        captured["default_dry_run"] = kwargs["default_dry_run"]
        return FakeServer()

    monkeypatch.setattr("anima_app.cli.create_http_server", fake_create_http_server)
    monkeypatch.setattr("anima_app.cli.webbrowser.open", opened_urls.append)

    exit_code = main(["serve", "--host", "127.0.0.1", "--port", "0", "--dry-run-default", "--open"], paths=paths)
    output = capsys.readouterr().out

    assert exit_code == 0
    assert captured["host"] == "127.0.0.1"
    assert captured["port"] == 0
    assert captured["default_dry_run"] is True
    assert captured["closed"] is True
    assert "http://127.0.0.1:43210" in output
    assert opened_urls == ["http://127.0.0.1:43210"]

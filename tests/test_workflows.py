import copy
import io
import json
import zipfile
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest
from PIL import Image

from anima_app import server
from anima_app.config import AppPaths
from anima_app.manifests import read_manifest
from anima_app.output_names import allocate_output_path
from anima_app.providers import novelai
from anima_app.requests import T2IRequest, I2ISettings, FaceDetailerSettings
from anima_app.runtime.pipeline import T2IRenderOutput


def plan(base="novelai", steps=("local",)):
    return {
        "provider": base,
        "nai_model": "nai-diffusion-4-5-full",
        "prompt": "portrait",
        "negative_prompt": "blur",
        "width": 512,
        "height": 512,
        "seed": 21,
        "workflow": {
            "version": 1,
            "steps": [
                {
                    "provider": p,
                    "operation": "detail",
                    "inherit_prompt": True,
                    "request": {"nai_model": "nai-diffusion-4-5-full"}
                    if p == "novelai"
                    else {},
                }
                for p in steps
            ],
        },
    }


def test_nai_workflow_keeps_character_coordinates_wildcards_and_selected_settings(harness):
    paths, calls, local = harness
    payload = plan(steps=("local", "novelai"))
    payload.update(cfg=4, steps=17, nai_sampler="k_euler_ancestral", nai_use_coords=True,
                   nai_characters=[{"prompt": "{red|green} hair", "negative_prompt": "hat", "x": .2, "y": .5},
                                   {"prompt": "blue hair", "negative_prompt": "ribbon", "x": .8, "y": .5}])
    step = payload["workflow"]["steps"][1]
    step["inherit_settings"] = ["cfg", "steps"]
    step["request"].update(cfg=8, nai_sampler="k_euler", nai_detailer={"steps": 24})
    status, result = server.handle_generate(payload, paths=paths, renderer=local)
    assert status == 200, result
    detail = calls[-1][3]
    assert detail.cfg == 4 and detail.detailer["steps"] == 17
    assert detail.sampler == "k_euler"
    assert detail.detailer["matching"] == "wd14"
    assert detail.characters[0]["x"] == .2 and detail.characters[1]["negative_prompt"] == "ribbon"
    assert detail.characters[0]["prompt"] == calls[0][3]["parameters"]["v4_prompt"]["caption"]["char_captions"][0]["char_caption"]


@pytest.mark.parametrize("fields", [["token"], ["cfg", "cfg"], "cfg", ["seed"], [None]])
def test_workflow_rejects_invalid_inherited_settings(harness, fields):
    paths, calls, local = harness
    payload = plan(steps=("novelai",))
    payload["workflow"]["steps"][0]["inherit_settings"] = fields
    status, result = server.handle_generate(payload, paths=paths, renderer=local)
    assert status == 400, result
    assert not calls


@pytest.fixture
def harness(tmp_path, monkeypatch):
    paths = AppPaths(project_root=tmp_path)
    calls = []
    monkeypatch.setattr(
        server, "_generation_readiness", lambda *a, **kw: {"ready": True}
    )
    from anima_app.runtime import face_detailer

    monkeypatch.setattr(face_detailer, "missing_detector_paths", lambda *a: ())
    monkeypatch.setattr(novelai, "token_status", lambda: {"configured": True})
    monkeypatch.setenv("NAI_ACCESS_TOKEN", "synthetic-test-only")
    from anima_app.providers.novelai import detailer

    monkeypatch.setattr(detailer, "preflight", lambda *a, **kw: None)
    monkeypatch.setattr(detailer.Detector, "preflight", lambda *a: None)

    def repaint(source, request, paths, **kwargs):
        calls.append(("novelai", "detail", source.copy(), request))
        edited = source.copy()
        edited.putpixel((0, 0), (0, 0, 255))
        return edited, Image.new("L", source.size, 255), []

    monkeypatch.setattr(detailer, "repaint", repaint)

    def transport(url, headers, body, timeout):
        payload = json.loads(body)
        calls.append(("novelai", "generate", None, payload))
        png, output = io.BytesIO(), io.BytesIO()
        Image.new(
            "RGB",
            (payload["parameters"]["width"], payload["parameters"]["height"]),
            "red",
        ).save(png, format="PNG")
        with zipfile.ZipFile(output, "w") as archive:
            archive.writestr("image.png", png.getvalue())
        return output.getvalue()

    generate = novelai.generate

    def remote(request, **kwargs):
        return generate(
            request,
            **kwargs,
            transport=transport,
            sleep=lambda _: None,
            subscription_transport=lambda *a: json.dumps(
                {"active": True, "tier": 3, "usage": {"percent": 100}}
            ).encode(),
        )

    monkeypatch.setattr(novelai, "generate", remote)

    def local(request, paths):
        source = (
            Image.open(paths.project_root / request.i2i.image_path).convert("RGB")
            if request.i2i.enabled
            else None
        )
        calls.append(("local", request.operation, source, request))
        output = allocate_output_path(request, paths=paths, status="generated")
        output.parent.mkdir(parents=True, exist_ok=True)
        image = (
            source.copy()
            if source
            else Image.new("RGB", (request.width, request.height), "green")
        )
        if request.operation == "detail":
            image.putpixel((0, 0), (255, 255, 0))
        if request.operation == "upscale":
            image = image.resize(
                (
                    int(request.width * request.upscale.scale),
                    int(request.height * request.upscale.scale),
                )
            )
        image.save(output)
        return T2IRenderOutput(output)

    return paths, calls, local


@pytest.mark.parametrize(
    "base,steps",
    [
        ("novelai", ("local",)),
        ("local", ("novelai",)),
        ("novelai", ("local", "novelai")),
    ],
)
def test_cross_provider_handoff_and_durable_lineage(harness, base, steps):
    paths, calls, local = harness
    payload = plan(base, steps)
    original = copy.deepcopy(payload)
    status, result = server.handle_generate(payload, paths=paths, renderer=local)
    assert status == 200, result
    assert result["workflow_run"]["status"] == "completed"
    assert [(c[0], c[1]) for c in calls] == [
        (base, "generate"),
        *[(p, "detail") for p in steps],
    ]
    assert calls[1][2].getpixel((1, 1)) == (
        (255, 0, 0) if base == "novelai" else (0, 128, 0)
    )
    if len(steps) > 1:
        assert calls[2][2].getpixel((0, 0)) == (255, 255, 0)
    assert payload == original
    run = result["workflow_run"]
    assert run["steps"][1]["input_sha256"] == run["steps"][0]["output_sha256"]
    assert len(list(paths.manifest_root.glob("*.json"))) == len(steps) + 1
    final = read_manifest(Path(result["manifest_path"]))
    assert (
        final["workflow_base_request"]["provider"] == base
        if base == "novelai"
        else final["workflow_base_request"].get("provider", "local") == base
    )
    assert len(final["workflow"]["steps"]) == len(steps)
    assert (
        len([k for k in final["variants"] if k.startswith("workflow_")])
        == len(steps) + 1
    )
    assert (
        json.loads(next((paths.output_root / "workflows").glob("*.json")).read_text())[
            "run"
        ]["status"]
        == "completed"
    )


def test_reordering_uses_previous_step_and_inherits_actual_output_size(harness):
    paths, calls, local = harness
    payload = plan("novelai", ("local", "local"))
    payload["workflow"]["steps"][0].update(
        operation="upscale", request={"upscale": {"scale": 1.5}}
    )
    status, result = server.handle_generate(payload, paths=paths, renderer=local)
    assert status == 200, result
    assert result["workflow_run"]["status"] == "completed"
    assert calls[2][2].size == (768, 768)
    assert (calls[2][3].width, calls[2][3].height) == (768, 768)


@pytest.mark.parametrize(
    "base, downstream", [("novelai", "local"), ("local", "novelai")]
)
def test_prompt_adaptation_and_source_survive_real_orchestration(
    harness, base, downstream
):
    paths, calls, local = harness
    payload = plan(base, (downstream,))
    original = "(artist:alpha, artist:beta:0.85), portrait"
    source = {"asset_id": "a" * 64, "record_id": "b" * 64, "scope": "artists"}
    payload.update(
        prompt=original, prompt_routing={"source": "auto"}, generation_sources=[source]
    )
    code, result = server.handle_generate(payload, paths=paths, renderer=local)
    assert code == 200 and result["workflow_run"]["status"] == "completed", result
    for engine, operation, image, request in calls:
        prompt = request["input"] if isinstance(request, dict) else request.prompt
        assert (
            ("artist:alpha" in prompt)
            if engine == "novelai"
            else ("@alpha" in prompt and "artist:" not in prompt)
        )
    for step in result["workflow_run"]["steps"]:
        manifest = read_manifest(paths.manifest_root / step["manifest_name"])
        assert manifest["generation_sources"] == [source]
        assert manifest["authoring_request"]["prompt"] == original
        assert manifest["workflow_base_request"]["prompt"] == original
        assert manifest["prompt_processing"]["fields"][0]["original"] == original


def test_failure_keeps_base_and_stops_remaining_steps(harness):
    paths, calls, _ = harness

    def fail(*a):
        raise RuntimeError("detailer failed")

    status, result = server.handle_generate(
        plan("novelai", ("local", "novelai")), paths=paths, renderer=fail
    )
    assert status == 200 and result["status"] == "partial"
    assert result["stop_scheduling"]
    assert Path(result["output_path"]).exists()
    assert len(calls) == 1
    assert [s["status"] for s in result["workflow_run"]["steps"]] == [
        "completed",
        "failed",
        "skipped",
    ]


def test_cancel_after_base_does_not_start_next_provider(harness):
    paths, calls, local = harness
    status, result = server.handle_generate(
        plan("local", ("novelai",)),
        paths=paths,
        renderer=local,
        cancelled=lambda: bool(calls),
    )
    assert status == 200 and result["status"] == "partial"
    assert result["workflow_run"]["status"] == "cancelled"
    assert len(calls) == 1


def test_dry_run_plans_without_transport_renderer_or_placeholder_images(harness):
    paths, calls, local = harness
    status, result = server.handle_generate(
        {**plan(), "dry_run": True}, paths=paths, renderer=local
    )
    assert status == 200, result
    assert result["status"] == "dry_run" and result["output_path"] is None
    assert result["workflow_run"]["status"] == "dry_run"
    assert [s["status"] for s in result["workflow_run"]["steps"]] == [
        "configured",
        "configured",
    ]
    assert not calls and not paths.input_root.exists()


def test_preflight_blocks_paid_base_when_downstream_models_are_missing(
    harness, monkeypatch
):
    paths, calls, local = harness
    monkeypatch.setattr(
        server, "_generation_readiness", lambda *a, **kw: {"ready": False}
    )
    status, result = server.handle_generate(plan(), paths=paths, renderer=local)
    assert status == 400 and "2단계" in result["error"]
    assert not calls


def test_selected_nai_detector_checked_before_paid_first_step(tmp_path, monkeypatch):
    import sys
    paths = AppPaths(project_root=tmp_path, face_detailer_detector_source=tmp_path / "external_detectors",
                     face_detailer_detector_fallback_sources=())
    models = paths.model_root / "detectors"
    models.mkdir(parents=True)
    for name in ("sam_b.pt", "face_yolov8n.pt", "full_eyes_detect_v1.pt"):
        (models / name).write_bytes(b"synthetic placeholder")
    monkeypatch.setattr(novelai, "token_status", lambda: {"configured": True})
    monkeypatch.setitem(sys.modules, "ultralytics", SimpleNamespace(SAM=lambda: None, YOLO=lambda: None))
    calls = []
    monkeypatch.setattr(novelai, "generate", lambda *a, **kw: calls.append(1))
    payload = plan(steps=("novelai",))
    payload["workflow"]["steps"][0]["request"]["nai_detailer"] = {"face_detector": "face_yolov8m.pt"}
    status, result = server.handle_generate(payload, paths=paths)
    assert status == 400 and "face_yolov8m.pt" in result["error"]
    assert not calls


@pytest.mark.parametrize(
    "mutation",
    [
        lambda p: p["workflow"]["steps"][0].update(operation="generate"),
        lambda p: p["workflow"]["steps"][0]["request"].update(workflow={"steps": []}),
        lambda p: p["workflow"]["steps"][0]["request"].update(api_key="never-store"),
        lambda p: p["workflow"]["steps"][0]["request"].update(dry_run=False),
        lambda p: p["workflow"].update(steps=p["workflow"]["steps"] * 7),
        lambda p: p["workflow"]["steps"][0].update(inherit_prompt="false"),
    ],
)
def test_invalid_workflow_rejected_before_base(harness, mutation):
    paths, calls, local = harness
    payload = plan()
    mutation(payload)
    status, result = server.handle_generate(payload, paths=paths, renderer=local)
    assert status >= 400, result
    assert not calls


def test_prompt_override_and_preset_roundtrip(harness):
    paths, calls, local = harness
    payload = plan()
    payload["workflow"]["steps"][0].update(
        inherit_prompt=False,
        request={"prompt": "blue eyes", "negative_prompt": "red eyes"},
    )
    normalized = server._normalized_preset_request(payload)
    assert server._normalized_preset_request(normalized) == normalized
    status, result = server.handle_generate(normalized, paths=paths, renderer=local)
    assert status == 200, result
    assert (calls[1][3].prompt, calls[1][3].negative_prompt) == (
        "blue eyes",
        "red eyes",
    )


@pytest.mark.parametrize(
    "base,steps", [("novelai", ("local", "novelai")), ("local", ("novelai", "local"))]
)
def test_actual_provider_handoffs_route_from_authoring_once(harness, base, steps):
    paths, calls, local = harness
    payload = plan(base, steps)
    payload.update(
        prompt="(artist:alpha, artist:beta:0.9), portrait",
        negative_prompt="(blur:1.2)",
        prompt_routing={"source": "auto"},
        generation_sources=[
            {"asset_id": "a" * 64, "record_id": "b" * 64, "scope": "artists"}
        ],
    )
    status, result = server.handle_generate(payload, paths=paths, renderer=local)
    assert status == 200, result
    assert result["workflow_run"]["status"] == "completed"
    for provider, operation, _, request in calls:
        prompt = request["input"] if isinstance(request, dict) else request.prompt
        if provider == "local":
            assert prompt == "(@alpha, @beta:0.9), portrait"
        else:
            assert prompt.startswith("0.9::artist:alpha, artist:beta")
    manifests = [read_manifest(path) for path in paths.manifest_root.glob("*.json")]
    assert len(manifests) == 3
    assert all(m["authoring_request"]["prompt"] == payload["prompt"] for m in manifests)
    assert all(
        m["generation_sources"] == payload["generation_sources"] for m in manifests
    )


def test_local_detail_operation_never_samples_full_canvas(tmp_path, monkeypatch):
    import sys
    from anima_app.runtime import comfy_t2i as runtime, face_detailer

    paths = AppPaths(project_root=tmp_path)
    source = paths.input_root / "references" / "source.png"
    source.parent.mkdir(parents=True)
    Image.new("RGB", (512, 512), "red").save(source)
    original = source.read_bytes()
    comfy = ModuleType("comfy")
    comfy.__path__ = []
    for name in ("sd", "sample", "utils"):
        module = ModuleType(f"comfy.{name}")
        setattr(comfy, name, module)
        monkeypatch.setitem(sys.modules, f"comfy.{name}", module)
    comfy.sd.load_diffusion_model = lambda *a, **kw: object()
    comfy.sd.load_clip = lambda **kw: object()
    comfy.sd.CLIPType = SimpleNamespace(QWEN_IMAGE=1)
    comfy.sd.VAE = lambda **kw: object()
    comfy.utils.load_torch_file = lambda *a: {}
    monkeypatch.setitem(sys.modules, "comfy", comfy)
    monkeypatch.setitem(
        sys.modules, "folder_paths", SimpleNamespace(get_folder_paths=lambda *a: [])
    )
    for name in (
        "configure_default_cuda_device",
        "_require_model_files",
        "bootstrap_comfy_runtime",
    ):
        monkeypatch.setattr(runtime, name, lambda *a: None)
    monkeypatch.setattr(runtime, "_encode_prompt", lambda *a: None)
    monkeypatch.setattr(runtime, "_apply_loras", lambda m, c, loras: (m, c, []))
    for model_path in vars(runtime.model_paths_for_request(T2IRequest(prompt="test"), paths)).values():
        model_path.parent.mkdir(parents=True, exist_ok=True)
        model_path.write_bytes(b"mock weight")
    from anima_app.runtime import model_cache
    model_cache.clear()

    def forbidden(*a, **kw):
        raise AssertionError("Full-canvas sampling must not run for detail-only")

    monkeypatch.setattr(runtime, "_sample_latent", forbidden)
    monkeypatch.setattr(runtime, "_make_initial_latent", forbidden)
    monkeypatch.setattr(runtime, "_decode_samples", forbidden)

    def detail(path, **kw):
        assert Image.open(path).getpixel((100, 100)) == (255, 0, 0)
        return SimpleNamespace(
            output_path=path,
            metadata={"status": "skipped", "reason": "no_targets"},
            warnings=(),
        )

    monkeypatch.setattr(face_detailer, "run_face_detailer", detail)
    request = T2IRequest(
        prompt="portrait",
        width=512,
        height=512,
        operation="detail",
        i2i=I2ISettings(
            enabled=True, image_path=source.relative_to(tmp_path).as_posix()
        ),
        face_detailer=FaceDetailerSettings(enabled=True),
    )
    try:
        result = runtime.render_t2i(request, paths)
    finally:
        model_cache.clear()
    assert source.read_bytes() == original
    assert result.output_path != source
    assert result.stages["base_t2i"]["status"] == "skipped"

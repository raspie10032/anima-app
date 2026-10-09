import base64
import io
import json
import zipfile
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from anima_app import server
from anima_app.config import AppPaths
from anima_app.providers import novelai
from anima_app.providers.novelai.inpaint import read_inputs
from anima_app.providers.novelai.metadata import normalize_metadata
from anima_app.providers.novelai.metadata import read_image_metadata


def fixture_request(tmp_path, **values):
    root = tmp_path / "inputs/references"
    root.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (64, 64), "green").save(root / "source.png")
    mask = Image.new("L", (64, 64), 0)
    ImageDraw.Draw(mask).rectangle((16, 16, 47, 47), fill=255)
    mask.save(root / "mask.png")
    return {"provider": "novelai", "operation": "infill", "nai_model": "nai-diffusion-5-full-inpainting",
            "prompt": "a flower", "negative_prompt": "", "width": 64, "height": 64, "seed": 0,
            "input_image": "inputs/references/source.png", "mask_image": "inputs/references/mask.png",
            "nai_limit_opus_free": False, **values}


@pytest.mark.parametrize("values", [
    {"nai_limit_opus_free": True}, {"nai_model": "nai-diffusion-5-full"},
    {"input_image": ""}, {"mask_image": ""}, {"inpaint_strength": float("nan")},
    {"inpaint_strength": True}, {"inpaint_strength": -0.1}, {"operation": "unknown"},
    {"operation": "generate"}, {"nai_model": "nai-diffusion-3-inpainting", "inpaint_strength": 0.5},
])
def test_invalid_or_capped_inpaint_rejected_before_inputs_or_transport(tmp_path, monkeypatch, values):
    monkeypatch.setattr(novelai, "generate", lambda *a, **k: pytest.fail("transport called"))
    payload = fixture_request(tmp_path, **values)
    status, result = server.handle_generate(payload, paths=AppPaths(tmp_path))
    assert status == 400
    assert result["error_code"] == "generation_invalid_request"


@pytest.mark.parametrize("case", ["outside", "traversal", "symlink", "empty", "mismatch", "missing"])
def test_queue_rejects_invalid_images_before_enqueue(tmp_path, monkeypatch, case):
    from test_novelai_integration import make_queue

    payload = fixture_request(tmp_path)
    if case == "outside":
        payload["input_image"] = str(tmp_path / "inputs/references/source.png")
    elif case == "traversal":
        payload["mask_image"] = "inputs/references/../../source.png"
    elif case == "symlink":
        (tmp_path / "inputs/references/link.png").symlink_to(tmp_path / "inputs/references/source.png")
        payload["input_image"] = "inputs/references/link.png"
    elif case == "empty":
        Image.new("L", (64, 64), 0).save(tmp_path / "inputs/references/mask.png")
    elif case == "mismatch":
        Image.new("L", (128, 64), 255).save(tmp_path / "inputs/references/mask.png")
    else:
        payload["mask_image"] = "inputs/references/missing.png"
    monkeypatch.setattr(novelai, "generate", lambda *a, **k: pytest.fail("transport called"))
    queue = make_queue(tmp_path, dry_run=True)
    try:
        status, response = queue.enqueue({"request": payload})
        assert status == 400
        assert response["error_code"] == "generation_invalid_request"
        assert queue.list()["items"] == []
    finally:
        queue.close()


def test_inpaint_mock_transport_composites_and_preserves_original_response(tmp_path, monkeypatch):
    from test_novelai_integration import make_queue, wait_terminal

    monkeypatch.setenv("NAI_ACCESS_TOKEN", "synthetic-inpaint-secret")
    captured = []
    raw = io.BytesIO()
    Image.new("RGB", (64, 64), "purple").save(raw, format="PNG")
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as zipped:
        zipped.writestr("image.png", raw.getvalue())

    def transport(url, headers, body, timeout):
        captured.append(json.loads(body))
        return archive.getvalue()

    monkeypatch.setattr(novelai.client, "_requests_transport", transport)
    queue = make_queue(tmp_path)
    payload = fixture_request(tmp_path, inpaint_strength=0)
    try:
        status, batch = queue.enqueue({"request": payload})
        assert status == 202
        job = wait_terminal(queue, batch["jobs"][0]["id"])
        assert job["status"] == "completed", job
        assert len(captured) == 1
        submitted = captured[0]
        assert submitted["action"] == "infill"
        assert submitted["model"] == payload["nai_model"]
        assert submitted["parameters"]["img2img"] == {"strength": 0, "color_correct": True}
        assert submitted["parameters"]["seed"] == 0
        with Image.open(io.BytesIO(base64.b64decode(submitted["parameters"]["mask"]))) as mask:
            assert mask.getpixel((0, 0)) == 0
            assert mask.getpixel((32, 32)) == 255
        manifest = json.loads((tmp_path / "outputs/manifests" / job["result"]["manifest_name"]).read_text())
        with Image.open(manifest["output_path"]) as image:
            assert image.getpixel((0, 0)) == (0, 128, 0)
            assert image.getpixel((32, 32)) == (128, 0, 128)
            assert image.info["Software"] == "Anima APP"
            assert "Signature" not in image.info
        imported = read_image_metadata(Path(manifest["output_path"]))
        assert imported["request"]["nai_model"] == payload["nai_model"]
        assert imported["request"]["inpaint_strength"] == 0
        assert imported["request"]["operation"] == "infill"
        assert any("마스크 합성" in warning for warning in imported["warnings"])
        assert manifest["novelai"]["inpaint"]["outside_mask_preserved"]
        assert manifest["novelai"]["png_sha256"] != manifest["novelai"]["remote_png_sha256"]
        assert Path(manifest["variants"]["remote_inpaint"]).read_bytes() == raw.getvalue()
        assert "synthetic-inpaint-secret" not in json.dumps(manifest)
        assert "image" not in manifest["novelai"]["effective"]
        status, preset = server.handle_preset_save({"name": "inpaint", "request": payload}, paths=AppPaths(tmp_path))
        assert status == 200
        assert preset["request"]["operation"] == "infill"
        assert preset["request"]["inpaint_strength"] == 0
    finally:
        queue.close()


def test_inpaint_dry_run_has_provenance_and_never_encodes_or_sends(tmp_path, monkeypatch):
    import anima_app.providers.novelai.service as service

    payload = fixture_request(tmp_path, dry_run=True)
    monkeypatch.delenv("NAI_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("NAI_API_TOKEN", raising=False)
    monkeypatch.setattr(service, "encode_png", lambda *a: pytest.fail("image encoded"))
    monkeypatch.setattr(service, "post_json", lambda *a, **k: pytest.fail("transport called"))
    status, result = server.handle_generate(payload, paths=AppPaths(tmp_path))
    assert status == 200
    manifest = json.loads((tmp_path / "outputs/manifests" / result["manifest_name"]).read_text())
    assert manifest["novelai"]["action"] == "infill"
    assert len(manifest["novelai"]["inpaint"]["input_sha256"]) == 64
    assert manifest["output_path"] is None


def test_transparent_mask_pixels_are_preserved(tmp_path):
    payload = fixture_request(tmp_path)
    mask = Image.new("RGBA", (64, 64), (255, 255, 255, 0))
    ImageDraw.Draw(mask).rectangle((16, 16, 47, 47), fill=(255, 255, 255, 255))
    mask.save(tmp_path / payload["mask_image"])
    _, converted, _ = read_inputs(novelai.request_from_payload(payload), AppPaths(tmp_path))
    assert converted.getpixel((0, 0)) == 0
    assert converted.getpixel((32, 32)) == 255


def test_source_orientation_matches_browser_display_before_mask_compositing(tmp_path):
    payload = fixture_request(tmp_path)
    source = Image.new("RGB", (64, 64), "green")
    source.putpixel((0, 0), (255, 0, 0))
    exif = Image.Exif()
    exif[274] = 3  # Browser displays a 180-degree rotation without changing dimensions.
    source.save(tmp_path / payload["input_image"], exif=exif)
    normalized, _, _ = read_inputs(novelai.request_from_payload(payload), AppPaths(tmp_path))
    assert normalized.getpixel((63, 63)) == (255, 0, 0)
    assert normalized.getpixel((0, 0)) == (0, 128, 0)


@pytest.mark.parametrize("strength", [0, 0.65, 1])
def test_metadata_restores_dedicated_model_and_strength_without_inputs_or_cost_override(strength):
    result = normalize_metadata({"Software": "NovelAI", "Comment": {
        "prompt": "a flower", "model": "nai-diffusion-4-curated-inpainting",
        "request_type": "NativeInfillingRequest", "img2img": {"strength": strength}}})
    request = result["request"]
    assert request["operation"] == "infill"
    assert request["nai_model"] == "nai-diffusion-4-curated-inpainting"
    assert request["inpaint_strength"] == strength
    assert request["input_image"] == request["mask_image"] == ""
    assert "nai_limit_opus_free" not in request

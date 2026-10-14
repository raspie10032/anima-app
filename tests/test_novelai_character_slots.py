import io
import json
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image
from PIL.PngImagePlugin import PngInfo

from anima_app import server
from anima_app.config import AppPaths
from anima_app.providers.novelai import detailer, service
from anima_app.providers.novelai.images import with_character_slots
from anima_app.providers.novelai.metadata import normalize_metadata, read_image_metadata
from anima_app.providers.novelai.models import MODEL_IDS, SUPPORTED_INPAINT_MODEL_IDS, character_limit
from anima_app.providers.novelai.payloads import build_payload
from anima_app.providers.novelai.requests import NovelAIRequest, request_from_payload
from test_novelai_detailer import assets, regions  # noqa: F401
from test_novelai_integration import make_queue, wait_terminal
from test_novelai_metadata import _metadata, _stealth_bytes


def slots(count=22):
    return [{"prompt": f"character {i + 1}", "negative_prompt": f"negative {i + 1}",
             "x": i / 21, "y": 0, "enabled": True, "collapsed": i % 2 == 0} for i in range(count)]


def request(model, **kwargs):
    values = {"prompt": "scene", "model": model, "width": 64, "height": 64, "seed": 0}
    if model in SUPPORTED_INPAINT_MODEL_IDS:
        values.update(operation="infill", input_image="inputs/references/a.png",
                      mask_image="inputs/references/m.png", limit_opus_free=False)
    return NovelAIRequest(**{**values, **kwargs})


@pytest.mark.parametrize("model", sorted(MODEL_IDS | SUPPORTED_INPAINT_MODEL_IDS))
def test_each_model_exact_limit_and_overflow(model):
    limit = 22 if model.startswith("nai-diffusion-5") else 6 if model.startswith("nai-diffusion-4") else 0
    req = request(model, characters=[{}] * limit)
    assert character_limit(model) == limit
    effective, wire = build_payload(req)
    assert request_from_payload(effective.to_payload()) == effective
    if limit:
        assert len(wire["parameters"]["v4_prompt"]["caption"]["char_captions"]) == limit
    with pytest.raises(ValueError):
        request(model, characters=[{}] * (limit + 1))


@pytest.mark.parametrize("count,disabled,expected", [(22, [], 22), (6, [], 6), (22, list(range(16)), 6), (0, [], 0)])
def test_hidden_disabled_and_collapsed_slots_round_trip(count, disabled, expected):
    saved = slots()
    for i in disabled:
        saved[i]["enabled"] = False
    req = request("nai-diffusion-5-full", character_slots=saved, character_count=count)
    effective, wire = build_payload(req)
    assert len(effective.characters) == expected
    assert request_from_payload(effective.to_payload()) == effective
    assert effective.character_slots == tuple(saved)
    assert len(wire["parameters"]["v4_prompt"]["caption"]["char_captions"]) == expected
    assert "character_slots" not in json.dumps(wire) and "collapsed" not in json.dumps(wire)
    assert effective.active_character_slots == [i + 1 for i in range(count) if i not in disabled]
    saved[-1]["prompt"] = "outside mutation"
    assert effective.character_slots[-1]["prompt"] == "character 22"


@pytest.mark.parametrize("changes", [
    {"nai_character_count": True}, {"nai_character_count": 1.5}, {"nai_character_count": -1},
    {"nai_character_count": 23}, {"nai_character_count": "2"}, {"nai_character_slots": [{}] * 23},
    {"nai_character_slots": [{"enabled": "false"}]}, {"nai_character_slots": [{"collapsed": 0}]},
    {"nai_character_slots": [{"enabled": False, "x": float("nan")}]},
    {"nai_character_slots": [{"token": "never-store"}]}, {"nai_characters": []},
    {"nai_characters": [{"prompt": "different"}]}, {"nai_character_slots": None, "nai_character_count": 1},
])
def test_invalid_slots_rejected_before_provider(tmp_path, monkeypatch, changes):
    monkeypatch.setattr(server.novelai, "generate", lambda *a, **k: pytest.fail("provider reached"))
    payload = {"provider": "novelai", "prompt": "scene", "nai_character_slots": slots(), **changes}
    status, _ = server.handle_generate(payload, paths=AppPaths(tmp_path))
    assert status == 400


def test_fallback_limit_checked_before_token_or_inputs(tmp_path, monkeypatch):
    monkeypatch.setattr(service, "get_token", lambda: pytest.fail("token read"))
    status, result = server.handle_generate({"provider": "novelai", "prompt": "scene", "operation": "infill",
        "nai_model": "nai-diffusion-4-5-curated-inpainting", "nai_characters": [{}] * 7,
        "input_image": "missing", "mask_image": "missing", "nai_limit_opus_free": False}, paths=AppPaths(tmp_path))
    assert status == 400 and result["error_code"] == "generation_invalid_request"
    with pytest.raises(ValueError, match="6 active"):
        request("nai-diffusion-4-5-curated-inpainting", characters=[{}] * 7)


def test_medium_slots_keep_requested_negatives_and_effective_round_trip():
    req = request("nai-diffusion-5-full-medium", character_slots=slots(), character_count=6)
    effective, wire = build_payload(req)
    assert effective.characters[0]["negative_prompt"] == ""
    assert req.character_slots[0]["negative_prompt"] == "negative 1"
    assert effective.character_slots[6]["negative_prompt"] == "negative 7"
    assert request_from_payload(effective.to_payload()) == effective
    assert all(not c["char_caption"] for c in wire["parameters"]["v4_negative_prompt"]["caption"]["char_captions"])


def test_native_metadata_22_and_model_excess_preserved_for_correction():
    _, wire = build_payload(request("nai-diffusion-5-full", characters=[{}] * 22))
    parsed = normalize_metadata({"Software": "NovelAI", "Comment": {"model": "nai-diffusion-5-full", **wire["parameters"]}})
    assert len(parsed["request"]["nai_characters"]) == 22
    parsed = normalize_metadata({"Software": "NovelAI", "Comment": {"model": "nai-diffusion-4-full", **wire["parameters"]}})
    assert len(parsed["request"]["nai_characters"]) == 22
    assert any("6명" in w for w in parsed["warnings"])


def test_alpha_metadata_retains_added_editor_state_and_pixels(tmp_path):
    original = _stealth_bytes(_metadata())
    saved = slots()
    saved[1]["enabled"] = False
    annotated = with_character_slots(original, saved, 4)
    assert annotated[:-12].startswith(original[:-12])
    with Image.open(io.BytesIO(original)) as a, Image.open(io.BytesIO(annotated)) as b:
        assert a.tobytes() == b.tobytes()
    path = tmp_path / "saved.png"
    path.write_bytes(annotated)
    parsed = read_image_metadata(path)
    assert parsed["metadata_source"] == "alpha"
    assert parsed["request"]["nai_character_slots"] == saved
    assert len(parsed["request"]["nai_characters"]) == 3


def test_slot_metadata_size_rejected_before_generation():
    saved = slots()
    for item in saved:
        item["prompt"] = item["negative_prompt"] = "가" * 32768
    with pytest.raises(ValueError, match="1 MiB"):
        request("nai-diffusion-5-full", character_slots=saved)


def test_invalid_editor_metadata_does_not_drop_valid_native_characters():
    _, wire = build_payload(request("nai-diffusion-5-full", characters=[{"prompt": "native"}]))
    parsed = normalize_metadata({"Software": "NovelAI", "Comment": {"model": "nai-diffusion-5-full", **wire["parameters"]},
                                 "anima_app_character_slots": {"slots": [{"token": "not-allowed"}], "count": 1}})
    assert "nai_character_slots" not in parsed["request"]
    assert parsed["request"]["nai_characters"][0]["prompt"] == "native"
    assert "not-allowed" not in json.dumps(parsed)


@pytest.mark.parametrize("operation", ["generate", "img2img", "infill", "focused_infill", "detail"])
def test_all_operations_preserve_saved_slots_and_output_pixels(tmp_path, monkeypatch, assets, operation):  # noqa: F811
    sent, saved = [], slots()
    for s in saved[:-1]:
        s["enabled"] = False

    def transport(url, headers, body, timeout):
        wire = json.loads(body)
        sent.append(wire)
        png, archive = io.BytesIO(), io.BytesIO()
        info = PngInfo()
        info.add_text("Software", "NovelAI")
        info.add_itxt("Comment", json.dumps({"model": wire["model"], **wire["parameters"]}))
        params = wire["parameters"]
        Image.new("RGB", (params["width"], params["height"]), "purple").save(png, format="PNG", pnginfo=info)
        with zipfile.ZipFile(archive, "w") as z:
            z.writestr("image.png", png.getvalue())
        return archive.getvalue()

    from anima_app.providers import novelai
    monkeypatch.setattr(novelai.client, "_requests_transport", transport)
    monkeypatch.setattr(detailer.Detector, "detect", lambda self, image, cancelled: regions(image))
    payload = {**assets, "operation": operation, "nai_model": "nai-diffusion-5-full-medium",
               "nai_character_slots": saved, "nai_character_count": 22}
    if operation in {"infill", "focused_infill"}:
        payload.update(nai_model="nai-diffusion-5-full-medium-inpainting", mask_image="inputs/references/mask.png")
    if operation == "generate":
        payload["input_image"] = ""  # generate + automatic detailer
    if operation in {"img2img", "infill"}:
        payload.update(nai_limit_opus_free=False, nai_detailer={"enabled": False})
    status, result = server.handle_generate(payload, paths=AppPaths(tmp_path))
    assert status == 200, result
    manifest = json.loads(Path(result["manifest_path"]).read_text())
    assert read_image_metadata(Path(manifest["output_path"]))["request"]["nai_character_slots"] == saved
    with Image.open(manifest["output_path"]) as a, Image.open(manifest["variants"]["without_character_slots"]) as b:
        assert a.mode == b.mode and a.size == b.size and a.tobytes() == b.tobytes()
    if operation in {"generate", "detail", "focused_infill"}:
        assert manifest["novelai"]["detailer"][0]["character_slot"] == 22
        assert all(not p["parameters"]["v4_prompt"]["caption"]["char_captions"] for p in sent if p["action"] == "infill")
    else:
        assert len(sent[0]["parameters"]["v4_prompt"]["caption"]["char_captions"]) == 1


def test_queue_preset_wildcards_and_png_saved_state(tmp_path, monkeypatch):
    monkeypatch.setenv("NAI_ACCESS_TOKEN", "synthetic")
    paths, sent = AppPaths(tmp_path), []
    paths.wildcard_root.mkdir(parents=True)
    (paths.wildcard_root / "hair.txt").write_text("silver hair\n")
    saved = slots()
    saved[0]["prompt"], saved[1]["enabled"] = "__hair__", False
    saved[10]["prompt"] = "__missing_hidden__"
    raw = []

    def post(url, **kwargs):
        wire = kwargs["payload"]
        sent.append(wire)
        png, archive = io.BytesIO(), io.BytesIO()
        info = PngInfo()
        info.add_text("Software", "NovelAI")
        info.add_itxt("Comment", json.dumps({"model": wire["model"], "request_type": "PromptGenerateRequest", **wire["parameters"]}))
        Image.new("RGB", (64, 64), "blue").save(png, format="PNG", pnginfo=info)
        raw.append(png.getvalue())
        with zipfile.ZipFile(archive, "w") as z:
            z.writestr("image.png", png.getvalue())
        return archive.getvalue()

    monkeypatch.setattr(service, "get_token", lambda: "synthetic")
    monkeypatch.setattr(service, "post_json", post)
    payload = {"provider": "novelai", "prompt": "scene", "width": 64, "height": 64, "seed": 0,
               "nai_character_slots": saved, "nai_character_count": 6, "nai_model": "nai-diffusion-5-full-medium"}
    assert server.handle_preset_save({"name": "slots", "request": payload}, paths=paths)[0] == 200
    assert server.handle_presets(paths=paths)["items"][0]["request"]["nai_character_slots"] == saved
    queue = make_queue(tmp_path)
    try:
        status, batch = queue.enqueue({"request": payload})
        assert status == 202
        job = wait_terminal(queue, batch["jobs"][0]["id"])
        assert job["status"] == "completed", job
        manifest = json.loads(Path(job["result"]["manifest_path"]).read_text())
        assert len(sent) == 1
        assert manifest["characters"][0]["prompt"] == "silver hair"
        parsed = read_image_metadata(Path(manifest["output_path"]))
        assert parsed["request"]["nai_character_slots"] == saved
        assert parsed["request"]["nai_character_count"] == 6
        assert manifest["novelai"]["effective"]["nai_character_slots"][0]["negative_prompt"] == ""
        assert manifest["novelai"]["requested"]["nai_character_slots"][0]["negative_prompt"] == "negative 1"
        assert Path(manifest["variants"]["without_character_slots"]).read_bytes() == raw[0]
        assert len(sent[0]["parameters"]["v4_prompt"]["caption"]["char_captions"]) == 5
    finally:
        queue.close()


def test_matching_keeps_slot22_identity_after_disabled_slots():
    saved = slots()
    for s in saved[:-1]:
        s["enabled"] = False
    saved[-1]["prompt"] = "red hair"
    req = request("nai-diffusion-5-full", character_slots=saved, detailer={"enabled": True, "matching": "wd14"})
    source = Image.new("RGB", (64, 64))
    mask = Image.new("L", source.size, 255)
    region = detailer.Region((10, 10, 20, 20), mask, "face")
    tagger = SimpleNamespace(score=lambda images: [{"red_hair": .99} for _ in images])
    _, matches, chars, report = detailer.plan(source, [region], req, tagger)
    assert matches[0].character_index == 0
    assert report[0]["character"] == 1 and report[0]["character_slot"] == 22
    assert chars[0].prompt == "red hair"

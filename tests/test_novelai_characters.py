import http.client
import io
import json
import threading

import pytest
from PIL import Image

from anima_app import server
from anima_app.config import AppPaths
from anima_app.providers.novelai.converters import convert_prompt
from anima_app.providers.novelai.eligibility import validate_opus_free_payload
from anima_app.providers.novelai.inpaint import composite_png
from anima_app.providers.novelai.metadata import normalize_metadata, read_image_metadata
from anima_app.providers.novelai.payloads import build_payload
from anima_app.providers.novelai.requests import NovelAIRequest, request_from_payload


CHARACTERS = [{"prompt": "silver hair", "negative_prompt": "red hair", "x": 0, "y": 1},
              {"prompt": "black hair", "negative_prompt": "", "x": 1, "y": 0}]


@pytest.mark.parametrize("model", ["nai-diffusion-4-full", "nai-diffusion-4-5-curated", "nai-diffusion-5-curated"])
@pytest.mark.parametrize("coords", [True, False])
def test_characters_payload_and_request_roundtrip(model, coords):
    request = NovelAIRequest(prompt="two adults", model=model, characters=CHARACTERS, use_coords=coords, use_order=False, seed=0)
    assert request_from_payload(request.to_payload()) == request
    effective, payload = build_payload(request)
    assert effective.characters == tuple(CHARACTERS)
    pos, neg = payload["parameters"]["v4_prompt"], payload["parameters"]["v4_negative_prompt"]
    assert pos["use_coords"] is coords and pos["use_order"] is False
    assert neg["use_coords"] is False and neg["use_order"] is False
    assert pos["caption"]["char_captions"] == [
        {"char_caption": "silver hair", "centers": [{"x": 0, "y": 1}]},
        {"char_caption": "black hair", "centers": [{"x": 1, "y": 0}]}]
    assert [c["char_caption"] for c in neg["caption"]["char_captions"]] == ["red hair", ""]
    validate_opus_free_payload(payload)
    result = normalize_metadata({"Software": "NovelAI", "Comment": {"model": model, **payload["parameters"]}})
    assert result["request"]["nai_characters"] == CHARACTERS
    assert result["request"]["nai_use_coords"] is coords
    assert result["request"]["nai_use_order"] is False


@pytest.mark.parametrize("characters", [None, {}, "x", [{}] * 6, ["x"], [{"x": True}], [{"x": -0.1}],
    [{"y": 1.01}], [{"x": float("nan")}], [{"y": float("inf")}], [{"x": "0"}],
    [{"prompt": 7}], [{"negative_prompt": []}], [{"prompt": "x" * 32769}], [{"image": "ref"}]])
def test_invalid_characters_rejected_before_provider(tmp_path, monkeypatch, characters):
    monkeypatch.setattr(server.novelai, "generate", lambda *a, **k: pytest.fail("provider reached"))
    status, _ = server.handle_generate({"provider": "novelai", "prompt": "adults", "nai_characters": characters}, paths=AppPaths(tmp_path))
    assert status == 400


@pytest.mark.parametrize("values", [{"nai_model": "nai-diffusion-3"}, {"nai_use_coords": 1}, {"nai_use_order": "true"},
    {"nai_characters": [{"token": "secret"}]}])
def test_unsupported_character_settings_fail_closed(values):
    with pytest.raises(ValueError):
        request_from_payload({"prompt": "adults", "nai_characters": CHARACTERS, **values})


def test_five_characters_and_isolated_data():
    original = CHARACTERS * 2 + [{}]
    request = NovelAIRequest(prompt="five adults", characters=original)
    original[0] = {"prompt": "changed"}
    assert len(build_payload(request)[1]["parameters"]["v4_prompt"]["caption"]["char_captions"]) == 5
    assert request.characters[0]["prompt"] == "silver hair"


def test_inpaint_composite_character_metadata(tmp_path):
    request = NovelAIRequest(prompt="two adults", model="nai-diffusion-5-full-inpainting", operation="infill",
        input_image="inputs/references/source.png", mask_image="inputs/references/mask.png", limit_opus_free=False,
        width=64, height=64, characters=CHARACTERS, use_coords=False, use_order=False, seed=0)
    image = Image.new("RGB", (64, 64), "red")
    png = io.BytesIO()
    image.save(png, format="PNG")
    path = tmp_path / "composite.png"
    path.write_bytes(composite_png(png.getvalue(), image, Image.new("L", image.size, 255), request))
    result = read_image_metadata(path)
    assert result["request"]["nai_characters"] == CHARACTERS
    assert result["request"]["nai_model"] == request.model
    assert result["request"]["operation"] == "infill"


@pytest.mark.parametrize("mutator", [
    lambda block: block["caption"].update(char_captions=[{}] * 6),
    lambda block: block["caption"]["char_captions"][0].update(centers=[{"x": 0, "y": 0}, {"x": 1, "y": 1}]),
    lambda block: block.update(use_coords="yes"),
    lambda block: block["caption"]["char_captions"][0].update(centers=[{"x": -1, "y": 0}]),
])
def test_metadata_does_not_partially_import_layout(mutator):
    _, payload = build_payload(NovelAIRequest(prompt="adults", characters=CHARACTERS))
    mutator(payload["parameters"]["v4_prompt"])
    result = normalize_metadata({"Software": "NovelAI", "Comment": {"model": payload["model"], **payload["parameters"]}})
    assert result["request"]["nai_characters"] == []
    assert any("캐릭터" in notice for notice in result["unsupported"])


def test_character_wildcards_and_preset_manifest(tmp_path):
    paths = AppPaths(tmp_path)
    paths.wildcard_root.mkdir(parents=True)
    (paths.wildcard_root / "hair.txt").write_text("silver hair\n")
    characters = [{"prompt": "__hair__", "negative_prompt": "", "x": 0, "y": 1}]
    request = {"provider": "novelai", "prompt": "adults", "seed": 0, "nai_characters": characters, "dry_run": True}
    status, saved = server.handle_preset_save({"name": "characters", "request": request}, paths=paths)
    assert status == 200
    assert server.handle_presets(paths=paths)["items"][0]["request"]["nai_characters"] == characters
    status, result = server.handle_generate(request, paths=paths)
    assert status == 200
    manifest = json.loads((paths.manifest_root / result["manifest_name"]).read_text())
    assert manifest["characters"][0]["prompt"] == "silver hair"
    assert manifest["wildcards"]["characters"][0]["original"] == characters[0]
    assert manifest["wildcards"]["enabled"] is True


@pytest.mark.parametrize("source,target,text,expected", [
    ("comfyui", "naiv4", "(silver hair:1.05), artist:test", "1.05::silver hair ::, artist:test"),
    ("naiv4", "comfyui", "-1.5::silver hair ::, artist:test", "(silver hair:-1.5), artist:test"),
    ("naiv4", "oldnai", "1.05::silver hair ::, 0::cat ::", "{silver hair}, [cat]"),
    ("oldnai", "naiv4", "{silver hair}, [cat]", "1.05::silver hair ::, 0.95::cat ::"),
    ("comfyui", "oldnai", "(silver hair:1.05), cat", "{silver hair}, cat"),
    ("oldnai", "comfyui", "{silver hair}, [cat]", "(silver hair:1.05), (cat:0.95)"),
    ("comfyui", "naiv4", r"fate\(series\), ((hair))", "fate(series), 1.21::hair ::"),
    ("naiv4", "comfyui", "1.2::silver hair, blue eyes ::, coat", "(silver hair:1.2), (blue eyes:1.2), coat"),
])
def test_six_conversions_and_node_semantics(source, target, text, expected):
    result = convert_prompt({"source": source, "target": target, "text": text})
    assert result["original"] == text and result["converted"] == expected
    if target == "oldnai":
        assert result["warnings"]


@pytest.mark.parametrize("payload", [
    {"source": "bad", "target": "naiv4", "text": "a"},
    {"source": "comfyui", "target": "comfyui", "text": "a"},
    {"source": "comfyui", "target": "naiv4", "text": "a" * 32769},
    {"source": "comfyui", "target": "naiv4", "text": "(" * 65 + "a" + ")" * 65},
    {"source": [], "target": "naiv4", "text": "a"},
    {"source": "comfyui", "target": "naiv4", "text": None},
    {"source": "comfyui", "target": "naiv4", "text": "a", "token": "secret"},
    {"source": "comfyui", "target": "naiv4", "text": "a", "unexpected": "field"},
])
def test_converter_invalid_inputs(payload):
    with pytest.raises(ValueError):
        convert_prompt(payload)


def test_converter_http_contract_and_trusted_origin(tmp_path, monkeypatch):
    monkeypatch.setattr(server.novelai, "generate", lambda *a, **k: pytest.fail("provider reached"))
    http_server = server.create_http_server("127.0.0.1", 0, paths=AppPaths(tmp_path), default_dry_run=True)
    threading.Thread(target=http_server.serve_forever, daemon=True).start()
    try:
        client = http.client.HTTPConnection(*http_server.server_address)
        payload = json.dumps({"source": "comfyui", "target": "naiv4", "text": "(hair:1.05)"})
        client.request("POST", "/api/prompts/convert", payload, {"Content-Type": "application/json"})
        response = client.getresponse()
        assert response.status == 200 and json.loads(response.read())["converted"] == "1.05::hair ::"
        client.request("POST", "/api/prompts/convert", payload, {"Content-Type": "application/json", "Origin": "https://untrusted.invalid"})
        response = client.getresponse()
        assert response.status == 403
        response.read()
        client.close()
    finally:
        http_server.shutdown()
        http_server.server_close()

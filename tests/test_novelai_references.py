import base64
import io
import json

import pytest
from PIL import Image

from anima_app import server
from anima_app.config import AppPaths
from anima_app.providers import novelai
from anima_app.providers.novelai.references import ENCODE_VIBE_URL
from test_novelai_integration import png_archive


@pytest.fixture
def reference_request(tmp_path, monkeypatch):
    monkeypatch.setenv("NAI_ACCESS_TOKEN", "synthetic-reference-secret")
    monkeypatch.setattr(novelai.client, "REQUEST_INTERVAL_SECONDS", 0)
    root = tmp_path / "inputs/references"
    root.mkdir(parents=True)
    Image.new("RGBA", (64, 128), (0, 255, 0, 0)).save(root / "ref.png")
    return {"provider": "novelai", "prompt": "flower", "width": 64, "height": 64,
            "nai_model": "nai-diffusion-4-5-full", "nai_limit_opus_free": False}, {"image": "inputs/references/ref.png"}


@pytest.mark.parametrize("changes,kind", [
    ({"nai_limit_opus_free": True}, "vibes"), ({"nai_limit_opus_free": True}, "references"),
    ({"nai_model": "nai-diffusion-5-full"}, "vibes"), ({"nai_model": "nai-diffusion-5-full"}, "references"),
    ({"nai_model": "nai-diffusion-3"}, "references"),
    ({"operation": "infill", "nai_model": "nai-diffusion-4-5-full-inpainting"}, "vibes"),
])
def test_incompatible_rejected_before_encoding_or_token(tmp_path, monkeypatch, reference_request, changes, kind):
    request, entry = reference_request
    monkeypatch.setattr(novelai.service, "get_token", lambda: pytest.fail("token read"))
    status, _ = server.handle_generate({**request, **changes, f"nai_{kind}": [entry]}, paths=AppPaths(tmp_path))
    assert status == 400


@pytest.mark.parametrize("entry", [{"strength": -1}, {"fidelity": 2}, {"fidelity": True},
                                    {"strength": float("nan")}, {"reference_type": "unknown"},
                                    {"image": ""}, {"token": "secret"}, {"fidelity": "1"}])
def test_invalid_precise_entries(reference_request, entry):
    request, ref = reference_request
    with pytest.raises(ValueError):
        novelai.request_from_payload({**request, "nai_references": [{**ref, **entry}]})


def test_mutually_exclusive_and_count(reference_request):
    request, entry = reference_request
    with pytest.raises(ValueError):
        novelai.request_from_payload({**request, "nai_vibes": [entry], "nai_references": [entry]})
    with pytest.raises(ValueError):
        novelai.request_from_payload({**request, "nai_vibes": [entry] * 17})


def test_v4_encoding_cache_normalization_invalidation(tmp_path, monkeypatch, reference_request):
    request, entry = reference_request
    calls = []

    def transport(url, headers, body, timeout):
        payload = json.loads(body)
        calls.append((url, payload))
        if url == ENCODE_VIBE_URL:
            return b"synthetic-binary-encoding"
        assert payload["parameters"]["reference_strength_multiple"] == [.5, .5]
        assert all(base64.b64decode(v) == b"synthetic-binary-encoding" for v in payload["parameters"]["reference_image_multiple"])
        return png_archive()

    monkeypatch.setattr(novelai.client, "_requests_transport", transport)
    payload = {**request, "nai_vibes": [{**entry, "strength": 1}] * 2}
    for _ in range(2):
        status, response = server.handle_generate(payload, paths=AppPaths(tmp_path))
        assert status == 200, response
    assert len([url for url, _ in calls if url == ENCODE_VIBE_URL]) == 1
    payload["nai_vibes"] = [{**entry, "strength": 1, "information_extracted": .5}] * 2
    status, _ = server.handle_generate(payload, paths=AppPaths(tmp_path))
    assert status == 200
    assert len([url for url, _ in calls if url == ENCODE_VIBE_URL]) == 2
    caches = list((tmp_path / "outputs/nai-vibe-cache").glob("*.json"))
    assert len(caches) == 2
    assert all("synthetic-reference-secret" not in p.read_text() for p in caches)


def test_corrupt_cache_does_not_reencode(tmp_path, monkeypatch, reference_request):
    request, entry = reference_request
    calls = []

    def transport(url, *args):
        calls.append(url)
        return b"encoding" if url == ENCODE_VIBE_URL else png_archive()

    monkeypatch.setattr(novelai.client, "_requests_transport", transport)
    payload = {**request, "nai_vibes": [entry]}
    assert server.handle_generate(payload, paths=AppPaths(tmp_path))[0] == 200
    cache = next((tmp_path / "outputs/nai-vibe-cache").glob("*.json"))
    cache.write_text("{}")
    before = len(calls)
    assert server.handle_generate(payload, paths=AppPaths(tmp_path))[0] == 400
    assert len(calls) == before


def test_v3_has_no_encode_request_and_pads(tmp_path, monkeypatch, reference_request):
    request, entry = reference_request

    def transport(url, headers, body, timeout):
        assert url != ENCODE_VIBE_URL
        parameters = json.loads(body)["parameters"]
        assert parameters["reference_information_extracted_multiple"] == [0]
        with Image.open(io.BytesIO(base64.b64decode(parameters["reference_image_multiple"][0]))) as image:
            assert image.size == (448, 448)
            assert image.getpixel((0, 0)) == (0, 0, 0)
        return png_archive()

    monkeypatch.setattr(novelai.client, "_requests_transport", transport)
    assert server.handle_generate({**request, "nai_model": "nai-diffusion-3", "nai_vibes": [{**entry, "information_extracted": 0}]}, paths=AppPaths(tmp_path))[0] == 200


def test_precise_letterbox_types_fidelity_payload_and_manifest(tmp_path, monkeypatch, reference_request):
    request, entry = reference_request

    def transport(url, headers, body, timeout):
        parameters = json.loads(body)["parameters"]
        assert "reference_image_multiple" not in parameters
        assert parameters["director_reference_secondary_strength_values"] == [0, 1]
        assert parameters["director_reference_strength_values"] == [1, .5]
        assert [d["caption"]["base_caption"] for d in parameters["director_reference_descriptions"]] == ["character", "style"]
        with Image.open(io.BytesIO(base64.b64decode(parameters["director_reference_images"][0]))) as image:
            assert image.size == (1024, 1536)
        return png_archive()

    monkeypatch.setattr(novelai.client, "_requests_transport", transport)
    payload = {**request, "nai_references": [entry, {**entry, "reference_type": "style", "fidelity": 0, "strength": .5}]}
    status, response = server.handle_generate(payload, paths=AppPaths(tmp_path))
    assert status == 200, response
    manifest = json.loads(next(AppPaths(tmp_path).manifest_root.glob("*.json")).read_text())
    assert len(manifest["novelai"]["references"]) == 2
    assert manifest["novelai"]["effective"]["nai_references"][1]["fidelity"] == 0
    assert "director_reference_images" not in json.dumps(manifest)


def test_dry_run_validates_paths_without_encoding(tmp_path, monkeypatch, reference_request):
    request, entry = reference_request
    monkeypatch.setattr(novelai.service, "get_token", lambda: pytest.fail("token read"))
    status, _ = server.handle_generate({**request, "nai_vibes": [entry], "dry_run": True}, paths=AppPaths(tmp_path))
    assert status == 200
    status, _ = server.handle_generate({**request, "nai_vibes": [{**entry, "image": "inputs/references/missing.png"}], "dry_run": True}, paths=AppPaths(tmp_path))
    assert status == 400

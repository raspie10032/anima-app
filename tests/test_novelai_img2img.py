import base64
import io
import json

import pytest
from PIL import Image

from anima_app import server
from anima_app.config import AppPaths
from anima_app.providers import novelai
from anima_app.providers.novelai.metadata import normalize_metadata
from test_novelai_integration import make_queue, png_archive, wait_terminal


def payload(tmp_path, **values):
    directory = tmp_path / "inputs/references"
    directory.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (128, 64), "green").save(directory / "input.png")
    return {"provider": "novelai", "operation": "img2img", "prompt": "flower", "width": 64,
            "height": 128, "seed": 0, "img2img_strength": 0, "img2img_noise": 0.2,
            "input_image": "inputs/references/input.png", "nai_limit_opus_free": False, **values}


@pytest.mark.parametrize("values", [
    {"nai_limit_opus_free": True}, {"input_image": ""}, {"mask_image": "inputs/references/input.png"},
    {"img2img_strength": True}, {"img2img_noise": -1}, {"img2img_noise": float("nan")},
    {"img2img_strength": 1.1}, {"img2img_strength": "0.5"}, {"img2img_noise": float("inf")},
])
def test_reject_before_token_or_input(tmp_path, monkeypatch, values):
    monkeypatch.setattr(novelai.service, "get_token", lambda: pytest.fail("token read"))
    status, _ = server.handle_generate(payload(tmp_path, **values), paths=AppPaths(tmp_path))
    assert status == 400


def test_real_queue_mock_payload_and_manifest(tmp_path, monkeypatch):
    monkeypatch.setenv("NAI_ACCESS_TOKEN", "synthetic-img2img-secret")
    calls = []

    def transport(url, headers, body, timeout):
        data = json.loads(body)
        calls.append(data)
        assert data["action"] == "img2img"
        params = data["parameters"]
        assert params["strength"] == params["seed"] == 0
        assert params["noise"] == 0.2 and "mask" not in params
        with Image.open(io.BytesIO(base64.b64decode(params["image"]))) as image:
            assert image.size == (64, 128)
        return png_archive(64, 128)

    monkeypatch.setattr(novelai.client, "_requests_transport", transport)
    queue = make_queue(tmp_path)
    try:
        status, batch = queue.enqueue({"request": payload(tmp_path)})
        assert status == 202
        job = wait_terminal(queue, batch["jobs"][0]["id"])
        assert job["status"] == "completed", job
        manifests = list(AppPaths(tmp_path).manifest_root.glob("*.json"))
        manifest = json.loads(manifests[0].read_text())
        assert manifest["operation"] == "img2img"
        assert manifest["novelai"]["img2img"]["original_size"] == [128, 64]
        assert manifest["novelai"]["effective"]["img2img_strength"] == 0
        assert "synthetic-img2img-secret" not in manifests[0].read_text()
        assert len(calls) == 1
    finally:
        queue.close()


def test_import_img2img_model_and_zero_values():
    result = normalize_metadata({"Software": "NovelAI", "Source": "NovelAI Diffusion V5 DB276663",
                                 "Comment": json.dumps({"prompt": "flower", "request_type": "Img2ImgRequest",
                                                        "strength": 0, "noise": 0})})
    request = result["request"]
    assert request["nai_model"] == "nai-diffusion-5-curated"
    assert request["operation"] == "img2img"
    assert request["img2img_strength"] == request["img2img_noise"] == 0
    assert request["input_image"] == request["mask_image"] == ""

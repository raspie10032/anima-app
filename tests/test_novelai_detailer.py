import base64
import io
import json
import sys
from types import ModuleType
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image, ImageDraw

from anima_app import server
from anima_app.config import AppPaths
from anima_app.providers import novelai
from anima_app.providers.novelai import detailer
from anima_app.providers.novelai.detailer_matching import match_characters, selected_prompts
from anima_app.providers.novelai.eligibility import FocusedContext, validate_opus_free_payload
from anima_app.providers.novelai.errors import NovelAIError
from anima_app.providers.novelai.inpaint import encode_png
from test_novelai_integration import make_queue, png_archive, wait_terminal


@pytest.fixture
def assets(tmp_path, monkeypatch):
    root = tmp_path / "inputs/references"
    root.mkdir(parents=True)
    Image.new("RGB", (256, 128), "green").save(root / "source.png")
    mask = Image.new("L", (256, 128))
    ImageDraw.Draw(mask).rectangle((20, 30, 40, 50), fill=255)
    mask.save(root / "mask.png")
    monkeypatch.setenv("NAI_ACCESS_TOKEN", "synthetic-detailer-secret")
    monkeypatch.setattr(novelai.client, "REQUEST_INTERVAL_SECONDS", 0)
    monkeypatch.setattr(novelai.client, "_request_coordinator", novelai.client.RequestCoordinator())
    monkeypatch.setattr(novelai.client, "_requests_subscription_transport", lambda *_: b'{"active":true,"tier":3,"usage":{"percent":100,"isNegative":false}}')
    monkeypatch.setattr(detailer.Detector, "preflight", lambda _: None)
    return {"provider": "novelai", "prompt": "shared scene", "negative_prompt": "bad composition", "width": 256, "height": 128,
            "seed": 0, "nai_model": "nai-diffusion-4-5-full", "nai_limit_opus_free": True,
            "input_image": "inputs/references/source.png", "operation": "detail",
            "nai_detailer": {"enabled": True, "crop_factor": 2, "padding": 0}}


def regions(source):
    result = []
    for box in ((20, 30, 40, 50), (70, 30, 90, 50)):
        mask = Image.new("L", source.size)
        ImageDraw.Draw(mask).rectangle(box, fill=255)
        result.append(detailer.Region(box, mask))
    return result


def transport_recorder(calls, fail_at=None):
    def transport(url, headers, body, timeout):
        data = json.loads(body)
        calls.append(data)
        if fail_at == len(calls):
            raise TimeoutError("synthetic-detailer-secret")
        parameters = data["parameters"]
        return png_archive(parameters["width"], parameters["height"])
    return transport


def test_focused_mask_only_calls_small_infill_and_preserves_outside(tmp_path, monkeypatch, assets):
    calls = []
    monkeypatch.setattr(novelai.client, "_requests_transport", transport_recorder(calls))
    payload = {**assets, "operation": "focused_infill", "nai_model": "nai-diffusion-4-5-full-inpainting",
               "mask_image": "inputs/references/mask.png", "nai_detailer": {"crop_factor": 1, "padding": 0}}
    status, response = server.handle_generate(payload, paths=AppPaths(tmp_path))
    assert status == 200, response
    assert len(calls) == 1 and calls[0]["action"] == "infill"
    params = calls[0]["parameters"]
    assert max(params["width"], params["height"]) <= 1024
    manifest = json.loads(next(AppPaths(tmp_path).manifest_root.glob("*.json")).read_text())
    item = manifest["novelai"]["detailer"][0]
    assert item["opus_preflight"]["status"] == "verified"
    with Image.open(manifest["output_path"]) as image:
        assert image.getpixel((0, 0)) == (0, 128, 0)
        assert image.getpixel((30, 40)) == (128, 0, 128)
        assert image.info["Software"] == "Anima APP"
    assert "synthetic-detailer-secret" not in json.dumps(manifest)


def test_two_regions_frozen_source_seeds_and_disjoint_masks(tmp_path, monkeypatch, assets):
    calls = []
    monkeypatch.setattr(detailer.Detector, "detect", lambda _, source, cancelled: regions(source))
    monkeypatch.setattr(novelai.client, "_requests_transport", transport_recorder(calls))
    status, response = server.handle_generate(assets, paths=AppPaths(tmp_path))
    assert status == 200, response
    assert [c["parameters"]["seed"] for c in calls] == [0, 1]
    for call in calls:
        with Image.open(io.BytesIO(base64.b64decode(call["parameters"]["image"]))) as image:
            assert image.getpixel((20, 20)) == (0, 128, 0)  # second crop did not receive the first purple result
    manifest = json.loads(next(AppPaths(tmp_path).manifest_root.glob("*.json")).read_text())
    assert len(manifest["novelai"]["detailer"]) == 2
    assert all(r["status"] == "edited" for r in manifest["novelai"]["detailer"])


def test_full_source_focus_blocked_before_transport(tmp_path, monkeypatch, assets):
    Image.new("L", (256, 128), 255).save(tmp_path / "inputs/references/mask.png")
    monkeypatch.setattr(novelai.client, "_requests_transport", lambda *_: pytest.fail("remote called"))
    status, _ = server.handle_generate({**assets, "operation": "focused_infill", "nai_model": "nai-diffusion-4-5-full-inpainting",
                                       "mask_image": "inputs/references/mask.png"}, paths=AppPaths(tmp_path))
    assert status == 400


def test_preview_existing_image_needs_no_token_or_remote(tmp_path, monkeypatch, assets):
    monkeypatch.setattr(detailer.Detector, "detect", lambda _, source, cancelled: regions(source))
    monkeypatch.setattr(novelai.service, "get_token", lambda: pytest.fail("token read"))
    monkeypatch.setattr(novelai.client, "_requests_transport", lambda *_: pytest.fail("remote called"))
    status, response = server.handle_generate({**assets, "nai_detailer": {"enabled": True, "preview_only": True}}, paths=AppPaths(tmp_path))
    assert status == 200, response
    manifest = json.loads(next(AppPaths(tmp_path).manifest_root.glob("*.json")).read_text())
    assert all(r["status"] == "planned" for r in manifest["novelai"]["detailer"])


def test_missing_detector_blocks_before_base_generation(tmp_path, monkeypatch, assets):
    def fail(_):
        raise FileNotFoundError("detectors missing")
    monkeypatch.setattr(detailer.Detector, "preflight", fail)
    monkeypatch.setattr(novelai.service, "get_token", lambda: pytest.fail("token read"))
    payload = {**assets, "operation": "generate", "input_image": ""}
    assert server.handle_generate(payload, paths=AppPaths(tmp_path))[0] == 400


def test_tokenless_preview_works_through_common_queue(tmp_path, monkeypatch, assets):
    monkeypatch.delenv("NAI_ACCESS_TOKEN")
    monkeypatch.delenv("NAI_API_TOKEN", raising=False)
    monkeypatch.setattr(detailer.Detector, "detect", lambda _, source, cancelled: regions(source))
    monkeypatch.setattr(novelai.client, "_requests_transport", lambda *_: pytest.fail("remote called"))
    queue = make_queue(tmp_path)
    try:
        status, batch = queue.enqueue({"request": {**assets, "nai_detailer": {"enabled": True, "preview_only": True}}})
        assert status == 202, batch
        result = wait_terminal(queue, batch["jobs"][0]["id"])
        assert result["status"] == "completed"
        assert result["result"]["status"] == "previewed"
    finally:
        queue.close()


@pytest.mark.parametrize("infinite", [False, True])
def test_partial_detailer_failure_stops_automatic_and_finite_followups(tmp_path, monkeypatch, assets, infinite):
    calls = []
    monkeypatch.setattr(detailer.Detector, "detect", lambda _, source, cancelled: regions(source))
    monkeypatch.setattr(novelai.client, "_requests_transport", transport_recorder(calls, fail_at=2))
    queue = make_queue(tmp_path)
    try:
        status, batch = queue.enqueue({"request": {**assets, "operation": "generate", "input_image": ""},
                                       "count": 3, "infinite": infinite})
        assert status == 202
        result = wait_terminal(queue, batch["jobs"][0]["id"])
        assert result["result"]["stop_scheduling"] and result["result"]["remote_outcome_unknown"]
        jobs = queue.list()["items"]
        assert len(jobs) == (1 if infinite else 3)
        assert all(job["status"] == "cancelled" for job in jobs[1:])
        assert len(calls) == 2
    finally:
        queue.close()


def test_manual_focused_crop_never_changes_black_mask_pixels_even_with_padding(tmp_path, monkeypatch, assets):
    monkeypatch.setattr(novelai.client, "_requests_transport", transport_recorder([]))
    payload = {**assets, "operation": "focused_infill", "nai_model": "nai-diffusion-4-5-full-inpainting",
               "mask_image": "inputs/references/mask.png", "nai_detailer": {"padding": 16}}
    status, response = server.handle_generate(payload, paths=AppPaths(tmp_path))
    assert status == 200, response
    with Image.open(response["output_path"]) as result, Image.open(tmp_path / "inputs/references/mask.png") as mask:
        original = np.array(Image.new("RGB", result.size, "green"))
        assert np.array_equal(np.array(result)[np.array(mask) == 0], original[np.array(mask) == 0])


def test_failure_after_base_preserves_base_and_durable_crop(tmp_path, monkeypatch, assets):
    monkeypatch.setattr(detailer.Detector, "detect", lambda _, source, cancelled: regions(source))
    calls = []
    monkeypatch.setattr(novelai.client, "_requests_transport", transport_recorder(calls, fail_at=3))
    payload = {**assets, "operation": "generate", "input_image": ""}
    status, response = server.handle_generate(payload, paths=AppPaths(tmp_path))
    assert status == 200, response
    manifest = json.loads(next(AppPaths(tmp_path).manifest_root.glob("*.json")).read_text())
    assert manifest["novelai"]["detailer_failure"] == {"code": "nai_timeout", "remote_outcome_unknown": True}
    assert manifest["stages"]["face_detailer"]["status"] == "failed"
    assert manifest["warnings"]
    assert len(list(AppPaths(tmp_path).image_root.glob("*-composite.png"))) == 1
    assert len(calls) == 3


def test_existing_image_partial_failure_returns_completed_composite_and_stops(tmp_path, monkeypatch, assets):
    calls = []
    monkeypatch.setattr(detailer.Detector, "detect", lambda _, source, cancelled: regions(source))
    monkeypatch.setattr(novelai.client, "_requests_transport", transport_recorder(calls, fail_at=2))
    status, response = server.handle_generate(assets, paths=AppPaths(tmp_path))
    assert status == 200 and response["stop_scheduling"] and response["remote_outcome_unknown"]
    assert response["warnings"]
    with Image.open(response["output_path"]) as image:
        assert image.getpixel((30, 40)) == (128, 0, 128)
        assert image.getpixel((80, 40)) == (0, 128, 0)
    assert len(calls) == 2


def test_local_detector_runtime_failure_preserves_base_and_stops(tmp_path, monkeypatch, assets):
    calls = []
    monkeypatch.setattr(novelai.client, "_requests_transport", transport_recorder(calls))

    def fail_detection(*args):
        raise RuntimeError("synthetic-detailer-secret local inference failure")

    monkeypatch.setattr(detailer.Detector, "detect", fail_detection)
    status, response = server.handle_generate({**assets, "operation": "generate", "input_image": ""}, paths=AppPaths(tmp_path))
    assert status == 200 and response["stop_scheduling"] and not response["remote_outcome_unknown"]
    assert response["warnings"] and len(calls) == 1
    assert "synthetic-detailer-secret" not in json.dumps(response)
    with Image.open(response["output_path"]) as image:
        assert image.getpixel((30, 40)) == (128, 0, 128)


def test_local_failure_after_completed_crops_preserves_standalone_result(tmp_path, monkeypatch, assets):
    monkeypatch.setattr(novelai.client, "_requests_transport", transport_recorder([]))
    monkeypatch.setattr(detailer.Detector, "detect", lambda _, source, cancelled: regions(source))
    repaint = detailer.repaint

    def fail_after_crops(*args, **kwargs):
        repaint(*args, **kwargs)
        raise RuntimeError("synthetic-detailer-secret local inference failure")

    monkeypatch.setattr(detailer, "repaint", fail_after_crops)
    status, response = server.handle_generate(assets, paths=AppPaths(tmp_path))
    assert status == 200 and response["stop_scheduling"] and not response["remote_outcome_unknown"]
    assert "synthetic-detailer-secret" not in json.dumps(response)
    with Image.open(response["output_path"]) as image:
        assert image.getpixel((30, 40)) == image.getpixel((80, 40)) == (128, 0, 128)


def test_wd_ambiguous_skip_and_tight_retry_without_generated_tags(tmp_path, monkeypatch, assets):
    character_data = [{"prompt": "1.2::alice (franchise)::, red hair", "negative_prompt": "bad alice", "x": 0, "y": .5},
                      {"prompt": "bob (franchise), blue hair", "negative_prompt": "bad bob", "x": 1, "y": .5}]
    request = novelai.request_from_payload({**assets, "nai_characters": character_data, "nai_detailer": {"enabled": True, "matching": "wd14", "padding": 0}})

    class Tagger:
        attempts = 0

        def score(self, images):
            self.attempts += 1
            if self.attempts == 1:
                return [{"red_hair": .95, "blue_hair": .1, "generated_tag": 1}, {"red_hair": .8, "blue_hair": .8}]
            return [{"red_hair": .1, "blue_hair": .9}]

    calls = []
    source = Image.open(tmp_path / "inputs/references/source.png").convert("RGB")
    _, _, report = detailer.repaint(source, request, AppPaths(tmp_path), token="synthetic", detector=SimpleNamespace(detect=lambda *_: regions(source)),
                                     tagger=Tagger(), transport=transport_recorder(calls), sleep=lambda _: None)
    assert [r["character"] for r in report] == [1, 2]
    assert report[1]["reason"] == "tag_match_tight"
    assert calls[0]["input"] == "shared scene, " + character_data[0]["prompt"]
    assert calls[1]["parameters"]["negative_prompt"] == "bad composition, bad bob"
    assert "generated_tag" not in json.dumps(calls)
    assert not calls[0]["parameters"]["v4_prompt"]["caption"]["char_captions"]


@pytest.mark.parametrize("scores", [{}, {"red_hair": .8, "blue_hair": .79}, {"blue_eyes": .99}, {"solo": 1, "best_quality": 1}])
def test_uncertain_wd_never_assigns_by_order(scores):
    characters = [SimpleNamespace(prompt="red hair, blue eyes, solo"), SimpleNamespace(prompt="blue hair, red eyes, solo")]
    assert match_characters(scores, characters).character_index is None


def test_prompt_boundary_preserves_original_weights_and_names():
    characters = [SimpleNamespace(prompt="-1::alice (franchise)::", uc="bad alice")]
    assert selected_prompts("shared", "bad", characters, detailer.Match(0, .9, .9, "test")) == ("shared, -1::alice (franchise)::", "bad, bad alice")


def focused_payload():
    return {"input": "flower", "action": "infill", "model": "nai-diffusion-4-5-full-inpainting",
            "parameters": {"width": 64, "height": 64, "steps": 28, "n_samples": 1,
                           "image": encode_png(Image.new("RGB", (64, 64))), "mask": encode_png(Image.new("L", (64, 64), 255)),
                           "inpaintImg2ImgStrength": .5, "noise": 0, "add_original_image": True}}


@pytest.mark.parametrize("changes", [{"width": 1088}, {"n_samples": 2}, {"steps": 29}, {"noise": .1},
                                    {"mask": "invalid"}, {"image": ""}, {"reference_image_multiple": []},
                                    {"inpaintImg2ImgStrength": True}, {"add_original_image": False}])
def test_strict_focused_guard(changes):
    payload = focused_payload()
    payload["parameters"].update(changes)
    with pytest.raises(NovelAIError):
        validate_opus_free_payload(payload, focused_context=FocusedContext((256, 128), (20, 20, 60, 60)))


def test_public_boolean_cannot_enable_focused_guard():
    with pytest.raises(NovelAIError):
        validate_opus_free_payload(focused_payload())
    with pytest.raises(NovelAIError):
        validate_opus_free_payload(focused_payload(), focused_context=True)
    with pytest.raises(NovelAIError):
        validate_opus_free_payload(focused_payload(), focused_context=FocusedContext((256, 128), (0, 0, 256, 128)))


def test_ownership_ties_are_disjoint_at_original_and_grid_resolutions():
    yy, xx = np.ogrid[:64, :128]
    centers = [(32, 32), (96, 32)]
    masks = [detailer._owned(xx, yy, centers, i) for i in range(2)]
    assert not np.logical_and(*masks).any()
    assert np.logical_or(*masks).all()


def test_sam3_face_eye_hand_contract_groups_eyes_with_faces(tmp_path, monkeypatch, assets):
    calls = []
    model_root = tmp_path / "models/detectors"
    model_root.mkdir(parents=True)
    (model_root / "sam3.pt").write_bytes(b"synthetic")
    boxes = {"face": (20, 30, 40, 50), "eye": (24, 34, 28, 36), "hand": (100, 30, 120, 50)}

    class Predictor:
        def __init__(self, overrides):
            assert overrides["device"] == "cpu"

        def set_image(self, image):
            assert isinstance(image, Image.Image) and image.mode == "RGB"
            self.size = image.size

        def __call__(self, text):
            calls.append(text[0])
            mask = Image.new("L", self.size)
            ImageDraw.Draw(mask).rectangle(boxes[text[0]], fill=255)
            tensor = SimpleNamespace(cpu=lambda: SimpleNamespace(numpy=lambda: np.array(mask) / 255))
            return [SimpleNamespace(masks=SimpleNamespace(data=[tensor]))]

    module = ModuleType("ultralytics.models.sam")
    module.SAM3SemanticPredictor = Predictor
    monkeypatch.setitem(sys.modules, "ultralytics.models.sam", module)
    tokenizer = ModuleType("clip.simple_tokenizer")
    tokenizer.SimpleTokenizer = lambda: (lambda text: text)
    monkeypatch.setitem(sys.modules, "clip.simple_tokenizer", tokenizer)
    source = Image.new("RGB", (256, 128))
    result = detailer.Detector(AppPaths(tmp_path), detailer.validate_settings({"backend": "sam3", "concepts": ["face", "eyes", "hands"]})).detect(source, lambda: False)
    assert calls == ["face", "eye", "hand"]
    assert len(result) == 2 and [r.concept for r in result] == ["face", "hands"]
    assert all(r.mask.size == source.size and r.mask.getbbox() for r in result)

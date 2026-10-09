"""SAM3 acceptance: real detector orchestration with synthetic predictor outputs."""
import json
import sys
from types import ModuleType, SimpleNamespace

import numpy as np
import pytest
from PIL import Image, ImageDraw

from anima_app import server
from anima_app.config import AppPaths
from anima_app.providers import novelai
from anima_app.providers.novelai import detailer
from anima_app.providers.novelai.errors import NovelAIError


@pytest.fixture
def sam3(tmp_path, monkeypatch):
    paths = AppPaths(tmp_path)
    model = paths.model_root / "detectors/sam3.pt"
    model.parent.mkdir(parents=True)
    model.write_bytes(b"synthetic, not model weights")
    calls = []
    state = {"cancelled": False, "empty": False}

    class Predictor:
        def __init__(self, overrides):
            calls.append(("init", overrides))

        def set_image(self, image):
            assert isinstance(image, Image.Image) and image.mode == "RGB"
            self.size = image.size
            calls.append(("image", image.getpixel((0, 0))))

        def __call__(self, *, text):
            calls.append(("query", text))
            masks = []
            if not state["empty"]:
                boxes = {"face": ((10, 10, 30, 40), (90, 10, 110, 40)),
                         "eye": ((15, 15, 20, 18), (95, 15, 100, 18)),
                         "hand": ((50, 50, 65, 70),)}
                for box in boxes[text[0]]:
                    mask = Image.new("L", self.size)
                    ImageDraw.Draw(mask).rectangle(box, fill=255)
                    array = np.array(mask, dtype=np.float32) / 255
                    masks.append(SimpleNamespace(cpu=lambda array=array: SimpleNamespace(numpy=lambda: array)))
            if state.get("cancel_after_query"):
                state["cancelled"] = True
            return [SimpleNamespace(masks=SimpleNamespace(data=masks))]

    module = ModuleType("ultralytics.models.sam")
    module.SAM3SemanticPredictor = Predictor
    monkeypatch.setitem(sys.modules, "ultralytics.models.sam", module)
    tokenizer = ModuleType("clip.simple_tokenizer")
    tokenizer.SimpleTokenizer = lambda: (lambda text: text)
    monkeypatch.setitem(sys.modules, "clip.simple_tokenizer", tokenizer)
    return paths, calls, state


@pytest.mark.parametrize("concepts,expected,queries", [
    (["face"], ["face", "face"], ["face"]),
    (["eyes"], ["eyes", "eyes"], ["eye"]),
    (["hands"], ["hands"], ["hand"]),
    (["face", "eyes", "hands"], ["face", "face", "hands"], ["face", "eye", "hand"]),
    (["hands", "eyes", "face"], ["hands", "face", "face"], ["hand", "eye", "face"]),
])
def test_concepts_preserve_instances_and_use_one_rgb_image(sam3, concepts, expected, queries):
    paths, calls, state = sam3
    settings = detailer.validate_settings({"backend": "sam3", "concepts": concepts, "threshold": .73})
    result = detailer.Detector(paths, settings).detect(Image.new("RGB", (128, 96), (249, 13, 31)), lambda: False)
    assert [r.concept for r in result] == expected
    assert [c[1][0] for c in calls if c[0] == "query"] == queries
    assert [c for c in calls if c[0] == "image"] == [("image", (249, 13, 31))]
    assert len([c for c in calls if c[0] == "init"]) == 1
    assert calls[0][1]["conf"] == .73 and calls[0][1]["device"] == "cpu"
    assert not calls[0][1]["save"] and calls[0][1]["model"].endswith("sam3.pt")
    assert all(r.mask.size == (128, 96) and r.mask.getbbox() == r.box for r in result)


def test_empty_detections_are_empty(sam3):
    paths, calls, state = sam3
    state["empty"] = True
    assert detailer.Detector(paths, detailer.validate_settings({"backend": "sam3"})).detect(
        Image.new("RGB", (128, 96)), lambda: False) == []


@pytest.mark.parametrize("when", ["before", "after_query"])
def test_cancellation_prevents_remaining_queries(sam3, when):
    paths, calls, state = sam3
    state["cancelled"] = when == "before"
    state["cancel_after_query"] = when == "after_query"
    with pytest.raises(NovelAIError) as error:
        detailer.Detector(paths, detailer.validate_settings({"backend": "sam3"})).detect(
            Image.new("RGB", (128, 96)), lambda: state["cancelled"])
    assert error.value.code == "generation_cancelled"
    assert len([c for c in calls if c[0] == "query"]) == (0 if when == "before" else 1)
    if when == "before":
        assert calls == []


@pytest.mark.parametrize("operation", ["generate", "detail"])
@pytest.mark.parametrize("missing", ["model", "runtime", "tokenizer", "noncallable_tokenizer"])
def test_unavailable_sam3_blocks_before_account_encoding_and_generation(sam3, monkeypatch, operation, missing):
    paths, calls, state = sam3
    source = paths.input_root / "references/source.png"
    source.parent.mkdir(parents=True)
    Image.new("RGB", (128, 128)).save(source)
    if missing == "model":
        (paths.model_root / "detectors/sam3.pt").unlink()
    elif missing == "runtime":
        monkeypatch.setitem(sys.modules, "ultralytics.models.sam", ModuleType("ultralytics.models.sam"))
    elif missing == "tokenizer":
        monkeypatch.setitem(sys.modules, "clip.simple_tokenizer", None)
    else:
        sys.modules["clip.simple_tokenizer"].SimpleTokenizer = lambda: object()

    def forbid(*args, **kwargs):
        pytest.fail("unavailable SAM3 must be rejected before remote methods")

    monkeypatch.setattr(novelai.client, "_requests_transport", forbid)
    monkeypatch.setattr(novelai.client, "_requests_subscription_transport", forbid)
    monkeypatch.setattr(novelai.service, "reference_parameters", forbid)
    monkeypatch.setattr(novelai.service, "get_token", forbid)
    payload = {"provider": "novelai", "prompt": "SAM3", "width": 128, "height": 128,
               "operation": operation, "input_image": "inputs/references/source.png" if operation == "detail" else "",
               "nai_detailer": {"enabled": True, "backend": "sam3"}}
    status, response = server.handle_generate(payload, paths=paths)
    assert status == 400, response
    assert response["error_code"] == ("generation_invalid_request" if missing == "model" else "sam3_runtime_unavailable")
    assert calls == []


def test_missing_runtime_error_is_secret_free(sam3, monkeypatch):
    paths, _, _ = sam3
    module = ModuleType("ultralytics.models.sam")

    def unavailable(name):
        raise ImportError("synthetic-private-runtime-value")

    module.__getattr__ = unavailable
    monkeypatch.setitem(sys.modules, "ultralytics.models.sam", module)
    with pytest.raises(NovelAIError) as error:
        detailer.Detector(paths, detailer.validate_settings({"backend": "sam3"})).preflight()
    assert "synthetic-private-runtime-value" not in json.dumps(error.value.payload())


def test_sam3_resolves_existing_fallback_asset(sam3):
    paths, _, _ = sam3
    fallback = paths.model_root / "detectors"
    other = AppPaths(paths.project_root / "other", face_detailer_detector_fallback_sources=(fallback,))
    detailer.Detector(other, detailer.validate_settings({"backend": "sam3"})).preflight()

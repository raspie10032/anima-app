"""YOLO hands + both SAM B adapters, with synthetic tensors and real planning."""
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import numpy as np
import pytest
from PIL import Image, ImageDraw

from anima_app import server
from anima_app.config import AppPaths
from anima_app.providers import novelai
from anima_app.providers.novelai import detailer
from anima_app.providers.novelai.errors import NovelAIError


def tensor(array):
    return SimpleNamespace(cpu=lambda: SimpleNamespace(numpy=lambda: np.asarray(array)))


@pytest.fixture
def models(tmp_path, monkeypatch):
    paths = AppPaths(tmp_path)
    root = paths.model_root / "detectors"
    root.mkdir(parents=True)
    for name in ("hand_yolov8n.pt", "hand_yolov8s.pt", "face_yolov8n.pt", "full_eyes_detect_v1.pt", "sam_b.pt"):
        (root / name).write_bytes(b"synthetic fixture, never loaded as weights")
    calls = []
    state = {"empty": False, "empty_mask": False, "no_mask": False, "cancelled": False}
    boxes = {"face_yolov8n.pt": [(10, 10, 30, 40)], "full_eyes_detect_v1.pt": [(15, 15, 20, 18)],
             "hand_yolov8n.pt": [(50, 50, 65, 70), (90, 50, 110, 70)],
             "hand_yolov8s.pt": [(50, 50, 65, 70), (90, 50, 110, 70)]}

    class YOLO:
        def __init__(self, path):
            self.name = Path(path).name
            calls.append(("yolo_init", self.name))

        def __call__(self, source, **kwargs):
            assert isinstance(source, Image.Image) and source.mode == "RGB"
            calls.append(("yolo", self.name, kwargs))
            if state.get("cancel_after_yolo"):
                state["cancelled"] = True
            array = np.asarray([] if state["empty"] else boxes[self.name]).reshape(-1, 4)
            return [SimpleNamespace(boxes=SimpleNamespace(xyxy=tensor(array)))]

    def mask_for(size, box):
        mask = Image.new("L", size)
        if not state["empty_mask"]:
            ImageDraw.Draw(mask).ellipse(tuple(box), fill=255)
        return np.array(mask, dtype=np.float32) / 255

    class SAM:
        def __init__(self, path):
            calls.append(("sam_init", Path(path).name))

        def __call__(self, source, *, bboxes, **kwargs):
            assert isinstance(source, Image.Image) and source.mode == "RGB"
            assert source.getpixel((0, 0)) == (249, 13, 31)
            calls.append(("sam", bboxes, kwargs))
            if state.get("cancel_after_sam"):
                state["cancelled"] = True
            masks = None if state["no_mask"] else SimpleNamespace(data=[tensor(mask_for(source.size, bboxes[0]))])
            return [SimpleNamespace(masks=masks)]

    class SamPredictor:
        def __init__(self, model):
            calls.append(("pth_init", model))

        def set_image(self, source):
            assert source.shape == (96, 128, 3) and tuple(source[0, 0]) == (249, 13, 31)
            self.size = (source.shape[1], source.shape[0])
            calls.append(("pth_image", tuple(source[0, 0])))

        def predict(self, *, box, multimask_output):
            assert multimask_output is False
            calls.append(("pth", list(box)))
            if state.get("cancel_after_sam"):
                state["cancelled"] = True
            return np.asarray([mask_for(self.size, box)], dtype=bool), None, None

    ultra = ModuleType("ultralytics")
    ultra.YOLO, ultra.SAM = YOLO, SAM
    segment = ModuleType("segment_anything")
    segment.SamPredictor = SamPredictor
    segment.sam_model_registry = {"vit_b": lambda checkpoint: SimpleNamespace(to=lambda device: (checkpoint, device))}
    monkeypatch.setitem(sys.modules, "ultralytics", ultra)
    monkeypatch.setitem(sys.modules, "segment_anything", segment)
    return paths, calls, state


def use_pth(paths):
    (paths.model_root / "detectors/sam_b.pt").unlink()
    (paths.model_root / "detectors/sam_vit_b_01ec64.pth").write_bytes(b"synthetic fixture")


@pytest.mark.parametrize("adapter", ["pt", "pth"])
@pytest.mark.parametrize("concepts,expected", [(["hands"], ["hands", "hands"]),
                                             (["face", "eyes", "hands"], ["face", "hands", "hands"])])
def test_hand_masks_rgb_threshold_and_independent_regions(models, adapter, concepts, expected):
    paths, calls, _ = models
    if adapter == "pth":
        use_pth(paths)
    result = detailer.Detector(paths, detailer.validate_settings({"concepts": concepts, "threshold": .73})).detect(
        Image.new("RGB", (128, 96), (249, 13, 31)), lambda: False)
    assert [r.concept for r in result] == expected
    assert all(r.mask.size == (128, 96) and r.mask.getbbox() for r in result)
    assert all(c[2] == {"conf": .73, "verbose": False, "device": "cpu"} for c in calls if c[0] == "yolo")
    hands = [r for r in result if r.concept == "hands"]
    assert not np.any(np.array(hands[0].mask) & np.array(hands[1].mask))
    # SAM's ellipse, not its bounding rectangle, must drive repaint masks.
    assert hands[0].mask.getpixel((50, 50)) == 0 and hands[0].mask.getpixel((57, 60)) == 255
    if adapter == "pth":
        assert len([c for c in calls if c[0] == "pth_image"]) == 1
    if concepts == ["hands"]:
        assert [c[1] for c in calls if c[0] == "yolo_init"] == ["hand_yolov8n.pt"]


def test_hand_small_model_fallback_resolves_existing_root(models):
    paths, calls, _ = models
    (paths.model_root / "detectors/hand_yolov8n.pt").unlink()
    fallback = AppPaths(paths.project_root / "other", face_detailer_detector_fallback_sources=(paths.model_root / "detectors",))
    detailer.Detector(fallback, detailer.validate_settings({"concepts": ["hands"]})).detect(
        Image.new("RGB", (128, 96), (249, 13, 31)), lambda: False)
    assert [c[1] for c in calls if c[0] == "yolo_init"] == ["hand_yolov8s.pt"]


@pytest.mark.parametrize("adapter", ["pt", "pth"])
def test_empty_yolo_avoids_segmentation(models, adapter):
    paths, calls, state = models
    if adapter == "pth":
        use_pth(paths)
    state["empty"] = True
    assert detailer.Detector(paths, detailer.validate_settings({"concepts": ["hands"]})).detect(
        Image.new("RGB", (128, 96), (249, 13, 31)), lambda: False) == []
    assert not [c for c in calls if c[0] in {"sam", "pth"}]


@pytest.mark.parametrize("adapter", ["pt", "pth"])
def test_empty_sam_masks_are_excluded_from_plan(models, adapter):
    paths, _, state = models
    if adapter == "pth":
        use_pth(paths)
    state["empty_mask"] = True
    source = Image.new("RGB", (128, 96), (249, 13, 31))
    settings = {"concepts": ["hands"], "enabled": True}
    regions = detailer.Detector(paths, detailer.validate_settings(settings)).detect(source, lambda: False)
    request = novelai.request_from_payload({"prompt": "hands", "nai_detailer": settings})
    assert detailer.plan(source, regions, request)[3] == []


@pytest.mark.parametrize("adapter", ["pt", "pth"])
@pytest.mark.parametrize("when", ["before", "after_yolo", "after_sam"])
def test_cancel_stops_next_hand_inference(models, adapter, when):
    paths, calls, state = models
    if adapter == "pth":
        use_pth(paths)
    state["cancelled"] = when == "before"
    state[f"cancel_{when}"] = True
    with pytest.raises(NovelAIError) as error:
        detailer.Detector(paths, detailer.validate_settings({"concepts": ["hands"]})).detect(
            Image.new("RGB", (128, 96), (249, 13, 31)), lambda: state["cancelled"])
    assert error.value.code == "generation_cancelled"
    assert len([c for c in calls if c[0] in {"sam", "pth"}]) == (1 if when == "after_sam" else 0)
    if when == "before":
        assert not calls


@pytest.mark.parametrize("missing", ["hands", "sam", "SAM_class", "YOLO_class", "pth_predictor"])
@pytest.mark.parametrize("operation", ["generate", "detail"])
def test_missing_assets_or_adapters_block_before_remote(models, monkeypatch, missing, operation):
    paths, calls, _ = models
    if missing == "hands":
        for name in ("hand_yolov8n.pt", "hand_yolov8s.pt"):
            (paths.model_root / "detectors" / name).unlink()
    elif missing == "sam":
        (paths.model_root / "detectors/sam_b.pt").unlink()
    elif missing == "pth_predictor":
        use_pth(paths)
        del sys.modules["segment_anything"].SamPredictor
    else:
        delattr(sys.modules["ultralytics"], missing.removesuffix("_class"))
    source = paths.input_root / "references/source.png"
    source.parent.mkdir(parents=True)
    Image.new("RGB", (128, 128)).save(source)

    def forbid(*args, **kwargs):
        pytest.fail("Missing hand detector must block before remote work")

    for name in ("_requests_transport", "_requests_subscription_transport"):
        monkeypatch.setattr(novelai.client, name, forbid)
    monkeypatch.setattr(novelai.service, "reference_parameters", forbid)
    monkeypatch.setattr(novelai.service, "get_token", forbid)
    payload = {"provider": "novelai", "operation": operation, "prompt": "hands", "width": 128, "height": 128,
               "input_image": "inputs/references/source.png" if operation == "detail" else "",
               "nai_detailer": {"enabled": True, "concepts": ["hands"]}}
    status, response = server.handle_generate(payload, paths=paths)
    expected = "generation_invalid_request" if missing in {"hands", "sam"} else "sam_b_runtime_unavailable"
    assert status == 400 and response["error_code"] == expected, response
    assert not calls

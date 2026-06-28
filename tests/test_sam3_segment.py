from types import ModuleType

import numpy as np
import pytest
from PIL import Image

from anima_app.config import AppPaths
from anima_app.runtime.sam3_segment import adjust_segment_mask, resolve_segment_source, segment_image_concept, segment_image_concepts


def test_resolve_segment_source_accepts_outputs_and_rejects_escape(tmp_path):
    paths = AppPaths(project_root=tmp_path)
    image = paths.image_root / "sample.png"
    image.parent.mkdir(parents=True)
    Image.new("RGB", (8, 8), "white").save(image)

    assert resolve_segment_source("/outputs/images/sample.png", paths) == image.resolve()

    with pytest.raises(ValueError, match="outputs/images or inputs"):
        resolve_segment_source(str(tmp_path.parent / "outside.png"), paths)


def test_segment_image_concept_writes_mask_and_overlay(tmp_path, monkeypatch):
    paths = AppPaths(project_root=tmp_path)
    source = paths.image_root / "sample.png"
    source.parent.mkdir(parents=True)
    Image.new("RGB", (16, 16), "white").save(source)
    model = paths.model_root / "detectors" / "sam3.pt"
    model.parent.mkdir(parents=True)
    model.write_bytes(b"sam3")

    class FakeArray:
        def __init__(self, array):
            self.array = array

        def cpu(self):
            return self

        def numpy(self):
            return self.array

    class FakeMasks:
        data = [FakeArray(np.ones((16, 16), dtype=np.float32))]

    class FakeBoxes:
        xyxy = FakeArray(np.array([[1, 2, 3, 4]], dtype=np.float32))
        conf = FakeArray(np.array([0.9], dtype=np.float32))

    class FakeResult:
        masks = FakeMasks()
        boxes = FakeBoxes()

    class FakePredictor:
        def __init__(self, overrides):
            assert overrides["model"].endswith("sam3.pt")

        def set_image(self, image):
            assert image.shape[:2] == (16, 16)

        def __call__(self, *, text):
            assert text == ["clothes"]
            return [FakeResult()]

    fake_sam_module = ModuleType("ultralytics.models.sam")
    fake_sam_module.SAM3SemanticPredictor = FakePredictor
    monkeypatch.setitem(__import__("sys").modules, "ultralytics.models.sam", fake_sam_module)
    monkeypatch.setattr("anima_app.runtime.sam3_segment._select_device", lambda: "cpu")

    result = segment_image_concept("/outputs/images/sample.png", prompt="clothes", paths=paths)

    assert result.prompt == "clothes"
    assert result.boxes == ((1.0, 2.0, 3.0, 4.0),)
    assert result.scores == pytest.approx((0.9,))
    assert result.mask_path.is_file()
    assert result.overlay_path.is_file()


def test_segment_image_concepts_reuses_image_for_prompt_candidates(tmp_path, monkeypatch):
    paths = AppPaths(project_root=tmp_path)
    source = paths.image_root / "sample.png"
    source.parent.mkdir(parents=True)
    Image.new("RGB", (16, 16), "white").save(source)
    model = paths.model_root / "detectors" / "sam3.pt"
    model.parent.mkdir(parents=True)
    model.write_bytes(b"sam3")
    calls: list[list[str]] = []

    class FakeArray:
        def __init__(self, array):
            self.array = array

        def cpu(self):
            return self

        def numpy(self):
            return self.array

    class FakeMasks:
        data = [FakeArray(np.ones((16, 16), dtype=np.float32))]

    class FakeBoxes:
        xyxy = FakeArray(np.array([[1, 2, 3, 4]], dtype=np.float32))
        conf = FakeArray(np.array([0.8], dtype=np.float32))

    class FakeResult:
        masks = FakeMasks()
        boxes = FakeBoxes()

    class FakePredictor:
        def __init__(self, overrides):
            assert overrides["model"].endswith("sam3.pt")
            self.image_set_count = 0

        def set_image(self, image):
            self.image_set_count += 1
            assert image.shape[:2] == (16, 16)

        def __call__(self, *, text):
            calls.append(text)
            return [FakeResult()]

    fake_sam_module = ModuleType("ultralytics.models.sam")
    fake_sam_module.SAM3SemanticPredictor = FakePredictor
    monkeypatch.setitem(__import__("sys").modules, "ultralytics.models.sam", fake_sam_module)
    monkeypatch.setattr("anima_app.runtime.sam3_segment._select_device", lambda: "cpu")

    results = segment_image_concepts(
        "/outputs/images/sample.png",
        prompts=["white dress", "white dress", "upper body clothing"],
        paths=paths,
    )

    assert [result.prompt for result in results] == ["white dress", "upper body clothing"]
    assert calls == [["white dress"], ["upper body clothing"]]
    assert all(result.overlay_path.is_file() for result in results)


def test_adjust_segment_mask_expands_feathers_and_writes_crop(tmp_path):
    paths = AppPaths(project_root=tmp_path)
    source = paths.image_root / "source.png"
    mask = paths.image_root / "source_clothes_sam3_mask.png"
    source.parent.mkdir(parents=True)
    Image.new("RGB", (64, 64), "white").save(source)
    mask_image = Image.new("L", (64, 64), 0)
    mask_image.paste(255, (28, 28, 36, 36))
    mask_image.save(mask)

    result = adjust_segment_mask(
        "/outputs/images/source.png",
        mask_path="/outputs/images/source_clothes_sam3_mask.png",
        paths=paths,
        dilation=8,
        feather=4,
        crop_padding=4,
    )

    assert result.dilation == 8
    assert result.feather == 4
    assert result.mask_path.is_file()
    assert result.overlay_path.is_file()
    assert result.crop_path.is_file()
    assert result.crop_mask_path.is_file()
    assert result.crop_box[0] < 28
    assert result.crop_box[1] < 28
    assert result.crop_box[2] > 36
    assert result.crop_box[3] > 36

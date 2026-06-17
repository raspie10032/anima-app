from types import ModuleType

import numpy as np
from PIL import Image

from anima_app.config import AppPaths
from anima_app.requests import FaceDetailerSettings, T2IRequest
from anima_app.runtime.face_detailer import (
    EYE_DETECTOR,
    FACE_DETECTOR,
    SAM_DETECTOR,
    AnimeFaceDetailer,
    FaceDetailerMaskResult,
    align_mask_to_grid,
    composite_face_crop,
    detector_paths,
    expand_box,
    feather_mask,
    missing_detector_paths,
    run_face_detailer,
)


def test_align_mask_empty_stays_empty():
    mask = np.zeros((64, 64), dtype=np.uint8)

    assert align_mask_to_grid(mask).sum() == 0


def test_align_mask_solid_block_fills_grid():
    mask = np.zeros((64, 64), dtype=np.uint8)
    mask[0:48, 0:48] = 255

    result = align_mask_to_grid(mask)

    assert result.max() == 255
    assert result[0:32, 0:32].mean() == 255


def test_detector_paths_are_project_local(tmp_path):
    paths = AppPaths(project_root=tmp_path)
    expected = detector_paths(paths)

    assert expected.face == tmp_path / "models" / "detectors" / FACE_DETECTOR
    assert expected.eyes == tmp_path / "models" / "detectors" / EYE_DETECTOR
    assert expected.sam == tmp_path / "models" / "detectors" / SAM_DETECTOR


def test_missing_detector_paths_reports_all_required_assets(tmp_path):
    paths = AppPaths(project_root=tmp_path)

    missing = missing_detector_paths(paths)

    assert {path.name for path in missing} == {FACE_DETECTOR, EYE_DETECTOR, SAM_DETECTOR}


def test_build_mask_returns_none_when_detectors_find_no_boxes(tmp_path, monkeypatch):
    paths = AppPaths(project_root=tmp_path)
    required = detector_paths(paths)
    for path in (required.face, required.eyes, required.sam):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"model")

    class EmptyBoxes:
        def __len__(self):
            return 0

    class EmptyResult:
        boxes = EmptyBoxes()

    class FakeDetector:
        def __init__(self, _path):
            pass

        def to(self, _device):
            return self

        def __call__(self, *_args, **_kwargs):
            return [EmptyResult()]

    fake_ultralytics = ModuleType("ultralytics")
    fake_ultralytics.YOLO = FakeDetector
    fake_ultralytics.SAM = FakeDetector
    monkeypatch.setitem(__import__("sys").modules, "ultralytics", fake_ultralytics)
    monkeypatch.setattr(AnimeFaceDetailer, "_select_device", staticmethod(lambda: "cpu"))

    detailer = AnimeFaceDetailer(paths)
    result = detailer.build_mask(Image.new("RGB", (64, 64)), FaceDetailerSettings())

    assert result is None


def test_expand_box_applies_crop_scale_padding_and_image_bounds():
    box = expand_box((40, 50, 80, 90), image_size=(128, 128), crop_scale=1.5, padding=8)

    assert box == (22, 32, 98, 108)


def test_feather_mask_preserves_size_and_softens_edges():
    mask = Image.new("L", (32, 32), 0)
    mask.paste(255, (8, 8, 24, 24))

    softened = feather_mask(mask, feather=4)

    assert softened.size == mask.size
    assert softened.getpixel((16, 16)) > 220
    assert 0 < softened.getpixel((7, 16)) < 255


def test_composite_face_crop_pastes_detail_with_feathered_mask():
    base = Image.new("RGB", (64, 64), "black")
    detail = Image.new("RGB", (32, 32), "white")
    mask = Image.new("L", (32, 32), 255)

    result = composite_face_crop(base, detail, crop_box=(16, 16, 48, 48), mask=mask, feather=2)

    assert result.size == base.size
    assert result.getpixel((32, 32)) == (255, 255, 255)
    assert result.getpixel((4, 4)) == (0, 0, 0)


def test_run_face_detailer_records_missing_detector_skip(tmp_path):
    image_path = tmp_path / "base.png"
    Image.new("RGB", (64, 64), "black").save(image_path)

    result = run_face_detailer(
        image_path,
        request=T2IRequest(prompt="face", face_detailer=FaceDetailerSettings(enabled=True)),
        paths=AppPaths(project_root=tmp_path),
    )

    assert result.output_path == image_path
    assert result.metadata["status"] == "skipped"
    assert result.metadata["reason"] == "missing_detectors"
    assert result.warnings[0].startswith("missing face detailer detector assets")


def test_run_face_detailer_records_no_detection_skip(tmp_path):
    image_path = tmp_path / "base.png"
    Image.new("RGB", (64, 64), "black").save(image_path)

    class NoDetectionDetailer:
        def build_mask(self, _image, _settings):
            return None

    result = run_face_detailer(
        image_path,
        request=T2IRequest(prompt="face", face_detailer=FaceDetailerSettings(enabled=True)),
        paths=AppPaths(project_root=tmp_path),
        detailer=NoDetectionDetailer(),
    )

    assert result.output_path == image_path
    assert result.metadata["status"] == "skipped"
    assert result.metadata["reason"] == "no_detections"


def test_run_face_detailer_records_pending_when_repaint_backend_is_missing(tmp_path):
    image_path = tmp_path / "base.png"
    Image.new("RGB", (64, 64), "black").save(image_path)
    mask = Image.new("L", (64, 64), 0)
    mask.paste(255, (16, 16, 48, 48))

    class DetectionDetailer:
        def build_mask(self, _image, _settings):
            return FaceDetailerMaskResult(
                mask=mask,
                boxes=((16.0, 16.0, 48.0, 48.0),),
                detector="anime-eyes",
            )

    result = run_face_detailer(
        image_path,
        request=T2IRequest(prompt="face", face_detailer=FaceDetailerSettings(enabled=True)),
        paths=AppPaths(project_root=tmp_path),
        detailer=DetectionDetailer(),
    )

    assert result.output_path == image_path
    assert result.metadata["status"] == "pending_repaint"
    assert result.metadata["boxes"] == [[16.0, 16.0, 48.0, 48.0]]
    assert result.warnings == ("face detailer detected faces, but local repaint backend is not wired yet",)


def test_run_face_detailer_composites_repainted_crop(tmp_path):
    image_path = tmp_path / "base.png"
    Image.new("RGB", (64, 64), "black").save(image_path)
    mask = Image.new("L", (64, 64), 0)
    mask.paste(255, (24, 24, 40, 40))

    class DetectionDetailer:
        def build_mask(self, _image, _settings):
            return FaceDetailerMaskResult(
                mask=mask,
                boxes=((24.0, 24.0, 40.0, 40.0),),
                detector="anime-eyes",
            )

    def repaint(crop, crop_mask, _request, _paths):
        assert crop.size == crop_mask.size
        return Image.new("RGB", crop.size, "white")

    result = run_face_detailer(
        image_path,
        request=T2IRequest(
            prompt="face",
            face_detailer=FaceDetailerSettings(enabled=True, crop_scale=1.0, padding=0, feather=0),
        ),
        paths=AppPaths(project_root=tmp_path),
        detailer=DetectionDetailer(),
        repaint=repaint,
    )

    assert result.output_path != image_path
    assert result.metadata["status"] == "completed"
    assert Image.open(result.output_path).getpixel((32, 32)) == (255, 255, 255)


def test_run_face_detailer_excludes_forehead_from_repaint_mask(tmp_path):
    image_path = tmp_path / "base.png"
    Image.new("RGB", (64, 64), "black").save(image_path)
    mask = Image.new("L", (64, 64), 0)
    mask.paste(255, (16, 16, 48, 48))
    captured: dict[str, Image.Image] = {}

    class DetectionDetailer:
        def build_mask(self, _image, _settings):
            return FaceDetailerMaskResult(
                mask=mask,
                boxes=((16.0, 16.0, 48.0, 48.0),),
                detector="anime-eyes",
            )

    def repaint(crop, crop_mask, _request, _paths):
        captured["mask"] = crop_mask.copy()
        return Image.new("RGB", crop.size, "white")

    result = run_face_detailer(
        image_path,
        request=T2IRequest(
            prompt="face",
            face_detailer=FaceDetailerSettings(
                enabled=True,
                crop_scale=1.0,
                padding=0,
                feather=0,
                exclude_forehead_ratio=0.25,
            ),
        ),
        paths=AppPaths(project_root=tmp_path),
        detailer=DetectionDetailer(),
        repaint=repaint,
    )

    assert result.metadata["status"] == "completed"
    assert result.metadata["exclude_forehead_ratio"] == 0.25
    assert result.metadata["excluded_forehead_pixels"] == 8
    assert captured["mask"].getpixel((16, 2)) == 0
    assert captured["mask"].getpixel((16, 10)) == 255

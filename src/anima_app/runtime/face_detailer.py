from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np
from PIL import Image, ImageFilter

from anima_app.config import AppPaths
from anima_app.requests import FaceDetailerSettings, T2IRequest


FACE_DETECTOR = "face_yolov8n.pt"
EYE_DETECTOR = "full_eyes_detect_v1.pt"
SAM_DETECTOR = "sam_b.pt"


@dataclass(frozen=True)
class FaceDetailerDetectorPaths:
    face: Path
    eyes: Path
    sam: Path


@dataclass(frozen=True)
class FaceDetailerMaskResult:
    mask: Image.Image
    boxes: tuple[tuple[float, float, float, float], ...]
    detector: str


@dataclass(frozen=True)
class FaceDetailerStageResult:
    output_path: Path
    metadata: dict[str, object]
    warnings: tuple[str, ...] = ()


FaceRepaintBackend = Callable[[Image.Image, Image.Image, T2IRequest, AppPaths], Image.Image]


def detector_paths(paths: AppPaths) -> FaceDetailerDetectorPaths:
    root = paths.model_root / "detectors"
    return FaceDetailerDetectorPaths(
        face=root / FACE_DETECTOR,
        eyes=root / EYE_DETECTOR,
        sam=root / SAM_DETECTOR,
    )


def missing_detector_paths(paths: AppPaths) -> tuple[Path, ...]:
    expected = detector_paths(paths)
    return tuple(path for path in (expected.face, expected.eyes, expected.sam) if not path.is_file())


def align_mask_to_grid(mask: np.ndarray, box_size: int = 32, grid_step: int = 8, threshold: float = 0.3) -> np.ndarray:
    """Adapted from NAI-FaceDetailer core.face_pipeline under the MIT License."""
    height, width = mask.shape
    grid_mask = np.zeros_like(mask)
    for y in range(0, height - box_size + 1, grid_step):
        for x in range(0, width - box_size + 1, grid_step):
            window = mask[y : y + box_size, x : x + box_size]
            if window.size > 0 and np.mean(window) > (255 * threshold):
                grid_mask[y : y + box_size, x : x + box_size] = 255
    return grid_mask


def expand_box(
    box: tuple[float, float, float, float],
    *,
    image_size: tuple[int, int],
    crop_scale: float,
    padding: int,
) -> tuple[int, int, int, int]:
    x1, y1, x2, y2 = box
    width, height = image_size
    center_x = (x1 + x2) / 2
    center_y = (y1 + y2) / 2
    box_width = (x2 - x1) * crop_scale + padding * 2
    box_height = (y2 - y1) * crop_scale + padding * 2
    left = max(0, round(center_x - box_width / 2))
    top = max(0, round(center_y - box_height / 2))
    right = min(width, round(center_x + box_width / 2))
    bottom = min(height, round(center_y + box_height / 2))
    return left, top, right, bottom


def feather_mask(mask: Image.Image, feather: int) -> Image.Image:
    normalized = mask.convert("L")
    if feather <= 0:
        return normalized
    return normalized.filter(ImageFilter.GaussianBlur(radius=feather))


def exclude_forehead_from_mask(mask: Image.Image, ratio: float) -> tuple[Image.Image, int]:
    normalized = mask.convert("L")
    if ratio <= 0:
        return normalized, 0
    excluded_pixels = min(normalized.height, round(normalized.height * ratio))
    if excluded_pixels <= 0:
        return normalized, 0
    adjusted = normalized.copy()
    adjusted.paste(0, (0, 0, normalized.width, excluded_pixels))
    return adjusted, excluded_pixels


def composite_face_crop(
    base: Image.Image,
    detail: Image.Image,
    *,
    crop_box: tuple[int, int, int, int],
    mask: Image.Image,
    feather: int,
) -> Image.Image:
    result = base.convert("RGB").copy()
    crop_size = (crop_box[2] - crop_box[0], crop_box[3] - crop_box[1])
    detail_crop = detail.convert("RGB").resize(crop_size, Image.LANCZOS)
    crop_mask = feather_mask(mask.resize(crop_size, Image.LANCZOS), feather)
    result.paste(detail_crop, crop_box, crop_mask)
    return result


def run_face_detailer(
    image_path: Path,
    *,
    request: T2IRequest,
    paths: AppPaths,
    detailer: object | None = None,
    repaint: FaceRepaintBackend | None = None,
) -> FaceDetailerStageResult:
    if not request.face_detailer.enabled:
        return FaceDetailerStageResult(
            output_path=image_path,
            metadata={"enabled": False, "status": "disabled"},
        )

    with Image.open(image_path) as opened:
        base = opened.convert("RGB")
    active_detailer = detailer or AnimeFaceDetailer(paths)
    try:
        mask_result = active_detailer.build_mask(base, request.face_detailer)
    except FileNotFoundError as exc:
        return _skipped(image_path, reason="missing_detectors", warning=str(exc))
    except ImportError as exc:
        return _skipped(image_path, reason="missing_dependency", warning=f"missing face detailer dependency: {exc}")
    except Exception as exc:
        return _skipped(image_path, reason="detection_failed", warning=f"face detailer detection failed: {exc}")

    if mask_result is None:
        return FaceDetailerStageResult(
            output_path=image_path,
            metadata={"enabled": True, "status": "skipped", "reason": "no_detections", "boxes": []},
        )

    boxes = [list(box) for box in mask_result.boxes]
    crop_box = expand_box(
        mask_result.boxes[0],
        image_size=base.size,
        crop_scale=request.face_detailer.crop_scale,
        padding=request.face_detailer.padding,
    )
    crop = base.crop(crop_box)
    crop_mask = mask_result.mask.crop(crop_box)
    crop_mask, excluded_forehead_pixels = exclude_forehead_from_mask(
        crop_mask,
        request.face_detailer.exclude_forehead_ratio,
    )
    metadata = {
        "enabled": True,
        "status": "pending_repaint",
        "detector": mask_result.detector,
        "boxes": boxes,
        "crop_box": list(crop_box),
        "exclude_forehead_ratio": request.face_detailer.exclude_forehead_ratio,
        "excluded_forehead_pixels": excluded_forehead_pixels,
    }
    if repaint is None:
        return FaceDetailerStageResult(
            output_path=image_path,
            metadata=metadata,
            warnings=("face detailer detected faces, but local repaint backend is not wired yet",),
        )

    try:
        detail_crop = repaint(crop, crop_mask, request, paths)
    except Exception as exc:
        metadata["status"] = "skipped"
        metadata["reason"] = "repaint_failed"
        return FaceDetailerStageResult(
            output_path=image_path,
            metadata=metadata,
            warnings=(f"face detailer repaint failed: {exc}",),
        )

    composited = composite_face_crop(
        base,
        detail_crop,
        crop_box=crop_box,
        mask=crop_mask,
        feather=request.face_detailer.feather,
    )
    output_path = image_path.with_name(f"{image_path.stem}_face_detail.png")
    composited.save(output_path)
    metadata["status"] = "completed"
    metadata["output_path"] = str(output_path)
    return FaceDetailerStageResult(output_path=output_path, metadata=metadata)


def _skipped(image_path: Path, *, reason: str, warning: str) -> FaceDetailerStageResult:
    return FaceDetailerStageResult(
        output_path=image_path,
        metadata={"enabled": True, "status": "skipped", "reason": reason, "boxes": []},
        warnings=(warning,),
    )


class AnimeFaceDetailer:
    """Build anime face/eye masks using local detector assets."""

    def __init__(self, paths: AppPaths):
        self.paths = paths
        self.yolo_model = None
        self.eyes_model = None
        self.sam_model = None

    def build_mask(self, image: Image.Image, settings: FaceDetailerSettings) -> FaceDetailerMaskResult | None:
        missing = missing_detector_paths(self.paths)
        if missing:
            raise FileNotFoundError("missing face detailer detector assets: " + ", ".join(str(path) for path in missing))

        from ultralytics import SAM, YOLO

        expected = detector_paths(self.paths)
        device = self._select_device()
        if self.yolo_model is None:
            self.yolo_model = YOLO(str(expected.face)).to(device)
        if self.eyes_model is None:
            self.eyes_model = YOLO(str(expected.eyes)).to(device)
        if self.sam_model is None:
            self.sam_model = SAM(str(expected.sam)).to(device)

        boxes = self._detect_boxes(image, settings.threshold)
        if not boxes:
            return None

        image_np = np.array(image.convert("RGB"))
        combined_mask = np.zeros(image_np.shape[:2], dtype=np.uint8)
        try:
            sam_results = self.sam_model(image_np, bboxes=[list(box) for box in boxes], verbose=False)
            if sam_results and sam_results[0].masks is not None:
                for mask_tensor in sam_results[0].masks.data:
                    mask_np = mask_tensor.cpu().numpy()
                    mask_image = Image.fromarray((mask_np * 255).astype(np.uint8)).resize(image.size, Image.NEAREST)
                    combined_mask = np.maximum(combined_mask, np.array(mask_image))
        except Exception:
            for box in boxes:
                x1, y1, x2, y2 = [int(value) for value in box]
                combined_mask[y1:y2, x1:x2] = 255

        grid_mask = align_mask_to_grid(combined_mask)
        return FaceDetailerMaskResult(
            mask=Image.fromarray(grid_mask),
            boxes=tuple(boxes),
            detector=settings.detector,
        )

    def _detect_boxes(self, image: Image.Image, threshold: float) -> list[tuple[float, float, float, float]]:
        boxes: list[tuple[float, float, float, float]] = []
        for model in (self.yolo_model, self.eyes_model):
            results = model(image, conf=threshold, verbose=False)
            if results and len(results[0].boxes) > 0:
                for box in results[0].boxes.xyxy.cpu().numpy():
                    boxes.append(tuple(float(value) for value in box))
        return boxes

    @staticmethod
    def _select_device() -> str:
        import torch

        if torch.backends.mps.is_available():
            return "mps"
        if torch.cuda.is_available():
            try:
                capability = torch.cuda.get_device_capability(torch.cuda.current_device())
                arch = f"sm_{capability[0]}{capability[1]}"
                supported_arches = set(torch.cuda.get_arch_list())
                if supported_arches and arch not in supported_arches:
                    return "cpu"
            except Exception:
                return "cpu"
            return "cuda"
        return "cpu"

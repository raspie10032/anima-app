from __future__ import annotations

import math
import time
import warnings
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

from anima_app.config import AppPaths
from anima_app.requests import MAX_OUTPUT_IMAGE_PIXELS, MAX_PROMPT_CHARACTERS


SAM3_DETECTOR = "sam3.pt"
MAX_SEGMENT_PROMPTS = 12


@dataclass(frozen=True)
class Sam3SegmentResult:
    prompt: str
    source_path: Path
    mask_path: Path
    overlay_path: Path
    boxes: tuple[tuple[float, float, float, float], ...]
    scores: tuple[float, ...]


@dataclass(frozen=True)
class Sam3MaskAdjustmentResult:
    source_path: Path
    mask_path: Path
    overlay_path: Path
    crop_path: Path
    crop_mask_path: Path
    crop_box: tuple[int, int, int, int]
    dilation: int
    feather: int


def sam3_model_path(paths: AppPaths) -> Path:
    return paths.model_root / "detectors" / SAM3_DETECTOR


def resolve_segment_source(image_path: str, paths: AppPaths) -> Path:
    raw = str(image_path or "").strip()
    if not raw:
        raise ValueError("image_path is required")
    if raw.startswith("/outputs/images/"):
        candidate = paths.image_root / Path(raw).name
    else:
        requested = Path(raw)
        candidate = requested if requested.is_absolute() else paths.project_root / requested
    resolved = candidate.resolve()
    allowed_roots = (paths.image_root.resolve(), paths.input_root.resolve())
    if not any(_is_relative_to(resolved, root) for root in allowed_roots):
        raise ValueError("image_path must be under outputs/images or inputs")
    if not resolved.is_file():
        raise FileNotFoundError(f"missing SAM3 source image: {image_path}")
    return resolved


def segment_image_concept(
    image_path: str,
    *,
    prompt: str,
    paths: AppPaths,
    threshold: float = 0.25,
) -> Sam3SegmentResult:
    return segment_image_concepts(
        image_path,
        prompts=(prompt,),
        paths=paths,
        threshold=threshold,
    )[0]


def segment_image_concepts(
    image_path: str,
    *,
    prompts: tuple[str, ...] | list[str],
    paths: AppPaths,
    threshold: float = 0.25,
) -> tuple[Sam3SegmentResult, ...]:
    normalized_prompts = _normalize_prompts(prompts)
    _validate_threshold(threshold)

    model_path = sam3_model_path(paths)
    if not model_path.is_file():
        raise FileNotFoundError(f"missing SAM3 detector asset: {model_path}")

    source_path = resolve_segment_source(image_path, paths)
    image = _load_bounded_image(source_path, mode="RGB", label="source image")
    image_np = np.array(image)

    from ultralytics.models.sam import SAM3SemanticPredictor

    device = _select_device()
    predictor = SAM3SemanticPredictor(
        overrides={
            "conf": threshold,
            "task": "segment",
            "mode": "predict",
            "model": str(model_path),
            "half": device == "cuda",
            "verbose": False,
            "save": False,
            "device": device,
        }
    )
    predictor.set_image(image_np)
    segment_results = []
    for prompt in normalized_prompts:
        results = predictor(text=[prompt])
        segment_results.append(_write_segment_result(source_path, image, image_np, prompt, results, paths))
    return tuple(segment_results)


def adjust_segment_mask(
    image_path: str,
    *,
    mask_path: str,
    paths: AppPaths,
    dilation: int = 0,
    feather: int = 0,
    threshold: int = 8,
    crop_padding: int = 96,
) -> Sam3MaskAdjustmentResult:
    _validate_mask_adjustment(dilation=dilation, feather=feather, threshold=threshold, crop_padding=crop_padding)
    source_path = resolve_segment_source(image_path, paths)
    resolved_mask = resolve_mask_path(mask_path, paths)
    image = _load_bounded_image(source_path, mode="RGB", label="source image")
    mask = _load_bounded_image(resolved_mask, mode="L", label="mask image")
    if mask.size != image.size:
        mask = mask.resize(image.size, Image.NEAREST)
    adjusted = mask.point(lambda value: 255 if value > threshold else 0)
    adjusted = _dilate_mask(adjusted, dilation)
    if feather > 0:
        adjusted = adjusted.filter(ImageFilter.GaussianBlur(radius=feather))
    crop_box = _mask_crop_box(adjusted, image.size, padding=crop_padding)
    paths.image_root.mkdir(parents=True, exist_ok=True)
    stem = f"{resolved_mask.stem}_d{dilation}_f{feather}"
    adjusted_mask_path = paths.image_root / f"{stem}_mask.png"
    overlay_path = paths.image_root / f"{stem}_overlay.png"
    crop_path = paths.image_root / f"{stem}_crop.png"
    crop_mask_path = paths.image_root / f"{stem}_crop_mask.png"
    adjusted.save(adjusted_mask_path)
    _make_overlay(image, adjusted).save(overlay_path)
    image.crop(crop_box).save(crop_path)
    adjusted.crop(crop_box).save(crop_mask_path)
    return Sam3MaskAdjustmentResult(
        source_path=source_path,
        mask_path=adjusted_mask_path,
        overlay_path=overlay_path,
        crop_path=crop_path,
        crop_mask_path=crop_mask_path,
        crop_box=crop_box,
        dilation=dilation,
        feather=feather,
    )


def resolve_mask_path(mask_path: str, paths: AppPaths) -> Path:
    raw = str(mask_path or "").strip()
    if not raw:
        raise ValueError("mask_path is required")
    if raw.startswith("/outputs/images/"):
        candidate = paths.image_root / Path(raw).name
    else:
        requested = Path(raw)
        candidate = requested if requested.is_absolute() else paths.project_root / requested
    resolved = candidate.resolve()
    image_root = paths.image_root.resolve()
    if not _is_relative_to(resolved, image_root):
        raise ValueError("mask_path must be under outputs/images")
    if not resolved.is_file():
        raise FileNotFoundError(f"missing SAM3 mask image: {mask_path}")
    return resolved


def _write_segment_result(
    source_path: Path,
    image: Image.Image,
    image_np: np.ndarray,
    prompt: str,
    results: object,
    paths: AppPaths,
) -> Sam3SegmentResult:
    result = results[0] if results else None

    combined_mask = np.zeros(image_np.shape[:2], dtype=np.uint8)
    boxes: list[tuple[float, float, float, float]] = []
    scores: list[float] = []
    if result and result.masks is not None:
        for mask_tensor in result.masks.data:
            mask_np = mask_tensor.cpu().numpy()
            mask_image = Image.fromarray((mask_np * 255).astype(np.uint8)).resize(image.size, Image.NEAREST)
            combined_mask = np.maximum(combined_mask, np.array(mask_image))
    if result and result.boxes is not None:
        raw_boxes = result.boxes.xyxy.cpu().numpy()
        boxes = [tuple(float(value) for value in box) for box in raw_boxes]
        if getattr(result.boxes, "conf", None) is not None:
            scores = [float(value) for value in result.boxes.conf.cpu().numpy()]

    mask = Image.fromarray(combined_mask, mode="L")
    paths.image_root.mkdir(parents=True, exist_ok=True)
    stem = _segment_stem(source_path, prompt)
    mask_path = paths.image_root / f"{stem}_sam3_mask.png"
    overlay_path = paths.image_root / f"{stem}_sam3_overlay.png"
    mask.save(mask_path)
    _make_overlay(image, mask).save(overlay_path)
    return Sam3SegmentResult(
        prompt=prompt,
        source_path=source_path,
        mask_path=mask_path,
        overlay_path=overlay_path,
        boxes=tuple(boxes),
        scores=tuple(scores),
    )


def _validate_mask_adjustment(*, dilation: int, feather: int, threshold: int, crop_padding: int) -> None:
    if dilation < 0 or dilation > 128:
        raise ValueError("dilation must be between 0 and 128")
    if feather < 0 or feather > 64:
        raise ValueError("feather must be between 0 and 64")
    if threshold < 0 or threshold > 255:
        raise ValueError("threshold must be between 0 and 255")
    if crop_padding < 0 or crop_padding > 512:
        raise ValueError("crop_padding must be between 0 and 512")


def _dilate_mask(mask: Image.Image, dilation: int) -> Image.Image:
    if dilation <= 0:
        return mask
    adjusted = mask
    full_steps, remainder = divmod(dilation, 8)
    for _ in range(full_steps):
        adjusted = adjusted.filter(ImageFilter.MaxFilter(17))
    if remainder > 0:
        size = remainder * 2 + 1
        adjusted = adjusted.filter(ImageFilter.MaxFilter(size))
    return adjusted


def _mask_crop_box(mask: Image.Image, image_size: tuple[int, int], *, padding: int) -> tuple[int, int, int, int]:
    array = np.asarray(mask)
    ys, xs = np.where(array > 0)
    width, height = image_size
    if len(xs) == 0 or len(ys) == 0:
        return (0, 0, width, height)
    left = max(0, int(xs.min()) - padding)
    top = max(0, int(ys.min()) - padding)
    right = min(width, int(xs.max()) + padding + 1)
    bottom = min(height, int(ys.max()) + padding + 1)
    return left, top, right, bottom


def _normalize_prompts(prompts: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    normalized: list[str] = []
    seen: set[str] = set()
    for prompt in prompts:
        raw_value = str(prompt or "")
        if len(raw_value) > MAX_PROMPT_CHARACTERS:
            raise ValueError(f"SAM3 prompt must not exceed {MAX_PROMPT_CHARACTERS} characters")
        value = raw_value.strip()
        key = value.lower()
        if value and key not in seen:
            normalized.append(value)
            seen.add(key)
    if not normalized:
        raise ValueError("prompt is required")
    if len(normalized) > MAX_SEGMENT_PROMPTS:
        raise ValueError(f"at most {MAX_SEGMENT_PROMPTS} SAM3 prompts can be compared at once")
    return tuple(normalized)


def _validate_threshold(threshold: float) -> None:
    if not math.isfinite(threshold) or threshold < 0 or threshold > 1:
        raise ValueError("threshold must be finite and between 0 and 1")


def _load_bounded_image(path: Path, *, mode: str, label: str) -> Image.Image:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(path) as opened:
                width, height = opened.size
                if width * height > MAX_OUTPUT_IMAGE_PIXELS:
                    raise ValueError(f"{label} must not exceed {MAX_OUTPUT_IMAGE_PIXELS} pixels")
                return opened.convert(mode)
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ValueError(f"{label} exceeds safe decompression limits") from exc


def _make_overlay(image: Image.Image, mask: Image.Image) -> Image.Image:
    base = image.convert("RGBA")
    overlay = Image.new("RGBA", base.size, (0, 210, 130, 0))
    alpha = mask.point(lambda value: 120 if value > 0 else 0)
    overlay.putalpha(alpha)
    return Image.alpha_composite(base, overlay).convert("RGB")


def _segment_stem(source_path: Path, prompt: str) -> str:
    safe_prompt = "".join(char.lower() if char.isalnum() else "-" for char in prompt).strip("-")
    while "--" in safe_prompt:
        safe_prompt = safe_prompt.replace("--", "-")
    return f"{source_path.stem}_{safe_prompt[:48] or 'concept'}_{int(time.time())}"


def _select_device() -> str:
    import torch

    if torch.cuda.is_available():
        try:
            device_name = torch.cuda.get_device_name(torch.cuda.current_device()).lower()
            if "5060" in device_name:
                return "cpu"
        except Exception:
            return "cpu"
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True

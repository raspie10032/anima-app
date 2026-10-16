from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

from anima_app.comfy_runtime import bootstrap_comfy_runtime
from anima_app.config import AppPaths
from anima_app.gpu import configure_default_cuda_device
from anima_app.requests import (
    MAX_BASE_IMAGE_PIXELS,
    MAX_CFG,
    MAX_GENERATION_DIMENSION,
    MAX_OUTPUT_IMAGE_PIXELS,
    MAX_PROMPT_CHARACTERS,
    MAX_SAMPLING_STEPS,
    MAX_SEED,
    T2ILoraConfig,
    T2IRequest,
    VaeDecodeSettings,
)
from anima_app.runtime.comfy_t2i import (
    _load_models,
    _decode_samples,
    _encode_prompt,
    _normalize_sampler,
    _normalize_scheduler,
    _pil_to_image_tensor,
    _require_model_files,
    default_model_paths,
)
from anima_app.runtime.sam3_segment import resolve_mask_path, resolve_segment_source


MASKED_INPAINT_METHODS = {"noise_mask", "vae_inpaint", "crop_i2i_composite"}


@dataclass(frozen=True)
class MaskedInpaintSettings:
    image_path: str
    mask_path: str
    prompt: str
    checkpoint: str
    loras: tuple[T2ILoraConfig, ...] = ()
    negative_prompt: str = ""
    method: str = "noise_mask"
    denoise: float = 0.65
    steps: int = 20
    cfg: float = 3.5
    seed: int | None = None
    width: int | None = None
    height: int | None = None


@dataclass(frozen=True)
class MaskedInpaintResult:
    output_path: Path
    crop_path: Path
    crop_box: tuple[int, int, int, int]
    method: str
    seed: int


def run_masked_inpaint(settings: MaskedInpaintSettings, *, paths: AppPaths) -> MaskedInpaintResult:
    import torch
    _validate_settings(settings)
    source_path = resolve_segment_source(settings.image_path, paths)
    mask_path = resolve_mask_path(settings.mask_path, paths)
    with Image.open(source_path) as opened:
        _validate_output_image_size(opened.size, "source image")
        base = opened.convert("RGB")
    with Image.open(mask_path) as opened:
        _validate_output_image_size(opened.size, "mask image")
        mask = opened.convert("L")
    if mask.size != base.size:
        mask = mask.resize(base.size, Image.NEAREST)
    crop_box = _mask_crop_box(mask, base.size, padding=96)
    crop = base.crop(crop_box)
    crop_mask = mask.crop(crop_box)
    width = settings.width or _nearest_multiple(crop.width, 8)
    height = settings.height or _nearest_multiple(crop.height, 8)
    _validate_render_size(width, height)
    seed = settings.seed if settings.seed is not None else int(torch.randint(0, 2**31 - 1, (1,)).item())
    request = T2IRequest(
        prompt=settings.prompt,
        negative_prompt=settings.negative_prompt,
        checkpoint=settings.checkpoint,
        loras=settings.loras,
        width=width,
        height=height,
        steps=settings.steps,
        cfg=settings.cfg,
        seed=seed,
    )
    detail = _render_masked_crop(
        crop,
        crop_mask,
        request=request,
        paths=paths,
        method=settings.method,
        denoise=settings.denoise,
    )
    if detail.size != crop.size:
        detail = detail.resize(crop.size, Image.LANCZOS)
    result = base.copy()
    result.paste(detail, crop_box, crop_mask)
    stem = f"{source_path.stem}_inpaint_{settings.method}_s{seed}"
    output_path = paths.image_root / f"{stem}.png"
    crop_path = paths.image_root / f"{stem}_crop.png"
    paths.image_root.mkdir(parents=True, exist_ok=True)
    detail.save(crop_path)
    result.save(output_path)
    return MaskedInpaintResult(
        output_path=output_path,
        crop_path=crop_path,
        crop_box=crop_box,
        method=settings.method,
        seed=seed,
    )


def _render_masked_crop(
    crop: Image.Image,
    crop_mask: Image.Image,
    *,
    request: T2IRequest,
    paths: AppPaths,
    method: str,
    denoise: float,
) -> Image.Image:
    import torch
    configure_default_cuda_device()
    bootstrap_comfy_runtime(paths)
    model_paths = default_model_paths(paths, checkpoint=request.checkpoint)
    _require_model_files(model_paths)

    import comfy.sample
    import comfy.sd
    import comfy.utils
    import folder_paths

    model, clip, _resolved_loras, vae = _load_models(model_paths, request.loras)
    positive = _encode_prompt(clip, request.prompt)
    negative = _encode_prompt(clip, request.negative_prompt)

    pixels = _pil_to_image_tensor(crop, request.width, request.height)
    if method == "vae_inpaint":
        pixels = _apply_gray_hole(pixels, crop_mask, request.width, request.height)
    with torch.inference_mode():
        encoded = vae.encode(pixels)
    latent_image = comfy.sample.fix_empty_latent_channels(model, encoded, None, None)
    noise_mask = None
    if method in {"noise_mask", "vae_inpaint"}:
        noise_mask = _latent_noise_mask(crop_mask, latent_image)
    noise = comfy.sample.prepare_noise(latent_image, request.seed or 0, None)
    samples = comfy.sample.sample(
        model,
        noise,
        request.steps,
        request.cfg,
        _normalize_sampler(request.sampler),
        _normalize_scheduler(request.scheduler),
        positive,
        negative,
        latent_image,
        denoise=denoise,
        noise_mask=noise_mask,
        callback=None,
        disable_pbar=False,
        seed=request.seed or 0,
    )
    decoded, _method = _decode_samples(vae, samples, VaeDecodeSettings(mode="standard"))
    return _tensor_to_pil(decoded)


def _apply_gray_hole(pixels: torch.Tensor, mask: Image.Image, width: int, height: int) -> torch.Tensor:
    import torch
    mask_array = np.asarray(mask.resize((width, height), Image.LANCZOS), dtype=np.float32) / 255.0
    mask_tensor = torch.from_numpy((mask_array > 0.06).astype(np.float32)).unsqueeze(0).unsqueeze(-1)
    return pixels * (1.0 - mask_tensor) + 0.5 * mask_tensor


def _latent_noise_mask(mask: Image.Image, latent_image: torch.Tensor) -> torch.Tensor:
    import torch
    latent_height = latent_image.shape[-2]
    latent_width = latent_image.shape[-1]
    mask_array = np.asarray(mask.resize((latent_width, latent_height), Image.LANCZOS), dtype=np.float32) / 255.0
    return torch.from_numpy((mask_array > 0.06).astype(np.float32)).unsqueeze(0).unsqueeze(0)


def _tensor_to_pil(tensor: torch.Tensor) -> Image.Image:
    import torch
    image = tensor.detach().to("cpu", torch.float32)
    while image.dim() > 3:
        image = image[0]
    array = ((image.clamp(0, 1) * 255 + 0.5).to(torch.uint8)).contiguous().numpy()
    return Image.fromarray(array, "RGB")


def _mask_crop_box(mask: Image.Image, image_size: tuple[int, int], *, padding: int) -> tuple[int, int, int, int]:
    array = np.asarray(mask)
    ys, xs = np.where(array > 0)
    width, height = image_size
    if len(xs) == 0 or len(ys) == 0:
        return (0, 0, width, height)
    return (
        max(0, int(xs.min()) - padding),
        max(0, int(ys.min()) - padding),
        min(width, int(xs.max()) + padding + 1),
        min(height, int(ys.max()) + padding + 1),
    )


def _nearest_multiple(value: int, divisor: int) -> int:
    return max(divisor, round(value / divisor) * divisor)


def _validate_settings(settings: MaskedInpaintSettings) -> None:
    if settings.method not in MASKED_INPAINT_METHODS:
        raise ValueError("masked inpaint method must be one of: crop_i2i_composite, noise_mask, vae_inpaint")
    if not settings.prompt.strip():
        raise ValueError("prompt is required")
    if len(settings.prompt) > MAX_PROMPT_CHARACTERS:
        raise ValueError(f"prompt must not exceed {MAX_PROMPT_CHARACTERS} characters")
    if len(settings.negative_prompt) > MAX_PROMPT_CHARACTERS:
        raise ValueError(f"negative prompt must not exceed {MAX_PROMPT_CHARACTERS} characters")
    if not math.isfinite(settings.denoise) or settings.denoise < 0 or settings.denoise > 1:
        raise ValueError("denoise must be finite and between 0 and 1")
    if (
        isinstance(settings.steps, bool)
        or not isinstance(settings.steps, int)
        or settings.steps <= 0
        or settings.steps > MAX_SAMPLING_STEPS
    ):
        raise ValueError(f"steps must be an integer between 1 and {MAX_SAMPLING_STEPS}")
    if not math.isfinite(settings.cfg) or settings.cfg < 0 or settings.cfg > MAX_CFG:
        raise ValueError(f"cfg must be finite and between 0 and {MAX_CFG:g}")
    if settings.seed is not None and (
        isinstance(settings.seed, bool)
        or not isinstance(settings.seed, int)
        or settings.seed < 0
        or settings.seed > MAX_SEED
    ):
        raise ValueError(f"seed must be an integer between 0 and {MAX_SEED}")
    _validate_requested_dimension(settings.width, "width")
    _validate_requested_dimension(settings.height, "height")
    if settings.width is not None and settings.height is not None:
        _validate_render_size(settings.width, settings.height)


def _validate_requested_dimension(value: int | None, label: str) -> None:
    if value is None:
        return
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < 8
        or value > MAX_GENERATION_DIMENSION
        or value % 8
    ):
        raise ValueError(
            f"{label} must be an integer between 8 and {MAX_GENERATION_DIMENSION} and divisible by 8"
        )


def _validate_render_size(width: int, height: int) -> None:
    if width > MAX_GENERATION_DIMENSION or height > MAX_GENERATION_DIMENSION:
        raise ValueError(f"width and height must be <= {MAX_GENERATION_DIMENSION}")
    if width * height > MAX_BASE_IMAGE_PIXELS:
        raise ValueError(f"masked inpaint render must not exceed {MAX_BASE_IMAGE_PIXELS} pixels")


def _validate_output_image_size(size: tuple[int, int], label: str) -> None:
    width, height = size
    if width * height > MAX_OUTPUT_IMAGE_PIXELS:
        raise ValueError(f"{label} must not exceed {MAX_OUTPUT_IMAGE_PIXELS} pixels")

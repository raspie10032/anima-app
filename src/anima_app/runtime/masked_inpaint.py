from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import torch
from PIL import Image

from anima_app.comfy_runtime import bootstrap_comfy_runtime
from anima_app.config import AppPaths
from anima_app.gpu import configure_default_cuda_device
from anima_app.requests import T2ILoraConfig, T2IRequest, VaeDecodeSettings
from anima_app.runtime.comfy_t2i import (
    _apply_loras,
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
    _validate_settings(settings)
    source_path = resolve_segment_source(settings.image_path, paths)
    mask_path = resolve_mask_path(settings.mask_path, paths)
    with Image.open(source_path) as opened:
        base = opened.convert("RGB")
    with Image.open(mask_path) as opened:
        mask = opened.convert("L")
    if mask.size != base.size:
        mask = mask.resize(base.size, Image.NEAREST)
    crop_box = _mask_crop_box(mask, base.size, padding=96)
    crop = base.crop(crop_box)
    crop_mask = mask.crop(crop_box)
    width = settings.width or _nearest_multiple(crop.width, 8)
    height = settings.height or _nearest_multiple(crop.height, 8)
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
    configure_default_cuda_device()
    bootstrap_comfy_runtime(paths)
    model_paths = default_model_paths(paths, checkpoint=request.checkpoint)
    _require_model_files(model_paths)

    import comfy.sample
    import comfy.sd
    import comfy.utils
    import folder_paths

    model = comfy.sd.load_diffusion_model(str(model_paths.diffusion_model), model_options={})
    clip = comfy.sd.load_clip(
        ckpt_paths=[str(model_paths.text_encoder)],
        embedding_directory=folder_paths.get_folder_paths("embeddings"),
        clip_type=comfy.sd.CLIPType.QWEN_IMAGE,
    )
    model, clip, _resolved_loras = _apply_loras(model, clip, request.loras)
    vae = comfy.sd.VAE(sd=comfy.utils.load_torch_file(str(model_paths.vae)))
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
    mask_array = np.asarray(mask.resize((width, height), Image.LANCZOS), dtype=np.float32) / 255.0
    mask_tensor = torch.from_numpy((mask_array > 0.06).astype(np.float32)).unsqueeze(0).unsqueeze(-1)
    return pixels * (1.0 - mask_tensor) + 0.5 * mask_tensor


def _latent_noise_mask(mask: Image.Image, latent_image: torch.Tensor) -> torch.Tensor:
    latent_height = latent_image.shape[-2]
    latent_width = latent_image.shape[-1]
    mask_array = np.asarray(mask.resize((latent_width, latent_height), Image.LANCZOS), dtype=np.float32) / 255.0
    return torch.from_numpy((mask_array > 0.06).astype(np.float32)).unsqueeze(0).unsqueeze(0)


def _tensor_to_pil(tensor: torch.Tensor) -> Image.Image:
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
    if settings.denoise < 0 or settings.denoise > 1:
        raise ValueError("denoise must be between 0 and 1")
    if settings.steps <= 0:
        raise ValueError("steps must be positive")
    if settings.cfg < 0:
        raise ValueError("cfg must be >= 0")
    if settings.width is not None and (settings.width <= 0 or settings.width % 8):
        raise ValueError("width must be positive and divisible by 8")
    if settings.height is not None and (settings.height <= 0 or settings.height % 8):
        raise ValueError("height must be positive and divisible by 8")

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import numpy as np
import torch
from PIL import Image, ImageOps

from anima_app.comfy_runtime import bootstrap_comfy_runtime
from anima_app.config import AppPaths
from anima_app.defaults import DEFAULT_T2I_CHECKPOINT
from anima_app.gpu import configure_default_cuda_device
from anima_app.output_names import allocate_output_path
from anima_app.requests import T2ILoraConfig, T2IRequest, VaeDecodeSettings
from anima_app.runtime.pipeline import T2IRenderOutput, latent_shape_for_request


@dataclass(frozen=True)
class T2IModelPaths:
    diffusion_model: Path
    text_encoder: Path
    vae: Path


def default_model_paths(paths: AppPaths, *, checkpoint: str = DEFAULT_T2I_CHECKPOINT) -> T2IModelPaths:
    return T2IModelPaths(
        diffusion_model=_diffusion_model_path(paths, checkpoint),
        text_encoder=paths.model_root / "text_encoders" / "qwen_3_06b_base.safetensors",
        vae=paths.model_root / "vae" / "qwen_image_vae.safetensors",
    )


def model_paths_for_request(request: T2IRequest, paths: AppPaths) -> T2IModelPaths:
    return default_model_paths(paths, checkpoint=request.checkpoint)


def _diffusion_model_path(paths: AppPaths, checkpoint: str) -> Path:
    root = (paths.model_root / "diffusion_models").resolve()
    candidate = (root / checkpoint).resolve()
    candidate.relative_to(root)
    return candidate


def render_t2i(request: T2IRequest, paths: AppPaths) -> T2IRenderOutput:
    configure_default_cuda_device()
    bootstrap_comfy_runtime(paths)
    model_paths = model_paths_for_request(request, paths)
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
    model, clip, resolved_loras = _apply_loras(model, clip, request.loras)
    vae = comfy.sd.VAE(sd=comfy.utils.load_torch_file(str(model_paths.vae)))

    positive = _encode_prompt(clip, request.prompt)
    negative = _encode_prompt(clip, request.negative_prompt)
    latent, denoise = _make_initial_latent(request, vae, paths)
    sampled = _sample_latent(
        model,
        positive,
        negative,
        latent,
        request=request,
        steps=request.steps,
        denoise=denoise,
    )
    output_path = allocate_output_path(request, paths=paths, status="generated")
    variants: dict[str, Path] = {}
    if request.upscale.enabled:
        original_decoded, _ = _decode_samples(vae, sampled["samples"], request.vae_decode)
        original_path = _variant_output_path(output_path, "original")
        _save_image_tensor(original_decoded, original_path)
        variants["original"] = original_path
        sampled = _upscale_latent_samples(
            sampled,
            request.upscale.scale,
            request.upscale.method,
            tiled=request.upscale.tiled,
            tile_size=request.upscale.tile_size,
            overlap=request.upscale.overlap,
        )
        sampled = _sample_latent(
            model,
            positive,
            negative,
            sampled,
            request=request,
            steps=request.upscale.steps,
            denoise=request.upscale.denoise,
        )
    decoded, vae_decode_method = _decode_samples(vae, sampled["samples"], request.vae_decode)
    _save_image_tensor(decoded, output_path)
    if request.upscale.enabled:
        variants["upscale"] = output_path
    else:
        variants["original"] = output_path
    face_detailer_stage: dict[str, object] | None = None
    warnings: tuple[str, ...] = ()
    if request.face_detailer.enabled:
        from anima_app.runtime.face_detailer import run_face_detailer

        def repaint_face_crop(crop: Image.Image, _crop_mask: Image.Image, repaint_request: T2IRequest, repaint_paths: AppPaths) -> Image.Image:
            return _repaint_face_crop(
                crop,
                request=repaint_request,
                paths=repaint_paths,
                model=model,
                vae=vae,
                positive=positive,
                negative=negative,
            )

        face_result = run_face_detailer(
            output_path,
            request=request,
            paths=paths,
            repaint=repaint_face_crop,
        )
        output_path = face_result.output_path
        variants["face_detailer"] = output_path
        face_detailer_stage = face_result.metadata
        warnings = face_result.warnings
    return T2IRenderOutput(
        output_path=output_path,
        stages=_build_renderer_stages(
            request,
            resolved_loras=resolved_loras,
            vae_decode_method=vae_decode_method,
            face_detailer_stage=face_detailer_stage,
        ),
        warnings=warnings,
        variants=variants,
    )


def _variant_output_path(output_path: Path, name: str) -> Path:
    return output_path.with_name(f"{output_path.stem}_{name}{output_path.suffix}")


def _require_model_files(model_paths: T2IModelPaths) -> None:
    missing = [str(path) for path in (model_paths.diffusion_model, model_paths.text_encoder, model_paths.vae) if not path.is_file()]
    if missing:
        raise FileNotFoundError("missing copied Anima T2I assets: " + ", ".join(missing))


def _encode_prompt(clip: object, text: str) -> object:
    tokens = clip.tokenize(text or "")
    return clip.encode_from_tokens_scheduled(tokens)


def _make_empty_latent(request: T2IRequest) -> dict[str, torch.Tensor | int]:
    shape = latent_shape_for_request(request)
    latent = torch.zeros(
        [shape["batch"], shape["channels"], shape["height"], shape["width"]],
        device=_intermediate_device(),
        dtype=_intermediate_dtype(),
    )
    return {"samples": latent, "downscale_ratio_spacial": shape["downscale_factor"]}


def _make_initial_latent(request: T2IRequest, vae: object, paths: AppPaths) -> tuple[dict[str, torch.Tensor | int], float]:
    if not request.i2i.enabled:
        return _make_empty_latent(request), 1.0

    image_path = _resolve_i2i_image_path(request.i2i.image_path, paths)
    pixels = _load_image_tensor(image_path, request.width, request.height)
    with torch.inference_mode():
        encoded = vae.encode(pixels)
    return {"samples": encoded}, request.i2i.denoise


def _resolve_i2i_image_path(image_path: str, paths: AppPaths) -> Path:
    requested = Path(image_path)
    candidates = [requested] if requested.is_absolute() else [paths.project_root / requested]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(f"missing i2i source image: {image_path}")


def _load_image_tensor(path: Path, width: int, height: int) -> torch.Tensor:
    with Image.open(path) as image:
        normalized = ImageOps.exif_transpose(image).convert("RGB")
    return _pil_to_image_tensor(normalized, width, height)


def _pil_to_image_tensor(image: Image.Image, width: int, height: int) -> torch.Tensor:
    normalized = image.convert("RGB")
    array = np.asarray(normalized, dtype=np.float32) / 255.0
    tensor = torch.from_numpy(array).unsqueeze(0)
    if tensor.shape[1] == height and tensor.shape[2] == width:
        return tensor
    return _resize_image_tensor(tensor, width, height)


def _resize_image_tensor(tensor: torch.Tensor, width: int, height: int, method: str = "bicubic") -> torch.Tensor:
    import comfy.utils

    channels_first = tensor.movedim(-1, 1)
    resized = comfy.utils.common_upscale(channels_first, width, height, method, "center")
    return resized.movedim(1, -1)


def _sample_latent(
    model: object,
    positive: object,
    negative: object,
    latent: dict[str, torch.Tensor | int],
    *,
    request: T2IRequest,
    steps: int,
    denoise: float,
) -> dict[str, torch.Tensor]:
    import comfy.sample

    latent_image = comfy.sample.fix_empty_latent_channels(
        model,
        latent["samples"],
        latent.get("downscale_ratio_spacial"),
        None,
    )
    noise = comfy.sample.prepare_noise(latent_image, request.seed or 0, None)
    samples = comfy.sample.sample(
        model,
        noise,
        steps,
        request.cfg,
        _normalize_sampler(request.sampler),
        _normalize_scheduler(request.scheduler),
        positive,
        negative,
        latent_image,
        denoise=denoise,
        noise_mask=None,
        callback=None,
        disable_pbar=False,
        seed=request.seed or 0,
    )
    return {"samples": samples}


def _upscale_latent_samples(
    latent: dict[str, torch.Tensor],
    scale: float,
    method: str,
    *,
    tiled: bool,
    tile_size: int,
    overlap: int,
) -> dict[str, torch.Tensor]:
    import comfy.utils

    samples = latent["samples"]
    if tiled:
        return {"samples": _tiled_common_upscale(samples, scale=scale, method=method, tile_size=tile_size, overlap=overlap)}
    width = round(samples.shape[-1] * scale)
    height = round(samples.shape[-2] * scale)
    return {"samples": comfy.utils.common_upscale(samples, width, height, method, "disabled")}


def _tiled_common_upscale(
    samples: torch.Tensor,
    *,
    scale: float,
    method: str,
    tile_size: int,
    overlap: int,
) -> torch.Tensor:
    import comfy.utils

    output_height = round(samples.shape[-2] * scale)
    output_width = round(samples.shape[-1] * scale)
    output = torch.zeros(
        (*samples.shape[:-2], output_height, output_width),
        device=samples.device,
        dtype=samples.dtype,
    )
    weights = torch.zeros_like(output)
    for y in _tile_starts(samples.shape[-2], tile_size=tile_size, overlap=overlap):
        for x in _tile_starts(samples.shape[-1], tile_size=tile_size, overlap=overlap):
            y2 = min(y + tile_size, samples.shape[-2])
            x2 = min(x + tile_size, samples.shape[-1])
            out_y1 = round(y * scale)
            out_x1 = round(x * scale)
            out_y2 = round(y2 * scale)
            out_x2 = round(x2 * scale)
            upscaled = comfy.utils.common_upscale(
                samples[..., y:y2, x:x2],
                out_x2 - out_x1,
                out_y2 - out_y1,
                method,
                "disabled",
            )
            output[..., out_y1:out_y2, out_x1:out_x2] += upscaled
            weights[..., out_y1:out_y2, out_x1:out_x2] += 1
    return output / weights.clamp_min(1)


def _tile_starts(length: int, *, tile_size: int, overlap: int) -> list[int]:
    if tile_size >= length:
        return [0]
    stride = tile_size - overlap
    starts = [0]
    while starts[-1] + tile_size < length:
        starts.append(min(starts[-1] + stride, length - tile_size))
    return starts


def _decode_samples(vae: object, samples: torch.Tensor, settings: VaeDecodeSettings) -> tuple[torch.Tensor, str]:
    with torch.inference_mode():
        if settings.mode in {"auto", "tiled"} and hasattr(vae, "decode_tiled"):
            return vae.decode_tiled(
                samples,
                tile_x=settings.tile_size,
                tile_y=settings.tile_size,
                overlap=settings.overlap,
            ), "tiled"
        if settings.mode == "tiled":
            raise ValueError("tiled VAE decode requested but runtime does not provide decode_tiled")
        return vae.decode(samples), "standard"


def _repaint_face_crop(
    crop: Image.Image,
    *,
    request: T2IRequest,
    paths: AppPaths,
    model: object,
    vae: object,
    positive: object,
    negative: object,
) -> Image.Image:
    width, height = _latent_aligned_size(crop.size)
    pixels = _pil_to_image_tensor(crop, width, height)
    with torch.inference_mode():
        encoded = vae.encode(pixels)
    sampled = _sample_latent(
        model,
        positive,
        negative,
        {"samples": encoded},
        request=request,
        steps=request.face_detailer.steps,
        denoise=request.face_detailer.denoise,
    )
    decoded, _method = _decode_samples(
        vae,
        sampled["samples"],
        VaeDecodeSettings(mode="standard", tile_size=request.vae_decode.tile_size, overlap=request.vae_decode.overlap),
    )
    detail = _tensor_to_pil_image(decoded)
    if detail.size != crop.size:
        detail = detail.resize(crop.size, Image.LANCZOS)
    return detail


def _latent_aligned_size(size: tuple[int, int]) -> tuple[int, int]:
    width, height = size
    return _nearest_multiple(width, 8), _nearest_multiple(height, 8)


def _nearest_multiple(value: int, divisor: int) -> int:
    return max(divisor, round(value / divisor) * divisor)


def _apply_loras(
    model: object,
    clip: object,
    loras: tuple[T2ILoraConfig, ...],
) -> tuple[object, object, list[Path]]:
    if not loras:
        return model, clip, []

    import comfy
    import folder_paths

    lora_roots = [Path(path) for path in folder_paths.get_folder_paths("loras")]
    current_model = model
    current_clip = clip
    resolved_paths: list[Path] = []
    for lora in loras:
        lora_path = _resolve_lora_path(lora, lora_roots)
        resolved_paths.append(lora_path)
        lora_data = comfy.utils.load_torch_file(str(lora_path), safe_load=True)
        current_model, current_clip = comfy.sd.load_lora_for_models(
            current_model,
            current_clip,
            lora_data,
            lora.model_strength,
            lora.clip_strength,
        )
    return current_model, current_clip, resolved_paths


def _build_renderer_stages(
    request: T2IRequest,
    *,
    resolved_loras: Sequence[Path],
    vae_decode_method: str,
    face_detailer_stage: dict[str, object] | None = None,
) -> dict[str, object]:
    face_stage = _face_detailer_stage_for_request(request, face_detailer_stage)
    return {
        "base_t2i": {
            "status": "completed",
            "checkpoint": request.checkpoint,
            "steps": request.steps,
            "cfg": request.cfg,
            "sampler": request.sampler,
            "scheduler": request.scheduler,
            "width": request.width,
            "height": request.height,
        },
        "loras": {
            "status": "completed" if request.loras else "disabled",
            "count": len(request.loras),
            "resolved_paths": [str(path) for path in resolved_loras],
        },
        "i2i": {
            "status": "completed" if request.i2i.enabled else "disabled",
            "image_path": request.i2i.image_path if request.i2i.enabled else "",
            "denoise": request.i2i.denoise,
        },
        "high_res_fix": {
            "status": "completed" if request.upscale.enabled else "disabled",
            "scale": request.upscale.scale,
            "steps": request.upscale.steps,
            "denoise": request.upscale.denoise,
            "method": request.upscale.method,
            "tiled": request.upscale.tiled,
            "tile_size": request.upscale.tile_size,
            "overlap": request.upscale.overlap,
            "output_width": round(request.width * request.upscale.scale) if request.upscale.enabled else request.width,
            "output_height": round(request.height * request.upscale.scale) if request.upscale.enabled else request.height,
        },
        "vae_decode": {
            "status": "completed",
            "mode": request.vae_decode.mode,
            "tile_size": request.vae_decode.tile_size,
            "overlap": request.vae_decode.overlap,
            "method": vae_decode_method,
        },
        "face_detailer": face_stage,
    }


def _face_detailer_stage_for_request(
    request: T2IRequest,
    face_detailer_stage: dict[str, object] | None,
) -> dict[str, object]:
    stage: dict[str, object] = {
        "status": "disabled",
        "reason": "",
        "detector": request.face_detailer.detector,
        "threshold": request.face_detailer.threshold,
        "crop_scale": request.face_detailer.crop_scale,
        "padding": request.face_detailer.padding,
        "feather": request.face_detailer.feather,
        "exclude_forehead_ratio": request.face_detailer.exclude_forehead_ratio,
        "steps": request.face_detailer.steps,
        "denoise": request.face_detailer.denoise,
    }
    if not request.face_detailer.enabled:
        return stage
    stage["status"] = "skipped"
    stage["reason"] = "face_detailer_not_executed"
    if face_detailer_stage:
        stage.update(face_detailer_stage)
        if stage.get("status") == "completed" and "reason" not in face_detailer_stage:
            stage["reason"] = ""
        else:
            stage.setdefault("reason", "")
    return stage


def _resolve_lora_path(lora: T2ILoraConfig, lora_roots: Sequence[Path]) -> Path:
    requested = Path(lora.path)
    if requested.is_absolute():
        if requested.is_file():
            return requested
        raise FileNotFoundError(f"missing lora file: {requested}")

    for root in lora_roots:
        candidate = (root / requested).resolve()
        if candidate.is_file():
            return candidate

    raise FileNotFoundError(f"missing lora file: {lora.path}")


def _save_image_tensor(tensor: torch.Tensor, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _tensor_to_pil_image(tensor).save(path)


def _tensor_to_pil_image(tensor: torch.Tensor) -> Image.Image:
    image = tensor.detach().to("cpu", torch.float32)
    while image.dim() > 3:
        image = image[0]
    array = ((image.clamp(0, 1) * 255 + 0.5).to(torch.uint8)).contiguous().numpy()
    return Image.fromarray(array, "RGB")


def _intermediate_device() -> torch.device | str:
    try:
        import comfy.model_management

        return comfy.model_management.intermediate_device()
    except Exception:
        return "cpu"


def _intermediate_dtype() -> torch.dtype:
    try:
        import comfy.model_management

        return comfy.model_management.intermediate_dtype()
    except Exception:
        return torch.float32


def _normalize_sampler(value: str) -> str:
    return "euler_ancestral" if value == "euler" else value


def _normalize_scheduler(value: str) -> str:
    return "sgm_uniform" if value == "normal" else value

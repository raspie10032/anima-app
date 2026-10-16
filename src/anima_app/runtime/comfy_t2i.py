from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path, PureWindowsPath
import time
from typing import TYPE_CHECKING, Sequence
import warnings

import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

from anima_app.assets import (
    MAX_LORA_UPLOAD_BYTES,
    MAX_REFERENCE_IMAGE_DIMENSION,
    MAX_REFERENCE_IMAGE_PIXELS,
    MAX_REFERENCE_UPLOAD_BYTES,
    REFERENCE_IMAGE_EXTENSIONS,
    asset_file_is_ready,
    required_t2i_model_files,
)
from anima_app.comfy_runtime import bootstrap_comfy_runtime
from anima_app.config import AppPaths
from anima_app.defaults import DEFAULT_T2I_CHECKPOINT
from anima_app.gpu import configure_default_cuda_device
from anima_app.output_names import allocate_output_path
from anima_app.requests import FaceDetailerSettings, T2ILoraConfig, T2IRequest, VaeDecodeSettings
from anima_app.runtime.pipeline import ModelsNotReadyError, T2IRenderOutput, latent_shape_for_request

if TYPE_CHECKING:
    import torch


FACE_DETAILER_TARGET_LONG_EDGE = 1536


@dataclass(frozen=True)
class T2IModelPaths:
    diffusion_model: Path
    text_encoder: Path
    vae: Path


class RuntimeMetrics:
    def __init__(self) -> None:
        import torch
        self.started_at = time.perf_counter()
        self.stages: dict[str, dict[str, object]] = {}
        self.cuda_available = bool(torch.cuda.is_available())
        if self.cuda_available:
            try:
                torch.cuda.reset_peak_memory_stats()
            except Exception:
                self.cuda_available = False

    def record(self, name: str, started_at: float) -> None:
        import torch
        elapsed_sec = round(time.perf_counter() - started_at, 3)
        payload: dict[str, object] = {"elapsed_sec": elapsed_sec}
        if self.cuda_available:
            try:
                payload["cuda_allocated_mb"] = _bytes_to_mb(torch.cuda.memory_allocated())
                payload["cuda_reserved_mb"] = _bytes_to_mb(torch.cuda.memory_reserved())
                payload["cuda_peak_allocated_mb"] = _bytes_to_mb(torch.cuda.max_memory_allocated())
                payload["cuda_peak_reserved_mb"] = _bytes_to_mb(torch.cuda.max_memory_reserved())
            except Exception as exc:
                payload["cuda_metrics_error"] = str(exc)
        self.stages[name] = payload

    def snapshot(self) -> dict[str, object]:
        import torch
        payload: dict[str, object] = {
            "status": "completed",
            "elapsed_sec": round(time.perf_counter() - self.started_at, 3),
            "cuda_available": self.cuda_available,
            "stages": self.stages,
        }
        if self.cuda_available:
            try:
                payload["cuda_peak_allocated_mb"] = _bytes_to_mb(torch.cuda.max_memory_allocated())
                payload["cuda_peak_reserved_mb"] = _bytes_to_mb(torch.cuda.max_memory_reserved())
            except Exception as exc:
                payload["cuda_metrics_error"] = str(exc)
        return payload


def default_model_paths(paths: AppPaths, *, checkpoint: str = DEFAULT_T2I_CHECKPOINT) -> T2IModelPaths:
    diffusion_model, text_encoder, vae = required_t2i_model_files(paths, checkpoint)
    return T2IModelPaths(
        diffusion_model=diffusion_model,
        text_encoder=text_encoder,
        vae=vae,
    )


def model_paths_for_request(request: T2IRequest, paths: AppPaths) -> T2IModelPaths:
    return default_model_paths(paths, checkpoint=request.checkpoint)


def render_t2i(request: T2IRequest, paths: AppPaths) -> T2IRenderOutput:
    metrics = RuntimeMetrics()
    configure_default_cuda_device()
    model_paths = model_paths_for_request(request, paths)
    _require_model_files(model_paths)
    bootstrap_comfy_runtime(paths)

    stage_started = time.perf_counter()
    model, clip, resolved_loras, vae = _load_models(model_paths, request.loras)
    metrics.record("load_models", stage_started)

    stage_started = time.perf_counter()
    positive = _encode_prompt(clip, request.prompt)
    negative = _encode_prompt(clip, request.negative_prompt)
    metrics.record("text_encode", stage_started)
    output_path = allocate_output_path(request, paths=paths, status="generated")
    variants: dict[str, Path] = {}
    if request.operation == "detail":
        # Preserve the full input; only the selected crops enter diffusion below.
        source = resolve_managed_reference_path(request.i2i.image_path, paths)
        with Image.open(source) as image:
            if image.size != (request.width, request.height):
                raise ValueError("detailer input dimensions must match the request")
            output_path.parent.mkdir(parents=True, exist_ok=True)
            image.convert("RGB").save(output_path)
        variants["original"] = output_path
        vae_decode_method = "not_required"
    else:
        stage_started = time.perf_counter()
        latent, denoise = _make_initial_latent(request, vae, paths)
        metrics.record("initial_latent", stage_started)
        stage_started = time.perf_counter()
        if request.operation == "upscale":
            sampled = latent
        else:
            sampled = _sample_latent(
                model,
                positive,
                negative,
                latent,
                request=request,
                steps=request.steps,
                denoise=denoise,
            )
        metrics.record("base_sample", stage_started)
        if request.upscale.enabled:
            stage_started = time.perf_counter()
            original_decoded, _ = _decode_samples(vae, sampled["samples"], request.vae_decode)
            original_path = _variant_output_path(output_path, "original")
            _save_image_tensor(original_decoded, original_path)
            variants["original"] = original_path
            metrics.record("original_decode_save", stage_started)
            stage_started = time.perf_counter()
            sampled = _upscale_latent_samples(
                sampled,
                request.upscale.scale,
                request.upscale.method,
                tiled=request.upscale.tiled,
                tile_size=request.upscale.tile_size,
                overlap=request.upscale.overlap,
            )
            metrics.record("latent_upscale", stage_started)
            stage_started = time.perf_counter()
            sampled = _sample_latent(
                model,
                positive,
                negative,
                sampled,
                request=request,
                steps=request.upscale.steps,
                denoise=request.upscale.denoise,
            )
            metrics.record("highres_sample", stage_started)
        stage_started = time.perf_counter()
        decoded, vae_decode_method = _decode_samples(vae, sampled["samples"], request.vae_decode)
        _save_image_tensor(decoded, output_path)
        metrics.record("vae_decode_save", stage_started)
        if request.upscale.enabled:
            variants["upscale"] = output_path
        else:
            variants["original"] = output_path
    face_detailer_stage: dict[str, object] | None = None
    detailer_stages: dict[str, dict[str, object]] = {}
    warnings: tuple[str, ...] = ()
    if request.face_detailer.enabled:
        from anima_app.runtime.face_detailer import cached_face_detailer, run_face_detailer

        detailer = cached_face_detailer(paths)

        for stage_key, variant_key, concepts, output_suffix, pass_settings, prompt_suffix, negative_suffix in _detailer_pass_specs(
            request.face_detailer
        ):
            pass_request = replace(
                request,
                prompt=f"{request.prompt}, {prompt_suffix}" if prompt_suffix else request.prompt,
                negative_prompt=f"{request.negative_prompt}, {negative_suffix}" if negative_suffix else request.negative_prompt,
                face_detailer=pass_settings,
            )
            pass_positive = _encode_prompt(clip, pass_request.prompt)
            pass_negative = _encode_prompt(clip, pass_request.negative_prompt)

            def repaint_detail_crop(
                crop: Image.Image,
                _crop_mask: Image.Image,
                repaint_request: T2IRequest,
                repaint_paths: AppPaths,
            ) -> Image.Image:
                return _repaint_face_crop(
                    crop,
                    request=repaint_request,
                    paths=repaint_paths,
                    model=model,
                    vae=vae,
                    positive=pass_positive,
                    negative=pass_negative,
                )

            stage_started = time.perf_counter()
            pass_result = run_face_detailer(
                output_path,
                request=pass_request,
                paths=paths,
                repaint=repaint_detail_crop,
                detailer=detailer,
                concepts=concepts,
                output_suffix=output_suffix,
            )
            metrics.record(stage_key, stage_started)
            output_path = pass_result.output_path
            detailer_stages[stage_key] = pass_result.metadata
            if pass_result.metadata.get("status") == "completed":
                variants[variant_key] = output_path
            warnings += pass_result.warnings

        pass_statuses = [stage.get("status") for stage in detailer_stages.values()]
        face_detailer_stage = {
            "enabled": True,
            "status": "completed" if "completed" in pass_statuses else "skipped",
            "reason": "" if "completed" in pass_statuses else ("no_targets" if not pass_statuses else "all_passes_skipped"),
            "passes": detailer_stages,
        }
        if "completed" in pass_statuses:
            face_detailer_stage["output_path"] = str(output_path)
            variants["face_detailer"] = output_path
    return T2IRenderOutput(
        output_path=output_path,
        stages=_build_renderer_stages(
            request,
            resolved_loras=resolved_loras,
            vae_decode_method=vae_decode_method,
            face_detailer_stage=face_detailer_stage,
            detailer_stages=detailer_stages,
            runtime_metrics=metrics.snapshot(),
        ),
        warnings=warnings,
        variants=variants,
    )


def _detailer_pass_specs(
    settings: FaceDetailerSettings,
) -> tuple[tuple[str, str, tuple[str, ...] | None, str, FaceDetailerSettings, str, str], ...]:
    if settings.mask_backend != "sam3":
        return (("face_detailer", "face_detailer", None, "face_detail", settings, "", ""),)

    passes = []
    if settings.sam3_face_eyes:
        passes.append(
            (
                "face_eye_detailer",
                "face_eye_detailer",
                ("face", "eyes"),
                "face_eye_detail",
                settings,
                "detailed face, detailed eyes, symmetrical eyes",
                "deformed face, malformed eyes, asymmetrical eyes",
            )
        )
    if settings.sam3_hands:
        passes.append(
            (
                "hand_detailer",
                "hand_detailer",
                ("hand", "hands"),
                "hand_detail",
                replace(settings, denoise=settings.hand_denoise, exclude_forehead_ratio=0.0),
                "detailed hands, five fingers, natural fingers",
                "bad hands, malformed hands, extra fingers, missing fingers, fused fingers",
            )
        )
    return tuple(passes)


def _variant_output_path(output_path: Path, name: str) -> Path:
    return output_path.with_name(f"{output_path.stem}_{name}{output_path.suffix}")


def _require_model_files(model_paths: T2IModelPaths) -> None:
    missing = tuple(
        path
        for path in (model_paths.diffusion_model, model_paths.text_encoder, model_paths.vae)
        if not asset_file_is_ready(path)
    )
    if missing:
        raise ModelsNotReadyError(missing)


def _load_models(model_paths, loras):
    from anima_app.runtime.model_cache import get_models
    return get_models(model_paths, loras, apply_loras=_apply_loras, resolve_lora=_resolve_lora_path)


def _encode_prompt(clip: object, text: str) -> object:
    from anima_app.runtime.model_cache import encode
    return encode(clip, text)


def _make_empty_latent(request: T2IRequest) -> dict[str, torch.Tensor | int]:
    import torch
    shape = latent_shape_for_request(request)
    latent = torch.zeros(
        [shape["batch"], shape["channels"], shape["height"], shape["width"]],
        device=_intermediate_device(),
        dtype=_intermediate_dtype(),
    )
    return {"samples": latent, "downscale_ratio_spacial": shape["downscale_factor"]}


def _make_initial_latent(request: T2IRequest, vae: object, paths: AppPaths) -> tuple[dict[str, torch.Tensor | int], float]:
    import torch
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


def resolve_managed_reference_path(reference_path: str, paths: AppPaths) -> Path:
    parts = _managed_relative_parts(reference_path, "managed reference")
    if parts[:2] == ("inputs", "references"):
        root = paths.input_root / "references"
    elif parts[:2] == ("outputs", "images"):
        root = paths.image_root
    else:
        raise ValueError("managed reference path must be under inputs/references or outputs/images")
    if len(parts) <= 2:
        raise ValueError("managed reference path must name a file")
    resolved = _resolve_managed_file(root, parts[2:], "managed reference")
    _validate_managed_reference_image(resolved)
    return resolved


def resolve_managed_lora_path(lora_path: str, paths: AppPaths) -> Path:
    parts = _managed_relative_parts(lora_path, "managed LoRA")
    relative = Path(*parts)
    if relative.suffix.lower() != ".safetensors":
        raise ValueError("managed LoRA path must use the .safetensors extension")
    resolved = _resolve_managed_file(paths.model_root / "loras", parts, "managed LoRA")
    if resolved.stat().st_size > MAX_LORA_UPLOAD_BYTES:
        raise ValueError(f"managed LoRA file size must not exceed {MAX_LORA_UPLOAD_BYTES} bytes")
    return resolved


def _managed_relative_parts(value: str, label: str) -> tuple[str, ...]:
    if not isinstance(value, str):
        raise ValueError(f"{label} path must be a relative string")
    raw = value.strip()
    normalized = raw.replace("\\", "/")
    windows_path = PureWindowsPath(raw)
    parts = tuple(normalized.split("/"))
    if (
        not raw
        or normalized.startswith("/")
        or windows_path.drive
        or windows_path.root
        or any(part in {"", ".", ".."} or ":" in part for part in parts)
    ):
        raise ValueError(f"{label} path must be a safe relative path")
    return parts


def _resolve_managed_file(root: Path, parts: Sequence[str], label: str) -> Path:
    resolved_root = root.resolve()
    try:
        candidate = root.joinpath(*parts).resolve()
        candidate.relative_to(resolved_root)
    except (OSError, RuntimeError, ValueError) as exc:
        raise ValueError(f"{label} path escapes its managed root") from exc
    if not candidate.is_file():
        raise FileNotFoundError(f"missing {label} file: {'/'.join(parts)}")
    return candidate


def _validate_managed_reference_image(path: Path) -> None:
    suffix = path.suffix.lower()
    if suffix not in REFERENCE_IMAGE_EXTENSIONS:
        raise ValueError(f"unsupported managed reference image format: {suffix or '(none)'}")
    if path.stat().st_size > MAX_REFERENCE_UPLOAD_BYTES:
        raise ValueError(f"managed reference image size must not exceed {MAX_REFERENCE_UPLOAD_BYTES} bytes")

    expected_format = {".png": "PNG", ".jpg": "JPEG", ".jpeg": "JPEG", ".webp": "WEBP"}[suffix]
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(path) as image:
                width, height = image.size
                actual_format = str(image.format or "").upper()
                frames = int(getattr(image, "n_frames", 1))
                if actual_format != expected_format:
                    raise ValueError("managed reference image extension does not match its encoded format")
                if frames != 1:
                    raise ValueError("managed reference image must contain exactly one frame")
                if max(width, height) > MAX_REFERENCE_IMAGE_DIMENSION:
                    raise ValueError(
                        f"managed reference image dimension must not exceed {MAX_REFERENCE_IMAGE_DIMENSION}"
                    )
                if width * height > MAX_REFERENCE_IMAGE_PIXELS:
                    raise ValueError(
                        f"managed reference image pixel count must not exceed {MAX_REFERENCE_IMAGE_PIXELS}"
                    )
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ValueError("managed reference image exceeds safe decompression limits") from exc
    except (OSError, UnidentifiedImageError) as exc:
        raise ValueError("unsupported or invalid managed reference image") from exc


def _load_image_tensor(path: Path, width: int, height: int) -> torch.Tensor:
    with Image.open(path) as image:
        normalized = ImageOps.exif_transpose(image).convert("RGB")
    return _pil_to_image_tensor(normalized, width, height)


def _pil_to_image_tensor(image: Image.Image, width: int, height: int) -> torch.Tensor:
    import torch
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
    import torch
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
    import torch
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
    import torch
    width, height = _face_detailer_render_size(crop.size)
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


def _face_detailer_render_size(size: tuple[int, int]) -> tuple[int, int]:
    width, height = size
    scale = max(1.0, FACE_DETAILER_TARGET_LONG_EDGE / max(width, height))
    return _nearest_multiple(round(width * scale), 8), _nearest_multiple(round(height * scale), 8)


def _nearest_multiple(value: int, divisor: int) -> int:
    return max(divisor, round(value / divisor) * divisor)


def _bytes_to_mb(value: int) -> float:
    return round(value / (1024 * 1024), 1)


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
    detailer_stages: dict[str, dict[str, object]] | None = None,
    runtime_metrics: dict[str, object] | None = None,
) -> dict[str, object]:
    face_stage = _face_detailer_stage_for_request(request, face_detailer_stage)
    stages: dict[str, object] = {
        "memory_profile": {
            "status": "completed",
            "profile": request.memory_profile,
            "upscale_tiled": request.upscale.tiled,
            "vae_decode_mode": request.vae_decode.mode,
            "output_width": round(request.width * request.upscale.scale) if request.upscale.enabled else request.width,
            "output_height": round(request.height * request.upscale.scale) if request.upscale.enabled else request.height,
        },
        "base_t2i": {
            "status": "completed" if request.operation == "generate" else "skipped",
            "operation": request.operation,
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
    if detailer_stages:
        stages.update(detailer_stages)
    if runtime_metrics is not None:
        stages["runtime_metrics"] = runtime_metrics
    return stages


def _face_detailer_stage_for_request(
    request: T2IRequest,
    face_detailer_stage: dict[str, object] | None,
) -> dict[str, object]:
    stage: dict[str, object] = {
        "status": "disabled",
        "reason": "",
        "detector": request.face_detailer.detector,
        "mask_backend": request.face_detailer.mask_backend,
        "threshold": request.face_detailer.threshold,
        "crop_scale": request.face_detailer.crop_scale,
        "padding": request.face_detailer.padding,
        "feather": request.face_detailer.feather,
        "exclude_forehead_ratio": request.face_detailer.exclude_forehead_ratio,
        "steps": request.face_detailer.steps,
        "denoise": request.face_detailer.denoise,
        "sam3_face_eyes": request.face_detailer.sam3_face_eyes,
        "sam3_hands": request.face_detailer.sam3_hands,
        "hand_denoise": request.face_detailer.hand_denoise,
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
    import torch
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
    import torch
    try:
        import comfy.model_management

        return comfy.model_management.intermediate_dtype()
    except Exception:
        return torch.float32


def _normalize_sampler(value: str) -> str:
    return "euler_ancestral" if value == "euler" else value


def _normalize_scheduler(value: str) -> str:
    return "sgm_uniform" if value == "normal" else value

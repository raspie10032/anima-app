from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from PIL import Image

from anima_app.config import AppPaths
from anima_app.manifests import write_t2i_manifest
from anima_app.png_metadata import build_a1111_parameters, embed_png_parameters
from anima_app.requests import T2IRequest


LATENT_DOWNSCALE_FACTOR = 8
ANIMA_LATENT_CHANNELS = 16


@dataclass(frozen=True)
class T2IResult:
    status: str
    manifest_path: Path
    output_path: Path | None = None
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class T2IRenderOutput:
    output_path: Path
    stages: dict[str, object] | None = None
    warnings: tuple[str, ...] = ()
    variants: dict[str, Path] | None = None


T2IRenderer = Callable[[T2IRequest, AppPaths], T2IRenderOutput]


def latent_shape_for_request(request: T2IRequest) -> dict[str, int]:
    return {
        "batch": 1,
        "channels": ANIMA_LATENT_CHANNELS,
        "height": request.height // LATENT_DOWNSCALE_FACTOR,
        "width": request.width // LATENT_DOWNSCALE_FACTOR,
        "source_width": request.width,
        "source_height": request.height,
        "downscale_factor": LATENT_DOWNSCALE_FACTOR,
    }


def run_t2i(
    request: T2IRequest,
    *,
    paths: AppPaths,
    dry_run: bool,
    renderer: T2IRenderer | None = None,
    wildcards: dict[str, object] | None = None,
) -> T2IResult:
    if not dry_run:
        if renderer is None:
            raise NotImplementedError("real rendering is not wired yet")
        rendered = renderer(request, paths)
        _validate_output_png(rendered.output_path, paths)
        for variant_path in (rendered.variants or {}).values():
            _validate_output_png(variant_path, paths)
        parameters = build_a1111_parameters(request, wildcards=wildcards)
        embed_png_parameters(rendered.output_path, parameters)
        _validate_output_png(rendered.output_path, paths)
        manifest_path = write_t2i_manifest(
            request,
            paths=paths,
            status="generated",
            output_path=rendered.output_path,
            latent=latent_shape_for_request(request),
            stages=rendered.stages,
            warnings=rendered.warnings,
            comfyui_runtime="renderer",
            wildcards=wildcards,
            png_metadata={"parameters": parameters},
            variants=rendered.variants,
        )
        return T2IResult(
            status="generated",
            manifest_path=manifest_path,
            output_path=rendered.output_path,
            warnings=rendered.warnings,
        )

    parameters = build_a1111_parameters(request, wildcards=wildcards)
    manifest_path = write_t2i_manifest(
        request,
        paths=paths,
        status="dry_run",
        output_path=None,
        latent=latent_shape_for_request(request),
        stages=dry_run_stages_for_request(request),
        wildcards=wildcards,
        png_metadata={"parameters": parameters},
    )
    return T2IResult(status="dry_run", manifest_path=manifest_path)


def dry_run_stages_for_request(request: T2IRequest) -> dict[str, object]:
    stages: dict[str, object] = {
        "vae_decode": {
            "status": "configured",
            "mode": request.vae_decode.mode,
            "tile_size": request.vae_decode.tile_size,
            "overlap": request.vae_decode.overlap,
            "method": "not_run",
        }
    }
    if request.face_detailer.enabled:
        stages["face_detailer"] = {
            "status": "skipped",
            "reason": "dry_run_not_executed",
            "detector": request.face_detailer.detector,
            "threshold": request.face_detailer.threshold,
            "crop_scale": request.face_detailer.crop_scale,
            "padding": request.face_detailer.padding,
            "feather": request.face_detailer.feather,
            "exclude_forehead_ratio": request.face_detailer.exclude_forehead_ratio,
            "steps": request.face_detailer.steps,
            "denoise": request.face_detailer.denoise,
        }
    return stages


def _validate_output_png(output_path: Path, paths: AppPaths) -> None:
    resolved = output_path.resolve()
    try:
        resolved.relative_to(paths.image_root.resolve())
    except ValueError as exc:
        raise ValueError(f"renderer output must be under image_root: {resolved}") from exc
    if not resolved.is_file():
        raise ValueError(f"renderer output does not exist: {resolved}")
    try:
        with Image.open(resolved) as image:
            image.verify()
            if image.format != "PNG":
                raise ValueError
    except Exception as exc:
        raise ValueError(f"renderer output is not a valid PNG: {resolved}") from exc

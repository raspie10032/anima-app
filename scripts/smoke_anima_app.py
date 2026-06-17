from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from anima_app.config import AppPaths
from anima_app.gpu import ensure_default_cuda_visible_devices
from anima_app.manifests import read_manifest
from anima_app.requests import FaceDetailerSettings, I2ISettings, T2ILoraConfig, T2IRequest, UpscaleSettings, VaeDecodeSettings
from anima_app.runtime.pipeline import T2IResult, run_t2i
from anima_app.wildcards import DEFAULT_WILDCARD_MODE, WILDCARD_MODES, expand_request_wildcards


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Smoke-test Anima APP generation inputs.")
    parser.add_argument("--project-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--prompt", default="anime portrait, clean lineart")
    parser.add_argument("--negative", default="low quality")
    parser.add_argument("--width", type=int, default=512)
    parser.add_argument("--height", type=int, default=768)
    parser.add_argument("--steps", type=int, default=28)
    parser.add_argument("--cfg", type=float, default=5.0)
    parser.add_argument("--sampler", default="euler")
    parser.add_argument("--scheduler", default="normal")
    parser.add_argument("--seed", type=int, default=123)
    parser.add_argument("--checkpoint", default="anima-base-v1.0.safetensors")
    parser.add_argument("--dry-run", action="store_true", help="Record the request without loading models.")
    parser.add_argument("--require-checks", action="store_true", help="Return non-zero if smoke checks fail.")
    parser.add_argument("--lora", action="append", default=[], help="LoRA spec: path|model_strength|clip_strength")
    parser.add_argument("--image", default="", help="Enable I2I with this source image path.")
    parser.add_argument("--denoise", type=float, default=0.35)
    parser.add_argument("--upscale", action="store_true")
    parser.add_argument("--upscale-scale", type=float, default=1.5)
    parser.add_argument("--upscale-steps", type=int, default=12)
    parser.add_argument("--upscale-denoise", type=float, default=0.35)
    parser.add_argument("--upscale-method", default="bicubic")
    parser.add_argument("--upscale-tiled", action="store_true")
    parser.add_argument("--upscale-tile-size", type=int, default=64)
    parser.add_argument("--upscale-overlap", type=int, default=8)
    parser.add_argument("--vae-decode", choices=["auto", "tiled", "standard"], default="auto")
    parser.add_argument("--vae-tile-size", type=int, default=64)
    parser.add_argument("--vae-overlap", type=int, default=8)
    parser.add_argument("--face-detailer", action="store_true")
    parser.add_argument("--face-detector", default="default")
    parser.add_argument("--face-threshold", type=float, default=0.5)
    parser.add_argument("--face-crop-scale", type=float, default=1.5)
    parser.add_argument("--face-padding", type=int, default=32)
    parser.add_argument("--face-feather", type=int, default=24)
    parser.add_argument("--face-steps", type=int, default=12)
    parser.add_argument("--face-denoise", type=float, default=0.28)
    parser.add_argument("--wildcards", choices=sorted(WILDCARD_MODES), default=DEFAULT_WILDCARD_MODE)
    return parser


def request_from_args(args: argparse.Namespace) -> T2IRequest:
    return T2IRequest(
        prompt=args.prompt,
        negative_prompt=args.negative,
        width=args.width,
        height=args.height,
        steps=args.steps,
        cfg=args.cfg,
        sampler=args.sampler,
        scheduler=args.scheduler,
        seed=args.seed,
        checkpoint=args.checkpoint,
        loras=_parse_loras(args.lora),
        i2i=I2ISettings(enabled=bool(args.image), image_path=args.image, denoise=args.denoise),
        upscale=UpscaleSettings(
            enabled=args.upscale,
            scale=args.upscale_scale,
            steps=args.upscale_steps,
            denoise=args.upscale_denoise,
            method=args.upscale_method,
            tiled=args.upscale_tiled,
            tile_size=args.upscale_tile_size,
            overlap=args.upscale_overlap,
        ),
        face_detailer=FaceDetailerSettings(
            enabled=args.face_detailer,
            detector=args.face_detector,
            threshold=args.face_threshold,
            crop_scale=args.face_crop_scale,
            padding=args.face_padding,
            feather=args.face_feather,
            steps=args.face_steps,
            denoise=args.face_denoise,
        ),
        vae_decode=VaeDecodeSettings(
            mode=args.vae_decode,
            tile_size=args.vae_tile_size,
            overlap=args.vae_overlap,
        ),
    )


def _parse_loras(specs: Sequence[str]) -> tuple[T2ILoraConfig, ...]:
    return tuple(_parse_lora_spec(spec) for spec in specs)


def _parse_lora_spec(spec: str) -> T2ILoraConfig:
    parts = [part.strip() for part in spec.split("|")]
    if not parts or not parts[0]:
        raise ValueError("LoRA path is required")
    model_strength = float(parts[1]) if len(parts) >= 2 and parts[1] else 1.0
    clip_strength = float(parts[2]) if len(parts) >= 3 and parts[2] else model_strength
    if len(parts) > 3:
        raise ValueError(f"invalid LoRA spec: {spec}")
    return T2ILoraConfig(path=parts[0], model_strength=model_strength, clip_strength=clip_strength)


def expected_output_size(request: T2IRequest) -> tuple[int, int]:
    if request.upscale.enabled:
        return round(request.width * request.upscale.scale), round(request.height * request.upscale.scale)
    return request.width, request.height


def build_smoke_checks(
    *,
    result: T2IResult,
    manifest: dict[str, object],
    expected_width: int,
    expected_height: int,
) -> dict[str, object]:
    checks: dict[str, object] = {
        "manifest_exists": result.manifest_path.is_file(),
        "output_exists": result.output_path.is_file() if result.output_path else None,
        "manifest_output_matches": None,
        "output_is_png": None,
        "output_width": None,
        "output_height": None,
        "output_matches_request": None,
        "png_parameters_present": None,
        "png_parameters_matches_manifest": None,
        "pipeline": manifest.get("pipeline"),
    }
    if result.output_path is None:
        return checks

    manifest_output = manifest.get("output_path")
    checks["manifest_output_matches"] = str(result.output_path) == str(manifest_output)
    if not result.output_path.is_file():
        return checks

    with Image.open(result.output_path) as image:
        checks["output_is_png"] = image.format == "PNG"
        checks["output_width"] = image.width
        checks["output_height"] = image.height
        checks["output_matches_request"] = image.width == expected_width and image.height == expected_height
        parameters = image.text.get("parameters", "")
    manifest_parameters = ""
    png_metadata = manifest.get("png_metadata")
    if isinstance(png_metadata, dict):
        manifest_parameters = str(png_metadata.get("parameters", ""))
    checks["png_parameters_present"] = bool(parameters)
    checks["png_parameters_matches_manifest"] = bool(parameters) and parameters == manifest_parameters
    return checks


def smoke_checks_pass(checks: dict[str, object], *, require_output: bool) -> bool:
    if checks.get("manifest_exists") is not True:
        return False
    if not require_output:
        return True
    required = (
        "output_exists",
        "manifest_output_matches",
        "output_is_png",
        "output_matches_request",
        "png_parameters_present",
        "png_parameters_matches_manifest",
    )
    return all(checks.get(key) is True for key in required)


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.dry_run:
        ensure_default_cuda_visible_devices()
    paths = AppPaths(project_root=args.project_root)
    request = request_from_args(args)
    request, wildcard_expansion = expand_request_wildcards(request, paths=paths, mode=args.wildcards)
    result = run_t2i(
        request,
        paths=paths,
        dry_run=args.dry_run,
        renderer=None if args.dry_run else default_t2i_renderer,
        wildcards=wildcard_expansion,
    )
    manifest = read_manifest(result.manifest_path)
    expected_width, expected_height = expected_output_size(request)
    checks = build_smoke_checks(
        result=result,
        manifest=manifest,
        expected_width=expected_width,
        expected_height=expected_height,
    )
    payload = {
        "status": result.status,
        "manifest_path": str(result.manifest_path),
        "output_path": str(result.output_path) if result.output_path else None,
        "warnings": manifest.get("warnings", []),
        "stages": manifest.get("stages", {}),
        "wildcards": manifest.get("wildcards", {}),
        "checks": checks,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if args.require_checks and not smoke_checks_pass(checks, require_output=not args.dry_run):
        return 1
    return 0


def default_t2i_renderer(request: T2IRequest, paths: AppPaths):
    from anima_app.runtime.comfy_t2i import render_t2i

    return render_t2i(request, paths)


if __name__ == "__main__":
    raise SystemExit(main())

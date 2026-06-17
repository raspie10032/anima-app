from __future__ import annotations

import argparse
import json
import webbrowser
from pathlib import Path
from typing import Sequence

from anima_app.assets import (
    asset_profile,
    asset_profiles,
    copy_asset_profile,
    import_lora_file,
    list_local_checkpoints,
    list_local_loras,
    scan_model_source,
)
from anima_app.config import AppPaths, default_paths
from anima_app.defaults import (
    DEFAULT_T2I_CHECKPOINT,
    DEFAULT_T2I_CFG,
    DEFAULT_T2I_HEIGHT,
    DEFAULT_T2I_SAMPLER,
    DEFAULT_T2I_SCHEDULER,
    DEFAULT_T2I_STEPS,
    DEFAULT_T2I_WIDTH,
)
from anima_app.gpu import ensure_default_cuda_visible_devices
from anima_app.health import build_health_payload
from anima_app.manifests import read_manifest
from anima_app.requests import FaceDetailerSettings, I2ISettings, T2ILoraConfig, T2IRequest, UpscaleSettings, VaeDecodeSettings
from anima_app.runtime.pipeline import run_t2i
from anima_app.wildcards import DEFAULT_WILDCARD_MODE, WILDCARD_MODES, expand_request_wildcards
from anima_app.server import create_http_server


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="anima-app")
    subparsers = parser.add_subparsers(dest="command", required=True)

    health = subparsers.add_parser("health", help="print local runtime health")
    health.add_argument("--json", action="store_true", dest="as_json")

    models = subparsers.add_parser("models", help="inspect or copy model assets")
    model_subparsers = models.add_subparsers(dest="models_command", required=True)
    model_subparsers.add_parser("inventory", help="scan development model source")
    model_subparsers.add_parser("checkpoints", help="list copied local diffusion checkpoints")
    model_subparsers.add_parser("loras", help="list copied local LoRA files")
    import_lora = model_subparsers.add_parser("import-lora", help="copy an external LoRA into the project")
    import_lora.add_argument("path")
    copy_profile = model_subparsers.add_parser("copy-profile", help="copy a known asset profile")
    copy_profile.add_argument("profile", choices=[profile.name for profile in asset_profiles()])
    copy_profile.add_argument(
        "--source",
        choices=["auto", "local", "huggingface", "download"],
        default="auto",
        help="Use local files, remote download, or auto mode. For anima-t2i, huggingface/download use the Hugging Face source.",
    )

    t2i = subparsers.add_parser("t2i", help="generate an image from text")
    t2i.add_argument("--prompt", required=True)
    t2i.add_argument("--negative", default="")
    t2i.add_argument("--width", type=int, default=DEFAULT_T2I_WIDTH)
    t2i.add_argument("--height", type=int, default=DEFAULT_T2I_HEIGHT)
    t2i.add_argument("--steps", type=int, default=DEFAULT_T2I_STEPS)
    t2i.add_argument("--cfg", type=float, default=DEFAULT_T2I_CFG)
    t2i.add_argument("--seed", type=int)
    t2i.add_argument("--checkpoint", default=DEFAULT_T2I_CHECKPOINT, help="Diffusion checkpoint under models/diffusion_models.")
    t2i.add_argument("--sampler", default=DEFAULT_T2I_SAMPLER)
    t2i.add_argument("--scheduler", default=DEFAULT_T2I_SCHEDULER)
    t2i.add_argument("--image", default="", help="Reference image path for image-to-image generation.")
    t2i.add_argument("--denoise", type=float, default=0.35)
    t2i.add_argument("--upscale", action="store_true", help="Enable high-res fix/upscale stage.")
    t2i.add_argument("--upscale-scale", type=float, default=1.5)
    t2i.add_argument("--upscale-steps", type=int, default=12)
    t2i.add_argument("--upscale-denoise", type=float, default=0.35)
    t2i.add_argument("--upscale-method", default="bicubic")
    t2i.add_argument("--upscale-tiled", action="store_true", help="Upscale latent samples in overlapping tiles.")
    t2i.add_argument("--upscale-tile-size", type=int, default=64)
    t2i.add_argument("--upscale-overlap", type=int, default=8)
    t2i.add_argument("--vae-decode", choices=["auto", "tiled", "standard"], default="auto")
    t2i.add_argument("--vae-tile-size", type=int, default=64)
    t2i.add_argument("--vae-overlap", type=int, default=8)
    t2i.add_argument("--face-detailer", action="store_true", help="Enable optional face detailer stage.")
    t2i.add_argument("--face-detector", default="default")
    t2i.add_argument("--face-threshold", type=float, default=0.5)
    t2i.add_argument("--face-crop-scale", type=float, default=1.5)
    t2i.add_argument("--face-padding", type=int, default=32)
    t2i.add_argument("--face-feather", type=int, default=24)
    t2i.add_argument(
        "--face-exclude-forehead",
        type=float,
        default=0.0,
        help="Exclude this top ratio of the detected face crop from face-detailer repaint.",
    )
    t2i.add_argument("--face-steps", type=int, default=12)
    t2i.add_argument("--face-denoise", type=float, default=0.28)
    t2i.add_argument("--wildcards", choices=sorted(WILDCARD_MODES), default=DEFAULT_WILDCARD_MODE)
    t2i.add_argument(
        "--lora",
        action="append",
        default=[],
        help="Optional LoRA spec: path|model_strength|clip_strength",
    )
    t2i.add_argument("--dry-run", action="store_true")

    serve = subparsers.add_parser("serve", help="start the local Anima APP GUI/API server")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8765)
    serve.add_argument("--dry-run-default", action="store_true", help="make /api/generate dry-run unless the request overrides dry_run")
    serve.add_argument("--open", action="store_true", help="open the local GUI in the default browser after the server starts")

    return parser


def main(argv: Sequence[str] | None = None, *, paths: AppPaths | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    resolved_paths = paths or default_paths()

    if args.command == "health":
        payload = build_health_payload(resolved_paths)
        print(json.dumps(payload, ensure_ascii=False, indent=2) if args.as_json else "ok")
        return 0

    if args.command == "models":
        if args.models_command == "inventory":
            inventory = scan_model_source(resolved_paths.development_model_source)
            payload = {
                "source_root": str(inventory.source_root),
                "model_root": str(resolved_paths.model_root),
                "folders": list(inventory.folders),
                "files": [
                    {"relative_path": str(item.relative_path), "size_bytes": item.size_bytes}
                    for item in inventory.files
                ],
            }
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 0
        if args.models_command == "copy-profile":
            profile = asset_profile(args.profile)
            source, copied_paths = copy_asset_profile(profile, resolved_paths, source=args.source)
            copied = [str(path) for path in copied_paths]
            print(json.dumps({"profile": profile.name, "source": source, "copied": copied}, ensure_ascii=False, indent=2))
            return 0
        if args.models_command == "loras":
            print(json.dumps({"items": list_local_loras(resolved_paths)}, ensure_ascii=False, indent=2))
            return 0
        if args.models_command == "checkpoints":
            items = list_local_checkpoints(resolved_paths)
            print(json.dumps({"count": len(items), "items": items}, ensure_ascii=False, indent=2))
            return 0
        if args.models_command == "import-lora":
            imported = import_lora_file(Path(args.path), resolved_paths)
            print(json.dumps({"imported": str(imported)}, ensure_ascii=False, indent=2))
            return 0

    if args.command == "t2i":
        ensure_default_cuda_visible_devices()
        request = T2IRequest(
            prompt=args.prompt,
            negative_prompt=args.negative,
            width=args.width,
            height=args.height,
            steps=args.steps,
            cfg=args.cfg,
            seed=args.seed,
            checkpoint=args.checkpoint,
            sampler=args.sampler,
            scheduler=args.scheduler,
            loras=_parse_lora_args(args.lora),
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
                exclude_forehead_ratio=args.face_exclude_forehead,
                steps=args.face_steps,
                denoise=args.face_denoise,
            ),
            vae_decode=VaeDecodeSettings(
                mode=args.vae_decode,
                tile_size=args.vae_tile_size,
                overlap=args.vae_overlap,
            ),
        )
        request, wildcard_expansion = expand_request_wildcards(request, paths=resolved_paths, mode=args.wildcards)
        result = run_t2i(
            request,
            paths=resolved_paths,
            dry_run=args.dry_run,
            renderer=None if args.dry_run else default_t2i_renderer,
            wildcards=wildcard_expansion,
        )
        manifest = read_manifest(result.manifest_path)
        print(
            json.dumps(
                {
                    "status": result.status,
                    "manifest_path": str(result.manifest_path),
                    "output_path": str(result.output_path) if result.output_path else None,
                    "warnings": list(result.warnings),
                    "stages": manifest.get("stages", {}),
                    "wildcards": manifest.get("wildcards", {}),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    if args.command == "serve":
        ensure_default_cuda_visible_devices()
        server = create_http_server(
            args.host,
            args.port,
            paths=resolved_paths,
            renderer=default_t2i_renderer,
            default_dry_run=args.dry_run_default,
        )
        url = f"http://{args.host}:{server.server_address[1]}"
        print(f"Anima APP listening on {url}", flush=True)
        if args.open:
            webbrowser.open(url)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            return 0
        finally:
            server.server_close()

    parser.error(f"command not implemented yet: {args.command}")
    return 2


def console_main() -> None:
    raise SystemExit(main())


def default_t2i_renderer(request: T2IRequest, paths: AppPaths):
    from anima_app.runtime.comfy_t2i import render_t2i

    return render_t2i(request, paths)


def _parse_lora_args(raw_specs: list[str]) -> tuple[T2ILoraConfig, ...]:
    return tuple(_parse_lora_spec(value) for value in raw_specs)


def _parse_lora_spec(value: str) -> T2ILoraConfig:
    parts = [chunk.strip() for chunk in value.split("|")]
    if not parts or not parts[0]:
        raise ValueError("lora spec cannot be empty")
    if len(parts) == 1:
        return T2ILoraConfig(path=parts[0], model_strength=1.0, clip_strength=1.0)
    if len(parts) == 2:
        strength = float(parts[1])
        return T2ILoraConfig(path=parts[0], model_strength=strength, clip_strength=strength)
    if len(parts) == 3:
        return T2ILoraConfig(path=parts[0], model_strength=float(parts[1]), clip_strength=float(parts[2]))
    raise ValueError("lora spec must be path | path|strength | path|strength|strength")


if __name__ == "__main__":
    console_main()

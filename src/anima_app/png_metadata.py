from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image
from PIL.PngImagePlugin import PngInfo

from anima_app.requests import T2IRequest


def build_a1111_parameters(
    request: T2IRequest,
    *,
    wildcards: dict[str, object] | None = None,
) -> str:
    lines = [request.prompt]
    if request.negative_prompt:
        lines.append(f"Negative prompt: {request.negative_prompt}")

    fields: list[tuple[str, str]] = [
        ("Steps", str(request.steps)),
        ("Sampler", request.sampler),
        ("Schedule type", request.scheduler),
        ("CFG scale", _format_number(request.cfg)),
        ("Seed", str(request.seed) if request.seed is not None else "random"),
        ("Size", f"{request.width}x{request.height}"),
        ("Model", request.checkpoint),
    ]
    if request.i2i.enabled:
        fields.append(("Denoising strength", _format_number(request.i2i.denoise)))
    if request.upscale.enabled:
        fields.append(
            (
                "Anima upscale",
                (
                    f"{_format_number(request.upscale.scale)}x, "
                    f"steps {_format_number(request.upscale.steps)}, "
                    f"denoise {_format_number(request.upscale.denoise)}, "
                    f"method {request.upscale.method}"
                ),
            )
        )
        if request.upscale.tiled:
            fields.append(
                (
                    "Anima tiled upscale",
                    f"tile {request.upscale.tile_size}, overlap {request.upscale.overlap}",
                )
            )
    fields.append(
        (
            "Anima VAE decode",
            (
                f"{request.vae_decode.mode}, "
                f"tile {request.vae_decode.tile_size}, "
                f"overlap {request.vae_decode.overlap}"
            ),
        )
    )
    if request.loras:
        fields.append(("Anima LoRAs", _format_loras(request)))
    if wildcards and wildcards.get("enabled"):
        fields.append(("Anima wildcards", str(wildcards.get("mode", "random"))))
    fields.append(("Anima app", "anima-app"))
    lines.append(", ".join(f"{key}: {value}" for key, value in fields))
    return "\n".join(lines)


def embed_png_parameters(path: Path, parameters: str) -> None:
    with Image.open(path) as image:
        image.load()
        copied = image.copy()
        existing_text = dict(getattr(image, "text", {}))

    info = PngInfo()
    for key, value in existing_text.items():
        if key != "parameters" and isinstance(value, str):
            info.add_text(key, value)
    info.add_text("parameters", parameters)
    copied.save(path, pnginfo=info)


def _format_loras(request: T2IRequest) -> str:
    return "; ".join(
        f"{lora.path}:{_format_number(lora.model_strength)}/{_format_number(lora.clip_strength)}"
        for lora in request.loras
    )


def _format_number(value: Any) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)

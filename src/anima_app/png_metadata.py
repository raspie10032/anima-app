from __future__ import annotations

import os
import struct
import tempfile
import zlib
from pathlib import Path
from typing import Any

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
    """Replace only the PNG text chunk, preserving compressed pixels verbatim."""
    info = PngInfo()
    info.add_text("parameters", parameters)
    temporary = None
    try:
        with path.open("rb") as source, tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as target:
            temporary = Path(target.name)
            signature = source.read(8)
            if signature != b"\x89PNG\r\n\x1a\n":
                raise ValueError("invalid PNG signature")
            target.write(signature)
            while True:
                header = source.read(8)
                if len(header) != 8:
                    raise ValueError("truncated PNG chunk")
                length, kind = struct.unpack(">I4s", header)
                prefix = source.read(min(length, 80))
                if len(prefix) != min(length, 80):
                    raise ValueError("truncated PNG data")
                discard = kind in (b"tEXt", b"zTXt", b"iTXt") and prefix.split(b"\0", 1)[0] == b"parameters"
                if kind == b"IEND":
                    for chunk_type, data, *_ in info.chunks:
                        target.write(struct.pack(">I", len(data)) + chunk_type + data)
                        target.write(struct.pack(">I", zlib.crc32(chunk_type + data) & 0xffffffff))
                if not discard:
                    target.write(header + prefix)
                remaining = length - len(prefix) + 4  # include original CRC
                while remaining:
                    block = source.read(min(remaining, 65536))
                    if not block:
                        raise ValueError("truncated PNG data")
                    if not discard:
                        target.write(block)
                    remaining -= len(block)
                if kind == b"IEND":
                    break
            target.flush()
            os.fsync(target.fileno())
        os.chmod(temporary, path.stat().st_mode)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _format_loras(request: T2IRequest) -> str:
    return "; ".join(
        f"{lora.path}:{_format_number(lora.model_strength)}/{_format_number(lora.clip_strength)}"
        for lora in request.loras
    )


def _format_number(value: Any) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)

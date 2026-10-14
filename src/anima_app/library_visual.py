"""Versioned, pixel-only observations. No metadata or network in retrieval."""
from __future__ import annotations

import hashlib
import io
import warnings
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

VISUAL_VERSION = "anima-color-layout-edge-v1"
MAX_IMAGE_BYTES = 32 * 1024 * 1024
MAX_IMAGE_PIXELS = 16 * 1024 * 1024


def read_pixels(path: Path) -> Image.Image:
    if path.stat().st_size > MAX_IMAGE_BYTES:
        raise ValueError("이미지는 32 MiB 이하여야 합니다.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(path) as source:
                if source.format not in {"PNG", "JPEG", "WEBP"} or source.width * source.height > MAX_IMAGE_PIXELS:
                    raise ValueError("PNG/JPEG/WebP, 최대 16메가픽셀 이미지를 사용해 주세요.")
                source.load()
                # Canonical RGB removes text/EXIF/alpha metadata before any encoder.
                return ImageOps.exif_transpose(source).convert("RGB")
    except (OSError, SyntaxError, Image.DecompressionBombWarning, Image.DecompressionBombError):
        raise ValueError("이미지를 읽을 수 없습니다.") from None


def unit(vector) -> np.ndarray:
    value = np.asarray(vector, dtype=np.float32).reshape(-1)
    norm = float(np.linalg.norm(value))
    if not value.size or not np.isfinite(value).all() or not np.isfinite(norm) or norm <= 0:
        raise ValueError("유효하지 않은 시각 벡터입니다.")
    return value / norm


def observe(image: Image.Image) -> dict:
    pixels = np.asarray(image.resize((64, 64), Image.Resampling.LANCZOS), dtype=np.float32) / 255
    hsv = np.asarray(image.resize((64, 64)).convert("HSV"), dtype=np.float32) / 256
    histogram, _ = np.histogramdd(hsv.reshape(-1, 3), bins=(12, 4, 4), range=((0, 1),) * 3)
    layout = np.asarray(image.resize((8, 8), Image.Resampling.BOX), dtype=np.float32).reshape(-1) / 255
    gray = pixels.mean(axis=2)
    dx, dy = np.gradient(gray)
    magnitude = np.hypot(dx, dy)
    angle = (np.arctan2(dy, dx) + np.pi) / (2 * np.pi)
    edges = []
    for y in range(0, 64, 16):
        for x in range(0, 64, 16):
            hist, _ = np.histogram(angle[y:y+16, x:x+16], bins=8, range=(0, 1),
                                   weights=magnitude[y:y+16, x:x+16])
            edges.extend(hist)
    # Include a nonzero background component for blank images.
    vector = unit(np.concatenate([unit(histogram + 1e-6) * .7, unit(layout + 1e-6) * .5,
                                  unit(np.asarray(edges) + 1e-6) * .3]))
    pixel_hash = hashlib.sha256(f"RGB:{image.width}:{image.height}:".encode() + image.tobytes()).hexdigest()
    thumb = image.copy()
    thumb.thumbnail((320, 320))
    output = io.BytesIO()
    thumb.save(output, format="JPEG", quality=82)
    return {"pixel_hash": pixel_hash, "vector": vector.tolist(), "thumbnail": output.getvalue(),
            "width": image.width, "height": image.height}

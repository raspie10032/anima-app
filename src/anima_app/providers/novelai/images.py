from __future__ import annotations

import io
import os
import tempfile
import warnings
import zipfile
from pathlib import Path

from PIL import Image

from anima_app.providers.novelai.client import MAX_RESPONSE_BYTES
from anima_app.providers.novelai.errors import NovelAIError


def first_png_from_zip(data: bytes) -> bytes:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            if len(archive.infolist()) > 16:
                raise ValueError("too many archive entries")
            candidates = [
                item
                for item in archive.infolist()
                if not item.is_dir() and item.filename.lower().endswith(".png")
            ]
            if not candidates:
                raise ValueError("NovelAI response did not contain a PNG")
            if len(candidates) != 1 or candidates[0].file_size > MAX_RESPONSE_BYTES:
                raise ValueError("expected one bounded PNG")
            png = archive.read(candidates[0])
    except (OSError, RuntimeError, ValueError, zipfile.BadZipFile):
        raise NovelAIError("nai_response_invalid", "NovelAI response was not a valid PNG archive", unknown=True) from None
    verify_png_bytes(png)
    return png


def verify_png_bytes(data: bytes, expected_size: tuple[int, int] | None = None) -> None:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as image:
                if image.format != "PNG" or getattr(image, "n_frames", 1) != 1:
                    raise ValueError
                if max(image.size) > 2048 or image.width * image.height > 2048 * 2048:
                    raise ValueError
                if expected_size is not None and image.size != expected_size:
                    raise ValueError
                image.verify()
            with Image.open(io.BytesIO(data)) as image:
                image.load()
    except Exception:
        raise NovelAIError("nai_response_invalid", "NovelAI response did not contain a valid PNG with the expected dimensions", unknown=True) from None


def write_verified_png(path: Path, data: bytes) -> None:
    verify_png_bytes(data)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile("wb", dir=path.parent, prefix=".nai-", suffix=".tmp", delete=False) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(data)
            temporary.flush()
            os.fsync(temporary.fileno())
        temporary_path.replace(path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)

from __future__ import annotations

import io
import json
import os
import tempfile
import warnings
import zipfile
import zlib
from pathlib import Path

from PIL import Image

from anima_app.providers.novelai.client import MAX_RESPONSE_BYTES
from anima_app.providers.novelai.errors import NovelAIError


def with_character_slots(data: bytes, slots, count: int) -> bytes:
    """Append app-only iTXt; preserve all original PNG chunks and decoded pixels."""
    verify_png_bytes(data)
    end = 8
    while data[end + 4:end + 8] != b"IEND":
        end += 12 + int.from_bytes(data[end:end + 4], "big")
        if end + 12 > len(data):
            raise ValueError("PNG is missing IEND")
    text = json.dumps({"slots": slots, "count": count}, ensure_ascii=False).encode("utf-8")
    body = b"iTXt" + b"anima_app_character_slots\x00\x00\x00\x00\x00" + text
    chunk = (len(body) - 4).to_bytes(4, "big") + body + (zlib.crc32(body) & 0xffffffff).to_bytes(4, "big")
    return data[:end] + chunk + data[end:]


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
    except (EOFError, NotImplementedError, OSError, RuntimeError, ValueError, zipfile.BadZipFile):
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

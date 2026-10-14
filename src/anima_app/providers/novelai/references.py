# SPDX-License-Identifier: GPL-3.0-only
"""Port of RS_NAI reference validation, image preparation and durable Vibe caching."""
from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import tempfile
import threading
from pathlib import Path

from PIL import Image, ImageOps

from anima_app.providers.novelai import client
from anima_app.providers.novelai.errors import NovelAIError, invalid, diagnosed, mark_stage
from anima_app.providers.novelai.inpaint import encode_png
from anima_app.runtime.comfy_t2i import resolve_managed_reference_path

ENCODE_VIBE_URL = "https://image.novelai.net/ai/encode-vibe"
VIBE_MODELS = frozenset({"nai-diffusion-3", "nai-diffusion-furry-3", "nai-diffusion-4-curated-preview",
                         "nai-diffusion-4-full", "nai-diffusion-4-5-curated", "nai-diffusion-4-5-full"})
PRECISE_MODELS = frozenset({"nai-diffusion-4-5-curated", "nai-diffusion-4-5-full"})
REFERENCE_TYPES = ("character", "style", "character&style")
MAX_REFERENCES = 16
_cache_lock = threading.Lock()


def validate_entries(value, kind):
    if not isinstance(value, (list, tuple)) or len(value) > MAX_REFERENCES:
        raise invalid("REFERENCE_INPUT", "NovelAI accepts at most 16 references")
    allowed = {"image", "strength", "information_extracted"} if kind == "vibe" else {"image", "strength", "fidelity", "reference_type"}
    defaults = {"strength": .6, "information_extracted": 1.0} if kind == "vibe" else {"strength": 1.0, "fidelity": 1.0, "reference_type": "character"}
    result = []
    for entry in value:
        if not isinstance(entry, dict) or entry.keys() - allowed:
            raise invalid("REFERENCE_INPUT", "Unknown NovelAI reference field")
        item = {**defaults, **entry}
        if not isinstance(item.get("image"), str) or not item["image"] or len(item["image"]) > 4096:
            raise invalid("REFERENCE_INPUT", "Reference image must be a managed image path")
        for key in ("strength", "information_extracted" if kind == "vibe" else "fidelity"):
            if type(item[key]) not in (int, float) or not 0 <= item[key] <= 1:
                raise invalid("REFERENCE_INPUT", "Reference strength, information and fidelity must be finite numbers between 0 and 1")
        if kind != "vibe" and (not isinstance(item["reference_type"], str) or item["reference_type"] not in REFERENCE_TYPES):
            raise invalid("REFERENCE_INPUT", "Unknown Precise Reference type")
        result.append(item)
    return tuple(result)


def validate_compatibility(model, operation, vibes, precise, limit_opus_free):
    # Even a zero-strength reference cannot evade the explicit paid-mode gate.
    if limit_opus_free and (vibes or precise):
        raise invalid("PAID_BLOCKED", "Vibe와 Precise Reference는 Anlas 비용이 발생할 수 있습니다. Opus 보호 모드를 직접 해제해 주세요.")
    if vibes and precise:
        raise invalid("REFERENCE_BOTH", "Vibe Transfer and Precise Reference cannot be combined")
    base_model = model.removesuffix("-inpainting")
    if vibes and (base_model not in VIBE_MODELS or operation in {"infill", "focused_infill", "detail"} and base_model.startswith("nai-diffusion-4")):
        raise invalid("VIBE_MODEL", "Vibe requires V3/V4/V4.5; V4/V4.5 inpainting is unsupported")
    if precise and base_model not in PRECISE_MODELS:
        raise invalid("PRECISE_MODEL", "Precise Reference requires V4.5 Curated or Full")


def read_reference_image(path, paths):
    current = paths.project_root
    for part in Path(path).parts:
        current /= part
        if current.is_symlink():
            raise invalid("REFERENCE_INPUT", "Reference images cannot be symlinks")
    source = resolve_managed_reference_path(path, paths)
    raw = source.read_bytes()
    with Image.open(io.BytesIO(raw)) as opened:
        rgba = ImageOps.exif_transpose(opened).convert("RGBA")
        image = Image.new("RGB", rgba.size, "black")
        image.paste(rgba, mask=rgba.getchannel("A"))
    return image, hashlib.sha256(raw).hexdigest()


def validate_managed_references(request, paths):
    for item in (*request.vibes, *request.references):
        read_reference_image(item["image"], paths)


def _encoding(image, model, information, paths, token, transport, sleep, cancelled):
    key = hashlib.sha256(json.dumps([1, model, float(information).hex(), image], separators=(",", ":")).encode()).hexdigest()
    root = paths.output_root / "nai-vibe-cache"
    path = root / f"{key}.json"
    while not _cache_lock.acquire(timeout=.1):
        client._check_cancelled(cancelled)
    try:
        client._check_cancelled(cancelled)
        if path.is_symlink() or root.is_symlink():
            raise invalid("VIBE_CACHE", "Vibe cache cannot be a symlink")
        if path.exists():
            try:
                stored = json.loads(path.read_text())
                raw = base64.b64decode(stored["encoding"], validate=True)
                if not raw or hashlib.sha256(raw).hexdigest() != stored["sha256"]:
                    raise ValueError("checksum")
                return stored["encoding"], {"key": key, "status": "cached"}
            except (ValueError, KeyError, TypeError):
                raise invalid("VIBE_CACHE", "Vibe cache is invalid. Restore it or explicitly remove it before paid re-encoding.") from None
        root.mkdir(parents=True, exist_ok=True)
        # Confirm writable storage before any encoding charge. Replace atomically only after validation.
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=root, delete=False) as handle:
            temporary = Path(handle.name)
            try:
                mark_stage("vibe_encoding", unknown=True)
                raw = client.post_json(ENCODE_VIBE_URL, token=token,
                                       payload={"image": image, "information_extracted": information, "model": model},
                                       transport=transport, sleep=sleep, cancelled=cancelled)
                if not raw:
                    raise NovelAIError("nai_vibe_encoding_invalid", "NovelAI가 빈 Vibe 인코딩을 반환했습니다.", unknown=True)
                encoding = base64.b64encode(raw).decode("ascii")
                mark_stage("vibe_cache_save")
                json.dump({"encoding": encoding, "sha256": hashlib.sha256(raw).hexdigest()}, handle)
                handle.flush()
                os.fsync(handle.fileno())
                handle.close()
                os.replace(temporary, path)
                return encoding, {"key": key, "status": "encoded"}
            finally:
                temporary.unlink(missing_ok=True)
    finally:
        _cache_lock.release()


@diagnosed("reference_prepare")
def reference_parameters(request, paths, *, token, transport, sleep, cancelled):
    validate_compatibility(request.model, request.operation, request.vibes, request.references, request.limit_opus_free)
    parameters, audit = {}, []
    if request.references:
        active = [r for r in request.references if r["strength"] != 0]
        images = []
        for reference in active:
            client._check_cancelled(cancelled)
            image, digest = read_reference_image(reference["image"], paths)
            ratio = image.width / image.height
            size = min(((1024, 1536), (1536, 1024), (1472, 1472)), key=lambda s: abs(s[0] / s[1] - ratio))
            images.append(encode_png(ImageOps.pad(image, size, method=Image.Resampling.LANCZOS, color="black")))
            audit.append({"type": "precise", "input_sha256": digest, "prepared_size": list(size)})
        if active:
            parameters.update(director_reference_images=images,
                              director_reference_descriptions=[{"caption": {"base_caption": r["reference_type"], "char_captions": []}, "legacy_uc": False} for r in active],
                              director_reference_information_extracted=[1.0 for _ in active],
                              director_reference_strength_values=[r["strength"] for r in active],
                              director_reference_secondary_strength_values=[1.0 - r["fidelity"] for r in active])
    elif request.vibes:
        active = [r for r in request.vibes if r["strength"] != 0]
        images, strengths = [], [r["strength"] for r in active]
        model = request.model.removesuffix("-inpainting")
        if model.startswith("nai-diffusion-4") and request.normalize_vibe_strengths and sum(abs(s) for s in strengths) > 1:
            total = sum(abs(s) for s in strengths)
            strengths = [s / total for s in strengths]
        for reference in active:
            client._check_cancelled(cancelled)
            image, digest = read_reference_image(reference["image"], paths)
            entry = {"type": "vibe", "input_sha256": digest}
            if model.startswith("nai-diffusion-4"):
                encoded, cache = _encoding(encode_png(image), model, reference["information_extracted"], paths, token, transport, sleep, cancelled)
                entry.update(cache)
            else:
                encoded = encode_png(ImageOps.pad(image, (448, 448), method=Image.Resampling.LANCZOS, color="black"))
            images.append(encoded)
            audit.append(entry)
        if active:
            parameters.update(reference_image_multiple=images, reference_strength_multiple=strengths)
            if model.startswith(("nai-diffusion-3", "nai-diffusion-furry-3")):
                parameters["reference_information_extracted_multiple"] = [r["information_extracted"] for r in active]
    return parameters, audit

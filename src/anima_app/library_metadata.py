"""Observed generation intent; never infer image authorship from similarity."""
from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path

from PIL import Image

from anima_app.providers.novelai.metadata import read_image_metadata
from anima_app.providers.novelai.converters import parse_comfyui, parse_naiv4, parse_oldnai, to_comfyui, to_naiv4

PARSER_VERSION = 'artist-explicit-context-v3'
REQUEST_KEYS = frozenset("provider prompt negative_prompt seed width height steps cfg sampler scheduler checkpoint model memory_profile loras i2i upscale vae_decode face_detailer wildcards wildcard_mode novelai operation characters character_slots character_count use_coords use_order cfg_rescale prefer_brownian variety_boost limit_opus_free input_image mask_image img2img_strength img2img_noise inpaint_strength".split())


def clean(value, depth=0):
    if depth > 16:
        return None
    if isinstance(value, dict):
        return {k: clean(v, depth + 1) for k, v in value.items() if not any(
            word in k.lower() for word in ("token", "secret", "password", "authorization", "api_key", "base64"))}
    if isinstance(value, list):
        return [clean(v, depth + 1) for v in value[:1024]]
    if value is None or type(value) in (str, bool, int):
        return value
    if isinstance(value, float) and math.isfinite(value):
        return value
    return None


def request_snapshot(manifest):
    return clean({k: v for k, v in manifest.items() if k in REQUEST_KEYS or k.startswith("nai_") or k in {
        "workflow", "workflow_base_request", "authoring_request", "prompt_routing", "generation_sources"}})


def metadata(path: Path, manifest=None):
    if manifest is not None:
        return request_snapshot(manifest), "anima_manifest", []
    try:
        result = read_image_metadata(path)
        return request_snapshot(result["request"]), "novelai_" + result["metadata_source"], result["warnings"]
    except ValueError:
        pass
    with Image.open(path) as image:
        parameters = image.info.get("parameters", "")
        has_comfy = "prompt" in image.info or "workflow" in image.info
    if isinstance(parameters, str) and 0 < len(parameters) < 1024 * 1024:
        body, sep, settings = parameters.rpartition("\nSteps:")
        if not sep:
            body, settings = parameters, ""
        positive, _, negative = body.partition("\nNegative prompt:")
        # Preserve unknown settings as evidence, not executable form defaults.
        return {"prompt": positive.strip(), "negative_prompt": negative.strip(),
                "settings_text": "Steps:" + settings if settings else ""}, "a1111", [
                    "외부 A1111 설정은 원문으로 보존됩니다. 프롬프트만 적용할 수 있습니다."]
    return {}, "none", ["ComfyUI 그래프는 아직 해석하지 않습니다."] if has_comfy else []


def artist_combo(request):
    prompt = request.get("prompt", "")
    if not isinstance(prompt, str) or len(prompt) > 100000:
        return {"key": "", "artists": [], "prompt": "", "syntax": "unknown"}
    is_nai = request.get("provider") == "novelai" or "::" in prompt
    parser = parse_naiv4 if "::" in prompt else parse_oldnai if is_nai else parse_comfyui
    rows = []
    try:
        for tag, weight in ((piece, weight) for group, weight in parser(prompt) for piece in group.split(',')):
            tag = tag.replace("__artist__", "artist:").strip()
            match = re.fullmatch(r"(?:artist:\s*|@)(.{1,200})", tag, re.I)
            if match and math.isfinite(weight) and weight != 0:
                rows.append({"tag": match.group(1), "weight": weight})
    except (ValueError, RecursionError, OverflowError):
        rows = []
    effective = request.get('novelai', {}).get('effective', {}) if isinstance(request.get('novelai'), dict) else {}
    if not isinstance(effective, dict):
        effective = {}
    context = {'provider': request.get('provider', 'unknown'),
               'model': effective.get('nai_model') or request.get('nai_model') or request.get('model') or request.get('checkpoint', '')}
    identity = json.dumps([rows, context], ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    tags = [("artist:" + row["tag"], row["weight"]) for row in rows]
    return {"key": hashlib.sha256(identity.encode()).hexdigest() if rows else "",
            "artists": rows, "prompt": (to_naiv4 if is_nai else to_comfyui)(tags),
            "syntax": "novelai" if is_nai else "comfyui", "context": context}

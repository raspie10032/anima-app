from __future__ import annotations

import random
from dataclasses import asdict

from anima_app.providers.novelai.models import (
    OPUS_FREE_MAX_PIXELS,
    OPUS_FREE_MAX_STEPS,
    default_skip_cfg_above_sigma,
)
from anima_app.providers.novelai.requests import NovelAIRequest, replace_characters
from anima_app.providers.novelai.medium import MEDIUM_SAMPLER, MEDIUM_STEPS, is_medium, medium_negative


def build_payload(request: NovelAIRequest) -> tuple[NovelAIRequest, dict[str, object]]:
    effective = _effective_request(request)
    parameters: dict[str, object] = {
        "width": effective.width,
        "height": effective.height,
        "n_samples": 1,
        "seed": effective.seed,
        "extra_noise_seed": effective.seed,
        "sampler": effective.sampler,
        "steps": effective.steps,
        "scale": effective.cfg,
        "negative_prompt": effective.negative_prompt,
        "cfg_rescale": effective.cfg_rescale,
        "prefer_brownian": effective.prefer_brownian,
        "noise_schedule": effective.scheduler,
        "params_version": 4 if effective.model.startswith("nai-diffusion-5") else 3,
        "legacy": False,
        "legacy_v3_extend": False,
    }
    skip_cfg = default_skip_cfg_above_sigma(effective.model)
    if effective.variety_boost and skip_cfg is not None:
        parameters["skip_cfg_above_sigma"] = skip_cfg
    if effective.model.startswith(("nai-diffusion-4", "nai-diffusion-5")):
        parameters.update(_v4_prompt_parameters(effective))
    if effective.operation == "infill":
        parameters["add_original_image"] = True
        if effective.inpaint_strength != 1:
            parameters["img2img"] = {"strength": effective.inpaint_strength, "color_correct": True}
    elif effective.operation == "img2img":
        parameters.update(strength=effective.img2img_strength, noise=effective.img2img_noise)
    return effective, {
        "input": effective.prompt,
        "model": effective.model,
        "action": effective.operation,
        "parameters": parameters,
    }


def _effective_request(request: NovelAIRequest) -> NovelAIRequest:
    width, height, steps = request.width, request.height, request.steps
    if request.limit_opus_free and request.operation == "generate":
        width, height, steps = apply_opus_free_limits(width, height, steps)
    seed = request.seed if request.seed is not None else random.randint(0, 0x7FFFFFFF)
    overrides = {}
    if is_medium(request.model):
        request = replace_characters(request, [{**c, "negative_prompt": ""} for c in request.characters])
        overrides = {
            "steps": MEDIUM_STEPS, "sampler": MEDIUM_SAMPLER, "cfg_rescale": 0.0,
            "negative_prompt": medium_negative(request.prompt),
        }
    return NovelAIRequest(
        **{
            **asdict(request),
            "width": width,
            "height": height,
            "steps": steps,
            "seed": seed,
            **overrides,
        }
    )


def _v4_prompt_parameters(request: NovelAIRequest) -> dict[str, object]:
    return {
        "add_original_image": True,
        "legacy_uc": False,
        "v4_prompt": {
            "caption": {"base_caption": request.prompt, "char_captions": [
                {"char_caption": c["prompt"], "centers": [{"x": c["x"], "y": c["y"]}]} for c in request.characters]},
            "use_coords": bool(request.characters) and request.use_coords,
            "use_order": request.use_order,
            "legacy_uc": False,
        },
        "v4_negative_prompt": {
            "caption": {"base_caption": request.negative_prompt, "char_captions": [
                {"char_caption": c["negative_prompt"], "centers": [{"x": c["x"], "y": c["y"]}]} for c in request.characters]},
            "use_coords": False,
            "use_order": False,
            "legacy_uc": False,
        },
    }


def apply_opus_free_limits(width: int, height: int, steps: int) -> tuple[int, int, int]:
    steps = min(steps, OPUS_FREE_MAX_STEPS)
    if width * height <= OPUS_FREE_MAX_PIXELS:
        return width, height, steps
    scale = (OPUS_FREE_MAX_PIXELS / (width * height)) ** 0.5
    width = max(64, int(width * scale) // 64 * 64)
    height = max(64, int(height * scale) // 64 * 64)
    while width * height > OPUS_FREE_MAX_PIXELS:
        if width >= height:
            width = max(64, width - 64)
        else:
            height = max(64, height - 64)
    return width, height, steps

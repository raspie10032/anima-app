# SPDX-License-Identifier: GPL-3.0-only
# Copyright (c) 2025 raspie10032
"""Medium Effort rules from RS NAI main 4de914676de8ca313b8389f4303754045a6a9cfb."""

MEDIUM_MODEL = "nai-diffusion-5-full-medium"
MEDIUM_INPAINT_MODEL = MEDIUM_MODEL + "-inpainting"
MEDIUM_STEPS = 14
MEDIUM_SAMPLER = "k_euler_ancestral"
MEDIUM_UC = (
    "lowres, artistic error, film grain, scan artifacts, worst quality, bad quality, "
    "jpeg artifacts, very displeasing, chromatic aberration, dithering, halftone, "
    "screentone, multiple views, logo, too many watermarks, negative space, blank page"
)
MEDIUM_NOTICE = (
    "Medium Effort: 14스텝 · Euler Ancestral · CFG Rescale 0 · Heavy 네거티브 고정. "
    "입력한 기본/캐릭터 네거티브는 전송에 사용하지 않습니다. CFG와 시드는 유지합니다."
)


def is_medium(model: str) -> bool:
    return model in {MEDIUM_MODEL, MEDIUM_INPAINT_MODEL}


def medium_negative(prompt: str) -> str:
    return MEDIUM_UC if "nsfw" in prompt.lower() else "nsfw, " + MEDIUM_UC


def valid_medium_payload(payload: dict[str, object]) -> bool:
    """Check the final wire values, including structured character negatives."""
    parameters = payload.get("parameters")
    prompt = payload.get("input")
    if not isinstance(parameters, dict) or not isinstance(prompt, str):
        return False
    structured = parameters.get("v4_negative_prompt")
    caption = structured.get("caption") if isinstance(structured, dict) else None
    if not isinstance(caption, dict):
        return False
    characters = caption.get("char_captions")
    return (
        type(parameters.get("steps")) is int and parameters["steps"] == MEDIUM_STEPS
        and parameters.get("sampler") == MEDIUM_SAMPLER
        and type(parameters.get("cfg_rescale")) in (int, float) and parameters["cfg_rescale"] == 0
        and parameters.get("negative_prompt") == medium_negative(prompt)
        and caption.get("base_caption") == medium_negative(prompt)
        and isinstance(characters, list)
        and all(isinstance(c, dict) and c.get("char_caption") == "" for c in characters)
    )

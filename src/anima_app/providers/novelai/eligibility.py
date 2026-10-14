"""Strict Opus guards ported from ComfyUI_RS_NAI_API_Request/nai_api.py.

The 2-percent V5 reserve is the node's conservative policy, not a billing estimate.
"""
from __future__ import annotations

import base64
import io
import math
from dataclasses import dataclass

from PIL import Image

from anima_app.providers.novelai.errors import NovelAIError
from anima_app.providers.novelai.medium import is_medium, valid_medium_payload
from anima_app.providers.novelai.models import MODEL_IDS, OPUS_FREE_MAX_PIXELS, OPUS_FREE_MAX_STEPS, SUPPORTED_INPAINT_MODEL_IDS

OPUS_V5_MIN_REMAINING_PERCENT = 2
OPUS_FREE_PARAMETER_KEYS = frozenset({
    "width", "height", "n_samples", "seed", "extra_noise_seed", "sampler", "steps",
    "scale", "negative_prompt", "cfg_rescale", "prefer_brownian", "noise_schedule",
    "params_version", "legacy", "legacy_v3_extend", "skip_cfg_above_sigma",
    "add_original_image", "legacy_uc", "v4_prompt", "v4_negative_prompt",
})


@dataclass(frozen=True)
class FocusedContext:
    source_size: tuple[int, int]
    crop_box: tuple[int, int, int, int]


def validate_opus_free_payload(payload: dict[str, object], *, focused_context: FocusedContext | None = None) -> None:
    parameters = payload.get("parameters")
    focused = isinstance(focused_context, FocusedContext)
    allowed = OPUS_FREE_PARAMETER_KEYS | {"image", "mask", "inpaintImg2ImgStrength", "noise", "img2img"} if focused else OPUS_FREE_PARAMETER_KEYS
    if (
        payload.keys() - {"input", "model", "action", "parameters"}
        or not isinstance(payload.get("model"), str)
        or payload.get("model") not in (SUPPORTED_INPAINT_MODEL_IDS if focused else MODEL_IDS)
        or payload.get("action") != ("infill" if focused else "generate")
        or not isinstance(parameters, dict)
        or parameters.keys() - allowed
    ):
        raise NovelAIError("nai_opus_request_blocked", "Opus 보호 모드에서 확인할 수 없는 모델·동작·이미지 참조 요청을 차단했습니다.", 400)
    if is_medium(payload["model"]) and not valid_medium_payload(payload):
        raise NovelAIError("nai_opus_request_blocked", "Medium Effort의 고정 샘플링·네거티브 조건을 확인할 수 없어 전송을 차단했습니다.", 400)
    width, height, steps = (parameters.get(name) for name in ("width", "height", "steps"))
    if (
        type(width) is not int or type(height) is not int or type(steps) is not int
        or width <= 0 or height <= 0 or width * height > OPUS_FREE_MAX_PIXELS
        or not 1 <= steps <= OPUS_FREE_MAX_STEPS
        or type(parameters.get("n_samples")) is not int or parameters["n_samples"] != 1
    ):
        raise NovelAIError("nai_opus_request_blocked", "Opus 보호 모드는 1장, 1,048,576픽셀 이하, 28스텝 이하만 허용합니다.", 400)
    if focused:
        sw, sh = focused_context.source_size
        x0, y0, x1, y1 = focused_context.crop_box
        strength, noise = parameters.get("inpaintImg2ImgStrength"), parameters.get("noise")
        if (not all(type(v) is int for v in (sw, sh, x0, y0, x1, y1))
            or not 0 <= x0 < x1 <= sw or not 0 <= y0 < y1 <= sh
            or (x0, y0, x1, y1) == (0, 0, sw, sh) or width > 1024 or height > 1024
            or parameters.get("add_original_image") is not True
            or type(strength) not in (int, float) or not math.isfinite(strength) or not 0 <= strength <= 1
            or type(noise) not in (int, float) or not math.isfinite(noise) or noise != 0):
            raise NovelAIError("nai_opus_request_blocked", "Focused crop 조건을 확인할 수 없어 전송을 차단했습니다.", 400)
        nested = parameters.get("img2img")
        partial = payload["model"].startswith(("nai-diffusion-4", "nai-diffusion-5")) and strength < 1
        if partial:
            if (not isinstance(nested, dict) or set(nested) != {"strength", "color_correct"}
                or type(nested.get("strength")) not in (int, float) or nested["strength"] != strength
                or nested.get("color_correct") is not True):
                raise NovelAIError("nai_opus_request_blocked", "Focused 부분 강도가 API 설정과 일치하지 않아 전송을 차단했습니다.", 400)
        elif "img2img" in parameters:
            raise NovelAIError("nai_opus_request_blocked", "Focused 요청에 지원하지 않는 부분 강도 설정이 있습니다.", 400)
        for key in ("image", "mask"):
            try:
                value = parameters.get(key)
                if not isinstance(value, str) or len(value) > 16 * 1024 * 1024:
                    raise ValueError("invalid image")
                with Image.open(io.BytesIO(base64.b64decode(value, validate=True))) as image:
                    if image.size != (width, height) or key == "mask" and not image.convert("L").getbbox():
                        raise ValueError("invalid focused input")
                    image.load()
            except (ValueError, OSError, Image.DecompressionBombError):
                raise NovelAIError("nai_opus_request_blocked", "Focused 입력 이미지 / 마스크를 확인할 수 없습니다.", 400) from None


def verify_opus_state(state: object, model: str) -> dict[str, object]:
    if (
        not isinstance(state, dict) or state.get("active") is not True
        or type(state.get("tier")) is not int or state["tier"] != 3
    ):
        raise NovelAIError("nai_opus_ineligible", "활성 Opus 구독을 확인할 수 없어 생성 요청을 차단했습니다.", 409)
    summary: dict[str, object] = {"status": "verified", "active": True, "tier": 3}
    if model.startswith("nai-diffusion-5"):
        usage = state.get("usage")
        if (
            not isinstance(usage, dict) or usage.get("isNegative") is not False
            or type(usage.get("percent")) is not int
            or usage["percent"] < OPUS_V5_MIN_REMAINING_PERCENT
        ):
            raise NovelAIError("nai_opus_v5_allowance_low", "V5 무료 잔여량이 2% 미만이거나 확인할 수 없어 생성 요청을 차단했습니다.", 409)
        summary.update(v5_remaining_percent=usage["percent"], v5_min_remaining_percent=OPUS_V5_MIN_REMAINING_PERCENT)
    return summary

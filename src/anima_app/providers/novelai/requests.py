from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from pathlib import Path

from anima_app.providers.novelai.models import MODEL_IDS, SAMPLERS, SCHEDULERS, SUPPORTED_INPAINT_MODEL_IDS
from anima_app.requests import MAX_BASE_IMAGE_PIXELS, MAX_CFG, MAX_GENERATION_DIMENSION, MAX_PROMPT_CHARACTERS

MAX_NAI_SEED = 2**32 - 1
MAX_NAI_STEPS = 50
CREDENTIAL_KEYS = frozenset({"token", "access_token", "api_token", "api_key", "authorization", "headers",
                            "nai_access_token", "nai_api_token", "password", "cookie", "cookies"})


def validate_characters(value: object) -> tuple[dict[str, object], ...]:
    if not isinstance(value, (list, tuple)) or len(value) > 5:
        raise ValueError("NovelAI characters must be a list of at most five characters")
    characters = []
    for item in value:
        if not isinstance(item, dict) or item.keys() - {"prompt", "negative_prompt", "x", "y"}:
            raise ValueError("NovelAI character accepts only prompt, negative_prompt, x and y")
        character = {"prompt": item.get("prompt", ""), "negative_prompt": item.get("negative_prompt", ""),
                     "x": item.get("x", 0.5), "y": item.get("y", 0.5)}
        for name in ("prompt", "negative_prompt"):
            if not isinstance(character[name], str) or len(character[name]) > MAX_PROMPT_CHARACTERS:
                raise ValueError("NovelAI character prompt exceeds the supported text length")
        for name in ("x", "y"):
            coordinate = character[name]
            if isinstance(coordinate, bool) or not isinstance(coordinate, (int, float)) or not 0 <= coordinate <= 1:
                raise ValueError("NovelAI character coordinates must be finite numbers between 0 and 1")
        characters.append(character)
    return tuple(characters)


def reject_credentials(value: object) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).lower() in CREDENTIAL_KEYS:
                raise ValueError("credentials must only be configured in the server environment")
            reject_credentials(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            reject_credentials(item)


@dataclass(frozen=True)
class NovelAIRequest:
    prompt: str
    negative_prompt: str = ""
    width: int = 832
    height: int = 1216
    steps: int = 28
    cfg: float = 6.0
    seed: int | None = None
    model: str = "nai-diffusion-5-curated"
    sampler: str = "k_euler"
    scheduler: str = "karras"
    cfg_rescale: float = 0.0
    prefer_brownian: bool = False
    variety_boost: bool = True
    limit_opus_free: bool = True
    operation: str = "generate"
    input_image: str = ""
    mask_image: str = ""
    inpaint_strength: float = 1.0
    img2img_strength: float = 0.5
    img2img_noise: float = 0.0
    characters: tuple[dict[str, object], ...] = ()
    use_coords: bool = True
    use_order: bool = True
    vibes: tuple[dict[str, object], ...] = ()
    references: tuple[dict[str, object], ...] = ()
    normalize_vibe_strengths: bool = True
    detailer: dict[str, object] | None = None

    def __post_init__(self) -> None:
        for label, value in (("prompt", self.prompt), ("negative prompt", self.negative_prompt)):
            if not isinstance(value, str) or len(value) > MAX_PROMPT_CHARACTERS:
                raise ValueError(f"{label} must be text with at most {MAX_PROMPT_CHARACTERS} characters")
        if not self.prompt.strip():
            raise ValueError("prompt is required")
        if not isinstance(self.operation, str) or self.operation not in {"generate", "img2img", "infill", "detail", "focused_infill"}:
            raise ValueError("Unsupported NovelAI operation")
        models = SUPPORTED_INPAINT_MODEL_IDS if self.operation in {"infill", "focused_infill"} else MODEL_IDS
        if not isinstance(self.model, str) or self.model not in models:
            raise ValueError("unsupported NovelAI model")
        if not isinstance(self.sampler, str) or self.sampler not in SAMPLERS:
            raise ValueError("unsupported NovelAI sampler")
        if not isinstance(self.scheduler, str) or self.scheduler not in SCHEDULERS:
            raise ValueError("unsupported NovelAI scheduler")
        object.__setattr__(self, "characters", validate_characters(self.characters))
        if self.characters and not self.model.startswith(("nai-diffusion-4", "nai-diffusion-5")):
            raise ValueError("NovelAI character prompts require a V4 or V5 model")
        for name in ("limit_opus_free", "prefer_brownian", "variety_boost", "use_coords", "use_order", "normalize_vibe_strengths"):
            if not isinstance(getattr(self, name), bool):
                raise ValueError(f"{name} must be a boolean")
        from anima_app.providers.novelai.references import validate_compatibility, validate_entries
        object.__setattr__(self, "vibes", validate_entries(self.vibes, "vibe"))
        object.__setattr__(self, "references", validate_entries(self.references, "precise"))
        validate_compatibility(self.model, self.operation, self.vibes, self.references, self.limit_opus_free)
        from anima_app.providers.novelai.detailer import validate_settings
        object.__setattr__(self, "detailer", validate_settings(self.detailer or {}))
        if self.operation == "focused_infill":
            object.__setattr__(self, "detailer", {**self.detailer, "enabled": True})
        if self.operation == "detail" and not self.detailer["enabled"]:
            raise ValueError("Existing-image detail operation requires enabled detailer")
        if self.detailer["enabled"] and self.detailer["matching"] == "wd14" and not self.characters:
            raise ValueError("WD matching requires original character prompts")
        if self.detailer["enabled"] and self.detailer["matching"] == "shared" and len(self.characters) > 1:
            raise ValueError("Multiple characters require WD matching for detailing")
        if self.detailer["enabled"] and not self.detailer["preview_only"] and self.vibes and self.model.startswith("nai-diffusion-4"):
            raise ValueError("V4/V4.5 Vibe cannot be used for detailing")
        for name in ("input_image", "mask_image"):
            value = getattr(self, name)
            if not isinstance(value, str) or len(value) > 4096:
                raise ValueError(f"{name} must be a managed image path")
        if self.operation in {"infill", "focused_infill"}:
            if not self.input_image or not self.mask_image:
                raise ValueError("NovelAI inpaint requires an input image and a white-on-black mask")
            if self.limit_opus_free and self.operation == "infill":
                raise ValueError("NAI 인페인트는 Anlas 비용이 발생할 수 있습니다. Opus 요청 한도를 직접 해제해 주세요.")
            if self.model in {"nai-diffusion-3-inpainting", "nai-diffusion-furry-3-inpainting"} and self.inpaint_strength != 1:
                raise ValueError("NovelAI V3 inpainting only supports strength 1")
        elif self.operation in {"img2img", "detail"}:
            if self.limit_opus_free and self.operation == "img2img":
                raise ValueError("NAI Img2Img는 Anlas 비용이 발생할 수 있습니다. Opus 보호 모드를 직접 해제해 주세요.")
            if not self.input_image or self.mask_image:
                raise ValueError("NovelAI Img2Img/detail requires an input image and no mask")
        elif self.input_image or self.mask_image:
            raise ValueError("image inputs require img2img or infill")
        for value in (self.width, self.height):
            if isinstance(value, bool) or not isinstance(value, int) or not 64 <= value <= MAX_GENERATION_DIMENSION or value % 64:
                raise ValueError(f"NovelAI width and height must be multiples of 64 between 64 and {MAX_GENERATION_DIMENSION}")
        if not self.limit_opus_free and self.width * self.height > MAX_BASE_IMAGE_PIXELS:
            raise ValueError(f"NovelAI image cannot exceed {MAX_BASE_IMAGE_PIXELS} pixels without the Opus request cap")
        if isinstance(self.steps, bool) or not isinstance(self.steps, int) or not 1 <= self.steps <= MAX_NAI_STEPS:
            raise ValueError(f"NovelAI steps must be an integer between 1 and {MAX_NAI_STEPS}")
        for label, value, maximum in (("cfg", self.cfg, MAX_CFG), ("cfg rescale", self.cfg_rescale, 1),
                                      ("inpaint strength", self.inpaint_strength, 1),
                                      ("Img2Img strength", self.img2img_strength, 1),
                                      ("Img2Img noise", self.img2img_noise, 1)):
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"NovelAI {label} must be a finite number between 0 and {maximum}")
            try:
                valid = math.isfinite(value) and 0 <= value <= maximum
            except OverflowError:
                valid = False
            if not valid:
                raise ValueError(f"NovelAI {label} must be a finite number between 0 and {maximum}")
        if self.seed is not None and (isinstance(self.seed, bool) or not isinstance(self.seed, int) or not 0 <= self.seed <= MAX_NAI_SEED):
            raise ValueError(f"NovelAI seed must be an integer between 0 and {MAX_NAI_SEED}")

    def to_payload(self) -> dict[str, object]:
        values = asdict(self)
        for name in ("model", "sampler", "scheduler", "cfg_rescale", "prefer_brownian", "variety_boost", "limit_opus_free",
                     "characters", "use_coords", "use_order", "vibes", "references", "normalize_vibe_strengths", "detailer"):
            values[f"nai_{name}"] = values.pop(name)
        values["nai_characters"] = list(values["nai_characters"])
        return {"provider": "novelai", **values}


@dataclass(frozen=True)
class NovelAIResult:
    status: str
    manifest_path: Path
    output_path: Path | None
    request: NovelAIRequest
    cancellation_requested: bool = False


def request_from_payload(payload: dict[str, object]) -> NovelAIRequest:
    reject_credentials(payload)
    for name in ("i2i", "upscale", "face_detailer"):
        option = payload.get(name, {})
        if not isinstance(option, dict) or not isinstance(option.get("enabled", False), bool):
            raise ValueError(f"{name} must contain a boolean enabled flag")
        if option.get("enabled"):
            raise ValueError(f"NovelAI T2I does not support {name}")
    if payload.get("loras") or payload.get("i2i_image"):
        raise ValueError("NovelAI T2I does not support local LoRAs or reference images")
    return NovelAIRequest(
        prompt=payload.get("prompt", ""),
        negative_prompt=payload.get("negative_prompt", payload.get("negative", "")),
        width=payload.get("width", 832), height=payload.get("height", 1216),
        steps=payload.get("steps", 28), cfg=payload.get("cfg", 6.0),
        seed=None if payload.get("seed") in (None, "") else payload["seed"],
        model=payload.get("nai_model", payload.get("model", "nai-diffusion-5-curated")),
        sampler=payload.get("nai_sampler", "k_euler"), scheduler=payload.get("nai_scheduler", "karras"),
        cfg_rescale=payload.get("nai_cfg_rescale", 0.0),
        prefer_brownian=payload.get("nai_prefer_brownian", False),
        variety_boost=payload.get("nai_variety_boost", True),
        limit_opus_free=payload.get("nai_limit_opus_free", True),
        operation=payload.get("operation", "generate"),
        input_image=payload.get("input_image", ""), mask_image=payload.get("mask_image", ""),
        inpaint_strength=payload.get("inpaint_strength", 1.0),
        img2img_strength=payload.get("img2img_strength", 0.5),
        img2img_noise=payload.get("img2img_noise", 0.0),
        characters=payload.get("nai_characters", payload.get("characters", [])),
        use_coords=payload.get("nai_use_coords", payload.get("use_coords", True)),
        use_order=payload.get("nai_use_order", payload.get("use_order", True)),
        vibes=payload.get("nai_vibes", payload.get("vibes", [])),
        references=payload.get("nai_references", payload.get("references", [])),
        normalize_vibe_strengths=payload.get("nai_normalize_vibe_strengths", True),
        detailer=payload.get("nai_detailer", payload.get("detailer", {})),
    )

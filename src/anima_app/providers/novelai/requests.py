from __future__ import annotations

from anima_app.providers.novelai.errors import invalid

import math
import json
from dataclasses import asdict, dataclass, replace
from pathlib import Path

from anima_app.providers.novelai.models import MAX_CHARACTER_SLOTS, MODEL_IDS, SAMPLERS, SCHEDULERS, SUPPORTED_INPAINT_MODEL_IDS, character_limit
from anima_app.requests import MAX_BASE_IMAGE_PIXELS, MAX_CFG, MAX_GENERATION_DIMENSION, MAX_PROMPT_CHARACTERS

MAX_NAI_SEED = 2**32 - 1
MAX_NAI_STEPS = 50
CREDENTIAL_KEYS = frozenset({"token", "access_token", "api_token", "api_key", "authorization", "headers",
                            "nai_access_token", "nai_api_token", "password", "cookie", "cookies"})


def validate_characters(value: object) -> tuple[dict[str, object], ...]:
    if not isinstance(value, (list, tuple)) or len(value) > MAX_CHARACTER_SLOTS:
        raise invalid("CHARACTER_INPUT", "NovelAI characters must be a list of at most 22 characters")
    characters = []
    for item in value:
        if not isinstance(item, dict) or item.keys() - {"prompt", "negative_prompt", "x", "y"}:
            raise invalid("CHARACTER_INPUT", "NovelAI character accepts only prompt, negative_prompt, x and y")
        character = {"prompt": item.get("prompt", ""), "negative_prompt": item.get("negative_prompt", ""),
                     "x": item.get("x", 0.5), "y": item.get("y", 0.5)}
        for name in ("prompt", "negative_prompt"):
            if not isinstance(character[name], str) or len(character[name]) > MAX_PROMPT_CHARACTERS:
                raise invalid("CHARACTER_INPUT", "NovelAI character prompt exceeds the supported text length")
        for name in ("x", "y"):
            coordinate = character[name]
            if isinstance(coordinate, bool) or not isinstance(coordinate, (int, float)) or not 0 <= coordinate <= 1:
                raise invalid("CHARACTER_INPUT", "NovelAI character coordinates must be finite numbers between 0 and 1")
        characters.append(character)
    return tuple(characters)


def validate_character_slots(value: object, count: object) -> tuple[tuple[dict[str, object], ...], int]:
    if not isinstance(value, (list, tuple)) or len(value) > MAX_CHARACTER_SLOTS:
        raise invalid("CHARACTER_INPUT", "NovelAI character slots must be a list of at most 22 slots")
    if count is None:
        count = len(value)
    if type(count) is not int or not 0 <= count <= len(value):
        raise invalid("CHARACTER_INPUT", "NovelAI character count must be an integer between 0 and the saved slot count")
    slots = []
    for item in value:
        if not isinstance(item, dict) or item.keys() - {"prompt", "negative_prompt", "x", "y", "enabled", "collapsed"}:
            raise invalid("CHARACTER_INPUT", "Invalid NovelAI character slot fields")
        enabled, collapsed = item.get("enabled", True), item.get("collapsed", False)
        if type(enabled) is not bool or type(collapsed) is not bool:
            raise invalid("CHARACTER_INPUT", "NovelAI character enabled and collapsed must be boolean")
        character = validate_characters([{k: v for k, v in item.items() if k not in {"enabled", "collapsed"}}])[0]
        slots.append({**character, "enabled": enabled, "collapsed": collapsed})
    if len(json.dumps({"slots": slots, "count": count}, ensure_ascii=False).encode("utf-8")) > 1024 * 1024:
        raise invalid("CHARACTER_INPUT", "Saved NovelAI character slots exceed the 1 MiB metadata limit")
    return tuple(slots), count


def active_characters(slots, count):
    return tuple({k: v for k, v in s.items() if k not in {"enabled", "collapsed"}}
                 for s in slots[:count] if s["enabled"])


def replace_characters(request, characters):
    """Transform active text without dropping disabled/hidden slots or their identities."""
    slots = request.character_slots
    if slots is not None:
        indices = request.active_character_slots
        if len(characters) != len(indices):
            raise invalid("CHARACTER_INPUT", "Active character replacement must preserve slot count")
        slots = [dict(s) for s in slots]
        for index, character in zip(indices, characters):
            slots[index - 1].update(character)
    return replace(request, characters=tuple(characters), character_slots=slots)


def reject_credentials(value: object) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).lower() in CREDENTIAL_KEYS:
                raise invalid("REQUEST_INPUT", "credentials must only be configured in the server environment")
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
    character_slots: tuple[dict[str, object], ...] | None = None
    character_count: int | None = None
    use_coords: bool = True
    use_order: bool = True
    vibes: tuple[dict[str, object], ...] = ()
    references: tuple[dict[str, object], ...] = ()
    normalize_vibe_strengths: bool = True
    detailer: dict[str, object] | None = None

    def __post_init__(self) -> None:
        for label, value in (("prompt", self.prompt), ("negative prompt", self.negative_prompt)):
            if not isinstance(value, str) or len(value) > MAX_PROMPT_CHARACTERS:
                raise invalid("REQUEST_INPUT", f"{label} must be text with at most {MAX_PROMPT_CHARACTERS} characters")
        if not self.prompt.strip():
            raise invalid("REQUEST_INPUT", "prompt is required")
        if not isinstance(self.operation, str) or self.operation not in {"generate", "img2img", "infill", "detail", "focused_infill"}:
            raise invalid("REQUEST_INPUT", "Unsupported NovelAI operation")
        models = SUPPORTED_INPAINT_MODEL_IDS if self.operation in {"infill", "focused_infill"} else MODEL_IDS
        if not isinstance(self.model, str) or self.model not in models:
            raise invalid("MODEL", "unsupported NovelAI model")
        if not isinstance(self.sampler, str) or self.sampler not in SAMPLERS:
            raise invalid("REQUEST_INPUT", "unsupported NovelAI sampler")
        if not isinstance(self.scheduler, str) or self.scheduler not in SCHEDULERS:
            raise invalid("REQUEST_INPUT", "unsupported NovelAI scheduler")
        object.__setattr__(self, "characters", validate_characters(self.characters))
        if self.character_slots is not None:
            slots, count = validate_character_slots(self.character_slots, self.character_count)
            active = active_characters(slots, count)
            if self.characters and self.characters != active:
                raise invalid("CHARACTER_INPUT", "NovelAI active characters do not match saved slots")
            object.__setattr__(self, "character_slots", slots)
            object.__setattr__(self, "character_count", count)
            object.__setattr__(self, "characters", active)
        elif self.character_count is not None:
            raise invalid("CHARACTER_INPUT", "NovelAI character count requires saved slots")
        limit = character_limit(self.model)
        if len(self.characters) > limit:
            raise invalid("CHARACTER_MODEL" if limit == 0 else "CHARACTER_LIMIT", f"{self.model} supports at most {limit} active character prompts; received {len(self.characters)}. "
                             "Reduce character_count or disable slots. V5 Curated inpainting uses V4.5 (6 characters).")
        for name in ("limit_opus_free", "prefer_brownian", "variety_boost", "use_coords", "use_order", "normalize_vibe_strengths"):
            if not isinstance(getattr(self, name), bool):
                raise invalid("REQUEST_INPUT", f"{name} must be a boolean")
        from anima_app.providers.novelai.references import validate_compatibility, validate_entries
        object.__setattr__(self, "vibes", validate_entries(self.vibes, "vibe"))
        object.__setattr__(self, "references", validate_entries(self.references, "precise"))
        validate_compatibility(self.model, self.operation, self.vibes, self.references, self.limit_opus_free)
        from anima_app.providers.novelai.detailer import validate_settings
        object.__setattr__(self, "detailer", validate_settings(self.detailer or {}))
        if self.operation == "focused_infill":
            object.__setattr__(self, "detailer", {**self.detailer, "enabled": True})
        if self.operation == "detail" and not self.detailer["enabled"]:
            raise invalid("DETAIL_MODE", "Existing-image detail operation requires enabled detailer")
        if self.detailer["enabled"] and self.detailer["matching"] == "wd14" and not self.characters:
            raise invalid("MATCHING_INPUT", "WD matching requires original character prompts")
        if self.detailer["enabled"] and self.detailer["matching"] == "shared" and len(self.characters) > 1:
            raise invalid("MATCHING_INPUT", "Multiple characters require WD matching for detailing")
        if self.detailer["enabled"] and not self.detailer["preview_only"] and self.vibes and self.model.startswith("nai-diffusion-4"):
            raise invalid("VIBE_INPAINT", "V4/V4.5 Vibe cannot be used for detailing")
        for name in ("input_image", "mask_image"):
            value = getattr(self, name)
            if not isinstance(value, str) or len(value) > 4096:
                raise invalid("IMAGE_INPUT", f"{name} must be a managed image path")
        if self.operation in {"infill", "focused_infill"}:
            if not self.input_image or not self.mask_image:
                raise invalid("MASK_INPUT", "NovelAI inpaint requires an input image and a white-on-black mask")
            if self.limit_opus_free and self.operation == "infill":
                raise invalid("PAID_BLOCKED", "NAI 인페인트는 Anlas 비용이 발생할 수 있습니다. Opus 요청 한도를 직접 해제해 주세요.")
            if self.model in {"nai-diffusion-3-inpainting", "nai-diffusion-furry-3-inpainting"} and self.inpaint_strength != 1:
                raise invalid("REQUEST_INPUT", "NovelAI V3 inpainting only supports strength 1")
        elif self.operation in {"img2img", "detail"}:
            if self.limit_opus_free and self.operation == "img2img":
                raise invalid("PAID_BLOCKED", "NAI Img2Img는 Anlas 비용이 발생할 수 있습니다. Opus 보호 모드를 직접 해제해 주세요.")
            if not self.input_image or self.mask_image:
                raise invalid("IMAGE_INPUT", "NovelAI Img2Img/detail requires an input image and no mask")
        elif self.input_image or self.mask_image:
            raise invalid("IMAGE_INPUT", "image inputs require img2img or infill")
        for value in (self.width, self.height):
            if isinstance(value, bool) or not isinstance(value, int) or not 64 <= value <= MAX_GENERATION_DIMENSION or value % 64:
                raise invalid("REQUEST_INPUT", f"NovelAI width and height must be multiples of 64 between 64 and {MAX_GENERATION_DIMENSION}")
        if not self.limit_opus_free and self.width * self.height > MAX_BASE_IMAGE_PIXELS:
            raise invalid("REQUEST_INPUT", f"NovelAI image cannot exceed {MAX_BASE_IMAGE_PIXELS} pixels without the Opus request cap")
        if isinstance(self.steps, bool) or not isinstance(self.steps, int) or not 1 <= self.steps <= MAX_NAI_STEPS:
            raise invalid("REQUEST_INPUT", f"NovelAI steps must be an integer between 1 and {MAX_NAI_STEPS}")
        for label, value, maximum in (("cfg", self.cfg, MAX_CFG), ("cfg rescale", self.cfg_rescale, 1),
                                      ("inpaint strength", self.inpaint_strength, 1),
                                      ("Img2Img strength", self.img2img_strength, 1),
                                      ("Img2Img noise", self.img2img_noise, 1)):
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise invalid("REQUEST_INPUT", f"NovelAI {label} must be a finite number between 0 and {maximum}")
            try:
                valid = math.isfinite(value) and 0 <= value <= maximum
            except OverflowError:
                valid = False
            if not valid:
                raise invalid("REQUEST_INPUT", f"NovelAI {label} must be a finite number between 0 and {maximum}")
        if self.seed is not None and (isinstance(self.seed, bool) or not isinstance(self.seed, int) or not 0 <= self.seed <= MAX_NAI_SEED):
            raise invalid("REQUEST_INPUT", f"NovelAI seed must be an integer between 0 and {MAX_NAI_SEED}")

    @property
    def active_character_slots(self) -> list[int]:
        if self.character_slots is None:
            return list(range(1, len(self.characters) + 1))
        return [i + 1 for i, s in enumerate(self.character_slots[:self.character_count]) if s["enabled"]]

    def to_payload(self) -> dict[str, object]:
        values = asdict(self)
        for name in ("model", "sampler", "scheduler", "cfg_rescale", "prefer_brownian", "variety_boost", "limit_opus_free",
                     "characters", "character_slots", "character_count", "use_coords", "use_order", "vibes", "references", "normalize_vibe_strengths", "detailer"):
            values[f"nai_{name}"] = values.pop(name)
        values["nai_characters"] = list(values["nai_characters"])
        if self.character_slots is None:
            values.pop("nai_character_slots")
            values.pop("nai_character_count")
        else:
            values["nai_character_slots"] = list(values["nai_character_slots"])
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
    slots = payload.get("nai_character_slots", payload.get("character_slots"))
    count = payload.get("nai_character_count", payload.get("character_count"))
    if slots is not None:
        slots, count = validate_character_slots(slots, count)
        supplied = payload.get("nai_characters", payload.get("characters"))
        if supplied is not None and validate_characters(supplied) != active_characters(slots, count):
            raise invalid("CHARACTER_INPUT", "NovelAI active characters do not match saved slots")
    for name in ("i2i", "upscale", "face_detailer"):
        option = payload.get(name, {})
        if not isinstance(option, dict) or not isinstance(option.get("enabled", False), bool):
            raise invalid("REQUEST_INPUT", f"{name} must contain a boolean enabled flag")
        if option.get("enabled"):
            raise invalid("REQUEST_INPUT", f"NovelAI T2I does not support {name}")
    if payload.get("loras") or payload.get("i2i_image"):
        raise invalid("REQUEST_INPUT", "NovelAI T2I does not support local LoRAs or reference images")
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
        character_slots=slots, character_count=count,
        use_coords=payload.get("nai_use_coords", payload.get("use_coords", True)),
        use_order=payload.get("nai_use_order", payload.get("use_order", True)),
        vibes=payload.get("nai_vibes", payload.get("vibes", [])),
        references=payload.get("nai_references", payload.get("references", [])),
        normalize_vibe_strengths=payload.get("nai_normalize_vibe_strengths", True),
        detailer=payload.get("nai_detailer", payload.get("detailer", {})),
    )

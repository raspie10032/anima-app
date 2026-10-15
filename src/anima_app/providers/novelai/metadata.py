"""Read existing NovelAI images without submitting or retaining an image request."""
from __future__ import annotations

import gzip
import io
import json
import math
import re
import warnings
import zlib
from pathlib import Path
from typing import Any

from PIL import Image, UnidentifiedImageError

from anima_app.providers.novelai.models import (
    INPAINT_MODEL_IDS, INPAINT_MODELS, MODEL_IDS, SAMPLERS, SCHEDULERS,
    MAX_CHARACTER_SLOTS, SUPPORTED_INPAINT_MODEL_IDS, character_limit, default_skip_cfg_above_sigma,
)
from anima_app.requests import MAX_CFG, MAX_GENERATION_DIMENSION, MAX_PROMPT_CHARACTERS
from anima_app.providers.novelai.requests import active_characters, validate_characters, validate_character_slots

MAX_METADATA_BYTES = 1024 * 1024
MAX_METADATA_IMAGE_PIXELS = 16 * 1024 * 1024
METADATA_FIELDS = ("Comment", "Description", "Source", "Software", "anima_app_character_slots",
                   "rs_nai", "rs_detailer_regions", "rs_nai_inset")

# NovelAI /image frontend, pages/_app-b1c0ffe38c343809.js, 2026-10-09.
# DB276663 also matches this app's V5 Curated live acceptance.
# Keep unknown hashes unresolved rather than copying the website's default guess.
MODEL_HASHES = {
    **dict.fromkeys(("DB276663",), "nai-diffusion-5-curated"),
    **dict.fromkeys(("657484A5", "0ADF9AB7"), "nai-diffusion-5-full"),
    # Official web hash-family map, checked 2026-10-11. request_type decides infill.
    **dict.fromkeys(("93F4BD30", "70AB5786"), "nai-diffusion-5-full-medium"),
    **dict.fromkeys(("4BDE2A90", "1229B44F", "B9F340FD", "F3D95188"), "nai-diffusion-4-5-full"),
    **dict.fromkeys(("C02D4F98", "5AB81C7C", "B5A2A797"), "nai-diffusion-4-5-curated"),
    **dict.fromkeys(("37442FCA", "4F49EC75", "CA4B7203", "79F47848", "F6302A9D"), "nai-diffusion-4-full"),
    **dict.fromkeys(("7ABFFA2A", "C1CCBA86", "770A9E12"), "nai-diffusion-4-curated-preview"),
    **dict.fromkeys(("B0BDF6C1", "C1E1DE52", "7BCCAA2C", "1120E6A9", "8BA2AF87"), "nai-diffusion-3"),
    **dict.fromkeys(("4BE8C60C", "C8704949", "37C2B166", "F306816B", "9CC2F394"), "nai-diffusion-furry-3"),
}
# The website collapses these variants into a model family. Without request_type
# that alone cannot establish whether a file used T2I or a dedicated infill model.
MODEL_FAMILY_ONLY_HASHES = {"1229B44F", "B9F340FD", "F3D95188", "93F4BD30", "70AB5786"}
REQUEST_MODES = {"PromptGenerateRequest": "t2i", "Img2ImgRequest": "i2i", "NativeInfillingRequest": "inpaint"}


def _character_fields(comment: dict[str, Any]) -> dict[str, Any]:
    positive = comment.get("v4_prompt", {})
    negative = comment.get("v4_negative_prompt", {})
    if not isinstance(positive, dict) or not isinstance(negative, dict):
        raise ValueError("invalid character blocks")
    pos_caption, neg_caption = positive.get("caption", {}), negative.get("caption", {})
    if not isinstance(pos_caption, dict) or not isinstance(neg_caption, dict):
        raise ValueError("invalid character captions")
    pos = pos_caption.get("char_captions", [])
    neg = neg_caption.get("char_captions", [])
    coords, order = positive.get("use_coords", False), positive.get("use_order", True)
    if type(coords) is not bool or type(order) is not bool:
        raise ValueError("invalid character flags")
    if not isinstance(pos, list) or not isinstance(neg, list) or len(pos) > MAX_CHARACTER_SLOTS or neg and len(pos) != len(neg):
        raise ValueError("unsupported character count")
    characters = []
    for index, item in enumerate(pos):
        uc = neg[index] if neg else {}
        if not isinstance(item, dict) or not isinstance(uc, dict):
            raise ValueError("invalid character caption")
        centers = item.get("centers", [])
        if not isinstance(centers, list) or len(centers) > 1 or coords and not centers:
            raise ValueError("multiple or missing character centers")
        center = centers[0] if centers else {"x": 0.5, "y": 0.5}
        if not isinstance(center, dict) or set(center) != {"x", "y"}:
            raise ValueError("invalid character center")
        if uc.get("centers") and uc["centers"] != centers:
            raise ValueError("different negative character centers")
        characters.append({"prompt": item.get("char_caption", ""), "negative_prompt": uc.get("char_caption", ""), **center})
    return {"nai_characters": list(validate_characters(characters)), "nai_use_coords": coords, "nai_use_order": order}


def _json_object(value: object) -> dict[str, Any]:
    if isinstance(value, str):
        if len(value.encode("utf-8")) > MAX_METADATA_BYTES:
            raise ValueError("NAI 메타데이터가 너무 큽니다.")
        try:
            value = json.loads(value)
        except (ValueError, RecursionError):
            raise ValueError("NAI 메타데이터 JSON을 읽을 수 없습니다.") from None
    if not isinstance(value, dict):
        raise ValueError("NAI 메타데이터는 JSON 객체여야 합니다.")
    return value


def _alpha_metadata(image: Image.Image) -> dict[str, Any] | None:
    if image.mode != "RGBA":
        return None
    import numpy as np

    alpha = np.asarray(image.getchannel("A"), dtype=np.uint8).T.reshape(-1)
    packed = np.packbits(alpha & 1).tobytes()
    magic = b"stealth_pngcomp"
    if not packed.startswith(magic):
        return None
    header = len(magic) + 4
    bits = int.from_bytes(packed[len(magic):header], "big")
    if bits % 8 or not 0 < bits // 8 <= MAX_METADATA_BYTES or header + bits // 8 > len(packed):
        raise ValueError("숨겨진 NAI 메타데이터 길이가 올바르지 않습니다.")
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(packed[header:header + bits // 8])) as compressed:
            decoded = compressed.read(MAX_METADATA_BYTES + 1)
        if len(decoded) > MAX_METADATA_BYTES:
            raise ValueError("NAI 메타데이터가 너무 큽니다.")
        return _json_object(decoded.decode("utf-8"))
    except (OSError, EOFError, UnicodeError, zlib.error):
        raise ValueError("숨겨진 NAI 메타데이터를 읽을 수 없습니다.") from None


def _file_metadata(image: Image.Image) -> dict[str, Any]:
    if image.format == "PNG":
        return {name: image.info[name] for name in METADATA_FIELDS if name in image.info}
    exif = image.getexif()
    result = {name: exif[tag] for tag, name in ((270, "Description"), (305, "Source")) if tag in exif}
    comment = exif.get_ifd(34665).get(37510) if 34665 in exif else exif.get(37510)
    if isinstance(comment, bytes):
        if comment.startswith(b"ASCII\x00\x00\x00"):
            comment = comment[8:].rstrip(b"\x00").decode("utf-8")
        elif comment.startswith(b"UNICODE\x00"):
            comment = comment[8:].decode("utf-16").rstrip("\x00")
        else:
            raise ValueError("지원하지 않는 WebP 메타데이터 인코딩입니다.")
    if comment is not None:
        result["Comment"] = comment
    if 37395 in exif:
        # RS NAI stores PNG-equivalent fields in ImageHistory on WebP.
        try:
            extra = _json_object(exif[37395])
            result.update({key: value for key, value in extra.items() if key in METADATA_FIELDS})
        except (ValueError, RecursionError):
            # Do not fall back to a possibly stale crop Comment after a broken record.
            result["rs_nai"] = "invalid"
    return result


def read_image_metadata(path: Path) -> dict[str, Any]:
    """Return only form fields and diagnostics; never raw reference or secret fields."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(path) as image:
                if image.format not in {"PNG", "WEBP"}:
                    raise ValueError("NAI PNG 또는 WebP 파일을 선택해 주세요.")
                if image.width * image.height > MAX_METADATA_IMAGE_PIXELS:
                    raise ValueError("메타데이터 이미지의 최대 크기는 16메가픽셀입니다.")
                image.load()
                metadata = _file_metadata(image)
                location = "png_text" if image.format == "PNG" else "webp_exif"
                if not any(key in metadata for key in ("Comment", "rs_nai", "rs_detailer_regions")):
                    metadata = {**metadata, **(_alpha_metadata(image) or {})}
                    location = "alpha"
                if not any(key in metadata for key in ("Comment", "rs_nai", "rs_detailer_regions")):
                    raise ValueError("NAI 생성 메타데이터가 없습니다. 원본 파일을 사용해 주세요.")
                result = normalize_metadata(metadata)
                result.update(metadata_source=location, image_width=image.width, image_height=image.height)
                if (result["request"].get("width", image.width), result["request"].get("height", image.height)) != image.size:
                    result["warnings"].append("파일 크기와 생성 크기가 다릅니다. 메타데이터에 기록된 생성 크기를 적용합니다.")
                return result
    except (UnidentifiedImageError, OSError, SyntaxError, UnicodeError,
            Image.DecompressionBombWarning, Image.DecompressionBombError):
        raise ValueError("이미지 파일이 손상되었거나 지원 범위를 벗어났습니다.") from None


def normalize_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    if any(key in metadata for key in ("rs_nai", "rs_detailer_regions", "rs_nai_inset")):
        from anima_app.providers.novelai.rs_metadata import normalize_record
        return normalize_record(metadata)
    comment = _json_object(metadata.get("Comment"))
    source = metadata.get("Source", "")
    source = source if isinstance(source, str) else ""
    explicit = comment.get("model", comment.get("model_id"))
    if not explicit and isinstance(comment.get("model_name"), str) and comment["model_name"] in MODEL_IDS | INPAINT_MODEL_IDS:
        explicit = comment["model_name"]
    explicit_inpaint = isinstance(explicit, str) and explicit in INPAINT_MODEL_IDS
    source_match = re.search(r"\b([0-9a-fA-F]{8})$", source)
    source_hash = source_match.group(1).upper() if source_match else None
    source_label = source if len(source) <= 200 and re.fullmatch(
        r"(?:NovelAI Diffusion|Stable Diffusion XL|DiffusionModelMetaName\.NAIv4next)[ A-Za-z0-9.]*", source
    ) else None
    if not (metadata.get("Software") == "NovelAI" or source.startswith("NovelAI Diffusion")
            or source.startswith("Stable Diffusion XL") and source_hash in MODEL_HASHES
            or isinstance(explicit, str) and explicit in MODEL_IDS or explicit_inpaint):
        raise ValueError("NAI 생성 메타데이터를 확인할 수 없습니다.")
    request: dict[str, Any] = {"provider": "novelai"}
    notices: list[str] = []
    if metadata.get("Software") == "Anima APP" and comment.get("anima_app_composite") is True:
        notices.append("이 파일은 Anima APP에서 마스크 합성한 결과입니다. 원격 응답 원본은 별도로 보존되며, 합성 파일은 NAI 서명 검증용 원본이 아닙니다.")
    invalid: list[str] = []
    model_hash = comment.get("model_hash")
    model_hash = model_hash.upper() if isinstance(model_hash, str) and re.fullmatch(r"[0-9a-fA-F]{8}", model_hash) else source_hash
    model = MODEL_HASHES.get(model_hash or "")
    request_type = comment.get("request_type")
    mode = REQUEST_MODES.get(request_type, "unknown") if isinstance(request_type, str) else "unknown"
    if explicit_inpaint:
        mode = "inpaint"
        explicit = next(base for base, infill in INPAINT_MODELS.items() if infill == explicit)
    if model_hash and source_hash and model_hash != source_hash:
        model = None
        notices.append("Source와 model_hash가 다릅니다. 모델을 직접 확인해 주세요.")
    elif isinstance(explicit, str) and explicit in MODEL_IDS:
        if model and model != explicit:
            model = None
            notices.append("모델 ID와 해시가 다릅니다. 모델을 직접 확인해 주세요.")
        else:
            model = explicit
    detected_model = INPAINT_MODELS[model] if model and mode == "inpaint" else model
    migrated_model = bool(model and source.startswith("NovelAI Diffusion V4 ") and model.startswith("nai-diffusion-4-5"))
    if model and mode != "inpaint" and not migrated_model and not (mode == "unknown" and model_hash in MODEL_FAMILY_ONLY_HASHES):
        request["nai_model"] = model
    elif model and mode == "inpaint" and not migrated_model and detected_model in SUPPORTED_INPAINT_MODEL_IDS:
        request["nai_model"] = detected_model
    elif not model:
        notices.append("알 수 없는 모델 해시 또는 모델입니다. 적용 전에 모델을 선택해 주세요.")
    if mode == "inpaint":
        if detected_model and detected_model not in SUPPORTED_INPAINT_MODEL_IDS:
            notices.append("원본 인페인트 모델은 현재 웹의 실행 모델 목록에 없습니다. 다른 모델로 자동 변경하지 않으므로 모델을 직접 선택하세요.")
        request["operation"] = "infill"
        # Always clear previously selected inputs; generated files do not contain the original mask.
        request.update(input_image="", mask_image="")
        strength = comment.get("inpaintImg2ImgStrength")
        if strength is None and isinstance(comment.get("img2img"), dict):
            strength = comment["img2img"].get("strength")
        if strength is not None:
            if not isinstance(strength, bool) and isinstance(strength, (int, float)) and 0 <= strength <= 1:
                request["inpaint_strength"] = strength
            else:
                invalid.append("inpaint_strength")
        notices.append("인페인트 조건을 가져옵니다. 원본 입력 이미지와 마스크는 생성 결과에 포함되지 않으므로 다시 지정해 주세요. "
                       "인페인트 비용을 허용하려면 Opus 요청 한도를 직접 해제해야 합니다.")
    elif mode == "i2i":
        notices.append("Img2Img 조건을 가져옵니다. 원본 입력 이미지는 다시 지정하고 Opus 보호 모드를 직접 해제해 주세요.")
        request.update(operation="img2img", input_image="", mask_image="")
        for target, key in (("img2img_strength", "strength"), ("img2img_noise", "noise")):
            value = comment.get(key)
            if value is not None:
                if type(value) in (int, float) and 0 <= value <= 1:
                    request[target] = value
                else:
                    invalid.append(target)
    else:
        request.update(operation="generate", input_image="", mask_image="")
    if mode == "unknown" and model_hash in MODEL_FAMILY_ONLY_HASHES:
        notices.append("이 해시는 모델 계열만 확인됩니다. 인페인트 여부를 확정할 수 없어 T2I 모델을 자동 선택하지 않습니다.")
    if migrated_model:
        notices.append("NAI 웹의 현행 대응표는 이 V4 해시를 V4.5로 연결합니다. 원본과 다른 버전을 자동 적용하지 않으므로 모델을 직접 확인해 주세요.")

    def caption(name: str, key: str) -> object:
        block = comment.get(name)
        block = block.get("caption") if isinstance(block, dict) else None
        if isinstance(block, dict) and "base_caption" in block:
            return block["base_caption"]
        fallback = metadata.get("Description") if key == "prompt" else comment.get("negative_prompt")
        return comment.get(key, fallback)

    for target, value in (("prompt", caption("v4_prompt", "prompt")),
                          ("negative_prompt", caption("v4_negative_prompt", "uc"))):
        if value is None:
            continue
        if isinstance(value, str) and len(value) <= MAX_PROMPT_CHARACTERS and (target != "prompt" or value.strip()):
            request[target] = value
        else:
            invalid.append(target)
    for target, key, maximum, minimum, multiple in (
        ("width", "width", MAX_GENERATION_DIMENSION, 64, 64),
        ("height", "height", MAX_GENERATION_DIMENSION, 64, 64),
        ("steps", "steps", 50, 1, 1), ("seed", "seed", 2**32 - 1, 0, 1),
        ("cfg", "scale", MAX_CFG, 0, None), ("nai_cfg_rescale", "cfg_rescale", 1, 0, None),
    ):
        if key not in comment:
            continue
        value = comment[key]
        try:
            valid = (not isinstance(value, bool) and isinstance(value, (int, float))
                     and math.isfinite(value) and minimum <= value <= maximum
                     and (multiple is None or isinstance(value, int) and value % multiple == 0))
        except OverflowError:
            valid = False
        if valid:
            request[target] = value
        else:
            invalid.append(target)
    for target, key, options in (("nai_sampler", "sampler", SAMPLERS), ("nai_scheduler", "noise_schedule", SCHEDULERS)):
        if key in comment:
            if isinstance(comment[key], str) and comment[key] in options:
                request[target] = comment[key]
            else:
                invalid.append(target)
    if "prefer_brownian" in comment:
        if isinstance(comment["prefer_brownian"], bool):
            request["nai_prefer_brownian"] = comment["prefer_brownian"]
        else:
            invalid.append("nai_prefer_brownian")
    skip_cfg = comment.get("skip_cfg_above_sigma")
    if "skip_cfg_above_sigma" in comment:
        default = default_skip_cfg_above_sigma(model or "")
        if skip_cfg is None:
            request["nai_variety_boost"] = False
        elif default is not None and not isinstance(skip_cfg, bool) and skip_cfg == default:
            request["nai_variety_boost"] = True
        else:
            notices.append("사용자 지정 Variety boost 값은 현재 앱에서 재현할 수 없습니다.")

    unsupported: list[str] = []
    if mode not in {"inpaint", "i2i"} and comment.get("strength"):
        unsupported.append("이미지 입력 / 마스크 / noise")
    try:
        request.update(_character_fields(comment))
    except ValueError:
        # Do not partially import or silently truncate a character layout.
        request["nai_characters"] = []
        unsupported.append("캐릭터별 프롬프트와 좌표 (최대 22명, 캐릭터당 좌표 1개; 원본 구조를 확인하세요)")
    if "anima_app_character_slots" in metadata:
        try:
            saved = _json_object(metadata["anima_app_character_slots"])
            if saved.keys() - {"slots", "count"}:
                raise ValueError("Invalid slot metadata")
            slots, count = validate_character_slots(saved.get("slots"), saved.get("count"))
            request.update(nai_character_slots=list(slots), nai_character_count=count,
                           nai_characters=list(active_characters(slots, count)))
            notices.append("앱에 저장한 캐릭터 슬롯·숨김·사용 여부·접기 상태를 복원합니다. 와일드카드와 Medium 적용 전 입력값이며 NAI 서명 정보가 아닙니다.")
        except ValueError:
            invalid.append("nai_character_slots")
    selected_model = request.get("nai_model")
    if selected_model and len(request.get("nai_characters", [])) > character_limit(selected_model):
        notices.append(f"이 모델은 활성 캐릭터 {character_limit(selected_model)}명까지 지원합니다. 가져온 값은 보존하며, 생성 전에 슬롯 수를 줄이거나 사용을 해제하세요.")
    if metadata.get("Software") == "Anima APP" and isinstance(comment.get("anima_app_detailer"), dict):
        from anima_app.providers.novelai.detailer import validate_settings
        try:
            request["nai_detailer"] = validate_settings(comment["anima_app_detailer"])
            operation = comment.get("anima_app_operation")
            if operation in {"detail", "focused_infill"}:
                request.update(operation=operation, input_image="", mask_image="")
                notices.append("앱의 보정 조건을 가져옵니다. 입력 이미지 / 마스크를 다시 지정해 주세요.")
        except (ValueError, TypeError):
            invalid.append("nai_detailer")
    for keys, label in (
        (("reference_image_multiple", "reference_strength_multiple", "reference_information_extracted_multiple"), "Vibe Transfer"),
        (("director_reference_images", "director_reference_strengths", "director_reference_descriptions"), "Precise Reference"),
        (("sm", "sm_dyn"), "SMEA / DYN"), (("dynamic_thresholding",), "Dynamic thresholding"),
        (("image", "mask"), "원본 이미지 입력 / 마스크"),
        (("legacy_v3_extend", "legacy_uc", "legacy"), "레거시 옵션"),
        (("deliberate_euler_ancestral_bug",), "구형 Euler ancestral 동작"),
        (("upscale", "quality_boost", "straight_alpha"), "업스케일 / 추가 출력 옵션"),
    ):
        if any(comment.get(key) for key in keys):
            unsupported.append(label)
    if unsupported:
        notices.append("현재 앱에서 복원하지 못하는 조건: " + ", ".join(unsupported))
    if invalid:
        notices.append("지원 범위를 벗어나 적용하지 않는 값: " + ", ".join(invalid))
    required = ("prompt", "negative_prompt", "width", "height", "steps", "cfg", "seed", "nai_sampler", "nai_scheduler",
                "nai_cfg_rescale", "nai_prefer_brownian", "nai_variety_boost")
    missing = [key for key in required if key not in request]
    if missing:
        notices.append("메타데이터에 없거나 적용할 수 없는 항목은 현재 폼 값을 유지합니다: " + ", ".join(missing))
    notices.append("Opus 요청 한도는 현재 설정을 유지합니다. 실제 전송 크기와 스텝을 확인해 주세요.")
    return {"status": "metadata_read", "request": request, "model_hash": model_hash,
            "source_model": source_label, "detected_model": detected_model, "generation_mode": mode,
            "model_candidates": sorted(SUPPORTED_INPAINT_MODEL_IDS if mode == "inpaint" else MODEL_IDS), "warnings": notices,
            "unsupported": unsupported, "missing": missing}

"""Read the pinned RS NAI 2.9.0 autosave schema, keeping crop history separate."""
from __future__ import annotations

from anima_app.providers.novelai.metadata import _json_object, normalize_metadata
from anima_app.providers.novelai.models import MODEL_IDS, INPAINT_MODEL_IDS


def _from_request(record):
    if not isinstance(record, dict) or not isinstance(record.get("parameters"), dict):
        raise ValueError("invalid saved request")
    parameters = record["parameters"]
    if not isinstance(record.get("input"), str) or not record["input"].strip():
        raise ValueError("missing source prompt")
    if not isinstance(parameters.get("negative_prompt"), str):
        raise ValueError("missing source negative prompt")
    model = record.get("model")
    if not isinstance(model, str) or model not in MODEL_IDS | INPAINT_MODEL_IDS:
        raise ValueError("unknown source model")
    comment = {**parameters, "model": model, "prompt": record["input"]}
    action = record.get("action")
    if action not in {"generate", "img2img", "infill"}:
        raise ValueError("unknown source operation")
    comment["request_type"] = {"generate": "PromptGenerateRequest", "img2img": "Img2ImgRequest",
                               "infill": "NativeInfillingRequest"}[action]
    result = normalize_metadata({"Software": "NovelAI", "Comment": comment})
    if record.get("references_omitted"):
        result["warnings"].append("참조 이미지가 사용된 기록입니다. 참조 이미지는 다시 지정해 주세요.")
    return result


def _partial(message, history=()):
    return {"status": "metadata_partial", "can_apply": False, "request": {},
            "model_hash": None, "source_model": None, "detected_model": None,
            "generation_mode": "unknown", "model_candidates": [], "warnings": [message],
            "missing": [], "unsupported": [], "correction_history": list(history)}


def normalize_record(metadata):
    # Never return the raw record: it may contain credentials, image bytes or paths.
    record = {}
    try:
        if "rs_nai" in metadata:
            record = _json_object(metadata["rs_nai"])
            if type(record.get("version")) is not int or record["version"] != 1:
                raise ValueError("unsupported record version")
    except (ValueError, RecursionError):
        return _partial("RS NAI 생성 기록이 손상되었거나 지원하지 않는 버전입니다. 이미지 검색은 사용할 수 있습니다.")
    history = []
    edits = record.get("edits", [])
    if isinstance(edits, list):
        for index, edit in enumerate(edits[:64]):
            try:
                if not isinstance(edit, dict):
                    continue
                restored = _from_request(edit.get("request"))
                history.append({"region": index + 1, "request": restored["request"]})
            except (ValueError, TypeError, OverflowError, RecursionError):
                continue
    detail = record.get("operation") == "detailer" or "rs_detailer_regions" in metadata
    if detail:
        try:
            if record.get("base_generation_available") is not True:
                raise ValueError("no source context")
            result = _from_request(record.get("base_generation"))
        except (ValueError, TypeError, OverflowError, RecursionError):
            return _partial("그림 전체의 생성 조건이 없는 디테일러 결과입니다. 얼굴 보정 기록은 전체 프롬프트로 적용하지 않습니다.", history)
        result["settings_origin"] = "base_generation"
        result["warnings"].insert(0, "원본 그림의 생성 조건을 복원했습니다. 얼굴별 보정 기록은 별도로 표시합니다.")
    else:
        try:
            if record.get("request") is not None:
                result = _from_request(record["request"])
            else:
                result = normalize_metadata({key: value for key, value in metadata.items()
                                             if key not in {"rs_nai", "rs_detailer_regions", "rs_nai_inset"}})
        except (ValueError, TypeError, OverflowError, RecursionError):
            return _partial("RS NAI 생성 조건을 복원할 수 없습니다. 이미지 검색은 사용할 수 있습니다.", history)
        result["settings_origin"] = "generation"
    result.update(correction_history=history, can_apply=True)
    if record.get("operation") == "inset" or "rs_nai_inset" in metadata:
        result["can_apply"] = False
        result["warnings"].append("인셋 그림은 원본 참조 캔버스가 필요합니다. 프롬프트는 확인할 수 있지만 생성 조건은 자동 적용하지 않습니다.")
    return result

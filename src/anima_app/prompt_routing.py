"""Provider prompt adaptation and local case references, without network access.

Authoring text is retained separately from the actual provider prompt. Adaptation
is opt-in for API clients and enabled by the workspace UI.
"""
from __future__ import annotations

import copy
import re

from anima_app.manifests import _write_json_atomically, read_manifest
from anima_app.providers.novelai.converters import convert_prompt
from anima_app.providers.novelai.requests import reject_credentials
from anima_app.requests import MAX_PROMPT_CHARACTERS

FORMATS = {"auto", "comfyui", "naiv4", "oldnai", "native"}


def normalize_routing(value):
    if not isinstance(value, dict) or value.keys() - {"source"} or value.get("source") not in FORMATS:
        raise ValueError("프롬프트 표기는 auto, comfyui, naiv4, oldnai, native 중 선택해 주세요.")
    return {"source": value["source"]}


def normalize_sources(value):
    if not isinstance(value, list) or len(value) > 16:
        raise ValueError("참고 사례는 최대 16개까지 연결할 수 있습니다.")
    out = []
    for row in value:
        if not isinstance(row, dict) or row.keys() - {"asset_id", "record_id", "scope"}:
            raise ValueError("참고 사례의 필드가 올바르지 않습니다.")
        if any(not isinstance(row.get(k), str) or not re.fullmatch(r"[0-9a-f]{64}", row[k]) for k in ("asset_id", "record_id")):
            raise ValueError("참고 이미지와 생성 기록 ID가 올바르지 않습니다.")
        if row.get("scope") not in {"artists", "prompt", "all"}:
            raise ValueError("참고 사례의 적용 범위가 올바르지 않습니다.")
        if row not in out:
            out.append(dict(row))
    return out


def context_fields(payload):
    result = {}
    if "prompt_routing" in payload:
        result["prompt_routing"] = normalize_routing(payload["prompt_routing"])
    if "generation_sources" in payload:
        result["generation_sources"] = normalize_sources(payload["generation_sources"])
    return result


def detect_format(text, target):
    numeric_nai = bool(re.search(r"(?:^|,)\s*-?\d+(?:\.\d+)?::", text))
    comfy = bool(re.search(r"(?<!\\)\([^\n]*?:-?\d+(?:\.\d+)?\s*\)", text))
    if numeric_nai and comfy:
        raise ValueError("NAI와 Anima 가중치가 섞여 있습니다. 입력 표기를 하나로 맞추거나 '변환 안 함'을 선택해 주세요.")
    if numeric_nai:
        return "naiv4"
    if comfy:
        return "comfyui"
    # Wildcards use braces too; detect only after expanding them for execution.
    if re.search(r"[{}\[\]]", text) and not re.search(r"\{[^{}]*\|", text):
        return "oldnai"
    # Bare parentheses are ambiguous (character copyrights vs emphasis). Keep
    # them native unless the user explicitly chooses ComfyUI syntax.
    return target


def route_text(text, source, target, *, catalog=None, inferred=None):
    if not isinstance(text, str) or len(text) > MAX_PROMPT_CHARACTERS:
        raise ValueError("프롬프트 길이를 확인해 주세요.")
    if source == "native":
        return text, [], "native"
    detected = detect_format(text, target) if source == "auto" else source
    if catalog:
        from anima_app.artist_catalog import mark_bare_artists
        text, matches = mark_bare_artists(text, catalog.get("names", {}))
        if inferred is not None:
            inferred.extend(matches)
    normalized = re.sub(r"(^|[\s,(:])@(?=\S)", r"\1artist:", text)
    warnings = []
    if detected != target and normalized:
        conversion = convert_prompt({"text": normalized, "source": detected, "target": target})
        normalized, warnings = conversion["converted"], conversion["warnings"]
        # Never silently send a prompt after the converter discarded a tag.
        if any("제외했습니다" in warning or "대체했습니다" in warning for warning in warnings):
            raise ValueError("프롬프트 자동 변환을 멈췄습니다: " + "; ".join(warnings))
    if target == "comfyui":
        normalized = re.sub(r"(^|[\s,(])artist:\s*", r"\1@", normalized, flags=re.I)
    if len(normalized) > MAX_PROMPT_CHARACTERS:
        raise ValueError("변환된 프롬프트가 길이 제한을 넘습니다.")
    return normalized, warnings, detected


def route_request(payload, *, paths=None):
    """Return an independent provider payload and a bounded conversion receipt."""
    reject_credentials(payload)
    request = copy.deepcopy(payload)
    config = context_fields(payload)
    routing = config.get("prompt_routing", {"source": "native"})
    provider = payload.get("provider", "local")
    if provider not in {"local", "novelai"}:
        raise ValueError("생성 엔진이 올바르지 않습니다.")
    model = payload.get("nai_model", payload.get("model", "nai-diffusion-5-curated"))
    target = "comfyui" if provider == "local" else "oldnai" if re.match(r"nai-diffusion-(?:furry-)?3(?:$|-)", str(model)) else "naiv4"
    fields, warnings = [], []
    from anima_app.artist_catalog import load_catalog
    catalog = load_catalog(paths)

    def adapt(container, key, path):
        original = container.get(key, "")
        inferred = []
        converted, notices, detected = route_text(original, routing["source"], target, catalog=catalog, inferred=inferred)
        container[key] = converted
        fields.append({"field": path, "original": original, "converted": converted, "source": detected, "recognized_artists": inferred})
        warnings.extend(notices)

    for key in ("prompt", "negative_prompt"):
        adapt(request, key, key)
    # Both active characters and inactive saved slots preserve their own text.
    for key in ("nai_characters", "nai_character_slots"):
        for i, character in enumerate(request.get(key, [])):
            for field in ("prompt", "negative_prompt"):
                adapt(character, field, f"{key}.{i}.{field}")
    receipt = {"version": 1, "source": routing["source"], "target": target, "fields": fields,
               "warnings": list(dict.fromkeys(warnings)), "artist_catalog": {k:v for k,v in catalog.items() if k != "names"}}
    return request, receipt


def preview_plan(payload, *, paths=None):
    from anima_app.server import _normalized_preset_request
    from anima_app.workflows import output_size, stage_request
    base = _normalized_preset_request({k: v for k, v in payload.items() if k != "workflow"})
    planned = [base]
    if "workflow" in payload:
        from anima_app.workflows import normalize_workflow
        workflow = normalize_workflow(payload["workflow"], base)
        size = output_size(base)
        for step in workflow["steps"]:
            request = stage_request(step, base, size)
            planned.append(request)
            size = output_size(request)
    stages = []
    for i, request in enumerate(planned):
        _, receipt = route_request(request, paths=paths)
        stages.append({"index": i + 1, "provider": request.get("provider", "local"),
                       "operation": request.get("operation", "generate"), **receipt})
    return {"stages": stages, "note": "미리보기는 생성하지 않습니다. 와일드카드는 실행 시 펼친 뒤 변환합니다."}


def save_context(path, authoring, receipt):
    """Keep a replayable authoring request beside the effective image manifest."""
    from anima_app.server import _normalized_preset_request
    context = context_fields(authoring)
    if not context:
        return
    manifest = read_manifest(path)
    manifest.update(context)
    manifest["authoring_request"] = _normalized_preset_request(authoring)
    manifest["prompt_processing"] = receipt
    manifest["warnings"] = [*manifest.get("warnings", []), *receipt["warnings"]]
    _write_json_atomically(path, manifest)

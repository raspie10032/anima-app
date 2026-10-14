"""Ordered, durable cross-provider image work. No transport or implicit retries here."""
from __future__ import annotations

import copy
import hashlib
import time
import uuid
from pathlib import Path

from PIL import Image

from anima_app.assets import store_reference_upload
from anima_app.manifests import _write_json_atomically, read_manifest
from anima_app.providers import novelai
from anima_app.providers.novelai.errors import NovelAIError
from anima_app.providers.novelai.requests import reject_credentials

MAX_STEPS = 6
PREVIOUS_IMAGE = "inputs/references/workflow-previous.png"


def has_local_step(payload):
    return payload.get("provider", "local") == "local" or any(
        s.get("provider") == "local" for s in payload.get("workflow", {}).get("steps", []))


def output_size(request):
    if request.get("provider") == "novelai":
        effective, _ = novelai.build_payload(novelai.request_from_payload(request))
        return effective.width, effective.height
    width, height = request["width"], request["height"]
    upscale = request.get("upscale", {})
    if upscale.get("enabled"):
        # Comfy common_upscale works in latent pixels and rounds down to integers.
        scale = upscale["scale"]
        return int(width // 8 * scale) * 8, int(height // 8 * scale) * 8
    return width, height


def stage_request(step, base, size, input_image=PREVIOUS_IMAGE):
    request = copy.deepcopy(step["request"])
    request.update(provider=step["provider"], operation=step["operation"], width=size[0], height=size[1])
    if step["inherit_prompt"]:
        request.update(prompt=base["prompt"], negative_prompt=base.get("negative_prompt", ""))
        if "prompt_routing" in base:
            request["prompt_routing"] = copy.deepcopy(base["prompt_routing"])
    elif "prompt_routing" not in request and "prompt_routing" in base:
        request["prompt_routing"] = {"source": "auto"}
    if "generation_sources" in base:
        request["generation_sources"] = copy.deepcopy(base["generation_sources"])
    if step["provider"] == "local":
        request["i2i"] = {"enabled": True, "image_path": input_image, "denoise": 0}
    else:
        request.update(input_image=input_image, mask_image="")
    return request


def normalize_workflow(value, base):
    from anima_app.server import _normalized_preset_request
    reject_credentials(value)
    if not isinstance(value, dict) or value.keys() - {"version", "steps"} or value.get("version", 1) != 1:
        raise ValueError("workflow must be a version 1 object")
    steps = value.get("steps")
    if not isinstance(steps, list) or not 1 <= len(steps) <= MAX_STEPS:
        raise ValueError(f"workflow requires 1 to {MAX_STEPS} post-processing steps")
    normalized, size = [], output_size(base)
    for index, raw in enumerate(steps):
        if not isinstance(raw, dict) or raw.keys() - {"provider", "operation", "request", "inherit_prompt"}:
            raise ValueError(f"workflow step {index + 2}: invalid fields")
        provider, operation = raw.get("provider"), raw.get("operation")
        if (provider, operation) not in {("local", "detail"), ("local", "upscale"), ("novelai", "detail")}:
            raise ValueError("workflow supports Anima detail/upscale and NovelAI detail")
        inherit = raw.get("inherit_prompt", True)
        if type(inherit) is not bool:
            raise ValueError("inherit_prompt must be a boolean")
        request = copy.deepcopy(raw.get("request", {}))
        if not isinstance(request, dict) or any(k in request for k in ("workflow", "workflow_base_request", "dry_run", "progress_id")):
            raise ValueError("workflow step cannot contain nested workflows or execution overrides")
        if provider == "local":
            request["upscale"] = {**request.get("upscale", {}), "enabled": operation == "upscale"}
            request["face_detailer"] = {**request.get("face_detailer", {}), "enabled": operation == "detail"}
        else:
            request["nai_detailer"] = {**request.get("nai_detailer", {}), "enabled": True}
            if request["nai_detailer"].get("preview_only"):
                raise ValueError("workflow detailer must render; use standalone preview to inspect masks")
        step = {"provider": provider, "operation": operation, "inherit_prompt": inherit, "request": request}
        effective = _normalized_preset_request(stage_request(step, base, size))
        # A whole-canvas size change during detail would violate the chain contract.
        if provider == "novelai" and output_size(effective) != size:
            raise ValueError("NAI detailer cannot resize the preceding result; reduce the earlier image dimensions")
        size = output_size(effective)
        if provider == "local":
            effective["i2i"] = {"enabled": False, "image_path": "", "denoise": 0}
        else:
            effective["input_image"] = ""
        step["request"] = effective
        normalized.append(step)
    return {"version": 1, "steps": normalized}


def preflight(payload, paths, *, dry_run):
    """Validate the complete plan before a paid base request can be sent."""
    from anima_app.server import (_normalized_preset_request, _generation_readiness,
                                  _validate_managed_generation_inputs, request_from_payload)
    from anima_app.runtime.comfy_t2i import resolve_managed_lora_path
    from anima_app.runtime.face_detailer import missing_detector_paths
    from anima_app.requests import FaceDetailerSettings
    from anima_app.providers.novelai.references import validate_managed_references
    base = _normalized_preset_request({k: v for k, v in payload.items() if k != "workflow"})
    workflow = normalize_workflow(payload["workflow"], base)
    size = output_size(base)
    planned = [base]
    for step in workflow["steps"]:
        request = _normalized_preset_request(stage_request(step, base, size))
        planned.append(request)
        size = output_size(request)
    for index, request in enumerate(planned):
        from anima_app.prompt_routing import route_request
        route_request(request, paths=paths)
        if request.get("provider") == "novelai":
            parsed = novelai.request_from_payload(request)
            validate_managed_references(parsed, paths)
            if not dry_run and not novelai.token_status()["configured"]:
                raise NovelAIError("nai_token_missing", f"{index + 1}단계: NAI_ACCESS_TOKEN 설정이 필요합니다.", 409)
            detail = parsed.detailer
            settings = FaceDetailerSettings(enabled=detail["enabled"], mask_backend=detail["backend"],
                                          sam3_hands="hands" in detail["concepts"])
        else:
            parsed = request_from_payload(request)
            if index == 0:
                _validate_managed_generation_inputs(parsed, paths)
            for lora in parsed.loras:
                resolve_managed_lora_path(lora.path, paths)
            if not dry_run:
                ready = _generation_readiness(paths, checkpoint=parsed.checkpoint, dry_run=False)
                if not ready["ready"]:
                    raise ValueError(f"{index + 1}단계: Anima 모델 파일이 준비되지 않았습니다.")
            settings = parsed.face_detailer
        if not dry_run and settings.enabled and missing_detector_paths(paths, settings):
            raise ValueError(f"{index + 1}단계: 디테일러 검출 / 마스크 모델이 준비되지 않았습니다.")
    return base, workflow, planned


def run_workflow(payload, *, paths, renderer, default_dry_run, progress_store=None, cancelled=None):
    from anima_app.server import handle_generate, _boolean_value, _progress_id_from_payload
    cancelled = cancelled or (lambda: False)
    progress_id = _progress_id_from_payload(payload)
    try:
        dry_run = _boolean_value(payload.get("dry_run", default_dry_run), "dry_run")
        base, workflow, planned = preflight(payload, paths, dry_run=dry_run)
    except NovelAIError as exc:
        return exc.status, exc.payload()
    except (ValueError, TypeError, AttributeError, FileNotFoundError, OverflowError) as exc:
        return 400, {"error_code": "workflow_invalid_request", "error": str(exc)}
    journal_path = paths.output_root / "workflows" / f"{uuid.uuid4().hex}.json"
    journal_path.parent.mkdir(parents=True, exist_ok=True)
    run = {"id": journal_path.stem, "status": "running", "created_at": time.time(), "steps": []}
    for index, request in enumerate(planned):
        engine = "NovelAI" if request.get("provider") == "novelai" else "Anima"
        action = {"generate": "생성", "detail": "디테일러", "upscale": "업스케일"}.get(request.get("operation", "generate"), "이미지 편집")
        run["steps"].append({"index": index + 1, "label": f"{engine} {action}", "status": "pending"})
    base_saved = {**base, "workflow": workflow}
    last_result, variants, base_resolved = {}, {}, base

    def save():
        _write_json_atomically(journal_path, {"request": base_saved, "run": run})

    def attach(result):
        manifest_path = Path(result["manifest_path"])
        manifest = read_manifest(manifest_path)
        manifest.update(workflow=workflow, workflow_base_request=base_saved, workflow_run=copy.deepcopy(run))
        _write_json_atomically(manifest_path, manifest)

    if progress_store and progress_id:
        progress_store.start(progress_id, payload)
    save()
    for index, request in enumerate(planned):
        entry = run["steps"][index]
        if dry_run and index > 0:
            entry["status"] = "configured"
            continue
        if cancelled():
            run["status"], entry["status"] = "cancelled", "cancelled"
            break
        entry.update(status="running", started_at=time.time())
        save()
        if progress_store and progress_id:
            progress_store.update_summary(progress_id, f"{index + 1}/{len(planned)} · {entry['label']}")
            progress_store.update_stage(progress_id, f"workflow_{index + 1}", "active", label=entry["label"])
        try:
            if index > 0:
                source = Path(last_result["output_path"]).resolve()
                source.relative_to(paths.image_root.resolve())
                with Image.open(source) as image:
                    size = image.size
                # The upload store preserves the completed output and deduplicates input copies.
                imported = store_reference_upload(source, source.name, "image/png", paths)
                request = stage_request(workflow["steps"][index - 1], base_resolved, size, imported["relative_path"])
                entry.update(input_manifest=last_result["manifest_name"], input_sha256=hashlib.sha256(source.read_bytes()).hexdigest())
                save()
            request = {**request, "dry_run": dry_run}
            status, result = handle_generate(request, paths=paths, renderer=renderer, default_dry_run=dry_run,
                                             enforce_managed_inputs=True, cancelled=cancelled)
        except Exception as exc:
            is_cancel = cancelled()
            status, result = (499 if is_cancel else 500), {"error": "생성이 취소되었습니다." if is_cancel else str(exc)}
        if status >= 400:
            entry.update(status="cancelled" if status == 499 else "failed", error=result, http_status=int(status))
            run["status"] = entry["status"]
            break
        entry.update(status="configured" if dry_run else "completed", manifest_name=result["manifest_name"],
                     stages=result.get("stages", {}), warnings=result.get("warnings", []),
                     output_path=result.get("output_path"), output_url=result.get("output_url"), completed_at=time.time())
        if result.get("output_path"):
            entry["output_sha256"] = hashlib.sha256(Path(result["output_path"]).read_bytes()).hexdigest()
            variants[f"workflow_{index + 1}"] = {"label": f"{index + 1} · {entry['label']}",
                                                 "output_path": result["output_path"], "output_url": result["output_url"]}
        last_result = result
        if index == 0:
            manifest = read_manifest(Path(result["manifest_path"]))
            resolved = manifest.get("wildcards", {})
            base_resolved = {**base, "prompt": resolved.get("prompt", base["prompt"]),
                             "negative_prompt": resolved.get("negative_prompt", base.get("negative_prompt", ""))}
        if result.get("stop_scheduling") or result.get("cancellation_requested"):
            entry["status"] = "partial"
            run["status"] = "cancelled" if result.get("cancellation_requested") else "failed"
        attach(result)
        save()
        if progress_store and progress_id:
            progress_store.update_stage(progress_id, f"workflow_{index + 1}", entry["status"])
        if run["status"] != "running":
            break
    if run["status"] == "running":
        run["status"] = "dry_run" if dry_run else "completed"
    for entry in run["steps"]:
        if entry["status"] == "pending":
            entry["status"] = "skipped"
    run["completed_at"] = time.time()
    save()
    succeeded = run["status"] in {"completed", "dry_run"}
    if last_result:
        attach(last_result)
        response = {**last_result, "workflow_run": run, "variants": {**last_result.get("variants", {}), **variants},
                    "stop_scheduling": not succeeded}
        if not succeeded:
            failure = next((s.get("error", {}).get("error") for s in run["steps"] if s.get("error")), run["status"])
            response.update(status="partial", warnings=[*response.get("warnings", []), f"작업 순서가 중단되었습니다: {failure}. 완료된 결과는 보존했습니다."])
        # Make intermediate variants accessible after reload as well as in this response.
        manifest_path = Path(last_result["manifest_path"])
        manifest = read_manifest(manifest_path)
        manifest["variants"] = {**manifest.get("variants", {}), **variants}
        _write_json_atomically(manifest_path, manifest)
        code = 200
    else:
        failed = next((s["error"] for s in run["steps"] if "error" in s), {"error": "생성이 취소되었습니다."})
        response = {**failed, "workflow_run": run, "stop_scheduling": True}
        code = next((s["http_status"] for s in run["steps"] if "http_status" in s),
                    499 if run["status"] == "cancelled" else 500)
    if progress_store and progress_id:
        if succeeded:
            progress_store.complete(progress_id, response)
        elif run["status"] == "cancelled":
            progress_store.cancel(progress_id)
        else:
            progress_store.fail(progress_id, "작업 순서가 중단되었습니다. 완료된 결과는 보존했습니다.")
    return code, response

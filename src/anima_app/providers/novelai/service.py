from __future__ import annotations

import hashlib
import io
import json
import time
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path

from PIL.PngImagePlugin import PngInfo

from anima_app.config import AppPaths
from anima_app.manifests import _write_json_atomically
from anima_app.output_names import _with_collision_suffix, allocate_manifest_path, allocate_output_path
from anima_app.providers.novelai.auth import get_token, current_account
from anima_app.providers.novelai.client import SubscriptionTransport, Transport, post_json
from anima_app.providers.novelai.eligibility import validate_opus_free_payload
from anima_app.providers.novelai.images import first_png_from_zip, verify_png_bytes, with_character_slots, write_verified_png
from anima_app.providers.novelai.inpaint import composite_png, encode_png, read_img2img_input, read_inputs
from anima_app.providers.novelai.models import GENERATE_IMAGE_URL
from anima_app.providers.novelai.medium import MEDIUM_NOTICE, is_medium
from anima_app.providers.novelai.payloads import apply_opus_free_limits
from anima_app.providers.novelai.payloads import build_payload
from anima_app.providers.novelai.requests import NovelAIRequest, NovelAIResult, replace_characters
from anima_app.providers.novelai.references import reference_parameters, validate_managed_references
from anima_app.providers.novelai.errors import diagnosed, mark_stage, failure
from anima_app.providers.novelai import detailer
from anima_app.requests import T2IRequest


@diagnosed("validation")
def generate(
    request: NovelAIRequest,
    *,
    paths: AppPaths,
    dry_run: bool = False,
    transport: Transport | None = None,
    subscription_transport: SubscriptionTransport | None = None,
    sleep: Callable[[float], None] = time.sleep,
    wildcards: dict[str, object] | None = None,
    cancelled: Callable[[], bool] = lambda: False,
    tagger_progress: Callable[[dict], None] | None = None,
) -> NovelAIResult:
    effective, payload = build_payload(request)
    output_path = None
    status = "dry_run"
    audit: dict[str, object] = {"retry_count": 0, "png_sha256": None,
                              "opus_preflight": {"status": "not_checked" if dry_run else "disabled"}}
    source = mask = None
    variants: dict[str, str] = {}
    validate_managed_references(effective, paths)
    if request.operation in {"infill", "focused_infill"}:
        source, mask, inputs = read_inputs(effective, paths)
        audit["inpaint"] = inputs
    elif request.operation in {"img2img", "detail"}:
        source, inputs = read_img2img_input(effective, paths)
        audit["img2img"] = inputs
    if not dry_run:
        if effective.limit_opus_free and request.operation not in {"focused_infill", "detail"}:
            validate_opus_free_payload(payload)
        mark_stage("detailer_prepare")
        tagger = detailer.preflight(effective, paths, cancelled=cancelled, progress=tagger_progress)
        preview = request.operation in {"detail", "focused_infill"} and effective.detailer["preview_only"]
        token = "" if preview else get_token()
        mark_stage("reference_prepare")
        reference_params, reference_audit = ({}, []) if preview else reference_parameters(
            effective, paths, token=token, transport=transport, sleep=sleep, cancelled=cancelled)
        payload["parameters"].update(reference_params)
        audit["references"] = reference_audit
        if source is not None and request.operation not in {"focused_infill", "detail"}:
            payload["parameters"]["image"] = encode_png(source)
            if mask is not None:
                payload["parameters"]["mask"] = encode_png(mask)
        if request.operation in {"focused_infill", "detail"}:
            try:
                edited, total_mask, report = detailer.repaint(
                    source, effective, paths, token=token, reference_params=reference_params, transport=transport,
                    subscription_transport=subscription_transport, sleep=sleep, cancelled=cancelled,
                    manual_mask=mask, audit=audit, tagger=tagger)
            except Exception as exc:
                # Native inference can also raise RuntimeError; keep any durable completed crops.
                completed = [item for item in audit.get("detailer", []) if item.get("composite_path")]
                if not completed:
                    raise
                from PIL import Image
                with Image.open(completed[-1]["composite_path"]) as image:
                    edited = image.convert("RGB")
                with Image.open(completed[-1]["mask_path"]) as image:
                    total_mask = image.convert("L")
                report = audit["detailer"]
                audit["detailer_failure"] = failure(exc, stage="detailer")
            png_bytes = _detail_png(edited, effective, report)
            audit["detailer"] = report
        else:
            mark_stage("generation", unknown=True)
            response = post_json(
                GENERATE_IMAGE_URL,
                token=token,
                payload=payload,
                transport=transport,
                sleep=sleep,
                cancelled=cancelled,
                audit=audit,
                limit_opus_free=effective.limit_opus_free,
                subscription_transport=subscription_transport,
            )
            mark_stage("response", unknown=True)
            png_bytes = first_png_from_zip(response)
        verify_png_bytes(png_bytes, expected_size=(effective.width, effective.height))
        audit["png_sha256"] = hashlib.sha256(png_bytes).hexdigest()
        mark_stage("output_save")
        paths.image_root.mkdir(parents=True, exist_ok=True)
        output_path = allocate_output_path(_naming_request(effective), paths=paths, status="generated",
                                          unique_suffix=(current_account() or {}).get("job_id", ""))
        if mask is not None and request.operation == "infill":
            raw_path = _with_collision_suffix(output_path.with_name(output_path.stem + "-remote-inpaint.png"))
            write_verified_png(raw_path, png_bytes)
            variants["remote_inpaint"] = str(raw_path)
            audit["remote_png_sha256"] = audit["png_sha256"]
            png_bytes = composite_png(png_bytes, source, mask, effective)
            audit["png_sha256"] = hashlib.sha256(png_bytes).hexdigest()
        write_verified_png(output_path, png_bytes)
        if effective.detailer["enabled"] and request.operation not in {"focused_infill", "detail"}:
            # Base result is durable before any extra operation, cancellation or uncertain remote outcome.
            from PIL import Image
            with Image.open(io.BytesIO(png_bytes)) as base:
                try:
                    edited, total_mask, report = detailer.repaint(
                        base.convert("RGB"), effective, paths, token=token, reference_params=reference_params,
                        transport=transport, subscription_transport=subscription_transport, sleep=sleep,
                        cancelled=cancelled, audit=audit, tagger=tagger)
                    detail_path = _with_collision_suffix(output_path.with_name(output_path.stem + "-detail.png"))
                    write_verified_png(detail_path, _detail_png(edited, effective, report))
                    variants["base"] = str(output_path)
                    variants["detailer"] = str(detail_path)
                    output_path = detail_path
                    audit["detailer"] = report
                    audit["png_sha256"] = hashlib.sha256(detail_path.read_bytes()).hexdigest()
                except Exception as exc:
                    # Never discard the successful base or retry a whole partially completed pipeline.
                    audit["detailer_failure"] = failure(exc, stage="detailer")
                    completed = [item for item in audit.get("detailer", []) if item.get("composite_path")]
                    if completed:
                        variants["base"] = str(output_path)
                        output_path = Path(completed[-1]["composite_path"])
                        variants["detailer_partial"] = str(output_path)
                        audit["png_sha256"] = hashlib.sha256(output_path.read_bytes()).hexdigest()
        if request.operation in {"detail", "focused_infill"}:
            mask_path = _with_collision_suffix(output_path.with_name(output_path.stem + "-mask.png"))
            total_mask.save(mask_path)
            variants["detailer_mask"] = str(mask_path)
        if request.character_slots:
            restored = request
            if wildcards and "characters" in wildcards:
                restored = replace_characters(request, [item["original"] for item in wildcards["characters"]])
            saved_path = _with_collision_suffix(output_path.with_name(output_path.stem + "-settings.png"))
            saved_png = with_character_slots(output_path.read_bytes(), restored.character_slots, restored.character_count)
            write_verified_png(saved_path, saved_png)
            variants["without_character_slots"] = str(output_path)
            output_path = saved_path
            audit["png_sha256"] = hashlib.sha256(saved_png).hexdigest()
        status = "previewed" if preview else "generated"
    cancellation_requested = cancelled()
    mark_stage("metadata_save")
    manifest_path = _write_manifest(
        effective,
        payload=payload,
        paths=paths,
        status=status,
        output_path=output_path,
        wildcards=wildcards,
        requested=request,
        audit=audit,
        cancellation_requested=cancellation_requested,
        variants=variants,
    )
    return NovelAIResult(
        status=status,
        manifest_path=manifest_path,
        output_path=output_path,
        request=effective,
        cancellation_requested=cancellation_requested,
    )


def _write_manifest(
    request: NovelAIRequest,
    *,
    payload: dict[str, object],
    paths: AppPaths,
    status: str,
    output_path: Path | None,
    wildcards: dict[str, object] | None,
    requested: NovelAIRequest,
    audit: dict[str, object],
    cancellation_requested: bool,
    variants: dict[str, str],
) -> Path:
    paths.manifest_root.mkdir(parents=True, exist_ok=True)
    manifest_path = allocate_manifest_path(
        _naming_request(request),
        paths=paths,
        status=status,
        output_path=output_path,
        unique_suffix=(current_account() or {}).get("job_id", ""),
    )
    warnings = []
    limits_applied = (
        requested.limit_opus_free and requested.operation == "generate"
        and (requested.width, requested.height, requested.steps)
        != apply_opus_free_limits(requested.width, requested.height, requested.steps)
    )
    if limits_applied:
        warnings.append(f"Opus 요청 한도 적용: {requested.width}x{requested.height}, {requested.steps} 스텝 → {request.width}x{request.height}, {request.steps} 스텝")
    if is_medium(request.model):
        warnings.append(MEDIUM_NOTICE)
    if cancellation_requested:
        warnings.append("정지 요청 뒤 도착한 NovelAI 결과를 보존했습니다. 다음 작업은 예약하지 않습니다.")
    if "detailer_failure" in audit:
        warnings.append("NAI 디테일러가 완료되지 않았습니다. 원본과 완료된 보정 결과를 보존했습니다. 자동 재전송하지 않습니다.")
    if request.model == "nai-diffusion-5-curated" and request.detailer["enabled"]:
        warnings.append("V5 Curated의 디테일러 인페인트 모델은 V4.5 Curated (nai-diffusion-4-5-curated-inpainting)입니다.")
    if "detailer" in audit:
        regions = audit["detailer"]
        if not regions:
            warnings.append("유효한 검출 영역이 없습니다. 원본을 보존했으며 디테일러 NAI 요청은 보내지 않았습니다.")
        elif not any(row["status"] in {"planned", "edited", "failed", "cancelled", "checkpoint_failed"} for row in regions):
            warnings.append("모든 검출 영역을 건너뛰었습니다. 원본을 보존했으며 디테일러 NAI 요청은 보내지 않았습니다.")
        for row in regions:
            if row.get("tight_crop_retried") or row["status"] in {"skipped", "empty_mask"}:
                retry = "좁은 크롭 재확인 후 · " if row.get("tight_crop_retried") else ""
                warnings.append(f"영역 {row['region']}: {retry}{row.get('explanation', row['reason'])}")
    for label, entry in [("생성", audit), *[(f"영역 {r['region']}", r) for r in audit.get("detailer", [])]]:
        for event in entry.get("rate_limit_events", []):
            if event["retry_scheduled"]:
                warnings.append(f"{label}: HTTP 429로 {event['wait_seconds']:g}초 대기 후 1회 재시도를 예약했습니다. 대기 중 정지는 후속 전송을 막습니다.")
    manifest = {
        **asdict(request),
        "provider": "novelai",
        "checkpoint": request.model,
        "status": status,
        "output_path": str(output_path) if output_path else None,
        "variants": variants,
        "warnings": warnings,
        "cancellation_requested": cancellation_requested,
        "stages": {
            "request": {"status": "completed"},
            "wildcards": {"status": "completed"},
            "text_encode": {"status": "skipped"},
            "vae_decode": {"status": "skipped"},
            "high_res_fix": {"status": "skipped"},
            "face_detailer": {"status": "failed" if "detailer_failure" in audit else "completed" if "detailer" in audit else "skipped"},
            "face_eye_detailer": {"status": "skipped"},
            "hand_detailer": {"status": "skipped"},
            "metadata": {"status": "completed"},
            "base_t2i": {
                "status": "completed" if output_path else "skipped",
                "method": "novelai_api",
                "operation": request.operation,
            },
        },
        "wildcards": wildcards or {"enabled": False, "mode": "random", "selections": []},
        "created_at": time.time(),
        "manifest_path": str(manifest_path),
        "provenance": {
            "app": "anima-app",
            "provider": "novelai",
            "endpoint": GENERATE_IMAGE_URL,
        },
        "novelai": {
            "action": payload["action"],
            "model": payload["model"],
            "params_version": payload["parameters"]["params_version"],
            **audit,
            "requested": requested.to_payload(),
            "effective": request.to_payload(),
            "opus_limits_applied": limits_applied,
        },
    }
    if current_account():
        manifest['barracks'] = current_account()
    _write_json_atomically(manifest_path, manifest)
    return manifest_path


def _detail_png(image, request, report):
    from anima_app.providers.novelai.payloads import _v4_prompt_parameters
    info = PngInfo()
    info.add_text("Software", "Anima APP")
    info.add_itxt("Comment", json.dumps({"model": request.model, "prompt": request.prompt, "uc": request.negative_prompt,
                                         "request_type": {"generate": "PromptGenerateRequest", "img2img": "Img2ImgRequest",
                                                          "infill": "NativeInfillingRequest", "focused_infill": "NativeInfillingRequest"}.get(request.operation),
                                         "strength": request.img2img_strength if request.operation == "img2img" else None,
                                         "noise": request.img2img_noise if request.operation == "img2img" else None,
                                         "width": request.width, "height": request.height, "steps": request.steps, "scale": request.cfg,
                                         "seed": request.seed, "sampler": request.sampler, "noise_schedule": request.scheduler,
                                         "cfg_rescale": request.cfg_rescale, "prefer_brownian": request.prefer_brownian,
                                         "anima_app_composite": True, "anima_app_detailer": request.detailer,
                                         "anima_app_operation": request.operation,
                                         **(_v4_prompt_parameters(request) if request.model.startswith(("nai-diffusion-4", "nai-diffusion-5")) else {})}))
    info.add_itxt("anima_app_detailer_regions", json.dumps(report))
    stream = io.BytesIO()
    image.save(stream, format="PNG", pnginfo=info)
    return stream.getvalue()


def _naming_request(request: NovelAIRequest) -> T2IRequest:
    return T2IRequest(
        prompt=request.prompt,
        negative_prompt=request.negative_prompt,
        width=request.width,
        height=request.height,
        steps=request.steps,
        cfg=request.cfg,
        seed=request.seed,
    )

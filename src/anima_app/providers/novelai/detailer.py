# SPDX-License-Identifier: GPL-3.0-only
"""Standalone region detection and frozen-source sequential NAI focused repaint.

Region ownership, WD matching and 32/8 mask alignment follow RS_NAI's detailer.
Tagger observations select original character text and never become prompt text.
"""
from __future__ import annotations

import io
import hashlib
import math
from dataclasses import asdict, dataclass, replace
from types import SimpleNamespace

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from anima_app.providers.novelai.client import _check_cancelled, post_json
from anima_app.providers.novelai.detailer_matching import Match, match_characters, selected_prompts
from anima_app.providers.novelai.eligibility import FocusedContext, validate_opus_free_payload
from anima_app.providers.novelai.errors import NovelAIError, invalid, diagnosed, mark_stage, failure
from anima_app.providers.novelai.wd_tagger import DEFAULT_MODEL, MODELS, WDTagger
from anima_app.providers.novelai.images import first_png_from_zip, verify_png_bytes, write_verified_png
from anima_app.providers.novelai.inpaint import encode_png
from anima_app.providers.novelai.models import GENERATE_IMAGE_URL, INPAINT_ROUTING, SUPPORTED_INPAINT_MODEL_IDS
from anima_app.providers.novelai.payloads import build_payload
from anima_app.runtime.face_detailer import align_mask_to_grid, expand_box

DEFAULTS = {"enabled": False, "preview_only": False, "mode": "all", "matching": "shared",
            "backend": "sam_b", "concepts": ["face", "eyes"], "threshold": .5, "mask_threshold": .3,
            "crop_factor": 2.0, "padding": 32, "dilation": 0, "strength": .55, "steps": 28,
            "max_regions": 16, "match_min_score": .25, "match_min_margin": .08, "match_crop_factor": 2.0,
            "wd_device": "auto", "wd_batch_size": 4, "wd_model": DEFAULT_MODEL}


def validate_settings(value):
    if not isinstance(value, dict) or value.keys() - DEFAULTS.keys():
        raise invalid("DETAIL_MODE", "Unknown NAI detailer setting")
    result = {**DEFAULTS, **value}
    if not isinstance(result["wd_model"], str) or result["wd_model"] not in MODELS:
        raise invalid("DETAIL_MODE", "Unknown NAI detailer tagger model")
    for key in ("enabled", "preview_only"):
        if type(result[key]) is not bool:
            raise invalid("DETAIL_MODE", "Detailer flags must be boolean")
    for key, options in (("mode", ("first", "all")), ("matching", ("shared", "wd14")), ("backend", ("sam_b", "sam3")), ("wd_device", ("auto", "cpu"))):
        if result[key] not in options:
            raise invalid("DETAIL_MODE", "Unsupported NAI detailer mode")
    concepts = result["concepts"]
    if not isinstance(concepts, (list, tuple)) or not concepts or len(concepts) > 3 or any(not isinstance(x, str) or x not in {"face", "eyes", "hands"} for x in concepts):
        raise invalid("DETAIL_MODE", "Detailer concepts must be face, eyes or hands")
    result["concepts"] = list(dict.fromkeys(concepts))
    for key, maximum in (("threshold", 1), ("mask_threshold", 1), ("strength", 1), ("crop_factor", 8),
                         ("match_min_score", 1), ("match_min_margin", 1), ("match_crop_factor", 8)):
        if type(result[key]) not in (int, float) or not 0 <= result[key] <= maximum:
            raise invalid("DETAIL_MODE", "Detailer numeric setting out of range")
    if result["crop_factor"] < 1 or result["match_crop_factor"] < 1:
        raise invalid("DETAIL_MODE", "Detailer crop factors must be at least 1")
    for key, low, high in (("steps", 1, 50), ("max_regions", 1, 16), ("padding", 0, 256), ("dilation", -64, 128), ("wd_batch_size", 1, 16)):
        if type(result[key]) is not int or not low <= result[key] <= high:
            raise invalid("DETAIL_MODE", "Detailer integer setting out of range")
    return result


@dataclass
class Region:
    box: tuple[float, float, float, float]
    mask: Image.Image
    concept: str = "face"


def detector_asset(paths, names):
    roots = (paths.model_root / "detectors", paths.face_detailer_detector_source, *paths.face_detailer_detector_fallback_sources)
    for root in roots:
        for name in names:
            candidate = root / name
            if candidate.is_file():
                return candidate
    raise FileNotFoundError("Missing NAI detailer asset: " + " / ".join(names))


class Detector:
    def __init__(self, paths, settings):
        self.paths, self.settings = paths, settings

    def preflight(self):
        if self.settings["backend"] == "sam3":
            detector_asset(self.paths, ("sam3.pt",))
            self._sam3_predictor_class()
        else:
            sam_path = detector_asset(self.paths, ("sam_b.pt", "sam_vit_b_01ec64.pth"))
            try:
                from ultralytics import SAM, YOLO
                if not callable(SAM) or not callable(YOLO):
                    raise TypeError("SAM and YOLO must be callable")
                if sam_path.suffix == ".pth":
                    from segment_anything import SamPredictor, sam_model_registry
                    if not callable(SamPredictor) or not callable(sam_model_registry.get("vit_b")):
                        raise TypeError("SAM vit_b adapter is unavailable")
            except (ImportError, AttributeError, TypeError):
                raise NovelAIError(
                    "sam_b_runtime_unavailable",
                    "YOLO + SAM B requires Ultralytics SAM/YOLO and, for .pth weights, "
                    "segment-anything's vit_b predictor. Install the face-detailer dependencies "
                    "in the app's Python environment.",
                    400,
                ) from None
            for concept in self.settings["concepts"]:
                detector_asset(self.paths, self._names(concept))

    @staticmethod
    def _sam3_predictor_class():
        try:
            from ultralytics.models.sam import SAM3SemanticPredictor
            from clip.simple_tokenizer import SimpleTokenizer
            # SAM3 requires the callable tokenizer from Ultralytics' CLIP fork.
            # Check it before base generation, rather than letting model loading
            # attempt an automatic install after a remote request has succeeded.
            if not callable(SimpleTokenizer()):
                raise TypeError("SAM3 tokenizer must be callable")
        except (ImportError, AttributeError, TypeError):
            raise NovelAIError(
                "sam3_runtime_unavailable",
                "SAM3 requires SAM3SemanticPredictor and the callable Ultralytics CLIP tokenizer. "
                "Install the sam3 dependencies in the app's Python environment.",
                400,
            ) from None
        return SAM3SemanticPredictor

    @staticmethod
    def _names(concept):
        return {"face": ("face_yolov8n.pt", "face_yolov8m.pt"), "eyes": ("full_eyes_detect_v1.pt",),
                "hands": ("hand_yolov8n.pt", "hand_yolov8s.pt")}[concept]

    def detect(self, source, cancelled):
        _check_cancelled(cancelled)
        self.preflight()
        if self.settings["backend"] == "sam3":
            predictor = self._sam3_predictor_class()(overrides={"model": str(detector_asset(self.paths, ("sam3.pt",))),
                                                       "task": "segment", "mode": "predict", "conf": self.settings["threshold"],
                                                       "device": "cpu", "verbose": False, "save": False})
            # Ultralytics treats NumPy images as BGR; PIL carries the RGB contract.
            predictor.set_image(source.convert("RGB"))
            regions = []
            for concept in self.settings["concepts"]:
                _check_cancelled(cancelled)
                for result in predictor(text=[{"face": "face", "eyes": "eye", "hands": "hand"}[concept]]):
                    _check_cancelled(cancelled)
                    if result.masks is not None:
                        for tensor in result.masks.data:
                            _check_cancelled(cancelled)
                            mask = Image.fromarray((tensor.cpu().numpy() * 255).astype(np.uint8)).resize(source.size, Image.Resampling.NEAREST)
                            box = mask.getbbox()
                            if box:
                                regions.append(Region(box, mask, concept))
            return group_regions(regions)
        from ultralytics import SAM, YOLO
        sam_path = detector_asset(self.paths, ("sam_b.pt", "sam_vit_b_01ec64.pth"))
        predictor = None
        if sam_path.suffix == ".pth":
            from segment_anything import SamPredictor, sam_model_registry
            predictor = SamPredictor(sam_model_registry["vit_b"](checkpoint=str(sam_path)).to("cpu"))
            predictor.set_image(np.asarray(source.convert("RGB")))
        else:
            sam = SAM(str(sam_path))
        regions = []
        for concept in self.settings["concepts"]:
            _check_cancelled(cancelled)
            model = YOLO(str(detector_asset(self.paths, self._names(concept))))
            for result in model(source, conf=self.settings["threshold"], verbose=False, device="cpu"):
                for box in result.boxes.xyxy.cpu().numpy():
                    _check_cancelled(cancelled)
                    mask = Image.new("L", source.size)
                    if predictor is not None:
                        masks, _, _ = predictor.predict(box=np.asarray(box), multimask_output=False)
                        _check_cancelled(cancelled)
                        mask = Image.fromarray((masks[0] * 255).astype(np.uint8))
                    else:
                        # Ultralytics interprets NumPy images as BGR, unlike
                        # segment-anything's RGB arrays above.
                        results = sam(source.convert("RGB"), bboxes=[list(box)], verbose=False, device="cpu")
                        _check_cancelled(cancelled)
                        if results and results[0].masks is not None:
                            for tensor in results[0].masks.data:
                                current = Image.fromarray((tensor.cpu().numpy() * 255).astype(np.uint8)).resize(source.size, Image.Resampling.NEAREST)
                                mask = Image.fromarray(np.maximum(np.array(mask), np.array(current)))
                        else:
                            ImageDraw.Draw(mask).rectangle(tuple(box), fill=255)
                    regions.append(Region(tuple(float(v) for v in box), mask, concept))
        return group_regions(regions)


def center(box):
    return ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)


def group_regions(regions):
    # Eye detections belong to the containing/nearest face rather than new repaint requests.
    faces = [r for r in regions if r.concept == "face"]
    if not faces:
        return regions
    for eye in [r for r in regions if r.concept == "eyes"]:
        x, y = center(eye.box)
        owner = min(faces, key=lambda r: (not (r.box[0] <= x <= r.box[2] and r.box[1] <= y <= r.box[3]),
                                         (center(r.box)[0] - x) ** 2 + (center(r.box)[1] - y) ** 2))
        owner.mask = Image.fromarray(np.maximum(np.array(owner.mask), np.array(eye.mask)))
    return [r for r in regions if r.concept != "eyes"]


def preflight(request, paths, *, cancelled=lambda: False, progress=None):
    settings = request.detailer
    if not settings["enabled"] or request.operation == "focused_infill":
        return
    Detector(paths, settings).preflight()
    if settings["matching"] == "wd14":
        tagger = WDTagger(paths.wd_tagger_root, device=settings["wd_device"], batch_size=settings["wd_batch_size"],
                          model_name=settings["wd_model"])
        tagger.cancelled, tagger.progress = cancelled, progress
        return tagger.prepare()


def _crop(source, box, factor):
    return source.crop(expand_box(box, image_size=source.size, crop_scale=factor, padding=0))


def plan(source, regions, request, tagger=None, cancelled=lambda: False):
    settings = request.detailer
    if settings["mode"] == "all":
        regions = sorted(regions, key=lambda r: center(r.box))
    validated = []
    for r in regions:
        if len(r.box) != 4 or any(not math.isfinite(float(v)) for v in r.box) or r.mask.size != source.size:
            continue
        x0, y0, x1, y1 = r.box
        if not 0 <= x0 < x1 <= source.width or not 0 <= y0 < y1 <= source.height:
            continue
        if r.mask.getbbox():
            validated.append(r)
    regions = validated
    count = min(len(regions), 1 if settings["mode"] == "first" else settings["max_regions"])
    characters = [SimpleNamespace(prompt=c["prompt"], uc=c["negative_prompt"]) for c in request.characters]
    matches = [Match(0 if len(characters) == 1 else None, 1, 1, "shared") for _ in regions]
    retried = set()
    if settings["matching"] == "wd14" and count:
        if tagger is None:
            raise invalid("MATCHING_INPUT", "WD matching requires a loaded tagger")
        tagger.cancelled = cancelled
        scores = tagger.score([_crop(source, r.box, settings["match_crop_factor"]) for r in regions[:count]])
        if len(scores) != count:
            raise invalid("MATCHING_INPUT", "WD returned the wrong number of regions")
        for i, scores_i in enumerate(scores):
            matches[i] = match_characters(scores_i, characters, settings["match_min_score"], settings["match_min_margin"])
        uncertain = [i for i in range(count) if matches[i].character_index is None]
        if uncertain and settings["match_crop_factor"] > 1.25:
            retried.update(uncertain)
            scores = tagger.score([_crop(source, regions[i].box, 1.25) for i in uncertain])
            if len(scores) != len(uncertain):
                raise invalid("MATCHING_INPUT", "WD returned the wrong number of retry regions")
            for i, scores_i in zip(uncertain, scores):
                match = match_characters(scores_i, characters, settings["match_min_score"], settings["match_min_margin"])
                if match.character_index is not None:
                    matches[i] = replace(match, reason="tag_match_tight")
                else:
                    matches[i] = match
    report = []
    for i, (region, match) in enumerate(zip(regions, matches)):
        crop = expand_box(region.box, image_size=source.size, crop_scale=settings["crop_factor"], padding=settings["padding"])
        eligible = i < count and (settings["matching"] == "shared" or match.character_index is not None)
        if i >= count:
            diagnostic = "region_limit"
            explanation = "첫 영역 모드 또는 최대 영역 수 제한으로 건너뛰었습니다."
        elif settings["matching"] == "wd14" and match.character_index is None:
            if match.score < settings["match_min_score"]:
                diagnostic = "score_below_minimum"
                explanation = f"점수 {match.score:.3f} < 최소 {settings['match_min_score']:.3f}: 캐릭터 근거가 부족합니다."
            else:
                diagnostic = "margin_below_minimum"
                explanation = f"점수 차이 {match.margin:.3f} < 최소 {settings['match_min_margin']:.3f}: 후보가 비슷합니다."
        else:
            diagnostic = "shared_prompt" if settings["matching"] == "shared" else "character_selected"
            explanation = "공통 프롬프트를 사용합니다." if diagnostic == "shared_prompt" else "선택된 원래 캐릭터 프롬프트를 사용합니다."
        report.append({"region": i + 1, "bbox": list(region.box), "crop": list(crop), "concept": region.concept,
                       "character": None if match.character_index is None else match.character_index + 1,
                       "character_slot": None if match.character_index is None else request.active_character_slots[match.character_index],
                       "score": match.score, "margin": match.margin, "reason": match.reason,
                       "status": "planned" if eligible else "skipped", "diagnostic": diagnostic,
                       "explanation": explanation, "tight_crop_retried": i in retried})
        if settings["matching"] == "wd14":
            repo, revision = MODELS[settings["wd_model"]]
            report[-1]["tagger"] = {"model_name": settings["wd_model"], "repo": repo, "revision": revision}
    return regions, matches, characters, report


def _owned(x, y, centers, index):
    cx, cy = centers[index]
    distance = (x - cx) ** 2 + (y - cy) ** 2
    owned = np.ones(np.broadcast_shapes(x.shape, y.shape), dtype=bool)
    for other, (ox, oy) in enumerate(centers):
        if other != index:
            competing = (x - ox) ** 2 + (y - oy) ** 2
            owned &= distance < competing if other < index else distance <= competing
    return owned


@diagnosed("detailer_prepare", "detailer_failed")
def repaint(source, request, paths, *, token, reference_params=None, transport=None, subscription_transport=None,
            sleep, cancelled=lambda: False, detector=None, tagger=None, manual_mask=None, audit=None):
    settings = request.detailer
    if manual_mask is not None:
        box = manual_mask.getbbox()
        regions = [Region(box, manual_mask, "manual")] if box else []
    else:
        regions = (detector or Detector(paths, settings)).detect(source, cancelled)
    if tagger is None and settings["matching"] == "wd14":
        tagger = WDTagger(paths.wd_tagger_root, device=settings["wd_device"], batch_size=settings["wd_batch_size"],
                          model_name=settings["wd_model"])
    regions, matches, characters, report = plan(source, regions, request, tagger, cancelled)
    if audit is not None:
        audit["detailer"] = report
    out, total_mask = source.copy(), Image.new("L", source.size)
    if settings["preview_only"]:
        for item in report:
            draw = ImageDraw.Draw(out)
            color = "lime" if item["status"] == "planned" else "orange"
            draw.rectangle(item["bbox"], outline=color, width=2)
            draw.text(tuple(item["bbox"][:2]),
                      f"{item['region']} -> {item['character_slot'] or '?'} {item['status']} "
                      f"score={item['score']:.2f} margin={item['margin']:.2f}", fill=color)
        return out, total_mask, report
    model = request.model if request.model in SUPPORTED_INPAINT_MODEL_IDS else INPAINT_ROUTING.get(request.model)
    if not model:
        raise invalid("MODEL", "No supported NAI inpainting model for detailer")
    prepared = []
    centers = [center(r.box) for r in regions]
    for i, item in enumerate(report):
        if item["status"] != "planned":
            continue
        crop_box = tuple(item["crop"])
        if request.limit_opus_free and crop_box == (0, 0, *source.size):
            raise invalid("FOCUSED_CROP", "Opus focused inpainting requires a crop smaller than the source")
        crop = source.crop(crop_box)
        cw, ch = crop.size
        scale = 1024 / max(cw, ch)
        nw, nh = max(64, round(cw * scale) // 64 * 64), max(64, round(ch * scale) // 64 * 64)
        mask = regions[i].mask.crop(crop_box).convert("L").resize((nw, nh), Image.Resampling.NEAREST)
        dilation = settings["dilation"]
        if dilation:
            mask = mask.filter(ImageFilter.MaxFilter(2 * dilation + 1) if dilation > 0 else ImageFilter.MinFilter(2 * abs(dilation) + 1))
        aligned = align_mask_to_grid(np.array(mask), threshold=settings["mask_threshold"])
        x0, y0, x1, y1 = crop_box
        gy, gx = np.ogrid[:nh // 8, :nw // 8]
        cells = _owned(x0 + (gx + .5) * 8 * cw / nw, y0 + (gy + .5) * 8 * ch / nh, centers, i)
        aligned = np.where(np.repeat(np.repeat(cells, 8, axis=0), 8, axis=1), aligned, 0).astype(np.uint8)
        request_mask = Image.fromarray(aligned)
        local_mask = request_mask.resize((cw, ch), Image.Resampling.NEAREST)
        yy, xx = np.ogrid[y0:y1, x0:x1]
        local_mask = Image.fromarray(np.where(_owned(xx, yy, centers, i), np.array(local_mask), 0).astype(np.uint8))
        if manual_mask is not None:
            local_mask = Image.fromarray(np.minimum(np.array(local_mask), np.array(manual_mask.crop(crop_box).convert("L"))))
        if not request_mask.getbbox() or not local_mask.getbbox():
            item.update(status="empty_mask", diagnostic="empty_mask",
                        explanation="마스크 정렬·침식·영역 분리 후 수정할 픽셀이 없어 전송하지 않았습니다.")
            continue
        prompt, negative = selected_prompts(request.prompt, request.negative_prompt, characters, matches[i])
        from anima_app.providers.novelai.requests import NovelAIRequest
        # Public infill remains blocked in strict mode. Only this internally planned crop gets a context.
        crop_request = NovelAIRequest(**{**asdict(request), "model": model, "operation": "infill", "limit_opus_free": False,
                                         "width": nw, "height": nh, "steps": min(settings["steps"], 28) if request.limit_opus_free else settings["steps"],
                                         "seed": (request.seed + i) % 2**32, "prompt": prompt, "negative_prompt": negative,
                                         "input_image": "internal-crop", "mask_image": "internal-mask", "characters": (),
                                         "character_slots": None, "character_count": None,
                                         "detailer": {"enabled": False},
                                         "inpaint_strength": settings["strength"] if model.startswith(("nai-diffusion-4", "nai-diffusion-5")) else 1})
        _, payload = build_payload(crop_request)
        payload["parameters"].update(image=encode_png(crop.resize((nw, nh), Image.Resampling.LANCZOS)),
                                     mask=encode_png(request_mask), inpaintImg2ImgStrength=settings["strength"], noise=0,
                                     **(reference_params or {}))
        context = FocusedContext(source.size, crop_box) if request.limit_opus_free else None
        if context:
            validate_opus_free_payload(payload, focused_context=context)
        prepared.append((item, crop_box, payload, local_mask, context))
    # Validate all crop plans before any remote request; partial failures keep every completed crop on disk.
    if audit is not None:
        audit["detailer"] = report
    for item, crop_box, payload, local_mask, context in prepared:
        params = payload["parameters"]
        item.update(transmitted_size=[params["width"], params["height"]],
                    transmitted_model=payload["model"], transmitted_steps=params["steps"], seed=params["seed"])
        entry_audit = {}
        try:
            _check_cancelled(cancelled)
            mark_stage("detailer", unknown=True)
            raw = post_json(GENERATE_IMAGE_URL, token=token, payload=payload, transport=transport,
                            subscription_transport=subscription_transport, sleep=sleep, cancelled=cancelled,
                            limit_opus_free=request.limit_opus_free, focused_context=context, audit=entry_audit, stage="detailer")
            png = first_png_from_zip(raw)
            verify_png_bytes(png, expected_size=(params["width"], params["height"]))
        except Exception as exc:
            code = exc.code if isinstance(exc, NovelAIError) else "detailer_failed"
            item.update(status="cancelled" if code == "generation_cancelled" else "failed",
                        failure=failure(exc, stage="detailer", unknown=True),
                        **entry_audit)
            raise
        mark_stage("detailer_save")
        crop_size = (crop_box[2] - crop_box[0], crop_box[3] - crop_box[1])
        paths.image_root.mkdir(parents=True, exist_ok=True)
        import uuid
        remote_path = paths.image_root / f"nai-detail-{uuid.uuid4().hex}.png"
        write_verified_png(remote_path, png)
        with Image.open(io.BytesIO(png)) as image:
            out.paste(image.convert("RGB").resize(crop_size, Image.Resampling.LANCZOS), crop_box, local_mask)
        current = np.array(total_mask)
        x0, y0, x1, y1 = crop_box
        current[y0:y1, x0:x1] = np.maximum(current[y0:y1, x0:x1], np.array(local_mask))
        total_mask = Image.fromarray(current)
        item.update(status="checkpoint_failed", remote_path=str(remote_path),
                    remote_sha256=hashlib.sha256(png).hexdigest(),
                    prompt=payload["input"], negative_prompt=params["negative_prompt"], **entry_audit)
        # Publish a recoverable checkpoint only after BOTH files are durable. A later
        # mask/save failure must never hide an earlier complete composite/mask pair.
        checkpoint = remote_path.with_name(remote_path.stem + "-composite.png")
        mask_checkpoint = remote_path.with_name(remote_path.stem + "-mask.png")
        from anima_app.providers.novelai.service import _detail_png
        complete_item = {**item, "status": "edited", "composite_path": str(checkpoint), "mask_path": str(mask_checkpoint)}
        checkpoint_report = [complete_item if row is item else row for row in report]
        try:
            mask_bytes = io.BytesIO()
            total_mask.save(mask_bytes, format="PNG")
            write_verified_png(mask_checkpoint, mask_bytes.getvalue())
            write_verified_png(checkpoint, _detail_png(out, request, checkpoint_report))
        except OSError as exc:
            from anima_app.providers.novelai.errors import explain
            error = explain(exc, stage="detailer_save", fallback="nai_checkpoint_failed",
                            message="보정 응답은 저장했지만 합성 결과 저장에 실패했습니다. 자동 재전송하지 않습니다.")
            item["failure"] = failure(error, stage="detailer_save")
            raise error from None
        item.update(complete_item)
    return out, total_mask, report

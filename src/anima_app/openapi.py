from __future__ import annotations

from typing import Any

from anima_app.defaults import (
    DEFAULT_T2I_CFG,
    DEFAULT_T2I_HEIGHT,
    DEFAULT_T2I_SAMPLER,
    DEFAULT_T2I_SCHEDULER,
    DEFAULT_T2I_STEPS,
    DEFAULT_T2I_WIDTH,
)
from anima_app.requests import (
    CFG_PP_SAMPLERS,
    FACE_DETAILER_MASK_BACKENDS,
    MEMORY_PROFILES,
    FaceDetailerSettings,
    I2ISettings,
    MAX_CFG,
    MAX_FACE_CROP_SCALE,
    MAX_FACE_FEATHER,
    MAX_FACE_PADDING,
    MAX_GENERATION_DIMENSION,
    MAX_LORA_COUNT,
    MAX_LORA_STRENGTH,
    MAX_PROMPT_CHARACTERS,
    MAX_SAMPLING_STEPS,
    MAX_SEED,
    MAX_TILE_SIZE,
    MAX_UPSCALE_SCALE,
    MIN_TILE_SIZE,
    UpscaleSettings,
    VaeDecodeSettings,
)
from anima_app.wildcards import WILDCARD_MODES
from anima_app.providers.novelai.models import MODEL_IDS, SAMPLERS, SCHEDULERS, SUPPORTED_INPAINT_MODEL_IDS
from anima_app.providers.novelai.requests import MAX_NAI_SEED
from anima_app.providers.novelai.wd_tagger import DEFAULT_MODEL, MODELS as TAGGER_MODELS


def _schema_ref(name: str) -> dict[str, str]:
    return {"$ref": f"#/components/schemas/{name}"}


def _json_response(
    description: str,
    schema: dict[str, Any],
    *,
    example: dict[str, Any] | None = None,
) -> dict[str, Any]:
    media_type: dict[str, Any] = {"schema": schema}
    if example is not None:
        media_type["example"] = example
    return {"description": description, "content": {"application/json": media_type}}


def _path_parameter(name: str, description: str) -> dict[str, Any]:
    return {
        "name": name,
        "in": "path",
        "required": True,
        "description": description,
        "schema": {"type": "string", "minLength": 1},
    }


def build_openapi_document(
    *,
    app_version: str,
    max_queue_jobs: int,
    max_queue_delay_seconds: int,
    default_dry_run: bool,
) -> dict[str, Any]:
    """Return the dependency-free OpenAPI contract for local agent clients."""

    i2i = I2ISettings()
    upscale = UpscaleSettings()
    face_detailer = FaceDetailerSettings()
    vae = VaeDecodeSettings()
    error_response = _json_response("Request failed", _schema_ref("Error"))
    models_not_ready_response = _json_response(
        "Required local models are missing or invalid",
        _schema_ref("Error"),
        example={
            "error_code": "models_not_ready",
            "error": "필수 모델 파일이 없거나 손상되었습니다.",
            "missing_files": ["diffusion_models/example.safetensors"],
            "invalid_files": [],
        },
    )
    queue_full_response = _json_response(
        "The active queue limit would be exceeded",
        _schema_ref("Error"),
        example={
            "error_code": "queue_full",
            "error": f"active queue cannot exceed {max_queue_jobs} jobs",
            "active_count": max_queue_jobs,
            "requested_count": 1,
            "max_active_jobs": max_queue_jobs,
        },
    )
    generic_response = _json_response("Current server state", _schema_ref("GenericObject"))

    schemas: dict[str, Any] = {
        "GenericObject": {"type": "object", "additionalProperties": True},
        "Error": {
            "type": "object",
            "required": ["error"],
            "properties": {
                "error_code": {"type": "string"},
                "error": {"type": "string"},
                "provider": {"type": "string", "enum": ["local", "novelai"]},
                "remote_outcome_unknown": {"type": "boolean"},
                "error_detail": {"type": "object", "description": "NovelAI cause code, execution stage, optional upstream HTTP status, sanitized details and en/ko/ja [cause, next action]. Display language never changes the generation request.",
                                 "properties": {"code": {"type": "string"}, "stage": {"type": "string"},
                                                "http_status": {"type": ["integer", "null"]},
                                                "exception_type": {"type": "string"}, "details": {"type": "string"},
                                                "messages": {"type": "object"}}},
                "missing_files": {"type": "array", "items": {"type": "string"}},
                "invalid_files": {"type": "array", "items": {"type": "string"}},
            },
            "additionalProperties": True,
        },
        "LoraConfig": {
            "type": "object",
            "required": ["path"],
            "properties": {
                "path": {
                    "type": "string",
                    "minLength": 1,
                    "pattern": "\\S",
                    "description": "Relative path below the local models/loras directory.",
                },
                "model_strength": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": MAX_LORA_STRENGTH,
                    "default": 1.0,
                },
                "clip_strength": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": MAX_LORA_STRENGTH,
                    "default": 1.0,
                },
            },
            "additionalProperties": False,
        },
        "I2ISettings": {
            "type": "object",
            "required": ["enabled"],
            "description": "Canonical agent requests explicitly state whether image-to-image is enabled.",
            "properties": {
                "enabled": {"type": "boolean", "default": i2i.enabled},
                "image_path": {
                    "type": "string",
                    "default": i2i.image_path,
                    "description": "Managed path below inputs/references or outputs/images.",
                },
                "denoise": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 1,
                    "default": i2i.denoise,
                },
            },
            "allOf": [
                {
                    "if": {"properties": {"enabled": {"const": True}}, "required": ["enabled"]},
                    "then": {
                        "required": ["image_path"],
                        "properties": {
                            "image_path": {"type": "string", "minLength": 1, "pattern": "\\S"}
                        },
                    },
                }
            ],
            "additionalProperties": False,
        },
        "UpscaleSettings": {
            "type": "object",
            "properties": {
                "enabled": {"type": "boolean", "default": upscale.enabled},
                "scale": {
                    "type": "number",
                    "exclusiveMinimum": 0,
                    "maximum": MAX_UPSCALE_SCALE,
                    "default": upscale.scale,
                },
                "steps": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": MAX_SAMPLING_STEPS,
                    "default": upscale.steps,
                },
                "denoise": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 1,
                    "default": upscale.denoise,
                },
                "method": {"type": "string", "default": upscale.method},
                "tiled": {"type": "boolean", "default": upscale.tiled},
                "tile_size": {
                    "type": "integer",
                    "minimum": MIN_TILE_SIZE,
                    "maximum": MAX_TILE_SIZE,
                    "default": upscale.tile_size,
                },
                "overlap": {"type": "integer", "minimum": 0, "default": upscale.overlap},
            },
            "additionalProperties": False,
        },
        "FaceDetailerSettings": {
            "type": "object",
            "properties": {
                "enabled": {"type": "boolean", "default": face_detailer.enabled},
                "detector": {"type": "string", "default": face_detailer.detector},
                "mask_backend": {
                    "type": "string",
                    "enum": sorted(FACE_DETAILER_MASK_BACKENDS),
                    "default": face_detailer.mask_backend,
                },
                "threshold": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 1,
                    "default": face_detailer.threshold,
                },
                "crop_scale": {
                    "type": "number",
                    "exclusiveMinimum": 0,
                    "maximum": MAX_FACE_CROP_SCALE,
                    "default": face_detailer.crop_scale,
                },
                "padding": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": MAX_FACE_PADDING,
                    "default": face_detailer.padding,
                },
                "feather": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": MAX_FACE_FEATHER,
                    "default": face_detailer.feather,
                },
                "exclude_forehead_ratio": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 0.75,
                    "default": face_detailer.exclude_forehead_ratio,
                },
                "steps": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": MAX_SAMPLING_STEPS,
                    "default": face_detailer.steps,
                },
                "denoise": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 1,
                    "default": face_detailer.denoise,
                },
                "sam3_face_eyes": {"type": "boolean", "default": face_detailer.sam3_face_eyes},
                "sam3_hands": {"type": "boolean", "default": face_detailer.sam3_hands},
                "hand_denoise": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 1,
                    "default": face_detailer.hand_denoise,
                },
            },
            "additionalProperties": False,
        },
        "VaeDecodeSettings": {
            "type": "object",
            "properties": {
                "mode": {
                    "type": "string",
                    "enum": ["auto", "standard", "tiled"],
                    "default": vae.mode,
                },
                "tile_size": {
                    "type": "integer",
                    "minimum": MIN_TILE_SIZE,
                    "maximum": MAX_TILE_SIZE,
                    "default": vae.tile_size,
                },
                "overlap": {"type": "integer", "minimum": 0, "default": vae.overlap},
            },
            "additionalProperties": False,
        },
        "T2IRequest": {
            "type": "object",
            "required": ["prompt"],
            "description": (
                "Canonical agent request. The server also accepts a few browser compatibility aliases, "
                "but agents should only send fields declared here. Runtime validation additionally enforces "
                "combined pixel budgets and tile overlap constraints."
            ),
            "properties": {
                "provider": {"type": "string", "const": "local", "default": "local"},
                "operation": {"type": "string", "enum": ["generate", "detail", "upscale"], "default": "generate",
                              "description": "Detail/upscale require a managed i2i input and the corresponding post-processing settings."},
                "workflow": _schema_ref("GenerationWorkflow"),
                "prompt": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": MAX_PROMPT_CHARACTERS,
                    "pattern": "\\S",
                },
                "negative_prompt": {
                    "type": "string",
                    "maxLength": MAX_PROMPT_CHARACTERS,
                    "default": "",
                },
                "memory_profile": {
                    "type": "string",
                    "enum": sorted(MEMORY_PROFILES),
                    "default": "auto",
                },
                "width": {
                    "type": "integer",
                    "minimum": 8,
                    "maximum": MAX_GENERATION_DIMENSION,
                    "multipleOf": 8,
                    "default": DEFAULT_T2I_WIDTH,
                },
                "height": {
                    "type": "integer",
                    "minimum": 8,
                    "maximum": MAX_GENERATION_DIMENSION,
                    "multipleOf": 8,
                    "default": DEFAULT_T2I_HEIGHT,
                },
                "steps": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": MAX_SAMPLING_STEPS,
                    "default": DEFAULT_T2I_STEPS,
                },
                "cfg": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": MAX_CFG,
                    "default": DEFAULT_T2I_CFG,
                },
                "seed": {
                    "type": ["integer", "null"],
                    "minimum": 0,
                    "maximum": MAX_SEED,
                    "default": None,
                },
                "checkpoint": {
                    "type": "string",
                    "minLength": 1,
                    "description": "Relative .safetensors path; omit to use the default from /api/checkpoints.",
                },
                "sampler": {
                    "type": "string",
                    "enum": sorted(CFG_PP_SAMPLERS),
                    "default": DEFAULT_T2I_SAMPLER,
                },
                "scheduler": {"type": "string", "default": DEFAULT_T2I_SCHEDULER},
                "loras": {
                    "type": "array",
                    "maxItems": MAX_LORA_COUNT,
                    "items": _schema_ref("LoraConfig"),
                    "default": [],
                },
                "i2i": _schema_ref("I2ISettings"),
                "upscale": _schema_ref("UpscaleSettings"),
                "face_detailer": _schema_ref("FaceDetailerSettings"),
                "vae_decode": _schema_ref("VaeDecodeSettings"),
                "wildcard_mode": {
                    "type": "string",
                    "enum": sorted(WILDCARD_MODES),
                    "default": "random",
                },
                "dry_run": {"type": "boolean", "default": default_dry_run},
            },
            "additionalProperties": False,
        },
        "NovelAICharacter": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "prompt": {"type": "string", "maxLength": MAX_PROMPT_CHARACTERS, "default": ""},
                "negative_prompt": {"type": "string", "maxLength": MAX_PROMPT_CHARACTERS, "default": ""},
                "x": {"type": "number", "minimum": 0, "maximum": 1, "default": 0.5},
                "y": {"type": "number", "minimum": 0, "maximum": 1, "default": 0.5},
            },
        },
        "NovelAIRequest": {
            "type": "object", "required": ["provider", "prompt"], "additionalProperties": False,
            "description": "NovelAI T2I or infill. Infill requires managed input/mask paths matching the requested size, a dedicated inpainting model and nai_limit_opus_free=false. Credentials come from the server environment.",
            "properties": {
                "provider": {"type": "string", "const": "novelai"},
                "workflow": _schema_ref("GenerationWorkflow"),
                "prompt": {"type": "string", "minLength": 1, "maxLength": MAX_PROMPT_CHARACTERS, "pattern": "\\S"},
                "negative_prompt": {"type": "string", "maxLength": MAX_PROMPT_CHARACTERS, "default": ""},
                "width": {"type": "integer", "minimum": 64, "maximum": MAX_GENERATION_DIMENSION, "multipleOf": 64, "default": 832},
                "height": {"type": "integer", "minimum": 64, "maximum": MAX_GENERATION_DIMENSION, "multipleOf": 64, "default": 1216},
                "steps": {"type": "integer", "minimum": 1, "maximum": 50, "default": 28},
                "cfg": {"type": "number", "minimum": 0, "maximum": MAX_CFG, "default": 6.0},
                "seed": {"type": ["integer", "null"], "minimum": 0, "maximum": MAX_NAI_SEED, "default": None},
                "nai_model": {"type": "string", "enum": sorted(MODEL_IDS | SUPPORTED_INPAINT_MODEL_IDS), "default": "nai-diffusion-5-curated"},
                "operation": {"type": "string", "enum": ["generate", "img2img", "infill", "detail", "focused_infill"], "default": "generate"},
                "input_image": {"type": "string", "maxLength": 4096, "default": "", "description": "Managed path under inputs/references or outputs/images."},
                "mask_image": {"type": "string", "maxLength": 4096, "default": "", "description": "Same-sized mask: white repaints, black preserves."},
                "inpaint_strength": {"type": "number", "minimum": 0, "maximum": 1, "default": 1},
                "img2img_strength": {"type": "number", "minimum": 0, "maximum": 1, "default": 0.5},
                "img2img_noise": {"type": "number", "minimum": 0, "maximum": 1, "default": 0},
                "nai_sampler": {"type": "string", "enum": sorted(SAMPLERS), "default": "k_euler"},
                "nai_scheduler": {"type": "string", "enum": sorted(SCHEDULERS), "default": "karras"},
                "nai_cfg_rescale": {"type": "number", "minimum": 0, "maximum": 1, "default": 0},
                "nai_prefer_brownian": {"type": "boolean", "default": False},
                "nai_characters": {"type": "array", "maxItems": 22, "items": _schema_ref("NovelAICharacter"), "default": [],
                                   "description": "Active prompts: V5 max 22; V4/V4.5 max 6; V3 zero. V5 Curated infill routes to V4.5 (6). If slots are supplied this list must match their enabled visible entries, or may be omitted."},
                "nai_character_slots": {"type": "array", "maxItems": 22, "items": {
                    "type": "object", "additionalProperties": False, "properties": {
                        "prompt": {"type": "string", "maxLength": MAX_PROMPT_CHARACTERS, "default": ""},
                        "negative_prompt": {"type": "string", "maxLength": MAX_PROMPT_CHARACTERS, "default": ""},
                        "x": {"type": "number", "minimum": 0, "maximum": 1, "default": 0.5},
                        "y": {"type": "number", "minimum": 0, "maximum": 1, "default": 0.5},
                        "enabled": {"type": "boolean", "default": True},
                        "collapsed": {"type": "boolean", "default": False}}},
                    "description": "Optional saved slots, including hidden/disabled values; never sent to NovelAI."},
                "nai_character_count": {"type": "integer", "minimum": 0, "maximum": 22,
                    "description": "Visible prefix of saved slots (default all). Entries after this count are retained but excluded from generation."},
                "nai_use_coords": {"type": "boolean", "default": True},
                "nai_use_order": {"type": "boolean", "default": True},
                "nai_vibes": {"type": "array", "maxItems": 16, "items": {"type": "object", "additionalProperties": False,
                    "required": ["image"], "properties": {"image": {"type": "string", "maxLength": 4096},
                    "strength": {"type": "number", "minimum": 0, "maximum": 1, "default": 0.6},
                    "information_extracted": {"type": "number", "minimum": 0, "maximum": 1, "default": 1}}}},
                "nai_references": {"type": "array", "maxItems": 16, "items": {"type": "object", "additionalProperties": False,
                    "required": ["image"], "properties": {"image": {"type": "string", "maxLength": 4096},
                    "reference_type": {"type": "string", "enum": ["character", "style", "character&style"], "default": "character"},
                    "strength": {"type": "number", "minimum": 0, "maximum": 1, "default": 1},
                    "fidelity": {"type": "number", "minimum": 0, "maximum": 1, "default": 1}}}},
                "nai_normalize_vibe_strengths": {"type": "boolean", "default": True},
                "nai_detailer": {"type": "object", "description": "NAI detector/matching/focused crop settings. See provider guide.",
                    "additionalProperties": False, "properties": {
                        "enabled": {"type": "boolean", "default": False}, "preview_only": {"type": "boolean", "default": False},
                        "mode": {"type": "string", "enum": ["first", "all"]}, "matching": {"type": "string", "enum": ["shared", "wd14"]},
                        "backend": {"type": "string", "enum": ["sam_b", "sam3"]},
                        "wd_device": {"type": "string", "enum": ["auto", "cpu"]}, "wd_batch_size": {"type": "integer", "minimum": 1, "maximum": 16},
                        "concepts": {"type": "array", "minItems": 1, "maxItems": 3, "items": {"enum": ["face", "eyes", "hands"]}},
                        **{key: {"type": "number", "minimum": 0, "maximum": 1} for key in ("threshold", "mask_threshold", "strength", "match_min_score", "match_min_margin")},
                        **{key: {"type": "number", "minimum": 1, "maximum": 8} for key in ("crop_factor", "match_crop_factor")},
                        "steps": {"type": "integer", "minimum": 1, "maximum": 50}, "max_regions": {"type": "integer", "minimum": 1, "maximum": 16},
                        "padding": {"type": "integer", "minimum": 0, "maximum": 256}, "dilation": {"type": "integer", "minimum": -64, "maximum": 128}}},
                "nai_variety_boost": {"type": "boolean", "default": True},
                "nai_limit_opus_free": {"type": "boolean", "default": True,
                                        "description": "Cap T2I to one image, 1048576 pixels and 28 steps; before each transport attempt require active Opus tier 3 and, for V5, verifiable remaining allowance >=2 percent. Failed checks block generation. Infill is rejected while enabled."},
                "wildcard_mode": {"type": "string", "enum": sorted(WILDCARD_MODES), "default": "random"},
                "dry_run": {"type": "boolean", "default": default_dry_run},
            },
        },
        "GenerationWorkflow": {
            "type": "object", "additionalProperties": False, "required": ["steps"],
            "properties": {
                "version": {"type": "integer", "const": 1, "default": 1},
                "steps": {"type": "array", "minItems": 1, "maxItems": 6, "items": _schema_ref("GenerationWorkflowStep")},
            },
            "description": "Ordered post-processing after the base request. Intermediate images and a workflow journal are retained. Dry-run validates all stages without generating images.",
        },
        "GenerationWorkflowStep": {
            "type": "object", "additionalProperties": False, "required": ["provider", "operation"],
            "properties": {
                "provider": {"type": "string", "enum": ["local", "novelai"]},
                "operation": {"type": "string", "enum": ["detail", "upscale"]},
                "inherit_prompt": {"type": "boolean", "default": True},
                "request": {"type": "object", "description": "Partial provider settings. Previous output supplies the input and size. Nested workflows, credentials, dry_run and progress_id are rejected."},
            },
            "description": "Anima supports detail/upscale; NovelAI supports detail only. Up to six post-processing stages, plus the base generation.",
        },
        "GenerationRequest": {"oneOf": [_schema_ref("T2IRequest"), _schema_ref("NovelAIRequest")]},
        "Variant": {
            "type": "object",
            "properties": {
                "label": {"type": "string"},
                "output_path": {"type": "string"},
                "output_url": {"type": "string"},
            },
            "additionalProperties": True,
        },
        "GenerateResult": {
            "type": "object",
            "required": ["status", "manifest_path", "manifest_name", "warnings", "stages", "dry_run"],
            "properties": {
                "provider": {"type": "string", "enum": ["local", "novelai"]},
                "cancellation_requested": {"type": "boolean"},
                "status": {"type": "string", "enum": ["generated", "dry_run"]},
                "manifest_path": {"type": "string"},
                "manifest_name": {"type": "string"},
                "output_path": {"type": ["string", "null"]},
                "output_url": {"type": ["string", "null"]},
                "variants": {
                    "type": "object",
                    "additionalProperties": _schema_ref("Variant"),
                },
                "warnings": {"type": "array", "items": {"type": "string"}},
                "stages": {"type": "object", "additionalProperties": True},
                "wildcards": {"type": "object", "additionalProperties": True},
                "checkpoint": {"type": "string"},
                "dry_run": {"type": "boolean"},
            },
            "additionalProperties": True,
        },
        "Job": {
            "type": "object",
            "required": ["id", "batch_id", "index", "status", "request", "cancel_requested"],
            "properties": {
                "id": {"type": "string"},
                "batch_id": {"type": "string"},
                "index": {"type": "integer", "minimum": 0},
                "status": {
                    "type": "string",
                    "enum": ["queued", "waiting", "running", "completed", "failed", "cancelled"],
                },
                "request": _schema_ref("GenerationRequest"),
                "progress_id": {"type": "string"},
                "cancel_requested": {"type": "boolean"},
                "result": {
                    "oneOf": [
                        _schema_ref("GenerateResult"),
                        _schema_ref("Error"),
                        {"type": "null"},
                    ]
                },
                "error": {"type": "string"},
                "http_status": {"type": ["integer", "null"]},
                "delay_seconds": {"type": "number", "minimum": 0},
                "created_at": {"type": "number"},
                "started_at": {"type": ["number", "null"]},
                "finished_at": {"type": ["number", "null"]},
                "updated_at": {"type": "number"},
            },
            "additionalProperties": True,
        },
        "JobEnqueueRequest": {
            "type": "object",
            "required": ["request"],
            "properties": {
                "request": _schema_ref("GenerationRequest"),
                "count": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": max_queue_jobs,
                    "default": 1,
                },
                "infinite": {"type": "boolean", "default": False},
                "seed_mode": {
                    "type": "string",
                    "enum": ["fixed", "increment", "random"],
                    "default": "increment",
                },
                "delay_seconds": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": max_queue_delay_seconds,
                    "default": 0,
                },
            },
            "additionalProperties": False,
        },
        "JobEnqueueResult": {
            "type": "object",
            "required": ["status", "batch_id", "count", "infinite", "jobs", "summary"],
            "properties": {
                "status": {"type": "string", "const": "queued"},
                "batch_id": {"type": "string"},
                "count": {"type": "integer"},
                "infinite": {"type": "boolean"},
                "jobs": {"type": "array", "items": _schema_ref("Job")},
                "summary": {"type": "object", "additionalProperties": {"type": "integer"}},
            },
            "additionalProperties": True,
        },
        "JobListResult": {
            "type": "object",
            "required": ["count", "items", "summary"],
            "properties": {
                "count": {"type": "integer"},
                "items": {"type": "array", "items": _schema_ref("Job")},
                "summary": {"type": "object", "additionalProperties": {"type": "integer"}},
            },
            "additionalProperties": True,
        },
        "JobCancelResult": {
            "type": "object",
            "required": ["status", "job"],
            "properties": {
                "status": {"type": "string"},
                "job": _schema_ref("Job"),
            },
            "additionalProperties": True,
        },
    }

    for provider_schema in ("T2IRequest", "NovelAIRequest"):
        schemas[provider_schema]["properties"].update({
            "prompt_routing": {"type": "object", "additionalProperties": False, "required": ["source"],
                "properties": {"source": {"enum": ["auto", "native", "comfyui", "naiv4", "oldnai"]}},
                "description": "Optional provider-specific adaptation; omitted API setting preserves native text. Whole bare artist tags are matched offline against the local catalog."},
            "generation_sources": {"type": "array", "maxItems": 16, "items": {"type": "object", "additionalProperties": False,
                "required": ["asset_id", "record_id", "scope"], "properties": {
                    "asset_id": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                    "record_id": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                    "scope": {"enum": ["artists", "prompt", "all"]}}}},
        })

    paths: dict[str, Any] = {
        "/api/prompts/plan": {"post": {
            "operationId": "previewGenerationPrompts", "summary": "Preview each stage's prompt syntax, artist recognition, and warnings without generating",
            "requestBody": {"required": True, "content": {"application/json": {"schema": _schema_ref("GenerationRequest")}}},
            "responses": {"200": generic_response, "400": error_response, "403": error_response},
        }},
        "/api/providers": {"get": {"operationId": "getProviders", "summary": "Discover provider capabilities and dry-run policy", "tags": ["Discovery"], "responses": {"200": generic_response}}},
        "/api/nai/status": {"get": {"operationId": "getNovelAIStatus", "summary": "Check server token presence without exposing credentials", "tags": ["Discovery"], "responses": {"200": generic_response}}},
        "/api/nai/tagger": {"get": {"operationId": "getTaggerPreparation", "summary": "Pinned tagger models and current local preparation/download progress (no network lookup)", "responses": {"200": generic_response}}},
        "/api/nai/tagger/prepare": {"post": {
            "operationId": "prepareTagger", "summary": "Download selected pinned tagger from Hugging Face and validate local load; no NAI request",
            "requestBody": {"required": True, "content": {"application/json": {"schema": {
                "type": "object", "additionalProperties": False, "properties": {
                    "model_name": {"type": "string", "enum": list(TAGGER_MODELS), "default": DEFAULT_MODEL},
                    "device": {"type": "string", "enum": ["auto", "cpu"], "default": "auto"},
                    "batch_size": {"type": "integer", "minimum": 1, "maximum": 16, "default": 4},
                }}}}}, "responses": {"202": generic_response, "400": error_response, "409": error_response}}},
        "/api/nai/tagger/cancel": {"post": {
            "operationId": "cancelTaggerPreparation", "summary": "Cooperatively cancel the identified preparation; poll until terminal",
            "requestBody": {"required": True, "content": {"application/json": {"schema": {
                "type": "object", "required": ["job_id"], "properties": {"job_id": {"type": "string"}}}}}},
            "responses": {"202": generic_response, "404": error_response}}},
        "/api/openapi.json": {
            "get": {
                "operationId": "getOpenApiDocument",
                "summary": "Get the machine-readable local agent contract",
                "tags": ["Discovery"],
                "responses": {"200": _json_response("OpenAPI 3.1 document", _schema_ref("GenericObject"))},
            }
        },
        "/api/version": {
            "get": {
                "operationId": "getVersion",
                "summary": "Get application version information",
                "tags": ["Discovery"],
                "responses": {"200": generic_response},
            }
        },
        "/api/health": {
            "get": {
                "operationId": "getHealth",
                "summary": "Get local runtime, model, and storage health",
                "tags": ["Discovery"],
                "responses": {"200": generic_response},
            }
        },
        "/api/readiness": {
            "get": {
                "operationId": "getReadiness",
                "summary": "Check whether the selected checkpoint can generate",
                "tags": ["Discovery"],
                "parameters": [
                    {
                        "name": "checkpoint",
                        "in": "query",
                        "required": False,
                        "schema": {"type": "string"},
                        "description": "Relative checkpoint path; omit to inspect the current default.",
                    }
                ],
                "responses": {"200": generic_response},
            }
        },
        "/api/checkpoints": {
            "get": {
                "operationId": "listCheckpoints",
                "summary": "List locally available checkpoints and the current default",
                "tags": ["Discovery"],
                "responses": {"200": generic_response},
            }
        },
        "/api/loras": {
            "get": {
                "operationId": "listLoras",
                "summary": "List locally available LoRAs",
                "tags": ["Discovery"],
                "responses": {"200": generic_response},
            }
        },
        "/api/prompts/convert": {"post": {
            "operationId": "convertPromptWeights", "summary": "Preview one of six local prompt syntax conversions",
            "tags": ["Discovery"],
            "requestBody": {"required": True, "content": {"application/json": {"schema": {
                "type": "object", "required": ["source", "target", "text"], "additionalProperties": False,
                "properties": {"source": {"enum": ["comfyui", "naiv4", "oldnai"]},
                               "target": {"enum": ["comfyui", "naiv4", "oldnai"]},
                               "text": {"type": "string", "maxLength": MAX_PROMPT_CHARACTERS}},
            }}}}, "responses": {"200": generic_response, "400": error_response, "403": error_response},
        }},
        "/api/metadata/novelai": {
            "post": {
                "operationId": "readNovelAIImageMetadata",
                "summary": "Read existing PNG/WebP generation settings without generating an image",
                "description": "Reads PNG text, WebP EXIF or alpha metadata. Returns supported form fields, model hash, "
                               "model candidates and warnings. Temporary upload is deleted; no provider call is made.",
                "tags": ["Discovery"],
                "requestBody": {
                    "required": True,
                    "content": {media_type: {"schema": {"type": "string", "format": "binary"}}
                                for media_type in ("image/png", "image/webp", "application/octet-stream")},
                },
                "responses": {"200": generic_response, "400": error_response, "403": error_response,
                              "411": error_response, "413": error_response, "415": error_response},
            }
        },
        "/api/generate": {
            "post": {
                "operationId": "generateImage",
                "summary": "Generate synchronously; prefer the job queue for cancellable work",
                "tags": ["Generation"],
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": _schema_ref("GenerationRequest"),
                            "example": {"prompt": "anime portrait", "dry_run": True},
                        }
                    },
                },
                "responses": {
                    "200": _json_response("Generation result", _schema_ref("GenerateResult")),
                    "400": error_response,
                    "401": error_response,
                    "402": error_response,
                    "403": error_response,
                    "429": error_response,
                    "409": models_not_ready_response,
                    "500": error_response,
                    "502": error_response,
                    "504": error_response,
                },
            }
        },
        "/api/jobs": {
            "get": {
                "operationId": "listJobs",
                "summary": "List retained local queue jobs",
                "tags": ["Jobs"],
                "responses": {"200": _json_response("Queue state", _schema_ref("JobListResult"))},
            },
            "post": {
                "operationId": "enqueueJobs",
                "summary": "Enqueue one or more cancellable generation jobs",
                "tags": ["Jobs"],
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": _schema_ref("JobEnqueueRequest"),
                            "example": {
                                "count": 1,
                                "seed_mode": "fixed",
                                "request": {"prompt": "anime portrait", "dry_run": True},
                            },
                        }
                    },
                },
                "responses": {
                    "202": _json_response("Jobs accepted", _schema_ref("JobEnqueueResult")),
                    "400": error_response,
                    "409": models_not_ready_response,
                    "429": queue_full_response,
                },
            },
        },
        "/api/jobs/{job_id}": {
            "get": {
                "operationId": "getJob",
                "summary": "Get one queue job",
                "tags": ["Jobs"],
                "parameters": [_path_parameter("job_id", "Job id returned by enqueueJobs.")],
                "responses": {
                    "200": _json_response("Job state", _schema_ref("Job")),
                    "400": error_response,
                    "404": error_response,
                },
            }
        },
        "/api/jobs/{job_id}/cancel": {
            "post": {
                "operationId": "cancelJob",
                "summary": "Cancel a queued job or request interruption of the running job",
                "tags": ["Jobs"],
                "parameters": [_path_parameter("job_id", "Job id returned by enqueueJobs.")],
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {"type": "object", "maxProperties": 0, "additionalProperties": False}
                        }
                    },
                },
                "responses": {
                    "200": _json_response("Cancellation state", _schema_ref("JobCancelResult")),
                    "400": error_response,
                    "404": error_response,
                },
            }
        },
        "/api/progress/{progress_id}": {
            "get": {
                "operationId": "getProgress",
                "summary": "Get stage progress for a queue job",
                "tags": ["Jobs"],
                "parameters": [_path_parameter("progress_id", "Progress id, normally the queue job id.")],
                "responses": {
                    "200": generic_response,
                    "400": error_response,
                    "404": error_response,
                },
            }
        },
        "/api/manifests/{manifest_name}": {
            "get": {
                "operationId": "getManifest",
                "summary": "Read one generated JSON manifest",
                "tags": ["Results"],
                "parameters": [_path_parameter("manifest_name", "Manifest filename returned in manifest_name.")],
                "responses": {
                    "200": generic_response,
                    "400": error_response,
                    "403": error_response,
                    "404": error_response,
                },
            }
        },
    }

    for suffix, method, operation_id, summary in (
        ('status', 'get', 'libraryStatus', 'Local library capacity, encoder and import status'),
        ('items', 'get', 'libraryItems', 'Browse prompt, annotation and combination records'),
        ('item/{asset_id}', 'get', 'libraryItem', 'Read saved generation evidence and source locations'),
        ('thumbnail/{asset_id}', 'get', 'libraryThumbnail', 'Read a library thumbnail'),
        ('preview/{asset_id}', 'get', 'libraryPreview', 'Read a metadata-free JPEG preview bounded to 1600 pixels'),
        ('search', 'post', 'librarySearch', 'Find pixel-derived neighbors for an indexed image'),
        ('query-image', 'post', 'libraryQueryImage', 'Find neighbors from a local image upload'),
        ('import', 'post', 'libraryImport', 'Import folders, sync manifests, or build VRS features'),
        ('cancel', 'post', 'libraryCancel', 'Cancel the current library background job'),
        ('annotate', 'post', 'libraryAnnotate', 'Update favorites, tags, collection and note'),
        ('feedback', 'post', 'libraryFeedback', 'Record similarity and reuse evaluations without training'),
        ('compare', 'post', 'libraryCompare', 'Record a relative visual judgment between two results of the same query'),
        ('compare/undo', 'post', 'libraryCompareUndo', 'Undo a comparison while retaining its audit record'),
    ):
        operation = {'operationId': operation_id, 'summary': summary, 'tags': ['Library'],
                     'responses': {'200': generic_response, '400': error_response, '403': error_response,
                                   '404': error_response, '409': error_response}}
        if '{asset_id}' in suffix:
            operation['parameters'] = [_path_parameter('asset_id', 'SHA-256 image identifier')]
        if method == 'post':
            content = {'application/json': {'schema': {'type': 'object'}}}
            if suffix == 'query-image':
                content = {media: {'schema': {'type': 'string', 'format': 'binary'}}
                           for media in ('image/png', 'image/jpeg', 'image/webp')}
                operation['parameters'] = [{'name': 'mode', 'in': 'query',
                    'schema': {'type': 'string', 'enum': ['visual', 'vrs'], 'default': 'visual'}},
                    {'name': 'ranking', 'in': 'query',
                     'schema': {'type': 'string', 'enum': ['similar', 'diverse'], 'default': 'similar'}}]
            elif suffix == 'search':
                content['application/json']['schema'] = {'type': 'object', 'required': ['id'],
                    'properties': {'id': {'type': 'string'},
                        'mode': {'type': 'string', 'enum': ['visual', 'vrs'], 'default': 'visual'},
                        'ranking': {'type': 'string', 'enum': ['similar', 'diverse'], 'default': 'similar'},
                        'limit': {'type': 'integer', 'minimum': 1, 'maximum': 100, 'default': 24}}}
            operation['requestBody'] = {'required': True, 'content': content}
        if suffix.startswith(('thumbnail/', 'preview/')):
            operation['responses']['200'] = {'description': 'Local JPEG preview',
                'content': {'image/jpeg': {'schema': {'type': 'string', 'format': 'binary'}}}}
        paths['/api/library/' + suffix] = {method: operation}

    paths['/api/setup/catalog'] = {'get': {
        'operationId': 'setupCatalog', 'tags': ['Setup'],
        'summary': 'Feature requirements, local model-file readiness and original reference links',
        'responses': {'200': generic_response, '403': error_response},
    }}
    paths['/api/setup/vrs/settings'] = {'post': {
        'operationId': 'setupVrsEnabled', 'tags': ['Setup'],
        'summary': 'Persist VRS enable state; disabling releases the idle encoder and retains all library records',
        'requestBody': {'required': True, 'content': {'application/json': {'schema': {
            'type': 'object', 'additionalProperties': False, 'required': ['enabled'],
            'properties': {'enabled': {'type': 'boolean'}},
        }}}},
        'responses': {'200': generic_response, '400': error_response, '403': error_response},
    }}
    paths['/api/setup/nai'] = {'post': {
        'operationId': 'setupNaiToken', 'tags': ['Setup'],
        'summary': 'Apply or clear an NAI token; optionally persist in this PC OS credential store',
        'requestBody': {'required': True, 'content': {'application/json': {'schema': {
            'type': 'object', 'additionalProperties': False,
            'properties': {'token': {'type': 'string', 'writeOnly': True, 'maxLength': 4096},
                           'use_current': {'type': 'boolean', 'default': False},
                           'persist': {'type': 'boolean', 'default': False}},
            'oneOf': [{'required': ['token'], 'properties': {'use_current': {'const': False}}},
                      {'required': ['use_current'], 'properties': {'use_current': {'const': True}},
                       'not': {'required': ['token']}}],
        }}}},
        'responses': {'200': generic_response, '400': error_response, '403': error_response},
    }}
    for suffix, method in [('status', 'get'), ('accounts', 'post'), ('accounts/remove', 'post'),
                           ('accounts/storage', 'post'),
                           ('start', 'post'), ('cancel', 'post')]:
        operation = {'operationId': 'barracks_' + suffix.replace('/', '_'), 'tags': ['Barracks'],
                     'summary': 'NAI standalone T2I batch: ' + suffix,
                     'responses': {'202' if suffix == 'start' else '200': generic_response,
                                   '400': error_response, '403': error_response}}
        if method == 'post':
            fields = {
                'accounts': {'name': {'type': 'string', 'minLength': 1, 'maxLength': 48},
                             'token': {'type': 'string', 'writeOnly': True, 'maxLength': 4096},
                             'use_current': {'type': 'boolean', 'default': False},
                             'persist': {'type': 'boolean', 'default': False}},
                'accounts/remove': {'id': {'type': 'string'}},
                'accounts/storage': {'id': {'type': 'string'}, 'persist': {'type': 'boolean'}},
                'start': {'request': {'type': 'object', 'description': 'NovelAI generate only. No workflow, detailer, input images or references.'},
                          'account_ids': {'type': 'array', 'items': {'type': 'string'}, 'minItems': 1, 'maxItems': 8, 'uniqueItems': True},
                          'count': {'type': 'integer', 'minimum': 1, 'maximum': 100, 'default': 1},
                          'seed_mode': {'type': 'string', 'enum': ['fixed', 'increment', 'random'], 'default': 'increment'}},
                'cancel': {},
            }[suffix]
            operation['requestBody'] = {'required': True, 'content': {'application/json': {'schema': {
                'type': 'object', 'additionalProperties': False, 'properties': fields,
                'required': {'accounts': ['name'], 'accounts/remove': ['id'], 'accounts/storage': ['id', 'persist'],
                             'start': ['request', 'account_ids'], 'cancel': []}[suffix],
            }}}}
        paths['/api/barracks/' + suffix] = {method: operation}

    return {
        "openapi": "3.1.0",
        "jsonSchemaDialect": "https://json-schema.org/draft/2020-12/schema",
        "info": {
            "title": "Anima APP Local Agent API",
            "version": app_version,
            "description": (
                "Machine-readable contract for local AI agents. The server is loopback-only. "
                "Use /api/jobs for cancellable work and validate requests against GenerationRequest before submission. NovelAI transmits prompts to the remote provider."
            ),
        },
        "servers": [{"url": "/", "description": "Current local Anima APP server"}],
        "tags": [
            {"name": "Discovery"},
            {"name": "Generation"},
            {"name": "Jobs"},
            {"name": "Results"},
            {"name": "Library"},
        ],
        "paths": paths,
        "components": {"schemas": schemas},
        "x-anima-agent": {
            "local_only": True,
            "idempotency_supported": False,
            "remote_outcome_policy": "Never automatically resubmit NovelAI requests after a timeout, lost response, malformed response or server restart. Running cancellation only stops future scheduling; already submitted requests may complete and be billed.",
            "unknown_request_fields": (
                "Clients should enforce additionalProperties=false; current server compatibility parsing may ignore them."
            ),
            "recommended_flow": [
                "GET /api/readiness",
                "POST /api/jobs",
                "GET /api/jobs/{job_id}",
                "POST /api/jobs/{job_id}/cancel when needed",
                "GET /api/manifests/{manifest_name}",
            ],
        },
    }

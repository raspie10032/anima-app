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
                "request": _schema_ref("T2IRequest"),
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
                "request": _schema_ref("T2IRequest"),
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

    paths: dict[str, Any] = {
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
        "/api/generate": {
            "post": {
                "operationId": "generateImage",
                "summary": "Generate synchronously; prefer the job queue for cancellable work",
                "tags": ["Generation"],
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": _schema_ref("T2IRequest"),
                            "example": {"prompt": "anime portrait", "dry_run": True},
                        }
                    },
                },
                "responses": {
                    "200": _json_response("Generation result", _schema_ref("GenerateResult")),
                    "400": error_response,
                    "409": models_not_ready_response,
                    "500": error_response,
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

    return {
        "openapi": "3.1.0",
        "jsonSchemaDialect": "https://json-schema.org/draft/2020-12/schema",
        "info": {
            "title": "Anima APP Local Agent API",
            "version": app_version,
            "description": (
                "Machine-readable contract for local AI agents. The server is loopback-only. "
                "Use /api/jobs for cancellable work and validate requests against T2IRequest before submission."
            ),
        },
        "servers": [{"url": "/", "description": "Current local Anima APP server"}],
        "tags": [
            {"name": "Discovery"},
            {"name": "Generation"},
            {"name": "Jobs"},
            {"name": "Results"},
        ],
        "paths": paths,
        "components": {"schemas": schemas},
        "x-anima-agent": {
            "local_only": True,
            "idempotency_supported": False,
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

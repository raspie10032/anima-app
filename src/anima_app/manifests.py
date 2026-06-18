from __future__ import annotations

import json
import time
from dataclasses import asdict
from pathlib import Path

from anima_app.config import AppPaths
from anima_app.output_names import allocate_manifest_path
from anima_app.requests import T2IRequest


PIPELINE_STAGES = ["tokenize", "text_encode", "base_t2i", "high_res_fix", "vae_decode", "face_detailer"]


def write_t2i_manifest(
    request: T2IRequest,
    *,
    paths: AppPaths,
    status: str,
    output_path: Path | None,
    latent: dict[str, int],
    stages: dict[str, object] | None = None,
    warnings: tuple[str, ...] = (),
    comfyui_runtime: str = "not_loaded",
    wildcards: dict[str, object] | None = None,
    png_metadata: dict[str, str] | None = None,
    variants: dict[str, Path] | None = None,
) -> Path:
    paths.manifest_root.mkdir(parents=True, exist_ok=True)
    created_at = time.time()
    manifest_path = allocate_manifest_path(
        request,
        paths=paths,
        status=status,
        output_path=output_path,
        created_at=created_at,
    )
    payload = {
        **asdict(request),
        "status": status,
        "output_path": str(output_path) if output_path else None,
        "pipeline": PIPELINE_STAGES,
        "stages": stages or {},
        "warnings": list(warnings),
        "variants": _manifest_variants(variants),
        "wildcards": wildcards or {"enabled": False, "mode": "random", "selections": []},
        "png_metadata": png_metadata or {},
        "latent": latent,
        "model_root": str(paths.model_root),
        "created_at": created_at,
        "manifest_path": str(manifest_path),
        "provenance": {
            "app": "anima-app",
            "comfyui_runtime": comfyui_runtime,
            "impact_pack_runtime": "not_loaded",
        },
    }
    manifest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest_path


def _manifest_variants(variants: dict[str, Path] | None) -> dict[str, dict[str, str]]:
    if not variants:
        return {}
    labels = {
        "original": "Original",
        "upscale": "Upscale",
        "face_detailer": "Face Detailer",
    }
    return {
        key: {
            "label": labels.get(key, key.replace("_", " ").title()),
            "output_path": str(path),
        }
        for key, path in variants.items()
    }


def read_manifest(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_t2i_history(paths: AppPaths, *, limit: int = 20) -> list[dict[str, object]]:
    if not paths.manifest_root.is_dir():
        return []
    payloads = [read_manifest(path) for path in paths.manifest_root.glob("*.json")]
    payloads.sort(key=lambda payload: float(payload.get("created_at", 0)), reverse=True)
    return payloads[:limit]

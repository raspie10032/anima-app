from __future__ import annotations

import json
import os
import tempfile
import time
from dataclasses import asdict
from pathlib import Path

from anima_app.config import AppPaths
from anima_app.output_names import allocate_manifest_path
from anima_app.path_safety import path_is_link as _path_is_link
from anima_app.requests import T2IRequest


PIPELINE_STAGES = [
    "tokenize",
    "text_encode",
    "base_t2i",
    "high_res_fix",
    "vae_decode",
    "face_detailer",
    "face_eye_detailer",
    "hand_detailer",
]

HISTORY_KINDS = frozenset({"all", "images", "dry-run"})


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
    _write_json_atomically(manifest_path, payload)
    return manifest_path


def _manifest_variants(variants: dict[str, Path] | None) -> dict[str, dict[str, str]]:
    if not variants:
        return {}
    labels = {
        "original": "Original",
        "upscale": "Upscale",
        "face_detailer": "Face Detailer",
        "face_eye_detailer": "Face + Eyes",
        "hand_detailer": "Hands",
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


def read_t2i_history(
    paths: AppPaths,
    *,
    limit: int | None = 20,
    before: tuple[float, str] | None = None,
    query: str = "",
    kind: str = "all",
) -> list[dict[str, object]]:
    if kind not in HISTORY_KINDS:
        raise ValueError(f"history kind must be one of: {', '.join(sorted(HISTORY_KINDS))}")
    if (
        _path_is_link(paths.output_root)
        or _path_is_link(paths.manifest_root)
        or not paths.manifest_root.is_dir()
    ):
        return []
    query_tokens = tuple(part.casefold() for part in query.split())
    payloads = []
    for path in paths.manifest_root.glob("*.json"):
        if _path_is_link(path):
            continue
        try:
            payload = read_manifest(path)
        except (json.JSONDecodeError, OSError, UnicodeError):
            continue
        if not isinstance(payload, dict):
            continue
        payload = dict(payload)
        payload.setdefault("manifest_path", str(path))
        payload["_history_filename"] = path.name
        if not _matches_history_query(payload, query_tokens):
            continue
        has_image = _has_managed_history_image(paths, payload)
        if kind == "images" and not has_image:
            continue
        if kind == "dry-run" and has_image:
            continue
        if before is not None and history_sort_key(payload) >= before:
            continue
        payloads.append(payload)
    payloads.sort(key=history_sort_key, reverse=True)
    return payloads if limit is None else payloads[:limit]


def _matches_history_query(
    payload: dict[str, object],
    query_tokens: tuple[str, ...],
) -> bool:
    if not query_tokens:
        return True
    searchable = [
        payload.get("prompt"),
        payload.get("negative_prompt"),
        payload.get("checkpoint"),
        payload.get("seed"),
        payload.get("_history_filename"),
    ]
    loras = payload.get("loras")
    if isinstance(loras, list):
        searchable.extend(
            lora.get("path")
            for lora in loras
            if isinstance(lora, dict)
        )
    haystack = "\n".join(str(value) for value in searchable if value is not None).casefold()
    return all(token in haystack for token in query_tokens)


def _has_managed_history_image(paths: AppPaths, payload: dict[str, object]) -> bool:
    raw_output_path = payload.get("output_path")
    if not isinstance(raw_output_path, str) or not raw_output_path:
        return False
    output_path = Path(raw_output_path)
    if not output_path.is_absolute():
        output_path = paths.project_root / output_path
    try:
        if (
            _path_is_link(paths.output_root)
            or _path_is_link(paths.image_root)
            or _path_is_link(output_path)
            or not output_path.is_file()
        ):
            return False
        output_path.resolve(strict=True).relative_to(paths.image_root.resolve(strict=False))
    except (OSError, ValueError):
        return False
    return True


def history_sort_key(payload: dict[str, object]) -> tuple[float, str]:
    try:
        created_at = float(payload.get("created_at", 0))
    except (TypeError, ValueError):
        created_at = 0.0
    return created_at, str(payload.get("_history_filename", ""))


def _write_json_atomically(path: Path, payload: dict[str, object]) -> None:
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f"{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            json.dump(payload, temporary, ensure_ascii=False, indent=2)
            temporary.flush()
            os.fsync(temporary.fileno())
        temporary_path.replace(path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()

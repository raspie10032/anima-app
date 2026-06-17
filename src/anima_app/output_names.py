from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from anima_app.config import AppPaths
from anima_app.requests import T2IRequest


PROMPT_SLUG_MAX_CHARS = 48


def build_output_stem(
    request: T2IRequest,
    *,
    status: str,
    created_at: float | None = None,
) -> str:
    created = time.time() if created_at is None else created_at
    timestamp = datetime.fromtimestamp(created).strftime("%Y%m%d-%H%M%S")
    seed = f"s{request.seed}" if request.seed is not None else "srandom"
    mode = _mode_for_request(request)
    if status == "dry_run":
        mode = f"{mode}_dry"
    prompt_slug = _prompt_slug(request.prompt)
    digest = _request_digest(request, status=status)
    return f"{timestamp}_{seed}_{request.width}x{request.height}_{mode}_{prompt_slug}_{digest}"


def allocate_output_path(
    request: T2IRequest,
    *,
    paths: AppPaths,
    status: str,
    created_at: float | None = None,
) -> Path:
    stem = build_output_stem(request, status=status, created_at=created_at)
    return _with_collision_suffix(paths.image_root / f"{stem}.png")


def allocate_manifest_path(
    request: T2IRequest,
    *,
    paths: AppPaths,
    status: str,
    output_path: Path | None = None,
    created_at: float | None = None,
) -> Path:
    stem = output_path.stem if output_path is not None else build_output_stem(request, status=status, created_at=created_at)
    return _with_collision_suffix(paths.manifest_root / f"{stem}.json")


def _mode_for_request(request: T2IRequest) -> str:
    if request.i2i.enabled:
        return "i2i"
    if request.loras:
        return "lora"
    if request.upscale.enabled:
        return "upscale"
    return "t2i"


def _prompt_slug(prompt: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", prompt.lower()).strip("-")
    slug = re.sub(r"-+", "-", slug)
    if not slug:
        return "prompt"
    return slug[:PROMPT_SLUG_MAX_CHARS].strip("-") or "prompt"


def _request_digest(request: T2IRequest, *, status: str) -> str:
    payload = {"request": asdict(request), "status": status}
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:6]


def _with_collision_suffix(path: Path) -> Path:
    if not path.exists():
        return path
    for index in range(2, 1000):
        candidate = path.with_name(f"{path.stem}_{index:02d}{path.suffix}")
        if not candidate.exists():
            return candidate
    raise FileExistsError(f"could not allocate unique output path for {path}")

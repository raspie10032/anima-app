from __future__ import annotations

import os
import shutil
from pathlib import Path

from anima_app.assets import ANIMA_T2I_ASSET_PROFILE, asset_file_is_ready, list_local_loras
from anima_app.config import AppPaths
from anima_app.memory_profiles import cached_runtime_profile_decision
from anima_app.path_safety import path_is_link as _path_is_link


def build_health_payload(paths: AppPaths) -> dict[str, object]:
    missing = [
        str(paths.model_root / relative_path)
        for relative_path in ANIMA_T2I_ASSET_PROFILE.files
        if not asset_file_is_ready(paths.model_root / relative_path, relative_path)
    ]
    memory_profile = cached_runtime_profile_decision(paths)
    output_root_is_link = _path_is_link(paths.output_root)
    image_count, image_bytes = (0, 0) if output_root_is_link else _regular_file_stats(paths.image_root)
    manifest_count, manifest_bytes = (0, 0) if output_root_is_link else _regular_file_stats(paths.manifest_root)
    disk = shutil.disk_usage(_nearest_existing_path(paths.project_root))
    return {
        "project_root": str(paths.project_root),
        "model_root": str(paths.model_root),
        "memory_profile": memory_profile,
        "models": {
            "profile": ANIMA_T2I_ASSET_PROFILE.name,
            "ready": not missing,
            "missing": missing,
        },
        "loras": {
            "count": len(list_local_loras(paths)),
        },
        "outputs": {
            "image_root": str(paths.image_root),
            "manifest_root": str(paths.manifest_root),
            "image_count": image_count,
            "image_bytes": image_bytes,
            "manifest_count": manifest_count,
            "manifest_bytes": manifest_bytes,
            "managed_bytes": image_bytes + manifest_bytes,
            "disk_free_bytes": disk.free,
            "disk_total_bytes": disk.total,
        },
    }


def _regular_file_stats(root: Path) -> tuple[int, int]:
    if not root.is_dir() or _path_is_link(root):
        return 0, 0
    count = 0
    size = 0
    pending = [root]
    while pending:
        directory = pending.pop()
        try:
            with os.scandir(directory) as entries:
                for entry in entries:
                    try:
                        entry_path = Path(entry.path)
                        if _path_is_link(entry_path):
                            continue
                        if entry.is_file(follow_symlinks=False):
                            count += 1
                            size += entry.stat(follow_symlinks=False).st_size
                        elif entry.is_dir(follow_symlinks=False):
                            pending.append(entry_path)
                    except OSError:
                        continue
        except OSError:
            continue
    return count, size


def _nearest_existing_path(path: Path) -> Path:
    candidate = path.resolve(strict=False)
    while not candidate.exists():
        parent = candidate.parent
        if parent == candidate:
            break
        candidate = parent
    return candidate

from __future__ import annotations

from anima_app.assets import ANIMA_T2I_ASSET_PROFILE, list_local_loras
from anima_app.config import AppPaths


def build_health_payload(paths: AppPaths) -> dict[str, object]:
    missing = [str(paths.model_root / relative_path) for relative_path in ANIMA_T2I_ASSET_PROFILE.files if not (paths.model_root / relative_path).is_file()]
    return {
        "project_root": str(paths.project_root),
        "model_root": str(paths.model_root),
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
        },
    }

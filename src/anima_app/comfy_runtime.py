from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from importlib.machinery import ModuleSpec
from pathlib import Path
from types import ModuleType

from anima_app.config import AppPaths, default_paths


class NativeAttentionImportBlocker:
    blocked_roots = ("flash_attn", "sageattention", "sageattn3", "xformers")

    def find_spec(
        self,
        fullname: str,
        path: object | None = None,
        target: ModuleType | None = None,
    ) -> ModuleSpec | None:
        root = fullname.split(".", 1)[0]
        if root in self.blocked_roots:
            raise ModuleNotFoundError(f"{root} is disabled for Anima APP local rendering stability")
        return None


@dataclass(frozen=True)
class ComfyRuntimeBootstrap:
    runtime_root: Path
    python_packages_root: Path
    model_root: Path
    model_folders: dict[str, Path]


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def vendor_root() -> Path:
    return project_root() / "vendor"


def comfy_runtime_root() -> Path:
    return vendor_root() / "anima_runtime"


def comfy_python_packages_root() -> Path:
    return vendor_root() / "python_packages"


def bootstrap_comfy_runtime(paths: AppPaths | None = None) -> ComfyRuntimeBootstrap:
    resolved_paths = paths or default_paths()
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
    _prepend_sys_path(comfy_python_packages_root())
    _prepend_sys_path(comfy_runtime_root())
    _install_native_attention_import_blocker()

    import folder_paths

    model_folders = _model_folder_paths(resolved_paths.model_root)
    for name, path in model_folders.items():
        folder_paths.add_model_folder_path(name, str(path))

    return ComfyRuntimeBootstrap(
        runtime_root=comfy_runtime_root(),
        python_packages_root=comfy_python_packages_root(),
        model_root=resolved_paths.model_root,
        model_folders=model_folders,
    )


def _prepend_sys_path(path: Path) -> None:
    text = str(path)
    if path.exists() and text not in sys.path:
        sys.path.insert(0, text)


def _install_native_attention_import_blocker() -> None:
    if any(isinstance(finder, NativeAttentionImportBlocker) for finder in sys.meta_path):
        return
    sys.meta_path.insert(0, NativeAttentionImportBlocker())


def _model_folder_paths(model_root: Path) -> dict[str, Path]:
    return {
        "checkpoints": model_root / "checkpoints",
        "diffusion_models": model_root / "diffusion_models",
        "unet": model_root / "diffusion_models",
        "text_encoders": model_root / "text_encoders",
        "clip": model_root / "clip",
        "vae": model_root / "vae",
        "loras": model_root / "loras",
        "embeddings": model_root / "embeddings",
        "vae_approx": model_root / "vae_approx",
        "upscale_models": model_root / "upscale_models",
        "ultralytics": model_root / "ultralytics",
        "sams": model_root / "sams",
    }

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


DEFAULT_PROJECT_ROOT = Path(r"C:\Users\seine\Documents\Anima APP")
DEFAULT_DEVELOPMENT_MODEL_SOURCE = Path(r"E:\ComfyUI_sage\ComfyUI\models")
DEFAULT_FACE_DETAILER_DETECTOR_SOURCE = Path(r"C:\Users\seine\Desktop\NAI-FaceDetailer\models\detectors")
DEFAULT_FACE_DETAILER_DETECTOR_FALLBACK_SOURCES = (
    Path(r"C:\Users\seine\Documents\AnimaStudio\models\detectors"),
    Path(r"C:\Users\seine\Documents\Anima-Gemma4-Fusion-Multimodal\models\detectors"),
)


@dataclass(frozen=True)
class AppPaths:
    project_root: Path = DEFAULT_PROJECT_ROOT
    development_model_source: Path = DEFAULT_DEVELOPMENT_MODEL_SOURCE
    face_detailer_detector_source: Path = DEFAULT_FACE_DETAILER_DETECTOR_SOURCE
    face_detailer_detector_fallback_sources: tuple[Path, ...] = DEFAULT_FACE_DETAILER_DETECTOR_FALLBACK_SOURCES

    @property
    def model_root(self) -> Path:
        return self.project_root / "models"

    @property
    def output_root(self) -> Path:
        return self.project_root / "outputs"

    @property
    def manifest_root(self) -> Path:
        return self.output_root / "manifests"

    @property
    def image_root(self) -> Path:
        return self.output_root / "images"

    @property
    def input_root(self) -> Path:
        return self.project_root / "inputs"

    @property
    def wildcard_root(self) -> Path:
        return self.project_root / "wildcards"

    @property
    def wildcard_state_path(self) -> Path:
        return self.output_root / "wildcard_state.json"


def default_paths() -> AppPaths:
    return AppPaths()

from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path


ENV_PROJECT_ROOT = "ANIMA_APP_ROOT"
ENV_MODEL_SOURCE = "ANIMA_APP_MODEL_SOURCE"
ENV_FACE_DETECTOR_SOURCE = "ANIMA_APP_FACE_DETECTOR_SOURCE"
ENV_FACE_DETECTOR_FALLBACKS = "ANIMA_APP_FACE_DETECTOR_FALLBACKS"


def _env_path(name: str) -> Path | None:
    raw = os.environ.get(name)
    if not raw:
        return None
    return Path(raw).expanduser()


def _env_paths(name: str) -> tuple[Path, ...]:
    raw = os.environ.get(name)
    if not raw:
        return ()
    return tuple(Path(chunk).expanduser() for chunk in raw.split(os.pathsep) if chunk)


def _default_project_root() -> Path:
    return _env_path(ENV_PROJECT_ROOT) or Path.cwd()


def _default_development_model_source() -> Path:
    root = _default_project_root()
    return _env_path(ENV_MODEL_SOURCE) or root / "external_models"


def _default_face_detailer_detector_source() -> Path:
    root = _default_project_root()
    return _env_path(ENV_FACE_DETECTOR_SOURCE) or root / "external_detectors"


def _default_face_detailer_detector_fallback_sources() -> tuple[Path, ...]:
    return _env_paths(ENV_FACE_DETECTOR_FALLBACKS)


@dataclass(frozen=True)
class AppPaths:
    project_root: Path = field(default_factory=_default_project_root)
    development_model_source: Path = field(default_factory=_default_development_model_source)
    face_detailer_detector_source: Path = field(default_factory=_default_face_detailer_detector_source)
    face_detailer_detector_fallback_sources: tuple[Path, ...] = field(
        default_factory=_default_face_detailer_detector_fallback_sources
    )

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

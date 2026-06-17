from __future__ import annotations

import shutil
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    from huggingface_hub import hf_hub_download
except ImportError:  # pragma: no cover - exercised only in environments missing the declared dependency.
    hf_hub_download = None


KNOWN_MODEL_FOLDERS = (
    "checkpoints",
    "diffusion_models",
    "vae",
    "text_encoders",
    "clip",
    "loras",
    "upscale_models",
    "detectors",
    "ultralytics",
    "sams",
)


ANIMA_T2I_HF_REPO = "circlestone-labs/Anima"
ANIMA_T2I_HF_SUBFOLDER = "split_files"


@dataclass(frozen=True)
class AssetFile:
    relative_path: Path
    size_bytes: int


@dataclass(frozen=True)
class ModelInventory:
    source_root: Path
    folders: tuple[str, ...]
    files: tuple[AssetFile, ...]


@dataclass(frozen=True)
class AssetProfile:
    name: str
    files: tuple[Path, ...]


@dataclass(frozen=True)
class RemoteAsset:
    repo_id: str | None = None
    filename: str | None = None
    url: str | None = None
    reference: str = ""
    license: str = ""


ANIMA_T2I_ASSET_PROFILE = AssetProfile(
    name="anima-t2i",
    files=(
        Path("diffusion_models") / "anima-base-v1.0.safetensors",
        Path("text_encoders") / "qwen_3_06b_base.safetensors",
        Path("vae") / "qwen_image_vae.safetensors",
    ),
)


FACE_DETAILER_DETECTOR_ASSET_PROFILE = AssetProfile(
    name="face-detailer-detectors",
    files=(
        Path("detectors") / "face_yolov8n.pt",
        Path("detectors") / "full_eyes_detect_v1.pt",
        Path("detectors") / "sam_b.pt",
    ),
)


MIN_DETECTOR_ASSET_BYTES = 1024

DETECTOR_REMOTE_ASSETS: dict[Path, RemoteAsset] = {
    Path("detectors") / "face_yolov8n.pt": RemoteAsset(
        repo_id="Bingsu/adetailer",
        filename="face_yolov8n.pt",
        reference="https://huggingface.co/Bingsu/adetailer",
        license="apache-2.0 model card; Ultralytics runtime/model licensing may impose AGPL/commercial obligations",
    ),
    Path("detectors") / "full_eyes_detect_v1.pt": RemoteAsset(
        repo_id="guon/hand-eyes",
        filename="full_eyes_detect_v1.pt",
        reference="https://huggingface.co/guon/hand-eyes",
        license="not specified by source model card",
    ),
    Path("detectors") / "sam_b.pt": RemoteAsset(
        url="https://github.com/ultralytics/assets/releases/download/v0.0.0/sam_b.pt",
        reference="https://github.com/facebookresearch/segment-anything",
        license="SAM reference model Apache-2.0; Ultralytics asset/runtime licensing may impose AGPL/commercial obligations",
    ),
}


def asset_profiles() -> tuple[AssetProfile, ...]:
    return (ANIMA_T2I_ASSET_PROFILE, FACE_DETAILER_DETECTOR_ASSET_PROFILE)


def asset_profile(name: str) -> AssetProfile:
    for profile in asset_profiles():
        if name == profile.name:
            return profile
    raise ValueError(f"unknown asset profile: {name}")


def scan_model_source(source_root: Path) -> ModelInventory:
    source_root = source_root.resolve()
    folders = tuple(name for name in KNOWN_MODEL_FOLDERS if (source_root / name).is_dir())
    files: list[AssetFile] = []
    for folder in folders:
        for path in sorted((source_root / folder).rglob("*")):
            if path.is_file():
                files.append(AssetFile(path.relative_to(source_root), path.stat().st_size))
    return ModelInventory(source_root=source_root, folders=folders, files=tuple(files))


def copy_asset_file(source_root: Path, dest_root: Path, relative_path: Path) -> Path:
    source_root = source_root.resolve()
    dest_root = dest_root.resolve()
    source = (source_root / relative_path).resolve()
    destination = (dest_root / relative_path).resolve()

    source.relative_to(source_root)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return destination


def download_asset_file_from_huggingface(dest_root: Path, relative_path: Path) -> Path:
    if hf_hub_download is None:
        raise RuntimeError("huggingface_hub is required to download Anima model assets")

    dest_root = dest_root.resolve()
    destination = (dest_root / relative_path).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    remote_path = (Path(ANIMA_T2I_HF_SUBFOLDER) / relative_path).as_posix()
    downloaded = Path(hf_hub_download(repo_id=ANIMA_T2I_HF_REPO, filename=remote_path))
    shutil.copy2(downloaded, destination)
    return destination


def download_asset_file_from_remote(dest_root: Path, relative_path: Path) -> Path:
    remote = DETECTOR_REMOTE_ASSETS.get(relative_path)
    if remote is None:
        raise ValueError(f"no remote download source is configured for {relative_path}")

    if remote.repo_id and remote.filename:
        if hf_hub_download is None:
            raise RuntimeError("huggingface_hub is required to download detector assets")
        downloaded = Path(hf_hub_download(repo_id=remote.repo_id, filename=remote.filename))
        destination = _destination_for(dest_root, relative_path)
        shutil.copy2(downloaded, destination)
        _validate_detector_download(destination, relative_path)
        return destination

    if remote.url:
        destination = _destination_for(dest_root, relative_path)
        temporary = destination.with_name(f"{destination.name}.download")
        try:
            with urllib.request.urlopen(remote.url) as response, temporary.open("wb") as output:
                shutil.copyfileobj(response, output)
            _validate_detector_download(temporary, relative_path)
            temporary.replace(destination)
            return destination
        finally:
            if temporary.exists():
                temporary.unlink()

    raise ValueError(f"invalid remote download source for {relative_path}")


def _destination_for(dest_root: Path, relative_path: Path) -> Path:
    dest_root = dest_root.resolve()
    destination = (dest_root / relative_path).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.relative_to(dest_root)
    return destination


def _validate_detector_download(path: Path, relative_path: Path) -> None:
    if path.stat().st_size < MIN_DETECTOR_ASSET_BYTES:
        raise RuntimeError(f"downloaded detector asset is too small: {relative_path}")


def copy_asset_profile(profile: AssetProfile, paths: Any, *, source: str = "auto") -> tuple[str, list[Path]]:
    if profile.name == FACE_DETAILER_DETECTOR_ASSET_PROFILE.name:
        selected_source = _select_face_detailer_detector_source(profile, paths, source)
        if selected_source == "download":
            return (
                selected_source,
                [download_asset_file_from_remote(paths.model_root, relative_path) for relative_path in profile.files],
            )
        return (
            selected_source,
            [
                copy_asset_file(
                    _select_face_detector_source(paths, Path(relative_path.name)),
                    paths.model_root / "detectors",
                    Path(relative_path.name),
                )
                for relative_path in profile.files
            ],
        )
    if profile.name == ANIMA_T2I_ASSET_PROFILE.name:
        selected_source = _select_anima_t2i_source(profile, paths, source)
        if selected_source == "huggingface":
            return (
                selected_source,
                [download_asset_file_from_huggingface(paths.model_root, relative_path) for relative_path in profile.files],
            )
        return (
            selected_source,
            [copy_asset_file(paths.development_model_source, paths.model_root, relative_path) for relative_path in profile.files],
        )
    return (
        "local",
        [copy_asset_file(paths.development_model_source, paths.model_root, relative_path) for relative_path in profile.files],
    )


def _select_anima_t2i_source(profile: AssetProfile, paths: Any, source: str) -> str:
    if source == "download":
        return "huggingface"
    if source in {"local", "huggingface"}:
        return source
    if source != "auto":
        raise ValueError(f"unsupported model source: {source}")
    local_ready = all((paths.development_model_source / relative_path).is_file() for relative_path in profile.files)
    return "local" if local_ready else "huggingface"


def _select_face_detailer_detector_source(profile: AssetProfile, paths: Any, source: str) -> str:
    if source == "local":
        return "local"
    if source in {"download", "huggingface"}:
        return "download"
    if source != "auto":
        raise ValueError(f"unsupported detector source: {source}")
    local_ready = all(
        any(
            (source_root / relative_path.name).is_file()
            and (source_root / relative_path.name).stat().st_size >= MIN_DETECTOR_ASSET_BYTES
            for source_root in (paths.face_detailer_detector_source, *paths.face_detailer_detector_fallback_sources)
        )
        for relative_path in profile.files
    )
    return "local" if local_ready else "download"


def _select_face_detector_source(paths: Any, relative_path: Path) -> Path:
    checked: list[str] = []
    for source_root in (paths.face_detailer_detector_source, *paths.face_detailer_detector_fallback_sources):
        candidate = source_root / relative_path
        if candidate.is_file() and candidate.stat().st_size >= MIN_DETECTOR_ASSET_BYTES:
            return source_root
        checked.append(str(candidate))
    raise FileNotFoundError(
        f"missing valid face detailer detector asset {relative_path}; checked: " + ", ".join(checked)
    )


def import_lora_file(source_path: Path, paths: Any) -> Path:
    source = source_path.resolve()
    if source.suffix.lower() != ".safetensors":
        raise ValueError("LoRA import only accepts .safetensors files")
    if not source.is_file():
        raise FileNotFoundError(source)
    destination = paths.model_root / "loras" / source.name
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return destination


def list_local_loras(paths: Any) -> list[dict[str, int | str]]:
    lora_root = paths.model_root / "loras"
    if not lora_root.is_dir():
        return []
    items = []
    for path in sorted(lora_root.rglob("*.safetensors")):
        if path.is_file():
            items.append(
                {
                    "relative_path": path.relative_to(lora_root).as_posix(),
                    "size_bytes": path.stat().st_size,
                }
            )
    return items


def list_local_checkpoints(paths: Any) -> list[dict[str, int | str]]:
    checkpoint_root = paths.model_root / "diffusion_models"
    if not checkpoint_root.is_dir():
        return []
    items = []
    for path in sorted(checkpoint_root.rglob("*.safetensors")):
        if path.is_file():
            items.append(
                {
                    "relative_path": path.relative_to(checkpoint_root).as_posix(),
                    "size_bytes": path.stat().st_size,
                }
            )
    return items

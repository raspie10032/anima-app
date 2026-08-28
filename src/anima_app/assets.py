from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
import threading
import urllib.request
import warnings
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
from typing import Any

from PIL import Image, UnidentifiedImageError
from safetensors import SafetensorError, safe_open

from anima_app.defaults import PREFERRED_T2I_CHECKPOINT
from anima_app.requests import normalize_checkpoint_path

try:
    from huggingface_hub import hf_hub_download
except ImportError:  # pragma: no cover - exercised only in environments missing the declared dependency.
    hf_hub_download = None


ANIMA_T2I_HF_REPO = "circlestone-labs/Anima"
ANIMA_T2I_HF_SUBFOLDER = "split_files"
MAX_REFERENCE_UPLOAD_BYTES = 64 * 1024 * 1024
MAX_REFERENCE_IMAGE_DIMENSION = 8192
MAX_REFERENCE_IMAGE_PIXELS = 16_777_216
MAX_LORA_UPLOAD_BYTES = 1024 * 1024 * 1024

_REFERENCE_IMAGE_TYPE_BY_EXTENSION = {
    ".png": ("image/png", "PNG", ".png"),
    ".jpg": ("image/jpeg", "JPEG", ".jpg"),
    ".jpeg": ("image/jpeg", "JPEG", ".jpg"),
    ".webp": ("image/webp", "WEBP", ".webp"),
}
REFERENCE_IMAGE_EXTENSIONS = frozenset(_REFERENCE_IMAGE_TYPE_BY_EXTENSION)
REFERENCE_IMAGE_CONTENT_TYPES = frozenset(
    content_type for content_type, _, _ in _REFERENCE_IMAGE_TYPE_BY_EXTENSION.values()
)

_HASH_CHUNK_BYTES = 1024 * 1024
_WINDOWS_FORBIDDEN_FILENAME_CHARS = frozenset('<>:"/\\|?*')
_WINDOWS_RESERVED_FILENAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{index}" for index in range(1, 10)}
    | {f"LPT{index}" for index in range(1, 10)}
)
# ponytail: one process-wide lock is enough for the desktop app; split by directory only if upload throughput matters.
_UPLOAD_STORE_LOCK = threading.Lock()


@dataclass(frozen=True)
class AssetProfile:
    name: str
    files: tuple[Path, ...]
    requirement: str = "optional"


@dataclass(frozen=True)
class RemoteAsset:
    repo_id: str | None = None
    filename: str | None = None
    url: str | None = None


ANIMA_T2I_ASSET_PROFILE = AssetProfile(
    name="anima-t2i",
    files=(
        Path("diffusion_models") / "anima-base-v1.0.safetensors",
        Path("text_encoders") / "qwen_3_06b_base.safetensors",
        Path("vae") / "qwen_image_vae.safetensors",
    ),
    requirement="required",
)


ANIMA_AESTHETIC_V1_1_ASSET_PROFILE = AssetProfile(
    name="anima-aesthetic-v1.1",
    files=(Path("diffusion_models") / PREFERRED_T2I_CHECKPOINT,),
    requirement="recommended",
)


FACE_DETAILER_DETECTOR_ASSET_PROFILE = AssetProfile(
    name="face-detailer-detectors",
    files=(
        Path("detectors") / "face_yolov8n.pt",
        Path("detectors") / "full_eyes_detect_v1.pt",
        Path("detectors") / "sam_b.pt",
    ),
)


SAM3_DETECTOR_ASSET_PROFILE = AssetProfile(
    name="sam3-detector",
    files=(Path("detectors") / "sam3.pt",),
)


MIN_DETECTOR_ASSET_BYTES = 1024

DETECTOR_REMOTE_ASSETS: dict[Path, RemoteAsset] = {
    Path("detectors") / "face_yolov8n.pt": RemoteAsset(
        repo_id="Bingsu/adetailer",
        filename="face_yolov8n.pt",
    ),
    Path("detectors") / "full_eyes_detect_v1.pt": RemoteAsset(
        repo_id="guon/hand-eyes",
        filename="full_eyes_detect_v1.pt",
    ),
    Path("detectors") / "sam_b.pt": RemoteAsset(
        url="https://github.com/ultralytics/assets/releases/download/v0.0.0/sam_b.pt",
    ),
    Path("detectors") / "sam3.pt": RemoteAsset(
        repo_id="facebook/sam3",
        filename="sam3.pt",
    ),
}


def asset_profiles() -> tuple[AssetProfile, ...]:
    return (
        ANIMA_T2I_ASSET_PROFILE,
        ANIMA_AESTHETIC_V1_1_ASSET_PROFILE,
        FACE_DETAILER_DETECTOR_ASSET_PROFILE,
        SAM3_DETECTOR_ASSET_PROFILE,
    )


def asset_profile(name: str) -> AssetProfile:
    for profile in asset_profiles():
        if name == profile.name:
            return profile
    raise ValueError(f"unknown asset profile: {name}")


def copy_asset_file(source_root: Path, dest_root: Path, relative_path: Path) -> Path:
    source_root = source_root.resolve()
    dest_root = dest_root.resolve()
    source = (source_root / relative_path).resolve()
    destination = _destination_for(dest_root, relative_path)

    source.relative_to(source_root)
    return _copy_asset_atomically(source, destination, relative_path)


def download_asset_file_from_huggingface(dest_root: Path, relative_path: Path) -> Path:
    if hf_hub_download is None:
        raise RuntimeError("huggingface_hub is required to download Anima model assets")

    dest_root = dest_root.resolve()
    destination = _destination_for(dest_root, relative_path)
    remote_path = (Path(ANIMA_T2I_HF_SUBFOLDER) / relative_path).as_posix()
    downloaded = Path(hf_hub_download(repo_id=ANIMA_T2I_HF_REPO, filename=remote_path))
    return _copy_asset_atomically(downloaded, destination, relative_path)


def download_asset_file_from_remote(dest_root: Path, relative_path: Path) -> Path:
    remote = DETECTOR_REMOTE_ASSETS.get(relative_path)
    if remote is None:
        raise ValueError(f"no remote download source is configured for {relative_path}")

    if remote.repo_id and remote.filename:
        if hf_hub_download is None:
            raise RuntimeError("huggingface_hub is required to download detector assets")
        downloaded = Path(hf_hub_download(repo_id=remote.repo_id, filename=remote.filename))
        destination = _destination_for(dest_root, relative_path)
        return _copy_asset_atomically(downloaded, destination, relative_path)

    if remote.url:
        destination = _destination_for(dest_root, relative_path)
        temporary = _temporary_asset_path(destination)
        try:
            with urllib.request.urlopen(remote.url) as response, temporary.open("wb") as output:
                shutil.copyfileobj(response, output)
            _validate_asset_file(temporary, relative_path)
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


def asset_file_is_ready(path: Path, relative_path: Path | None = None) -> bool:
    relative_path = relative_path or Path(path.name)
    try:
        if not path.is_file() or path.stat().st_size <= 0:
            return False
        if relative_path.parts and relative_path.parts[0] == "detectors":
            return path.stat().st_size >= MIN_DETECTOR_ASSET_BYTES
        if relative_path.suffix.lower() == ".safetensors":
            with safe_open(path, framework="pt", device="cpu") as handle:
                return bool(handle.keys())
    except (OSError, SafetensorError):
        return False
    return True


def required_t2i_model_files(paths: Any, checkpoint: str) -> tuple[Path, Path, Path]:
    checkpoint = normalize_checkpoint_path(checkpoint)
    return (
        paths.model_root / "diffusion_models" / Path(checkpoint),
        paths.model_root / "text_encoders" / "qwen_3_06b_base.safetensors",
        paths.model_root / "vae" / "qwen_image_vae.safetensors",
    )


def asset_profile_prepare_plan(profile: AssetProfile, paths: Any, *, source: str = "auto") -> dict[str, str | int | None]:
    if profile.name in {FACE_DETAILER_DETECTOR_ASSET_PROFILE.name, SAM3_DETECTOR_ASSET_PROFILE.name}:
        selected_source = _select_face_detailer_detector_source(profile, paths, source)
        if selected_source != "local":
            return {"source": selected_source, "size_bytes": None}
        source_paths = [
            _select_face_detector_source(paths, Path(relative_path.name)) / relative_path.name
            for relative_path in profile.files
        ]
    elif profile.name in {ANIMA_T2I_ASSET_PROFILE.name, ANIMA_AESTHETIC_V1_1_ASSET_PROFILE.name}:
        selected_source = _select_anima_t2i_source(profile, paths, source)
        if selected_source != "local":
            return {"source": selected_source, "size_bytes": None}
        source_paths = [paths.development_model_source / relative_path for relative_path in profile.files]
    else:
        selected_source = "local"
        source_paths = [paths.development_model_source / relative_path for relative_path in profile.files]
    return {"source": selected_source, "size_bytes": sum(path.stat().st_size for path in source_paths)}


def copy_asset_profile(profile: AssetProfile, paths: Any, *, source: str = "auto") -> tuple[str, list[Path]]:
    selected_source = str(asset_profile_prepare_plan(profile, paths, source=source)["source"])
    if profile.name in {FACE_DETAILER_DETECTOR_ASSET_PROFILE.name, SAM3_DETECTOR_ASSET_PROFILE.name}:
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
    if profile.name in {ANIMA_T2I_ASSET_PROFILE.name, ANIMA_AESTHETIC_V1_1_ASSET_PROFILE.name}:
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
    local_ready = all(
        asset_file_is_ready(paths.development_model_source / relative_path, relative_path)
        for relative_path in profile.files
    )
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
    return _copy_asset_atomically(source, destination, Path("loras") / source.name)


def store_reference_upload(
    temp_source: Path,
    filename: str,
    content_type: str,
    paths: Any,
) -> dict[str, Any]:
    safe_name, image_type = _reference_upload_type(filename)
    expected_content_type, expected_format, canonical_extension = image_type
    media_type = str(content_type or "").split(";", 1)[0].strip().lower()
    if media_type != expected_content_type:
        raise ValueError(f"reference Content-Type must be {expected_content_type}")

    source = Path(temp_source).resolve()
    digest, size_bytes = _hash_upload_file(
        source,
        maximum_bytes=MAX_REFERENCE_UPLOAD_BYTES,
        label="reference upload",
    )
    width, height = _validate_reference_image(source, expected_format)
    reference_root = (paths.input_root / "references").resolve()
    reference_root.mkdir(parents=True, exist_ok=True)
    destination = reference_root / f"{digest}{canonical_extension}"
    destination.relative_to(reference_root)
    with _UPLOAD_STORE_LOCK:
        deduplicated = _publish_upload_without_overwrite(
            source,
            destination,
            digest=digest,
            size_bytes=size_bytes,
            maximum_bytes=MAX_REFERENCE_UPLOAD_BYTES,
            label="reference upload",
        )
    return {
        "path": destination,
        "relative_path": destination.relative_to(Path(paths.project_root).resolve()).as_posix(),
        "filename": destination.name,
        "content_type": expected_content_type,
        "format": expected_format,
        "sha256": digest,
        "size_bytes": size_bytes,
        "width": width,
        "height": height,
        "deduplicated": deduplicated,
    }


def store_lora_upload(
    temp_source: Path,
    filename: str,
    content_type: str,
    paths: Any,
) -> dict[str, Any]:
    upload_name = PureWindowsPath(validate_lora_upload_filename(filename))

    source = Path(temp_source).resolve()
    digest, size_bytes = _hash_upload_file(
        source,
        maximum_bytes=MAX_LORA_UPLOAD_BYTES,
        label="LoRA upload",
    )
    _validate_nonempty_safetensors(source)
    lora_root = (paths.model_root / "loras").resolve()
    lora_root.mkdir(parents=True, exist_ok=True)
    base_destination = lora_root / f"{upload_name.stem}.safetensors"
    base_destination.relative_to(lora_root)

    with _UPLOAD_STORE_LOCK:
        destination = base_destination
        if os.path.lexists(destination) and not _stored_upload_matches(
            destination,
            digest=digest,
            size_bytes=size_bytes,
            maximum_bytes=MAX_LORA_UPLOAD_BYTES,
            label="LoRA upload",
        ):
            destination = lora_root / f"{upload_name.stem}-{digest[:12]}.safetensors"
            destination.relative_to(lora_root)
        deduplicated = _publish_upload_without_overwrite(
            source,
            destination,
            digest=digest,
            size_bytes=size_bytes,
            maximum_bytes=MAX_LORA_UPLOAD_BYTES,
            label="LoRA upload",
        )
    return {
        "path": destination,
        "relative_path": destination.relative_to(Path(paths.project_root).resolve()).as_posix(),
        "filename": destination.name,
        "content_type": str(content_type or "").split(";", 1)[0].strip().lower(),
        "sha256": digest,
        "size_bytes": size_bytes,
        "deduplicated": deduplicated,
    }


def reference_upload_content_type(filename: str) -> str:
    _, image_type = _reference_upload_type(filename)
    return image_type[0]


def validate_lora_upload_filename(filename: str) -> str:
    safe_name = _safe_windows_basename(filename)
    if PureWindowsPath(safe_name).suffix.lower() != ".safetensors":
        raise ValueError("LoRA filename must end in .safetensors")
    return safe_name


def _reference_upload_type(filename: str) -> tuple[str, tuple[str, str, str]]:
    safe_name = _safe_windows_basename(filename)
    image_type = _REFERENCE_IMAGE_TYPE_BY_EXTENSION.get(PureWindowsPath(safe_name).suffix.lower())
    if image_type is None:
        raise ValueError("reference filename must end in .png, .jpg, .jpeg, or .webp")
    return safe_name, image_type


def _safe_windows_basename(filename: str) -> str:
    if not isinstance(filename, str) or not filename or filename != filename.strip():
        raise ValueError("upload filename must be a safe Windows basename")
    path = PureWindowsPath(filename)
    try:
        component_length = len(filename.encode("utf-16-le", errors="strict")) // 2
    except UnicodeEncodeError:
        raise ValueError("upload filename must be valid Unicode text") from None
    if (
        path.name != filename
        or filename in {".", ".."}
        or filename.endswith((".", " "))
        or component_length > 255
        or any(ord(char) < 32 or char in _WINDOWS_FORBIDDEN_FILENAME_CHARS for char in filename)
        or filename.split(".", 1)[0].upper() in _WINDOWS_RESERVED_FILENAMES
    ):
        raise ValueError("upload filename must be a safe Windows basename")
    return filename


def _hash_upload_file(path: Path, *, maximum_bytes: int, label: str) -> tuple[str, int]:
    if not path.is_file():
        raise FileNotFoundError(path)
    digest = hashlib.sha256()
    size_bytes = 0
    with path.open("rb") as source:
        while chunk := source.read(_HASH_CHUNK_BYTES):
            size_bytes += len(chunk)
            if size_bytes > maximum_bytes:
                raise ValueError(f"{label} size cannot exceed {maximum_bytes} bytes")
            digest.update(chunk)
    if size_bytes == 0:
        raise ValueError(f"{label} cannot be empty")
    return digest.hexdigest(), size_bytes


def _validate_reference_image(path: Path, expected_format: str) -> tuple[int, int]:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(path) as image:
                dimensions = _validate_reference_image_header(image, expected_format)
                image.verify()
            with Image.open(path) as image:
                if _validate_reference_image_header(image, expected_format) != dimensions:
                    raise ValueError("reference image dimensions changed during validation")
                image.load()
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ValueError(f"reference image decompression limit exceeded: {exc}") from None
    except (EOFError, OSError, SyntaxError, UnidentifiedImageError) as exc:
        raise ValueError(f"reference image is invalid: {exc}") from None
    return dimensions


def _validate_reference_image_header(image: Image.Image, expected_format: str) -> tuple[int, int]:
    if image.format != expected_format:
        raise ValueError(f"reference image content must be {expected_format}")
    width, height = image.size
    if width <= 0 or height <= 0:
        raise ValueError("reference image dimensions must be positive")
    if width > MAX_REFERENCE_IMAGE_DIMENSION or height > MAX_REFERENCE_IMAGE_DIMENSION:
        raise ValueError(f"reference image dimension cannot exceed {MAX_REFERENCE_IMAGE_DIMENSION}")
    if width * height > MAX_REFERENCE_IMAGE_PIXELS:
        raise ValueError(f"reference image pixel count cannot exceed {MAX_REFERENCE_IMAGE_PIXELS}")
    if int(getattr(image, "n_frames", 1)) != 1:
        raise ValueError("reference image must be single-frame")
    return width, height


def _validate_nonempty_safetensors(path: Path) -> None:
    try:
        with safe_open(path, framework="pt", device="cpu") as handle:
            if not handle.keys():
                raise ValueError("LoRA upload safetensors must contain at least one tensor")
    except (OSError, SafetensorError) as exc:
        raise ValueError(f"LoRA upload is not valid safetensors: {exc}") from None


def _stored_upload_matches(
    path: Path,
    *,
    digest: str,
    size_bytes: int,
    maximum_bytes: int,
    label: str,
) -> bool:
    if path.is_symlink() or not path.is_file():
        return False
    try:
        stored_digest, stored_size = _hash_upload_file(path, maximum_bytes=maximum_bytes, label=label)
    except (OSError, ValueError):
        return False
    return stored_size == size_bytes and stored_digest == digest


def _publish_upload_without_overwrite(
    source: Path,
    destination: Path,
    *,
    digest: str,
    size_bytes: int,
    maximum_bytes: int,
    label: str,
) -> bool:
    if os.path.lexists(destination):
        if _stored_upload_matches(
            destination,
            digest=digest,
            size_bytes=size_bytes,
            maximum_bytes=maximum_bytes,
            label=label,
        ):
            return True
        raise RuntimeError(f"{label} destination conflict: {destination.name}")

    temporary = _temporary_asset_path(destination)
    try:
        shutil.copy2(source, temporary)
        copied_digest, copied_size = _hash_upload_file(
            temporary,
            maximum_bytes=maximum_bytes,
            label=label,
        )
        if copied_size != size_bytes or copied_digest != digest:
            raise RuntimeError(f"{label} changed while it was being stored")
        try:
            os.link(temporary, destination)
        except FileExistsError:
            if _stored_upload_matches(
                destination,
                digest=digest,
                size_bytes=size_bytes,
                maximum_bytes=maximum_bytes,
                label=label,
            ):
                return True
            raise RuntimeError(f"{label} destination conflict: {destination.name}") from None
        return False
    finally:
        if temporary.exists():
            temporary.unlink()


def _copy_asset_atomically(source: Path, destination: Path, relative_path: Path) -> Path:
    source = source.resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    temporary = _temporary_asset_path(destination)
    try:
        shutil.copy2(source, temporary)
        if temporary.stat().st_size != source.stat().st_size:
            raise RuntimeError(f"copied asset size mismatch: {relative_path}")
        _validate_asset_file(temporary, relative_path)
        temporary.replace(destination)
        return destination
    finally:
        if temporary.exists():
            temporary.unlink()


def _temporary_asset_path(destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        dir=destination.parent,
        prefix=f"{destination.name}.",
        suffix=".download",
        delete=False,
    ) as temporary:
        return Path(temporary.name)


def _validate_asset_file(path: Path, relative_path: Path) -> None:
    if not asset_file_is_ready(path, relative_path):
        raise RuntimeError(f"copied asset is invalid or incomplete: {relative_path}")


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

import hashlib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pytest
from PIL import Image
from safetensors.numpy import save_file

from anima_app.assets import (
    ANIMA_AESTHETIC_V1_1_ASSET_PROFILE,
    ANIMA_T2I_ASSET_PROFILE,
    ANIMA_T2I_HF_REPO,
    ANIMA_T2I_HF_SUBFOLDER,
    DETECTOR_REMOTE_ASSETS,
    FACE_DETAILER_DETECTOR_ASSET_PROFILE,
    MAX_LORA_UPLOAD_BYTES,
    MAX_REFERENCE_IMAGE_DIMENSION,
    MAX_REFERENCE_IMAGE_PIXELS,
    MAX_REFERENCE_UPLOAD_BYTES,
    REFERENCE_IMAGE_CONTENT_TYPES,
    REFERENCE_IMAGE_EXTENSIONS,
    SAM3_DETECTOR_ASSET_PROFILE,
    asset_file_is_ready,
    copy_asset_file,
    copy_asset_profile,
    download_asset_file_from_huggingface,
    import_lora_file,
    list_local_checkpoints,
    list_local_loras,
    reference_upload_content_type,
    store_lora_upload,
    store_reference_upload,
    validate_lora_upload_filename,
)
from anima_app.config import AppPaths


def _write_safetensors(path: Path, *, value: float = 1.0) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    save_file({"weight": np.asarray([value], dtype=np.float32)}, str(path))


def _write_image(path: Path, *, image_format: str = "PNG", size: tuple[int, int] = (8, 8)) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, "purple").save(path, format=image_format)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_anima_t2i_profile_lists_required_files():
    assert ANIMA_T2I_ASSET_PROFILE.name == "anima-t2i"
    assert ANIMA_T2I_ASSET_PROFILE.requirement == "required"
    assert ANIMA_T2I_HF_REPO == "circlestone-labs/Anima"
    assert ANIMA_T2I_HF_SUBFOLDER == "split_files"
    assert tuple(str(path) for path in ANIMA_T2I_ASSET_PROFILE.files) == (
        str(Path("diffusion_models") / "anima-base-v1.0.safetensors"),
        str(Path("text_encoders") / "qwen_3_06b_base.safetensors"),
        str(Path("vae") / "qwen_image_vae.safetensors"),
    )


def test_anima_aesthetic_v1_1_profile_lists_checkpoint():
    assert ANIMA_AESTHETIC_V1_1_ASSET_PROFILE.name == "anima-aesthetic-v1.1"
    assert ANIMA_AESTHETIC_V1_1_ASSET_PROFILE.requirement == "recommended"
    assert tuple(str(path) for path in ANIMA_AESTHETIC_V1_1_ASSET_PROFILE.files) == (
        str(Path("diffusion_models") / "anima-aesthetic-v1.1.safetensors"),
    )


def test_anima_aesthetic_v1_1_profile_downloads_when_local_source_is_missing(tmp_path, monkeypatch):
    paths = AppPaths(project_root=tmp_path / "app", development_model_source=tmp_path / "missing")
    downloaded: list[Path] = []

    def fake_download(dest_root, relative_path):
        target = dest_root / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"aesthetic")
        downloaded.append(relative_path)
        return target

    monkeypatch.setattr("anima_app.assets.download_asset_file_from_huggingface", fake_download)

    source, copied = copy_asset_profile(ANIMA_AESTHETIC_V1_1_ASSET_PROFILE, paths)

    assert source == "huggingface"
    assert downloaded == list(ANIMA_AESTHETIC_V1_1_ASSET_PROFILE.files)
    assert copied == [paths.model_root / relative_path for relative_path in ANIMA_AESTHETIC_V1_1_ASSET_PROFILE.files]


def test_face_detailer_detector_profile_names_required_detector_files():
    assert FACE_DETAILER_DETECTOR_ASSET_PROFILE.name == "face-detailer-detectors"
    assert FACE_DETAILER_DETECTOR_ASSET_PROFILE.requirement == "optional"
    assert tuple(str(path) for path in FACE_DETAILER_DETECTOR_ASSET_PROFILE.files) == (
        str(Path("detectors") / "face_yolov8n.pt"),
        str(Path("detectors") / "full_eyes_detect_v1.pt"),
        str(Path("detectors") / "sam_b.pt"),
    )
    assert set(FACE_DETAILER_DETECTOR_ASSET_PROFILE.files).issubset(DETECTOR_REMOTE_ASSETS)


def test_sam3_detector_profile_is_separate_gated_asset():
    assert SAM3_DETECTOR_ASSET_PROFILE.name == "sam3-detector"
    assert SAM3_DETECTOR_ASSET_PROFILE.requirement == "optional"
    assert tuple(str(path) for path in SAM3_DETECTOR_ASSET_PROFILE.files) == (str(Path("detectors") / "sam3.pt"),)
    assert DETECTOR_REMOTE_ASSETS[Path("detectors") / "sam3.pt"].repo_id == "facebook/sam3"


def test_copy_face_detailer_detector_profile_downloads_when_local_assets_are_missing(tmp_path, monkeypatch):
    paths = AppPaths(project_root=tmp_path / "app", face_detailer_detector_source=tmp_path / "missing_detectors")
    downloaded: list[Path] = []

    def fake_download(dest_root, relative_path):
        target = dest_root / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(relative_path.name.encode("utf-8") * 128)
        downloaded.append(relative_path)
        return target

    monkeypatch.setattr("anima_app.assets.download_asset_file_from_remote", fake_download)

    source, copied = copy_asset_profile(FACE_DETAILER_DETECTOR_ASSET_PROFILE, paths)

    assert source == "download"
    assert downloaded == list(FACE_DETAILER_DETECTOR_ASSET_PROFILE.files)
    assert copied == [paths.model_root / relative_path for relative_path in FACE_DETAILER_DETECTOR_ASSET_PROFILE.files]
    assert (paths.model_root / "detectors" / "sam_b.pt").is_file()


def test_copy_face_detailer_detector_profile_keeps_local_source_when_assets_exist(tmp_path):
    paths = AppPaths(project_root=tmp_path / "app", face_detailer_detector_source=tmp_path / "detectors")
    for relative_path in FACE_DETAILER_DETECTOR_ASSET_PROFILE.files:
        source = paths.face_detailer_detector_source / relative_path.name
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes(relative_path.name.encode("utf-8") * 128)

    source, copied = copy_asset_profile(FACE_DETAILER_DETECTOR_ASSET_PROFILE, paths)

    assert source == "local"
    assert copied == [paths.model_root / relative_path for relative_path in FACE_DETAILER_DETECTOR_ASSET_PROFILE.files]


def test_copy_asset_file_copies_inside_destination(tmp_path):
    source_root = tmp_path / "source"
    dest_root = tmp_path / "dest"
    relative_path = Path("vae") / "qwen_image_vae.safetensors"
    _write_safetensors(source_root / relative_path)

    copied = copy_asset_file(source_root, dest_root, relative_path)

    assert copied == (dest_root / relative_path).resolve()
    assert copied.read_bytes() == (source_root / relative_path).read_bytes()


def test_copy_asset_file_preserves_existing_destination_when_copy_fails(tmp_path, monkeypatch):
    source_root = tmp_path / "source"
    dest_root = tmp_path / "dest"
    relative_path = Path("models") / "asset.bin"
    source = source_root / relative_path
    destination = dest_root / relative_path
    source.parent.mkdir(parents=True)
    destination.parent.mkdir(parents=True)
    source.write_bytes(b"replacement")
    destination.write_bytes(b"stable")

    def interrupted_copy(source_path, destination_path):
        Path(destination_path).write_bytes(b"partial")
        raise OSError("copy interrupted")

    monkeypatch.setattr("anima_app.assets.shutil.copy2", interrupted_copy)

    with pytest.raises(OSError, match="copy interrupted"):
        copy_asset_file(source_root, dest_root, relative_path)

    assert destination.read_bytes() == b"stable"
    assert not list(destination.parent.glob(f"{destination.name}.*.download"))


def test_copy_asset_file_preserves_existing_destination_when_validation_fails(tmp_path):
    source_root = tmp_path / "source"
    dest_root = tmp_path / "dest"
    relative_path = Path("vae") / "broken.safetensors"
    source = source_root / relative_path
    destination = dest_root / relative_path
    source.parent.mkdir(parents=True)
    destination.parent.mkdir(parents=True)
    source.write_bytes(b"not-a-safetensors-file")
    destination.write_bytes(b"stable")

    with pytest.raises(RuntimeError, match="invalid or incomplete"):
        copy_asset_file(source_root, dest_root, relative_path)

    assert destination.read_bytes() == b"stable"
    assert not list(destination.parent.glob(f"{destination.name}.*.download"))


def test_asset_file_is_ready_rejects_empty_safetensors_container(tmp_path):
    path = tmp_path / "empty.safetensors"
    save_file({}, str(path))

    assert asset_file_is_ready(path) is False


def test_download_asset_file_from_huggingface_writes_profile_path(tmp_path, monkeypatch):
    calls = []

    def fake_hf_hub_download(*, repo_id, filename):
        calls.append(
            {
                "repo_id": repo_id,
                "filename": filename,
            }
        )
        target = tmp_path / "hf-cache" / filename
        target.parent.mkdir(parents=True, exist_ok=True)
        _write_safetensors(target)
        return str(target)

    monkeypatch.setattr("anima_app.assets.hf_hub_download", fake_hf_hub_download)

    copied = download_asset_file_from_huggingface(
        tmp_path / "models",
        Path("vae") / "qwen_image_vae.safetensors",
    )

    assert copied == (tmp_path / "models" / "vae" / "qwen_image_vae.safetensors").resolve()
    assert copied.read_bytes() == (tmp_path / "hf-cache" / "split_files" / "vae" / "qwen_image_vae.safetensors").read_bytes()
    assert calls == [
        {
            "repo_id": "circlestone-labs/Anima",
            "filename": "split_files/vae/qwen_image_vae.safetensors",
        }
    ]


def test_import_lora_file_copies_safetensors_into_project_loras(tmp_path):
    paths = AppPaths(project_root=tmp_path / "app")
    source = tmp_path / "source" / "style.safetensors"
    _write_safetensors(source)

    imported = import_lora_file(source, paths)

    assert imported == paths.model_root / "loras" / "style.safetensors"
    assert imported.read_bytes() == source.read_bytes()
    assert list_local_loras(paths) == [{"relative_path": "style.safetensors", "size_bytes": source.stat().st_size}]


def test_list_local_checkpoints_lists_diffusion_safetensors(tmp_path):
    paths = AppPaths(project_root=tmp_path / "app")
    default_checkpoint = paths.model_root / "diffusion_models" / "anima-base-v1.0.safetensors"
    nested_checkpoint = paths.model_root / "diffusion_models" / "variants" / "anima-alt.safetensors"
    ignored = paths.model_root / "diffusion_models" / "notes.txt"
    nested_checkpoint.parent.mkdir(parents=True)
    default_checkpoint.parent.mkdir(parents=True, exist_ok=True)
    default_checkpoint.write_bytes(b"base")
    nested_checkpoint.write_bytes(b"alternate")
    ignored.write_text("not a checkpoint", encoding="utf-8")

    assert list_local_checkpoints(paths) == [
        {"relative_path": "anima-base-v1.0.safetensors", "size_bytes": 4},
        {"relative_path": "variants/anima-alt.safetensors", "size_bytes": 9},
    ]


def test_import_lora_file_rejects_non_safetensors(tmp_path):
    paths = AppPaths(project_root=tmp_path / "app")
    source = tmp_path / "bad.ckpt"
    source.write_bytes(b"bad")

    with pytest.raises(ValueError, match=".safetensors"):
        import_lora_file(source, paths)


def test_upload_storage_limits_and_reference_allowlists_are_explicit():
    assert MAX_REFERENCE_UPLOAD_BYTES == 64 * 1024 * 1024
    assert MAX_REFERENCE_IMAGE_DIMENSION == 8192
    assert MAX_REFERENCE_IMAGE_PIXELS == 16_777_216
    assert MAX_LORA_UPLOAD_BYTES == 1024 * 1024 * 1024
    assert REFERENCE_IMAGE_EXTENSIONS == frozenset({".png", ".jpg", ".jpeg", ".webp"})
    assert REFERENCE_IMAGE_CONTENT_TYPES == frozenset({"image/png", "image/jpeg", "image/webp"})


def test_upload_filename_metadata_can_be_validated_before_receiving_a_body():
    assert reference_upload_content_type("portrait.jpeg") == "image/jpeg"
    assert validate_lora_upload_filename("soft-style.safetensors") == "soft-style.safetensors"
    with pytest.raises(ValueError, match="reference filename"):
        reference_upload_content_type("portrait.txt")
    with pytest.raises(ValueError, match="LoRA filename"):
        validate_lora_upload_filename("soft-style.ckpt")


@pytest.mark.parametrize(
    ("filename", "content_type", "image_format", "canonical_extension"),
    [
        ("portrait.png", "image/png", "PNG", ".png"),
        ("portrait.jpeg", "image/jpeg", "JPEG", ".jpg"),
        ("portrait.webp", "image/webp", "WEBP", ".webp"),
    ],
)
def test_store_reference_upload_validates_and_content_addresses_images(
    tmp_path,
    filename,
    content_type,
    image_format,
    canonical_extension,
):
    paths = AppPaths(project_root=tmp_path / "app")
    source = tmp_path / "upload.tmp"
    _write_image(source, image_format=image_format)
    digest = _sha256(source)

    stored = store_reference_upload(source, filename, content_type, paths)
    duplicate = store_reference_upload(source, filename, content_type, paths)

    expected = paths.input_root / "references" / f"{digest}{canonical_extension}"
    assert stored["path"] == expected.resolve()
    assert stored["relative_path"] == f"inputs/references/{digest}{canonical_extension}"
    assert stored["sha256"] == digest
    assert stored["size_bytes"] == source.stat().st_size
    assert stored["width"] == 8
    assert stored["height"] == 8
    assert duplicate["path"] == stored["path"]
    assert duplicate["deduplicated"] is True
    assert source.is_file()
    assert expected.read_bytes() == source.read_bytes()


@pytest.mark.parametrize(
    ("filename", "content_type", "image_format"),
    [
        ("portrait.jpg", "image/jpeg", "PNG"),
        ("portrait.png", "image/jpeg", "PNG"),
        ("portrait.gif", "image/gif", "PNG"),
    ],
)
def test_store_reference_upload_rejects_extension_mime_or_format_mismatch(
    tmp_path,
    filename,
    content_type,
    image_format,
):
    source = tmp_path / "upload.tmp"
    _write_image(source, image_format=image_format)

    with pytest.raises(ValueError):
        store_reference_upload(source, filename, content_type, AppPaths(project_root=tmp_path / "app"))


@pytest.mark.parametrize(
    "filename",
    ["../portrait.png", r"C:\portrait.png", "CON.png", "bad?.png", "portrait.png."],
)
def test_store_reference_upload_rejects_unsafe_windows_basename(tmp_path, filename):
    source = tmp_path / "upload.tmp"
    _write_image(source)

    with pytest.raises(ValueError, match="filename"):
        store_reference_upload(source, filename, "image/png", AppPaths(project_root=tmp_path / "app"))


def test_store_reference_upload_enforces_byte_dimension_and_pixel_limits(tmp_path, monkeypatch):
    paths = AppPaths(project_root=tmp_path / "app")
    source = tmp_path / "upload.tmp"
    _write_image(source, size=(10, 2))

    monkeypatch.setattr("anima_app.assets.MAX_REFERENCE_UPLOAD_BYTES", source.stat().st_size - 1)
    with pytest.raises(ValueError, match="size"):
        store_reference_upload(source, "portrait.png", "image/png", paths)

    monkeypatch.setattr("anima_app.assets.MAX_REFERENCE_UPLOAD_BYTES", MAX_REFERENCE_UPLOAD_BYTES)
    monkeypatch.setattr("anima_app.assets.MAX_REFERENCE_IMAGE_DIMENSION", 8)
    with pytest.raises(ValueError, match="dimension"):
        store_reference_upload(source, "portrait.png", "image/png", paths)

    monkeypatch.setattr("anima_app.assets.MAX_REFERENCE_IMAGE_DIMENSION", MAX_REFERENCE_IMAGE_DIMENSION)
    monkeypatch.setattr("anima_app.assets.MAX_REFERENCE_IMAGE_PIXELS", 19)
    with pytest.raises(ValueError, match="pixel"):
        store_reference_upload(source, "portrait.png", "image/png", paths)


def test_store_reference_upload_rejects_animated_image(tmp_path):
    source = tmp_path / "animated.png"
    source.parent.mkdir(parents=True, exist_ok=True)
    frames = [Image.new("RGB", (4, 4), color) for color in ("red", "blue")]
    frames[0].save(source, format="PNG", save_all=True, append_images=frames[1:], duration=10)

    with pytest.raises(ValueError, match="single-frame"):
        store_reference_upload(source, "animated.png", "image/png", AppPaths(project_root=tmp_path / "app"))


@pytest.mark.parametrize("pillow_pixel_limit", [8, 1])
def test_store_reference_upload_rejects_pillow_decompression_warning_or_error(
    tmp_path,
    monkeypatch,
    pillow_pixel_limit,
):
    source = tmp_path / "upload.tmp"
    _write_image(source, size=(4, 4))
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", pillow_pixel_limit)

    with pytest.raises(ValueError, match="decompression"):
        store_reference_upload(source, "portrait.png", "image/png", AppPaths(project_root=tmp_path / "app"))


def test_store_reference_upload_never_overwrites_content_address_conflict(tmp_path):
    paths = AppPaths(project_root=tmp_path / "app")
    source = tmp_path / "upload.tmp"
    _write_image(source)
    destination = paths.input_root / "references" / f"{_sha256(source)}.png"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(b"existing")

    with pytest.raises(RuntimeError, match="conflict"):
        store_reference_upload(source, "portrait.png", "image/png", paths)

    assert destination.read_bytes() == b"existing"


def test_store_lora_upload_reuses_hash_and_suffixes_name_collision(tmp_path):
    paths = AppPaths(project_root=tmp_path / "app")
    first_source = tmp_path / "first.tmp"
    second_source = tmp_path / "second.tmp"
    _write_safetensors(first_source, value=1.0)
    _write_safetensors(second_source, value=2.0)

    first = store_lora_upload(first_source, "style.safetensors", "application/octet-stream", paths)
    duplicate = store_lora_upload(first_source, "style.safetensors", "application/octet-stream", paths)
    second = store_lora_upload(second_source, "style.safetensors", "application/octet-stream", paths)

    assert first["relative_path"] == "models/loras/style.safetensors"
    assert duplicate["path"] == first["path"]
    assert duplicate["deduplicated"] is True
    assert second["relative_path"] == f"models/loras/style-{_sha256(second_source)[:12]}.safetensors"
    assert first["path"].read_bytes() == first_source.read_bytes()
    assert second["path"].read_bytes() == second_source.read_bytes()
    assert first_source.is_file() and second_source.is_file()


@pytest.mark.parametrize(
    "filename",
    ["../style.safetensors", r"C:\style.safetensors", "NUL.safetensors", "bad*.safetensors", "style.ckpt"],
)
def test_store_lora_upload_rejects_unsafe_or_wrong_extension(tmp_path, filename):
    source = tmp_path / "upload.tmp"
    _write_safetensors(source)

    with pytest.raises(ValueError):
        store_lora_upload(source, filename, "application/octet-stream", AppPaths(project_root=tmp_path / "app"))


def test_store_lora_upload_rejects_empty_invalid_and_oversized_files(tmp_path, monkeypatch):
    paths = AppPaths(project_root=tmp_path / "app")
    empty = tmp_path / "empty.tmp"
    invalid = tmp_path / "invalid.tmp"
    valid = tmp_path / "valid.tmp"
    empty.write_bytes(b"")
    invalid.write_bytes(b"not safetensors")
    _write_safetensors(valid)

    with pytest.raises(ValueError, match="empty"):
        store_lora_upload(empty, "empty.safetensors", "application/octet-stream", paths)
    with pytest.raises(ValueError, match="safetensors"):
        store_lora_upload(invalid, "invalid.safetensors", "application/octet-stream", paths)

    monkeypatch.setattr("anima_app.assets.MAX_LORA_UPLOAD_BYTES", valid.stat().st_size - 1)
    with pytest.raises(ValueError, match="size"):
        store_lora_upload(valid, "large.safetensors", "application/octet-stream", paths)


def test_store_lora_upload_serializes_same_name_concurrency_without_overwrite(tmp_path):
    paths = AppPaths(project_root=tmp_path / "app")
    sources = [tmp_path / "first.tmp", tmp_path / "second.tmp"]
    _write_safetensors(sources[0], value=1.0)
    _write_safetensors(sources[1], value=2.0)

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(
                lambda source: store_lora_upload(source, "style.safetensors", "application/octet-stream", paths),
                sources,
            )
        )

    assert len({result["path"] for result in results}) == 2
    assert sum(result["path"].name == "style.safetensors" for result in results) == 1
    for source, result in zip(sources, results, strict=True):
        assert result["sha256"] == _sha256(source)
        assert result["path"].read_bytes() == source.read_bytes()

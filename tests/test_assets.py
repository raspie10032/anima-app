from pathlib import Path

import pytest

from anima_app.assets import (
    ANIMA_T2I_ASSET_PROFILE,
    ANIMA_T2I_HF_REPO,
    ANIMA_T2I_HF_SUBFOLDER,
    FACE_DETAILER_DETECTOR_ASSET_PROFILE,
    copy_asset_file,
    download_asset_file_from_huggingface,
    import_lora_file,
    list_local_checkpoints,
    list_local_loras,
    scan_model_source,
)
from anima_app.config import AppPaths


def test_anima_t2i_profile_lists_required_files():
    assert ANIMA_T2I_ASSET_PROFILE.name == "anima-t2i"
    assert ANIMA_T2I_HF_REPO == "circlestone-labs/Anima"
    assert ANIMA_T2I_HF_SUBFOLDER == "split_files"
    assert tuple(str(path) for path in ANIMA_T2I_ASSET_PROFILE.files) == (
        str(Path("diffusion_models") / "anima-base-v1.0.safetensors"),
        str(Path("text_encoders") / "qwen_3_06b_base.safetensors"),
        str(Path("vae") / "qwen_image_vae.safetensors"),
    )


def test_face_detailer_detector_profile_names_required_detector_files():
    assert FACE_DETAILER_DETECTOR_ASSET_PROFILE.name == "face-detailer-detectors"
    assert tuple(str(path) for path in FACE_DETAILER_DETECTOR_ASSET_PROFILE.files) == (
        str(Path("detectors") / "face_yolov8n.pt"),
        str(Path("detectors") / "full_eyes_detect_v1.pt"),
        str(Path("detectors") / "sam_b.pt"),
    )


def test_scan_model_source_reports_known_folders(tmp_path):
    (tmp_path / "diffusion_models").mkdir()
    (tmp_path / "vae").mkdir()
    (tmp_path / "diffusion_models" / "model.safetensors").write_bytes(b"model")

    inventory = scan_model_source(tmp_path)

    assert inventory.source_root == tmp_path.resolve()
    assert "diffusion_models" in inventory.folders
    assert "vae" in inventory.folders
    assert inventory.files[0].relative_path == Path("diffusion_models") / "model.safetensors"
    assert inventory.files[0].size_bytes == 5


def test_copy_asset_file_copies_inside_destination(tmp_path):
    source_root = tmp_path / "source"
    dest_root = tmp_path / "dest"
    relative_path = Path("vae") / "qwen_image_vae.safetensors"
    (source_root / relative_path.parent).mkdir(parents=True)
    (source_root / relative_path).write_bytes(b"vae")

    copied = copy_asset_file(source_root, dest_root, relative_path)

    assert copied == (dest_root / relative_path).resolve()
    assert copied.read_bytes() == b"vae"


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
        target.write_bytes(b"downloaded")
        return str(target)

    monkeypatch.setattr("anima_app.assets.hf_hub_download", fake_hf_hub_download)

    copied = download_asset_file_from_huggingface(
        tmp_path / "models",
        Path("vae") / "qwen_image_vae.safetensors",
    )

    assert copied == (tmp_path / "models" / "vae" / "qwen_image_vae.safetensors").resolve()
    assert copied.read_bytes() == b"downloaded"
    assert calls == [
        {
            "repo_id": "circlestone-labs/Anima",
            "filename": "split_files/vae/qwen_image_vae.safetensors",
        }
    ]


def test_import_lora_file_copies_safetensors_into_project_loras(tmp_path):
    paths = AppPaths(project_root=tmp_path / "app")
    source = tmp_path / "source" / "style.safetensors"
    source.parent.mkdir()
    source.write_bytes(b"lora")

    imported = import_lora_file(source, paths)

    assert imported == paths.model_root / "loras" / "style.safetensors"
    assert imported.read_bytes() == b"lora"
    assert list_local_loras(paths) == [{"relative_path": "style.safetensors", "size_bytes": 4}]


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

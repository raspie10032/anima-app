import pytest

from anima_app.comfy_runtime import NativeAttentionImportBlocker, _model_folder_paths, comfy_runtime_root, project_root, vendor_root


def test_runtime_paths_point_at_project_vendor_tree():
    root = project_root()

    assert (root / "pyproject.toml").is_file()
    assert vendor_root() == root / "vendor"
    assert comfy_runtime_root() == root / "vendor" / "anima_runtime"


def test_model_folder_paths_are_project_local(tmp_path):
    folders = _model_folder_paths(tmp_path / "models")

    assert folders["diffusion_models"] == tmp_path / "models" / "diffusion_models"
    assert folders["unet"] == tmp_path / "models" / "diffusion_models"
    assert folders["text_encoders"] == tmp_path / "models" / "text_encoders"
    assert folders["vae"] == tmp_path / "models" / "vae"
    assert folders["loras"] == tmp_path / "models" / "loras"
    assert folders["diffusion_models"].is_relative_to(tmp_path / "models")


def test_native_attention_import_blocker_blocks_unstable_roots():
    blocker = NativeAttentionImportBlocker()

    with pytest.raises(ModuleNotFoundError, match="disabled for Anima APP"):
        blocker.find_spec("xformers.ops")

    assert blocker.find_spec("json") is None

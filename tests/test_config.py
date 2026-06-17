from pathlib import Path

from anima_app.config import AppPaths, default_paths


def test_default_paths_point_at_anima_app_workspace():
    paths = default_paths()

    assert paths.project_root == Path(r"C:\Users\seine\Documents\Anima APP")
    assert paths.model_root == paths.project_root / "models"
    assert paths.output_root == paths.project_root / "outputs"
    assert paths.image_root == paths.output_root / "images"
    assert paths.manifest_root == paths.output_root / "manifests"
    assert paths.input_root == paths.project_root / "inputs"


def test_development_model_source_is_comfyui_sage_models():
    paths = AppPaths()

    assert paths.development_model_source == Path(r"E:\ComfyUI_sage\ComfyUI\models")

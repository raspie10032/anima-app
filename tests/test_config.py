import os

from anima_app.config import AppPaths, default_paths


def test_default_paths_point_at_current_checkout(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    paths = default_paths()

    assert paths.project_root == tmp_path
    assert paths.model_root == paths.project_root / "models"
    assert paths.output_root == paths.project_root / "outputs"
    assert paths.image_root == paths.output_root / "images"
    assert paths.manifest_root == paths.output_root / "manifests"
    assert paths.input_root == paths.project_root / "inputs"
    assert paths.development_model_source == tmp_path / "external_models"
    assert paths.face_detailer_detector_source == tmp_path / "external_detectors"
    assert paths.face_detailer_detector_fallback_sources == ()


def test_default_paths_can_be_configured_from_environment(monkeypatch, tmp_path):
    project_root = tmp_path / "project"
    model_source = tmp_path / "model_source"
    detector_source = tmp_path / "detectors"
    fallback_a = tmp_path / "fallback_a"
    fallback_b = tmp_path / "fallback_b"

    monkeypatch.setenv("ANIMA_APP_ROOT", str(project_root))
    monkeypatch.setenv("ANIMA_APP_MODEL_SOURCE", str(model_source))
    monkeypatch.setenv("ANIMA_APP_FACE_DETECTOR_SOURCE", str(detector_source))
    monkeypatch.setenv("ANIMA_APP_FACE_DETECTOR_FALLBACKS", str(fallback_a) + os.pathsep + str(fallback_b))

    paths = AppPaths()

    assert paths.project_root == project_root
    assert paths.development_model_source == model_source
    assert paths.face_detailer_detector_source == detector_source
    assert paths.face_detailer_detector_fallback_sources == (fallback_a, fallback_b)

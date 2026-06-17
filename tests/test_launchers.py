from pathlib import Path


def test_windows_gui_launcher_uses_dynamic_real_generation_server():
    launcher = Path("Run-AnimaAPP-GUI.cmd")

    assert launcher.is_file()
    content = launcher.read_text(encoding="utf-8")
    assert "PYTHONPATH=%APP_ROOT%\\src" in content
    assert "CUDA_VISIBLE_DEVICES=0" in content
    assert "python -m anima_app.cli serve" in content
    assert "--port 0" in content
    assert "--dry-run-default" not in content
    assert "--open" in content


def test_windows_dry_run_gui_launcher_keeps_safe_manifest_only_mode():
    launcher = Path("Run-AnimaAPP-GUI-DryRun.cmd")

    assert launcher.is_file()
    content = launcher.read_text(encoding="utf-8")
    assert "PYTHONPATH=%APP_ROOT%\\src" in content
    assert "CUDA_VISIBLE_DEVICES=0" in content
    assert "python -m anima_app.cli serve" in content
    assert "--port 0" in content
    assert "--dry-run-default" in content
    assert "--open" in content

from pathlib import Path


def test_windows_gui_launcher_uses_dynamic_real_generation_server():
    launcher = Path("Run-AnimaAPP-GUI.cmd")

    assert launcher.is_file()
    content = launcher.read_text(encoding="utf-8")
    assert "PYTHONPATH=%APP_ROOT%\\src" in content
    assert "set \"CUDA_VISIBLE_DEVICES=0\"" not in content
    assert "if defined CUDA_VISIBLE_DEVICES" in content
    assert "python -m anima_app.cli serve" in content
    assert "--port 0" in content
    assert "--dry-run-default" not in content
    assert "--open" in content

import os
import subprocess
from pathlib import Path

import pytest


def test_windows_gui_launcher_uses_dynamic_real_generation_server():
    launcher = Path("Run-AnimaAPP-GUI.cmd")

    assert launcher.is_file()
    content = launcher.read_text(encoding="utf-8")
    assert "PYTHONPATH=%APP_ROOT%\\src" in content
    assert 'if not defined ANIMA_APP_CUDA_VISIBLE_DEVICES set "ANIMA_APP_CUDA_VISIBLE_DEVICES=0"' in content
    assert 'set "CUDA_VISIBLE_DEVICES=%ANIMA_APP_CUDA_VISIBLE_DEVICES%"' in content
    assert content.index("ANIMA_APP_CUDA_VISIBLE_DEVICES=0") < content.index("python -m anima_app.cli serve")
    assert content.index("CUDA_VISIBLE_DEVICES=%ANIMA_APP_CUDA_VISIBLE_DEVICES%") < content.index("python -m anima_app.cli serve")
    assert "python -m anima_app.cli serve" in content
    assert "--port 0" in content
    assert "--dry-run-default" not in content
    assert "--open" in content
    assert 'set "APP_EXIT_CODE=%ERRORLEVEL%"' in content
    assert 'if "%APP_EXIT_CODE%"=="0" exit /b 0' in content
    assert "Anima APP failed to start" in content
    assert "pause >nul" in content
    assert "exit /b %APP_EXIT_CODE%" in content


def test_package_dry_run_script_checks_wheel_gui_and_source_runtime_boundary():
    script = Path("scripts/package_dry_run.py")

    assert script.is_file()
    content = script.read_text(encoding="utf-8")
    assert '"pip",' in content
    assert '"wheel",' in content
    assert "anima_app.server" in content
    assert "static/app.js" in content
    assert "vendor/anima_runtime/comfy/ldm/anima/model.py" in content


@pytest.mark.skipif(os.name != "nt", reason="Windows batch launcher")
def test_windows_gui_launcher_preserves_missing_python_failure(tmp_path):
    environment = os.environ.copy()
    environment["PATH"] = str(tmp_path)

    completed = subprocess.run(
        ["cmd.exe", "/d", "/c", "call", str(Path("Run-AnimaAPP-GUI.cmd").resolve())],
        input="\n",
        text=True,
        capture_output=True,
        env=environment,
        timeout=10,
        check=False,
    )

    assert completed.returncode != 0
    assert "Anima APP failed to start" in completed.stdout

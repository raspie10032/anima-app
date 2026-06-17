import json
import subprocess
import zipfile
from pathlib import Path

from scripts.package_dry_run import (
    build_standalone_layout_plan,
    inspect_wheel,
    packaging_checks_pass,
    run_package_dry_run,
)


def make_package_tree(root: Path) -> None:
    files = {
        "pyproject.toml": """
[build-system]
requires = ["setuptools>=69", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "anima-app"
version = "0.1.0"
readme = "README.md"

[project.scripts]
anima-app = "anima_app.cli:console_main"
""",
        "README.md": "# Anima APP\n",
        "NOTICE.md": "# Notice\n",
        "Run-AnimaAPP-GUI.cmd": "python -m anima_app.cli serve\n",
        "docs/ACCEPTANCE.md": "# Acceptance\n",
        "docs/REFERENCES.md": "# References\n",
        "docs/RELEASE_CHECKLIST.md": "# Release Checklist\n",
        "scripts/smoke_anima_app.py": "print('smoke')\n",
        "scripts/release_smoke.py": "print('release')\n",
        "scripts/package_dry_run.py": "print('package')\n",
        "src/anima_app/__init__.py": "",
        "src/anima_app/cli.py": "def console_main():\n    return 0\n",
        "vendor/anima_runtime/.keep": "",
        "vendor/python_packages/.keep": "",
        "wildcards/sample.txt": "soft light\n",
        "models/private.safetensors": "",
        "outputs/images/old.png": "",
        "inputs/reference.png": "",
    }
    for relative, content in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def make_wheel(path: Path) -> None:
    with zipfile.ZipFile(path, "w") as wheel:
        wheel.writestr("anima_app/__init__.py", "")
        wheel.writestr("anima_app/cli.py", "def console_main():\n    return 0\n")
        wheel.writestr("anima_app-0.1.0.dist-info/METADATA", "Name: anima-app\n")
        wheel.writestr(
            "anima_app-0.1.0.dist-info/entry_points.txt",
            "[console_scripts]\nanima-app=anima_app.cli:console_main\n",
        )


def test_standalone_layout_plan_includes_runtime_and_excludes_local_artifacts(tmp_path):
    make_package_tree(tmp_path)

    plan = build_standalone_layout_plan(tmp_path)

    assert "src" in plan["include_roots"]
    assert "vendor/anima_runtime" in plan["include_roots"]
    assert "vendor/python_packages" in plan["include_roots"]
    assert "wildcards" in plan["include_roots"]
    assert "Run-AnimaAPP-GUI.cmd" in plan["include_roots"]
    assert "Run-AnimaAPP-GUI-DryRun.cmd" not in plan["include_roots"]
    assert "Run-AnimaAPP-ReleaseSmoke.cmd" not in plan["include_roots"]
    assert "models" in plan["excluded_roots"]
    assert "outputs" in plan["excluded_roots"]
    assert "inputs" in plan["excluded_roots"]
    assert plan["ok"] is True


def test_inspect_wheel_requires_package_metadata_and_entrypoint(tmp_path):
    wheel_path = tmp_path / "anima_app-0.1.0-py3-none-any.whl"
    make_wheel(wheel_path)

    checks = inspect_wheel(wheel_path)

    assert packaging_checks_pass(checks) is True
    by_key = {check["key"]: check for check in checks}
    assert by_key["package_module"]["ok"] is True
    assert by_key["metadata"]["ok"] is True
    assert by_key["console_entrypoint"]["ok"] is True
    assert by_key["model_artifacts_excluded"]["ok"] is True


def test_run_package_dry_run_builds_wheel_and_writes_report(tmp_path):
    make_package_tree(tmp_path)
    calls = []

    def fake_runner(argv, cwd, env, text, capture_output, timeout):
        calls.append({"argv": list(argv), "cwd": cwd, "env": env})
        wheel_dir = Path(argv[argv.index("--wheel-dir") + 1])
        wheel_dir.mkdir(parents=True, exist_ok=True)
        make_wheel(wheel_dir / "anima_app-0.1.0-py3-none-any.whl")
        return subprocess.CompletedProcess(argv, 0, stdout="built wheel\n", stderr="")

    exit_code, payload = run_package_dry_run(project_root=tmp_path, runner=fake_runner)

    assert exit_code == 0
    assert payload["status"] == "passed"
    assert calls[0]["argv"][1:5] == ["-m", "pip", "wheel", "."]
    assert "--no-deps" in calls[0]["argv"]
    assert "--no-build-isolation" in calls[0]["argv"]
    report_path = Path(payload["report_path"])
    assert report_path.is_file()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["status"] == "passed"
    assert Path(payload["wheel_path"]).name == "anima_app-0.1.0-py3-none-any.whl"


def test_run_package_dry_run_fails_when_wheel_build_fails(tmp_path):
    make_package_tree(tmp_path)

    def fake_runner(argv, cwd, env, text, capture_output, timeout):
        return subprocess.CompletedProcess(argv, 1, stdout="", stderr="build failed")

    exit_code, payload = run_package_dry_run(project_root=tmp_path, runner=fake_runner)

    assert exit_code == 1
    assert payload["status"] == "failed"
    assert payload["wheel_command"]["ok"] is False
    assert payload["wheel_checks"] == []

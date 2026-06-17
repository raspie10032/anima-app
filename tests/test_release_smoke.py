import os
import subprocess
from pathlib import Path

from scripts.release_smoke import collect_static_checks, release_checks_pass, run_release_smoke


def make_release_tree(root: Path) -> None:
    files = {
        "pyproject.toml": "[project]\nname = \"anima-app\"\n",
        "README.md": "# Anima APP\n",
        "Run-AnimaAPP-GUI.cmd": "python -m anima_app.cli serve\n",
        "Run-AnimaAPP-GUI-DryRun.cmd": "python -m anima_app.cli serve --dry-run-default\n",
        "Run-AnimaAPP-ReleaseSmoke.cmd": "python scripts\\release_smoke.py\n",
        ".gitignore": "/models/\n/outputs/\n/inputs/\n",
        "docs/ACCEPTANCE.md": "# Acceptance\n",
        "docs/PACKAGING_PLAN.md": "# Packaging Plan\n",
        "docs/RELEASE_CHECKLIST.md": "# Release Checklist\n",
        "docs/REFERENCES.md": "# References\n",
        "scripts/smoke_anima_app.py": "print('smoke')\n",
        "scripts/release_smoke.py": "print('release')\n",
        "scripts/package_dry_run.py": "print('package')\n",
        "src/anima_app/__init__.py": "",
        "vendor/anima_runtime/.keep": "",
    }
    for relative, content in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def checks_by_key(checks):
    return {check["key"]: check for check in checks}


def test_collect_static_checks_accepts_source_checkout_tree(tmp_path):
    make_release_tree(tmp_path)

    checks = collect_static_checks(tmp_path)
    by_key = checks_by_key(checks)

    assert release_checks_pass(checks) is True
    assert by_key["pyproject"]["ok"] is True
    assert by_key["readme"]["ok"] is True
    assert by_key["gui_launcher"]["ok"] is True
    assert by_key["dry_run_gui_launcher"]["ok"] is True
    assert by_key["release_smoke_launcher"]["ok"] is True
    assert by_key["package_dry_run_script"]["ok"] is True
    assert by_key["packaging_plan"]["ok"] is True
    assert by_key["release_checklist"]["ok"] is True
    assert by_key["vendored_runtime"]["ok"] is True
    assert by_key["artifact_gitignore"]["ok"] is True


def test_collect_static_checks_reports_missing_release_files(tmp_path):
    make_release_tree(tmp_path)
    (tmp_path / "Run-AnimaAPP-ReleaseSmoke.cmd").unlink()

    checks = collect_static_checks(tmp_path)
    by_key = checks_by_key(checks)

    assert release_checks_pass(checks) is False
    assert by_key["release_smoke_launcher"]["ok"] is False
    assert "Run-AnimaAPP-ReleaseSmoke.cmd" in by_key["release_smoke_launcher"]["path"]


def test_run_release_smoke_runs_cpu_safe_commands_with_pythonpath(tmp_path):
    make_release_tree(tmp_path)
    calls = []

    def fake_runner(argv, cwd, env, text, capture_output, timeout):
        calls.append({"argv": list(argv), "cwd": cwd, "env": env})
        return subprocess.CompletedProcess(argv, 0, stdout="ok\n", stderr="")

    exit_code, payload = run_release_smoke(
        project_root=tmp_path,
        include_tests=True,
        runner=fake_runner,
    )

    assert exit_code == 0
    assert payload["status"] == "passed"
    assert [command["key"] for command in payload["commands"]] == [
        "health",
        "dry_run_smoke",
        "pytest",
    ]
    assert calls[0]["cwd"] == str(tmp_path)
    assert calls[0]["env"]["CUDA_VISIBLE_DEVICES"] == "0"
    assert calls[0]["env"]["PYTHONPATH"].split(os.pathsep)[0] == str(tmp_path / "src")
    assert calls[0]["argv"][1:] == ["-m", "anima_app.cli", "health", "--json"]
    assert Path(calls[1]["argv"][1]).name == "smoke_anima_app.py"
    assert "--dry-run" in calls[1]["argv"]
    assert "--require-checks" in calls[1]["argv"]


def test_run_release_smoke_fails_when_a_command_fails(tmp_path):
    make_release_tree(tmp_path)

    def fake_runner(argv, cwd, env, text, capture_output, timeout):
        return_code = 2 if any("smoke_anima_app.py" in part for part in argv) else 0
        return subprocess.CompletedProcess(argv, return_code, stdout="out", stderr="err")

    exit_code, payload = run_release_smoke(project_root=tmp_path, runner=fake_runner)

    assert exit_code == 1
    assert payload["status"] == "failed"
    assert payload["commands"][1]["key"] == "dry_run_smoke"
    assert payload["commands"][1]["ok"] is False

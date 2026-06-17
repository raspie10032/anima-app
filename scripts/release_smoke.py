from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
CommandRunner = Callable[..., subprocess.CompletedProcess[str]]


@dataclass(frozen=True)
class CommandSpec:
    key: str
    argv: tuple[str, ...]
    timeout: int


def _path_check(key: str, path: Path, *, kind: str = "file") -> dict[str, Any]:
    if kind == "dir":
        ok = path.is_dir()
        reason = "directory exists" if ok else "directory is missing"
    else:
        ok = path.is_file()
        reason = "file exists" if ok else "file is missing"
    return {"key": key, "ok": ok, "path": str(path), "reason": reason}


def _content_check(key: str, path: Path, required: Sequence[str]) -> dict[str, Any]:
    if not path.is_file():
        return {"key": key, "ok": False, "path": str(path), "reason": "file is missing"}
    text = path.read_text(encoding="utf-8", errors="replace")
    missing = [item for item in required if item not in text]
    if missing:
        return {
            "key": key,
            "ok": False,
            "path": str(path),
            "reason": "missing required text: " + ", ".join(missing),
        }
    return {"key": key, "ok": True, "path": str(path), "reason": "required text found"}


def collect_static_checks(project_root: Path) -> list[dict[str, Any]]:
    root = project_root.resolve()
    checks = [
        _content_check("pyproject", root / "pyproject.toml", ["anima-app"]),
        _path_check("readme", root / "README.md"),
        _path_check("source_package", root / "src" / "anima_app", kind="dir"),
        _path_check("vendored_runtime", root / "vendor" / "anima_runtime", kind="dir"),
        _path_check("smoke_script", root / "scripts" / "smoke_anima_app.py"),
        _path_check("release_smoke_script", root / "scripts" / "release_smoke.py"),
        _path_check("package_dry_run_script", root / "scripts" / "package_dry_run.py"),
        _content_check("gui_launcher", root / "Run-AnimaAPP-GUI.cmd", ["anima_app.cli serve"]),
        _path_check("acceptance_doc", root / "docs" / "ACCEPTANCE.md"),
        _path_check("packaging_plan", root / "docs" / "PACKAGING_PLAN.md"),
        _path_check("release_checklist", root / "docs" / "RELEASE_CHECKLIST.md"),
        _path_check("references_doc", root / "docs" / "REFERENCES.md"),
        _content_check("artifact_gitignore", root / ".gitignore", ["/models/", "/outputs/", "/inputs/"]),
    ]
    return checks


def release_checks_pass(checks: Sequence[dict[str, Any]]) -> bool:
    return all(bool(check.get("ok")) for check in checks)


def build_release_env(project_root: Path) -> dict[str, str]:
    env = os.environ.copy()
    src_path = str(project_root.resolve() / "src")
    existing_pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = src_path if not existing_pythonpath else src_path + os.pathsep + existing_pythonpath
    return env


def command_specs(project_root: Path, *, include_tests: bool, timeout: int) -> list[CommandSpec]:
    root = project_root.resolve()
    specs = [
        CommandSpec(
            key="health",
            argv=(sys.executable, "-m", "anima_app.cli", "health", "--json"),
            timeout=timeout,
        ),
        CommandSpec(
            key="manifest_check",
            argv=(
                sys.executable,
                str(root / "scripts" / "smoke_anima_app.py"),
                "--dry-run",
                "--require-checks",
            ),
            timeout=timeout,
        ),
    ]
    if include_tests:
        specs.append(
            CommandSpec(
                key="pytest",
                argv=(sys.executable, "-m", "pytest", "tests", "-q"),
                timeout=max(timeout, 300),
            )
        )
    return specs


def _tail(text: str, limit: int = 4000) -> str:
    if len(text) <= limit:
        return text
    return text[-limit:]


def run_command(
    spec: CommandSpec,
    *,
    cwd: Path,
    env: dict[str, str],
    runner: CommandRunner,
) -> dict[str, Any]:
    try:
        completed = runner(
            list(spec.argv),
            cwd=str(cwd),
            env=env,
            text=True,
            capture_output=True,
            timeout=spec.timeout,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "key": spec.key,
            "ok": False,
            "argv": list(spec.argv),
            "returncode": None,
            "stdout_tail": _tail(exc.stdout or ""),
            "stderr_tail": _tail(exc.stderr or ""),
            "error": f"timed out after {spec.timeout}s",
        }
    except OSError as exc:
        return {
            "key": spec.key,
            "ok": False,
            "argv": list(spec.argv),
            "returncode": None,
            "stdout_tail": "",
            "stderr_tail": "",
            "error": str(exc),
        }

    return {
        "key": spec.key,
        "ok": completed.returncode == 0,
        "argv": list(spec.argv),
        "returncode": completed.returncode,
        "stdout_tail": _tail(completed.stdout or ""),
        "stderr_tail": _tail(completed.stderr or ""),
    }


def run_release_smoke(
    *,
    project_root: Path,
    include_tests: bool = False,
    timeout: int = 180,
    runner: CommandRunner = subprocess.run,
) -> tuple[int, dict[str, Any]]:
    root = project_root.resolve()
    static_checks = collect_static_checks(root)
    env = build_release_env(root)
    commands = [
        run_command(spec, cwd=root, env=env, runner=runner)
        for spec in command_specs(root, include_tests=include_tests, timeout=timeout)
    ]
    ok = release_checks_pass(static_checks) and all(command["ok"] for command in commands)
    payload: dict[str, Any] = {
        "status": "passed" if ok else "failed",
        "project_root": str(root),
        "release_target": "source-checkout alpha",
        "gpu_policy": "set CUDA_VISIBLE_DEVICES externally when a specific GPU should be used",
        "packaged_release": "wheel and standalone packaging are not finalized",
        "static_checks": static_checks,
        "commands": commands,
    }
    return (0 if ok else 1), payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the Anima APP source-checkout release smoke.")
    parser.add_argument("--project-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--include-tests", action="store_true", help="Also run the full pytest suite.")
    parser.add_argument("--timeout", type=int, default=180, help="Per-command timeout in seconds.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    exit_code, payload = run_release_smoke(
        project_root=args.project_root,
        include_tests=args.include_tests,
        timeout=args.timeout,
    )
    print(json.dumps(payload, indent=2))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())

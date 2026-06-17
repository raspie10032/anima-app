from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import zipfile
from pathlib import Path
from typing import Any, Callable, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = Path("outputs") / "package_dry_run"
CommandRunner = Callable[..., subprocess.CompletedProcess[str]]


def packaging_checks_pass(checks: Sequence[dict[str, Any]]) -> bool:
    return all(bool(check.get("ok")) for check in checks)


def _path_check(root: Path, relative: str, *, kind: str = "file") -> dict[str, Any]:
    path = root / relative
    ok = path.is_dir() if kind == "dir" else path.is_file()
    return {
        "key": relative.replace("\\", "/"),
        "ok": ok,
        "path": str(path),
        "reason": f"{kind} exists" if ok else f"{kind} is missing",
    }


def collect_source_checks(project_root: Path) -> list[dict[str, Any]]:
    root = project_root.resolve()
    return [
        _path_check(root, "pyproject.toml"),
        _path_check(root, "README.md"),
        _path_check(root, "NOTICE.md"),
        _path_check(root, "src/anima_app", kind="dir"),
        _path_check(root, "vendor/anima_runtime", kind="dir"),
        _path_check(root, "vendor/python_packages", kind="dir"),
        _path_check(root, "Run-AnimaAPP-GUI.cmd"),
        _path_check(root, "scripts/smoke_anima_app.py"),
        _path_check(root, "scripts/release_smoke.py"),
        _path_check(root, "scripts/package_dry_run.py"),
        _path_check(root, "docs/ACCEPTANCE.md"),
        _path_check(root, "docs/REFERENCES.md"),
        _path_check(root, "docs/RELEASE_CHECKLIST.md"),
    ]


def build_standalone_layout_plan(project_root: Path) -> dict[str, Any]:
    root = project_root.resolve()
    include_candidates = [
        "pyproject.toml",
        "README.md",
        "NOTICE.md",
        "Run-AnimaAPP-GUI.cmd",
        "scripts",
        "src",
        "vendor/anima_runtime",
        "vendor/python_packages",
        "docs",
        "wildcards",
    ]
    excluded_roots = [
        "models",
        "outputs",
        "inputs",
        ".git",
        ".pytest_cache",
        "__pycache__",
    ]
    include_roots = [relative for relative in include_candidates if (root / relative).exists()]
    missing = [relative for relative in include_candidates if not (root / relative).exists()]
    required_missing = [relative for relative in missing if relative != "wildcards"]
    return {
        "ok": not required_missing,
        "include_roots": include_roots,
        "excluded_roots": excluded_roots,
        "missing_optional_roots": [relative for relative in missing if relative == "wildcards"],
        "missing_required_roots": required_missing,
        "notes": [
            "Model, detector, LoRA, input, and output artifacts stay outside the redistributable layout.",
            "Standalone binary bundling is still a plan; this dry-run proves the source-checkout layout contract.",
        ],
    }


def _check(key: str, ok: bool, reason: str) -> dict[str, Any]:
    return {"key": key, "ok": ok, "reason": reason}


def inspect_wheel(wheel_path: Path) -> list[dict[str, Any]]:
    if not wheel_path.is_file():
        return [_check("wheel_exists", False, "wheel file is missing")]
    with zipfile.ZipFile(wheel_path) as wheel:
        names = wheel.namelist()
        entry_points = "\n".join(
            wheel.read(name).decode("utf-8", errors="replace")
            for name in names
            if name.endswith(".dist-info/entry_points.txt")
        )
    return [
        _check("wheel_exists", True, str(wheel_path)),
        _check("package_module", any(name.startswith("anima_app/") for name in names), "anima_app package is present"),
        _check("metadata", any(name.endswith(".dist-info/METADATA") for name in names), "dist-info metadata is present"),
        _check(
            "console_entrypoint",
            "anima-app" in entry_points and "anima_app.cli:console_main" in entry_points,
            "anima-app console entrypoint is present",
        ),
        _check(
            "model_artifacts_excluded",
            not any(name.startswith(("models/", "outputs/", "inputs/")) for name in names),
            "local model/input/output artifacts are not inside the wheel",
        ),
        _check(
            "vendored_runtime_excluded_from_wheel",
            not any(name.startswith("vendor/") for name in names),
            "vendored runtime is intentionally handled by the standalone/source-checkout layout, not the wheel",
        ),
    ]


def _tail(text: str, limit: int = 4000) -> str:
    if len(text) <= limit:
        return text
    return text[-limit:]


def _ensure_output_dir(project_root: Path, output_dir: Path) -> Path:
    root = project_root.resolve()
    resolved = output_dir if output_dir.is_absolute() else root / output_dir
    resolved = resolved.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError("output directory must stay inside the project root") from exc
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def _find_latest_wheel(output_dir: Path, started_at: float) -> Path | None:
    wheels = [
        path
        for path in output_dir.glob("*.whl")
        if path.name.startswith("anima_app-") or path.name.startswith("anima-app-")
    ]
    if not wheels:
        return None
    fresh = [path for path in wheels if path.stat().st_mtime >= started_at - 1.0]
    return max(fresh or wheels, key=lambda path: path.stat().st_mtime)


def run_wheel_build(
    *,
    project_root: Path,
    output_dir: Path,
    timeout: int,
    runner: CommandRunner,
) -> dict[str, Any]:
    argv = [
        sys.executable,
        "-m",
        "pip",
        "wheel",
        ".",
        "--no-deps",
        "--no-build-isolation",
        "--wheel-dir",
        str(output_dir),
    ]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(project_root.resolve() / "src")
    try:
        completed = runner(
            argv,
            cwd=str(project_root.resolve()),
            env=env,
            text=True,
            capture_output=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "ok": False,
            "argv": argv,
            "returncode": None,
            "stdout_tail": _tail(exc.stdout or ""),
            "stderr_tail": _tail(exc.stderr or ""),
            "error": f"timed out after {timeout}s",
        }
    except OSError as exc:
        return {
            "ok": False,
            "argv": argv,
            "returncode": None,
            "stdout_tail": "",
            "stderr_tail": "",
            "error": str(exc),
        }
    return {
        "ok": completed.returncode == 0,
        "argv": argv,
        "returncode": completed.returncode,
        "stdout_tail": _tail(completed.stdout or ""),
        "stderr_tail": _tail(completed.stderr or ""),
    }


def run_package_dry_run(
    *,
    project_root: Path,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    timeout: int = 300,
    runner: CommandRunner = subprocess.run,
) -> tuple[int, dict[str, Any]]:
    root = project_root.resolve()
    active_output_dir = _ensure_output_dir(root, output_dir)
    source_checks = collect_source_checks(root)
    layout_plan = build_standalone_layout_plan(root)
    started_at = time.time()
    wheel_command = run_wheel_build(project_root=root, output_dir=active_output_dir, timeout=timeout, runner=runner)
    wheel_path = _find_latest_wheel(active_output_dir, started_at) if wheel_command["ok"] else None
    wheel_checks = inspect_wheel(wheel_path) if wheel_path else []
    ok = (
        packaging_checks_pass(source_checks)
        and layout_plan["ok"]
        and bool(wheel_command["ok"])
        and packaging_checks_pass(wheel_checks)
    )
    report_path = active_output_dir / "package_dry_run_report.json"
    payload: dict[str, Any] = {
        "status": "passed" if ok else "failed",
        "project_root": str(root),
        "output_dir": str(active_output_dir),
        "report_path": str(report_path),
        "wheel_path": str(wheel_path) if wheel_path else None,
        "source_checks": source_checks,
        "standalone_layout": layout_plan,
        "wheel_command": wheel_command,
        "wheel_checks": wheel_checks,
    }
    report_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return (0 if ok else 1), payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build and inspect Anima APP packaging artifacts in outputs.")
    parser.add_argument("--project-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--timeout", type=int, default=300)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    exit_code, payload = run_package_dry_run(
        project_root=args.project_root,
        output_dir=args.output_dir,
        timeout=args.timeout,
    )
    print(json.dumps(payload, indent=2))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path, PurePosixPath
import zipfile


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_SENTINEL = PROJECT_ROOT / "vendor/anima_runtime/comfy/ldm/anima/model.py"


def _run(arguments: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> None:
    subprocess.run(arguments, cwd=cwd, env=env, check=True)


def _copy_package_source(destination: Path) -> None:
    destination.mkdir()
    for name in ("pyproject.toml", "README.md", "LICENSE", "NOTICE.md"):
        shutil.copy2(PROJECT_ROOT / name, destination / name)
    shutil.copytree(
        PROJECT_ROOT / "src",
        destination / "src",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.egg-info"),
    )


def main() -> int:
    if not RUNTIME_SENTINEL.is_file():
        raise FileNotFoundError(f"source archive runtime sentinel is missing: {RUNTIME_SENTINEL}")

    with tempfile.TemporaryDirectory(prefix="anima-package-smoke-") as temporary_directory:
        temporary_root = Path(temporary_directory)
        source_root = temporary_root / "source"
        wheel_root = temporary_root / "wheel"
        site_root = temporary_root / "site"
        runtime_root = temporary_root / "runtime"
        _copy_package_source(source_root)
        wheel_root.mkdir()
        _run(
            [
                sys.executable,
                "-m",
                "pip",
                "wheel",
                "--no-deps",
                "--no-build-isolation",
                "--wheel-dir",
                str(wheel_root),
                str(source_root),
            ],
            cwd=temporary_root,
        )
        wheels = list(wheel_root.glob("anima_app-*.whl"))
        if len(wheels) != 1:
            raise RuntimeError(f"expected one Anima APP wheel, found {len(wheels)}")
        with zipfile.ZipFile(wheels[0]) as wheel:
            if any(PurePosixPath(name).parts[0] == "vendor" for name in wheel.namelist()):
                raise RuntimeError("wheel must not contain the source-checkout vendored runtime")
        _run(
            [sys.executable, "-m", "pip", "install", "--no-deps", "--target", str(site_root), str(wheels[0])],
            cwd=temporary_root,
        )

        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(site_root)
        environment["ANIMA_PACKAGE_SMOKE_ROOT"] = str(runtime_root)
        probe = """
import os
from importlib.metadata import version
from pathlib import Path
import anima_app
from anima_app.cli import main
from anima_app.config import AppPaths
from anima_app.server import APP_JS, INDEX_HTML

assert 'const animaDefaults' in APP_JS
assert '<script src="/app.js"></script>' in INDEX_HTML
assert (Path(anima_app.__file__).parent / 'static/app.js').is_file()
assert version('anima-app') == anima_app.__version__
assert not (Path(anima_app.__file__).resolve().parents[1] / 'vendor').exists()
root = Path(os.environ['ANIMA_PACKAGE_SMOKE_ROOT'])
raise SystemExit(main(['t2i', '--prompt', 'package smoke', '--dry-run'], paths=AppPaths(project_root=root)))
"""
        _run([sys.executable, "-c", probe], cwd=temporary_root, env=environment)

    print("package dry-run passed: wheel GUI/static asset, CLI dry-run, and source runtime sentinel")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

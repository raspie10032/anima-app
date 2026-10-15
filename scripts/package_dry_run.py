from __future__ import annotations

import argparse
import hashlib
import json
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
    parser = argparse.ArgumentParser(description="Build and verify an isolated wheel; optionally retain it")
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
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
            packaged = {}
            for path in sorted((source_root / "src/anima_app").rglob("*")):
                if not path.is_file() or path.suffix not in {".py", ".js", ".json", ".css"}:
                    continue
                name = path.relative_to(source_root / "src").as_posix()
                content = path.read_bytes()
                if wheel.read(name) != content:
                    raise RuntimeError(f"wheel content differs from source: {name}")
                packaged[name] = hashlib.sha256(content).hexdigest()
            for name in ("LICENSE", "NOTICE.md"):
                members = [member for member in wheel.namelist() if member.endswith("/" + name)]
                if len(members) != 1 or wheel.read(members[0]) != (source_root / name).read_bytes():
                    raise RuntimeError(f"wheel must preserve {name}")
            for package in ("swegca", "vrs_int"):
                name = f"anima_app/_vendor/{package}/LICENSE.txt"
                if wheel.read(name) != (source_root / "src" / name).read_bytes():
                    raise RuntimeError(f"wheel must preserve embedded license: {name}")
        _run(
            [sys.executable, "-m", "pip", "install", "--no-deps", "--target", str(site_root), str(wheels[0])],
            cwd=temporary_root,
        )

        environment = os.environ.copy()
        environment.pop("NAI_ACCESS_TOKEN", None)
        environment.pop("NAI_API_TOKEN", None)
        environment["PYTHONPATH"] = str(site_root)
        environment["ANIMA_PACKAGE_SMOKE_ROOT"] = str(runtime_root)
        probe = """
import os
from importlib.metadata import version
from pathlib import Path
import anima_app
from anima_app.cli import main
from anima_app.config import AppPaths
from anima_app.server import APP_JS, INDEX_HTML, NAI_I18N_JS, NAI_ERRORS_JS
from anima_app.providers.novelai import (
    converters, detailer, detailer_matching, eligibility, inpaint,
    metadata, references, requests, service, wd_tagger, medium, diagnostics,
    tagger_progress, tagger_setup, errors,
)
import json
from anima_app import library_core
from anima_app.library_vrs import VRSAdapter
assert library_core.status()['ready']
adapter = VRSAdapter(Path(os.environ['ANIMA_PACKAGE_SMOKE_ROOT']) / 'models')
assert not adapter.runtime.status()['weights_ready']
assert adapter.contract is None
assert library_core.__file__.startswith(os.environ['PYTHONPATH'])
assert (Path(anima_app.__file__).parent / 'static/setup.js').is_file()
assert (Path(anima_app.__file__).parent / 'barracks.py').is_file()
assert (Path(anima_app.__file__).parent / 'static/barracks.js').is_file()

assert 'const animaDefaults' in APP_JS
assert '<script src="/app.js"></script>' in INDEX_HTML
assert (Path(anima_app.__file__).parent / 'static/app.js').is_file()
assert (Path(anima_app.__file__).parent / 'static/i18n.js').is_file()
ui_messages = json.loads((Path(anima_app.__file__).parent / 'static/ui-messages.json').read_text())
assert ui_messages['앱 언어']['en'] == 'App language'
assert ui_messages['이미지 작업실']['ja'] == '画像ワークスペース'
assert NAI_I18N_JS and NAI_ERRORS_JS
catalog = json.loads((Path(anima_app.__file__).parent / 'static/nai-error-messages.json').read_text())
assert all(len(catalog[locale]) == 52 for locale in ('en', 'ko', 'ja'))
assert medium.MEDIUM_MODEL == 'nai-diffusion-5-full-medium'
assert version('anima-app') == anima_app.__version__
assert references.MAX_REFERENCES == 16
assert callable(detailer.Detector.preflight)
assert callable(wd_tagger.WDTagger.score)
assert all(module.__file__.startswith(os.environ['PYTHONPATH']) for module in (
    converters, detailer, detailer_matching, eligibility, inpaint,
    metadata, references, requests, service, wd_tagger, medium, diagnostics,
    tagger_progress, tagger_setup, errors,
))
assert not (Path(anima_app.__file__).resolve().parents[1] / 'vendor').exists()
root = Path(os.environ['ANIMA_PACKAGE_SMOKE_ROOT'])
raise SystemExit(main(['t2i', '--prompt', 'package smoke', '--dry-run'], paths=AppPaths(project_root=root)))
"""
        _run([sys.executable, "-c", probe], cwd=temporary_root, env=environment)
        if args.output_dir:
            output = args.output_dir.resolve()
            output.mkdir(parents=True, exist_ok=True)
            destination = output / wheels[0].name
            if destination.exists():
                raise FileExistsError(f"use a new output directory: {destination}")
            shutil.copy2(wheels[0], destination)
            digest = hashlib.sha256(destination.read_bytes()).hexdigest()
            destination.with_suffix(destination.suffix + ".sha256").write_text(
                f"{digest}  {destination.name}\n", encoding="ascii")
            (output / "wheel-report.json").write_text(json.dumps({
                "status": "passed", "wheel": destination.name, "sha256": digest,
                "bytes": destination.stat().st_size, "source_sha256": packaged,
                "isolated_install_import_cli": True, "live_nai_requests": 0,
                "limits": ["wheel excludes the vendored local generation runtime",
                           "optional model dependencies and live generation not tested"],
            }, indent=2) + "\n", encoding="utf-8")

    print("package dry-run passed: wheel GUI/static asset, CLI dry-run, and source runtime sentinel")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

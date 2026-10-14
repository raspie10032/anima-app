from __future__ import annotations

import argparse
import ast
from io import BytesIO
import hashlib
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys
import tarfile
import tempfile
import zipfile


PROJECT_ROOT = Path(__file__).resolve().parents[1]
VERSION_FILE = PROJECT_ROOT / "src" / "anima_app" / "__init__.py"
FORBIDDEN_TOP_LEVEL = {
    ".git",
    "build",
    "dist",
    "external_detectors",
    "external_models",
    "inputs",
    "models",
    "outputs",
}
FORBIDDEN_NATIVE_SUFFIXES = {".dll", ".dylib", ".pyd", ".so"}
REQUIRED_FILES = {
    ".github/workflows/ci.yml",
    "LICENSE",
    "NOTICE.md",
    "README.md",
    "Run-AnimaAPP-GUI.cmd",
    "docs/RELEASE_MANIFEST.md",
    "docs/USER_GUIDE_KO.md",
    "docs/NOVELAI_PROVIDER.md",
    "docs/RELEASE_0.5.0.md",
    "docs/NAI_PORT_ACCEPTANCE.md",
    "docs/NAI_NODE_UPDATE_2.4.6.md",
    "docs/REFERENCES.md",
    "pyproject.toml",
    "scripts/package_dry_run.py",
    "scripts/source_archive.py",
    "scripts/audit_nai_port_release.py",
    "scripts/audit_nai_update_release.py",
    "scripts/verify_vendor.py",
    "src/anima_app/static/app.js",
    "src/anima_app/static/nai-i18n.js",
    "src/anima_app/static/i18n.js",
    "src/anima_app/static/ui-messages.json",
    "src/anima_app/static/nai-errors.js",
    "src/anima_app/static/nai-error-messages.json",
    "src/anima_app/providers/novelai/medium.py",
    "src/anima_app/providers/novelai/diagnostics.py",
    "src/anima_app/providers/novelai/tagger_setup.py",
    "src/anima_app/providers/novelai/tagger_progress.py",
    "src/anima_app/providers/novelai/errors.py",
    "src/anima_app/providers/novelai/service.py",
    "src/anima_app/providers/novelai/client.py",
    "src/anima_app/providers/novelai/eligibility.py",
    "src/anima_app/providers/novelai/requests.py",
    "src/anima_app/providers/novelai/metadata.py",
    "src/anima_app/providers/novelai/inpaint.py",
    "src/anima_app/providers/novelai/references.py",
    "src/anima_app/providers/novelai/detailer.py",
    "src/anima_app/providers/novelai/detailer_matching.py",
    "src/anima_app/providers/novelai/wd_tagger.py",
    "src/anima_app/providers/novelai/converters.py",
    "vendor/README.md",
    "vendor/anima_runtime/LICENSE",
    "vendor/anima_runtime/comfy/ldm/anima/model.py",
    "vendor/python_packages/comfy_aimdo-0.3.0.dist-info/licenses/LICENSE",
    "vendor/python_packages/comfy_kitchen-0.2.8.dist-info/licenses/LICENSE",
    "wildcards/README_IMPACT_PACK.md",
}
FIXED_ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)


def project_version() -> str:
    tree = ast.parse(VERSION_FILE.read_text(encoding="utf-8"), filename=str(VERSION_FILE))
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if isinstance(target, ast.Name) and target.id == "__version__":
            value = ast.literal_eval(node.value)
            if isinstance(value, str) and value:
                return value
    raise RuntimeError(f"canonical __version__ is missing from {VERSION_FILE}")


def _git(*arguments: str, stdout: int | None = subprocess.PIPE) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *arguments],
        cwd=PROJECT_ROOT,
        check=True,
        stdout=stdout,
        stderr=subprocess.PIPE,
    )


def _require_clean_checkout() -> None:
    status = _git("status", "--porcelain", "--untracked-files=all").stdout.decode("utf-8")
    if status.strip():
        raise RuntimeError("official source archives require a clean Git checkout")


def _working_tree_entries() -> dict[str, bytes]:
    listed = _git("ls-files", "-z", "--cached", "--others", "--exclude-standard").stdout
    entries: dict[str, bytes] = {}
    for raw_name in listed.split(b"\0"):
        if not raw_name:
            continue
        name = raw_name.decode("utf-8")
        relative = PurePosixPath(name)
        path = PROJECT_ROOT.joinpath(*relative.parts)
        if not path.exists():
            continue
        if path.is_symlink() or not path.is_file():
            raise RuntimeError(f"release candidate must contain regular files only: {name}")
        entries[relative.as_posix()] = path.read_bytes()
    return entries


def _clean_head_entries() -> dict[str, bytes]:
    archive = _git("archive", "--format=tar", "HEAD").stdout
    entries: dict[str, bytes] = {}
    with tarfile.open(fileobj=BytesIO(archive), mode="r:") as source_tar:
        for member in source_tar.getmembers():
            if member.isdir():
                continue
            if not member.isfile():
                raise RuntimeError(f"release candidate must contain regular files only: {member.name}")
            extracted = source_tar.extractfile(member)
            if extracted is None:
                raise RuntimeError(f"cannot read Git archive member: {member.name}")
            entries[PurePosixPath(member.name).as_posix()] = extracted.read()
    return entries


def _validate_entries(entries: dict[str, bytes]) -> None:
    missing = sorted(REQUIRED_FILES.difference(entries))
    if missing:
        raise RuntimeError(f"source archive is missing required files: {', '.join(missing)}")
    for name in entries:
        relative = PurePosixPath(name)
        if relative.is_absolute() or ".." in relative.parts:
            raise RuntimeError(f"unsafe source archive path: {name}")
        if relative.parts and relative.parts[0] in FORBIDDEN_TOP_LEVEL:
            raise RuntimeError(f"forbidden source archive path: {name}")
        if relative.suffix.lower() in FORBIDDEN_NATIVE_SUFFIXES:
            raise RuntimeError(f"unresolved native binary in source archive: {name}")


def _write_archive(path: Path, prefix: str, entries: dict[str, bytes]) -> None:
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, suffix=".zip.tmp", delete=False) as temporary:
            temporary_path = Path(temporary.name)
        with zipfile.ZipFile(temporary_path, "w", compression=zipfile.ZIP_STORED) as destination:
            for name in sorted(entries):
                info = zipfile.ZipInfo(f"{prefix}/{name}", date_time=FIXED_ZIP_TIMESTAMP)
                info.create_system = 3
                info.external_attr = 0o100644 << 16
                destination.writestr(info, entries[name])
        temporary_path.replace(path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def verify_source_archive(path: Path, version: str | None = None) -> None:
    expected_version = version or project_version()
    prefix = f"anima-app-{expected_version}"
    with zipfile.ZipFile(path) as source_zip:
        names = source_zip.namelist()
        if len(names) != len(set(names)):
            raise RuntimeError("source archive contains duplicate paths")
        relative_names: set[str] = set()
        for name in names:
            archive_path = PurePosixPath(name)
            if not archive_path.parts or archive_path.parts[0] != prefix:
                raise RuntimeError(f"source archive path is outside {prefix}: {name}")
            relative = PurePosixPath(*archive_path.parts[1:])
            if relative.is_absolute() or ".." in relative.parts:
                raise RuntimeError(f"unsafe source archive member: {name}")
            if relative.parts and relative.parts[0] in FORBIDDEN_TOP_LEVEL:
                raise RuntimeError(f"forbidden source archive member: {name}")
            if relative.suffix.lower() in FORBIDDEN_NATIVE_SUFFIXES:
                raise RuntimeError(f"unresolved native binary in source archive: {name}")
            relative_names.add(relative.as_posix())
        missing = sorted(REQUIRED_FILES.difference(relative_names))
        if missing:
            raise RuntimeError(f"source archive verification is missing: {', '.join(missing)}")


def build_source_archive(output_dir: Path, *, require_clean: bool = False) -> tuple[Path, Path]:
    if require_clean:
        _require_clean_checkout()
        entries = _clean_head_entries()
    else:
        entries = _working_tree_entries()
    _validate_entries(entries)
    version = project_version()
    prefix = f"anima-app-{version}"
    output_dir.mkdir(parents=True, exist_ok=True)
    archive_path = output_dir / f"{prefix}-source.zip"
    digest_path = output_dir / f"{archive_path.name}.sha256"
    _write_archive(archive_path, prefix, entries)
    verify_source_archive(archive_path, version)
    digest = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    digest_path.write_text(f"{digest}  {archive_path.name}\n", encoding="ascii", newline="\n")
    return archive_path, digest_path


def smoke_source_archive(archive_path: Path) -> None:
    version = project_version()
    with tempfile.TemporaryDirectory(prefix="anima-source-smoke-") as temporary_directory:
        extraction_root = Path(temporary_directory)
        with zipfile.ZipFile(archive_path) as source_zip:
            source_zip.extractall(extraction_root)
        checkout = extraction_root / f"anima-app-{version}"
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(checkout / "src")
        environment["ANIMA_APP_ROOT"] = str(checkout)
        subprocess.run(
            [sys.executable, "scripts/verify_vendor.py"],
            cwd=checkout,
            env=environment,
            check=True,
        )
        subprocess.run(
            [sys.executable, "-m", "anima_app.cli", "t2i", "--prompt", "source archive smoke", "--dry-run"],
            cwd=checkout,
            env=environment,
            check=True,
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the verified Anima APP source-checkout archive")
    parser.add_argument("--output-dir", type=Path, default=PROJECT_ROOT / "outputs" / "release")
    parser.add_argument("--require-clean", action="store_true")
    parser.add_argument("--skip-smoke", action="store_true")
    arguments = parser.parse_args(argv)
    archive_path, digest_path = build_source_archive(
        arguments.output_dir,
        require_clean=arguments.require_clean,
    )
    if not arguments.skip_smoke:
        smoke_source_archive(archive_path)
    print(f"source archive passed: {archive_path}")
    print(digest_path.read_text(encoding="ascii").strip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
import zipfile

import pytest

from anima_app import __version__


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _load_script(module_name: str, filename: str):
    script = PROJECT_ROOT / "scripts" / filename
    spec = importlib.util.spec_from_file_location(module_name, script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_release_version_has_one_packaging_source_of_truth():
    pyproject = (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert __version__ == "0.6.1"
    assert 'dynamic = ["version"]' in pyproject
    assert '[tool.setuptools.dynamic]' in pyproject
    assert 'version = {attr = "anima_app.__version__"}' in pyproject
    assert f'version = "{__version__}"' not in pyproject


def test_release_docs_and_manifest_target_current_version():
    acceptance = (PROJECT_ROOT / "docs" / "ACCEPTANCE.md").read_text(encoding="utf-8")
    references = (PROJECT_ROOT / "docs" / "REFERENCES.md").read_text(encoding="utf-8")
    release = (PROJECT_ROOT / f"docs/RELEASE_{__version__}.md").read_text(encoding="utf-8")
    manifest = (PROJECT_ROOT / "docs" / "RELEASE_MANIFEST.md").read_text(encoding="utf-8")

    assert f"`{__version__}` source-checkout beta" in acceptance
    assert f"Current release target: `{__version__}`" in references
    assert f"Anima APP v{__version__}" in release
    assert f"anima-app-{__version__}-source.zip" in manifest


def test_ci_covers_supported_python_edges_and_release_checks():
    workflow = (PROJECT_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")

    assert 'python-version: ["3.10", "3.13"]' in workflow
    assert "runs-on: windows-latest" in workflow
    assert "permissions:\n  contents: read" in workflow
    for command in (
        "python -m ruff check src tests scripts",
        "python -m pytest -q",
        "node --check src/anima_app/static/app.js",
        "python scripts/package_dry_run.py",
        "python scripts/source_archive.py --require-clean",
        "python scripts/verify_vendor.py",
    ):
        assert command in workflow


def test_vendored_runtime_inventory_records_versions_licenses_and_unknown_commit():
    inventory = (PROJECT_ROOT / "vendor/README.md").read_text(encoding="utf-8")

    assert "ComfyUI 0.22.2" in inventory
    assert "exact upstream commit" in inventory
    assert "not preserved" in inventory
    assert "comfy-kitchen 0.2.8" in inventory
    assert "Apache-2.0" in inventory
    assert "comfy-aimdo 0.3.0" in inventory
    assert "GPL-3.0" in inventory
    assert "aimdo.dll" in inventory and "were removed" in inventory
    assert not (PROJECT_ROOT / "vendor/python_packages/comfy_aimdo/aimdo.dll").exists()
    assert not (PROJECT_ROOT / "vendor/python_packages/comfy_aimdo/aimdo_rocm.dll").exists()
    wildcard_notice = (PROJECT_ROOT / "wildcards/README_IMPACT_PACK.md").read_text(encoding="utf-8")
    assert "were copied or derived" in wildcard_notice
    assert "GNU GPL version 3" in wildcard_notice
    assert "exact upstream revision" in wildcard_notice


def test_vendored_record_hashes_and_product_boundary_are_current():
    verifier = _load_script("anima_verify_vendor", "verify_vendor.py")

    assert verifier.verify_records() == []
    assert verifier.verify_product_boundary() == []


def test_package_dry_run_builds_from_a_temporary_source_copy():
    script = (PROJECT_ROOT / "scripts/package_dry_run.py").read_text(encoding="utf-8")

    assert "_copy_package_source(source_root)" in script
    assert "str(source_root)" in script
    assert "version('anima-app') == anima_app.__version__" in script
    assert "wheel must not contain the source-checkout vendored runtime" in script


def test_source_archive_is_verified_and_reproducible(tmp_path):
    archive_module = _load_script("anima_source_archive", "source_archive.py")

    assert "docs/USER_GUIDE_KO.md" in archive_module.REQUIRED_FILES
    first_archive, first_digest = archive_module.build_source_archive(tmp_path / "first")
    second_archive, second_digest = archive_module.build_source_archive(tmp_path / "second")
    first_bytes = first_archive.read_bytes()

    assert first_bytes == second_archive.read_bytes()
    assert first_digest.read_text(encoding="ascii").split()[0] == hashlib.sha256(first_bytes).hexdigest()
    assert second_digest.is_file()
    with zipfile.ZipFile(first_archive) as source_zip:
        names = set(source_zip.namelist())
    prefix = f"anima-app-{__version__}"
    assert f"{prefix}/vendor/anima_runtime/comfy/ldm/anima/model.py" in names
    assert f"{prefix}/vendor/README.md" in names
    assert f"{prefix}/LICENSE" in names
    assert f"{prefix}/NOTICE.md" in names
    assert f"{prefix}/Run-AnimaAPP-GUI.cmd" in names
    assert f"{prefix}/docs/USER_GUIDE_KO.md" in names
    assert f"{prefix}/src/anima_app/static/app.js" in names
    assert f"{prefix}/wildcards/README_IMPACT_PACK.md" in names
    assert f"{prefix}/scripts/verify_vendor.py" in names
    assert not any(
        f"{prefix}/{excluded}/" in name
        for name in names
        for excluded in ("models", "inputs", "outputs", ".git")
    )
    assert not any(Path(name).suffix.lower() in {".dll", ".pyd", ".so", ".dylib"} for name in names)


@pytest.mark.parametrize("missing", ["src/anima_app/static/i18n.js", "src/anima_app/static/ui-messages.json",
    "src/anima_app/static/nai-error-messages.json",
    "src/anima_app/static/nai-i18n.js", "src/anima_app/static/nai-errors.js",
    "src/anima_app/providers/novelai/tagger_setup.py", "docs/NAI_NODE_UPDATE_2.4.6.md",
    "docs/RELEASE_0.6.1.md", "docs/NAI_TOKEN_SETUP.md",
    "SETUP.md", "docs/BARRACKS.md", "docs/EMBEDDED_VRS_CONTRACT.md",
    "src/anima_app/credentials.py", "src/anima_app/library_vrs_cached.py",
    "src/anima_app/_vendor/vrs_int/LICENSE.txt", "src/anima_app/_vendor/swegca/LICENSE.txt",
    "docs/IMAGE_GENERATION_KO.md", "docs/IMAGE_GENERATION_EN.md", "docs/IMAGE_GENERATION_JA.md",
    "src/anima_app/static/library.js", "src/anima_app/static/generation.css",
    "src/anima_app/static/authoring.js", "src/anima_app/static/workflow.js"])
def test_source_archive_rejects_omitted_update_resources(tmp_path, missing):
    archive_module = _load_script("anima_source_update_archive", "source_archive.py")
    target = tmp_path / "incomplete.zip"
    with zipfile.ZipFile(target, "w") as archive:
        for name in archive_module.REQUIRED_FILES - {missing}:
            archive.writestr(f"anima-app-{__version__}/{name}", b"fixture")
    with pytest.raises(RuntimeError, match="missing"):
        archive_module.verify_source_archive(target)

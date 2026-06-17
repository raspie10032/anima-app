# Anima APP Lightweight Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a lightweight standalone Anima image-generation app in `C:\Users\seine\Documents\Anima APP` using the verified AnimaStudio core as the starting point.

**Architecture:** Start with a small Python package and TDD-protected model-path/asset-copy contracts. Port the verified AnimaStudio CLI and runtime in layers: foundation, assets, manifests, dry-run T2I, vendored runtime, real PNG smoke, then GUI.

**Tech Stack:** Python 3.10+, setuptools, pytest, Pillow, torch/Comfy-derived runtime, safetensors, transformers, optional ultralytics.

---

## File Structure

- `pyproject.toml`: package metadata, runtime dependencies, pytest configuration.
- `README.md`: user-facing commands and current acceptance state.
- `NOTICE.md`: ComfyUI/face-detailer provenance.
- `Run-AnimaAPP-GUI.cmd`: later GUI launcher with GPU 0 pinning.
- `src/anima_app/config.py`: project paths.
- `src/anima_app/assets.py`: asset profiles, inventory, copy helpers, LoRA import.
- `src/anima_app/requests.py`: request dataclasses and validation.
- `src/anima_app/manifests.py`: manifest write/read/history.
- `src/anima_app/health.py`: readiness payload.
- `src/anima_app/gpu.py`: CUDA environment helpers.
- `src/anima_app/cli.py`: CLI commands.
- `src/anima_app/runtime/pipeline.py`: dry-run and real-render orchestration.
- `src/anima_app/runtime/comfy_t2i.py`: real Anima rendering.
- `src/anima_app/runtime/face_detailer.py`: optional face detailer.
- `src/anima_app/web.py`: later local GUI/API.
- `scripts/smoke_anima_app.py`: evidence-oriented smoke runner.
- `tests/`: behavior tests for each contract.

### Task 1: Foundation Package And Paths

**Files:**
- Create: `pyproject.toml`
- Create: `src/anima_app/__init__.py`
- Create: `src/anima_app/config.py`
- Create: `tests/test_config.py`

- [ ] **Step 1: Write the failing path tests**

```python
from pathlib import Path

from anima_app.config import AppPaths, default_paths


def test_default_paths_point_at_anima_app_workspace():
    paths = default_paths()

    assert paths.project_root == Path(r"C:\Users\seine\Documents\Anima APP")
    assert paths.model_root == paths.project_root / "models"
    assert paths.output_root == paths.project_root / "outputs"
    assert paths.image_root == paths.output_root / "images"
    assert paths.manifest_root == paths.output_root / "manifests"
    assert paths.input_root == paths.project_root / "inputs"


def test_development_model_source_is_comfyui_sage_models():
    paths = AppPaths()

    assert paths.development_model_source == Path(r"E:\ComfyUI_sage\ComfyUI\models")
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_config.py -q`

Expected: failure because the `anima_app` package does not exist yet.

- [ ] **Step 3: Add the minimal package and path implementation**

```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


DEFAULT_PROJECT_ROOT = Path(r"C:\Users\seine\Documents\Anima APP")
DEFAULT_DEVELOPMENT_MODEL_SOURCE = Path(r"E:\ComfyUI_sage\ComfyUI\models")
DEFAULT_FACE_DETAILER_DETECTOR_SOURCE = Path(r"C:\Users\seine\Desktop\NAI-FaceDetailer\models\detectors")


@dataclass(frozen=True)
class AppPaths:
    project_root: Path = DEFAULT_PROJECT_ROOT
    development_model_source: Path = DEFAULT_DEVELOPMENT_MODEL_SOURCE
    face_detailer_detector_source: Path = DEFAULT_FACE_DETAILER_DETECTOR_SOURCE

    @property
    def model_root(self) -> Path:
        return self.project_root / "models"

    @property
    def output_root(self) -> Path:
        return self.project_root / "outputs"

    @property
    def manifest_root(self) -> Path:
        return self.output_root / "manifests"

    @property
    def image_root(self) -> Path:
        return self.output_root / "images"

    @property
    def input_root(self) -> Path:
        return self.project_root / "inputs"


def default_paths() -> AppPaths:
    return AppPaths()
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest tests/test_config.py -q`

Expected: `2 passed`.

### Task 2: Asset Profiles And Copy Contracts

**Files:**
- Create: `src/anima_app/assets.py`
- Create: `tests/test_assets.py`

- [ ] **Step 1: Write failing tests for inventory and copy behavior**

```python
from pathlib import Path

from anima_app.assets import ANIMA_T2I_ASSET_PROFILE, copy_asset_file, scan_model_source


def test_anima_t2i_profile_lists_required_files():
    assert ANIMA_T2I_ASSET_PROFILE.name == "anima-t2i"
    assert tuple(str(path) for path in ANIMA_T2I_ASSET_PROFILE.files) == (
        r"diffusion_models\anima-base-v1.0.safetensors",
        r"text_encoders\qwen_3_06b_base.safetensors",
        r"vae\qwen_image_vae.safetensors",
    )


def test_scan_model_source_reports_known_folders(tmp_path):
    (tmp_path / "diffusion_models").mkdir()
    (tmp_path / "vae").mkdir()
    (tmp_path / "diffusion_models" / "model.safetensors").write_bytes(b"model")

    inventory = scan_model_source(tmp_path)

    assert inventory.source_root == tmp_path.resolve()
    assert "diffusion_models" in inventory.folders
    assert "vae" in inventory.folders
    assert inventory.files[0].relative_path == Path("diffusion_models") / "model.safetensors"


def test_copy_asset_file_copies_inside_destination(tmp_path):
    source_root = tmp_path / "source"
    dest_root = tmp_path / "dest"
    relative_path = Path("vae") / "qwen_image_vae.safetensors"
    (source_root / relative_path.parent).mkdir(parents=True)
    (source_root / relative_path).write_bytes(b"vae")

    copied = copy_asset_file(source_root, dest_root, relative_path)

    assert copied == (dest_root / relative_path).resolve()
    assert copied.read_bytes() == b"vae"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_assets.py -q`

Expected: failure because `anima_app.assets` does not exist.

- [ ] **Step 3: Implement the asset helpers**

Implement dataclasses `AssetFile`, `ModelInventory`, `AssetProfile`, constant `ANIMA_T2I_ASSET_PROFILE`, `scan_model_source`, and `copy_asset_file`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_assets.py -q`

Expected: `3 passed`.

### Task 3: Request Validation And Dry-Run Manifests

**Files:**
- Create: `src/anima_app/requests.py`
- Create: `src/anima_app/manifests.py`
- Create: `src/anima_app/runtime/pipeline.py`
- Create: `tests/test_requests_and_manifests.py`

- [ ] **Step 1: Write failing tests**

Cover prompt validation, width/height divisibility by 8, dry-run manifest writing, and output path absence for dry runs.

- [ ] **Step 2: Run tests to verify failure**

Run: `python -m pytest tests/test_requests_and_manifests.py -q`

Expected: failure because request/manifest modules do not exist.

- [ ] **Step 3: Implement minimal request and dry-run pipeline**

Port the verified AnimaStudio dataclass structure and write manifest JSON under `outputs\manifests`.

- [ ] **Step 4: Run tests to verify pass**

Run: `python -m pytest tests/test_requests_and_manifests.py -q`

Expected: all tests pass.

### Task 4: CLI Health, Inventory, Copy, And Dry-Run T2I

**Files:**
- Create: `src/anima_app/health.py`
- Create: `src/anima_app/gpu.py`
- Create: `src/anima_app/cli.py`
- Create: `tests/test_cli.py`

- [ ] **Step 1: Write failing CLI tests**

Cover `health --json`, `models inventory`, `models copy-profile anima-t2i`, and `t2i --dry-run`.

- [ ] **Step 2: Run tests to verify failure**

Run: `python -m pytest tests/test_cli.py -q`

Expected: failure because CLI does not exist.

- [ ] **Step 3: Implement minimal CLI**

Use `argparse`, structured JSON output, and default GPU environment helpers for generation commands.

- [ ] **Step 4: Run targeted CLI tests**

Run: `python -m pytest tests/test_cli.py -q`

Expected: all CLI tests pass.

### Task 5: Vendored Runtime And Real Base T2I

**Files:**
- Create or copy: `vendor/anima_runtime/**`
- Create: `vendor/python_packages/**` if needed
- Create: `src/anima_app/runtime/comfy_bootstrap.py`
- Create: `src/anima_app/runtime/comfy_t2i.py`
- Modify: `src/anima_app/runtime/pipeline.py`
- Create: `tests/test_comfy_runtime.py`
- Create: `tests/test_comfy_t2i.py`

- [ ] **Step 1: Write failing tests around bootstrap model-folder mapping and output validation**

Use temporary directories and fake renderer outputs so tests do not require GPU.

- [ ] **Step 2: Run tests to verify failure**

Run: `python -m pytest tests/test_comfy_runtime.py tests/test_comfy_t2i.py -q`

Expected: failure because runtime modules do not exist.

- [ ] **Step 3: Port runtime code from AnimaStudio**

Copy the verified bootstrap and renderer structure, update imports from `anima_studio` to `anima_app`, and keep native attention blockers.

- [ ] **Step 4: Run tests to verify pass**

Run: `python -m pytest tests/test_comfy_runtime.py tests/test_comfy_t2i.py -q`

Expected: all tests pass.

### Task 6: Smoke Runner And Real PNG Evidence

**Files:**
- Create: `scripts/smoke_anima_app.py`
- Create: `tests/test_smoke_anima_app.py`
- Modify: `README.md`
- Create: `docs/ACCEPTANCE.md`

- [ ] **Step 1: Write failing smoke-runner tests**

Test dry-run manifest checks and PNG validation using a fake renderer.

- [ ] **Step 2: Run tests to verify failure**

Run: `python -m pytest tests/test_smoke_anima_app.py -q`

Expected: failure because smoke script does not exist.

- [ ] **Step 3: Implement smoke runner**

Add `--dry-run`, `--require-checks`, prompt/resolution/stage flags, and strict manifest/output validation.

- [ ] **Step 4: Run tests and dry-run smoke**

Run:

```powershell
python -m pytest tests/test_smoke_anima_app.py -q
python scripts\smoke_anima_app.py --dry-run
```

Expected: tests pass and dry-run smoke writes a manifest.

- [ ] **Step 5: Run real PNG smoke after models are copied**

Run:

```powershell
$env:CUDA_VISIBLE_DEVICES='0'
python -m anima_app.cli models copy-profile anima-t2i
python scripts\smoke_anima_app.py --prompt "anime portrait, clean lineart" --negative "low quality" --width 512 --height 768 --steps 1 --cfg 1.0 --seed 52 --require-checks
```

Expected: smoke returns exit code 0, manifest exists, output exists, output is a valid PNG under `outputs\images`.

### Task 7: GUI/API After CLI Evidence

**Files:**
- Create: `src/anima_app/web.py`
- Create: `Run-AnimaAPP-GUI.cmd`
- Create: `tests/test_web.py`

- [ ] **Step 1: Write failing API tests with a fake renderer**

Cover `/api/health`, `/api/generate`, `/api/history`, generated image serving, and upload path sanitization.

- [ ] **Step 2: Run tests to verify failure**

Run: `python -m pytest tests/test_web.py -q`

Expected: failure because web module does not exist.

- [ ] **Step 3: Implement the local GUI/API**

Use the verified AnimaStudio HTTP server pattern, update naming to Anima APP, and filter history to generated images only.

- [ ] **Step 4: Run tests and HTTP smoke**

Run: `python -m pytest tests/test_web.py -q`

Expected: tests pass. Then start with `Run-AnimaAPP-GUI.cmd` and hit `/api/generate` for HTTP 200 after CLI evidence is stable.

## Plan Self-Review

- Spec coverage: the plan covers foundation, copied model assets, CLI-first flow, dry-run, real PNG smoke, optional GUI, and acceptance docs.
- Placeholder scan: no step uses TBD/TODO or asks for unspecified generic tests.
- Type consistency: package name is consistently `anima_app`; project root is consistently `C:\Users\seine\Documents\Anima APP`.

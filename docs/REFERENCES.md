# Anima APP References

This document keeps public source references, model layout, and release boundaries in one place. It must not contain user-specific local paths, private model locations, generated image paths, or machine-specific GPU inventory.

## Public Sources

- Anima model source: `circlestone-labs/Anima`
- Anima model subfolder: `split_files`
- Preferred checkpoint: `split_files/diffusion_models/anima-aesthetic-v1.1.safetensors`
- Face detector source: `Bingsu/adetailer` file `face_yolov8n.pt`
- Eye detector source: `guon/hand-eyes` file `full_eyes_detect_v1.pt`
- SAM detector source: Ultralytics asset `sam_b.pt`; SAM reference project: https://github.com/facebookresearch/segment-anything
- ComfyUI upstream project: https://github.com/comfyanonymous/ComfyUI
- ComfyUI Impact Pack upstream project: https://github.com/ltdrdata/ComfyUI-Impact-Pack
- Comfy Kitchen metadata: https://github.com/Comfy-Org/comfy-kitchen
- Comfy AIMDO metadata: https://github.com/Comfy-Org/comfy-aimdo

## Model Asset Layout

The runtime reads model files from the project-local `models` tree.

Required Anima T2I files:

- `models\diffusion_models\anima-base-v1.0.safetensors`
- `models\text_encoders\qwen_3_06b_base.safetensors`
- `models\vae\qwen_image_vae.safetensors`

The command below prepares the base profile. It downloads from Hugging Face unless a local mirror is configured with `ANIMA_APP_MODEL_SOURCE`.

```powershell
$env:PYTHONPATH='src'
python -m anima_app.cli models copy-profile anima-t2i
```

The preferred Aesthetic v1.1 checkpoint is a separate profile:

```powershell
$env:PYTHONPATH='src'
python -m anima_app.cli models copy-profile anima-aesthetic-v1.1
```

The GUI selects Aesthetic v1.1 when installed and otherwise falls back to the base checkpoint.

Additional Anima-family diffusion checkpoints can be placed under `models\diffusion_models` and selected by relative `.safetensors` path.

## Optional Detector Assets

Face-detailer detector assets are prepared into `models\detectors`. By default, the app uses a valid local detector source when configured, otherwise it downloads the detector profile.

```powershell
$env:PYTHONPATH='src'
python -m anima_app.cli models copy-profile face-detailer-detectors
```

To force a local mirror, set `ANIMA_APP_FACE_DETECTOR_SOURCE` and run the same command with `--source local`.

Expected detector filenames:

- `face_yolov8n.pt`
- `full_eyes_detect_v1.pt`
- `sam_b.pt`

SAM3 is optional and prepared as a separate profile because it is a gated Hugging Face model:

```powershell
$env:PYTHONPATH='src'
python -m anima_app.cli models copy-profile sam3-detector --source download
```

Expected SAM3 filename:

- `sam3.pt`

Source: https://huggingface.co/facebook/sam3

For face detailing, SAM3 can run one combined `face` + `eyes` mask pass and one `hand` + `hands` mask pass. These are sequential repaint passes with separate denoise values; a missing concept mask skips only its own pass.

Optional fallback detector folders can be supplied with `ANIMA_APP_FACE_DETECTOR_FALLBACKS`, separated by the platform path separator.

Detector weights are downloaded into the user's local `models` tree and remain excluded from this source release.

## LoRA Assets

LoRA files are user-provided local artifacts. Import them into `models\loras`:

```powershell
$env:PYTHONPATH='src'
python -m anima_app.cli models import-lora "path\to\style.safetensors"
```

Do not redistribute private or locally trained LoRA files without confirming their source license and permission.

## Runtime Configuration

Supported environment variables:

- `ANIMA_APP_ROOT`: override the project root.
- `ANIMA_APP_MODEL_SOURCE`: optional local mirror for base model files.
- `ANIMA_APP_FACE_DETECTOR_SOURCE`: optional detector source folder.
- `ANIMA_APP_FACE_DETECTOR_FALLBACKS`: optional detector fallback folders separated by the platform path separator.
- `ANIMA_APP_AUTOCOMPLETE_SOURCE`: optional prompt-autocomplete file path.
- `ANIMA_APP_CUDA_VISIBLE_DEVICES`: optional app-specific CUDA device selection. The Windows GUI launcher defaults it to `0` before Python starts.
- `CUDA_VISIBLE_DEVICES`: standard CUDA device selection respected by direct CLI runs when `ANIMA_APP_CUDA_VISIBLE_DEVICES` is not set.
- `ANIMA_LLM_RUNTIME_URL`: optional URL for a separately managed local LLM worker.

## Quality Defaults

Default CLI/API/GUI generation settings:

- Size: `832x1216`
- Steps: `20`
- CFG: `3.5`
- Sampler: `euler_ancestral_cfg_pp`
- Scheduler: `sgm_uniform`
- LoRA strength: `1.0`

GUI starting point size presets:

- `1024x1024`: square output.
- `832x1216`: 2:3 portrait output, with landscape available by swapping orientation.
- `896x1152`: 3:4 portrait output, with landscape available by swapping orientation.

## Wildcards

Prompt wildcard files live under `wildcards\*.txt`. Tokens use `__name__` and read `wildcards\name.txt`.

Prompt preset files live under `wildcards\presets\*.txt`. Tokens use `__presets/name__` and read `wildcards\presets\name.txt`.

Wildcard file values can contain nested wildcard tokens and inline random choices using `{choice A|choice B|choice C}` syntax. File-backed wildcard tokens follow the selected wildcard mode, while inline choices are always random. The GUI preview expands the current prompt without starting generation and surfaces missing files, invalid paths, and recursive wildcard cycles before GPU work begins.

The included wildcard files were copied or derived from a local ComfyUI Impact Pack checkout under the observed GPL-3.0 license. The exact upstream revision was not preserved. Keep that provenance limit, attribution, and the license text with redistributed builds.

## Release Boundary

Current release target: `0.4.0` source-checkout beta.

Included:

- Python package source under `src\anima_app`.
- Vendored runtime source under `vendor\anima_runtime`.
- Selected vendored Python packages under `vendor\python_packages`.
- Root GUI launcher for Windows users.
- Public docs, notices, and wildcard files.
- CI and release verification scripts, including the vendored integrity check and deterministic source archive generator.

Excluded:

- Base model weights and alternate checkpoints.
- Detector weights.
- LoRA files.
- Input images.
- Generated output images and generation-info JSON files.
- Unused aimdo native allocator DLLs and ignored local `comfy-kitchen` native extensions.

Not finalized:

- Standalone binary packaging.
- Final wheel redistribution policy for vendored runtime assets.
- Public tag creation and release upload; these remain owner-controlled manual actions.
- A standalone wheel containing the root-level vendored Comfy runtime.

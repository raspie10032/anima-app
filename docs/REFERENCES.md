# Anima APP References

This document keeps public source references, model layout, and release boundaries in one place. It must not contain user-specific local paths, private model locations, generated image paths, or machine-specific GPU inventory.

## Public Sources

- Anima base model source: `circlestone-labs/Anima`
- Anima base model subfolder: `split_files`
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

Additional Anima-family diffusion checkpoints can be placed under `models\diffusion_models` and selected by relative `.safetensors` path.

## Optional Detector Assets

Face-detailer detector assets are user-provided local files. Configure a detector source with `ANIMA_APP_FACE_DETECTOR_SOURCE` before copying them into `models\detectors`.

```powershell
$env:ANIMA_APP_FACE_DETECTOR_SOURCE='path\to\detectors'
$env:PYTHONPATH='src'
python -m anima_app.cli models copy-profile face-detailer-detectors
```

Expected detector filenames:

- `face_yolov8n.pt`
- `full_eyes_detect_v1.pt`
- `sam_b.pt`

Optional fallback detector folders can be supplied with `ANIMA_APP_FACE_DETECTOR_FALLBACKS`, separated by the platform path separator.

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
- `ANIMA_APP_CUDA_VISIBLE_DEVICES`: optional app-specific CUDA device selection. The Windows GUI launcher defaults it to `0` before Python starts.
- `CUDA_VISIBLE_DEVICES`: standard CUDA device selection respected by direct CLI runs when `ANIMA_APP_CUDA_VISIBLE_DEVICES` is not set.

## Quality Defaults

Default CLI/API/GUI generation settings:

- Size: `832x1216`
- Steps: `20`
- CFG: `3.5`
- Sampler: `euler_ancestral_cfg_pp`
- Scheduler: `sgm_uniform`
- LoRA strength: `1.0`

GUI quick presets:

- `Standard`: default size and sampler settings with optional enhancement stages disabled.
- `Reference Quality`: higher-detail preset with tiled upscale, tiled VAE, and face detailer settings enabled.

## Wildcards

Prompt wildcard files live under `wildcards\*.txt`. Tokens use `__name__` and read `wildcards\name.txt`.

The included wildcard files may be derived from ComfyUI Impact Pack wildcard files. Keep attribution and license notices with redistributed builds.

## Release Boundary

Current release target: source-checkout alpha.

Included:

- Python package source under `src\anima_app`.
- Vendored runtime source under `vendor\anima_runtime`.
- Selected vendored Python packages under `vendor\python_packages`.
- Root GUI launcher for Windows users.
- Public docs, notices, and wildcard files.

Excluded:

- Base model weights and alternate checkpoints.
- Detector weights.
- LoRA files.
- Input images.
- Generated output images and manifests.

Not finalized:

- Standalone binary packaging.
- Final wheel redistribution policy for vendored runtime assets.
- Automated public release packaging beyond GitHub source archives.

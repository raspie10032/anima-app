# Anima APP Lightweight Design

## Goal

Build `C:\Users\seine\Documents\Anima APP` as a lightweight standalone Anima image-generation app by reusing the verified `AnimaStudio` core and avoiding a live ComfyUI runtime dependency.

## Boundaries

- `Anima APP` is a separate image-generation app, not a GemmAnima mode.
- `E:\ComfyUI_sage\ComfyUI` is a development-time source for copied runtime code and model assets.
- Runtime model files live under `C:\Users\seine\Documents\Anima APP\models`.
- The app must not require starting a ComfyUI server.
- Local Anima runs default to GPU 0 through `CUDA_VISIBLE_DEVICES=0` unless the user changes that.
- The fixed image pipeline order is `base render -> high-res fix/upscale -> face detailer`.

## Product Surface

The first usable surface is CLI-first:

- `health`: report model, runtime, detector, LoRA, and output-directory readiness.
- `models inventory`: scan the ComfyUI-style development model source.
- `models copy-profile anima-t2i`: copy the required Anima base model, Qwen text encoder, and VAE into the project.
- `models import-lora`: copy a LoRA into the project-local model tree.
- `t2i`: generate a PNG from a prompt and write a manifest.

After the CLI path is verified with real PNG output, a local web GUI can be added with the same backend. The GUI should expose a simple default generation form and keep advanced settings compact.

## Architecture

The app is a Python package named `anima_app`.

- `config.py` owns project paths and source paths.
- `assets.py` owns model inventory, profile copying, and LoRA import.
- `requests.py` owns immutable request settings.
- `manifests.py` owns JSON output records.
- `health.py` owns readiness reporting.
- `gpu.py` owns CUDA process-environment defaults.
- `runtime/comfy_bootstrap.py` wires the vendored Comfy-derived runtime to project-local model folders.
- `runtime/t2i.py` owns base Anima rendering.
- `runtime/pipeline.py` owns stage orchestration and output validation.
- `runtime/face_detailer.py` owns optional face-detailer masking and repaint orchestration.
- `cli.py` owns command-line entry points.
- `web.py` owns the later local GUI/API.

The initial runtime may vendor a working subset copied from `AnimaStudio\vendor\anima_runtime`. Slimming happens after real PNG smoke tests pass, so dependency removal does not break known-good generation.

## Required Model Assets

The first asset profile is `anima-t2i`:

- `diffusion_models\anima-base-v1.0.safetensors`
- `text_encoders\qwen_3_06b_base.safetensors`
- `vae\qwen_image_vae.safetensors`

These files are copied from `E:\ComfyUI_sage\ComfyUI\models` into the project-local `models` tree. Symlinks and live source references are out of scope.

## Verification

The practical completion bar is evidence-based:

- Unit tests pass.
- `python -m anima_app.cli health --json` reports readiness after model copy.
- `python scripts\smoke_anima_app.py --dry-run` writes a manifest.
- `python scripts\smoke_anima_app.py --require-checks` generates a real PNG under `outputs\images`.
- The manifest records output path, request values, stage metadata, warnings, model root, and provenance.
- Later GUI verification must hit `/api/generate`, return HTTP 200, and serve the generated PNG.

## Risks

- Vendored Comfy-derived runtime can be larger than desired at first. The mitigation is to slim only after a verified real-render baseline.
- CUDA device selection must be set at process start for GUI/server flows. The launcher must set `CUDA_VISIBLE_DEVICES=0`.
- Face-detailer dependencies can add licensing and install complexity. Base T2I must keep working even when optional detector dependencies are missing.

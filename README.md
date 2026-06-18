# Anima APP

Lightweight local Anima image-generation app with a browser GUI.

Anima APP packages a focused Anima text-to-image workflow around a local, project-owned `models` folder. It does not require launching a ComfyUI server for normal generation.

## Reference Map

- [docs/REFERENCES.md](docs/REFERENCES.md): public source references, model asset layout, wildcard attribution, and release boundaries.
- [NOTICE.md](NOTICE.md): third-party runtime, optional detector runtime, LoRA redistribution, and wildcard notices.
- [docs/ACCEPTANCE.md](docs/ACCEPTANCE.md): accepted feature checklist.

## Install

```powershell
python -m pip install -e .
```

Optional face-detailer support:

```powershell
python -m pip install -e ".[face-detailer]"
```

## Model Assets

Prepare the base Anima T2I profile:

```powershell
$env:PYTHONPATH='src'
python -m anima_app.cli models copy-profile anima-t2i
```

By default, the app downloads the base profile from Hugging Face when a configured local mirror is not available. To use a local model mirror, set:

```powershell
$env:ANIMA_APP_MODEL_SOURCE='path\to\comfyui\models'
```

Required base files are copied into the project-local `models` tree:

- `models\diffusion_models\anima-base-v1.0.safetensors`
- `models\text_encoders\qwen_3_06b_base.safetensors`
- `models\vae\qwen_image_vae.safetensors`

Additional Anima-family diffusion checkpoints can be placed under `models\diffusion_models` and selected by relative `.safetensors` path.

Optional face-detailer detector files are downloaded automatically when a configured local detector folder is not available:

```powershell
$env:PYTHONPATH='src'
python -m anima_app.cli models copy-profile face-detailer-detectors
```

To use a local detector mirror instead, set `ANIMA_APP_FACE_DETECTOR_SOURCE` before running the same command.

Local LoRA files can be imported into `models\loras` and stacked in the GUI:

```powershell
$env:PYTHONPATH='src'
python -m anima_app.cli models import-lora "path\to\style.safetensors"
python -m anima_app.cli models loras
```

## Run The GUI

On Windows, double-click:

```powershell
.\Run-AnimaAPP-GUI.cmd
```

Or launch from a terminal:

```powershell
$env:ANIMA_APP_CUDA_VISIBLE_DEVICES='0'
$env:PYTHONPATH='src'
python -m anima_app.cli serve --host 127.0.0.1 --port 0 --open
```

The server chooses a free local port and opens the browser UI.
The Windows launcher sets `CUDA_VISIBLE_DEVICES` from `ANIMA_APP_CUDA_VISIBLE_DEVICES`, defaulting to CUDA device `0`, before Python starts.

## Defaults

CLI, API, and GUI generation defaults:

- Size: `832x1216`
- Steps: `20`
- CFG: `3.5`
- Sampler: `euler_ancestral_cfg_pp`
- Scheduler: `sgm_uniform`
- LoRA default strength: `1.0`

The browser GUI uses Korean labels by default while keeping API field names and request values stable.

Generated PNG files embed A1111-style `parameters` metadata, and app-managed outputs share a searchable filename stem with their generation-info JSON files.

## Wildcards

Prompt wildcards are read from root-level `wildcards\*.txt` files. Use `__name__` in prompts to expand `wildcards\name.txt`.

Prompt presets are stored separately under `wildcards\presets\*.txt`. Use `__presets/name__` in prompts, or use the GUI `Insert Preset` control, to expand `wildcards\presets\name.txt`.

Supported modes are `random`, `sequential`, and `reverse`. When no wildcard token is present, wildcard expansion is a no-op.
The GUI wildcard and preset insert buttons wrap inserted tokens with comma separators so they stay separated from surrounding prompt tags.

Wildcard values can contain other wildcard tokens. For example, `wildcards\character.txt` can contain `qiqi, __hair__, {soft smile|serious expression}`, and the app expands nested tokens before generation.

Inline random choices use `{choice A|choice B|choice C}` syntax inside prompts or wildcard files. Inline choices always choose randomly, while file-backed wildcard tokens still follow the selected `random`, `sequential`, or `reverse` mode. The prompt block includes a Preview Expansion button that expands the current prompt without starting a GPU generation job and reports missing files or recursive wildcard cycles.

## Auto Queue

The GUI can run a fixed auto queue count or Infinity mode through the server-side job queue. Once queued, jobs continue while the Python server process is alive even if the browser-side loop is interrupted.

Stop cancels queued or waiting jobs immediately and sends a runtime interrupt request for the running job when the Comfy runtime is loaded. Some GPU work may finish its current internal step before the running job stops.

## Update Check

The Runtime Status panel can check GitHub for newer Anima APP releases. The check reads `raspie10032/anima-app` releases first and falls back to tags when no release exists.

Update checks are read-only. The app does not run `git pull`, download archives, replace files, or update models automatically.

## History And Compare Grid

Click a history item to load that generation's final image in the center result panel. When a generation has intermediate outputs, the result panel shows a Compare Stages button for Original, Upscale, and Face Detailer image comparison.

## Runtime Boundary

- Runtime model files live under this checkout's `models` folder.
- The app does not read model files from an external ComfyUI folder during generation.
- The app does not launch or depend on a live ComfyUI server.
- Local model weights, detector weights, LoRA files, input images, and generated outputs are ignored by git and are not part of the public release.
- Set `ANIMA_APP_CUDA_VISIBLE_DEVICES` when you need to choose a CUDA device for Anima APP. Direct CLI runs also respect an existing `CUDA_VISIBLE_DEVICES` value when the app-specific variable is not set.

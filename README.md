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

SAM3 concept masks are optional and prepared separately because `facebook/sam3` is a gated Hugging Face model. After your Hugging Face account has access and `hf auth login` is configured:

```powershell
$env:PYTHONPATH='src'
python -m anima_app.cli models copy-profile sam3-detector --source download
```

The GUI can create SAM3 text-prompt masks for the current result image, such as `face`, `hair`, `dress`, or `clothes`, and writes mask/overlay PNG files under `outputs\images`. After selecting a mask, the result panel can expand the mask with dilation, soften it with feathering, and run masked inpaint with a user-selected method:

- `Noise mask`: keeps the original crop latent and limits sampling to the mask. This is the default for non-inpaint checkpoints.
- `VAE inpaint`: blanks the masked area before VAE encoding. This is available for comparison but usually needs an inpaint-friendly model.
- `Crop i2i`: regenerates the crop and composites it through the mask.

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

## Optional LLM Runtime Bridge

Anima APP can proxy an already-running tinylm/Gemma4 worker for prompt or planning features. Start the LLM worker separately, then point Anima APP at it:

```powershell
$env:ANIMA_LLM_RUNTIME_URL='http://127.0.0.1:8820'
$env:PYTHONPATH='src'
python -m anima_app.cli serve --host 127.0.0.1 --port 0 --open
```

The server exposes:

- `GET /api/llm/status`: reports whether the LLM bridge is configured and returns worker health.
- `POST /api/llm/generate`: forwards a tinylm-compatible JSON request and returns `completion_text`, metrics, and the raw runtime payload.

When the bridge is configured, the prompt tools panel shows an `LLM 보정` button. It sends the current prompt to `/api/llm/generate` and replaces the prompt field with the returned `completion_text`.

When `ANIMA_LLM_RUNTIME_URL` is not set, the image-generation app still runs normally and the LLM bridge reports `configured: false`.

## Low-VRAM High-Resolution Mode

Use the `low_vram_highres` memory profile when the target machine has limited VRAM but still needs a larger final image. The profile keeps the base latent workflow unchanged, automatically enables tiled latent upscale and tiled VAE decode, and fixes the high-resolution upscale pass at 10 steps so the high-resolution stages stay predictable on 8GB-class GPUs.

The default `auto` profile probes the local runtime once, caches the decision in `outputs\runtime_profile_cache.json`, and reuses that decision on later launches. GPUs in the 8GB VRAM class select `low_vram_highres`; larger GPUs select `balanced` unless the request explicitly chooses another profile.

CLI dry-run example:

```powershell
$env:PYTHONPATH='src'
python -m anima_app.cli t2i --prompt "anime portrait" --memory-profile low_vram_highres --dry-run
```

In the GUI, select `저VRAM 고해상도` from `VRAM 프로필` or press the `저VRAM 고해상도` preset button. Manifests record the selected `memory_profile`, effective upscale settings, VAE decode mode, final high-resolution dimensions, stage elapsed times, and CUDA memory peaks when CUDA metrics are available.

## Defaults

CLI, API, and GUI generation defaults:

- Size: `832x1216`
- Steps: `20`
- Upscale steps: `10`
- Face detailer steps: `10`
- Upscale/VAE tile size: `128`
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

## Prompt Autocomplete

Prompt autocomplete reads a ComfyUI Custom Scripts-style `autocomplete.txt` file using `tag,count` lines. Place the file at the project root as `autocomplete.txt`, or point the app at another file:

```powershell
$env:ANIMA_APP_AUTOCOMPLETE_SOURCE='path\to\autocomplete.txt'
```

The server loads the file into memory when the GUI starts and refreshes the cache if the file changes. Autocomplete is available in the main prompt, negative prompt, and masked-inpaint prompt fields.

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
- The optional LLM bridge does not launch Gemma4 itself; `ANIMA_LLM_RUNTIME_URL` must point at a separately managed local worker.
- Local model weights, detector weights, LoRA files, input images, and generated outputs are ignored by git and are not part of the public release.
- Set `ANIMA_APP_CUDA_VISIBLE_DEVICES` when you need to choose a CUDA device for Anima APP. Direct CLI runs also respect an existing `CUDA_VISIBLE_DEVICES` value when the app-specific variable is not set.

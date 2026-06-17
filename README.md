# Anima APP

Lightweight standalone Anima image-generation app.

This project is being built from the verified `AnimaStudio` core while keeping `E:\ComfyUI_sage\ComfyUI` as a development-time source only. Runtime model assets live in this project's own `models` tree; the Anima base profile can be copied locally or downloaded from Hugging Face.

Release/path references, current quality presets, local model sources, LoRA checkpoints, and latest evidence are tracked in [docs/REFERENCES.md](docs/REFERENCES.md).

## Reference Map

- [docs/REFERENCES.md](docs/REFERENCES.md): local/runtime sources, model asset paths, LoRA references, GPU boundary, quality presets, recent verification evidence, and release boundary.
- [NOTICE.md](NOTICE.md): third-party runtime, ComfyUI-derived code, optional detector runtime, LoRA redistribution, and Impact Pack wildcard notices.
- [docs/RELEASE_CHECKLIST.md](docs/RELEASE_CHECKLIST.md): source-checkout release checklist and smoke commands.
- [docs/PACKAGING_PLAN.md](docs/PACKAGING_PLAN.md): wheel and source-checkout packaging boundary.
- [docs/ACCEPTANCE.md](docs/ACCEPTANCE.md): accepted behavior and verification evidence history.
- [docs/IMPROVEMENT_PLAN.md](docs/IMPROVEMENT_PLAN.md): next improvement queue and product direction notes.

## Current Commands

Install the source checkout:

```powershell
python -m pip install -e .
```

Install optional face-detailer detector runtime support:

```powershell
python -m pip install -e ".[face-detailer]"
```

Run tests:

```powershell
python -m pytest tests -q
```

Inspect runtime health:

```powershell
$env:PYTHONPATH='src'
python -m anima_app.cli health --json
```

Prepare the first Anima T2I model profile. Auto mode copies from `E:\ComfyUI_sage\ComfyUI\models` when all files are present, otherwise downloads from Hugging Face:

```powershell
$env:PYTHONPATH='src'
python -m anima_app.cli models copy-profile anima-t2i
```

Force a specific source when needed:

```powershell
$env:PYTHONPATH='src'
python -m anima_app.cli models copy-profile anima-t2i --source huggingface
python -m anima_app.cli models copy-profile anima-t2i --source local
```

Copy local face-detailer detector assets into `models\detectors`:

```powershell
$env:PYTHONPATH='src'
python -m anima_app.cli models copy-profile face-detailer-detectors
```

Import a local LoRA into the project-local model tree:

```powershell
$env:PYTHONPATH='src'
python -m anima_app.cli models import-lora "D:\ComfyUI_Shared_Models\loras\anima_RSC.safetensors"
python -m anima_app.cli models loras
```

List local Anima-family diffusion checkpoints available for selection:

```powershell
$env:PYTHONPATH='src'
python -m anima_app.cli models checkpoints
```

Record a dry-run T2I request and manifest:

```powershell
$env:PYTHONPATH='src'
python -m anima_app.cli t2i --prompt "anime portrait" --negative "low quality" --seed 52 --dry-run
```

Use another project-local checkpoint by placing it under `models\diffusion_models` and passing its relative `.safetensors` path:

```powershell
$env:PYTHONPATH='src'
python -m anima_app.cli t2i --checkpoint "variants\anima-alt.safetensors" --prompt "anime portrait" --negative "low quality" --seed 52 --dry-run
```

The CLI, API, and GUI default generation settings are `832x1216`, `20` steps, CFG `3.5`, sampler `euler_ancestral_cfg_pp`, and scheduler `sgm_uniform` when those fields are not supplied.

Output files use searchable default names. Real PNGs and their manifests share the same stem when the renderer creates a new app-managed output; dry-run manifests include `_dry` in the stem:

```text
YYYYMMDD-HHMMSS_s<seed|random>_<width>x<height>_<mode>_<prompt-slug>_<hash>.png
YYYYMMDD-HHMMSS_s<seed|random>_<width>x<height>_<mode>_<prompt-slug>_<hash>.json
```

Generated PNGs also store an A1111-style `parameters` text chunk containing the final prompt, negative prompt, steps, sampler, scheduler, CFG, seed, size, selected model checkpoint, and Anima-specific LoRA/upscale/tiled VAE/wildcard fields. Dry-run manifests record the same metadata preview under `png_metadata.parameters`.

Use prompt wildcards from root-level `wildcards\*.txt` files. Tokens use `__name__` and read `wildcards\name.txt`; blank lines and lines starting with `#` are ignored:

```powershell
$env:PYTHONPATH='src'
python -m anima_app.cli t2i --prompt "anime portrait, __codex_smoke__" --width 512 --height 768 --steps 1 --seed 101 --wildcards random --dry-run
```

Wildcard modes are `random`, `sequential`, and `reverse`; `random` is the default. When the prompt contains no `__name__` wildcard tokens, wildcard expansion is a no-op. Sequential and reverse modes persist their next index in `outputs\wildcard_state.json`. In the GUI, use `Insert Wildcard` to choose a file from `wildcards` and insert its `__name__` token into the prompt field at the current cursor position.

Run the dry-run smoke check:

```powershell
python scripts\smoke_anima_app.py --dry-run --require-checks
```

Run the source-checkout release smoke. This verifies release files, health JSON, dry-run generation checks, and the full test suite without requesting a real GPU render:

```powershell
python scripts\release_smoke.py --include-tests
```

Run the packaging dry-run proof. This builds and inspects a wheel under `outputs\package_dry_run` and records the standalone layout plan without bundling model or output artifacts:

```powershell
python scripts\package_dry_run.py
```

Start the local GUI/API server for real generation on GPU 0:

```powershell
$env:PYTHONPATH='src'
python -m anima_app.cli serve --host 127.0.0.1 --port 0 --open
```

Use manifest-only dry-run mode when you want to test the GUI without rendering:

```powershell
$env:PYTHONPATH='src'
python -m anima_app.cli serve --host 127.0.0.1 --port 0 --dry-run-default --open
```

The server chooses a free local port, opens the GUI in your browser, and accepts `POST /api/generate`. Runtime readiness, model/detector readiness cards with prepare actions, local checkpoint and LoRA inventories, a left control frame with grouped accordion controls, a central image workspace focused on the current image, a collapsible right-frame Runtime Status panel, a right history frame, collapsible reference/upscale/face-detailer controls, red/off and green/on toggle switches for binary enhancement options, quick standard/reference-quality presets, checkpoint/sampler/scheduler controls, GUI LoRA selection, wildcard mode selection/insertion, browser-side auto queue with count/seed/delay/stop controls, backend-polled generation stage progress that auto-hides after successful completion, stale output clearing, readable current-result summaries, collapsed manifest JSON, I2I/upscale/tiled upscale/tiled VAE/face-detailer request options, reusable saved settings with import/export, filtered thumbnail history/gallery, manifest export/delete controls, output PNG links, and applying a manifest back into the form are available in the GUI and through `GET /api/health`, `GET /api/readiness`, `POST /api/models/prepare`, `GET /api/checkpoints`, `POST /api/loras/import`, `GET /api/loras`, `GET /api/wildcards`, `GET /api/presets`, `POST /api/presets`, `GET /api/presets/export`, `POST /api/presets/import`, `GET /api/history`, `GET /api/progress/<id>`, `GET /api/manifests/<name>`, and `DELETE /api/manifests/<name>`.

On Windows, real-generation GUI mode can be launched by double-clicking:

```powershell
.\Run-AnimaAPP-GUI.cmd
```

The dry-run GUI server can be launched by double-clicking:

```powershell
.\Run-AnimaAPP-GUI-DryRun.cmd
```

The release smoke can also be launched by double-clicking:

```powershell
.\Run-AnimaAPP-ReleaseSmoke.cmd
```

Record a dry-run high-res/upscale request without using the GPU:

```powershell
$env:PYTHONPATH='src'
python -m anima_app.cli t2i --prompt "anime portrait" --negative "low quality" --width 512 --height 768 --steps 1 --cfg 1.0 --seed 56 --upscale --upscale-scale 1.5 --upscale-steps 2 --upscale-denoise 0.25 --upscale-method bicubic --dry-run
```

Record a dry-run tiled upscale plus tiled VAE request without using the GPU:

```powershell
$env:PYTHONPATH='src'
python -m anima_app.cli t2i --prompt "anime portrait" --negative "low quality" --width 512 --height 768 --steps 1 --cfg 1.0 --seed 57 --upscale --upscale-scale 1.5 --upscale-tiled --upscale-tile-size 64 --upscale-overlap 8 --vae-decode tiled --vae-tile-size 96 --vae-overlap 16 --dry-run
```

Record a dry-run face-detailer request. Dry-run manifests keep the settings and mark the stage as skipped because no GPU runtime is executed:

```powershell
$env:PYTHONPATH='src'
python -m anima_app.cli t2i --prompt "anime portrait" --width 512 --height 768 --steps 1 --face-detailer --face-detector "bbox/face_yolov8m.pt" --face-threshold 0.45 --dry-run
```

Run a strict real-render base T2I smoke check after copying models:

```powershell
$env:PYTHONPATH='src'
$env:CUDA_VISIBLE_DEVICES='0'
python scripts\smoke_anima_app.py --prompt "anime portrait, clean lineart" --negative "low quality" --width 512 --height 768 --steps 1 --cfg 1.0 --seed 53 --require-checks
```

Run a strict LoRA smoke check:

```powershell
$env:PYTHONPATH='src'
$env:CUDA_VISIBLE_DEVICES='0'
python scripts\smoke_anima_app.py --prompt "anime portrait, clean lineart, RSC style" --negative "low quality" --width 512 --height 768 --steps 1 --cfg 1.0 --seed 54 --lora "anima_RSC.safetensors|0.5|0.5" --require-checks
```

Run a strict I2I smoke check:

```powershell
$env:PYTHONPATH='src'
$env:CUDA_VISIBLE_DEVICES='0'
python scripts\smoke_anima_app.py --prompt "anime portrait variation, clean lineart" --negative "low quality" --width 512 --height 768 --steps 1 --cfg 1.0 --seed 55 --image "inputs\i2i_reference_512x768.png" --denoise 0.35 --require-checks
```

Run a strict face-detailer smoke check after copying detector assets:

```powershell
$env:PYTHONPATH='src'
$env:CUDA_VISIBLE_DEVICES='0'
python scripts\smoke_anima_app.py --prompt "masterpiece anime key visual, close-up bust portrait, silver-haired android shrine maiden, layered translucent kimono jacket, iridescent circuit embroidery, rain-slick neon alley, holographic koi lanterns, detailed symmetrical eyes, intricate eyelashes, glossy lips, subtle blush, complex hair strands, soft rim light, cinematic depth of field, clean lineart, painterly cel shading, high detail" --negative "low quality, blurry, bad anatomy, deformed face, asymmetrical eyes, extra limbs, text, watermark, jpeg artifacts, muddy colors, overexposed, underexposed" --width 768 --height 1152 --steps 8 --cfg 1.5 --seed 605 --lora "anima_RSC.safetensors|0.45|0.45" --face-detailer --face-threshold 0.08 --face-steps 2 --face-denoise 0.16 --face-exclude-forehead 0.12 --require-checks
```

## Implementation Status

- Package foundation, path contracts, asset profile copying, checkpoint selection, LoRA import/list, request validation, manifest writing, health JSON, CLI dry-run, renderer output validation, dry-run smoke checks, vendored runtime bootstrap, real base T2I rendering, real single-LoRA rendering, and real I2I rendering are implemented.
- Source-checkout release smoke is implemented in `scripts\release_smoke.py`, with a double-clickable Windows wrapper and checklist in `docs\RELEASE_CHECKLIST.md`.
- Packaging dry-run proof is implemented in `scripts\package_dry_run.py`, with the wheel/standalone boundary documented in `docs\PACKAGING_PLAN.md`.
- `models copy-profile anima-t2i` supports `--source auto|local|huggingface`; auto mode downloads the base Anima profile from Hugging Face when the local development source is incomplete.
- Local GUI/API server, `GET /api/health`, `GET /api/readiness`, `POST /api/models/prepare`, `GET /api/checkpoints`, `POST /api/loras/import`, `GET /api/loras`, `GET /api/wildcards`, `GET /api/presets`, `POST /api/presets`, `GET /api/presets/export`, `POST /api/presets/import`, `GET /api/history`, `GET /api/progress/<id>`, `GET /api/manifests/<name>`, `DELETE /api/manifests/<name>`, manifest-to-form replay, manifest export/delete controls, model/detector readiness panel, browser-side auto queue, backend-polled generation stage progress panel, central current-result workspace, collapsible right-frame Runtime Status panel, collapsed manifest JSON, right-side filtered thumbnail history/gallery, grouped accordion GUI controls, collapsible optional sections, stale preview/link clearing, GUI quick quality presets, GUI checkpoint/sampler/scheduler controls, GUI LoRA selection/strength payloads, GUI wildcard mode/insertion controls, detailed GUI I2I/upscale/face-detailer payloads, saved-settings import/export, real `POST /api/generate`, dry-run server mode, output PNG URL mapping/linking, dynamic port launch, browser open, and double-clickable Windows launchers are implemented and covered by CPU tests.
- Root `wildcards\*.txt` prompt expansion is implemented for CLI, smoke, GUI, and API flows with `random`, `sequential`, and `reverse` modes, and manifests record original prompt text plus selected wildcard values.
- Searchable default output naming is implemented for app-managed outputs and dry-run manifests, and generated PNGs embed A1111-style `parameters` metadata while manifests retain the same text under `png_metadata.parameters`.
- Tiled VAE decode control is implemented for CLI, smoke, GUI, and API flows with `auto`, `tiled`, and `standard` modes. Tiled latent upscale is available for the high-res/upscale path with tile size and overlap controls.
- High-res/upscale CLI options are wired and verified with a real 4070-only PNG smoke. The real GUI/API generation path is verified with HTTP 200 plus a served PNG URL.
- Face detailer request options are wired through CLI/API/smoke paths. The real renderer now copies validated detector assets, builds YOLO/SAM masks, can exclude the upper forehead/hairline region from the repaint mask, repaints the detected crop through the local Comfy sampler/VAE path, composites the result, and records completed or skipped stage metadata.

## Runtime Boundary

- Do not launch a ComfyUI server for this app.
- Do not read model files from `E:\ComfyUI_sage\ComfyUI\models` during generation.
- Copy or download required base model files into `models`; additional selectable checkpoints must live under `models\diffusion_models` and are referenced by relative `.safetensors` path.
- Copy face-detailer detector files into `models\detectors`; the copy command rejects tiny placeholder `.pt` files and can fall back to known local detector sources.
- Face detailer needs the optional `face-detailer` extra, which installs Ultralytics. Without that extra, base generation still works and enabled face detailer runs are recorded as skipped with a manifest warning.
- Copy local LoRA files into `models\loras`; do not redistribute private/local training artifacts unless permission and license terms are confirmed.
- Local GPU runs must start with `CUDA_VISIBLE_DEVICES=0` for the RTX 4070 Ti SUPER. Do not use GPU 1 / RTX 5060 for this app.
- The current alpha release target is a source checkout with the vendored runtime tree present. Wheel/standalone binary packaging has not been finalized yet.

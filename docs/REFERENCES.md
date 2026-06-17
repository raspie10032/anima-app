# Anima APP References

This file keeps local paths, source references, dependency notes, and latest validated evidence in one place.

## Runtime Sources

- Project root: `C:\Users\seine\Documents\Anima APP`
- Development model source: `E:\ComfyUI_sage\ComfyUI\models`
- Hugging Face model source: `circlestone-labs/Anima`
- Vendored runtime: `vendor\anima_runtime`
- ComfyUI is a development-time source and vendored runtime base, not a live server dependency.
- Runtime model root: `models`

## Model Assets

`models copy-profile anima-t2i` uses `--source auto` by default. Auto mode copies from the development source when all required files are present; otherwise it downloads from Hugging Face:

- Repo: `circlestone-labs/Anima`
- Remote folder: `split_files`

Required local files:

- `diffusion_models\anima-base-v1.0.safetensors`
- `text_encoders\qwen_3_06b_base.safetensors`
- `vae\qwen_image_vae.safetensors`

Generation must read these files from the project-local `models` tree.

Selectable alternate checkpoints:

- Put additional Anima-family diffusion `.safetensors` files under `models\diffusion_models`.
- Select them by relative path, for example `variants\anima-alt.safetensors`.
- The base text encoder and VAE still come from the `anima-t2i` profile unless the runtime is explicitly extended later.
- Absolute paths, parent traversal, and non-`.safetensors` checkpoint values are rejected.

Inventory command:

```powershell
$env:PYTHONPATH='src'
python -m anima_app.cli models checkpoints
```

## Face Detailer Assets

`models copy-profile face-detailer-detectors` copies validated detector files into `models\detectors`.

Expected detector files:

- `face_yolov8n.pt`
- `full_eyes_detect_v1.pt`
- `sam_b.pt`

Configured detector source order:

- Primary: `C:\Users\seine\Desktop\NAI-FaceDetailer\models\detectors`
- Fallback: `C:\Users\seine\Documents\AnimaStudio\models\detectors`
- Fallback: `C:\Users\seine\Documents\Anima-Gemma4-Fusion-Multimodal\models\detectors`

The copy command rejects tiny placeholder `.pt` files and uses the first valid local source.

## LoRA References

Current local LoRA examples:

- Final RSC: `models\loras\anima_RSC.safetensors`
- RSC epoch 4: `models\loras\anima_RSC-000004.safetensors`

Epoch checkpoint source:

- `C:\Users\seine\Documents\Anima LoRA Train\upstream\anima_lora\output\ckpt\anima_RSC-000004.safetensors`

Local LoRA files are ignored by git and should not be redistributed without source license confirmation.

## Dependencies

Base install:

```powershell
python -m pip install -e .
```

The base install includes `huggingface_hub` for automatic Anima model downloads.

Face detailer runtime install:

```powershell
python -m pip install -e ".[face-detailer]"
```

The optional `face-detailer` extra installs Ultralytics. Without it, base generation still works and enabled face-detailer runs are recorded as skipped with a warning.

## GPU Boundary

- Use `CUDA_VISIBLE_DEVICES=0` for RTX 4070 Ti SUPER runs.
- Do not use GPU 1 / RTX 5060 for Anima APP generation unless the user explicitly reverses that rule.
- GUI launchers must set CUDA visibility before the Python process starts.

## Quality Preset Reference

Default CLI/API/GUI generation settings: `832x1216`, `20` steps, CFG `3.5`, sampler `euler_ancestral_cfg_pp`, scheduler `sgm_uniform`, checkpoint `anima-base-v1.0.safetensors`.

Default LoRA strength is `1.0` for both model and clip strength in the CLI/API parser and the GUI LoRA Strength field.

GUI generation progress shows a sticky stage panel while `POST /api/generate` is in flight. The GUI sends a `progress_id` and polls `GET /api/progress/<id>` for backend stage updates; after the response returns, the panel is finalized from manifest `stages` and auto-hides after successful completion. Stage rows use color markers for pending/completed/skipped states and keep visible status text only for running or failed rows.

GUI auto queue is browser-side and reuses the same `POST /api/generate` flow as the main Generate button. It supports queue count, seed modes `fixed` / `increment` / `random`, optional delay seconds, and Stop as "stop after the current job finishes."

Windows GUI launchers:

- `Run-AnimaAPP-GUI.cmd`: real generation mode on `CUDA_VISIBLE_DEVICES=0`.
- `Run-AnimaAPP-GUI-DryRun.cmd`: manifest-only dry-run mode for safe UI checks.

Repeated GUI playtest notes: generation start clears stale preview/output link/result state, failed requests show `Failed: <reason>`, successful requests open the generated manifest detail, and quick presets restore the default prompt/negative prompt when the current fields are blank.

Intuitive GUI pass: the GUI is split into a left control frame, central image workspace, and right history frame. The left frame groups related controls into fixed accordions for prompt/generate, model/style, image settings, enhancement, prompt tools, and saved settings; the center keeps the current result and image preview as the primary surface; runtime/model readiness status lives in a collapsed Runtime Status panel above the right history; binary enhancement options remain red/off and green/on toggle switches.

Result panel pass: the center workspace shows a compact current-result summary first, omits the long output path from summary cards, and keeps raw manifest JSON collapsed under `Manifest JSON`. Dry-run outputs must not show the output link. Right-frame history cards expose manifest open, output open when available, manifest JSON export, and delete for managed manifest/output pairs.

GUI quick presets:

- `Standard`: `832x1216`, 20 steps, CFG `3.5`, `euler_ancestral_cfg_pp + sgm_uniform`, upscale off, face detailer off.
- `Reference Quality`: `768x1152`, 24 steps, CFG `3.5`, `euler_ancestral_cfg_pp + sgm_uniform`, tiled `1.5x` upscale, tiled VAE, and face detailer reference settings.

Current high-quality CLI baseline:

```powershell
$env:PYTHONPATH='src'
$env:CUDA_VISIBLE_DEVICES='0'
python scripts\smoke_anima_app.py --prompt "masterpiece anime illustration, RSC style, close-up bust portrait, luminous silver-haired cyber shrine maiden, transparent raincoat over ornate kimono, neon reflections on wet skin, holographic talismans, glowing koi-shaped lanterns, complex layered hair strands, crystalline hair ornaments, detailed sparkling eyes, sharp eyelashes, delicate blush, soft lips, cinematic neon alley, volumetric mist, rim lighting, intricate lineart, elegant color harmony, high detail, crisp focus, finely detailed face, clean forehead, smooth glabella" --negative "low quality, blurry, bad anatomy, deformed face, asymmetrical eyes, crossed eyes, extra fingers, extra limbs, text, watermark, jpeg artifacts, muddy colors, flat lighting, oversaturated skin, soft blur, out of focus, forehead wrinkles, glabella wrinkles, double lines between eyebrows, duplicated hairline" --width 768 --height 1152 --steps 24 --cfg 3.5 --sampler euler_ancestral_cfg_pp --scheduler sgm_uniform --seed 609 --lora "anima_RSC-000004.safetensors|1|1" --upscale --upscale-scale 1.5 --upscale-steps 10 --upscale-denoise 0.28 --upscale-method bicubic --upscale-tiled --upscale-tile-size 64 --upscale-overlap 8 --vae-decode tiled --vae-tile-size 96 --vae-overlap 16 --face-detailer --face-threshold 0.08 --face-steps 4 --face-denoise 0.10 --face-feather 12 --face-padding 24 --face-crop-scale 1.35 --face-exclude-forehead 0.12 --require-checks
```

Important quality settings:

- Sampler: `euler_ancestral_cfg_pp`
- Scheduler: `sgm_uniform`
- Base: `768x1152`, 24 steps, CFG `3.5`
- Upscale: `1.5x`, 10 steps, denoise `0.28`
- VAE decode: tiled, tile size `96`, overlap `16`
- Face detailer: 4 steps, denoise `0.10`, feather `12`, crop scale `1.35`, forehead exclude `0.12`

## Latest Evidence

Fresh checks:

- `python -m pytest tests -q` -> `118 passed`
- `python scripts\release_smoke.py --include-tests` -> `status=passed`, static release checks passed, embedded pytest `118 passed`
- Release-smoke health command -> `models.ready=true`, `missing=[]`, `loras.count=2`
- Release-smoke dry-run command -> `status=dry_run`, `manifest_exists=true`, `warnings=[]`
- Checkpoint inventory command -> `count=1`, `items[0].relative_path=anima-base-v1.0.safetensors`
- HTTP endpoint smoke -> `/api/checkpoints` HTTP `200`, dry-run `/api/generate` HTTP `200`, response/manifest checkpoint `anima-base-v1.0.safetensors`, PNG metadata preview includes `Model: anima-base-v1.0.safetensors`
- Real GUI server mode smoke -> process command has no `--dry-run-default`, `/api/generate` returned `status=generated`, output exists at `outputs\images\20260617-205803_s920617_512x768_t2i_anime-portrait-clean-lineart-real-gui-smoke_5d46b8.png`
- Overlap guard smoke -> duplicate Python GUI server stopped, active server is `http://127.0.0.1:9863`, only one `anima_app.cli serve` process remains, dry-run `/api/generate` responds, and tests cover HTTP `409` for overlapping generation.
- Browser dry-run auto queue on port `11527`: queue count `2`, seed mode `increment`, seeds `700` and `701`, status `Queue complete. Done 2, failed 0.`, no console warnings/errors, no horizontal overflow.
- Browser dry-run sidebar reorder on port `4859`: superseded by the fixed left control-frame accordion layout.
- Browser dry-run three-frame layout on port `13116`: left control frame, center image workspace, right history frame, and six control accordions all rendered; `Generate` returned `Dry run`, history updated to `8 / 8 shown`, output link stayed hidden for dry-run, Prompt Tools accordion toggled closed->open, mobile width had no horizontal overflow (`scrollWidth=viewportWidth=375`), and console warnings/errors were empty. Superseding GUI cleanup moved runtime/readiness cards to a collapsed right-frame Runtime Status panel and kept the central top area reserved for active generation progress only.
- Browser dry-run center cleanup on port `8714`: `topStatusExists=false`, collapsed right-frame `Runtime Status` exists and is closed by default, initial result summary shows only `Status`, `Generate` returned `Dry run`, completed generation stages auto-hid, result summary omitted `Output`, output link stayed hidden for dry-run, history showed `8 / 8 shown`, console warnings/errors were empty, mobile viewport had no horizontal overflow, and the test server was stopped afterward.
- Browser dry-run stage text cleanup on port `7844`: completed/skipped stage rows kept color markers and accessible `aria-label` status, but visible status text was empty; success header did not show `Complete`; dry-run ended with `Dry run`, generation panel auto-hid, console warnings/errors were empty, and the test server was stopped afterward.

Recent 4070-only real outputs:

- High-quality RSC final LoRA: `outputs\images\20260616-222329_s609_768x1152_lora_masterpiece-anime-illustration-rsc-style-close-u_def453_face_detail.png`
- High-quality RSC epoch 4 LoRA: `outputs\images\20260616-222603_s609_768x1152_lora_masterpiece-anime-illustration-rsc-style-close-u_f813a4_face_detail.png`
- `euler_ancestral_cfg_pp + sgm_uniform` comparison: `outputs\images\20260616-221417_s608_768x1152_lora_masterpiece-anime-illustration-rsc-style-close-u_463a8c_face_detail.png`

Recent output checks passed with:

- `output_is_png=true`
- `output_width=1152`
- `output_height=1728`
- `png_parameters_present=true`
- `png_parameters_matches_manifest=true`
- `high_res_fix.status=completed`
- `vae_decode.method=tiled`
- `face_detailer.status=completed`

## Release Boundary

Current release target: source-checkout alpha.

Source-checkout release smoke:

```powershell
python scripts\release_smoke.py --include-tests
```

The release smoke verifies static source files, artifact ignore rules, health JSON, dry-run smoke checks, and the full test suite when `--include-tests` is supplied. The Windows wrapper is `Run-AnimaAPP-ReleaseSmoke.cmd`.

History and settings API additions:

- `DELETE /api/manifests/<name>` deletes a manifest and its managed output image when the output path is inside `outputs\images`.
- `GET /api/presets/export` exports saved GUI settings as an `anima-app/presets.v1` bundle.
- `POST /api/presets/import` imports that bundle after validating each preset request.
- `GET /api/checkpoints` lists selectable project-local diffusion checkpoints.

Packaging dry-run proof:

```powershell
python scripts\package_dry_run.py
```

The packaging proof builds a wheel under `outputs\package_dry_run`, inspects package metadata and the `anima-app` entry point, confirms local artifact roots are excluded from the wheel, and records the standalone layout plan.

Not finished for public packaged release:

- Wheel/standalone packaging.
- Automated vendored-runtime inclusion or runtime setup.
- Public packaged release automation.

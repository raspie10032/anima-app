# Anima APP Acceptance

This checklist tracks practical completion. Detailed local paths, model sources, quality presets, generated artifact references, and latest evidence live in `docs\REFERENCES.md`.

## Implemented And Verified

- [x] Package foundation exists under `src\anima_app`.
- [x] Project paths point at `C:\Users\seine\Documents\Anima APP`.
- [x] Development model source points at `E:\ComfyUI_sage\ComfyUI\models`.
- [x] Runtime generation reads copied project-local assets under `models`, not the development source.
- [x] `anima-t2i` asset profile names the base diffusion model, Qwen text encoder, and VAE.
- [x] `anima-t2i` profile can auto-download required base assets from Hugging Face when the local development source is incomplete.
- [x] Additional Anima-family diffusion checkpoints under `models\diffusion_models` can be listed and selected by relative `.safetensors` path.
- [x] `face-detailer-detectors` asset profile copies validated detector files into `models\detectors`.
- [x] `pyproject.toml` declares optional `face-detailer` extra for Ultralytics-based detector runtime support.
- [x] `T2IRequest` validates prompt, resolution, steps, CFG, denoise, LoRA, I2I, upscale, tiled VAE, and face-detailer settings.
- [x] Dry-run T2I writes a JSON manifest under `outputs\manifests`.
- [x] Real renderer output is validated as a PNG under `outputs\images`.
- [x] Generated PNGs embed A1111-style `parameters` metadata, including selected model checkpoint, and manifests record the same text under `png_metadata.parameters`.
- [x] Searchable output names include timestamp, seed, size, mode, prompt slug, and short hash.
- [x] CLI supports health, model inventory/copy, checkpoint list/select, LoRA import/list, dry-run T2I, real T2I, I2I, upscale, tiled upscale, tiled VAE, wildcards, and face detailer.
- [x] Smoke runner supports dry-run checks and strict PNG output checks.
- [x] Release smoke runner verifies source-checkout files, health JSON, dry-run smoke checks, and optional full tests.
- [x] Packaging dry-run runner builds and inspects a wheel and records the standalone layout plan under `outputs\package_dry_run`.
- [x] Vendored AnimaStudio-derived runtime is present under `vendor\anima_runtime`.
- [x] Local GUI/API server serves `/`, `GET /api/health`, `GET /api/readiness`, `POST /api/models/prepare`, `POST /api/generate`, `GET /api/checkpoints`, `GET /api/loras`, `POST /api/loras/import`, `GET /api/wildcards`, `GET /api/presets`, `POST /api/presets`, `GET /api/presets/export`, `POST /api/presets/import`, `GET /api/history`, `GET /api/progress/<id>`, `GET /api/manifests/<name>`, and `DELETE /api/manifests/<name>`.
- [x] GUI can select checkpoint and LoRA, choose sampler/scheduler, send detailed I2I/upscale/tiled VAE/face-detailer options, insert wildcards, save/apply/import/export presets, inspect history, export/delete manifests, open output links, and apply a manifest back into the form.
- [x] GUI shows Anima base and face-detector readiness cards and can prepare missing model profiles through `POST /api/models/prepare`.
- [x] CLI, API, and GUI default generation settings are `832x1216`, `20` steps, CFG `3.5`, sampler `euler_ancestral_cfg_pp`, and scheduler `sgm_uniform`.
- [x] GUI has quick `Standard` and `Reference Quality` preset buttons that preserve the current prompt while updating generation settings.
- [x] GUI uses a left control frame with grouped accordions for prompt/generate, model/style, image settings, enhancement, prompt tools, and saved settings.
- [x] GUI uses a central image workspace for the current result, a collapsible right-frame Runtime Status panel, and a right history frame.
- [x] GUI displays a sticky generation stage panel while a request is running, finalizes stage states from manifest metadata, uses color markers for completed/pending/skipped states, and auto-hides it after successful completion.
- [x] GUI sends a per-request `progress_id` and polls backend progress instead of advancing generation stages on a client-only timer.
- [x] GUI can run a browser-side auto queue from the current form settings with queue count, seed mode, delay, progress status, and stop-after-current controls.
- [x] Server rejects overlapping `/api/generate` requests so the Comfy runtime is not driven concurrently from multiple tabs or duplicate servers.
- [x] GUI shows a readable current-result summary and keeps raw manifest JSON collapsed behind `Manifest JSON`.
- [x] GUI history is a filtered thumbnail gallery with `All`, `Images`, and `Dry-run` views plus an empty state for filters without matches.
- [x] GUI history cards can open manifests, open image outputs, export manifest JSON, and delete managed manifest/output pairs.
- [x] GUI clears stale preview/output/result state at generation start, labels failed requests clearly, and opens the current manifest after a successful generation.
- [x] Windows `.cmd` launcher starts the real-generation GUI server with dynamic port selection.
- [x] Separate Windows dry-run GUI launcher starts manifest-only mode for safe UI checks.
- [x] Windows `.cmd` launcher runs the source-checkout release smoke.
- [x] Root `wildcards\*.txt` prompt expansion supports `random`, `sequential`, and `reverse`; prompts without wildcard tokens pass through unchanged.
- [x] Face detailer records `completed` with boxes/crop/output path when repaint succeeds, or `skipped` with a clear reason when unavailable.
- [x] Face detailer supports a forehead/hairline exclusion ratio that masks out the top of the repaint crop and records the applied value in manifests.
- [x] High-quality 4070-only generation has been verified with LoRA, high-res fix, tiled upscale, tiled VAE, and face detailer.

## Required Before Source-Checkout Alpha

- [x] Port the verified AnimaStudio vendored runtime into `Anima APP`.
- [x] Copy or auto-download the `anima-t2i` model profile into project-local `models`.
- [x] Copy valid face-detailer detector assets into project-local `models\detectors`.
- [x] Generate one real base T2I PNG on GPU 0.
- [x] Record real base T2I stage metadata in the manifest.
- [x] Add LoRA import/list support and verify at least one local LoRA run.
- [x] Add I2I support and verify one real I2I PNG.
- [x] Add high-res fix/upscale support and verify final image size.
- [x] Add tiled VAE decode and tiled upscale controls.
- [x] Add wildcard prompt expansion across CLI/API/GUI/smoke flows.
- [x] Add A1111-style PNG metadata.
- [x] Add selectable Anima-family checkpoint support across CLI/API/smoke/GUI flows.
- [x] Add face detailer support and verify completed repaint plus clear skipped reasons in the manifest.
- [x] Add local GUI/API and verify `/api/generate` returns HTTP 200 with a generated PNG URL.
- [x] Document source-checkout install, optional face-detailer dependency, model-copy commands, runtime boundaries, and current reference paths.
- [x] Add source-checkout release smoke and release checklist.
- [x] Add packaging dry-run proof and packaging plan.
- [x] Add output/history housekeeping controls.
- [x] Add saved-settings import/export.

## Packaging Boundary

- [x] Source-checkout alpha path is documented.
- [x] Source-checkout release smoke is implemented.
- [x] Release checklist documents the source-checkout alpha boundary.
- [x] Wheel dry-run proof and standalone layout plan are implemented.
- [x] Model, detector, LoRA, input, and output artifacts are excluded by `.gitignore`.
- [x] Optional face-detailer dependency is declared as `.[face-detailer]`.
- [ ] Wheel/standalone binary packaging has not been finalized.
- [ ] Vendored-runtime inclusion or runtime setup is not automated for packaged distribution.
- [x] Exact live backend stage polling is implemented through `GET /api/progress/<id>`.
- [x] Face-detailer forehead/hairline exclusion is implemented for CLI, API, GUI, dry-run manifests, and runtime masks.

## Verification Commands

```powershell
python -m pytest tests -q
$env:PYTHONPATH='src'; python -m anima_app.cli health --json
python scripts\smoke_anima_app.py --dry-run --require-checks
python scripts\release_smoke.py --include-tests
python scripts\package_dry_run.py
```

GPU smoke commands must use:

```powershell
$env:CUDA_VISIBLE_DEVICES='0'
```

Do not use GPU 1 / RTX 5060 for this app unless the user explicitly reverses that rule.

## Reference Index

See `docs\REFERENCES.md` for:

- Current local model, detector, LoRA, and runtime paths.
- Install commands and optional dependencies.
- Current high-quality CLI preset.
- Latest generated image/manifest evidence.
- GPU boundary.
- Remaining release boundary.

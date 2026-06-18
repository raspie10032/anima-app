# Anima APP Acceptance

This checklist records the accepted public source-checkout alpha scope.

## Implemented

- [x] Python package source exists under `src\anima_app`.
- [x] Runtime assets are read from the project-local `models` tree.
- [x] The `anima-t2i` asset profile can download required base assets from Hugging Face.
- [x] A local model mirror can be configured with `ANIMA_APP_MODEL_SOURCE`.
- [x] Additional Anima-family diffusion checkpoints can be listed and selected by relative `.safetensors` path.
- [x] Optional face-detailer detector assets can be downloaded automatically or copied from a user-configured local source.
- [x] Optional face-detailer runtime dependency is declared as `.[face-detailer]`.
- [x] Local LoRA files can be imported into `models\loras` and stacked by relative path in the GUI.
- [x] CLI, API, and GUI support text-to-image generation, image-to-image settings, upscale settings, tiled VAE settings, wildcards, LoRA settings, and face-detailer settings.
- [x] Generated PNGs embed A1111-style `parameters` metadata.
- [x] App-managed outputs use searchable filename stems shared with generation-info JSON files.
- [x] Root `wildcards\*.txt` prompt expansion supports `random`, `sequential`, and `reverse` modes.
- [x] `wildcards\presets\*.txt` prompt presets can be inserted as `__presets/name__` wildcard tokens.
- [x] GUI wildcard and prompt preset insertion keeps inserted tokens comma-separated from surrounding prompt text.
- [x] Wildcards support nested wildcard tokens, inline random `{A|B|C}` choices, cycle rejection, and GUI expansion preview before generation.
- [x] GUI Auto Queue uses a server-side job queue with fixed counts and Infinity mode.
- [x] Server-side queued or waiting jobs can be cancelled, and running jobs receive a runtime interrupt request when supported by the loaded runtime.
- [x] Runtime Status can perform a read-only GitHub release/tag update check for the app.
- [x] GUI history item clicks load the final image into the center result panel.
- [x] Enhanced generations can expose an Original / Upscale / Face Detailer compare grid from the result panel.
- [x] Browser GUI labels are Korean by default while API request keys remain stable.
- [x] Local browser GUI includes prompt controls, model/checkpoint controls, LoRA controls, image settings, enhancement settings, prompt tools, saved settings, progress display, current result view, and history.
- [x] The Windows user launcher is `Run-AnimaAPP-GUI.cmd`.
- [x] Local model weights, detector weights, LoRA files, input images, outputs, and generation-info JSON files are excluded from git.
- [x] Public release docs include license, notices, references, and release boundary.

## Release Boundary

- [x] Current release target is a source-checkout alpha.
- [x] GitHub source archives are the intended public release artifact for this version.
- [ ] Standalone binary packaging is not finalized.
- [ ] Final wheel redistribution policy for vendored runtime assets is not finalized.

## Verification Policy

Public user-facing docs stay focused on installation, model preparation, and launching the GUI.

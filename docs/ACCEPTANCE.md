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
- [x] App-managed outputs use searchable filename stems shared with JSON manifests.
- [x] Root `wildcards\*.txt` prompt expansion supports `random`, `sequential`, and `reverse` modes.
- [x] GUI wildcard insertion keeps inserted wildcard tokens comma-separated from surrounding prompt text.
- [x] GUI Auto Queue supports fixed counts and Infinity mode.
- [x] Local browser GUI includes prompt controls, model/checkpoint controls, LoRA controls, image settings, enhancement settings, prompt tools, saved settings, progress display, current result view, and history.
- [x] The Windows user launcher is `Run-AnimaAPP-GUI.cmd`.
- [x] Local model weights, detector weights, LoRA files, input images, outputs, and generated manifests are excluded from git.
- [x] Public release docs include license, notices, references, and release boundary.

## Release Boundary

- [x] Current release target is a source-checkout alpha.
- [x] GitHub source archives are the intended public release artifact for this version.
- [ ] Standalone binary packaging is not finalized.
- [ ] Final wheel redistribution policy for vendored runtime assets is not finalized.

## Verification Policy

Public user-facing docs stay focused on installation, model preparation, and launching the GUI.

# Anima APP v0.3.0 source-checkout beta

This release makes Anima Aesthetic v1.1 the preferred checkpoint and adds practical SAM3 multi-pass detail correction.

## Highlights

- Prefer and automatically prepare `anima-aesthetic-v1.1.safetensors`, with Anima Base v1.0 retained as a fallback.
- Run SAM3 face-and-eyes and hands correction as separate sequential detailer passes.
- Select either or both SAM3 correction targets and configure a separate hand denoise value.
- Show original, upscale, face-and-eyes, and hands stages in the comparison view.
- Keep multi-LoRA, nested/random wildcards, prompt presets, infinite auto queue, tiled VAE, tiled upscale, A1111 metadata, and LLM prompt cleanup in the same workflow.
- Load the browser JavaScript as a packaged static asset and display startup failures instead of failing silently.

## Defaults

- Resolution: 832 x 1216
- Steps: 20
- CFG: 3.5
- Sampler: Euler Ancestral CFG++
- Scheduler: SGM Uniform
- LoRA strength: 1.0

## Verification

- Full automated test suite passed.
- Anima Aesthetic v1.1 generation completed on CUDA with multi-LoRA, wildcard expansion, tiled upscale, tiled VAE, metadata, and face detail correction.
- SAM3 face-and-eyes and hands passes completed sequentially on a real generated image.
- Browser checks confirmed checkpoint selection, SAM3 controls, progress state, history selection, and comparison labels.
- The built wheel serves the GUI and packaged JavaScript successfully.

## Distribution boundary

The GitHub source archive is the supported artifact for this beta. The Python wheel is useful for package verification but is not a standalone generation bundle because the repository-level vendored runtime is intentionally excluded.

Model checkpoints, detector weights, LoRAs, input images, generated images, and user configuration are not included. Anima and SAM3 downloads remain subject to their upstream licenses and access terms.

See `README.md`, `NOTICE.md`, and `docs/REFERENCES.md` before preparing models or redistributing a build.

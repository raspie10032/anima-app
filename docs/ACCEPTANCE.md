# Anima APP Acceptance

This checklist records the accepted public `0.4.0` source-checkout beta scope.

## Implemented

- [x] Python package source exists under `src\anima_app`.
- [x] Runtime assets are read from the project-local `models` tree.
- [x] The `anima-t2i` asset profile can download required base assets from Hugging Face.
- [x] The `anima-aesthetic-v1.1` profile can download the preferred checkpoint, which the GUI selects when installed.
- [x] A local model mirror can be configured with `ANIMA_APP_MODEL_SOURCE`.
- [x] Additional Anima-family diffusion checkpoints can be listed and selected by relative `.safetensors` path.
- [x] Optional face-detailer detector assets can be downloaded automatically or copied from a user-configured local source.
- [x] Optional face-detailer runtime dependency is declared as `.[face-detailer]`.
- [x] Local LoRA files can be imported into `models\loras` and stacked by relative path in the GUI.
- [x] Browser picker and drag-and-drop upload one bounded reference image or LoRA at a time without exposing a local path; successful LoRAs are automatically selected.
- [x] Reference uploads are single-frame, type-matched PNG/JPEG/WebP files stored by SHA-256 under `inputs\references`, with byte, dimension, and pixel limits.
- [x] LoRA uploads require valid non-empty safetensors, preserve existing files, deduplicate identical content, and suffix same-name content collisions under `models\loras`.
- [x] CLI, API, and GUI support text-to-image generation, image-to-image settings, upscale settings, tiled VAE settings, wildcards, LoRA settings, and face-detailer settings.
- [x] Expected generation failures return structured JSON with stable error codes for missing required models, missing request files, and runtime failures.
- [x] `GET /api/openapi.json` exposes a dependency-free OpenAPI 3.1 contract for the canonical local agent generation, queue, progress, cancellation, and manifest flow.
- [x] Model and LoRA preparation uses validated temporary files and atomic destination replacement; the GUI confirms and freezes the displayed local or remote source.
- [x] Readiness separates required, recommended, and optional installation profiles from the selected checkpoint's request-specific execution gate.
- [x] Generated PNGs embed A1111-style `parameters` metadata.
- [x] App-managed outputs use searchable filename stems shared with generation-info JSON files.
- [x] Root `wildcards\*.txt` prompt expansion supports `random`, `sequential`, and `reverse` modes.
- [x] `wildcards\presets\*.txt` prompt presets can be inserted as `__presets/name__` wildcard tokens.
- [x] GUI wildcard and prompt preset insertion keeps inserted tokens comma-separated from surrounding prompt text.
- [x] Wildcards support nested wildcard tokens, inline random `{A|B|C}` choices, cycle rejection, and GUI expansion preview before generation.
- [x] Prompt autocomplete replaces the whole current tag, rejects stale responses, stays closed after applying a suggestion, and supports visible keyboard navigation without overriding textarea semantics.
- [x] Saved generation settings use bounded names, canonical validated request data, timestamped atomic JSON replacement, malformed-file isolation, link/junction rejection, and prevalidated schema-aware imports.
- [x] GUI Generate uses a cancelable one-job server batch; Auto Queue uses the same queue for fixed counts and Infinity mode, and Infinity stops scheduling after a generation failure.
- [x] Refreshing the browser reconnects to an active batch while the same Python server process remains alive; a server restart intentionally clears the in-memory queue.
- [x] Queued or generation-lock-waiting jobs cancel without interrupting another generation; a running job receives a runtime interrupt request and a cooperative interrupt ends as `cancelled`.
- [x] A failed stop request leaves the server job tracked and re-enables the Stop control for retry.
- [x] The HTTP server binds only to localhost/IPv4 loopback, requires the active port in Host, rejects cross-origin mutation requests, and accepts only bounded, finite, depth-limited mutation JSON objects.
- [x] Raw upload endpoints require a bounded positive Content-Length, reject transfer encoding and unsupported media types, stream through cleaned temporary files, and enforce managed reference/LoRA paths before HTTP generation or queue registration.
- [x] Generation, SAM3, and masked-inpaint requests enforce finite low-VRAM limits before decode/model work; prompts, source pixels, latent-rounded output pixels, feature flags, API/browser seed ranges, tiles, batches, queue delay, and active queue retention are covered by boundary tests and matching browser validation.
- [x] Generation, model preparation, SAM3 segment/compare, and masked inpaint share one GPU lock; competing direct GPU work returns structured `generation_busy` JSON.
- [x] Runtime Status can perform a read-only GitHub release/tag update check for the app.
- [x] GUI history item clicks load the final image into the center result panel.
- [x] GUI history supports cursor-based `더 보기`, skips malformed manifests, and publishes new manifest JSON atomically.
- [x] GUI history searches and filters the complete server-side result set before pagination and uses authoritative manifest filenames.
- [x] History cards use bounded in-memory JPEG thumbnails with lazy decoding instead of downloading full PNG files.
- [x] History shows managed image/manifest counts and bytes plus free disk space without enabling automatic or bulk cleanup.
- [x] Confirmed per-record deletion validates every target first, rejects path aliases, malformed variants, symlinks, and Windows junctions, rolls back partial multi-file failures, and preserves files referenced by another manifest.
- [x] Enhanced generations can expose an Original / Upscale / Face Detailer compare grid from the result panel.
- [x] SAM3 face detailing can run independent Face + Eyes and Hands passes with separate switches, hand denoise, progress stages, manifest evidence, and compare outputs.
- [x] Browser GUI labels are Korean by default while API request keys remain stable.
- [x] Browser controls expose generated-image text alternatives, live SAM3/inpaint/preset status, pressed preset states, validated dynamic LoRA strengths, focus-preserving LoRA edits, and reduced-motion behavior.
- [x] Local browser GUI includes prompt controls, model/checkpoint controls, LoRA controls, image settings, enhancement settings, prompt tools, saved settings, progress display, current result view, and history.
- [x] The Windows user launcher is `Run-AnimaAPP-GUI.cmd`.
- [x] The Windows launcher preserves a failed Python exit code and pauses only on failure.
- [x] A temporary wheel/package dry-run verifies packaged GUI JavaScript and CLI dry-run while preserving the source-archive runtime boundary.
- [x] Package metadata reads the canonical application version instead of duplicating a second version literal.
- [x] CI is configured to run the CPU-safe suite on Python 3.10 and 3.13, check browser JavaScript, exercise the Windows launcher on Windows, verify vendored integrity, and build both release candidates.
- [x] Vendored runtime/package versions, licenses, local compatibility patches, unknown exact revisions, and wildcard provenance limits are disclosed without private local paths.
- [x] Vendored `RECORD` hashes describe the disclosed patched files; unused aimdo native binaries and ignored local native extensions are excluded from the supported source archive.
- [x] A clean-checkout source-archive command reads committed Git blobs, uses fixed uncompressed ZIP metadata, verifies required runtime/UI/license surfaces, runs a dry-run CLI from extraction, and emits SHA-256.
- [x] Local model weights, detector weights, LoRA files, input images, outputs, and generation-info JSON files are excluded from git.
- [x] Public release docs include license, notices, references, and release boundary.

## Release Boundary

- [x] Current release target is a `0.4.0` source-checkout beta.
- [x] The verified `scripts/source_archive.py --require-clean` ZIP is the intended public artifact for this version; GitHub's automatic source archives are convenience copies rather than the verified artifact.
- [ ] Creating the public tag/release and uploading the verified ZIP remain manual owner actions.
- [ ] Standalone binary packaging is not finalized.
- [ ] Final wheel redistribution policy for vendored runtime assets is not finalized.
- [ ] The wheel is not a standalone generation build because it does not bundle the root-level vendored Comfy runtime.

## Verification Policy

Public user-facing docs cover installation, model preparation, GUI and CLI operation, and the local AI-agent API without implying a standalone wheel or live ComfyUI dependency.

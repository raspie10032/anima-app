# Anima APP Acceptance

This checklist records the implemented `0.6.1` source-checkout beta scope. The [release notes](RELEASE_0.6.1.md) describe the current distribution and the [main integration record](MAIN_UPDATE_2026-10-14.md) records earlier workspace, locale and workflow verification. Earlier feature-specific acceptance entries below retain their original test boundaries.

## v0.6.1 additions

- [x] Connect & prepare exposes NAI credentials, model preparation, feature-specific required models and references in Korean, English and Japanese.
- [x] NAI tokens default to volatile memory on the execution PC; explicit persistence uses the OS credential store. Browser storage, manifests and app configuration never contain token values.
- [x] Barracks distributes standalone NAI T2I across up to eight accounts, with per-token serialization, seed modes, unique output names and cancellation of future submissions. References, Img2Img and post-processing are rejected. Automated transport checks are mocked.
- [x] The VRS encoder and SWEGCA evidence accumulator ship in the package with source provenance, license texts and integrity checks. Vision weights are prepared separately; current VRS encoding requires CUDA.
- [x] Caption-free and malformed-metadata images can be registered and encoded from decoded pixels. Duplicate pixel identities preserve linked source records.
- [x] Cached encoder/matrix reuse, progressive indexing, cancellation and explicit evaluation replay preserve the encoder contract. Personal ordering and diverse results retain the raw score and core decision.
- [x] A persistent VRS switch preserves existing records while disabling VRS work. Image storage and basic search remain available. The library has no fixed image-count cap.
- [x] Focused tests and browser checks cover setup, saved credentials, Barracks, library, generation, authoring and locale changes. The release receipt records final local and remote CI results.

## Implemented

- [x] Up to 22 saved character slots retain prompt, negative, normalized center and coordinate/order flags through requests, payloads, presets, wildcard provenance, manifests and metadata import. V5 allows 22 active characters; V4/V4.5 allows six. V3, invalid values and unrepresentable imported layouts are rejected or warned before generation.
- [x] Six local prompt-weight syntax conversions show original/result, node fallback and old-NAI approximation warnings; explicit apply is invalidated when the source or selection changes.
- [ ] Live remote multi-character acceptance and composition quality have not been checked for this implementation.

- [x] Local Anima and optional NovelAI T2I share the browser server queue, presets, history, thumbnails and manifests.
- [x] NovelAI credentials can be applied through setup, restored from the optional OS credential store, or supplied through the process environment. Status endpoints expose presence and storage state without token values; credential keys are rejected before queue/preset storage.
- [x] NovelAI requests validate bounded text, dimensions, sampling values, booleans and 32-bit seeds before transport. Local LoRAs and local-only enhancements are rejected; NAI-specific references and detailing use separate validated contracts.
- [x] The browser shows provider controls, effective Opus-capped dimensions/steps, and remote cancellation/cost boundaries.
- [x] Protected T2I checks active Opus tier 3 and V5 integer remaining allowance >=2 percent immediately before every attempt, including the bounded 429 retry; malformed/failed account checks stop before generation. Dry-run performs no account lookup.
- [x] A process-wide gate per token serializes account checks, generation and retries across ordinary generation and Barracks; successful and failed transmissions enforce at least two seconds from completion before the next attempt on that token. Pending lock/cooldown waits are cancellable.
- [ ] These new account guards are validated with synthetic account/transport and clock/concurrency tests; current live account acceptance and billing are unverified.
- [x] NovelAI timeout/network failures are secret-free, expose an unknown remote outcome and stop Infinity scheduling without automatic resubmission. Only HTTP 429 gets one bounded retry.
- [x] Remote cancellation leaves local GPU interrupts untouched, stops future jobs, and preserves an already submitted result when it arrives.
- [x] NovelAI result PNGs are validated, byte-preserved and atomically written with request/effective parameters, SHA-256, retries and provider provenance in the manifest.
- [x] OpenAPI includes provider discovery, token-presence status and both generation request schemas.
- [x] NovelAI masked infill supports dedicated model IDs, managed source/mask inputs, in-browser paint/erase/save, pre-queue size/empty-mask validation, cost-cap rejection, and exact preservation outside the mask in the composited result.
- [x] Infill settings and model identity round-trip through manifests/presets and app-produced PNG metadata. Remote response bytes remain a separate variant.
- [x] Img2Img strength/noise, input resizing and metadata settings; Vibe multireference encoding/cache/normalization; Precise types/fidelity/letterboxing persist through canonical queue/preset/history contracts.
- [x] Sequential native detector / WD prompt selection and frozen-source, disjoint focused masks; preview without remote requests; strict focused preflight per crop and durable partial-result preservation with batch stop.
- [x] Real local CPU face/eye YOLO + SAM B and WD inference checked against the preserved earlier NAI image; other remote transports mocked.
- [x] Offline CPU SAM3 face/eye/hand inference and YOLO hand n/s with SAM B `.pt`/`.pth` loader paths produced nonempty masks on the preserved detector-preview derivative. Original input/model hashes were retained; native reports are under `outputs/all-nai-port-20261009/sam3/native` and `hands/native` in the development checkout.
- [ ] Broad detector accuracy, GPU execution, optional native dependencies in the app environment, actual remote acceptance/correction quality/Anlas changes for the new ports, and Windows GUI remain unverified.
- [ ] Actual NovelAI infill endpoint acceptance and correction quality remain unverified; `scripts/browser_inpaint_smoke.py` uses a synthetic transport only.
- [ ] Current integrated live NovelAI endpoint, actual account entitlement/billing and real GPU generation acceptance remain separate from mock/browser regression.

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

- [x] Current release target is a `0.5.0` source-checkout beta.
- [x] The verified `scripts/source_archive.py --require-clean` ZIP is the intended public artifact for this version; GitHub's automatic source archives are convenience copies rather than the verified artifact.
- [ ] Creating the public tag/release and uploading the verified ZIP remain manual owner actions.
- [ ] Standalone binary packaging is not finalized.
- [ ] Final wheel redistribution policy for vendored runtime assets is not finalized.
- [ ] The wheel is not a standalone generation build because it does not bundle the root-level vendored Comfy runtime.

## Verification Policy

Public user-facing docs cover installation, model preparation, GUI and CLI operation, and the local AI-agent API without implying a standalone wheel or live ComfyUI dependency.

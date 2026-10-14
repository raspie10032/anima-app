# Anima APP

Generate with local **Anima** or **NovelAI**, arrange detailing/upscaling stages, and find reusable prompts from similar images in a local browser workspace. The interface supports **English / 한국어 / 日本語**.

## Download v0.6.0

**[Download the verified source ZIP](https://github.com/raspie10032/anima-app/releases/download/v0.6.0/anima-app-0.6.0-source.zip)** · [Release and SHA-256 checksum](https://github.com/raspie10032/anima-app/releases/tag/v0.6.0) · [Changes and upgrade instructions](docs/RELEASE_0.6.0.md)

Extract the ZIP, then follow the first-image guide below. This source-checkout beta includes the Windows launcher and local generation runtime source; install Python 3.10+ and dependencies before starting it. Model weights are prepared separately. Image management and CPU similarity search work without a VRS model; enhanced VRS search uses an optional [local encoder setup](docs/IMAGE_LIBRARY_EN.md#optional-vrs-int-encoder).

## Start here

| Task | Documentation |
|---|---|
| Install, connect NAI, and generate a first image | **[한국어](docs/IMAGE_GENERATION_KO.md) · [English](docs/IMAGE_GENERATION_EN.md) · [日本語](docs/IMAGE_GENERATION_JA.md)** |
| Find the NAI token setting | **[NAI token setup](docs/NAI_TOKEN_SETUP.md)** — entered in the server's terminal environment, not a web form |
| Connect NAI → Anima or Anima → NAI | [한국어](docs/GENERATION_WORKSPACE_KO.md) · [English](docs/GENERATION_WORKSPACE_EN.md) |
| Search images, compare cases, reuse artist combinations | [한국어](docs/IMAGE_LIBRARY_KO.md) · [English](docs/IMAGE_LIBRARY_EN.md) |
| CLI, API, troubleshooting | [Full Korean manual](docs/USER_GUIDE_KO.md) · [Technical reference](docs/APP_REFERENCE.md) |
| Sources, attribution, models | [References](docs/REFERENCES.md) · [Third-party notices](NOTICE.md) |

The first-image guides explain each screen, settings to check before generation, ordered post-processing, intermediate outputs, selective prompt reuse, and recovery after an error. [The main update notes](docs/MAIN_UPDATE_2026-10-14.md) distinguish implemented features from remaining work.

## NAI token: where to enter it

There is **no token input box in the browser**. Obtain your Persistent API Token from NovelAI **Settings → Account → Get Persistent API Token**, then set `NAI_ACCESS_TOKEN` in the terminal that starts Anima APP. See [NovelAI's official account documentation](https://docs.novelai.net/en/text/usersettings/account/).

Linux / Bash, from an installed checkout with its environment activated:

```bash
read -rsp 'NAI token: ' NAI_ACCESS_TOKEN; printf '\n'
export NAI_ACCESS_TOKEN
python -m anima_app.cli serve --host 127.0.0.1 --port 8768 --open
```

Windows PowerShell: follow the [hidden-input token command](docs/NAI_TOKEN_SETUP.md#windows-powershell). After launch, select **NovelAI** under **Generation engine**; `/api/nai/status` reports whether a token was configured without exposing it. A configured token is not proof that it is valid. Changing the token requires restarting the server from the environment containing the new value. Use a stable port to retain browser drafts and language preferences at the same origin.

## Capabilities

The optional NovelAI provider supports T2I, Img2Img, masked and focused inpainting, Vibe Transfer, Precise Reference and sequential automatic detailing through the browser queue, presets, history and manifests. It includes up to 22 saved character slots (V5: 22 active; V4/V4.5: 6), six weight-syntax conversions and optional native WD matching of original character prompts. Hide or disable slots without losing text and positions; presets, history and app PNGs restore the full slot bank. Configure `NAI_ACCESS_TOKEN` in the server environment; local Anima remains the default. References and Img2Img require explicit removal of Opus protection. Focused crops have their own strict preflight. See [docs/NOVELAI_PROVIDER.md](docs/NOVELAI_PROVIDER.md) for setup, model dependencies, costs and the local/mock versus live validation boundary.

This source update adds V5 Full **Medium Effort** to generation, Img2Img, inpainting and detailing: 14 steps, Euler Ancestral, zero CFG rescale and fixed negative conditioning. English/Korean/Japanese interface text, NAI guidance and cause-specific error explanations follow the saved browser language without changing generation settings. Errors retain their code, execution stage, upstream HTTP status and sanitized details across queue results and partial-result history; prompts, records and raw technical details retain their original text. See the [2.4.6 node update checklist](docs/NAI_NODE_UPDATE_2.4.6.md) for source commits, per-requirement verification, reproduction commands and package boundaries.

The update also adds WD ViT v3 / WD EVA02 Large v3 / PixAI Tagger v1.0 selection for original-character matching. Prepare the selected model in the detailer panel to see per-file download progress and cancellation; generation uses the prepared cache. Install `.[wd-matching]` or `.[pixai-matching]` in the app environment first. Model choice is preserved in presets, history and PNG metadata; [setup and validation limits](docs/NOVELAI_PROVIDER.md#wd-vit--eva02--pixai-선택과-준비) describe the optional dependencies and local CPU evidence.

This release targets RS NAI **2.4.6, commit `4de9146`**. Upstream 2.5.0 (`ed96a4c`) adds reference inset generation and portable character assets after that pin; those additions are not included here. **Anima APP v0.6.0** packages that integration together with the image workspace, ordered workflows and three-language UI. Use the source-checkout ZIP for the bundled local runtime; the wheel alone omits that runtime. See [release verification](docs/RELEASE_0.6.0.md#verification) for the scope of automated checks and earlier live examples.

Anima APP packages a focused Anima text-to-image workflow around a local, project-owned `models` folder. It does not require launching a ComfyUI server for normal generation.

## Reference Map

- [App language / 앱 언어 / アプリの言語](docs/LOCALES.md): English, Korean and Japanese across generation, workflow and image workspace, with saved preference and original prompt preservation.

- [Generation workspace (한국어)](docs/GENERATION_WORKSPACE_KO.md) / [English](docs/GENERATION_WORKSPACE_EN.md): main-screen layout, ordered NAI/Anima detailing and upscaling, per-stage settings, intermediate results and live acceptance scope.
- [Image library guide (한국어)](docs/IMAGE_LIBRARY_KO.md) / [English](docs/IMAGE_LIBRARY_EN.md): image workspace, reference-based comparison, undoable prompt drafts, recorded artist combinations, optional VRS-INT indexing, and evaluation limits.
- [docs/USER_GUIDE_KO.md](docs/USER_GUIDE_KO.md): 설치, GUI, CLI, AI 에이전트 API, 오류 해결을 포함한 한국어 상세 사용 가이드.
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

Prepare the preferred Anima Aesthetic v1.1 checkpoint:

```powershell
$env:PYTHONPATH='src'
python -m anima_app.cli models copy-profile anima-aesthetic-v1.1
```

By default, the app downloads the base profile from Hugging Face when a configured local mirror is not available. To use a local model mirror, set:

```powershell
$env:ANIMA_APP_MODEL_SOURCE='path\to\comfyui\models'
```

The GUI shows whether each preparation action will use a local copy or a remote/Hugging Face download. It asks for confirmation and submits that displayed source explicitly, so a missing local file cannot silently switch the same click to a large download. Local copies, remote downloads, and LoRA imports are validated in a temporary file and atomically replace the destination only after validation succeeds.

Required base files are copied into the project-local `models` tree:

- `models\diffusion_models\anima-base-v1.0.safetensors`
- `models\text_encoders\qwen_3_06b_base.safetensors`
- `models\vae\qwen_image_vae.safetensors`

When `models\diffusion_models\anima-aesthetic-v1.1.safetensors` is valid, the GUI selects it by default. Otherwise it uses a valid `anima-base-v1.0.safetensors`, then the first valid custom checkpoint. Invalid checkpoint files remain visible for diagnosis but are not preferred over a usable model.

Additional Anima-family diffusion checkpoints can be placed under `models\diffusion_models` and selected by relative `.safetensors` path.
Runtime Status labels model profiles as required, recommended, or optional. Actual generation readiness is calculated separately for the selected checkpoint plus the shared text encoder and VAE, so a valid custom-only checkpoint setup can run even when the default base checkpoint is absent.

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

When the face detailer uses SAM3, the GUI exposes independent `얼굴 + 눈` and `손` switches. Enabled targets run as sequential detailer passes: the face/eyes pass uses the normal face denoise value, while the hands pass uses its own denoise value. Missing target masks skip only that pass. History comparison can show Original, Upscale, Face + Eyes, and Hands outputs.

Local LoRA files can be imported into `models\loras` and stacked in the GUI:

```powershell
$env:PYTHONPATH='src'
python -m anima_app.cli models import-lora "path\to\style.safetensors"
python -m anima_app.cli models loras
```

The browser GUI also accepts one local file at a time by picker or drag-and-drop. Reference images are streamed to `inputs\references`, validated as a single-frame PNG, JPEG, or WebP, and stored under a SHA-256 content name. They are limited to 64 MiB, 8192 pixels on either side, and 16,777,216 pixels total. Identical content reuses the existing file.

Browser-uploaded LoRAs are streamed to `models\loras`, limited to 1 GiB, and must be non-empty valid `.safetensors` files. Uploading the same name and same content reuses the file. A different file with the same name is preserved under `<stem>-<sha256-prefix>.safetensors`; an existing LoRA is never overwritten by this upload path. The GUI validates the extension and byte limit before upload, disables generation while a transfer is active, and automatically selects a successful LoRA upload.

For browser and HTTP generation, reference images must use an app-managed relative path under `inputs/references` or `outputs/images`, and LoRAs must use a relative path below `models/loras`. Absolute paths, traversal, missing files, and symlink escapes are rejected before generation or queue registration. Direct CLI workflows retain their existing explicit absolute-path support.

## Run The GUI

For the complete Korean GUI workflow, see [docs/USER_GUIDE_KO.md](docs/USER_GUIDE_KO.md#3-gui-사용법).

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
If Python exits with an error, the launcher keeps the window open, preserves the exit code, and points to the setup instructions. A normal shutdown does not pause.

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

When the bridge is configured, the prompt tools panel shows an `LLM 정리 기준` selector and a `보정` button. The selector chooses whether contradiction cleanup should prefer explicit tags or natural-language intent. The GUI asks the worker to return JSON containing cleaned English tags, one concise English natural-language reinforcement sentence, and any resolved conflict notes. If the worker returns JSON inside a code fence or with surrounding text, the GUI tries to recover it; if parsing fails, it keeps the current English tags and appends the raw completion as a fallback. Non-English description fragments are translated into English by the worker and removed from the cleaned tag prompt.

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

The browser GUI supports English, Korean and Japanese through the **App language** setting. It uses a supported browser language on first visit, with English as the fallback, and saves the selection without changing API fields or request values.

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

The server loads the file into memory when the GUI starts and refreshes the cache if the file changes. Autocomplete is available in the main prompt, negative prompt, and masked-inpaint prompt fields. A selection replaces the complete comma- or newline-delimited tag at the cursor, appends the separator for the next tag, and ignores an older response that arrives after a newer query. Arrow keys move through the visible list, Enter applies a suggestion, Escape closes it, and Tab keeps normal focus navigation.

## Saved Settings

Generation settings are stored under `outputs\presets` as validated JSON. Saving publishes a complete temporary file with flush/fsync and atomic replacement, refuses linked or junction-backed storage, normalizes accepted request aliases into the canonical API shape, records an update timestamp, and rejects a different name that would collide with an existing filename slug. A malformed preset is reported and skipped instead of breaking the complete list or export.

Exported bundles use `anima-app/presets.v1`. Import validates the bundle schema, every request, and duplicate filename slugs before writing any item; each accepted file is then atomically published. Preset names are limited to 120 characters and Windows-reserved filenames are rejected.

The saved-settings controls and long-running SAM3/inpaint status expose polite live updates. Starting size and orientation report their pressed state, generated images have meaningful alternative text, dynamic LoRA strength inputs participate in browser validation, and `prefers-reduced-motion` disables the progress pulse and smooth scrolling.

## AI Agent API

`GET /api/openapi.json` publishes an OpenAPI 3.1 document for local AI agents without adding a second server or runtime dependency. It describes the canonical generation request, current defaults and limits, model/readiness discovery, synchronous generation, queued generation, polling, cancellation, progress, and manifest retrieval. Agents should prefer `POST /api/jobs`, poll `GET /api/jobs/<job-id>`, and pass the completed result's `manifest_name` directly to `GET /api/manifests/<manifest-name>`.

The document marks canonical request objects with `additionalProperties: false`; clients should validate against it before submitting GPU work because the compatibility parser may ignore unknown fields. POST retries are not idempotent yet and can create another generation, so an agent must inspect the returned queue state instead of automatically retrying an uncertain submission. The API remains loopback-only and must not be exposed directly to a LAN or the internet.

For a complete Korean walkthrough with PowerShell examples, asset upload, queue polling, cancellation, and error handling, see [docs/USER_GUIDE_KO.md](docs/USER_GUIDE_KO.md#7-ai-에이전트-api-사용법).

## Generation API Errors

`POST /api/generate` reports expected generation failures as JSON with a stable `error_code` and a human-readable `error`. Missing or invalid required model files return HTTP `409` with `error_code: "models_not_ready"` and separate `missing_files` / `invalid_files` paths relative to the local `models` root; missing request files return HTTP `400` with `error_code: "generation_input_missing"`; runtime generation failures return HTTP `500` with `error_code: "generation_failed"`. Server-side queue jobs expose the same generation payload under `result` and preserve its status in `http_status`.

When the GUI receives `models_not_ready`, it opens Runtime Status so the missing files can be reviewed. It does not start a model download automatically.

## Local HTTP And Resource Safety

The browser server is local-only: it accepts `localhost` or IPv4 loopback bind addresses and rejects IPv6, wildcard, or LAN-facing binds. Every request must explicitly target the active loopback port in `Host`. State-changing requests also reject a present cross-origin `Origin`; local API clients may omit `Origin`. JSON mutations require `Content-Type: application/json`, one top-level object, valid Unicode text, finite numbers, at most 64 nesting levels, and a body no larger than 1 MiB.

`POST /api/inputs/reference?filename=...` and `POST /api/loras/upload?filename=...` are the two raw-body upload endpoints used by the GUI. They require exactly one positive `Content-Length`, reject transfer encoding and unsupported media types, stream through a bounded temporary file, and remove that temporary file after validation or failure. Reference uploads accept canonical PNG/JPEG/WebP media types or generic octet-stream; LoRA uploads use octet-stream. The 64 MiB reference and 1 GiB LoRA limits are enforced before reading an oversized body and again while publishing the validated asset.

Generation requests are rejected before rendering or queue registration when they exceed the conservative low-VRAM safety envelope: prompt and negative prompt are each at most 32,768 characters; each base dimension is at most 2048; the base image is at most 1,572,864 pixels; the latent-rounded enabled-upscale result is at most 4,194,304 pixels; sampling stages are at most 100 steps; API seed is an integer from 0 through `2^64 - 1`; CFG is at most 20; and upscale scale is at most 4. The browser limits seed to JavaScript's exact-integer range (`2^53 - 1`) so it never silently rounds a value. Tiles are 64-2048 pixels with overlap limited to one quarter of the tile, while face-detailer and LoRA inputs have matching finite upper bounds. Feature flags must be JSON booleans rather than truthy strings. SAM3 and masked inpaint apply prompt and source-image pixel guards before decoding or model work. These guards block accidental unbounded allocations and non-finite values; they do not guarantee that every valid request fits every GPU.

The server accepts 1-99 jobs per finite batch and at most 99 queued, waiting, or running jobs in total. Queue delay is a finite value from 0 through 60 seconds, and an incrementing seed wraps inside the supported seed range. Generation, model preparation, SAM3 segment/compare, and masked inpaint share one GPU lock. A competing direct GPU request returns HTTP `409` with `error_code: "generation_busy"`; queued work remains visible as waiting until the lock is available.

## Cancelable Generation and Auto Queue

The GUI sends both a normal Generate action and Auto Queue batches through the server-side job queue. A normal Generate action is a one-job fixed-seed batch, so the same `현재 작업 정지` control can cancel it without adding a second generation path.

Once queued, jobs continue while the Python server process is alive even if the browser is refreshed or its polling loop is interrupted. On reload, the GUI reconnects to the active server batch, restores the running controls and stage progress, and lets the user stop that batch. Queue state is in memory and is not restored after the Python server itself restarts.

Infinity mode schedules another job only after the current job succeeds. A failed generation remains in the queue results and stops further Infinity scheduling.

Fixed and Infinity queues validate the generation request and selected checkpoint before creating jobs. An invalid request returns HTTP `400`; an unready request returns one HTTP `409` response instead of registering a batch of deterministic failures. Dry-run queues bypass the model gate but keep request resource validation.

Stop cancels queued or lock-waiting jobs immediately and sends a runtime interrupt request only for the job that has actually started rendering. A cooperative Comfy interrupt is reported as `cancelled`; some GPU work may finish its current internal step before the running job stops. If a stop request fails, the Stop control becomes available again while the server job remains tracked.

`POST /api/generate` remains available as a synchronous compatibility endpoint. API clients that need polling or cancellation should enqueue one job with `POST /api/jobs` and cancel it with `POST /api/jobs/<job-id>/cancel`.

## Update Check

The Runtime Status panel can check GitHub for newer Anima APP releases. The check reads `raspie10032/anima-app` releases first and falls back to tags when no release exists.

Update checks are read-only. The app does not run `git pull`, download archives, replace files, or update models automatically.

## History And Compare Grid

Click a history item to load that generation's final image in the center result panel. History loads eight records at a time and exposes `더 보기` while an opaque cursor has older records. Search and the All / Images / Dry Run filters are applied by the server before pagination, so older matching records are not hidden behind a newer page. `GET /api/history` accepts a bounded `q` value and `type=all|images|dry-run`.

History cards request an on-demand JPEG thumbnail bounded to 320 pixels instead of downloading the full PNG. Thumbnail generation stays in memory and does not create a second thumbnail cache on disk. The history panel also shows managed image and manifest counts, their byte totals, and free disk space from `/api/health`.

A malformed manifest is skipped instead of breaking the whole list, and newly written manifests are atomically published. Deletion remains an explicit, confirmed, per-record action: it preflights the complete manifest, never follows output symlinks or Windows junctions, rolls back a multi-file deletion that fails partway, and retains an image that another manifest still references. The app does not automatically delete old, unreferenced, or over-quota files because `outputs` can contain masks, crops, overlays, and manually managed artifacts outside history ownership.

When a generation has intermediate outputs, the result panel shows a Compare Stages button for Original, Upscale, and Face Detailer image comparison. Generation warnings are also shown in the visible result summary rather than only in raw JSON.

## Package Verification

Run the release-path checks from a source checkout:

```powershell
python scripts\verify_vendor.py
python scripts\package_dry_run.py
python scripts\source_archive.py
```

The vendor check verifies the disclosed patched package hashes and product boundary. The wheel check copies package source into a temporary build root, installs the resulting wheel into a temporary target, verifies package/application version agreement and the packaged GUI JavaScript, proves that the root vendored runtime is absent, and runs a CLI dry-run. It does not turn the wheel into a standalone generation build.

The source-archive command writes `outputs\release\anima-app-0.6.0-source.zip` and its `.sha256` file, verifies required runtime, launcher, UI, notice, license, and wildcard-disclosure files, then extracts it and runs vendor plus CLI dry-run checks. A local dirty checkout can produce a review candidate. The official release command is stricter:

```powershell
python scripts\source_archive.py --require-clean
```

That mode refuses uncommitted files and reads committed Git blobs with fixed uncompressed ZIP metadata, avoiding checkout line-ending and compressor-version drift. The script does not create a tag, publish a GitHub release, or upload anything.

## Runtime Boundary

- Runtime model files live under this checkout's `models` folder.
- The app does not read model files from an external ComfyUI folder during generation.
- The app does not launch or depend on a live ComfyUI server.
- The optional LLM bridge does not launch Gemma4 itself; `ANIMA_LLM_RUNTIME_URL` must point at a separately managed local worker.
- Local model weights, detector weights, LoRA files, input images, and generated outputs are ignored by git and are not part of the public release.
- Set `ANIMA_APP_CUDA_VISIBLE_DEVICES` when you need to choose a CUDA device for Anima APP. Direct CLI runs also respect an existing `CUDA_VISIBLE_DEVICES` value when the app-specific variable is not set.
- The verified source-checkout ZIP is the supported release artifact. GitHub's automatic source archives are convenience copies and are not the digest-bound verified artifact. The Python wheel does not bundle the root-level vendored Comfy runtime and is not a standalone generation build.

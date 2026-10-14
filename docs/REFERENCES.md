# Anima APP References

This document keeps public source references, model layout, and release boundaries in one place. It must not contain user-specific local paths, private model locations, generated image paths, or machine-specific GPU inventory.

## Documentation map

- [한국어 generation tutorial](IMAGE_GENERATION_KO.md), [English](IMAGE_GENERATION_EN.md), [日本語](IMAGE_GENERATION_JA.md): install, first image, both detailer directions, stage comparison and reuse.
- [NAI token setup](NAI_TOKEN_SETUP.md): terminal input, source precedence, restart and status checks. There is no browser token field.
- [Application reference](APP_REFERENCE.md): workflow/prompt contracts, library routes, storage, environment and reproducible checks.
- [Current release](RELEASE_0.6.0.md): v0.6.0 download, setup, upgrade and verification.
- [Main update](MAIN_UPDATE_2026-10-14.md): historical integration record before the v0.6.0 release.
- [Locale settings](LOCALES.md): English/Korean/Japanese UI with original prompt preservation.

## Public Sources

The 2026-10-11 incremental NAI update is pinned to
[ComfyUI_RS_NAI_API_Request 4de914676de8ca313b8389f4303754045a6a9cfb](https://github.com/raspie10032/ComfyUI_RS_NAI_API_Request/tree/4de914676de8ca313b8389f4303754045a6a9cfb)
(2.4.6). This is the baseline for **new** ports, not a retroactive claim about every
file in the earlier 0.5.0 release. [The update checklist](NAI_NODE_UPDATE_2.4.6.md)
records individual source changes, acceptance evidence and reproduction commands.
The final upstream check found 2.5.0 at
[`ed96a4c4394a8af8f1644218a4feae73f2dc62c9`](https://github.com/raspie10032/ComfyUI_RS_NAI_API_Request/commit/ed96a4c4394a8af8f1644218a4feae73f2dc62c9),
one commit after this fixed target. Its reference inset and portable character
asset additions are not part of the 2.4.6 candidate. Do not call this candidate
complete parity with moving upstream `main`.
Medium Effort rules come from `nai_api.py`, `generators.py` and `detailer.py`, with
GPL-3.0-only attribution retained in the new rule module.
See [NovelAI's official Effort documentation](https://docs.novelai.net/en/image/effort/).
The official web hash-family map was checked on 2026-10-11 in
[`_app-b1c0ffe38c343809.js`](https://novelai.net/_next/static/chunks/pages/_app-b1c0ffe38c343809.js),
SHA-256 `8448129283ed130ef93622db123c23adf6aeb15a77649117c1661387d7723cdd`.
It maps `93F4BD30` and `70AB5786` to V5 Full Medium; operation metadata remains
necessary to distinguish generation and inpainting.

Input/response notices and region diagnostics follow the same pinned source's
[`ccc9898` audit](https://github.com/raspie10032/ComfyUI_RS_NAI_API_Request/commit/ccc9898c246775eec50c61cb0b6224f1078802e7):
`diagnostics.py`, `converters.py`, `detailer.py`, `generators.py`, `image_utils.py`
and `nai_api.py`. Request-local collection replaces the ComfyUI notice widget;
GPL-3.0-only notices remain in the derived modules. The app retains stricter
coordinate/mask alignment rejection and adds manifest/PNG/history diagnostics.
WD/PixAI model selection and download progress follow `wd_tagger.py` and
`tagger_progress.py` at the same source pin (initial change `7f435bd`). The app
uses an explicit preparation API/UI, local-only generation preflight and a
request-owned model rather than ComfyUI globals. Derived modules retain GPL-3.0-only.

Korean/Japanese guidance is adapted from the pinned source's
[`locales/ko/nodeDefs.json`](https://github.com/raspie10032/ComfyUI_RS_NAI_API_Request/blob/4de914676de8ca313b8389f4303754045a6a9cfb/locales/ko/nodeDefs.json)
and [`locales/ja/nodeDefs.json`](https://github.com/raspie10032/ComfyUI_RS_NAI_API_Request/blob/4de914676de8ca313b8389f4303754045a6a9cfb/locales/ja/nodeDefs.json)
(initial change `f3ac715`). Both installed files matched that commit during the
language feature verification. At final audit the installed copy had advanced
to 2.5.0, adding inset/asset entries; the app translations remain pinned to 2.4.6. App-specific
guidance covers strict mask alignment, explicit tagger setup, separate collapse
and visibility, and the base request in generate-then-preview. Browser-only
language storage does not alter prompt text or API IDs. The derived
`static/nai-i18n.js` retains GPL-3.0-only attribution.

Cause-specific errors follow the same pin's
[`errors.py`](https://github.com/raspie10032/ComfyUI_RS_NAI_API_Request/blob/4de914676de8ca313b8389f4303754045a6a9cfb/errors.py),
[`web/errors.js`](https://github.com/raspie10032/ComfyUI_RS_NAI_API_Request/blob/4de914676de8ca313b8389f4303754045a6a9cfb/web/errors.js),
[`web/error_messages.json`](https://github.com/raspie10032/ComfyUI_RS_NAI_API_Request/blob/4de914676de8ca313b8389f4303754045a6a9cfb/web/error_messages.json)
and `runtime_control.py`. All four installed blobs matched at the error feature
verification. At final audit the installed catalog had the three additional
2.5.0 inset/asset causes; the other three files still matched the 2.4.6 pin.
The 45 original causes are adapted to app actions; seven app causes cover generic
validation, prepared-cache/busy/save states, metadata import and prompt conversion.
The derived provider error module, `static/nai-errors.js` and message catalog
retain GPL-3.0-only licensing. The JSON catalog is covered by this notice rather
than an invalid JSON comment. App adaptation preserves existing error codes,
limited retry policy and credential masking while carrying translated guidance
through queue results, partial-result manifests and PNG region metadata.

The 22-slot/model-limit port follows `generators.py`, `nai_api.py` and
`web/characters.js` at the same 2.4.6 pin (initial change `803fc40`). All three
installed files match those committed blobs. ComfyUI's hidden widget bank is
adapted into app slot state, with per-slot enable/collapse and original slot
numbers in matching diagnostics. The app retains zero-character workflows,
strict coordinate validation, and stores editor state separately from native
NAI captions. Details and verification are in the incremental acceptance table.

### Pinned optional taggers

| Model / original source | Revision | Original model license |
|---|---|---|
| [SmilingWolf WD ViT v3](https://huggingface.co/SmilingWolf/wd-vit-tagger-v3) | `7f6b584d0bd3f55c4531f14ba3d4761b2bccdc0f` | Apache-2.0 |
| [SmilingWolf WD EVA02 Large v3](https://huggingface.co/SmilingWolf/wd-eva02-large-tagger-v3/blob/b25b82a03f7282e41aa2f257a52c7583b710bd1c/README.md) | `b25b82a03f7282e41aa2f257a52c7583b710bd1c` | Apache-2.0 |
| [PixAI Labs Tagger v1.0](https://huggingface.co/pixai-labs/pixai-tagger-v1.0/blob/9fe10addf9326e292da8a85a98ea74cd91b41771/README.md) | `9fe10addf9326e292da8a85a98ea74cd91b41771` | Apache-2.0 |

Model cards are the original documentation; weights are separately downloaded,
not redistributed in the source archive. PixAI's downloaded `tagger_pipeline.py`
must match SHA-256 `3431279fdfff234f62664999fc1fe6bb20f1e8756f7435d0e165ebd4456f7fcd`
before executing custom code. The processor/model mapping is validated too.
WD uses white square padding/BGR and PixAI uses its pinned RGB processor.
These preprocessing rules are not interchangeable. See
[preparation and runtime instructions](NOVELAI_PROVIDER.md#wd-vit--eva02--pixai-선택과-준비).

### Other public sources

- Anima model source: `circlestone-labs/Anima`
- Anima model subfolder: `split_files`
- Preferred checkpoint: `split_files/diffusion_models/anima-aesthetic-v1.1.safetensors`
- Face detector source: `Bingsu/adetailer` file `face_yolov8n.pt`
- Eye detector source: `guon/hand-eyes` file `full_eyes_detect_v1.pt`
- SAM detector source: Ultralytics asset `sam_b.pt`; SAM reference project: https://github.com/facebookresearch/segment-anything
- ComfyUI upstream project: https://github.com/comfyanonymous/ComfyUI
- ComfyUI Impact Pack upstream project: https://github.com/ltdrdata/ComfyUI-Impact-Pack
- ComfyUI NAI node source for the strict Opus guards and serialized request timing: https://github.com/raspie10032/ComfyUI_RS_NAI_API_Request (`nai_api.py`)
- NovelAI Opus usage-limit documentation: https://docs.novelai.net/en/faq/
- Vibe/Precise, matching, optional native WD and focused-region source: https://github.com/raspie10032/ComfyUI_RS_NAI_API_Request (`references.py`, `detailer.py`, `detailer_matching.py`, `wd_tagger.py`; ported modules retain GPL-3.0-only notices).
- WD source: https://huggingface.co/SmilingWolf/wd-vit-tagger-v3 (revision `7f6b584d0bd3f55c4531f14ba3d4761b2bccdc0f`).
- Reference and focused behavior: https://docs.novelai.net/en/image/vibetransfer/ ; https://docs.novelai.net/en/image/precisereference/ ; https://docs.novelai.net/en/image/inpaint/
- ComfyUI NAI character payload and six prompt-conversion source: https://github.com/raspie10032/ComfyUI_RS_NAI_API_Request (`nai_api.py`, `generators.py`, `converters.py`; converter helpers retain their GPL-3.0-only header).
- Comfy Kitchen metadata: https://github.com/Comfy-Org/comfy-kitchen
- Comfy AIMDO metadata: https://github.com/Comfy-Org/comfy-aimdo

## Model Asset Layout

The runtime reads model files from the project-local `models` tree.

Required Anima T2I files:

- `models\diffusion_models\anima-base-v1.0.safetensors`
- `models\text_encoders\qwen_3_06b_base.safetensors`
- `models\vae\qwen_image_vae.safetensors`

The command below prepares the base profile. It downloads from Hugging Face unless a local mirror is configured with `ANIMA_APP_MODEL_SOURCE`.

```powershell
$env:PYTHONPATH='src'
python -m anima_app.cli models copy-profile anima-t2i
```

The preferred Aesthetic v1.1 checkpoint is a separate profile:

```powershell
$env:PYTHONPATH='src'
python -m anima_app.cli models copy-profile anima-aesthetic-v1.1
```

The GUI selects Aesthetic v1.1 when installed and otherwise falls back to the base checkpoint.

Additional Anima-family diffusion checkpoints can be placed under `models\diffusion_models` and selected by relative `.safetensors` path.

## Optional Detector Assets

Face-detailer detector assets are prepared into `models\detectors`. By default, the app uses a valid local detector source when configured, otherwise it downloads the detector profile.

```powershell
$env:PYTHONPATH='src'
python -m anima_app.cli models copy-profile face-detailer-detectors
```

To force a local mirror, set `ANIMA_APP_FACE_DETECTOR_SOURCE` and run the same command with `--source local`.

Expected detector filenames:

- `face_yolov8n.pt`
- `full_eyes_detect_v1.pt`
- `sam_b.pt`

SAM3 is optional and prepared as a separate profile because it is a gated Hugging Face model:

```powershell
$env:PYTHONPATH='src'
python -m anima_app.cli models copy-profile sam3-detector --source download
```

Expected SAM3 filename:

- `sam3.pt`

Source: https://huggingface.co/facebook/sam3

For face detailing, SAM3 can run one combined `face` + `eyes` mask pass and one `hand` + `hands` mask pass. These are sequential repaint passes with separate denoise values; a missing concept mask skips only its own pass.

Optional fallback detector folders can be supplied with `ANIMA_APP_FACE_DETECTOR_FALLBACKS`, separated by the platform path separator.

Detector weights are downloaded into the user's local `models` tree and remain excluded from this source release.

## LoRA Assets

LoRA files are user-provided local artifacts. Import them into `models\loras`:

```powershell
$env:PYTHONPATH='src'
python -m anima_app.cli models import-lora "path\to\style.safetensors"
```

Do not redistribute private or locally trained LoRA files without confirming their source license and permission.

## Runtime Configuration

Supported environment variables:

- `ANIMA_APP_ROOT`: override the project root.
- `ANIMA_APP_MODEL_SOURCE`: optional local mirror for base model files.
- `ANIMA_APP_FACE_DETECTOR_SOURCE`: optional detector source folder.
- `ANIMA_APP_FACE_DETECTOR_FALLBACKS`: optional detector fallback folders separated by the platform path separator.
- `ANIMA_APP_AUTOCOMPLETE_SOURCE`: optional prompt-autocomplete file path.
- `ANIMA_APP_CUDA_VISIBLE_DEVICES`: optional app-specific CUDA device selection. The Windows GUI launcher defaults it to `0` before Python starts.
- `CUDA_VISIBLE_DEVICES`: standard CUDA device selection respected by direct CLI runs when `ANIMA_APP_CUDA_VISIBLE_DEVICES` is not set.
- `ANIMA_LLM_RUNTIME_URL`: optional URL for a separately managed local LLM worker.

## Quality Defaults

Default CLI/API/GUI generation settings:

- Size: `832x1216`
- Steps: `20`
- CFG: `3.5`
- Sampler: `euler_ancestral_cfg_pp`
- Scheduler: `sgm_uniform`
- LoRA strength: `1.0`

GUI starting point size presets:

- `1024x1024`: square output.
- `832x1216`: 2:3 portrait output, with landscape available by swapping orientation.
- `896x1152`: 3:4 portrait output, with landscape available by swapping orientation.

## Wildcards

Prompt wildcard files live under `wildcards\*.txt`. Tokens use `__name__` and read `wildcards\name.txt`.

Prompt preset files live under `wildcards\presets\*.txt`. Tokens use `__presets/name__` and read `wildcards\presets\name.txt`.

Wildcard file values can contain nested wildcard tokens and inline random choices using `{choice A|choice B|choice C}` syntax. File-backed wildcard tokens follow the selected wildcard mode, while inline choices are always random. The GUI preview expands the current prompt without starting generation and surfaces missing files, invalid paths, and recursive wildcard cycles before GPU work begins.

The included wildcard files were copied or derived from a local ComfyUI Impact Pack checkout under the observed GPL-3.0 license. The exact upstream revision was not preserved. Keep that provenance limit, attribution, and the license text with redistributed builds.

## Release Boundary

Current release target: `0.6.0` source-checkout beta.

Included:

- Python package source under `src\anima_app`.
- Vendored runtime source under `vendor\anima_runtime`.
- Selected vendored Python packages under `vendor\python_packages`.
- Root GUI launcher for Windows users.
- Public docs, notices, and wildcard files.
- CI and release verification scripts, including the vendored integrity check and deterministic source archive generator.

Excluded:

- Base model weights and alternate checkpoints.
- Detector weights.
- LoRA files.
- Input images.
- Generated output images and generation-info JSON files.
- Unused aimdo native allocator DLLs and ignored local `comfy-kitchen` native extensions.

Not finalized:

- Standalone binary packaging.
- Final wheel redistribution policy for vendored runtime assets.
- A standalone wheel containing the root-level vendored Comfy runtime.

## UI and library design references

The following are feature/design comparisons, not incorporated code or bundled media. License attribution for incorporated runtime code remains in [NOTICE](../NOTICE.md).

| Reference | Applied idea / boundary |
|---|---|
| [SD Studio 3.1.11](https://github.com/sunho/SDStudio/releases/tag/3.1.11) | Scene-oriented workflow, gallery and pairwise choice informed the design review; no runtime-parity claim |
| [Eagle organization](https://en.eagle.cool/support/desktop/organize) | Tags, collections and approachable asset browsing |
| [Diffusion Toolkit](https://github.com/RupertAvery/DiffusionToolkit) | Metadata/prompt-linked image retrieval |
| [Infinite Image Browsing](https://github.com/zanllp/infinite-image-browsing) | Search, compare, then reuse generation conditions |
| [Invoke gallery](https://invoke.ai/features/gallery/) | Selective condition reuse and visible context |
| [digiKam similarity](https://docs.digikam.org/en/left_sidebar/similarity_view.html) | Starting retrieval with an external image |
| [Danbooru tag API](https://danbooru.donmai.us/wiki_pages/api%3Atags) | Category-1 public artist tags for optional exact offline lookup; downloaded data is not bundled |
| [NovelAI account settings](https://docs.novelai.net/en/text/usersettings/account/) | Persistent API token issuance and replacement behavior |

VRS-INT is an optional external encoder integration; the adapter does not bundle model weights or claim native VRS decision-core behavior. [Library setup](IMAGE_LIBRARY_EN.md) describes configuration, ranking inputs and limits. Public guides use generic examples; private images, metadata, vectors and evaluation outputs stay outside the distribution.

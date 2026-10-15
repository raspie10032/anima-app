# Notices

Anima APP is a lightweight local Anima image-generation app.

## Embedded image encoder and SWEGCA evidence core

`src/anima_app/_vendor/vrs_int` adapts the Apache-2.0 VRS-INT vision encoder
from RS-Seasonal-Prompt-Generator, commit
`cf03659178f6a1abb7d1335f805a7f951511765d`. The app isolates model preparation
and fixes mean pooling across images with different token counts. Source hashes,
modifications and model revisions are recorded in `UPSTREAM.json` and `model.json`.
Gemma vision weights are downloaded separately and retain their upstream model
terms; they are not part of the source or wheel archive.

`src/anima_app/_vendor/swegca` includes the MPL-2.0 SWEGCA Architecture evidence
accumulator and its required Python kernel/arbiter definitions at commit
`5901a5aa2dcbd0ac7ad12ac6dd745699f72288a8`. Relative imports and a Python 3.10
StrEnum compatibility shim are the only upstream code adaptations. Decision
thresholds and algorithms are unchanged. Keep the included MPL license and
per-file source/provenance notices with redistribution. The app adapter replays
explicit image-case evaluations and stores receipts; it does not claim to be
the C++ SWEGCA-bit native graph engine.

## Runtime Code

The `vendor/anima_runtime` tree contains a ComfyUI 0.22.2-derived runtime snapshot. The reported version is preserved in `vendor/anima_runtime/comfyui_version.py`; the exact upstream commit was not preserved. Keep the upstream license and attribution notices with redistributed source or packaged builds, and do not claim commit-level reproducibility for this snapshot.

Relevant upstream project:

- ComfyUI: https://github.com/comfyanonymous/ComfyUI

## NovelAI Node Ports

Prompt converters, reference preparation/cache behavior, region ownership, focused inpainting,
character matching and optional native WD inference are derived from
https://github.com/raspie10032/ComfyUI_RS_NAI_API_Request. Ported modules retain their
`SPDX-License-Identifier: GPL-3.0-only` notices. ComfyUI graph interfaces are replaced by
standalone request, managed-input and queue contracts. NovelAI is an external service;
this app is not an official NovelAI client or a guarantee of account billing behavior.
The incremental 2026-10-11 update uses source commit
`4de914676de8ca313b8389f4303754045a6a9cfb` (2.4.6), including request-local
conversion notices, detailer diagnostics, WD/PixAI tagger selection and download
progress. Korean/Japanese guidance in `static/nai-i18n.js` is adapted from the
same commit's `locales/ko/nodeDefs.json` and `locales/ja/nodeDefs.json`, retaining
GPL-3.0-only attribution and documenting app-specific behavior.
Cause-specific errors in `providers/novelai/errors.py`, `static/nai-errors.js`
and `static/nai-error-messages.json` derive from the same pin's `errors.py`,
`web/errors.js`, `web/error_messages.json` and `runtime_control.py` and are
GPL-3.0-only. The catalog's 45 source causes are adapted for app controls with
seven app additions. JSON attribution is recorded here and in `docs/REFERENCES.md`.
The optional WD ViT/EVA02 and PixAI model assets are separately fetched
from their pinned Hugging Face repositories (Apache-2.0 model cards); their
weights are not bundled. PixAI's custom loader code is checksum-verified before
execution. See `docs/REFERENCES.md` for exact revisions and code SHA-256.
This pin describes the incremental
update, not the unidentified original snapshot for every earlier 0.5.0 port.

The subsequent RS NAI 2.9.0 compatibility update is based on
`a1c7d40bd40598665ab52d869968ccfe3fe1a07a` of the same GPL-3.0-only project.
Its `rs_nai` original-generation/edit record and WebP EXIF conventions inform
`providers/novelai/rs_metadata.py`, `metadata.py` and `images.py`. Workflow
inheritance, output settings and detector selection are adapted to the app's
existing request and history model. See `docs/NAI_NODE_UPDATE_2.9.0.md` for scope.
See `docs/NAI_NODE_UPDATE_2.4.6.md` for per-feature implementation and evidence status.

## Vendored Python Packages

The `vendor/python_packages` tree contains selected runtime packages and their metadata:

- `comfy-kitchen` 0.2.8, Apache-2.0, https://github.com/Comfy-Org/comfy-kitchen
- An Anima APP no-native compatibility shim based on `comfy-aimdo` 0.3.0, GPL-3.0, with repository metadata at https://github.com/Comfy-Org/comfy-aimdo

Keep each package's bundled license files and notices with redistributed builds.
The `comfy-aimdo` base version is retained in its metadata, but several Python modules and its `RECORD` are intentionally patched for Anima APP. See `vendor/README.md` for the exact disclosure and remaining native-binary boundary.

## Optional Detector Runtime

Face-detailer support can use Ultralytics YOLO/SAM detector assets when the optional `face-detailer` extra is installed.

The app can download detector weights into the user's local `models` tree:

- `face_yolov8n.pt` from `Bingsu/adetailer`.
- `full_eyes_detect_v1.pt` from `guon/hand-eyes`.
- `sam_b.pt` from Ultralytics assets, with SAM reference material from `facebookresearch/segment-anything`.
- `sam3.pt` from the gated `facebook/sam3` model repository.

Detector weights are not included in this repository. SAM3 access requires accepting the model repository's access conditions. Check each source model card, its access terms, and the optional Ultralytics runtime license before redistributing detector weights or packaged builds that include them.

## Model And LoRA Artifacts

Anima checkpoints are obtained from `circlestone-labs/Anima`, including the preferred Anima Aesthetic v1.1 profile. The model repository currently identifies its license as `circlestone-labs-non-commercial-license`.

Base model assets, alternate checkpoints, LoRA files, detector weights, input images, and generated output images are local user artifacts. They are ignored by git and are not part of the public source release. Review the upstream model license before using or redistributing any downloaded checkpoint.

## Wildcards

The `wildcards` folder includes text wildcard files copied or derived from a local ComfyUI Impact Pack checkout. The observed upstream license was GPL-3.0; the exact source revision was not preserved.

Relevant upstream project:

- ComfyUI Impact Pack: https://github.com/ltdrdata/ComfyUI-Impact-Pack

Keep Impact Pack attribution and the corresponding license notice with any redistributed build that includes derived wildcard files.

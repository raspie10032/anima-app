# App reference: generation, workflows and the image workspace

[README](../README.md) · [한국어 walkthrough](IMAGE_GENERATION_KO.md) · [English](IMAGE_GENERATION_EN.md) · [日本語](IMAGE_GENERATION_JA.md) · [Sources/model layout](REFERENCES.md)

This describes the current source tree. For endpoint schemas and numeric limits, read the running server's `GET /api/openapi.json`. Some library routes are implemented separately from that schema; their contract is listed below. The server is a trusted-local-user application, not an authenticated multi-user hosting service.

## Engines and stages

| Concern | Contract |
|---|---|
| Base provider | `local` for Anima, `novelai` for NAI |
| Base operation | Anima generation/i2i via local request; NAI `generate`, `img2img`, `infill`, `focused_infill`, `detail` |
| Added operations | `local:detail`, `local:upscale`, `novelai:detail` |
| Workflow shape | `{"version":1,"steps":[...]}` with 1–6 added stages; omit `workflow` for no added stages |
| Stage shape | `provider`, `operation`, `inherit_prompt` (boolean), `request` (stage settings) |
| Flow | Each stage consumes the previous completed image, records input/output hashes, and preserves intermediate outputs |
| Resolution | NAI detail must preserve the preceding output dimensions; an incompatible upstream upscale is rejected |
| Failure | Stop before subsequent stages; retain completed files and journal. No automatic retries of paid requests or crash-resume |
| Inline processing | Older detail/upscale controls can still run in the base request; inspect the first-stage summary to avoid unintended duplicate processing |

Implementation: [`workflows.py`](../src/anima_app/workflows.py), [`workflow.js`](../src/anima_app/static/workflow.js), [`server.py`](../src/anima_app/server.py). Quick direction buttons replace the added-stage list and disable inline processing. Generation only clears the added list without disabling existing inline controls.

## Prompt routing and provenance

API callers opt in with `"prompt_routing":{"source":"auto"}`. The GUI enables routing. Other accepted sources are `comfyui`, `naiv4`, `oldnai` and `native` (no conversion). If omitted by an API client, prompts remain native to preserve compatibility.

Anima targets Comfy-style weighting with `@artist`; NAI V4/V5 targets numeric `weight::...::` with `artist:`. V3 uses legacy weighting and can require approximation. Mixed weight syntaxes fail automatic detection; choose a consistent source syntax or explicitly disable conversion.

`artist:` and `@` are explicit. Only unprefixed complete tags are checked against the offline catalog, with space/underscore, case and escaped-bracket normalization. Unknown tags remain unchanged. Generation does not fetch the catalog; `scripts/update_artist_catalog.py` downloads public active artist tags separately. The default snapshot is partial. A failed update, including HTTP 429, retains the previous snapshot.

`POST /api/prompts/plan` accepts generation settings and returns one conversion receipt per stage. It does not generate or expand random wildcards. Execution expands wildcards before conversion. Minimal preview example:

```json
{
  "provider": "novelai",
  "operation": "generate",
  "prompt": "(artist:example_artist:0.9), landscape, soft light",
  "negative_prompt": "blurry",
  "nai_model": "nai-diffusion-4-5-full",
  "width": 768,
  "height": 1024,
  "steps": 28,
  "prompt_routing": {"source": "comfyui"}
}
```

Library reuse attaches `generation_sources`, up to 16 entries with exact `asset_id`, `record_id` (64 lowercase hexadecimal characters) and `scope` (`artists`, `prompt`, `all`). Manifests preserve authoring settings, effective provider prompts and conversion receipts separately. A reference in the result returns to that precise case record. This is provenance, not a claim that a selected style caused a particular output.

Implementation: [`prompt_routing.py`](../src/anima_app/prompt_routing.py), [`artist_catalog.py`](../src/anima_app/artist_catalog.py), [`authoring.js`](../src/anima_app/static/authoring.js).

## HTTP entry points

| Method / path | Purpose |
|---|---|
| `GET /api/health`, `/api/capabilities`, `/api/openapi.json` | Runtime readiness, available operations, machine-readable schemas |
| `GET /api/nai/status` | Token configured/source/variable, without its value or remote authentication |
| `POST /api/jobs`, `GET /api/jobs` | Submit and inspect queued work; request `dry_run` for offline execution validation |
| `POST /api/prompts/plan` | Preview per-stage prompt routing |
| `POST /api/prompts/convert` | Convert one explicit prompt syntax |
| `POST /api/inputs/reference` | Upload a validated app-managed reference image |
| `POST /api/metadata/novelai` | Import supported generation metadata from an image |
| `GET/POST /api/presets` | List/save reusable settings; import/export routes are described in OpenAPI |
| `GET /api/library/status`, `/api/library/items` | Index/job status; browse with `q`, `offset`, `combo`, `favorite` |
| `GET /api/library/item/{id}` | Case records, sources and reusable conditions |
| `GET /api/library/thumbnail/{id}`, `/api/library/preview/{id}` | Thumbnail or larger preview |
| `POST /api/library/import` | Start folder import, history sync or VRS indexing; see implementation for `kind` |
| `POST /api/library/cancel` | Request cancellation of current library work |
| `POST /api/library/query-image?mode=visual` | Raw PNG/JPEG/WebP body; visual retrieval without importing the query |
| `POST /api/library/search` | Existing-case query with `id`, `mode`, optional `limit` |
| `POST /api/library/annotate` | Save favorites, tags, collection name or note |
| `POST /api/library/feedback` | Store separate similarity/reuse feedback |
| `POST /api/library/compare`, `/api/library/compare/undo` | Store/retract a reference-based candidate judgment |

Library routes: [`library_http.py`](../src/anima_app/library_http.py). Do not send token fields in any request body; credentials are read only from the server environment.

## Storage and portability

Paths below are relative to the application root (working directory unless `ANIMA_APP_ROOT` is set).

| Location | Content / lifetime |
|---|---|
| `models/` | Local weights, LoRAs and optional taggers; excluded from Git |
| `inputs/references/` | Validated uploaded and workflow reference images; excluded from Git |
| `outputs/images/` | Generated and intermediate images |
| `outputs/manifests/` | Generation records, authoring/effective prompts and references |
| `outputs/workflows/` | Ordered execution journals and stage hashes |
| `outputs/presets/` | Named generation presets |
| `outputs/library/library.sqlite3` | Assets, records, combinations, vectors, queries, feedback and comparisons |
| `outputs/library/thumbnails/` | Derived thumbnails |
| `outputs/artist-catalog/danbooru.json` | Optional local artist-tag snapshot |
| Browser storage, current origin | Generation/library drafts, undo state, locale; no token |

The library references original images rather than replacing them. Keep their paths accessible. Byte duplicates share an asset; different records can remain connected. Pixel-identical images are excluded against the query and within a result list. Named presets do not embed model or reference files. For backups, stop writes and use SQLite's backup facility or back up the database consistently with its journal files; copying only a live SQLite file can miss recent transactions.

The current pilot limit is **2,000 assets**. Basic CPU similarity uses fixed color/layout/edge features. VRS uses a separately configured VRS-INT Gemma 4 encoder, comparing images before joining recorded metadata. Encoding shares the app generation lock. It does not stop other GPU applications. Feedback is stored, not used for automatic ranking updates. Native VRS decision-core integration remains future work.

## Environment and localization

| Variable | Purpose |
|---|---|
| `NAI_ACCESS_TOKEN` | Primary NAI token, server environment only |
| `NAI_API_TOKEN` | Compatibility fallback when primary is unset/blank |
| `ANIMA_APP_ROOT` | Application root for models, inputs, outputs and other local resources |
| `ANIMA_APP_MODEL_SOURCE` | Local model-copy source |
| `ANIMA_APP_FACE_DETECTOR_SOURCE` | Local detector-copy source |
| `ANIMA_APP_WD_TAGGER_SOURCE` | Optional tagger storage override |
| `ANIMA_LIBRARY_VRS_ROOT` | Checkout providing `vrs_int.encoder` |
| `ANIMA_LIBRARY_VRS_ENCODER` | Prepared local image-encoder model directory |
| `ANIMA_LIBRARY_VRS_PYTHON` | Compatible interpreter for the VRS worker |

See [token commands](NAI_TOKEN_SETUP.md), [VRS setup](IMAGE_LIBRARY_EN.md), and [model configuration](REFERENCES.md). `.env` is not loaded automatically.

Locale is `en`, `ko` or `ja`, stored as `anima.locale` for the browser origin. Supported browser language is used initially, then English fallback. Old `anima.nai.language` settings are migrated on initial read. UI translation uses [`i18n.js`](../src/anima_app/static/i18n.js) and [`ui-messages.json`](../src/anima_app/static/ui-messages.json), with NAI guidance/errors in their separate catalogs. Prompts, model IDs, records and request bytes are not translated. Raw server errors/conversion warnings and browser-native controls can use their original language.

## Verification and publication boundary

Run from a development environment with the project installed:

```bash
python -m ruff check src tests scripts
python -m pytest -q
python scripts/verify_vendor.py
python scripts/browser_locale_smoke.py
python scripts/browser_generation_smoke.py
python scripts/browser_library_smoke.py
python scripts/browser_authoring_smoke.py
python scripts/package_dry_run.py
python scripts/source_archive.py --require-clean
```

Browser checks require Playwright and its Chromium runtime. They use temporary synthetic data and headless browsers, then close them. Dry-run/browser tests do not establish remote NAI billing, GPU quality, or Windows GUI acceptance. The source archive requires a clean checkout for official output; the wheel deliberately excludes the root vendor runtime. See [main update notes](MAIN_UPDATE_2026-10-14.md) for the recorded verification scope and remaining features.

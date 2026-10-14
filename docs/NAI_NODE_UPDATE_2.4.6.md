# RS NAI 2.4.6 incremental port

Checked 2026-10-11. App baseline: `b3635050980518242923eb486847b7bfe90b744a`.
Source baseline: [RS NAI 4de914676de8ca313b8389f4303754045a6a9cfb](https://github.com/raspie10032/ComfyUI_RS_NAI_API_Request/tree/4de914676de8ca313b8389f4303754045a6a9cfb), version 2.4.6.
App remote main still matches the baseline. The final source remote check found
[`ed96a4c4394a8af8f1644218a4feae73f2dc62c9`](https://github.com/raspie10032/ComfyUI_RS_NAI_API_Request/commit/ed96a4c4394a8af8f1644218a4feae73f2dc62c9),
version 2.5.0, one commit after the fixed 2.4.6 target. Its reference inset and
portable character asset features are outside this target. Source comes from committed blobs, not
an uncommitted historical integration checkout. Existing app changes and its
separate historical checkouts are preserved.

One feature is implemented and verified per turn. All rows must be complete
before the update is declared finished. This document describes development
work, not a release announcement or live NovelAI acceptance.

| Order | Feature and acceptance scope | Source change | Status |
|---|---|---|---|
| 1 | V5 Full Medium generation/Img2Img/infill/Focused/detailing; fixed conditioning; model metadata; effective settings; protected crop partial strength | `6e778a9`, `2b58081`, `cfb9519`; final `nai_api.py`, `generators.py`, `detailer.py` | Implemented, local/mock verified |
| 2 | Node audit: per-conversion loss notices, finite/input/model checks, empty/misaligned masks, Curated fallback notice, ZIP image selection, collision-free saves, matching/region skip reasons and retry diagnostics | `ccc9898`; `diagnostics.py`, `converters.py`, `image_utils.py`, `detailer.py`, `nai_api.py` | Implemented, local/mock verified; stricter existing app checks retained |
| 3 | WD ViT v3 / EVA02 / PixAI selection, model-specific dependencies, pinned snapshots/code integrity, BGR versus RGB preprocessing, dense eligible-tag scores, cache isolation, per-file progress, download/load/cancel errors and setup UI | `7f435bd`; `wd_tagger.py`, `tagger_progress.py`, dependency files | Implemented; local/mock and all three native CPU models verified |
| 4 | 22 character slots; V5 22 vs V4/V4.5 6, V5 Curated infill fallback 6; hide/disable without losing values, request validation, metadata/preset/history/conversion/matching compatibility | `803fc40`; `generators.py`, `nai_api.py`, `web/characters.js` | Implemented; local/mock and browser verified |
| 5 | Korean/Japanese labels, explanations and usage guidance adapted to app controls; language persistence and fallback | `f3ac715`; `locales/ko/nodeDefs.json`, `locales/ja/nodeDefs.json` | Implemented; local/mock browser verified |
| 6 | Localized error cause and next action; explicit codes/stages, status/body preservation with token masking, cancellation/unknown-remote semantics; no retry expansion; visible/cleared error states | `4de9146`; `errors.py`, `web/errors.js`, `web/error_messages.json`, `runtime_control.py` | Implemented; local/mock and browser verified |
| 7 | Requirement audit, documentation/attribution consistency, complete current regressions and browser checks, wheel/source archive verification and final handoff | All above, README/NOTICE/REFERENCES and verification scripts | Complete for pinned 2.4.6 local/mock scope; real CPU taggers and artifacts verified |

The integrated Vibe/Precise/Focused merge (`228144d`) is compared as part of
these rows; existing equivalent behavior is retained, new semantics must be
covered explicitly. ComfyUI-specific widgets/events are implemented through
the app's form/API/queue, not copied as unusable graph plugins.

## Final verification and reproduction

The 2026-10-11 final code regression passed **1,054 tests**, with only the
Windows-specific launcher test skipped on Linux. All six new feature suites
and preserved baseline browser suites were rerun on the combined candidate:

| Requirement | Current source regression | Browser checks | Additional evidence |
|---|---|---:|---|
| Medium T2I / Img2Img / dedicated infill / Focused / automatic detailer | `tests/test_novelai_medium.py` | 7 | Exact wire settings, hash-based metadata, original input preservation, zero values and account gate |
| Input / response audit, conversion loss, region / retry diagnostics | `tests/test_novelai_audit.py` | 6 | Failed tight retry retains its last score/reason; empty detection preserves source |
| WD ViT / EVA02 / PixAI | `tests/test_novelai_tagger.py` | 9 | All three real offline CPU models again selected original slots 2 then 1 on supplied face boxes; input/weight hashes preserved |
| 22 slots, per-model limits, hide / disable / collapse / restore | `tests/test_novelai_character_slots.py` | 8 | Presets, queue, history, PNG, converter, inactive bank and original slot numbering |
| Korean / Japanese guidance and persistence | `tests/test_novelai_language.py` | 10 | Stored/browser locale fallback, cross-tab and blocked storage; values/uploads retained |
| 45 upstream + 7 app error causes | `tests/test_novelai_errors.py` | 12 | All three catalogs; UI languages, classification, token sanitization, partial-result history and PNG |
| Preserved Img2Img / Vibe / Precise / focused matching | `tests/test_novelai_references.py`, `tests/test_novelai_img2img.py`, `tests/test_novelai_detailer.py` | 9 | Cache reuse, mutual exclusion, original weighted prompts, partial-failure retention |
| Preserved focused behavior | `tests/test_novelai_focused.py` | 7 | Protected crop gate, zero strength, cancellation and retained results |
| Provider / local switching, queue, conversion | `tests/test_server.py`, `tests/test_novelai_characters.py` | 18 | Local renderer is synthetic; current 22-slot controls, remote-result retention |
| Ordinary masked infill | `tests/test_novelai_inpaint.py` | 8 | Painted/uploaded masks, Curated routing, outside pixels and refresh recovery |
| Hand / face / eye detailing | `tests/test_novelai_hands.py` | 8 | Synthetic detectors/SAM; preflight, masks, cancel, source retention |
| Finite / infinite queue seed sequence | `tests/test_server.py` | 6 | Both providers, explicit zero and maximum rollover, history/manifest |

These are **108 browser cases/checks in 12 suites, with zero page errors**.
The application paths execute against synthetic NAI/account/detector results;
native CPU tagger inference is separately recorded. The stale pre-update
browser harness expectations (five-character UI cap, raw dependency text and
the old `_load` stub signature) were updated to the implemented contracts.
The error harness now checks the cause code and install guidance as well as
the translated label. No application assertion was relaxed to hide a failure.

Fresh development evidence is under `outputs/nai-update-20261011/final/`:
`full-regression.xml`, `browser/<feature>/report.json`, `native/report.json`,
and the final `report.json`. These ignored local artifacts are not available
from a GitHub checkout. The test and verifier source needed to reproduce them
is included in the source ZIP. Earlier per-feature sections below describe
their own earlier observations; use the final report for the combined state.

The installed node is now a 2.5.0 file snapshot rather than an independent Git
checkout. Of 17 compared 2.4.6 files, 13 remain byte-identical. `diagnostics.py`,
the two `locales/*/nodeDefs.json` files and `web/error_messages.json` differ,
matching the later `ed96a4c` blobs: dict-result notice handling and new inset/
asset translations/errors. The final verifier records both SHA-256 hashes
and rejects unexplained drift. The app retains its pinned 2.4.6 semantics.

Reproduction in an app development environment with the test dependencies,
Node and Playwright Chromium available (no credentials needed):

```bash
export PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
unset NAI_ACCESS_TOKEN NAI_API_TOKEN
python -m pytest -q --junitxml=outputs/nai-update-20261011/final/full-regression.xml
python -m ruff check src tests scripts
node --check src/anima_app/static/app.js
node --check src/anima_app/static/nai-i18n.js
node --check src/anima_app/static/nai-errors.js
for feature in medium audit tagger characters language errors remaining; do
  python "scripts/browser_nai_${feature}_smoke.py" --output-dir "outputs/nai-update-20261011/final/browser/$feature" || exit 1
done
for feature in focused provider inpaint queue_seed; do
  python "scripts/browser_${feature}_smoke.py" --output-dir "outputs/nai-update-20261011/final/browser/$feature" || exit 1
done
python scripts/browser_nai_hands_smoke.py --output-dir outputs/nai-update-20261011/final/browser/hands
python scripts/native_nai_tagger_smoke.py --cache-dir /path/to/existing/rs_wd_tagger --image /path/to/original/workflow_example/example.png --output-dir outputs/nai-update-20261011/final/native
python scripts/package_dry_run.py --output-dir outputs/release/nai-node-2.4.6-final-20261011/verified
python scripts/source_archive.py --output-dir outputs/release/nai-node-2.4.6-final-20261011/verified
python scripts/audit_nai_update_release.py --evidence-dir outputs/nai-update-20261011/final --archive outputs/release/nai-node-2.4.6-final-20261011/verified/anima-app-0.5.0-source.zip --wheel-report outputs/release/nai-node-2.4.6-final-20261011/verified/wheel-report.json --source-repo /path/to/source/git/repository --installed-source /path/to/installed/node
```

Use a new output directory for a repeated wheel build. The native script
requires existing pinned weights and compatible optional dependencies; it
blocks HTTP rather than downloading missing files. Source comparison requires
both pinned and observed-upstream commit objects in the reference repository.
See [tagger setup](NOVELAI_PROVIDER.md#wd-vit--eva02--pixai-선택과-준비).

The source ZIP includes documentation, tests, scripts, licenses, static files,
JSON catalogs and the vendored local runtime. It excludes weights, inputs,
outputs, credentials, Git history and environments. The wheel preserves all
Python/JS/JSON app bytes and LICENSE/NOTICE, but omits the vendored runtime.
Both artifacts retain app version 0.5.0 and carry SHA-256 sidecars. The final
audit checks content equality, source ZIP reproducibility, isolated wheel
installation/import/CLI, and extracted source vendor/CLI/NAI dry-run behavior.
Publication would require a clean committed checkout; these are local review
artifacts and do not replace the existing installation.

Actual NAI account/image/reference-encoding requests in this update are zero.
Endpoint acceptance, generation quality, Anlas billing, native GPU execution,
Windows GUI, fresh model downloads and optional dependencies installed into
the app environment remain unverified. These are explicit verification limits;
neither the package nor this audit establishes those outcomes.

## Cause-specific multilingual errors acceptance

Source `errors.py`, `web/errors.js`, `web/error_messages.json` and
`runtime_control.py` match the installed node and pinned commit. The source's
45 causes are retained, adapted to app actions, with seven additions:
`REQUEST_INPUT`, `TAGGER_CACHE`, `BUSY`, `SAVE_FAILED`, `CANCELLED`,
`METADATA_INPUT`, `PROMPT_CONVERSION`. All 52 have English/Korean/Japanese
cause-and-action pairs. GPL-3.0-only attribution is recorded in modules and
NOTICE/REFERENCES (including the JSON catalog).

The API keeps existing `error_code`, message and remote-outcome fields and adds
`error_detail` with cause, stage, upstream status, exception type, bounded safe
details and localized explanations. Validation, subscription, generation,
response parsing, references, tagger preparation/inference, output/manifest
saving and partial detailer paths have explicit context. ContextVar-scoped
stages do not leak between concurrent/nested calls. Real exception types and
errno identify memory, permissions and disk-full failures; user text is not
used to guess causes. Only allowed HTTP message/error text is retained; token,
Bearer, credential-field, long encoded content and HTML filters apply.
Untrusted external exception text is omitted while type/errno are retained.

UI result, tagger, metadata and conversion panels show the cause and next
action with an expandable technical detail. Locale changes re-render current
failures; new work and success clear them. Queue failures keep the same object;
partial detailer failures survive manifest/PNG/history restoration with
completed outputs. No-image failures do not invent image history records.
Timeout/connection/5xx/bad-response failures remain uncertain with no automatic
resubmission; only the prior single bounded 429 retry is retained. Cancellation
and Opus guards remain enforced.

Evidence (local artifacts under `outputs/nai-update-20261011/errors/`):
full regression **1049 passed / one Windows launcher skip**; error-focused
suite **41 passed**, plus one new server static/API coverage test. The browser
script `scripts/browser_nai_errors_smoke.py` covers **12 scenarios**, zero page
errors/external HTTP attempts, with 11 synthetic image attempts. It covers
conversion/upload validation, 401/403/429/timeout, malformed ZIP, post-response
disk-full, recovery/clearing, tagger errors, partial history/PNG restoration,
language switching, English fallback and text-only rendering. Dedicated Firefox
also restored the partial result and showed Korean timeout/unknown-outcome and
completed-output guidance. Its text snapshot is in `browser/firefox-history-ko.txt`.
Ruff, bundled Node syntax and diff checks pass. Actual NAI account/encoding/image
requests are zero; real provider failures/billing and Windows execution remain
unverified. Final package and requirement-by-requirement audit are still row 7.

## Korean/Japanese guidance acceptance

Both locale files match the installed node and the pinned source commit.
Git blob IDs: `9bad2cf33558acc35214a8326347735b0c9e5c94` (Korean),
`bf96ecf624be7659d195b3731957122840529f24` (Japanese).
`static/nai-i18n.js` retains GPL-3.0-only attribution and maps source guidance to
app controls: one-image input, Medium conditioning, Opus/cancellation,
character limits/hide/collapse, reference support/cache/cost, native detection,
tagger preparation and conversion loss. It adds app-specific metadata guidance.
Strict mask dimensions and explicit preparation replace the node's resize and
implicit download flow. Standalone preview and generate-then-preview have
different request implications, stated in both languages.

Language persists only in browser storage, follows Japanese browser language
when no preference exists, defaults to Korean for unsupported languages, and
works without storage. Other tabs follow changes/removal. Text-only updates
preserve cards, input values, collapse, images/masks and converter previews.
API model IDs and payloads are unchanged; preset/history/PNG restore retains
the browser's language and original settings, including hidden slot 22.
Local-engine-only UI, history labels and raw server diagnostics are outside this
guidance scope; structured multilingual error causes are covered by row 6 above.

Evidence: `tests/test_novelai_language.py` checks fallbacks, catalog parameter
parity and storage behavior; `test_server.py` checks script delivery/order and
syntax; `scripts/browser_nai_language_smoke.py` covers ten DOM/API scenarios
including a synthetic queue result with history/PNG/preset restore, selected
reference/mask and converter state, cross-tab storage and unsupported languages,
safe prompt text, 420px layout and localized Medium/character validation.
Local reports are under `outputs/nai-update-20261011/language/`; dedicated
Firefox snapshots independently confirm Japanese guide/control rendering.
Final regression: **1007 passed, one Windows-only launcher skipped**; targeted:
**14 passed**; browser: **ten scenarios, zero page errors**. Dedicated Firefox
also confirmed Japanese after an actual reload. All account, transport and
image responses are synthetic. No live NAI request.

## Character slots acceptance

The three source files above match the installed node at the fixed 2.4.6 commit.
Their Git blob IDs are `ed8e4f874da8a86898c46703594257ba19f539e4` (generators),
`c4d82715b471159f0968599ceb5da841d4b4c821` (API) and
`14d54e89c903ac8bef8887fc346f75d5fa46821b` (character UI).
App adaptations preserve original GPL attribution and strict finite 0–1
coordinate validation instead of silently clamping legacy coordinates.

- Model capabilities and API validation allow V5 22 active characters, V4/V4.5
  six and V3 zero. Curated infill resolves to V4.5 before checking the six-person
  limit. Model switches never truncate the saved bank. Automatic detailing
  maps a selected character into each crop's base prompt, not an infill character
  array; a V5 Curated base with 22 remains valid through this single-character path.
- `nai_character_slots` saves up to 22 entries with enable/collapse state;
  `nai_character_count` selects a visible prefix (0–22, including prior zero-slot
  workflows). Only enabled visible entries become native `nai_characters`.
  An explicit conflicting active list is rejected. Hidden/disabled slots keep
  their values; collapsing alone does not exclude a character.
- Presets, queue and history preserve the full bank. Weight conversion and
  wildcard expansion use enabled visible entries; original values remain in
  requested metadata. Medium clears character negatives only in effective
  request settings. Matching diagnostics retain original, one-based slot numbers.
- Native captions import up to 22; valid but model-excess captions remain intact
  with a warning. Malformed/multi-center/over-22 data is rejected as a whole.
  App output adds a bounded editor-state iTXt to a separate `-settings.png` and
  keeps the original PNG variant. Original chunks, decoded pixels and stealth
  alpha survive. Sharing that PNG includes saved hidden/disabled prompt values.
  Invalid editor state falls back to valid native captions with a warning.
- `tests/test_novelai_character_slots.py`: **47 passed**. Covers model boundaries,
  validation before transport, all five operations, wildcard/Medium state,
  original slot 22 matching, preset/queue/import round trips, raw and alpha PNG
  preservation, malformed input and the 1 MiB metadata bound.
- Full suite: **995 passed, one Windows-only launcher skipped**, bundled Node
  on PATH; Ruff, JavaScript syntax and whitespace checks pass.
- `scripts/browser_nai_characters_smoke.py`: **eight scenarios**, zero page
  errors/external HTTP attempts, five synthetic image attempts, zero live NAI
  calls. Tests 22 ordered wire captions, six/zero limits, overflow blocking,
  hide/disable/collapse, history, preset/PNG restore and slot22 weight conversion.
  Dedicated Firefox separately restored a saved Medium bank, revealed slot22
  with coordinates 0/1 and original negative, and toggled its collapse state.

Ignored evidence is under `outputs/nai-update-20261011/characters/`. This is
local/mock acceptance; real NAI 22-character endpoint acceptance, image quality,
billing and Windows GUI remain unverified. No release archive or remote branch
was changed for this feature. Rows 5–7 remain pending.

## Medium acceptance

- Models: `nai-diffusion-5-full-medium` and its distinct `-inpainting` variant.
- 14 steps, `k_euler_ancestral`, zero CFG rescale, fixed Heavy base negative and
  empty character negatives. Prompt-based `nsfw` prefix matches the source.
- CFG/seed zero and original submitted settings survive normalization.
- Non-Medium behavior remains unchanged, except the shared missing V4/V5
  detailer partial-strength API field is now supplied and validated.
- Actual request values are checked before protected transport; partial
  `img2img` strength must agree with the internally planned Focused crop.
- `93F4BD30`/`70AB5786` select the Medium family. Operation remains derived from
  request type/model ID; hash-only ambiguity requires manual selection.
- V5 account guard and existing reference incompatibilities remain effective.

Evidence: `tests/test_novelai_medium.py` (30 cases), updated focused/guard tests,
and `scripts/browser_nai_medium_smoke.py` (seven browser acceptance categories).
The browser test covers model switching, queue T2I, low allowance rejection,
Img2Img, metadata-to-infill, Focused, automatic detailing and history restoration.
It blocks external requests and injects synthetic image/account/detector responses.

Local reports under ignored `outputs/nai-update-20261011/medium/` are not public
attachments: full suite 886 passed / four skipped, then the three Node-dependent
checks passed with the bundled Node on PATH. Combined: **889 passed / one
Windows-only launcher skipped**. Ruff, JavaScript syntax and diff whitespace
checks passed. Dedicated Firefox restored Medium/detail settings from history
and displayed the fixed-setting warning and completed synthetic result.

No live NAI account, reference encoding or generation request was sent. These
checks do not establish endpoint acceptance, image quality or billing. This
increment has not been committed/pushed or added to the final release archive.

## Input/response/diagnostics acceptance

Compared the complete audit commit `ccc9898c246775eec50c61cb0b6224f1078802e7`
and its final versions at the pinned 2.4.6 commit. Installed converters,
diagnostics, generators, image utilities, detailer and API files have identical
Git blob hashes to that pin. The app equivalents are:

| Source behavior | App behavior and evidence |
|---|---|
| Execution-local notices and clearing stale UI | Context-local, bounded/deduplicated conversion warnings; no prompt-fragment logging; input/target/syntax edits invalidate notices and apply state. Concurrent/nested/failure tests and browser clear-state assertions. |
| Dropped malformed ComfyUI groups, out-of-range weights, trailing NAI scope text, nonpositive legacy weights | Preserve node conversion output, but name the actual loss/substitution. Literal escapes survive. `tests/test_novelai_audit.py` and browser conversion cases. |
| Input frame/range/model validation | Existing API rejects animated source/mask before enqueue and transport; rejects invalid model IDs, nonfinite numbers and out-of-range coordinates. It does not silently clamp invalid coordinates. New audit tests plus existing request/converter regressions. |
| Empty or mismatched masks | Existing API rejects empty, differently sized or misaligned managed inputs. Soft masks and transparent-pixel handling remain intact. New eroded-empty-mask test; existing inpaint/focused tests cover preservation and alignment. |
| PNG selection inside response ZIP and collision-free save | Skip metadata/directories, accept case-insensitive PNG suffix. Keep one-image contract, size limits and PNG verification. Unsupported compression becomes sanitized unknown outcome; no automatic replay. Same-clock saves keep both PNG/manifest pairs. |
| WD retry and region diagnostics | Failed tight retry now retains the latest score/margin. Region-limit, low-score, ambiguous-margin and empty-mask reasons appear in result/manifest/PNG/history. Preview overlays contain region, character, status and score. No-detection/all-skipped notices specifically describe detailer requests, not any preceding base request. |
| Curated fallback and rate-limit diagnostics | Show V5 Curated → V4.5 Curated infill route; clear when switching models. Record actual 429 wait and retry scheduling per request/crop. Existing one-retry and cancellation bounds remain. |

WD runtime dependency/progress changes from the audit are included with the
model-specific tagger work in row 3, completed below. ComfyUI tensor
batch widgets have no direct app equivalent: this app accepts one managed
image and one mask. App validation boundaries are retained rather than adding
unused tensor conversions or copying graph-specific UI.

Evidence: **911 passed / one Windows-only launcher skipped** in the full suite,
including all three bundled-Node checks. The new audit file has **22 passing
cases**. `scripts/browser_nai_audit_smoke.py` passed six scenarios with zero
page errors or external HTTP attempts. Dedicated Firefox snapshots confirm
loss notices, clearing after a clean conversion and restored region diagnostics.
Ruff, JavaScript syntax and whitespace checks passed.

Local reports: ignored `outputs/nai-update-20261011/audit/full-regression.xml`,
`targeted.xml`, `browser/report.json`, `browser/firefox-*.txt`. The full suite
preceded only a retry-notice wording refinement and a defensive finite-margin
display check; the 22 targeted tests and six browser scenarios passed again
against those final changes. These are synthetic/local results; live NAI
account/encoding/generation requests remain zero for this increment.

## WD / EVA02 / PixAI acceptance

Compared final `wd_tagger.py`, `tagger_progress.py`, `pyproject.toml` and
`requirements.txt` at source pin `4de914676de8ca313b8389f4303754045a6a9cfb`:
the installed node files have identical Git blob hashes. App changes retain
GPL-3.0-only notices, and the exact model/code pins are in `REFERENCES.md`.

| Requirement | Implemented behavior / evidence |
|---|---|
| Model selection and compatibility | `nai_detailer.wd_model`, three model names; missing legacy field defaults to WD ViT. API validation, setup UI, queue, presets, history and PNG import/export retain selection. Region audit contains actual repo/revision. |
| Dependencies and preflight | Separate `wd-matching` / `pixai-matching` extras, callable dependency checks, Hub progress capability, Transformers 5 for PixAI. Load selected cache before base NAI request and reuse that model for matching. Missing/incompatible/cache-invalid models fail before transport. |
| Integrity and preprocessing | Fixed Hub snapshots, verified PixAI custom-code SHA-256 and class mappings, vocabulary/model dimensions checked. WD white square/BGR; PixAI pinned RGB processor/black pad. Full general/character scores, no rating/artist/style category substitution. |
| Cache and memory | Cache separated by repository/revision, no shared global model. Generation cache reads are offline; explicit preparation allows public Hub downloads with no implicit token. CPU load, auto/CPU inference, CPU return after success/error/cancellation. |
| Preparation and progress | Background local setup API, shared generation lock, per-file HTTP/Xet byte/percent reporting, stage messages, cancellable preparation, sanitized failures and retry. Cancelled work never reports ready. Browser disables conflicting controls. |
| Matching semantics | Preserve original character prompts and match/retry diagnostics. Loaded model reused between base preflight and detailer. Native app planner selected original slots 2 then 1 on the original node fixture with all three models. |

Evidence: **948 passed / one Windows-only launcher skipped** in the full suite
(71.98 seconds); bundled Node was on PATH. `tests/test_novelai_tagger.py` has
**37 passing cases** covering selection, dependencies, pins, invalid assets,
HTTP/Xet progress, cancellation, preflight, queue, manifest/PNG and setup APIs.
`scripts/browser_nai_tagger_smoke.py` passes **nine scenarios**, zero page errors,
no real downloads or NAI calls. Dedicated Firefox restored PixAI settings from
history and exercised cache-ready preparation on the same synthetic server.
Ruff, JavaScript syntax and diff whitespace checks pass.

`scripts/native_nai_tagger_smoke.py` used the existing ComfyUI Python environment
and pinned caches for real **CPU inference of all three models**. Source image:
the node's workflow example; two supplied face boxes, not live detection.
Two original character slots were correctly selected for each model; all
input/model file hashes were unchanged. HTTP was blocked, no attempts occurred.
Runtime: torch 2.14.0+cu130, timm 1.0.29, Hub 1.30.0, Transformers 5.16.1.
This is narrow fixture evidence, not calibrated identification or broad accuracy.
App venv optional installation, GPU, real new-download transfer, live NAI
acceptance/quality/billing remain unverified. Browser download/score/detector
results are synthetic; native model inference is separately recorded.

Ignored local evidence: `outputs/nai-update-20261011/tagger/targeted.xml`,
`full-regression.xml`, `native/report.json`, `browser/report.json` and
`browser/firefox-restored.txt`, `browser/firefox-ready.txt`. They are not public attachments. Next: row 4,
22 characters and model-specific limits. No final archive update or push yet.

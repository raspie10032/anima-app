# Remaining NAI ports: candidate acceptance

This records the requested 0.5.0 source-candidate implementation and local verification scope. It is not live NovelAI or billing acceptance. Original ComfyUI graph interfaces are expressed through managed app inputs, native detectors, browser controls and the common queue. The reference is the integrated RS_NAI implementation (`generators.py`, `references.py`, `detailer.py`, `detailer_matching.py`, `wd_tagger.py`).

| Requirement | Implemented behavior | Regression evidence | Browser/native evidence |
|---|---|---|---|
| Img2Img | Managed image, resize/EXIF/alpha handling, strength/noise including zero, model and metadata settings, explicit paid-mode gate | `tests/test_novelai_img2img.py` | Final remaining-port browser upload/request/history restore |
| Vibe Transfer | Up to 16 cards; V3 raw padded input; V4/V4.5 encoding; image/model/information cache keys; corruption rejection; normalization and incompatibility checks | `tests/test_novelai_references.py` | Final browser encoding once, repeated cache use, normalization and restore |
| Precise Reference | V4.5 type/strength/fidelity, aspect-matched black letterboxing and director parameters; mutual exclusion with Vibe | `tests/test_novelai_references.py` | Final browser type/fidelity/restore and incompatible combination rejection |
| Automatic detailer | After-generation and standalone modes; first/all; face/eyes/hands via YOLO/SAM B or SAM3; grouped eyes; frozen source and disjoint masks; preview/cancellation | `tests/test_novelai_detailer.py`, `test_novelai_sam3.py`, `test_novelai_hands.py` | Final browser sequential detail; focused/SAM3/hands browser cases; separate offline CPU native reports |
| WD character matching | Original weighted prompt/name/franchise/negative preserved; shared traits excluded; uncertain match retries tight context, then skips; observations do not become prompt text | `tests/test_novelai_detailer.py` | Final browser two-character matching and restore; real CPU WD inference; matching-quality coverage remains synthetic |
| Focused Inpainting | Dedicated infill model routing; strict internal crop exception; per-crop Opus/account/steps/dimensions check; exact black-mask pixel preservation; durable raw crop/composite/mask pair; partial failure stops queue | `tests/test_novelai_focused.py`, `test_novelai_detailer.py`, `test_novelai_eligibility.py` | Final browser focused/restore/timeout and history; seven focused browser cases including checkpoint failure/cancellation |
| Shared persistence and queue | Canonical requests, presets, history, PNG/manifest metadata, OpenAPI; fixed base seed per queue including Infinity refresh/stop | `tests/test_novelai_integration.py`, `test_server.py`, `test_novelai_metadata.py`, `test_queue_seeds.py` | Provider/inpaint/metadata acceptance; six queue-seed browser cases |
| Model identity and earlier node functions | Generation/infill identities remain distinct, unknown hash requires explicit choice; characters and six prompt conversions retained | `tests/test_novelai_metadata.py`, `test_novelai_characters.py` | Existing-image metadata import plus provider browser character/converter acceptance |
| Package and handoff | All ported modules/static GUI/docs included, isolated wheel import and CLI dry-run, source ZIP extraction/vendor/CLI checks, exact content/reproducibility audit | `tests/test_release.py`; `scripts/package_dry_run.py`, `source_archive.py`, `audit_nai_port_release.py` | Final local artifact audit and development handoff |

## Evidence locations

Development-only evidence under `outputs/all-nai-port-20261009` is excluded from the source ZIP:

- `final-package/full-regression.xml`: 858 passed, one Windows-only launcher skipped.
- `final-package/browser/report.json`: nine acceptance categories with synthetic remote transports/detectors; zero page errors and zero live requests.
- `focused/browser/report.json`, `sam3/browser/report.json`, `hands/browser/report.json`: seven, eight and eight cases respectively.
- `native/report.json`: real offline CPU YOLO face/eye, SAM B and WD inference on a preserved original NAI image.
- `sam3/native/report.json`, `hands/native/report.json`: real offline CPU SAM3 and five hand-YOLO/SAM combinations on its detector-preview derivative. SAM `.pt`/`.pth` files share a checkpoint hash.
- `queue-seed-fix/browser/report.json`: six tokenless queue cases and 22 stored seed manifests.
- `provider-regression`, `inpaint-regression`, `metadata-regression`: prior UI evidence; the final full suite covers their source contracts.
- `final-package/report.json`: archive/worktree byte equality, repeated deterministic ZIP hash, current original/model hashes, source/evidence hashes and isolated wheel smoke.
- `HANDOFF.md`: current Git state, commands, boundaries and next independent work.

The final local candidate is `outputs/release/all-nai-port-final-20261009/anima-app-0.5.0-source.zip`, accompanied by a SHA-256 file. It packages the dirty working tree, not a clean committed public release. Older archives remain available.

## Verification limits

No new live NovelAI generation, account or Vibe encoding request is authorized by this local acceptance pass. One earlier V5 Curated T2I request is recorded separately; it does not validate the new image/reference/infill ports or billing. New-port endpoint acceptance, correction quality and Anlas changes remain unverified.

Native checks used existing ComfyUI or isolated temporary CPU runtimes. App-environment optional dependencies, model weights, wide-image detection accuracy, GPU execution and Windows GUI were not validated by these checks. Optional extras and setup are documented in `NOVELAI_PROVIDER.md`; weights and tokens are excluded from distribution.

No merge, commit, push, tag, public upload, resident restart or automatic generation is part of this candidate handoff.

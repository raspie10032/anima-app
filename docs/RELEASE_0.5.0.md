# Anima APP v0.5.0 source-checkout beta and 2.4.6 update candidate

> Current main source includes the [2026-10-14 workspace, workflow, locale and documentation update](MAIN_UPDATE_2026-10-14.md). Version remains 0.5.0. Dated acceptance and artifact entries below describe their original validation snapshots, not a new published binary.


The original 0.5.0 integration was published at app commit `b3635050980518242923eb486847b7bfe90b744a`. The subsequent local candidate adds RS NAI 2.4.6 features at source commit `4de914676de8ca313b8389f4303754045a6a9cfb` without changing the app version. The current candidate has not been published. It adds Medium Effort, conversion/region diagnostics, three native taggers with explicit preparation, 22 saved character slots with model-specific limits, Korean/Japanese guidance, and 52 cause-specific errors. See [the incremental acceptance and package record](NAI_NODE_UPDATE_2.4.6.md). The source's later 2.5.0 inset/asset feature is outside this pin.

## Behavior

- Select local Anima or optional NovelAI T2I in the same browser GUI.
- Discover NovelAI model/sampler/scheduler capabilities from `/api/providers`; `/api/nai/status` reports server environment token presence only.
- Submit either provider through the common bounded queue, restore an active job after browser refresh, and save provider-aware presets.
- Reject local LoRAs, image inputs and enhancement options for NovelAI T2I; show effective Opus-capped dimensions and steps before submission.
- Port the ComfyUI node's strict Opus preflight: active tier 3, plus verifiable V5 remaining allowance >=2 percent, before every protected generation attempt including the 429 retry. Failed checks stop before submission; only safe summary fields enter manifests.
- Serialize account preflight and generation across provider instances in this Python process and wait at least two seconds after the preceding transport completes, including failures and paid requests. Pending waits remain cancellable.
- Preserve original remote PNG bytes with atomic output/manifest publication, requested/effective settings, response hash and retry count.
- Report sanitized remote failures and unknown outcomes. A timeout or lost response never triggers automatic resubmission; HTTP 429 has one bounded retry.
- Stop future remote scheduling without invoking local GPU interrupts. A submitted remote request may still complete and be billed; a result that arrives after Stop remains in history.
- Publish local/NovelAI request schemas in the OpenAPI contract.
- Import generation metadata from PNG/WebP while preserving the original model identity and operation; clear unavailable original input/mask references.
- Upload or paint an inpaint mask, use a dedicated infill model, require explicit removal of the cost cap, and preserve unmasked source pixels in the composited output. Keep the exact remote response as a separate variant.

## Verification boundary

The current candidate keeps up to 22 saved character prompts/negative prompts with normalized coordinates and order flags across generation, infill, presets, queue requests, wildcard provenance, manifests and PNG/WebP metadata import. V5 permits 22 active characters; V4/V4.5 and V5 Curated's V4.5 infill fallback permit six; V3 does not support separate character prompts. Hiding/disabling preserves editor values; collapse does not disable a character. Six local ComfyUI/NAI V4/old NAI weight conversions use explicit preview/apply, with warnings for approximations and node-specific fallback behavior. Tests and mock browser acceptance cover these paths; live multi-character generation remains unverified.

The implementation is tested using deterministic synthetic transport, temporary local model fixtures and a mock local renderer. Optional `scripts/browser_provider_smoke.py` exercises Chromium provider switching, preset restoration, queue recovery after refresh, remote cancellation, result retention, zero seed/CFG restoration and local operation without a NovelAI token. It also checks that V5 allowance 1 percent is blocked before generation and 2 percent permits the mocked request under the shared lock. External subscription and generation transports are disabled.

The earlier 2026-10-09 Firefox/queue acceptance records one live V5 Curated T2I request in `outputs/nai-live-20261009/report.json`. The subsequent infill extension is verified only with synthetic transport (`scripts/browser_inpaint_smoke.py`), including source/mask upload, painting, explicit cost-cap removal, queue reload recovery and manifest restoration. This does not establish live infill endpoint acceptance, account billing safety, real GPU inference or Windows browser acceptance.

## Scope and distribution

NovelAI now supports T2I, Img2Img, ordinary/focused masked infill, Vibe Transfer, Precise Reference and sequential automatic detailing with optional native WD matching. Requests, presets, history and manifests retain provider settings. Vibe/Precise compatibility follows the integrated RS_NAI source. Strict protection permits only internally planned focused crops after input and subscription preflight; references, Img2Img and generic infill remain blocked. Completed base/crop results survive later detailer failure and subsequent batch jobs stop. Tokens remain environment-only.

The remaining ports have unit/queue/synthetic browser validation. Separate offline CPU checks exercised face/eye YOLO, SAM B and WD tagger inference on a preserved earlier NAI image. SAM3 face/eye/hand concepts, hand YOLO n/s and both SAM B `.pt` and `.pth` loaders were checked on its detector-preview derivative. The two SAM B files have the same checkpoint hash; these are two loader paths, not distinct weights. These limited-image checks do not establish broad detection accuracy, GPU execution or real-image character-matching quality; multi-character assignment coverage uses synthetic scores. No new live NovelAI requests, encoding fees or billing checks were performed. Windows browser acceptance also remains unverified. Optional detector/tagger dependencies and model assets are not bundled or installed in the app environment by this candidate. See `outputs/all-nai-port-20261009/HANDOFF.md` in the development checkout for exact artifacts and reproduction.

The source-checkout ZIP remains the supported artifact. The wheel verifies package/CLI/browser-static boundaries but does not contain the vendored generation runtime. Tagging, publishing, merging and paid live requests are separate from preparing this candidate.

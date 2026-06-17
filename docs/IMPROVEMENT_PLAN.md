# Anima APP Improvement Plan

## Goal

Raise Anima APP from source-checkout alpha toward a comfortable local release by improving the GUI workflow, generation feedback, output review, model/asset handling, and release readiness in small verified batches.

## Improvement Tracks

1. GUI workflow clarity
   - Keep the left panel ordered as prompt, starting point, image settings, LoRA, generate, and optional tools.
   - Keep advanced reference/upscale/face controls collapsed until needed.
   - Prefer clear action labels over internal terms.

2. Result review
   - Show a readable current-result summary before raw manifest JSON.
   - Keep preview/output links, manifest details, and history behavior visually distinct.
   - Add richer history/gallery controls after the summary panel is stable.

3. Progress and error feedback
   - Replace synchronous-only progress hints with exact backend polling or streaming.
   - Keep failed requests clearly labeled and keep stale preview/output links hidden.
   - Preserve dry-run and real-run evidence separately.

4. Quality controls
   - Keep standard and reference-quality presets visible.
   - Add focused quality presets only when they map to verified local settings.
   - Add face-detailer forehead/hairline exclusion controls after the mask behavior is designed and tested.

5. Runtime and release readiness
   - Keep required models copied or downloaded into project-local `models`.
   - Keep GPU 0 as the Anima generation device unless explicitly changed.
   - Finish source-checkout release docs first, then address wheel or standalone packaging.

## Latest Completed Batches

Batch 1 improves result review:

- Add a readable `Current Result` panel.
- Show status, size, steps/CFG, sampler, seed, upscale, face-detailer, and output summary.
- Keep raw manifest JSON in a collapsed section.
- Verify dry-run generation, desktop layout, mobile layout, and the hidden output-link state.

Batch 2 improves history review:

- Add `All`, `Images`, and `Dry-run` filters to the history panel.
- Show history entries as thumbnail-first gallery cards, with manifest placeholders for dry-run entries.
- Keep the history count visible and show an empty state when a filter has no matching entries.
- Verify filter behavior, manifest replay, desktop layout, mobile layout, and browser console health.

Batch 3 improves generation progress:

- Add a per-request `progress_id` contract to `POST /api/generate`.
- Add `GET /api/progress/<id>` backed by an in-memory server progress store.
- Update the GUI to poll backend progress instead of advancing stage rows on a client-only timer.
- Verify in-progress polling with a blocked fake renderer, dry-run API completion, GUI generation, and browser console health.

Batch 4 improves face-detailer control:

- Add `exclude_forehead_ratio` to face-detailer request settings.
- Add CLI/API/GUI controls for excluding the upper forehead/hairline portion of the repaint crop.
- Apply the exclusion to the crop mask before repaint and composite.
- Verify request parsing, dry-run manifest recording, runtime mask behavior, API dry-run output, GUI generation, and browser console health.

Batch 5 improves model readiness:

- Add `GET /api/readiness` for Anima base and face-detector profile status.
- Add `POST /api/models/prepare` to reuse the copy/download profile flow from the GUI.
- Add readiness cards with file-level status and prepare buttons to the GUI.
- Verify detector profile copy through HTTP, ready-state rendering in the browser, and browser console health.

Batch 6 improves repeated generation:

- Add a browser-side Auto Queue panel that reuses the existing `/api/generate` flow.
- Add queue count, seed mode, delay seconds, start, stop-after-current, and status controls.
- Keep per-job progress, result rendering, manifest opening, and history refresh on the existing generation path.
- Verify the HTML contract, full test suite, and a 2-job dry-run browser queue.

Batch 7 improves source-checkout release readiness:

- Add a release smoke script for static release files, health JSON, dry-run generation checks, and optional full pytest.
- Add a double-clickable Windows release-smoke launcher.
- Add a release checklist that separates source-checkout alpha readiness from unfinished wheel/standalone packaging.
- Verify the release smoke, targeted tests, and full test suite.

Batch 8 improves packaging readiness:

- Add a packaging dry-run script that builds and inspects a wheel under `outputs\package_dry_run`.
- Add a standalone layout plan that includes source/runtime/docs/launchers and excludes models, inputs, and outputs.
- Document the wheel versus standalone boundary in `docs\PACKAGING_PLAN.md`.
- Verify the package dry-run tests and actual package dry-run command.

Batch 9 improves history housekeeping:

- Add manifest/open/export/delete actions to history cards.
- Add `DELETE /api/manifests/<name>` to delete managed manifest/output pairs safely.
- Keep deletion constrained to `outputs\manifests` and `outputs\images`.
- Verify server deletion behavior and GUI contract tests.

Batch 10 improves settings portability:

- Add `GET /api/presets/export` for an `anima-app/presets.v1` saved-settings bundle.
- Add `POST /api/presets/import` to validate and save imported presets.
- Add GUI Export Settings and Import Settings controls.
- Verify export/import round-tripping between separate app roots.

Batch 11 improves checkpoint selection:

- Add `checkpoint` to `T2IRequest`, manifests, A1111-style PNG metadata, CLI, smoke script, API, presets, and GUI.
- Add local diffusion checkpoint inventory from `models\diffusion_models`.
- Keep checkpoint values constrained to relative `.safetensors` paths under the project-local model tree.
- Verify targeted request/runtime/API/GUI/metadata tests plus full release smoke.

## Next Batch Candidates

1. Materialize a real portable source archive or standalone binary from the packaging dry-run plan.
2. Add richer browser visual regression checks for the full GUI workflow.

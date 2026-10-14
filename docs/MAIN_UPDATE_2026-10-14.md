# Main update — 2026-10-14

This source update connects image-first retrieval, provider-specific prompt authoring, ordered Anima/NAI processing and an English/Korean/Japanese interface. The application version remains **0.5.0**; this document does not announce a new versioned release or a downloadable binary.

## What changes

- The generation workspace keeps prompt/settings, a large result, recent outputs and persistent generation actions together.
- Workflows support NAI → Anima and Anima → NAI detailing, plus up to six ordered post-processing stages with independent settings and preserved intermediate results.
- Low-memory profiles retain tiled VAE decoding without adding an unintended upscale pass to detail-only stages, including automatic selection on 8 GB GPUs or when VRAM cannot be detected.
- Prompt routing keeps original text and adapts weights and `artist:`/`@` notation per engine. Unprefixed names use exact local-catalog matches only.
- Image workspace retrieval leads from a reference image to similar cases, recorded artist combinations and reusable prompts/settings. Reference-based comparisons, undoable drafts, annotations and exact source-record links are stored locally.
- English, Korean and Japanese UI changes preserve ongoing work. Browser drafts and locale survive reloads at the same origin.
- Pinned RS NAI 2.4.6 additions include Medium Effort, expanded character-slot handling, optional tagger preparation and structured diagnostics. See [the pinned update reference](NAI_NODE_UPDATE_2.4.6.md).
- [Three language walkthroughs](../README.md#start-here), [NAI token setup](NAI_TOKEN_SETUP.md), and [the application reference](APP_REFERENCE.md) explain the complete generation process.

## Operational limits

- NAI tokens are server environment variables, with **no browser token-entry field**. A token change requires restarting the server.
- The library limit is 2,000 assets. The offline artist catalog, image corpus, models, query results and evaluation records are not included in the source distribution.
- VRS needs a separately prepared local encoder. It is image-neighbor retrieval and record linkage; it does not identify the actual artist or run a native VRS decision core.
- Feedback does not automatically train/reorder retrieval. Permanent multi-item work boards, standalone combination-card management and controlled combination experiment grids remain future work.
- Completed stages survive later failures, but there is no automatic crash recovery or paid-request replay. Presets do not embed required model/reference files.
- Translated UI does not rewrite prompts or raw technical diagnostics. Windows GUI and all optional GPU/tagger combinations require their own acceptance checks.

## Validation

The pre-merge suite passed **1,118 tests with one platform-specific skip** under Python 3.12. The integration pass reran **46 headless browser scenarios** covering generation, library, authoring and all three locales with synthetic data. Packaging checks verify static resources and the separation of source-checkout assets from the wheel. The merge retains upstream's CI action updates and extends JavaScript syntax checks to the new modules.

Remote CPU CI exposed an unintended upscale setting in detail-only stages that the development GPU's balanced profile did not exercise. After fixing that behavior and adding explicit low-memory regressions, the complete local suite passed **1,122 tests with one skip with CUDA disabled**. This is CPU/mocked workflow validation, not physical 8 GB GPU acceptance.

Earlier development included live examples of both provider directions; those limited runs do not establish universal model compatibility, current subscription eligibility or billing guarantees. This documentation/integration pass does not generate new paid images. Machine-specific live artifacts and private corpus evaluations stay outside Git. Remote CI results are reported against the final pushed commit rather than assumed from local checks.

## Source and design references

Use [REFERENCES](REFERENCES.md) for source pins, licenses and model files. SD Studio's scene/gallery and pairwise-comparison patterns informed the UI design review; this is not a claim of runtime parity or copied UI assets. The public [design benchmark](LIBRARY_BENCHMARK_2026-10-14_KO.md) records feature choices. Private analysis paths and user-generated images are excluded from published guides.

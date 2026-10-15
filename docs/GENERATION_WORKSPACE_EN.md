# Generation workspace and ordered processing

Use **App language** in the header to switch between English, Korean and Japanese. The preference is saved in this browser; prompts and generation settings are preserved. See [language settings and scope](LOCALES.md).

The main screen places prompts and controls on the left, the image in the center, and recent results on the right. Generate and stop actions stay in the bottom bar. Advanced controls fold away; recent results can be hidden. The image workspace remains accessible from the top navigation.

## Connect the engines

Open **작업 순서** (processing order). **NAI → Anima** configures NAI generation followed by local Anima detailing; **Anima → NAI** configures the reverse. Each shortcut replaces the downstream list with one detailer stage.

Add Anima detailing, NAI detailing, or Anima upscaling, then reorder downstream stages with the arrow buttons. The first generation/edit operation remains first. Up to six downstream stages are supported. Each stage owns its model, steps, strength, CFG, detector/mask backend, crop scale and padding. Disable prompt inheritance to supply separate positive and negative prompts. Presets and history restore the plan. Existing inline post-processing remains part of the first operation when enabled; the first-stage label indicates this.

Example: `NAI generation → Anima upscale → Anima detail → NAI detail`. Each completed image supplies the next stage's input. **생성만** clears the downstream list.

## Requirements and outputs

Anima detailing requires the diffusion checkpoint, Qwen text encoder and VAE as well as detector/mask models. Install `python -m pip install -e '.[face-detailer]'` and prepare models under the project's `models` directory. NAI stages require `NAI_ACCESS_TOKEN` in the server environment; never put credentials in saved plans. See the [installation guide](USER_GUIDE_KO.md) and [NovelAI documentation](NOVELAI_PROVIDER.md).

The Opus protection setting defaults to enabled for NAI stages. If a face crop covers the entire source, reduce crop scale/padding. Appropriate values depend on the target region and image. Passing the request guard does not independently establish billed usage.

Intermediate images and manifests remain available for stage comparison. `outputs/workflows/<id>.json` stores execution state and input/output hashes; the final manifest also records the original request and plan. A downstream failure returns the last successful image and stops the rest. Dry-run validates the plan without calling image generation. The journal does not provide automatic restart recovery, and failed remote requests are not automatically retried.

## Walkthrough and validation

The [detailed generation walkthrough](IMAGE_GENERATION_EN.md) covers installation, a first image, both detailer directions and output comparison. **In v0.6.1 enter NAI credentials in Connect & prepare; [token setup](NAI_TOKEN_SETUP.md) also covers the optional terminal method.** See [release notes](RELEASE_0.6.1.md) for current validation and limits.

## Authoring, provider adaptation and case references

The prompt format control defaults to automatic detection. NAI V4/V5 stages receive `0.85::artist:name ::`; Anima receives `(@name:0.85)`. Group weights, order and escaped parentheses are retained while the editor preserves the original text. NAI V3 uses approximate legacy brace weights with warnings. Ambiguous unweighted parentheses are not reinterpreted automatically. Select an explicit source syntax or disable conversion when needed. Mixed weight syntax or a conversion that would drop/replace tags is rejected visibly.

**단계별 전달 미리보기** previews all stages, positive/negative prompts, NAI character slots, recognized bare artists and warnings without generating. Execution expands wildcards before conversion; preview does not predict wildcard choices. Static preflight validates the plan before the first generation; each expanded stage is validated again at execution time.

Only complete tags lacking `artist:` and `@` are checked against the local Danbooru artist catalog. Matching normalizes spaces/underscores, case and escaped parentheses. It does not infer sentence fragments, partial names, aliases or fuzzy matches. Explicit artist prefixes remain valid without a catalog entry. The default update requests **up to 20,000 active artist tags ordered by post count, not every artist**. Preview shows its count, collection date and partial coverage. No generation-time artist lookup is made. A missing or invalid snapshot disables bare-name inference while explicit-prefix conversion still works.

The ignored local file is `outputs/artist-catalog/danbooru.json`. Update it explicitly from the project environment:

```bash
PYTHONPATH=src .venv/bin/python scripts/update_artist_catalog.py --pages 20 --interval 2
```

Validation and atomic replacement preserve the old catalog on errors; rate limits are not retried. The updater downloads tag data, not images or account information.

The browser automatically saves the generation form, workflow and imported source references at the same origin. Reload restores them without submitting generation. **저장된 작업 불러오기 / 저장 초안 삭제** manage that draft. Uploaded image bytes are not stored in the browser; their managed server paths must remain available. Wait for uploads to finish, then edit the form and check the saved status. Library compose drafts and recent import undo history persist independently. Clearing browser storage, private-session shutdown or using another origin may prevent restoration.

Imported asset IDs, exact generation-record IDs and import scope follow presets, workflows and output manifests. Open the source from the editor/result, or detach it from a draft. Multi-record images open the exact imported record; missing sources are reported. `authoring_request` retains editable input, `prompt_processing` records conversion and catalog provenance, and top-level `prompt` is the effective provider text. Source references are not authorship attribution or automatic learning.

API calls retain native text when `prompt_routing` is omitted. Opt in using `{"prompt_routing":{"source":"auto"}}`; `POST /api/prompts/plan` accepts generation-shaped requests for preview. Presets and history restore the authoring request and original workflow when available.

Additional acceptance: 1,112 full-suite tests passed, one skipped; 10 generation, 20 library and eight authoring browser scenarios. Two- and three-stage bidirectional provider handoffs validate adapted prompts and provenance using mock providers. This change has not repeated live NAI/GPU generation. Headless Chromium was closed after testing; local artifacts are under ignored `outputs/usability-linkage-20261014/`.

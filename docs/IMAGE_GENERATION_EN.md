# Image generation walkthrough — English

[README](../README.md) · [한국어](IMAGE_GENERATION_KO.md) · [日本語](IMAGE_GENERATION_JA.md) · [Technical reference](APP_REFERENCE.md)

Choose **App language → English** at the top. Switching language preserves prompts and settings. This walkthrough follows the current application from a first image to ordered detailing and reuse.

## 1. Prepare your generation route

| Route | Requirements |
|---|---|
| NovelAI generation | Network access and a usable NovelAI account/token; no Anima weights needed |
| Local Anima generation | Anima checkpoint, shared Qwen text encoder, VAE and a compatible GPU runtime |
| Either engine followed by the other engine's detailer | Both requirements above, plus local detector weights and detailer dependencies |

NAI runs remotely. Local Anima checkpoints and LoRAs are not uploaded as NAI models. NAI detailing still uses local region detection.

Use Python 3.10+ in a complete source checkout or extracted source-checkout archive. The wheel does not include the root-level local runtime. Install PyTorch appropriate for your GPU environment.

Linux / Bash, from the project root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
```

Windows PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .
```

In v0.6.1 open **Connect & prepare → Generate with NAI → NAI access token → Apply token**. No restart is needed; the token stays only in volatile memory on the PC running the app until exit; select **Save on this PC** to restore it at the next launch. [Terminal token setup](NAI_TOKEN_SETUP.md) is also available. Prepare local models and the image encoder in the same dialog. [Setup walkthrough](../SETUP.md).

Start the application:

```bash
python -m anima_app.cli serve --host 127.0.0.1 --port 8768 --open
```

Use the same address/port on later visits to recover browser drafts. `--port 0` chooses a free port but may change the browser storage origin. Check for an existing server if a fixed port is occupied. Stop the server with Ctrl+C after its active work finishes.

For local Anima and detailing, prepare the required assets in the same Python environment:

```bash
python -m anima_app.cli models copy-profile anima-t2i --source download
python -m anima_app.cli models copy-profile anima-aesthetic-v1.1 --source download
python -m pip install -e '.[face-detailer]'
python -m anima_app.cli models copy-profile face-detailer-detectors --source download
python -m anima_app.cli health --json
```

The Aesthetic checkpoint is optional. The base profile includes shared text encoder/VAE files. Detector preparation and optional dependencies are needed for detailing. These commands explicitly download assets; [the model reference](REFERENCES.md) also explains local mirrors. A checkpoint alone cannot run Anima without its encoder and VAE.

## 2. Find the controls

| Area | Purpose |
|---|---|
| Header | Generation/image workspace, language, hide/show recent results |
| Left | Engine, prompt, size, workflow, model/character/style, references and post-processing |
| Center | Result image, enlargement, stage comparison, conditions and source cases |
| Right | Recent outputs and restoring settings |
| Fixed bottom bar | Generate, Stop, continuous-generation controls and progress |

Expand folded panels for model options and presets. On narrow screens the areas stack vertically.

## 3. Generate one NAI image

1. Choose **NovelAI** in the generation-engine selector. Check the status underneath. `/api/nai/status` reports configuration, not whether the token is valid.
2. In the workflow panel choose generation only. This clears added stages; also check that the older reference/post-processing controls do not enable an inline detailer.
3. Open model/character/style settings and choose **T2I**, **V4.5 Full** for this example.
4. Enter a simple prompt without references, wildcards or character slots for the first run:

```text
1girl, adult woman, short brown hair, brown eyes, hairclip,
white blouse, portrait, garden, soft daylight, detailed eyes
```

Negative prompt:

```text
blurry, low quality, extra fingers, text, watermark
```

5. Start with **768×1024, 28 steps, CFG 6, Euler Ancestral, seed 12345, one image**. These are comparison settings for this example. Medium Effort applies its own fixed conditions, including 14 steps; follow the effective settings shown in the UI.
6. Keep the default Opus protection and inspect eligibility. Unsupported operations or account conditions may be blocked. References and Img2Img require explicitly disabling protection and may cost Anlas. Passing local checks is not billing verification.
7. Open the stage prompt preview and inspect positive/negative prompts. Preview does not generate an image.
8. Click **Generate** once. Watch queued/running/completed states and inspect the center image. Stopping cannot undo a remote request already processed.
9. Select the output in recent results and check its recorded model, seed and prompt. For a useful comparison, keep the seed and change one setting at a time. Matching seeds across models/versions do not guarantee matching images.

## 4. Generate one Anima image

1. Choose local Anima, then a ready checkpoint in the model panel.
2. Confirm the selected checkpoint, text encoder and VAE are ready. Aesthetic v1.1 can be selected when installed.
3. Use the same scene prompt with the app defaults: **832×1216, 20 steps, CFG 3.5, euler_ancestral_cfg_pp, sgm_uniform**.
4. Begin with no extra stages or inline upscaling/detailing. Generate one image and inspect it before adding more processing.
5. If memory is insufficient, reduce resolution/post-processing or adjust the VRAM profile. Initial model loading and subsequent runs can take different amounts of time.

## 5. Preview artist and weight conversion

With automatic input-syntax detection, `(artist:example_artist:0.9)` becomes `0.9::artist:example_artist ::` for NAI V4/V5 and `(@example_artist:0.9)` for Anima. The name is a placeholder. Your original text stays in the editor.

- Explicit `artist:` or `@` names are recognized without a catalog.
- An unprefixed name is recognized only when its **whole tag** exactly matches a local artist catalog after normalization. Unknown names and fragments are not guessed.
- Group weights, artist order and escaped parentheses are retained. Select the input syntax manually when automatic detection is ambiguous; check warnings for V3 approximation.
- The catalog is not bundled. Optionally prepare a partial active-tag snapshot with `python scripts/update_artist_catalog.py --pages 20 --interval 2`. Generation itself does not query artist names online.
- Preview wildcard expansion separately. Execution expands wildcards before conversion, so a prompt-plan preview is not a guarantee of a particular random expansion.

## 6. NAI → Anima detailer

1. Prepare both engines and local detector dependencies.
2. Open the workflow panel and click **NAI → Anima**. This selects NAI as the base engine and replaces the added-stage list with one Anima detailer.
3. Configure the base NAI image as above.
4. Open the second stage's settings, select an Anima checkpoint, and try **10 detail steps / 0.28 denoise** as a starting point. Lower denoise generally keeps more of the source; the actual effect depends on the model and crop.
5. Keep inheritance of the first prompt, or disable it to enter a stage-specific positive and negative prompt.
6. Check detector, crop scale and padding. Preview both prompts: NAI should receive `artist:` syntax and Anima `@` syntax.
7. Generate. The saved NAI output becomes the Anima stage's input. Use stage comparison to inspect the original and detail result: facial identity, eyes, expression and accessories can change.

## 7. Anima → NAI detailer and longer workflows

1. Click **Anima → NAI** and configure the base Anima checkpoint and scene.
2. In the second stage select its NAI model, steps, strength and CFG. Reduce strength if the repaint changes too much.
3. Check the stage's Opus protection and crop. A full-image crop or disallowed conditions may be rejected. Fit the crop/padding to the region; understand cost implications before disabling protection.
4. Generate and compare the Anima original with the NAI detail result. The NAI stage sends the selected image region to the remote service.

Add Anima upscale/detail or NAI detail stages with the stage selector and move them using ↑/↓. Up to **six post-processing stages** follow the first generation/edit. Upscale before detailing and upscale after detailing are different experiments. Quick direction buttons replace the added list; generation only clears that list, while inline controls remain separately visible in the first-stage summary.

## 8. Save, compare and reuse

The current development version reads RS NAI 2.9.0 PNG/WebP files and separates original generation settings from region edit history. Open **Import generation settings from image** and choose the **Fields to apply**. Uncheck size and seed to keep their current values while importing prompts and character positions. Detailer files without original context cannot overwrite the full-image prompt with crop settings.

In a NAI workflow step, **Use first-step prompts and characters** passes characters and coordinates across intermediate Anima stages. **Inherit from the first NAI step** selects model/sampling settings individually. NAI settings also provide detector selection, PNG/WebP output and response timeout. See [scope and verification](NAI_NODE_UPDATE_2.9.0.md). These changes follow the published v0.6.1 release.

- Images and intermediate outputs: `outputs/images`. Generation records: `outputs/manifests`. Ordered-workflow journals: `outputs/workflows`.
- Save a named preset to retain settings and stage order. Restoring a history item prefers the saved authoring text and workflow.
- Drafts restore in the same browser and origin. They do not start generation. Presets do not contain model weights or reference image files; keep the referenced files available.
- Open **Image workspace**, import a local folder or sync app history, and drop a reference image. There is **no total image-count limit**; files are imported incrementally and the library is browsed in pages.
- Choose a retrieved case, inspect its recorded artist combination and prompt, and compare candidates against the reference. The query does not need prompt metadata.
- Reuse artist tags, prompts, or conditions into the editable draft. Apply it to the generation screen, review the engine/protection/stages, then generate explicitly.
- The result retains the exact source-case record and reuse scope. A reference button returns to it. Similarity does not establish the image's actual artist.
- Basic CPU retrieval is available immediately; [VRS requires separate local encoder configuration](IMAGE_LIBRARY_EN.md). Saved comparison feedback does not yet train the ranking model.

## 9. Troubleshoot

| Symptom | What to check |
|---|---|
| NAI Generate disabled | Correct server, token status, completed uploads, valid fields |
| Token changed but authentication fails | Restart from the terminal with the new environment; check whether another app regenerated the token |
| Protection error | Account eligibility, operation, references, dimensions and steps |
| Anima not ready | Selected checkpoint + encoder + VAE; detector assets/dependencies for detailing |
| No face repaint | Whether the detector found the target; inspect detection/mask preview |
| Later stage failed | Completed outputs remain; inspect stage errors before retrying. No automatic crash recovery or replay of failed paid requests |
| No VRS results | Imported sources still exist, indexing completed and encoder environment available; compare with CPU search |
| Draft disappeared | Same browser profile, origin and port; storage not cleared |

See [provider details](NOVELAI_PROVIDER.md), [API and storage reference](APP_REFERENCE.md), and [implementation/verification limits](MAIN_UPDATE_2026-10-14.md).

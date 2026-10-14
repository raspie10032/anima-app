# Image-first case library

The image workspace header includes **App language** for English, Korean and Japanese. Switching preserves selected examples, comparison candidates, edited drafts and original records. See [language settings](LOCALES.md).

Start with pixels, retrieve similar examples, inspect their **recorded** artist combinations, and reuse their prompts or generation settings. Query images need no embedded prompt. Single-artist prompts are valid combinations.

Open **Image workspace** in the app. Expand **검색 방식 · 라이브러리 관리**, enter absolute folder paths (one per line), and import PNG/JPEG/WebP recursively. **앱 생성 이력 연결** joins existing app manifests. The total library capacity is 2,000 files. App history is also periodically synchronized while the library is being used.

Drop a query image into the library, choose a result, and inspect its saved records. Artist buttons show examples with the same ordered, weighted artist tags and model context. The reuse actions stage artist tags, positive/negative prompts, or the saved request in the **03 프롬프트** draft. Edit the draft and use **생성 화면에 적용** to transfer it through the existing preset path. They do not start generation. Prompt-only reuse preserves the current provider/model; complete reuse preserves current Opus protection. Missing references, models, and settings still require review before generation.

Favorites, tags, collection names, notes, and text search are supported. Visual similarity and willingness to reuse the conditions are separate feedback fields. Feedback is saved locally; it does not yet train a model or change rankings.

## Optional VRS-INT encoder

The default CPU search compares fixed color, layout, and edge features. VRS search uses the existing VRS-INT Gemma 4 image encoder. Configure the app before launch:

```bash
cd /path/to/anima-app
export ANIMA_LIBRARY_VRS_ROOT='/path/to/RS-Seasonal-Prompt-Generator'
export ANIMA_LIBRARY_VRS_ENCODER='/path/to/local-gemma4-encoder'
export ANIMA_LIBRARY_VRS_PYTHON='/path/to/compatible-environment/bin/python'
PYTHONPATH=src .venv/bin/python -m anima_app.cli serve --host 127.0.0.1 --port 8768
```

Use an environment capable of running `vrs_int.encoder`, with its dependencies and local model files already installed. No model download is attempted. Click **VRS 색인 준비** to build the index; completed vectors survive cancellation and can be reused. VRS becomes the default search mode when every asset is indexed, unless the user explicitly chooses another mode. Cached case queries reuse their vectors; uploaded images incur additional model-loading and encoding time. Encoding takes the app's generation lock; independent ComfyUI processes are not controlled.

The adapter passes freshly decoded RGB PNGs without original metadata to the encoder. Ranking never uses artist tags, prompt text, or filenames. Records are joined after image ranking. Native VRS decision-core integration and adaptive preference learning are future work.

Index versioning includes encoder source, model provenance, preprocessing, and worker code hashes. It does not hash all weight files on each request: changing weights requires updating their provenance and preparing a new index.

## Data and provenance

The SQLite database is `outputs/library/library.sqlite3`; thumbnails are in `outputs/library/thumbnails`. Original images are referenced and never overwritten. Byte-identical files share an asset while distinct records are preserved. Identical decoded pixels are excluded both against the query and within a result set.

Explicit `artist:` tags are extracted with their order and weighting. Unknown/bare artist names are not inferred from images. Full prompts and source settings are retained separately. Combination statistics distinguish artist sequences from model-specific combinations. Standard NovelAI embedded metadata and Anima manifests are supported; A1111 metadata retains its original settings and allows prompt reuse. Arbitrary ComfyUI workflow interpretation is not implemented.

For downloaded cases, put `{"post":"https://example.org/post/123"}` in a sibling `source.json` before import. The app retains a validated HTTP(S) source link. It does not store login cookies. Private images, prompts, vectors, queries, and evaluations belong under the Git-ignored `outputs` directory. Use the server with trusted local users; folder import and metadata inspection are privileged local operations.

## Verification and retrieval quality

Synthetic checks validate upload, duplicate exclusion, record linkage, selective reuse, comparisons and undo. They do not measure style-retrieval accuracy. Evaluate quality separately with held-out queries, duplicate/derivative exclusion and source-post separation. Distinguish scene, pose and hair-color similarity from rendering style.

See [integration validation](MAIN_UPDATE_2026-10-14.md). Private images, prompts, per-case retrieval results, collection statistics and personal evaluation reports are not distributed.

## Integrated image workspace, 2026-10-14

The prototype is now connected to the real library. The entry opens a full-screen workspace with a persistent reference on the left, a large gallery in the center, and saved records on the right.

- **01 탐색**: uncropped images, adjustable card size, text/favorite filters, 48-item pagination, and abbreviated artist labels with full details in the inspector. Explore a retrieved combination and use **유사사례로 돌아가기** to return to the original result set.
- **02 비교**: compare adjacent-ranked pairs or two manually selected results from the same query. Choose A, B, both similar, neither similar, or defer; undo the latest judgment. Relative visual judgments are stored separately from absolute visual/reuse feedback.
- **03 프롬프트**: import artist tags, prompt only, or complete conditions into an editable draft before applying to generation. Undo restores the pre-import draft, including manual edits. The draft and ten recent import undo entries persist across reloads in the same browser and app origin. Clearing browser storage or closing a private session may remove them. Prompt-only import clears any previously staged conditions.
- Appending artist tags normalizes both drafts to compatible weight syntax before combining them. Final provider adaptation follows the [generation workspace settings](GENERATION_WORKSPACE_EN.md). Imported asset IDs, exact record IDs and import scope follow generation manifests and can be opened from the result. These are source references, not artist attribution or automatic model training.
- The inspector retains source records, artist order/weight, model/seed, original conditions, provenance, favorites, and annotations. Image enlargement uses a metadata-free JPEG up to 1,600px; missing or changed originals fall back to labeled stored thumbnails.
- The footer shows status and generation progress. Narrow layouts keep the reference at the top and put details after the gallery. Desktop arrow keys navigate cases outside editing controls.

Comparison rows persist in the new SQLite `comparisons` table (query, A/B assets, choice, timestamp, undone flag). Undo retains the original row. The browser's comparison cursor and undo stack last only for the current query session. Existing images, vectors, queries, and feedback remain intact. Generated results link the exact source case record and reuse scope. Adaptive VRS reranking, persistent project boards and a dedicated full-lineage browser are not included.

Headless Chromium checks use temporary synthetic data and close their browsers after completion. They exercise UI and storage without live NAI generation. See [reproduction commands](APP_REFERENCE.md#verification-and-publication-boundary).

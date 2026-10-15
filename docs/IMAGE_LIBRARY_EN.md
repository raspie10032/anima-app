# Image-first case library

The image workspace header includes **App language** for English, Korean and Japanese. Switching preserves selected examples, comparison candidates, edited drafts and original records. See [language settings](LOCALES.md).

Start with pixels, retrieve similar examples, inspect their **recorded** artist combinations, and reuse their prompts or generation settings. Query images need no embedded prompt. Single-artist prompts are valid combinations.

Open **Image workspace** in the app. Expand **검색 방식 · 라이브러리 관리**, enter absolute folder paths (one per line), and import PNG/JPEG/WebP recursively. **There is no library item-count limit.** Files are imported incrementally and listings are fetched by page. **앱 생성 이력 연결** joins existing app manifests. App history is also periodically synchronized while the library is being used.

Drop a query image into the library, choose a result, and inspect its saved records. Artist buttons show examples with the same ordered, weighted artist tags and model context. The reuse actions stage artist tags, positive/negative prompts, or the saved request in the **03 프롬프트** draft. Edit the draft and use **생성 화면에 적용** to transfer it through the existing preset path. They do not start generation. Prompt-only reuse preserves the current provider/model; complete reuse preserves current Opus protection. Missing references, models, and settings still require review before generation.

Favorites, tags, collection names, notes, and text search are supported. Visual similarity and willingness to reuse the conditions are separate feedback fields. Choose **Search reference again** to apply similarity ratings and A/B preferences to the same pixel reference and encoder. **Reset similarity rating** clears that candidate's absolute rating. Repeated judgments do not accumulate; reuse ratings do not change visual ordering. The original cosine score and SWEGCA decision thresholds stay unchanged.

**Most similar** is the default order. **Mix diverse cases** spreads nearby candidates using their image vectors; select it and search the reference again. It never uses artist tags or prompts to rank images. Equal/skip comparisons express no relative preference. Undo removes the latest comparison's effect when searching again.

Consecutive external searches reuse the encoder for up to 60 idle seconds. Another app GPU task releases the idle encoder before starting. Corpus matrices are cached in the execution PC's memory and invalidated on corpus/vector changes. The first external search after startup or encoder release includes model startup time.

## Embedded VRS image search

Open **Connect & prepare → Find similar images → Prepare image encoder**. The app bundles the encoder code and downloads about 320 MiB of pinned vision weights plus missing runtime dependencies to `models/vrs/gemma4-vision`. CUDA is required for this encoder; basic CPU similarity remains available without it. No sibling repository, external Python executable or `ANIMA_LIBRARY_VRS_*` variable is needed.

After importing a folder, choose **Index imported images**. Batches of eight are saved independently; cancel and resume without losing completed batches. Search works over the prepared subset while other images remain pending. **Check file issues** identifies missing originals, unreadable images and encoder failures. Restore missing originals and retry; one missing file does not stop other images.

Captioning is not required. Pixel decoding and metadata cleanup are separate. Malformed generation fields and JSON retain recoverable prompts with warnings and never turn readable pixels into an import failure. Similarity features use only decoded RGB; they do not use artist tags, filenames or prompts. Explicit personal judgments provide bounded ordering adjustments for the same query. Pixel-identical candidates share one result card, with all associated records and source paths available in details.

The bundled SWEGCA Architecture evidence accumulator is invoked during search and explicit feedback, preserving its original decision rules. Receipts distinguish similarity observations from explicit local ratings. Old vectors remain preserved under their original contract; changed weights, preprocessing, source or runtime versions require a separate index.

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

Comparison rows persist in the SQLite `comparisons` table (query, A/B assets, choice, timestamp, undone flag). Undo retains the original row. The latest active judgment for a pair controls its bounded preference adjustment. Ratings and ordering persist across app restarts; the browser's comparison cursor and undo stack last only for the current query session. Existing images, vectors, queries, and feedback remain intact. Generated results link the exact source case record and reuse scope.

Headless Chromium checks use temporary synthetic data and close their browsers after completion. They exercise UI and storage without live NAI generation. See [reproduction commands](APP_REFERENCE.md#verification-and-publication-boundary).

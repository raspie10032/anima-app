# Three Frame Accordion Layout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the GUI into a left control frame, center image workspace, and right history frame, with related controls grouped into accordion sections.

**Architecture:** Keep the existing stdlib-served single page in `src/anima_app/server.py`. Preserve all current form element IDs and `form="generate-form"` bindings, but move controls into grouped accordion `<details>` sections inside a dedicated left frame. Move the history panel into a right frame, keep the central workspace focused on the current image, and place runtime/readiness/status information in a collapsed right-frame Runtime Status panel.

**Tech Stack:** Python stdlib HTTP server, inline HTML/CSS/JavaScript, pytest string-contract tests, dry-run browser smoke verification.

---

### Task 1: Layout Contract Tests

**Files:**
- Modify: `tests/test_server.py`

- [x] **Step 1: Add frame and accordion assertions**

Assert the HTML includes:

```python
assert 'class="app-shell"' in INDEX_HTML
assert 'class="control-frame"' in INDEX_HTML
assert 'class="workspace-frame"' in INDEX_HTML
assert 'class="history-frame"' in INDEX_HTML
assert 'id="top-status-strip"' not in INDEX_HTML
assert 'id="side-status-panel"' in INDEX_HTML
assert 'id="control-groups"' in INDEX_HTML
assert 'class="control-group"' in INDEX_HTML
assert 'data-control-group="prompt-generate"' in INDEX_HTML
assert 'data-control-group="model-style"' in INDEX_HTML
assert 'data-control-group="image-settings"' in INDEX_HTML
assert 'data-control-group="enhance"' in INDEX_HTML
assert 'data-control-group="prompt-tools"' in INDEX_HTML
assert 'data-control-group="settings"' in INDEX_HTML
```

- [x] **Step 2: Update old sidebar reorder assertions**

Remove assertions that require `#sidebar-blocks`, `#reset-sidebar-layout`, drag handles, and `anima.sidebar.order.v1`, because the new layout uses fixed grouped accordions.

- [x] **Step 3: Run targeted contract tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_server.py::test_index_html_loads_history_panel tests/test_server.py::test_index_html_exposes_generation_stage_progress tests/test_server.py::test_index_html_exposes_auto_queue_controls -q
```

Expected: tests fail before implementation, pass after implementation.

### Task 2: Three-Frame HTML And CSS

**Files:**
- Modify: `src/anima_app/server.py`

- [x] **Step 1: Replace page grid with three frames**

Change the document body to:

```html
<body>
  <div class="app-shell">
    <aside class="control-frame" aria-label="Generation controls">...</aside>
    <main class="workspace-frame" aria-label="Image workspace">...</main>
    <aside class="history-frame" aria-label="Generation history">...</aside>
  </div>
</body>
```

- [x] **Step 2: Add collapsed right-frame status panel**

Move `#status-panel` and `#readiness-panel` into a collapsed Runtime Status panel inside the history frame. Keep `#generation-stages` in the workspace frame only as an active progress indicator:

```html
<details class="side-status-panel" id="side-status-panel">
  <summary>Runtime Status</summary>
  <section class="status-panel compact" id="status-panel" aria-label="Runtime status"></section>
  <section class="readiness-panel compact" id="readiness-panel" aria-label="Model readiness"></section>
</details>
<section class="generation-stages compact" id="generation-stages" aria-live="polite" aria-busy="false" hidden>...</section>
```

- [x] **Step 3: Make current result the central focus**

Keep `#result-panel`, `#preview`, `#output-link`, `#apply-manifest`, and manifest JSON in the center workspace and style `#preview` to occupy the primary available width without horizontal overflow.

- [x] **Step 4: Move history to right frame**

Move `.history-panel` into `.history-frame`, keep `#history`, `#history-count`, and all `data-history-filter` buttons unchanged.

### Task 3: Control Accordions

**Files:**
- Modify: `src/anima_app/server.py`
- Modify: `tests/test_server.py`

- [x] **Step 1: Group controls into fixed accordions**

Replace draggable sidebar blocks with:

```html
<div id="control-groups" class="control-groups">
  <details class="control-group" data-control-group="prompt-generate" open>...</details>
  <details class="control-group" data-control-group="model-style" open>...</details>
  <details class="control-group" data-control-group="image-settings">...</details>
  <details class="control-group" data-control-group="enhance">...</details>
  <details class="control-group" data-control-group="prompt-tools">...</details>
  <details class="control-group" data-control-group="settings">...</details>
</div>
```

- [x] **Step 2: Preserve form and API IDs**

Keep all IDs and names currently used by JavaScript:

```text
prompt, negative, generate-button, auto-queue-panel, checkpoint-select,
lora-select, lora-strength, width, height, steps, cfg, sampler, scheduler,
seed, wildcard-mode, wildcard-select, insert-wildcard, reference-image-section,
face-detailer-section, preset-select, lora-import-form
```

- [x] **Step 3: Remove sidebar reorder JavaScript**

Delete the sidebar order storage constants and handlers:

```js
sidebarBlocks
resetSidebarLayoutButton
sidebarOrderStorageKey
setupSidebarReorder()
applySidebarOrder()
```

No replacement JavaScript is needed for native `<details>` accordions.

### Task 4: Docs And Verification

**Files:**
- Modify: `README.md`
- Modify: `docs/ACCEPTANCE.md`
- Modify: `docs/REFERENCES.md`

- [x] **Step 1: Document the layout**

Record that the GUI uses left grouped accordions, a central image workspace, a collapsed right-frame Runtime Status panel, and a right history frame.

- [x] **Step 2: Run full tests and release smoke**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests -q
python scripts\release_smoke.py --include-tests
```

Expected: all tests pass and release smoke reports `status=passed`.

- [x] **Step 3: Browser dry-run smoke**

Start a dry-run GUI server and verify:

```text
left frame exists
center preview workspace exists
right history frame exists
six control accordions exist
Generate still performs a dry-run request
no console warnings/errors
no horizontal overflow
```

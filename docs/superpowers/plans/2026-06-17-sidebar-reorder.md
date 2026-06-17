# Sidebar Reorder Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let users reorder Anima APP's left sidebar function blocks by dragging handles, persist the order locally, and reset to the default layout.

**Architecture:** Keep the existing stdlib-served single-page GUI in `src/anima_app/server.py`. Wrap each left sidebar feature in a `data-sidebar-block` element under one sortable container, keep generation controls associated with an empty `generate-form` via `form="generate-form"`, and save block order to `localStorage`.

**Tech Stack:** Python stdlib HTTP server, inline HTML/CSS/JavaScript, browser `localStorage`, pytest string-contract tests, browser smoke verification.

---

### Task 1: Sidebar Block Structure

**Files:**
- Modify: `src/anima_app/server.py`
- Test: `tests/test_server.py`

- [x] **Step 1: Add sidebar contract assertions**

Add assertions to `test_index_html_loads_history_panel` for `id="sidebar-blocks"`, `data-sidebar-block` keys, `class="sidebar-drag-handle"`, `id="reset-sidebar-layout"`, and `form="generate-form"`.

- [x] **Step 2: Update the HTML layout**

Move the prompt, starting point, image settings, LoRA, generate/auto queue, prompt tools, reference/upscale, face detailer, saved settings, and import LoRA UI into a shared `#sidebar-blocks` container. Make `#generate-form` an empty form and attach generation inputs to it with `form="generate-form"`.

- [x] **Step 3: Run the sidebar contract test**

Run: `$env:PYTHONPATH='src'; python -m pytest tests/test_server.py::test_index_html_loads_history_panel -q`

Expected: pass.

### Task 2: Drag/Drop Persistence

**Files:**
- Modify: `src/anima_app/server.py`
- Test: `tests/test_server.py`

- [x] **Step 1: Add JavaScript contract assertions**

Assert the HTML contains `anima.sidebar.order.v1`, `applySidebarOrder`, `saveSidebarOrder`, `resetSidebarLayout`, `dragstart`, and pointer-based reorder handlers.

- [x] **Step 2: Implement drag and reset behavior**

Add handle-only pointer drag. Save current order to `localStorage`, apply it on load, append unknown future blocks after saved blocks, and clear storage on reset.

- [x] **Step 3: Run targeted server tests**

Run: `$env:PYTHONPATH='src'; python -m pytest tests/test_server.py::test_index_html_loads_history_panel -q`

Expected: pass.

### Task 3: Verification And Docs

**Files:**
- Modify: `README.md`
- Modify: `docs/ACCEPTANCE.md`
- Modify: `docs/REFERENCES.md`

- [x] **Step 1: Document the feature**

Mention that the left sidebar blocks are draggable, persisted locally, and resettable.

- [x] **Step 2: Run full verification**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests -q
python scripts\release_smoke.py --include-tests
```

Expected: all tests pass and release smoke reports `status=passed`.

- [x] **Step 3: Browser smoke**

Start dry-run GUI server, reorder one sidebar block, reload, confirm order persists, reset layout, and confirm the default order returns.

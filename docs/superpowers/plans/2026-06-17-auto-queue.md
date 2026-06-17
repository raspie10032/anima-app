# Auto Queue Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a GUI auto queue that repeatedly generates images from the current form settings.

**Architecture:** Keep this as a browser-side queue in the existing stdlib-served `src/anima_app/server.py` page. Each queued item reuses the existing `/api/generate` request path, progress polling, manifest rendering, history refresh, and dry-run support.

**Tech Stack:** Python stdlib HTTP server, inline HTML/CSS/JavaScript in `server.py`, pytest contract tests, browser dry-run smoke verification.

---

### Task 1: Lock The GUI Contract

**Files:**
- Modify: `tests/test_server.py`

- [ ] **Step 1: Add a failing HTML contract test**

Add assertions that `INDEX_HTML` contains the auto queue panel, count input, seed mode selector, delay input, start/stop buttons, status output, and JavaScript functions `startAutoQueue`, `stopAutoQueue`, and `runQueuedGenerate`.

- [ ] **Step 2: Run the targeted test**

Run: `$env:PYTHONPATH='src'; python -m pytest tests/test_server.py::test_index_html_exposes_auto_queue_controls -q`

Expected before implementation: fail because the auto queue controls do not exist.

### Task 2: Implement The Browser Queue

**Files:**
- Modify: `src/anima_app/server.py`

- [ ] **Step 1: Add the controls**

Add an `Auto Queue` section near the main Generate button with queue count, seed mode, delay seconds, start button, stop button, and a compact status line.

- [ ] **Step 2: Add queue state and helpers**

Add JavaScript state for running/stopping, current index, completed count, failed count, and last result.

- [ ] **Step 3: Reuse existing generation code**

Extract the single-generate POST flow into a reusable helper so both form submit and queued generation use the same request building, progress polling, result rendering, and history refresh.

- [ ] **Step 4: Add seed progression**

Implement seed modes: `fixed`, `increment`, and `random`. Increment mode uses the current seed plus the zero-based queue index when a numeric seed is present.

### Task 3: Document And Verify

**Files:**
- Modify: `README.md`
- Modify: `docs/ACCEPTANCE.md`
- Modify: `docs/REFERENCES.md`

- [ ] **Step 1: Update docs**

Document that the GUI supports a browser-side auto queue with count, seed mode, delay, progress, and stop controls.

- [ ] **Step 2: Run tests**

Run targeted server tests first, then the full test suite:

`$env:PYTHONPATH='src'; python -m pytest tests/test_server.py::test_index_html_exposes_auto_queue_controls -q`

`$env:PYTHONPATH='src'; python -m pytest tests -q`

- [ ] **Step 3: Browser dry-run smoke**

Launch the GUI in dry-run mode, set queue count to 2, start the queue, and verify two dry-run manifests are created with no console errors and no horizontal overflow.

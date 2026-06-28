# Prompt Presets Wildcards Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add prompt preset insertion backed by `wildcards/presets/*.txt`, using existing wildcard expansion semantics.

**Architecture:** Keep one wildcard engine. Extend wildcard token parsing to support path-style Unicode tokens like `__presets/portrait_clean__`, list presets separately from ordinary top-level wildcards, and expose a separate GUI selector that inserts preset tokens into the prompt. Existing random, sequential, and reverse modes remain shared.

**Tech Stack:** Python stdlib HTTP server, existing single-file HTML/JS in `src/anima_app/server.py`, pytest.

---

### Task 1: Wildcard Engine Preset Paths

**Files:**
- Modify: `src/anima_app/wildcards.py`
- Test: `tests/test_server.py`

- [ ] **Step 1: Add failing tests**

Add tests for `__presets/name__`, Unicode preset names, inventory separation, and path traversal rejection.

- [ ] **Step 2: Implement path-aware wildcard names**

Update the wildcard regex and file resolver so `wildcards/presets/name.txt` is valid while paths outside `wildcards` remain invalid.

- [ ] **Step 3: List presets separately**

Expose top-level wildcard files through `items` and preset files under `presets` in `/api/wildcards`.

### Task 2: GUI Insert Preset

**Files:**
- Modify: `src/anima_app/server.py`
- Test: `tests/test_server.py`

- [ ] **Step 1: Add prompt preset controls**

Add `preset-wildcard-select` and `insert-preset-wildcard` in Prompt Tools.

- [ ] **Step 2: Populate and insert preset tokens**

Read `payload.presets` from `/api/wildcards` and reuse comma-separated wildcard insertion behavior.

### Task 3: Docs and Verification

**Files:**
- Modify: `README.md`
- Modify: `docs/ACCEPTANCE.md`

- [ ] **Step 1: Document `wildcards/presets`**

Explain `__presets/name__` tokens and GUI insertion.

- [ ] **Step 2: Run verification**

Run targeted tests first, then the full test suite if targeted tests pass.

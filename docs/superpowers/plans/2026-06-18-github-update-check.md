# GitHub Update Check Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a read-only GitHub update checker for Anima APP releases/tags.

**Architecture:** Put version metadata, GitHub API fetch, and version comparison in a new `src/anima_app/updates.py` module. Add `/api/version` and `/api/update-check` to the existing stdlib HTTP server, then expose a `Check Update` card in the Runtime Status panel. Tests mock the update checker and never call GitHub.

**Tech Stack:** Python stdlib `urllib.request`, existing single-file HTML/JS UI in `src/anima_app/server.py`, pytest.

---

### Task 1: Update Logic

**Files:**
- Create: `src/anima_app/updates.py`
- Create: `tests/test_updates.py`

- [ ] **Step 1: Write tests for release, tag fallback, failure, and version comparison**

Use fake fetch callables returning JSON dictionaries/lists.

- [ ] **Step 2: Implement update metadata and comparison**

Expose `version_payload()` and `check_github_update()` without adding dependencies.

### Task 2: Server API

**Files:**
- Modify: `src/anima_app/server.py`
- Modify: `tests/test_server.py`

- [ ] **Step 1: Add API tests**

Cover `/api/version` and `/api/update-check` with monkeypatched update responses.

- [ ] **Step 2: Add GET routes**

Route requests to the update module and always return JSON.

### Task 3: GUI Integration

**Files:**
- Modify: `src/anima_app/server.py`
- Modify: `tests/test_server.py`

- [ ] **Step 1: Add Runtime Status update card**

Add current version, `Check Update` button, status text, and release link.

- [ ] **Step 2: Wire browser-side fetch**

Fetch `/api/version` during status load and `/api/update-check` only on button click.

### Task 4: Docs And Verification

**Files:**
- Modify: `README.md`
- Modify: `docs/ACCEPTANCE.md`

- [ ] **Step 1: Document read-only update checks**

State that update check uses GitHub releases/tags and does not auto-download or modify files.

- [ ] **Step 2: Run verification**

Run targeted tests, then full `python -m pytest tests -q`.

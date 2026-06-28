# Server Job Queue Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add server-owned generation queueing and first-pass generation stop/cancel controls to Anima APP.

**Architecture:** Keep the current stdlib HTTP server and single HTML/JS UI. Add an in-memory queue next to `ProgressStore`; queued jobs run sequentially on one worker thread through the existing `handle_generate` path. The browser submits jobs to `/api/jobs`, polls `/api/jobs`, and sends stop requests to cancel queued jobs or request stop on the active job.

**Tech Stack:** Python stdlib `ThreadingHTTPServer`, existing `src/anima_app/server.py` HTML/JS template, `pytest`, Pillow-based renderer tests.

---

### Task 1: Queue API

**Files:**
- Modify: `src/anima_app/server.py`
- Test: `tests/test_server.py`

- [ ] **Step 1: Write failing tests**

Add tests proving `POST /api/jobs` accepts `{"count": 2, "request": {...}}`, returns two job ids, `GET /api/jobs` lists them, and the worker completes dry-run jobs sequentially.

- [ ] **Step 2: Verify red**

Run: `python -m pytest tests/test_server.py -q`

Expected: failures for missing `/api/jobs`.

- [ ] **Step 3: Implement minimal queue**

Add `JobQueue` and `JobRecord` behavior inside `server.py`, backed by a lock, a condition, and one daemon worker thread. Store recent jobs in memory with statuses `queued`, `running`, `completed`, `failed`, and `cancelled`.

- [ ] **Step 4: Verify green**

Run: `python -m pytest tests/test_server.py -q`

Expected: queue API tests pass without breaking existing generate/history/progress tests.

### Task 2: Cancel And Stop API

**Files:**
- Modify: `src/anima_app/server.py`
- Test: `tests/test_server.py`

- [ ] **Step 1: Write failing tests**

Add tests proving `POST /api/jobs/<id>/cancel` cancels a queued job and sets active job stop-request state.

- [ ] **Step 2: Verify red**

Run: `python -m pytest tests/test_server.py -q`

Expected: failures for missing cancel route/status.

- [ ] **Step 3: Implement cancel**

Implement cancellation for queued jobs immediately. For active jobs, mark `cancel_requested=true`; generation will finish the current renderer call in this first pass, then report the job as completed or failed according to the existing renderer result. Hard interrupt inside PyTorch render remains out of scope until renderer subprocess isolation exists.

- [ ] **Step 4: Verify green**

Run: `python -m pytest tests/test_server.py -q`

Expected: cancel tests pass.

### Task 3: GUI Wiring

**Files:**
- Modify: `src/anima_app/server.py`
- Test: `tests/test_server.py`

- [ ] **Step 1: Write failing HTML tests**

Assert the UI contains `/api/jobs`, queue polling, a server queue id field, and stop buttons calling `/api/jobs/<id>/cancel`.

- [ ] **Step 2: Implement UI**

Replace browser-side sequential `/api/generate` loop with `POST /api/jobs`. Poll `/api/jobs` for totals and active/latest job. `Stop` sends cancel for queued/running jobs.

- [ ] **Step 3: Verify browser behavior**

Start a dry-run server and confirm `POST /api/jobs`, `GET /api/jobs`, and UI queue controls work from the running page.

### Task 4: Docs And Final Checks

**Files:**
- Modify: `README.md`
- Modify: `docs/ACCEPTANCE.md`

- [ ] **Step 1: Document behavior**

Document that server queue survives browser-side loop loss while the Python process is alive. Document first-pass active stop limitation.

- [ ] **Step 2: Run checks**

Run: `python -m pytest tests -q`

Expected: all tests pass.

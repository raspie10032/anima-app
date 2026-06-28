# Nested Wildcards And Preview Implementation Plan

**Goal:** Add recursive wildcard expansion, inline random prompt choices, and a GUI/API preview path that validates wildcard output before generation.

**Scope:** CPU-safe only. Do not launch GPU generation. Keep the existing stdlib server and single `wildcards.py` engine so CLI, API, and GUI share behavior.

## Tasks

- [x] Add tests for nested `__name__` expansion, inline `{A|B|C}` choices, sequential state through nested tokens, cycle rejection, and depth rejection.
- [x] Replace single-pass wildcard substitution with recursive expansion in `src/anima_app/wildcards.py`.
- [x] Add `/api/wildcards/preview` for prompt-only expansion and validation.
- [x] Add a Prompt Tools preview button and result panel.
- [x] Update README, acceptance notes, and references.
- [x] Run full verification.

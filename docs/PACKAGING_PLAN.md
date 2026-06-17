# Anima APP Packaging Plan

Current public release target: source-checkout alpha.

## Source-Checkout Layout

Included in the source release:

- `pyproject.toml`
- `README.md`
- `LICENSE`
- `NOTICE.md`
- `Run-AnimaAPP-GUI.cmd`
- `scripts`
- `src`
- `vendor/anima_runtime`
- `vendor/python_packages`
- `docs`
- `wildcards`

Excluded from the source release:

- `models`
- `outputs`
- `inputs`
- `.git`
- `.pytest_cache`
- `__pycache__`

## Maintainer Packaging Check

The maintainer packaging proof lives at:

```powershell
python scripts\package_dry_run.py
```

It builds and inspects a temporary wheel under `outputs\package_dry_run`, verifies package metadata and console entry points, confirms local artifact roots are excluded, and records a source-checkout layout report.

## Not Finalized

- Standalone binary packaging.
- Final wheel redistribution policy for vendored runtime assets.
- Automated public release artifact creation beyond GitHub source archives.

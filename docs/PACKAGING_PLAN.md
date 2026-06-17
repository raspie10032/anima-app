# Anima APP Packaging Plan

Current packaging target: source-checkout alpha with a proven wheel dry run.

The app is not yet a finalized standalone binary. This plan separates the pieces that can be proven now from the pieces that still need a dedicated packaging pass.

## Wheel Dry-Run Proof

Run:

```powershell
python scripts\package_dry_run.py
```

The dry-run script:

- Builds a wheel into `outputs\package_dry_run` with `python -m pip wheel . --no-deps --no-build-isolation`.
- Inspects the wheel for the `anima_app` package, package metadata, and `anima-app` console entry point.
- Confirms local artifact roots such as `models`, `outputs`, and `inputs` are not inside the wheel.
- Writes `outputs\package_dry_run\package_dry_run_report.json`.

The wheel proves Python packaging metadata and console-script wiring. It does not include the vendored runtime tree or local model assets.

## Standalone Layout Dry Run

`scripts\package_dry_run.py` also emits a standalone layout plan. The layout includes:

- `src`
- `scripts`
- `docs`
- `vendor\anima_runtime`
- `vendor\python_packages`
- `README.md`
- `NOTICE.md`
- `Run-AnimaAPP-GUI.cmd`
- `Run-AnimaAPP-GUI-DryRun.cmd`
- `Run-AnimaAPP-ReleaseSmoke.cmd`
- `wildcards` when present

The layout excludes:

- `models`
- `outputs`
- `inputs`
- `.git`
- `.pytest_cache`
- `__pycache__`

This is a dry-run contract, not a binary bundle. A later standalone pass should choose a real bundling tool or portable source archive format and then add a build command that materializes the layout.

## Open Packaging Work

- Decide whether the public artifact is a wheel, a portable source archive, a PyInstaller-style binary, or both wheel plus portable archive.
- Decide how to handle the vendored runtime in a redistributable artifact.
- Keep model, detector, LoRA, input, and output artifacts outside redistributable packages unless license and size constraints are explicitly handled.
- Preserve `CUDA_VISIBLE_DEVICES=0` launcher behavior for local Windows runs.

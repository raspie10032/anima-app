# Anima APP Release Checklist

Current release target: source-checkout alpha.

This checklist is for maintainers preparing a public source release. It verifies source files, docs, ignored artifact roots, and release tooling without including local model or output artifacts.

## Required Files

- [ ] `pyproject.toml` declares the `anima-app` package.
- [ ] `LICENSE` and `NOTICE.md` are present.
- [ ] `README.md`, `docs\ACCEPTANCE.md`, `docs\REFERENCES.md`, `docs\PACKAGING_PLAN.md`, and this checklist are present.
- [ ] `src\anima_app` exists.
- [ ] `vendor\anima_runtime` exists and retains upstream license notices.
- [ ] `vendor\python_packages` exists and retains package metadata/license files.
- [ ] `Run-AnimaAPP-GUI.cmd` starts the user-facing GUI.
- [ ] `scripts\smoke_anima_app.py`, `scripts\release_smoke.py`, and `scripts\package_dry_run.py` exist for maintainer validation.
- [ ] `.gitignore` excludes `models`, `outputs`, and `inputs`.

## Maintainer Validation

Run before tagging or sharing a source-checkout alpha:

```powershell
python scripts\release_smoke.py --include-tests
```

The release validation checks:

- Static source-checkout files and artifact ignore rules.
- Runtime health JSON.
- Manifest-generation validation path.
- The full pytest suite when `--include-tests` is supplied.

Packaging-focused validation:

```powershell
python scripts\package_dry_run.py
```

This writes reports and temporary wheel artifacts under `outputs\package_dry_run`, which stays out of git.

## Optional Real Generation Check

Only run real generation after model assets are prepared locally. If the machine has multiple GPUs, set `CUDA_VISIBLE_DEVICES` before launching the app or maintainer scripts.

## Source-Checkout Alpha Boundary

Included:

- Editable source checkout.
- Vendored runtime tree.
- Model preparation command.
- User-facing GUI launcher.
- Public docs and notices.
- Maintainer validation scripts.

Excluded:

- Model weights.
- Detector weights.
- LoRA files.
- Input images.
- Generated outputs and manifests.

Not finalized:

- Standalone binary packaging.
- Final wheel redistribution policy for vendored runtime assets.
- Redistribution of local model, detector, LoRA, input, or output artifacts.

# Anima APP Release Checklist

Current release target: source-checkout alpha.

This checklist is for the local lightweight app in `C:\Users\seine\Documents\Anima APP`. It verifies that a fresh source checkout has the expected app files, vendored runtime tree, dry-run generation path, and documentation before sharing or tagging.

## Required Files

- [ ] `pyproject.toml` declares the `anima-app` package.
- [ ] `src\anima_app` exists.
- [ ] `vendor\anima_runtime` exists.
- [ ] `README.md`, `docs\ACCEPTANCE.md`, `docs\REFERENCES.md`, and this checklist exist.
- [ ] `Run-AnimaAPP-GUI.cmd` starts the real-generation GUI.
- [ ] `Run-AnimaAPP-GUI-DryRun.cmd` starts the dry-run GUI.
- [ ] `Run-AnimaAPP-ReleaseSmoke.cmd` runs the release smoke.
- [ ] `scripts\smoke_anima_app.py`, `scripts\release_smoke.py`, and `scripts\package_dry_run.py` exist.
- [ ] `docs\PACKAGING_PLAN.md` documents the wheel and standalone dry-run boundary.
- [ ] `.gitignore` excludes `models`, `outputs`, and `inputs`.

## CPU-Safe Verification

Run this before tagging or sharing the source-checkout alpha:

```powershell
python scripts\release_smoke.py --include-tests
```

The release smoke checks:

- Static source-checkout files and artifact ignore rules.
- `python -m anima_app.cli health --json`.
- `python scripts\smoke_anima_app.py --dry-run --require-checks`.
- The full pytest suite when `--include-tests` is supplied.

The smoke script forces `CUDA_VISIBLE_DEVICES=0` in its subprocess environment and does not request a real GPU render.

On Windows, the same check can be launched with:

```powershell
.\Run-AnimaAPP-ReleaseSmoke.cmd
```

Run the packaging dry-run proof when preparing a packaging-focused snapshot:

```powershell
python scripts\package_dry_run.py
```

This writes its report and wheel artifact under `outputs\package_dry_run`, which stays out of git.

## Optional Real GPU Smoke

Only run real generation after model assets are prepared locally. Keep GPU visibility pinned to the 4070:

```powershell
$env:PYTHONPATH='src'
$env:CUDA_VISIBLE_DEVICES='0'
python scripts\smoke_anima_app.py --prompt "anime portrait, clean lineart" --negative "low quality" --width 512 --height 768 --steps 1 --cfg 1.0 --seed 53 --require-checks
```

Do not use GPU 1 / RTX 5060 for this app unless the user explicitly reverses that rule.

## Source-Checkout Alpha Boundary

Included:

- Editable install path.
- Vendored Anima runtime tree.
- Automatic Anima base profile copy/download command.
- Dry-run GUI/API launcher.
- Release smoke and acceptance checklist.
- Wheel dry-run proof and standalone layout plan.

Not finalized:

- Wheel packaging.
- Standalone binary packaging.
- Automated vendored-runtime packaging for public distribution.
- Redistribution of local model, detector, LoRA, input, or output artifacts.

# Release Artifact Manifest

This manifest distinguishes release source, verification code, and generated deliverables for the `0.5.0` source-checkout beta candidate.

The baseline source was published as `b363505`. The main source update integrates the pinned 2.4.6 work and image/generation workspaces at the same app version; [the original acceptance record](NAI_NODE_UPDATE_2.4.6.md) identifies the pinned source and verification limits. Dated `outputs/` paths below are local development artifacts, excluded from Git and from the ZIP itself.

| Path | Type | Role | Source | Status | Verification |
|---|---|---|---|---|---|
| `src/anima_app/__init__.py` | Python source | Canonical application version | Hand-edited | Verified | Version/packaging tests passed |
| `pyproject.toml` | Build config | Reads the canonical package version | Hand-edited | Verified | Wheel metadata matched application version |
| `.github/workflows/ci.yml` | CI config | CPU-safe lint, test, package, and archive checks | Hand-edited | Implemented | Contract test passed; remote Actions run is not claimed |
| `scripts/package_dry_run.py` | Verification source | Builds from a temporary source copy and installs to an isolated target without mutating the checkout | Hand-edited | Verified | Local wheel/install/CLI smoke passed |
| `scripts/source_archive.py` | Generator source | Builds and verifies the source-checkout ZIP | Hand-edited | Verified | Reproducibility and extracted smoke tests passed |
| `scripts/audit_nai_port_release.py` | Verification source | Checks all remaining-port evidence, source ZIP byte equality/reproducibility, preserved originals and isolated wheel | Hand-edited | Local candidate audit | Report under `outputs/all-nai-port-20261009/final-package` |
| `scripts/audit_nai_update_release.py` | Verification source | Checks all six update requirements, preserved baseline browser behavior, current CPU taggers, installed/pinned source hashes and artifact equality | Hand-edited | Local 2.4.6 audit | Report under `outputs/nai-update-20261011/final` |
| `outputs/release/nai-node-2.4.6-final-20261011/verified/` | Generated artifacts | Updated source ZIP, wheel, SHA-256 sidecars and wheel report | Package and archive scripts | Local 2.4.6 candidate | Exact source/static/catalog bytes, isolated wheel install, extracted CLI/vendor checks and reproducible ZIP |
| `docs/NAI_PORT_ACCEPTANCE.md` | Acceptance document | Maps requested ports to source tests, browser/native evidence and verification limits | Hand-edited from local artifacts | Local candidate | New live-port acceptance remains unverified |
| `vendor/README.md` | Provenance document | Records vendored runtime/package versions and licenses | Hand-edited from bundled metadata | Verified | RECORD, product-boundary, and disclosure tests passed |
| `docs/RELEASE_0.5.0.md` | Release document | Records provider integration and its evidence boundary | Hand-edited | Implemented | Release-surface tests |
| `docs/NOVELAI_PROVIDER.md` | User guide | NovelAI setup, costs, cancellation and API | Hand-edited | Implemented | Mock and browser acceptance |
| `docs/USER_GUIDE_KO.md` | User guide | Korean GUI, CLI, and AI-agent instructions | Hand-edited | Verified | Link, command, API, and source-archive contract checks passed |
| `outputs/release/all-nai-port-final-20261009/anima-app-0.5.0-source.zip` | Generated artifact | Final remaining-port local source-checkout review candidate | `scripts/source_archive.py` | Local candidate | Byte equality, repeated ZIP hash and extraction smoke; publication is separate |
| `outputs/release/all-nai-port-final-20261009/anima-app-0.5.0-source.zip.sha256` | Generated artifact | Digest for the final local review candidate | `scripts/source_archive.py` | Local candidate | Regenerated alongside source ZIP; older dated archives preserved |

Generated release candidates are ignored by Git and are not public uploads. A working-tree candidate is review evidence; an official archive requires a committed clean checkout and `--require-clean`. Model weights, detector weights, LoRAs, inputs, outputs, local configuration, and Git history are outside the archive boundary.

## Current main documentation

The [main update record](MAIN_UPDATE_2026-10-14.md), [token setup](NAI_TOKEN_SETUP.md), [app reference](APP_REFERENCE.md) and generation tutorials in [Korean](IMAGE_GENERATION_KO.md), [English](IMAGE_GENERATION_EN.md) and [Japanese](IMAGE_GENERATION_JA.md) accompany the integrated source. A main-branch push does not publish the local release artifacts listed above or create a versioned release.

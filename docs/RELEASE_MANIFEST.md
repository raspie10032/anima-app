# Release Artifact Manifest

This manifest distinguishes release source, verification code, and generated deliverables for the `0.5.0` source-checkout beta candidate.

| Path | Type | Role | Source | Status | Verification |
|---|---|---|---|---|---|
| `src/anima_app/__init__.py` | Python source | Canonical application version | Hand-edited | Verified | Version/packaging tests passed |
| `pyproject.toml` | Build config | Reads the canonical package version | Hand-edited | Verified | Wheel metadata matched application version |
| `.github/workflows/ci.yml` | CI config | CPU-safe lint, test, package, and archive checks | Hand-edited | Implemented | Contract test passed; remote Actions run is not claimed |
| `scripts/package_dry_run.py` | Verification source | Builds from a temporary source copy and installs to an isolated target without mutating the checkout | Hand-edited | Verified | Local wheel/install/CLI smoke passed |
| `scripts/source_archive.py` | Generator source | Builds and verifies the source-checkout ZIP | Hand-edited | Verified | Reproducibility and extracted smoke tests passed |
| `scripts/audit_nai_port_release.py` | Verification source | Checks all remaining-port evidence, source ZIP byte equality/reproducibility, preserved originals and isolated wheel | Hand-edited | Local candidate audit | Report under `outputs/all-nai-port-20261009/final-package` |
| `docs/NAI_PORT_ACCEPTANCE.md` | Acceptance document | Maps requested ports to source tests, browser/native evidence and verification limits | Hand-edited from local artifacts | Local candidate | New live-port acceptance remains unverified |
| `vendor/README.md` | Provenance document | Records vendored runtime/package versions and licenses | Hand-edited from bundled metadata | Verified | RECORD, product-boundary, and disclosure tests passed |
| `docs/RELEASE_0.5.0.md` | Release document | Records provider integration and its evidence boundary | Hand-edited | Implemented | Release-surface tests |
| `docs/NOVELAI_PROVIDER.md` | User guide | NovelAI setup, costs, cancellation and API | Hand-edited | Implemented | Mock and browser acceptance |
| `docs/USER_GUIDE_KO.md` | User guide | Korean GUI, CLI, and AI-agent instructions | Hand-edited | Verified | Link, command, API, and source-archive contract checks passed |
| `outputs/release/all-nai-port-final-20261009/anima-app-0.5.0-source.zip` | Generated artifact | Final remaining-port local source-checkout review candidate | `scripts/source_archive.py` | Local candidate | Byte equality, repeated ZIP hash and extraction smoke; publication is separate |
| `outputs/release/all-nai-port-final-20261009/anima-app-0.5.0-source.zip.sha256` | Generated artifact | Digest for the final local review candidate | `scripts/source_archive.py` | Local candidate | Regenerated alongside source ZIP; older dated archives preserved |

Generated release candidates are ignored by Git and are not public uploads. A working-tree candidate is review evidence; an official archive requires a committed clean checkout and `--require-clean`. Model weights, detector weights, LoRAs, inputs, outputs, local configuration, and Git history are outside the archive boundary.

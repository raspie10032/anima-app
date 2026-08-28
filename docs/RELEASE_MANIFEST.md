# Release Artifact Manifest

This manifest distinguishes release source, verification code, and generated deliverables for the `0.4.0` source-checkout beta.

| Path | Type | Role | Source | Status | Verification |
|---|---|---|---|---|---|
| `src/anima_app/__init__.py` | Python source | Canonical application version | Hand-edited | Verified | Version/packaging tests passed |
| `pyproject.toml` | Build config | Reads the canonical package version | Hand-edited | Verified | Wheel metadata matched application version |
| `.github/workflows/ci.yml` | CI config | CPU-safe lint, test, package, and archive checks | Hand-edited | Implemented | Contract test passed; remote Actions run is not claimed |
| `scripts/package_dry_run.py` | Verification source | Builds from a temporary source copy and installs to an isolated target without mutating the checkout | Hand-edited | Verified | Local wheel/install/CLI smoke passed |
| `scripts/source_archive.py` | Generator source | Builds and verifies the source-checkout ZIP | Hand-edited | Verified | Reproducibility and extracted smoke tests passed |
| `vendor/README.md` | Provenance document | Records vendored runtime/package versions and licenses | Hand-edited from bundled metadata | Verified | RECORD, product-boundary, and disclosure tests passed |
| `docs/RELEASE_0.4.0.md` | Release document | Records the user-visible release scope and limits | Hand-edited | Verified | Release-surface test passed |
| `docs/USER_GUIDE_KO.md` | User guide | Korean GUI, CLI, and AI-agent instructions | Hand-edited | Verified | Link, command, API, and source-archive contract checks passed |
| `outputs/release/anima-app-0.4.0-source.zip` | Generated artifact | Local source-checkout release candidate | `scripts/source_archive.py` | Stale | Regenerate after committing the guide and current source changes |
| `outputs/release/anima-app-0.4.0-source.zip.sha256` | Generated artifact | Digest for the local release candidate | `scripts/source_archive.py` | Stale | Regenerate with the source ZIP before publication |

Generated release candidates are ignored by Git and are not public uploads. The existing candidate and digest predate the current guide/source changes and must not be published as current. Model weights, detector weights, LoRAs, inputs, outputs, local configuration, and Git history are outside the archive boundary.

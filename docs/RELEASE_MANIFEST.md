# Release Artifact Manifest

Current distribution: **Anima APP 0.6.1 source-checkout beta**, 2026-10-15.

Download the attached **[anima-app-0.6.1-source.zip](https://github.com/raspie10032/anima-app/releases/download/v0.6.1/anima-app-0.6.1-source.zip)** from the [v0.6.1 release](https://github.com/raspie10032/anima-app/releases/tag/v0.6.1). Its sibling **[.sha256](https://github.com/raspie10032/anima-app/releases/download/v0.6.1/anima-app-0.6.1-source.zip.sha256)** identifies the exact verified artifact. GitHub's automatically generated source archives are convenience copies; their ZIP bytes differ from the attached verified archive.

## Public deliverables

| File | Purpose |
|---|---|
| `anima-app-0.6.1-source.zip` | Application source, Windows launcher, browser assets, vendored local runtime, wildcards, guides, tests and license notices |
| `anima-app-0.6.1-source.zip.sha256` | SHA-256 and filename of the source ZIP |
| `verification.json` | Release commit, local check results, artifact hashes and remote CI links |

The ZIP contains one `anima-app-0.6.1/` directory. Install Python 3.10+ and dependencies before running the launcher or CLI. Models, detector/tagger weights, LoRAs, image collections, vectors, local artist catalogs, inputs, outputs, tokens and local configuration are not bundled. Setup is described in the [release notes](RELEASE_0.6.1.md) and first-image guides in [한국어](IMAGE_GENERATION_KO.md), [English](IMAGE_GENERATION_EN.md) and [日本語](IMAGE_GENERATION_JA.md).

## Build and verification sources

| Path | Role |
|---|---|
| `src/anima_app/__init__.py` | Canonical version; packaging metadata reads it through `pyproject.toml` |
| `.github/workflows/ci.yml` | Python 3.10/3.13 CPU tests, lint, JavaScript checks, Windows launcher checks, vendor/package/archive verification |
| `scripts/source_archive.py` | Deterministic ZIP from committed Git blobs with `--require-clean`; validates required files and excludes private runtime directories/native binaries |
| `scripts/package_dry_run.py` | Isolated wheel build/install, Python/JS/JSON/CSS equality, license and CLI checks |
| `scripts/verify_vendor.py` | Vendored runtime/package integrity and product boundary |
| `tests/test_release.py` | Version agreement, required documentation/resources, omissions, reproducible source archive and packaging contracts |
| `vendor/README.md`, `NOTICE.md` | Runtime versions, provenance and third-party licenses |

From a clean checkout of `v0.6.1` with its Python environment installed:

```bash
python scripts/verify_vendor.py
python scripts/package_dry_run.py
python scripts/source_archive.py --require-clean
```

The final command writes `outputs/release/anima-app-0.6.1-source.zip` and its digest. Fixed timestamps, permissions, ordering and uncompressed ZIP members make a clean rebuild byte-for-byte reproducible across checkout line endings and compressor versions. It also extracts the archive and runs vendor verification and a local CLI dry-run. The command itself does not create a tag or publish anything.

The wheel is checked locally and in CI but is **not the supported full-generation download**: it excludes the root-level vendored runtime. Release upload uses only the explicit source ZIP, checksum and public verification receipt filenames, not a wildcard over development outputs.

To check a downloaded ZIP on Linux:

```bash
sha256sum -c anima-app-0.6.1-source.zip.sha256
```

On Windows PowerShell, compare the result with the first value in the downloaded `.sha256`:

```powershell
Get-FileHash ./anima-app-0.6.1-source.zip -Algorithm SHA256
```

## Earlier records

The [0.5.0 development record](RELEASE_0.5.0.md), [pinned RS NAI 2.4.6 acceptance](NAI_NODE_UPDATE_2.4.6.md) and [2026-10-14 main integration](MAIN_UPDATE_2026-10-14.md) retain their original dates and validation scope. Their ignored `outputs/` references are local evidence, not additional files in this release. Current remote CI and download checks are tied to the release tag/commit.

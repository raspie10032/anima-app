# Vendored Runtime Inventory

This directory is part of the Anima APP source-checkout distribution. It is not included in the Python wheel.

## `anima_runtime`

- Upstream: [ComfyUI](https://github.com/comfyanonymous/ComfyUI)
- Reported upstream version: ComfyUI 0.22.2, from `anima_runtime/comfyui_version.py`
- License: GPL-3.0, preserved in `anima_runtime/LICENSE`
- Provenance limit: the exact upstream commit used for this snapshot was not preserved in the repository history. Do not claim commit-level reproducibility for this vendored tree.
- Local compatibility change: `comfy/quant_ops.py` disables optional `comfy_kitchen` native operations by default through `ANIMA_APP_DISABLE_COMFY_KITCHEN`; setting that variable to `0`, `false`, or `no` opts back in.

## `python_packages`

- `comfy-kitchen 0.2.8`: Apache-2.0; its `LICENSE` and `NOTICE` are preserved under `comfy_kitchen-0.2.8.dist-info/licenses`.
- `comfy-aimdo 0.3.0` base package: GPL-3.0; its license is preserved under `comfy_aimdo-0.3.0.dist-info/licenses`.

The `comfy_aimdo` Python modules are intentionally patched into an Anima APP compatibility shim. On 2026-08-28, the project-added `__init__.py` and the patched `control.py`, `host_buffer.py`, `model_mmap.py`, `model_vbar.py`, `torch.py`, and `vram_buffer.py` were recorded as the local no-native shim surface. The shim avoids loading the optional native allocator and lets ComfyUI use standard PyTorch memory paths. The bundled metadata version therefore identifies the upstream base package, not an unmodified wheel. The exact upstream wheel hash and source revision were not preserved. `scripts/verify_vendor.py` owns the local `RECORD` hashes for this disclosed patched snapshot.

The unused upstream `aimdo.dll` and `aimdo_rocm.dll` files were removed from the supported source snapshot because the shim never loads them and their exact corresponding-source provenance was not retained. The `comfy-kitchen` native `_C.abi3.pyd` found in some local installations is also intentionally not tracked or included in the source release. A future standalone-binary release must resolve and document the corresponding-source boundary before adding native binaries as supported runtime components.

## Refresh Policy

Any vendor refresh must record the upstream repository, version/tag, exact commit, original artifact digest, local patches, license files, and regenerated integrity metadata before release.

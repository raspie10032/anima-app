"""Pure-Python compatibility shim for ComfyUI's optional aimdo package.

GemmAnima vendors the ComfyUI runtime, but does not require aimdo's native
Windows CUDA allocator extensions.  The original package eagerly loads
``aimdo.dll`` at import time, which can crash when the app's PyTorch/CUDA build
does not match the DLL.  Keep the public surface importable and report no
native VRAM usage so ComfyUI falls back to its standard PyTorch paths.
"""

lib = None


def get_devctx(device):
    return None


def get_total_vram_usage():
    return 0

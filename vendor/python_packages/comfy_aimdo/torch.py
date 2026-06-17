"""Torch helpers for the GemmAnima no-aimdo shim."""

from __future__ import annotations

import torch


def aimdo_to_tensor(alloc, device):
    if isinstance(alloc, torch.Tensor):
        return alloc.to(device=device, non_blocking=False)
    if isinstance(alloc, tuple) and alloc and isinstance(alloc[0], torch.Tensor):
        return alloc[0].to(device=device, non_blocking=False)
    raise RuntimeError("aimdo native allocation is unavailable in GemmAnima embedded runtime")


def hostbuf_to_tensor(hostbuf):
    if hasattr(hostbuf, "tensor"):
        return hostbuf.tensor
    raise RuntimeError("aimdo host buffer is unavailable in GemmAnima embedded runtime")


def get_torch_allocator():
    return None

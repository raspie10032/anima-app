"""One local generation context; GPUWorkLock releases it for VRS/other owners."""
from __future__ import annotations

import copy
import gc
import os
import sys
import threading
from collections import OrderedDict
from pathlib import Path

LOCAL_RUNTIME_OWNER = object()
_lock = threading.RLock()
_key = None
_context = None
_conditioning = OrderedDict()
_detector_key = None
_detector = None


def file_signature(path):
    path = Path(path).resolve()
    stat = path.stat()
    return str(path), stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns


def clear():
    global _key, _context, _detector_key, _detector
    with _lock:
        had_context = _context is not None or _detector is not None
        _key = _context = _detector_key = _detector = None
        _conditioning.clear()
        if had_context:
            management = sys.modules.get('comfy.model_management')
            if management is not None:
                management.unload_all_models()
            gc.collect()
            if management is not None:
                management.soft_empty_cache()


def get_models(model_paths, loras, *, apply_loras, resolve_lora):
    global _key, _context
    import torch
    import comfy.sd
    import comfy.utils
    import folder_paths

    roots = [Path(p) for p in folder_paths.get_folder_paths('loras')]
    embeddings = [Path(p) for p in folder_paths.get_folder_paths('embeddings')]
    embedding_files = tuple(file_signature(p) for root in embeddings if root.is_dir()
                            for p in sorted(root.rglob('*')) if p.is_file())
    key = (tuple(file_signature(p) for p in (model_paths.diffusion_model, model_paths.text_encoder, model_paths.vae)),
           tuple((file_signature(resolve_lora(lora, roots)), lora.model_strength, lora.clip_strength) for lora in loras),
           tuple(str(p.resolve()) for p in embeddings), embedding_files,
           os.environ.get('CUDA_VISIBLE_DEVICES'), torch.cuda.current_device() if torch.cuda.is_available() else 'cpu')
    with _lock:
        if key == _key and _context is not None:
            return _context
        clear()
        model = comfy.sd.load_diffusion_model(str(model_paths.diffusion_model), model_options={})
        clip = comfy.sd.load_clip(ckpt_paths=[str(model_paths.text_encoder)],
                                 embedding_directory=[str(p) for p in embeddings],
                                 clip_type=comfy.sd.CLIPType.QWEN_IMAGE)
        model, clip, resolved = apply_loras(model, clip, loras)
        vae = comfy.sd.VAE(sd=comfy.utils.load_torch_file(str(model_paths.vae)))
        _context = (model, clip, resolved, vae)
        _key = key
        return _context


def encode(clip, text):
    with _lock:
        cacheable = _context is not None and _context[1] is clip
        if cacheable and text in _conditioning:
            _conditioning.move_to_end(text)
            return copy.deepcopy(_conditioning[text])
        value = clip.encode_from_tokens_scheduled(clip.tokenize(text or ''))
        if cacheable:
            _conditioning[text] = copy.deepcopy(value)
            while len(_conditioning) > 8:
                _conditioning.popitem(last=False)
        return value


def get_detector(key, factory):
    """Keep one detector set, released alongside the model when VRS takes GPU."""
    global _detector_key, _detector
    with _lock:
        if key != _detector_key:
            _detector = None
            _detector_key = None
            _detector = factory()
            _detector_key = key
        return _detector

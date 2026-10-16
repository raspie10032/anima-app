"""Bounded model reuse, conditioning isolation and GPU handoff regressions."""
from types import ModuleType, SimpleNamespace
import sys

import pytest

from anima_app.requests import T2ILoraConfig
from anima_app.runtime import model_cache as cache


@pytest.fixture
def models(tmp_path, monkeypatch):
    comfy = ModuleType('comfy')
    comfy.__path__ = []
    counts = dict(model=0, clip=0, vae=0, encode=0, unload=0)

    class Clip:
        def tokenize(self, text):
            return text
        def encode_from_tokens_scheduled(self, text):
            counts['encode'] += 1
            return [[text, {'conditioning': [1]}]]

    def load(kind, value):
        def call(*a, **kw):
            counts[kind] += 1
            return value()
        return call

    for name in ('sd', 'utils', 'model_management'):
        module = ModuleType('comfy.' + name)
        setattr(comfy, name, module)
        monkeypatch.setitem(sys.modules, 'comfy.' + name, module)
    monkeypatch.setitem(sys.modules, 'comfy', comfy)
    monkeypatch.setitem(sys.modules, 'torch', SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: False)))
    comfy.sd.load_diffusion_model = load('model', object)
    comfy.sd.load_clip = load('clip', Clip)
    comfy.sd.CLIPType = SimpleNamespace(QWEN_IMAGE=1)
    comfy.sd.VAE = load('vae', object)
    comfy.utils.load_torch_file = lambda *a: {}
    comfy.model_management.unload_all_models = load('unload', lambda: None)
    comfy.model_management.soft_empty_cache = lambda: None
    monkeypatch.setitem(sys.modules, 'folder_paths', SimpleNamespace(get_folder_paths=lambda *a: [tmp_path]))
    paths = SimpleNamespace(diffusion_model=tmp_path/'model', text_encoder=tmp_path/'clip', vae=tmp_path/'vae')
    for path in vars(paths).values():
        path.write_bytes(b'weight')
    lora = tmp_path/'style'
    lora.write_bytes(b'lora')
    cache.clear()
    def get(loras=()):
        return cache.get_models(
            paths,
            loras,
            resolve_lora=lambda lora, roots: tmp_path / lora.path,
            apply_loras=lambda model, clip, configs: (model, clip, [lora.path for lora in configs]),
        )
    try:
        yield get, counts, paths, lora
    finally:
        cache.clear()


def test_identical_model_is_reused_lora_changes_and_removal_reload(models):
    get, counts, paths, lora = models
    first = get()
    assert get() is first
    assert counts['model'] == counts['clip'] == counts['vae'] == 1
    styled = get((T2ILoraConfig('style'),))
    assert styled is get((T2ILoraConfig('style'),))
    assert get((T2ILoraConfig('style', .5),)) is not styled
    assert get() is not first  # One entry only; no patched model survives removal.
    prior = get()
    paths.vae.write_bytes(b'changed model file')
    assert get() is not prior
    assert counts['model'] == 5


def test_conditioning_is_bounded_and_isolated_from_mutating_consumer(models):
    get, counts, *_ = models
    clip = get()[1]
    first = cache.encode(clip, 'portrait')
    first[0][1]['conditioning'].append(999)
    assert cache.encode(clip, 'portrait')[0][1]['conditioning'] == [1]
    assert counts['encode'] == 1
    for i in range(20):
        cache.encode(clip, str(i))
    assert len(cache._conditioning) == 8
    cache.encode(clip, 'portrait')
    assert counts['encode'] == 22


def test_gpu_handoff_releases_models_conditioning_and_detector(models):
    from anima_app.gpu_work_lock import GPUWorkLock
    get, counts, *_ = models
    first = get()
    cache.encode(first[1], 'text')
    detector = cache.get_detector('set1', object)
    assert cache.get_detector('set1', object) is detector
    lock = GPUWorkLock()
    with lock:
        assert get() is first
    assert lock.acquire(owner=object())  # VRS/other GPU owner.
    lock.release()
    assert cache._context is None and not cache._conditioning and cache._detector is None
    assert cache.get_detector('set1', object) is not detector
    assert get() is not first


def test_reused_sam3_predictor_refreshes_image_and_mask(tmp_path, monkeypatch):
    import numpy as np
    from anima_app.config import AppPaths
    from anima_app.runtime.face_detailer import AnimeFaceDetailer
    images = []
    instances = []

    class Predictor:
        def __init__(self, **kwargs):
            instances.append(self)
        def set_image(self, image):
            self.image = image
            images.append(image.copy())
        def __call__(self, **kwargs):
            pixels = (self.image[:, :, 0] > 0).astype(float)
            tensor = SimpleNamespace(cpu=lambda: SimpleNamespace(numpy=lambda: pixels))
            return [SimpleNamespace(masks=SimpleNamespace(data=[tensor]))]

    monkeypatch.setitem(sys.modules, 'ultralytics.models.sam', SimpleNamespace(SAM3SemanticPredictor=Predictor))
    detailer = AnimeFaceDetailer(AppPaths(tmp_path))
    first = detailer._build_sam3_mask(np.zeros((8, 8, 3), dtype=np.uint8), (8, 8), 'cpu', ('face',))
    second = detailer._build_sam3_mask(np.full((8, 8, 3), 255, dtype=np.uint8), (8, 8), 'cpu', ('face',))
    assert len(instances) == 1 and len(images) == 2
    assert first.sum() == 0 and second.sum() == 64 * 255

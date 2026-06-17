import os

from anima_app.gpu import ensure_default_cuda_visible_devices


def test_app_specific_cuda_device_overrides_inherited_cuda_visible_devices(monkeypatch):
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "1")
    monkeypatch.setenv("ANIMA_APP_CUDA_VISIBLE_DEVICES", "0")

    assert ensure_default_cuda_visible_devices() == "0"
    assert os.environ["CUDA_VISIBLE_DEVICES"] == "0"


def test_default_cuda_device_is_used_when_no_device_is_configured(monkeypatch):
    monkeypatch.delenv("CUDA_VISIBLE_DEVICES", raising=False)
    monkeypatch.delenv("ANIMA_APP_CUDA_VISIBLE_DEVICES", raising=False)

    assert ensure_default_cuda_visible_devices() == "0"
    assert os.environ["CUDA_VISIBLE_DEVICES"] == "0"

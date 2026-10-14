"""Focused crop contracts, including durable recovery after local save failure."""
import base64
import hashlib
import io
import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw

from anima_app import server
from anima_app.config import AppPaths
from anima_app.providers import novelai
from anima_app.providers.novelai import detailer
from anima_app.providers.novelai.errors import NovelAIError
from anima_app.providers.novelai.models import INPAINT_ROUTING
from test_novelai_detailer import assets as _assets_fixture, regions, transport_recorder

assets = _assets_fixture


def manifest_for(response):
    return json.loads(Path(response["manifest_path"]).read_text())


@pytest.mark.parametrize("failed_file", ["mask", "composite"])
def test_second_mask_checkpoint_failure_returns_last_complete_pair(tmp_path, monkeypatch, assets, failed_file):
    """A composite without its mask must not replace the recoverable first pair."""
    calls = []
    monkeypatch.setattr(detailer.Detector, "detect", lambda _, source, cancelled: regions(source))
    monkeypatch.setattr(novelai.client, "_requests_transport", transport_recorder(calls))
    original_save = Image.Image.save
    failed = False

    # Mask encoding also calls save; fail only after both requests have completed.
    def fail_checkpoint_mask(image, fp, *args, **kwargs):
        nonlocal failed
        if failed_file == "mask" and len(calls) == 2 and image.mode == "L" and not failed:
            failed = True
            raise OSError("synthetic-detailer-secret disk failure")
        return original_save(image, fp, *args, **kwargs)

    monkeypatch.setattr(Image.Image, "save", fail_checkpoint_mask)
    original_write = detailer.write_verified_png

    def fail_composite(path, data):
        if failed_file == "composite" and len(calls) == 2 and path.name.endswith("-composite.png"):
            raise OSError("synthetic-detailer-secret disk failure")
        original_write(path, data)

    monkeypatch.setattr(detailer, "write_verified_png", fail_composite)
    status, response = server.handle_generate(assets, paths=AppPaths(tmp_path))
    assert status == 200, response
    assert response["stop_scheduling"] and not response["remote_outcome_unknown"]
    manifest = manifest_for(response)
    assert manifest["novelai"]["detailer_failure"]["code"] == "nai_checkpoint_failed"
    report = manifest["novelai"]["detailer"]
    assert report[0]["status"] == "edited"
    assert report[1]["status"] == "checkpoint_failed"
    assert "mask_path" not in report[1] and "composite_path" not in report[1]
    assert hashlib.sha256(Path(report[1]["remote_path"]).read_bytes()).hexdigest() == report[1]["remote_sha256"]
    with Image.open(response["output_path"]) as output:
        assert output.getpixel((30, 40)) == (128, 0, 128)
        assert output.getpixel((80, 40)) == (0, 128, 0)
    assert "synthetic-detailer-secret" not in json.dumps(manifest)


def test_first_checkpoint_failure_keeps_raw_response_and_known_outcome(tmp_path, monkeypatch, assets):
    calls = []
    monkeypatch.setattr(detailer.Detector, "detect", lambda _, source, cancelled: regions(source))
    monkeypatch.setattr(novelai.client, "_requests_transport", transport_recorder(calls))
    original_write = detailer.write_verified_png

    def fail_mask(path, data):
        if path.name.endswith("-mask.png"):
            raise OSError("synthetic-detailer-secret disk failure")
        original_write(path, data)

    monkeypatch.setattr(detailer, "write_verified_png", fail_mask)
    status, response = server.handle_generate(assets, paths=AppPaths(tmp_path))
    assert status == 502 and response["error_code"] == "nai_checkpoint_failed"
    assert response["remote_outcome_unknown"] is False and len(calls) == 1
    assert "synthetic-detailer-secret" not in json.dumps(response)
    raw = list(AppPaths(tmp_path).image_root.glob("nai-detail-*.png"))
    assert len(raw) == 1
    with Image.open(raw[0]) as saved:
        assert saved.getpixel((0, 0)) == (128, 0, 128)


@pytest.mark.parametrize("model,infill", sorted(INPAINT_ROUTING.items()))
def test_model_routing_and_per_crop_contract(tmp_path, monkeypatch, assets, model, infill):
    calls, accounts = [], []
    monkeypatch.setattr(detailer.Detector, "detect", lambda _, source, cancelled: regions(source))
    monkeypatch.setattr(novelai.client, "_requests_transport", transport_recorder(calls))

    def subscription(*_):
        accounts.append(len(calls))
        return b'{"active":true,"tier":3,"usage":{"percent":100,"isNegative":false}}'

    monkeypatch.setattr(novelai.client, "_requests_subscription_transport", subscription)
    status, response = server.handle_generate({**assets, "nai_model": model, "seed": 2**32 - 1,
                                             "nai_detailer": {"enabled": True, "steps": 50, "padding": 0, "strength": 0}},
                                            paths=AppPaths(tmp_path))
    assert status == 200, response
    assert accounts == [0, 1]
    report = manifest_for(response)["novelai"]["detailer"]
    assert [item["seed"] for item in report] == [2**32 - 1, 0]
    for item, call in zip(report, calls):
        params = call["parameters"]
        assert call["model"] == infill == item["transmitted_model"]
        assert call["action"] == "infill"
        assert params["steps"] == (14 if "-medium" in model else 28) == item["transmitted_steps"]
        if model.startswith(("nai-diffusion-4", "nai-diffusion-5")):
            assert params["img2img"] == {"strength": 0, "color_correct": True}
        else:
            assert "img2img" not in params
        assert params["inpaintImg2ImgStrength"] == 0 and params["noise"] == 0
        assert params["n_samples"] == 1 and max(params["width"], params["height"]) <= 1024
        assert item["opus_preflight"]["status"] == "verified"
        assert hashlib.sha256(Path(item["remote_path"]).read_bytes()).hexdigest() == item["remote_sha256"]
        with Image.open(io.BytesIO(base64.b64decode(params["mask"]))) as mask:
            array = np.asarray(mask)
            # Every 8x8 API cell is constant; ownership never destroys the grid.
            cells = array.reshape(mask.height // 8, 8, mask.width // 8, 8)
            assert np.all(cells == cells[:, :1, :, :1])


@pytest.mark.parametrize("cancel_after", ["account", "response"])
def test_cancel_preserves_arriving_crop_and_never_submits_next(tmp_path, monkeypatch, assets, cancel_after):
    calls = []
    cancelled = False
    monkeypatch.setattr(detailer.Detector, "detect", lambda _, source, is_cancelled: regions(source))
    record = transport_recorder(calls)

    def subscription(*_):
        nonlocal cancelled
        if cancel_after == "account":
            cancelled = True
        return b'{"active":true,"tier":3}'

    def transport(*args):
        nonlocal cancelled
        result = record(*args)
        cancelled = True
        return result

    request = novelai.request_from_payload(assets)
    if cancel_after == "account":
        with pytest.raises(NovelAIError, match="취소"):
            novelai.generate(request, paths=AppPaths(tmp_path), transport=transport, subscription_transport=subscription,
                             cancelled=lambda: cancelled)
        assert not calls
    else:
        result = novelai.generate(request, paths=AppPaths(tmp_path), transport=transport, subscription_transport=subscription,
                                  cancelled=lambda: cancelled)
        assert result.cancellation_requested and len(calls) == 1
        manifest = json.loads(result.manifest_path.read_text())
        assert manifest["novelai"]["detailer_failure"]["code"] == "generation_cancelled"
        assert [item["status"] for item in manifest["novelai"]["detailer"]] == ["edited", "cancelled"]
        with Image.open(result.output_path) as output:
            assert output.getpixel((30, 40)) == (128, 0, 128)
            assert output.getpixel((80, 40)) == (0, 128, 0)


@pytest.mark.parametrize("edge", [False, True])
def test_manual_irregular_mask_preserves_every_black_pixel_and_original_file(tmp_path, monkeypatch, assets, edge):
    root = tmp_path / "inputs/references"
    yy, xx = np.indices((128, 256))
    original = np.stack((xx % 256, (yy * 2) % 256, (xx + yy) % 256), axis=-1).astype(np.uint8)
    Image.fromarray(original).save(root / "source.png")
    source_hash = hashlib.sha256((root / "source.png").read_bytes()).hexdigest()
    mask = Image.new("L", (256, 128))
    draw = ImageDraw.Draw(mask)
    draw.ellipse((0, 0, 30, 30) if edge else (70, 30, 110, 70), fill=255)
    if not edge:
        draw.rectangle((80, 40, 90, 50), fill=0)
    mask.save(root / "mask.png")
    monkeypatch.setattr(novelai.client, "_requests_transport", transport_recorder([]))
    status, response = server.handle_generate({**assets, "operation": "focused_infill",
                                             "nai_model": "nai-diffusion-4-5-full-inpainting",
                                             "mask_image": "inputs/references/mask.png", "nai_detailer": {"padding": 16, "dilation": 4}},
                                            paths=AppPaths(tmp_path))
    assert status == 200, response
    with Image.open(response["output_path"]) as output:
        assert np.array_equal(np.asarray(output)[np.asarray(mask) == 0], original[np.asarray(mask) == 0])
        assert np.any(np.asarray(output)[np.asarray(mask) > 0] != original[np.asarray(mask) > 0])
    assert hashlib.sha256((root / "source.png").read_bytes()).hexdigest() == source_hash


def test_all_crops_validated_before_first_account_or_generation(tmp_path, monkeypatch, assets):
    source = Image.new("RGB", (256, 128))
    second = detailer.Region((0, 0, 256, 128), Image.new("L", source.size, 255))
    monkeypatch.setattr(detailer.Detector, "detect", lambda *_: [regions(source)[0], second])
    monkeypatch.setattr(novelai.client, "_requests_transport", lambda *_: pytest.fail("generation submitted"))
    monkeypatch.setattr(novelai.client, "_requests_subscription_transport", lambda *_: pytest.fail("account queried"))
    status, _ = server.handle_generate({**assets, "nai_detailer": {"enabled": True, "crop_factor": 1, "padding": 0}},
                                      paths=AppPaths(tmp_path))
    assert status == 400

import gzip
import http.client
import io
import json
import threading

import numpy as np
import pytest
from PIL import Image
from PIL.PngImagePlugin import PngInfo

from anima_app.config import AppPaths
from anima_app.providers.novelai import metadata as metadata_module
from anima_app.providers.novelai.metadata import normalize_metadata, read_image_metadata
from anima_app.server import create_http_server


def _metadata(**overrides):
    comment = dict(prompt="silver hair, 카페", uc="", width=832, height=1216,
                   steps=28, scale=0, seed=0, cfg_rescale=0, prefer_brownian=False,
                   sampler="k_euler", noise_schedule="karras", skip_cfg_above_sigma=None,
                   model_hash="DB276663", request_type="PromptGenerateRequest")
    comment.update(overrides)
    return {"Software": "NovelAI", "Source": "NovelAI Diffusion V5 DB276663", "Comment": comment}


def _image_bytes(metadata=None, *, size=(64, 64), format="PNG"):
    output = io.BytesIO()
    image = Image.new("RGBA", size, "white")
    if format == "PNG":
        info = PngInfo()
        for key, value in (metadata or {}).items():
            info.add_itxt(key, json.dumps(value, ensure_ascii=False) if isinstance(value, dict) else value)
        image.save(output, format=format, pnginfo=info)
    else:
        exif = Image.Exif()
        exif[305] = metadata["Source"]
        exif[34665] = {37510: b"ASCII\x00\x00\x00" + json.dumps(metadata["Comment"]).encode("ascii")}
        image.save(output, format=format, exif=exif)
    return output.getvalue()


def _stealth_bytes(metadata, *, payload=None):
    encoded = payload if payload is not None else gzip.compress(json.dumps(metadata).encode())
    packed = b"stealth_pngcomp" + (len(encoded) * 8).to_bytes(4, "big") + encoded
    bits = np.unpackbits(np.frombuffer(packed, dtype=np.uint8))
    pixels = np.full((128, 128, 4), 255, dtype=np.uint8)
    alpha = pixels[:, :, 3].T.copy().reshape(-1)
    alpha[:len(bits)] = 254 | bits
    pixels[:, :, 3] = alpha.reshape((128, 128)).T
    image = Image.fromarray(pixels)
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


@pytest.mark.parametrize("hash_value,expected", [
    ("DB276663", "nai-diffusion-5-curated"), ("0adf9ab7", "nai-diffusion-5-full"),
    ("657484A5", "nai-diffusion-5-full"), ("4BDE2A90", "nai-diffusion-4-5-full"),
    ("C02D4F98", "nai-diffusion-4-5-curated"), ("37442FCA", "nai-diffusion-4-full"),
    ("7ABFFA2A", "nai-diffusion-4-curated-preview"), ("C1E1DE52", "nai-diffusion-3"),
    ("C8704949", "nai-diffusion-furry-3"),
])
def test_hash_selects_model_from_comment_or_source(hash_value, expected):
    metadata = _metadata(model_hash=hash_value)
    metadata["Source"] = f"NovelAI Diffusion {hash_value}"
    assert normalize_metadata(metadata)["request"]["nai_model"] == expected
    del metadata["Comment"]["model_hash"]
    assert normalize_metadata(metadata)["request"]["nai_model"] == expected


@pytest.mark.parametrize("format", ["PNG", "WEBP"])
def test_text_and_exif_roundtrip_preserve_empty_and_zero(tmp_path, format):
    path = tmp_path / "input.image"
    path.write_bytes(_image_bytes(_metadata(), format=format))
    result = read_image_metadata(path)
    request = result["request"]
    assert request["prompt"] == "silver hair, 카페"
    assert request["negative_prompt"] == ""
    assert request["seed"] == request["cfg"] == request["nai_cfg_rescale"] == 0
    assert request["nai_prefer_brownian"] is False
    assert request["nai_variety_boost"] is False
    assert "nai_limit_opus_free" not in request
    assert result["metadata_source"] == ("png_text" if format == "PNG" else "webp_exif")


def test_alpha_only_metadata_roundtrip(tmp_path):
    path = tmp_path / "stealth.png"
    path.write_bytes(_stealth_bytes(_metadata()))
    result = read_image_metadata(path)
    assert result["metadata_source"] == "alpha"
    assert result["request"]["nai_model"] == "nai-diffusion-5-curated"


def test_alpha_decompression_is_bounded(tmp_path, monkeypatch):
    path = tmp_path / "oversize.png"
    path.write_bytes(_stealth_bytes({}, payload=gzip.compress(b" " * 4000)))
    monkeypatch.setattr(metadata_module, "MAX_METADATA_BYTES", 1000)
    with pytest.raises(ValueError, match="너무 큽니다"):
        read_image_metadata(path)


def test_corrupt_alpha_deflate_is_reported_as_invalid_metadata(tmp_path):
    # Valid gzip header, reserved DEFLATE block type, and an empty trailer.
    payload = b"\x1f\x8b\x08\x00\x00\x00\x00\x00\x00\xff\x07" + b"\x00" * 8
    path = tmp_path / "corrupt-alpha.png"
    path.write_bytes(_stealth_bytes({}, payload=payload))
    with pytest.raises(ValueError, match="숨겨진 NAI 메타데이터를 읽을 수 없습니다"):
        read_image_metadata(path)


@pytest.mark.parametrize("changes", [
    {"model_hash": "DEADBEEF"}, {"model_hash": "0ADF9AB7"},
    {"model": "nai-diffusion-5-full"}, {"model_hash": ["bad"], "model_name": {}},
])
def test_unresolved_or_conflicting_hash_requires_manual_model(changes):
    metadata = _metadata(**changes)
    if changes.get("model_hash") == "DEADBEEF":
        metadata["Source"] = "NovelAI Diffusion V5 DEADBEEF"
    if isinstance(changes.get("model_hash"), list):
        metadata["Source"] = "NovelAI Diffusion V5"
    result = normalize_metadata(metadata)
    assert "nai_model" not in result["request"]
    assert result["warnings"]


def test_v4_base_prompts_win_and_unsupported_conditions_are_visible():
    metadata = _metadata(v4_prompt={"caption": {"base_caption": "base", "char_captions": [{"char_caption": "character"}]}},
                         v4_negative_prompt={"caption": {"base_caption": "negative"}},
                         reference_strength_multiple=[0.5], sm=True, strength=0.5,
                         headers={"Authorization": "private-sentinel"}, reference_image_multiple=["private-image"])
    result = normalize_metadata(metadata)
    assert result["request"]["prompt"] == "base"
    assert result["request"]["negative_prompt"] == "negative"
    assert {"Vibe Transfer", "SMEA / DYN", "이미지 입력 / 마스크 / noise"} <= set(result["unsupported"])
    assert result["request"]["nai_characters"] == [{"prompt": "character", "negative_prompt": "", "x": 0.5, "y": 0.5}]
    assert "private-sentinel" not in json.dumps(result)
    assert "private-image" not in json.dumps(result)


@pytest.mark.parametrize("request_type,mode", [("NativeInfillingRequest", "inpaint"), ("Img2ImgRequest", "i2i")])
def test_infill_or_i2i_does_not_silently_select_t2i_model(request_type, mode):
    metadata = _metadata(model_hash="1229B44F", request_type=request_type)
    metadata["Source"] = "NovelAI Diffusion V4.5 1229B44F"
    result = normalize_metadata(metadata)
    assert result["generation_mode"] == mode
    assert result["model_hash"] == "1229B44F"
    if mode == "inpaint":
        assert result["detected_model"] == "nai-diffusion-4-5-full-inpainting"
        assert result["request"]["nai_model"] == "nai-diffusion-4-5-full-inpainting"
        assert result["request"]["operation"] == "infill"
        assert result["request"]["input_image"] == result["request"]["mask_image"] == ""
    else:
        assert result["request"]["nai_model"] == "nai-diffusion-4-5-full"
        assert result["request"]["operation"] == "img2img"


def test_variant_hash_without_mode_remains_unresolved():
    metadata = _metadata(model_hash="1229B44F")
    metadata["Source"] = "NovelAI Diffusion V4.5 1229B44F"
    del metadata["Comment"]["request_type"]
    result = normalize_metadata(metadata)
    assert result["generation_mode"] == "unknown"
    assert "nai_model" not in result["request"]
    assert any("인페인트 여부" in warning for warning in result["warnings"])


def test_explicit_inpainting_model_keeps_original_identity():
    result = normalize_metadata(_metadata(model="nai-diffusion-5-curated-inpainting"))
    assert result["generation_mode"] == "inpaint"
    assert result["detected_model"] == "nai-diffusion-5-curated-inpainting"
    assert "nai_model" not in result["request"]
    assert "nai-diffusion-5-curated-inpainting" not in result["model_candidates"]


def test_legacy_v4_alias_does_not_silently_upgrade_to_v45():
    metadata = _metadata(model_hash="5AB81C7C")
    metadata["Source"] = "NovelAI Diffusion V4 5AB81C7C"
    result = normalize_metadata(metadata)
    assert result["source_model"] == "NovelAI Diffusion V4 5AB81C7C"
    assert "nai_model" not in result["request"]
    assert any("V4.5" in warning for warning in result["warnings"])


@pytest.mark.parametrize("key,value,target", [
    ("seed", True, "seed"), ("seed", -1, "seed"), ("seed", 2**32, "seed"),
    ("steps", 0, "steps"), ("steps", 28.5, "steps"), ("scale", float("nan"), "cfg"),
    ("scale", float("inf"), "cfg"), ("scale", 10**500, "cfg"),
    ("width", 833, "width"), ("sampler", "unknown", "nai_sampler"),
    ("noise_schedule", {}, "nai_scheduler"), ("prefer_brownian", "false", "nai_prefer_brownian"),
])
def test_invalid_fields_are_not_applied(key, value, target):
    result = normalize_metadata(_metadata(**{key: value}))
    assert target not in result["request"]
    assert result["warnings"]


@pytest.mark.parametrize("body", [b"not an image", _image_bytes(), _image_bytes({"Comment": "not JSON"})])
def test_non_nai_or_invalid_images_raise(tmp_path, body):
    path = tmp_path / "input.png"
    path.write_bytes(body)
    with pytest.raises(ValueError):
        read_image_metadata(path)


def test_http_import_is_tokenless_does_not_generate_and_cleans_uploads(tmp_path, monkeypatch):
    from anima_app.providers import novelai

    monkeypatch.delenv("NAI_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("NAI_API_TOKEN", raising=False)
    def forbidden(*args, **kwargs):
        pytest.fail("Metadata import must never generate")
    monkeypatch.setattr(novelai.client, "_requests_transport", forbidden)
    paths = AppPaths(project_root=tmp_path)
    server = create_http_server("127.0.0.1", 0, paths=paths, renderer=forbidden)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        for body, expected in ((_image_bytes(_metadata()), 200), (_image_bytes(), 400), (b"bad", 400)):
            connection = http.client.HTTPConnection(*server.server_address, timeout=5)
            connection.request("POST", "/api/metadata/novelai", body=body, headers={"Content-Type": "image/png"})
            response = connection.getresponse()
            payload = json.loads(response.read())
            assert response.status == expected
            if expected == 200:
                assert payload["request"]["seed"] == 0
            else:
                assert payload["error_code"] == "nai_metadata_invalid"
                assert payload["error_detail"]["code"] == "METADATA_INPUT"
                assert payload["error_detail"]["stage"] == "metadata_import"
                assert set(payload["error_detail"]["messages"]) == {"en", "ko", "ja"}
            connection.close()
            assert not list(paths.input_root.rglob("*.upload"))
        assert not list(paths.output_root.glob("manifests/*.json"))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

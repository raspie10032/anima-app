"""Synthetic RS NAI 2.9.0 records: original conditions must never be crop conditions."""
import copy
import json

import pytest
from PIL import Image
from PIL.PngImagePlugin import PngInfo

from anima_app.library_metadata import metadata, artist_combo
from anima_app.providers.novelai import NovelAIRequest, build_payload
from anima_app.providers.novelai.images import save_webp
from anima_app.providers.novelai.metadata import normalize_metadata, read_image_metadata


def saved_request(prompt="2people, artist:original"):
    _, payload = build_payload(NovelAIRequest(
        prompt=prompt, negative_prompt="blur", width=512, height=512, seed=0,
        model="nai-diffusion-5-full", use_coords=True,
        characters=({"prompt": "red hair", "negative_prompt": "hat", "x": .2, "y": .5},
                    {"prompt": "blue hair", "negative_prompt": "ribbon", "x": .8, "y": .5})))
    return payload


def record(kind="detailer", base=True):
    result = {"version": 1, "operation": kind}
    if kind == "detailer":
        result.update(base_generation_available=base, edits=[{"request": saved_request("artist:crop_only")}])
        if base:
            result["base_generation"] = saved_request()
    else:
        result["request"] = saved_request()
    return result


def save(path, fields, fmt):
    fields = {k: json.dumps(v) if not isinstance(v, str) else v for k, v in fields.items()}
    image = Image.new("RGB", (512, 512), "navy")
    if fmt == "png":
        pnginfo = PngInfo()
        for key, value in fields.items():
            pnginfo.add_text(key, value)
        image.save(path, format="PNG", pnginfo=pnginfo)
    else:
        exif = Image.Exif()
        exif[37395] = json.dumps(fields)
        image.save(path, format="WEBP", lossless=fmt == "webp_lossless", exif=exif)


@pytest.mark.parametrize("fmt", ["png", "webp_lossless", "webp_lossy"])
@pytest.mark.parametrize("kind,base", [("generate", True), ("detailer", True), ("detailer", False)])
def test_rs_roundtrip_and_library_excludes_crop_artists(tmp_path, fmt, kind, base):
    path = tmp_path / "image"
    fields = {"rs_nai": record(kind, base), "Comment": {"prompt": "artist:crop_only", "uc": "", "model": "nai-diffusion-5-full"}}
    save(path, fields, fmt)
    result = read_image_metadata(path)
    snapshot, origin, warnings = metadata(path)
    assert origin.startswith("novelai_")
    if base:
        assert result["request"]["prompt"] == "2people, artist:original"
        assert result["request"]["seed"] == 0
        assert result["request"]["nai_characters"][1]["x"] == .8
        assert "crop_only" not in json.dumps(artist_combo(snapshot))
    else:
        assert result["request"] == {}
        assert result["can_apply"] is False
        assert not snapshot.get("prompt")
    if kind == "detailer":
        assert result["correction_history"][0]["request"]["prompt"] == "artist:crop_only"


@pytest.mark.parametrize("broken", ["{bad", {"version": 2}, {"version": True}, {"version": 1, "operation": "detailer"},
                                    {"version": 1, "operation": "detailer", "base_generation_available": True, "base_generation": []}])
def test_broken_record_does_not_fall_back_to_last_crop(broken):
    result = normalize_metadata({"rs_nai": broken, "Software": "NovelAI", "Comment": {"prompt": "last crop"}})
    assert result["can_apply"] is False
    assert result["request"] == {}


def test_legacy_marker_blocks_crop_and_private_request_data_is_not_exposed():
    fields = {"rs_detailer_regions": "{}", "Software": "NovelAI", "Comment": {"prompt": "last crop"}}
    assert normalize_metadata(fields)["request"] == {}
    current = record()
    current["base_generation"]["parameters"].update(Authorization="secret-sentinel", image="private-pixels")
    current["edits"][0]["request"]["parameters"].update(Authorization="secret-sentinel", image="private-pixels")
    result = normalize_metadata({"rs_nai": current})
    assert "secret-sentinel" not in json.dumps(result)
    assert "private-pixels" not in json.dumps(result)


@pytest.mark.parametrize("lossless", [False, True])
def test_webp_export_preserves_base_and_correction_history(tmp_path, lossless):
    source = tmp_path / "input.png"
    save(source, {"rs_nai": record()}, "png")
    before = source.read_bytes()
    target = save_webp(source, lossless=lossless, quality=90)
    assert source.read_bytes() == before
    assert read_image_metadata(target)["request"] == read_image_metadata(source)["request"]
    assert len(read_image_metadata(target)["correction_history"]) == 1


def test_generation_record_wins_over_stale_comment():
    source = record("generate")
    stale = copy.deepcopy(source["request"]["parameters"])
    stale["v4_prompt"]["caption"]["base_caption"] = "last crop"
    stale["steps"] = 1
    result = normalize_metadata({"rs_nai": source, "Comment": stale})
    assert result["request"]["prompt"] == "2people, artist:original"
    assert result["request"]["steps"] == 28

"""RS NAI node-audit parity at conversion, queue, file and diagnostic boundaries."""
import io
import json
import struct
import urllib.error
import zipfile
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest
from PIL import Image

from anima_app import server
from anima_app.config import AppPaths
from anima_app.providers import novelai
from anima_app.providers.novelai import detailer
from anima_app.providers.novelai.converters import convert_prompt
from anima_app.providers.novelai.diagnostics import collect_notices, notice
from anima_app.providers.novelai.errors import NovelAIError
from anima_app.providers.novelai.images import first_png_from_zip
import test_novelai_detailer as detailer_tests
from test_novelai_detailer import regions, transport_recorder
from test_novelai_integration import make_queue


@pytest.fixture
def assets(tmp_path, monkeypatch):
    return detailer_tests.assets.__wrapped__(tmp_path, monkeypatch)


def convert(text, source="comfyui", target="naiv4"):
    return convert_prompt({"text": text, "source": source, "target": target})


@pytest.mark.parametrize("text,source,target,expected,notice_part", [
    ("ok, (tag:o), end", "comfyui", "naiv4", "ok, end", "(tag:o)"),
    ("(hair:7)", "comfyui", "naiv4", "1.1::hair ::", "1.1로 대체"),
    ("1.2::hair::lost", "naiv4", "comfyui", "(hair:1.2)", "lost"),
    ("0::hair::, -1::coat::", "naiv4", "oldnai", "[hair, coat]", "표현할 수 없어"),
])
def test_loss_notices_name_actual_input_without_changing_node_output(text, source, target, expected, notice_part):
    result = convert(text, source, target)
    assert result["converted"] == expected
    assert notice_part in "\n".join(result["warnings"])
    assert result["original"] == text


def test_clean_conversion_clears_warnings_and_escaped_literals_survive():
    assert convert("(tag:o)")["warnings"]
    result = convert(r"artist:test, tag\(series\), (hair:1.2)")
    assert result["warnings"] == []
    assert result["converted"] == "artist:test, tag(series), 1.2::hair ::"


def test_concurrent_nested_failed_conversions_never_share_or_log_fragments(caplog):
    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(lambda i: convert(f"(private{i}:oops)"), range(40)))
    for i, result in enumerate(results):
        assert len(result["warnings"]) == 1 and f"private{i}:oops" in result["warnings"][0]
    with collect_notices() as outer:
        notice("outer")
        assert convert("(nested:o)")["warnings"]
        with pytest.raises(ValueError):
            convert("9" * 400 + "::hair::", "naiv4", "comfyui")
        notice("outer")
    assert outer == ["outer"]
    assert convert("clean")["warnings"] == []
    assert "private" not in caplog.text and "nested" not in caplog.text


def test_conversion_notices_bounded_and_deduplicated():
    result = convert(", ".join(f"(tag{i}:oops)" for i in range(100)))
    assert len(result["warnings"]) == 51 and "생략" in result["warnings"][-1]
    assert len(convert("(tag:o), (tag:o)")["warnings"]) == 1


def archive_with(entries):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        for name, data in entries:
            archive.writestr(name, data)
    return stream.getvalue()


def test_zip_metadata_and_directories_before_uppercase_png():
    png = io.BytesIO()
    Image.new("RGB", (64, 64)).save(png, format="PNG")
    archive = archive_with([("metadata.json", b"{}"), ("folder/", b""), ("folder/image.PNG", png.getvalue())])
    assert first_png_from_zip(archive) == png.getvalue()


@pytest.mark.parametrize("entries", [[], [("data.json", b"{}")], [("a.png", b"bad")],
    [("a.png", b"a"), ("b.png", b"b")]])
def test_invalid_zip_is_unknown_remote_outcome(entries):
    with pytest.raises(NovelAIError) as exc:
        first_png_from_zip(archive_with(entries))
    assert exc.value.code == "nai_response_invalid" and exc.value.unknown


def test_unsupported_zip_compression_is_a_sanitized_unknown_response():
    archive = bytearray(archive_with([("image.png", b"data")]))
    struct.pack_into("<H", archive, archive.index(b"PK\x03\x04") + 8, 99)
    struct.pack_into("<H", archive, archive.index(b"PK\x01\x02") + 10, 99)
    with pytest.raises(NovelAIError) as exc:
        first_png_from_zip(archive)
    assert exc.value.code == "nai_response_invalid" and exc.value.unknown


@pytest.mark.parametrize("target", ["source.png", "mask.png"])
def test_animated_managed_input_rejected_before_queue_or_transport(tmp_path, monkeypatch, assets, target):
    path = tmp_path / "inputs/references" / target
    Image.new("RGB", (256, 128), "white").save(path, save_all=True,
        append_images=[Image.new("RGB", (256, 128), "black")], duration=100)
    monkeypatch.setattr(novelai, "generate", lambda *a, **k: pytest.fail("provider reached"))
    request = {**assets, "operation": "infill", "nai_model": "nai-diffusion-5-full-inpainting",
               "nai_limit_opus_free": False, "mask_image": "inputs/references/mask.png"}
    queue = make_queue(tmp_path)
    try:
        status, result = queue.enqueue({"request": request})
        assert status == 400 and result["error_code"] == "generation_invalid_request"
        assert queue.list()["items"] == []
    finally:
        queue.close()


@pytest.mark.parametrize("tight,diagnostic,score,margin", [
    ({"red_hair": .12, "blue_hair": .1}, "score_below_minimum", .12, .02),
    ({"red_hair": .9, "blue_hair": .87}, "margin_below_minimum", .9, .03),
])
def test_failed_tight_retry_retains_latest_scores_and_exact_skip_reason(assets, tight, diagnostic, score, margin):
    scores = iter([[{"red_hair": .8, "blue_hair": .79}], [tight]])
    tagger = SimpleNamespace(score=lambda images: next(scores))
    request = novelai.request_from_payload({**assets,
        "nai_characters": [{"prompt": "red hair"}, {"prompt": "blue hair"}],
        "nai_detailer": {"enabled": True, "matching": "wd14", "mode": "first"}})
    source = Image.new("RGB", (256, 128))
    _, _, _, report = detailer.plan(source, regions(source), request, tagger)
    first, second = report
    assert first["status"] == "skipped" and first["character"] is None
    assert first["score"] == pytest.approx(score) and first["margin"] == pytest.approx(margin)
    assert first["diagnostic"] == diagnostic and first["tight_crop_retried"]
    assert second["diagnostic"] == "region_limit" and not second["tight_crop_retried"]
    assert all(row["explanation"] for row in report)


def test_preview_manifest_png_and_api_preserve_skip_diagnostics(tmp_path, monkeypatch, assets):
    monkeypatch.setattr(detailer, "preflight", lambda *a, **k: None)
    monkeypatch.setattr(detailer.Detector, "detect", lambda _, source, cancelled: regions(source))
    from anima_app.providers.novelai.wd_tagger import WDTagger
    monkeypatch.setattr(WDTagger, "score", lambda _, images: [{"red_hair": .15, "blue_hair": .1} for _ in images])
    monkeypatch.setattr(novelai.client, "_requests_transport", lambda *a: pytest.fail("transport reached"))
    payload = {**assets, "nai_model": "nai-diffusion-5-curated",
               "nai_characters": [{"prompt": "red hair"}, {"prompt": "blue hair"}],
               "nai_detailer": {"enabled": True, "preview_only": True, "matching": "wd14"}}
    status, response = server.handle_generate(payload, paths=AppPaths(tmp_path))
    assert status == 200 and response["status"] == "previewed"
    manifest = json.loads(AppPaths(tmp_path).manifest_root.joinpath(response["manifest_name"]).read_text())
    assert response["detailer_regions"] == manifest["novelai"]["detailer"]
    assert "모든 검출 영역" in " ".join(response["warnings"])
    assert "V4.5 Curated" in " ".join(response["warnings"])
    assert "좁은 크롭" in " ".join(response["warnings"])
    with Image.open(response["output_path"]) as image:
        assert json.loads(image.info["anima_app_detailer_regions"]) == response["detailer_regions"]


def test_no_detections_notice_does_not_claim_no_base_request(tmp_path, monkeypatch, assets):
    calls = []
    monkeypatch.setattr(novelai.client, "_requests_transport", transport_recorder(calls))
    monkeypatch.setattr(detailer.Detector, "detect", lambda *a: [])
    status, response = server.handle_generate({**assets, "operation": "generate", "input_image": ""}, paths=AppPaths(tmp_path))
    assert status == 200 and len(calls) == 1
    assert any("디테일러 NAI 요청은 보내지 않았습니다" in msg for msg in response["warnings"])
    assert response["detailer_regions"] == []


def test_eroded_mask_reports_empty_and_never_sends(tmp_path, monkeypatch, assets):
    calls = []
    monkeypatch.setattr(novelai.client, "_requests_transport", transport_recorder(calls))
    def detect(_, source, cancelled):
        mask = Image.new("L", source.size)
        mask.putpixel((30, 40), 255)
        return [detailer.Region((20, 30, 40, 50), mask)]
    monkeypatch.setattr(detailer.Detector, "detect", detect)
    status, response = server.handle_generate({**assets,
        "nai_detailer": {"enabled": True, "dilation": -64, "padding": 0}}, paths=AppPaths(tmp_path))
    assert status == 200 and calls == []
    assert response["detailer_regions"][0]["diagnostic"] == "empty_mask"
    assert any("수정할 픽셀" in msg for msg in response["warnings"])


def test_429_delay_and_curated_fallback_recorded_on_actual_crop(tmp_path, monkeypatch, assets):
    now, attempts = [100.0], []
    coordinator = novelai.client.RequestCoordinator(lambda: now[0])
    monkeypatch.setattr(novelai.client, "_request_coordinator", coordinator)
    monkeypatch.setattr(detailer.Detector, "detect", lambda _, source, cancelled: regions(source)[:1])
    recorder = transport_recorder([])
    def transport(url, headers, body, timeout):
        attempts.append(json.loads(body))
        if len(attempts) == 1:
            raise urllib.error.HTTPError(url, 429, "private-server-detail", {"Retry-After": "999"}, None)
        return recorder(url, headers, body, timeout)
    result = novelai.generate(novelai.request_from_payload({**assets, "nai_model": "nai-diffusion-5-curated"}),
        paths=AppPaths(tmp_path), transport=transport, sleep=lambda delay: now.__setitem__(0, now[0] + delay))
    manifest = json.loads(result.manifest_path.read_text())
    assert len(attempts) == 2 and attempts[0] == attempts[1]
    assert attempts[1]["model"] == "nai-diffusion-4-5-curated-inpainting"
    row = manifest["novelai"]["detailer"][0]
    assert row["retry_count"] == 1
    assert row["rate_limit_events"] == [{"attempt": 1, "status": 429, "wait_seconds": 60, "retry_scheduled": True}]
    assert any("영역 1: HTTP 429로 60초" in msg for msg in manifest["warnings"])
    assert "private-server-detail" not in json.dumps(manifest)


def test_same_second_generation_keeps_both_pngs_and_manifests(tmp_path, monkeypatch, assets):
    monkeypatch.setattr("anima_app.output_names.time", SimpleNamespace(time=lambda: 1000))
    monkeypatch.setattr(novelai.client, "_requests_transport", transport_recorder([]))
    request = novelai.request_from_payload({**assets, "operation": "generate", "input_image": "", "nai_detailer": {}})
    results = [novelai.generate(request, paths=AppPaths(tmp_path)) for _ in range(2)]
    assert results[0].output_path != results[1].output_path
    assert results[0].manifest_path != results[1].manifest_path
    assert all(r.output_path.is_file() and r.manifest_path.is_file() for r in results)

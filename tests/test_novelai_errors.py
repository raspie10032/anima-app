"""Cause/stage diagnostics through real app boundaries, all network synthetic."""
import errno
import io
import json
import threading
import urllib.error
from concurrent.futures import ThreadPoolExecutor

import pytest
import requests
from PIL import Image

from anima_app import server
from anima_app.config import AppPaths
from anima_app.providers import novelai
from anima_app.providers.novelai import client, detailer, service, wd_tagger
from anima_app.providers.novelai.errors import MESSAGES, NovelAIError, diagnosed, explain, mark_stage, redact
from anima_app.providers.novelai.tagger_setup import TaggerSetup
from test_novelai_detailer import assets, regions, transport_recorder  # noqa: F401
from test_novelai_integration import make_queue, nai_request, png_archive, wait_terminal


@pytest.fixture(autouse=True)
def isolated(monkeypatch, nai_mock_account):
    monkeypatch.setenv("NAI_ACCESS_TOKEN", "synthetic-diagnostics-secret")
    monkeypatch.setenv("NAI_API_TOKEN", "synthetic-secondary-secret")
    monkeypatch.setenv("HF_TOKEN", "synthetic-hub-secret")
    monkeypatch.setattr(client, "REQUEST_INTERVAL_SECONDS", 0)
    monkeypatch.setattr(requests.sessions.Session, "request", lambda *a, **k: pytest.fail("Live HTTP forbidden"))


def error_payload(status, body=None):
    body = body or {"message": "expired synthetic-diagnostics-secret", "error": "token=another-secret",
                    "authorization": "private-header", "input": "private-prompt"}
    return urllib.error.HTTPError(client.GENERATE_IMAGE_URL, status, "unsafe raw exception", {"Retry-After": "0"},
                                  io.BytesIO(json.dumps(body).encode()))


@pytest.mark.parametrize("status,cause,count", [(400, "NAI_REQUEST", 1), (401, "NAI_AUTH", 1),
    (402, "NAI_PAYMENT", 1), (403, "NAI_FORBIDDEN", 1), (404, "NAI_HTTP", 1),
    (422, "NAI_REQUEST", 1), (429, "NAI_RATE_LIMIT", 2), (503, "NAI_SERVER", 1)])
def test_http_cause_status_body_and_retry_policy(status, cause, count):
    calls = []
    def transport(*args):
        calls.append(args)
        raise error_payload(status)
    with pytest.raises(NovelAIError) as raised:
        client.post_json(client.GENERATE_IMAGE_URL, token="synthetic-diagnostics-secret", payload={},
                         transport=transport, sleep=lambda _: None)
    result = raised.value.payload()
    detail = result["error_detail"]
    assert len(calls) == count
    assert (detail["code"], detail["stage"], detail["http_status"]) == (cause, "generation", status)
    assert "Server message: expired [redacted]" in detail["details"]
    assert "unsafe raw" not in detail["details"]
    for secret in ("synthetic-diagnostics-secret", "another-secret", "private-header", "private-prompt"):
        assert secret not in json.dumps(result)
    assert result["remote_outcome_unknown"] == (status >= 500)
    assert set(detail["messages"]) == {"en", "ko", "ja"}


def test_requests_error_and_explicit_boundary_token_are_masked():
    response = requests.Response()
    response.status_code = 403
    response._content = b'{"message":"Bearer special-boundary-secret", "error":"special-boundary-secret"}'
    def transport(*args):
        raise requests.HTTPError("private raw", response=response)
    with pytest.raises(NovelAIError) as caught:
        client.post_json(client.GENERATE_IMAGE_URL, token="special-boundary-secret", payload={}, transport=transport)
    assert "special-boundary-secret" not in json.dumps(caught.value.payload())
    assert caught.value.cause == "NAI_FORBIDDEN"


@pytest.mark.parametrize("body", [{"message": "<html>secret</html>"}, {"error": "x" * 17000},
                                       {"message": {"headers": "secret"}}, ["secret"]])
def test_server_body_is_bounded_text_only(body):
    def transport(*args):
        raise error_payload(400, body)
    with pytest.raises(NovelAIError) as caught:
        client.post_json(client.GENERATE_IMAGE_URL, token="synthetic-diagnostics-secret", payload={}, transport=transport)
    details = caught.value.payload()["error_detail"]["details"]
    assert len(details) <= 3000 and "secret" not in details and "<html>" not in details


@pytest.mark.parametrize("exc,cause", [(requests.exceptions.SSLError("private"), "NAI_TLS"),
    (requests.Timeout("private"), "NAI_TIMEOUT"), (requests.ConnectionError("private"), "NAI_CONNECTION")])
def test_ambiguous_network_outcome_is_not_retried(exc, cause):
    calls = []
    def transport(*args):
        calls.append(1)
        raise exc
    with pytest.raises(NovelAIError) as caught:
        client.post_json(client.GENERATE_IMAGE_URL, token="test", payload={}, transport=transport)
    assert caught.value.cause == cause and caught.value.unknown and len(calls) == 1


@pytest.mark.parametrize("status,cause", [(401, "NAI_AUTH"), (429, "SUBSCRIPTION_CHECK"), (503, "SUBSCRIPTION_CHECK")])
def test_subscription_failure_is_known_and_prevents_image_submission(status, cause):
    def subscription(*args):
        raise error_payload(status)
    with pytest.raises(NovelAIError) as caught:
        client.post_json(client.GENERATE_IMAGE_URL, token="test", payload=novelai.build_payload(novelai.NovelAIRequest(prompt="test"))[1],
                         limit_opus_free=True, subscription_transport=subscription,
                         transport=lambda *args: pytest.fail("Image submitted"))
    assert caught.value.cause == cause and caught.value.stage == "subscription" and not caught.value.unknown
    assert caught.value.http_status == status


def test_vibe_payment_names_actual_stage():
    def transport(*args):
        raise error_payload(402)
    with pytest.raises(NovelAIError) as caught:
        client.post_json("https://image.novelai.net/ai/encode-vibe", token="test", payload={}, transport=transport)
    assert (caught.value.cause, caught.value.stage) == ("VIBE_PAYMENT", "vibe_encoding")


@pytest.mark.parametrize("error,cause", [(MemoryError("private"), "MEMORY"),
    (type("OutOfMemoryError", (RuntimeError,), {})("private"), "MEMORY"),
    (OSError(errno.ENOSPC, "private"), "DISK_FULL"), (PermissionError("private"), "FILE_PERMISSION"),
    (FileNotFoundError("private"), "FILE_MISSING"), (ModuleNotFoundError("private"), "DEPENDENCY")])
def test_concrete_resource_failures_override_download_context(error, cause):
    result = explain(error, stage="tagger_download", fallback="tagger_download").payload()
    assert result["error_detail"]["code"] == cause
    assert "private" not in json.dumps(result) and not result["remote_outcome_unknown"]


def test_redaction_cyclic_chain_and_idempotent_context():
    source = PermissionError("unlabelled private token")
    outer = RuntimeError("another private token")
    outer.__cause__, source.__cause__ = source, outer
    error = explain(outer, stage="tagger_download", fallback="tagger_download")
    assert error.cause == "FILE_PERMISSION" and len(error.details) < 3000
    assert explain(error, stage="generation") is error
    assert "private token" not in json.dumps(error.payload())
    assert redact("token=bad authorization: bad2 Bearer bad3 " + "a" * 180) == (
        "token=[redacted] authorization: [redacted] Bearer [redacted] [long data omitted]")
    assert "secret" not in redact("synthetic-secondary-secret synthetic-hub-secret")


def test_stages_are_concurrent_and_nested_context_local():
    barrier = threading.Barrier(2)
    @diagnosed("validation")
    def run(stage):
        mark_stage(stage)
        barrier.wait(2)
        raise OSError(errno.ENOSPC, "private")
    def capture(stage):
        try:
            run(stage)
        except NovelAIError as exc:
            return exc.stage
    with ThreadPoolExecutor(2) as pool:
        assert list(pool.map(capture, ["output_save", "tagger_download"])) == ["output_save", "tagger_download"]


@pytest.mark.parametrize("overrides,cause", [({"nai_model": "wrong"}, "MODEL"),
    ({"nai_model": "nai-diffusion-3", "nai_characters": [{"prompt": "a"}]}, "CHARACTER_MODEL"),
    ({"operation": "wrong"}, "REQUEST_INPUT"), ({"prompt": 123}, "REQUEST_INPUT"),
    ({"width": 0}, "REQUEST_INPUT"), ({"operation": "img2img", "nai_limit_opus_free": False}, "IMAGE_INPUT"),
    ({"operation": "infill", "nai_model": "nai-diffusion-5-full-inpainting"}, "MASK_INPUT"),
    ({"nai_model": "nai-diffusion-4-5-full", "nai_characters": [{"prompt": "a"}] * 7}, "CHARACTER_LIMIT")])
def test_validation_cause_is_returned_by_queue_before_transport(tmp_path, overrides, cause):
    queue = make_queue(tmp_path)
    try:
        status, result = queue.enqueue({"request": {**nai_request(), **overrides}})
        assert status == 400 and result["error_detail"]["code"] == cause
        assert not result["remote_outcome_unknown"]
        assert not queue.list()["items"]
    finally:
        queue.close()


def test_save_disk_full_is_known_after_one_remote_image(tmp_path, monkeypatch):
    calls = []
    def transport(*args):
        calls.append(1)
        return png_archive()
    def save(*args):
        raise OSError(errno.ENOSPC, "secret local path")
    monkeypatch.setattr(client, "_requests_transport", transport)
    monkeypatch.setattr(service, "write_verified_png", save)
    status, result = server.handle_generate(nai_request(), paths=AppPaths(tmp_path))
    assert status == 502 and len(calls) == 1 and not result["remote_outcome_unknown"]
    assert (result["error_detail"]["code"], result["error_detail"]["stage"]) == ("DISK_FULL", "output_save")
    assert "secret local path" not in json.dumps(result)


def test_timeout_queue_stops_and_retains_localizable_result(tmp_path, monkeypatch):
    calls = []
    def transport(*args):
        calls.append(1)
        raise requests.Timeout("secret")
    monkeypatch.setattr(client, "_requests_transport", transport)
    queue = make_queue(tmp_path)
    try:
        status, result = queue.enqueue({"request": nai_request(), "infinite": True})
        assert status == 202
        job = wait_terminal(queue, result["jobs"][0]["id"])
        assert job["status"] == "failed" and len(calls) == 1 and len(queue.list()["items"]) == 1
        assert job["result"]["error_detail"]["code"] == "NAI_TIMEOUT"
        assert job["result"]["remote_outcome_unknown"]
    finally:
        queue.close()


def test_partial_error_round_trips_manifest_and_png(tmp_path, monkeypatch, assets):  # noqa: F811 -- shared fixture
    calls = []
    monkeypatch.setattr(detailer.Detector, "detect", lambda _, source, cancelled: regions(source))
    monkeypatch.setattr(client, "_requests_transport", transport_recorder(calls, fail_at=2))
    status, result = server.handle_generate(assets, paths=AppPaths(tmp_path))
    assert status == 200 and result["stop_scheduling"]
    manifest = json.loads(next(AppPaths(tmp_path).manifest_root.glob("*.json")).read_text())
    detail = result["detailer_failure"]
    assert manifest["novelai"]["detailer_failure"] == detail
    assert detail["error_detail"]["stage"] == "detailer"
    with Image.open(result["output_path"]) as image:
        failure = json.loads(image.info["anima_app_detailer_regions"])[1]["failure"]
    assert failure == result["detailer_regions"][1]["failure"]
    assert failure["error_detail"]["messages"]["ja"][0] == MESSAGES["ja"]["NAI_TIMEOUT"][0]


def test_tagger_download_disk_failure_and_recovery(tmp_path, monkeypatch):
    def hub(*args, **kwargs):
        raise OSError(errno.ENOSPC, "private-token")
    monkeypatch.setattr(wd_tagger, "check_dependencies", lambda *_: (None, hub, None, None, None))
    setup = TaggerSetup(tmp_path, threading.Lock())
    setup.start({})
    setup._thread.join(3)
    result = setup.snapshot()["job"]
    assert result["status"] == "failed" and result["error_code"] == "tagger_download"
    assert result["error_detail"]["code"] == "DISK_FULL"
    assert result["error_detail"]["stage"] == "tagger_download"
    assert "private-token" not in json.dumps(result)
    monkeypatch.setattr(wd_tagger.WDTagger, "prepare", lambda *a, **k: None)
    setup.start({})
    setup._thread.join(3)
    assert setup.snapshot()["job"]["status"] == "ready"
    assert "error_detail" not in setup.snapshot()["job"]


def test_catalog_has_all_source_causes_and_no_comfy_node_ui_instructions():
    # Source: 4de914676de8ca313b8389f4303754045a6a9cfb web/error_messages.json.
    original = set("""CHARACTER_INPUT CHARACTER_LIMIT CHARACTER_MODEL DEPENDENCY DETAIL_MODE
        DISK_FULL FILE_MISSING FILE_PERMISSION FOCUSED_CROP FREE_CONDITIONS IMAGE_INPUT
        IMAGE_RESPONSE MASK_EMPTY MASK_INPUT MATCHING_INPUT MEMORY MODEL NAI_AUTH NAI_CONNECTION
        NAI_FORBIDDEN NAI_HTTP NAI_PAYMENT NAI_RATE_LIMIT NAI_REQUEST NAI_SERVER NAI_TIMEOUT NAI_TLS
        OPUS_REQUIRED PAID_BLOCKED PRECISE_MODEL REFERENCE_BOTH REFERENCE_INPUT SUBSCRIPTION_CHECK
        TAGGER_DEPENDENCY TAGGER_DOWNLOAD TAGGER_MODEL TAGGER_SETTINGS TOKEN_MISSING UNKNOWN
        V5_ALLOWANCE VIBE_CACHE VIBE_INPAINT VIBE_MODEL VIBE_PAYMENT VIBE_RESPONSE""".split())
    expected = set(MESSAGES["en"])
    assert len(original) == 45
    assert original <= expected
    for locale in ("en", "ko", "ja"):
        assert set(MESSAGES[locale]) == expected
        for pair in MESSAGES[locale].values():
            assert len(pair) == 2 and all(isinstance(item, str) and item.strip() for item in pair)
        assert "ComfyUI" not in json.dumps(MESSAGES[locale], ensure_ascii=False)

import copy
import io
import json
import threading
import time
import urllib.error
import zipfile
from concurrent.futures import ThreadPoolExecutor
from email.utils import formatdate

import pytest
import requests
from PIL import Image

from anima_app import server
from anima_app.config import AppPaths
from anima_app.providers import novelai
from anima_app.providers.novelai import client
from anima_app.providers.novelai.eligibility import validate_opus_free_payload, verify_opus_state
from anima_app.providers.novelai.errors import NovelAIError
from anima_app.providers.novelai.models import GENERATE_IMAGE_URL, SUBSCRIPTION_URL


class Clock:
    def __init__(self):
        self.now = 100.0
        self.delays = []

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.delays.append(seconds)
        self.now += seconds


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def forbidden(*_args, **_kwargs):
        pytest.fail("Live HTTP is forbidden in account/spacing tests")

    monkeypatch.setattr(requests, "get", forbidden)
    monkeypatch.setattr(requests, "post", forbidden)


@pytest.fixture
def clock(monkeypatch):
    clock = Clock()
    monkeypatch.setattr(client, "_request_coordinator", client.RequestCoordinator(clock.monotonic))
    return clock


def payload(model="nai-diffusion-5-curated"):
    return novelai.build_payload(novelai.NovelAIRequest(prompt="flower", width=64, height=64, model=model))[1]


def account(**changes):
    return {"active": True, "tier": 3, "usage": {"percent": 2, "isNegative": False}, **changes}


def post(clock, **options):
    return client.post_json(GENERATE_IMAGE_URL, token="synthetic-secret", payload=payload(),
                            sleep=clock.sleep, **options)


@pytest.mark.parametrize("state,code", [
    (None, "nai_opus_ineligible"), ([], "nai_opus_ineligible"),
    ({}, "nai_opus_ineligible"), (account(active=False), "nai_opus_ineligible"),
    (account(active=1), "nai_opus_ineligible"), (account(tier=2), "nai_opus_ineligible"),
    (account(tier="3"), "nai_opus_ineligible"), (account(tier=3.0), "nai_opus_ineligible"),
    (account(usage=None), "nai_opus_v5_allowance_low"),
    (account(usage={}), "nai_opus_v5_allowance_low"),
    (account(usage={"percent": 1, "isNegative": False}), "nai_opus_v5_allowance_low"),
    (account(usage={"percent": 100, "isNegative": True}), "nai_opus_v5_allowance_low"),
    (account(usage={"percent": 100, "isNegative": 0}), "nai_opus_v5_allowance_low"),
    (account(usage={"percent": "100", "isNegative": False}), "nai_opus_v5_allowance_low"),
    (account(usage={"percent": 100.0, "isNegative": False}), "nai_opus_v5_allowance_low"),
    (account(usage={"percent": True, "isNegative": False}), "nai_opus_v5_allowance_low"),
])
def test_unverifiable_entitlement_blocks_before_post(clock, state, code):
    with pytest.raises(NovelAIError) as failure:
        post(clock, limit_opus_free=True, subscription_transport=lambda *_args: json.dumps(state).encode(),
             transport=lambda *_args: pytest.fail("ineligible generation submitted"))
    assert failure.value.code == code
    assert failure.value.unknown is False
    assert not client._request_coordinator.lock.locked()


@pytest.mark.parametrize("percent", [2, 100, 130])
def test_v5_preflight_whitelists_safe_summary_and_runs_under_lock(clock, percent):
    calls, audit = [], {}

    def subscription(url, headers, timeout):
        assert client._request_coordinator.lock.locked()
        assert url == SUBSCRIPTION_URL
        assert headers == {"Authorization": "Bearer synthetic-secret"}
        assert timeout == 30
        calls.append("get")
        return json.dumps(account(usage={"percent": percent, "isNegative": False},
                                  access_token="synthetic-secret", private_body="private-data")).encode()

    def transport(*_args):
        assert client._request_coordinator.lock.locked()
        calls.append("post")
        return b"result"

    assert post(clock, limit_opus_free=True, subscription_transport=subscription,
                transport=transport, audit=audit) == b"result"
    assert calls == ["get", "post"]
    assert audit["opus_preflight"] == {"status": "verified", "active": True, "tier": 3,
                                       "v5_remaining_percent": percent, "v5_min_remaining_percent": 2}
    assert "synthetic-secret" not in json.dumps(audit)
    assert "private-data" not in json.dumps(audit)


@pytest.mark.parametrize("model", sorted(model for model in novelai.MODEL_IDS if not model.startswith("nai-diffusion-5")))
def test_older_models_need_opus_but_not_v5_usage(model):
    assert verify_opus_state(account(usage=None), model) == {"status": "verified", "active": True, "tier": 3}


@pytest.mark.parametrize("response", [b"not-json private-data", b"\xff", b"x" * (1024 * 1024 + 1), "not bytes"])
def test_malformed_get_blocks_known_outcome_and_sanitizes(clock, response):
    with pytest.raises(NovelAIError) as failure:
        post(clock, limit_opus_free=True, subscription_transport=lambda *_args: response,
             transport=lambda *_args: pytest.fail("post submitted"))
    assert failure.value.code == "nai_opus_check_failed"
    assert failure.value.unknown is False
    assert "private-data" not in json.dumps(failure.value.payload())


@pytest.mark.parametrize("error", [
    TimeoutError("synthetic-secret"), requests.ConnectionError("synthetic-secret"),
    urllib.error.HTTPError(SUBSCRIPTION_URL, 401, "synthetic-secret", {}, None),
    urllib.error.HTTPError(SUBSCRIPTION_URL, 429, "synthetic-secret", {}, None),
])
def test_get_failure_never_retries_or_posts(clock, error):
    calls = []

    def subscription(*_args):
        calls.append("get")
        raise error

    with pytest.raises(NovelAIError) as failure:
        post(clock, limit_opus_free=True, subscription_transport=subscription,
             transport=lambda *_args: pytest.fail("post submitted"))
    assert calls == ["get"]
    assert failure.value.code == "nai_opus_check_failed"
    assert failure.value.unknown is False
    assert "synthetic-secret" not in str(failure.value)


@pytest.mark.parametrize("edit", [
    {"model": "unknown"}, {"action": "infill"}, {"action": "img2img"},
    {"parameters": {"image": "secret-base64"}}, {"parameters": {"reference_image_multiple": []}},
    {"parameters": {"director_reference_images": []}}, {"parameters": {"n_samples": 2}},
    {"parameters": {"n_samples": True}}, {"parameters": {"steps": 29}},
    {"parameters": {"width": 2048, "height": 2048}}, {"image": "secret-base64"},
])
def test_payload_guard_precedes_all_network_calls(clock, edit):
    data = copy.deepcopy(payload())
    for name, value in edit.items():
        if name == "parameters":
            data[name].update(value)
        else:
            data[name] = value
    with pytest.raises(NovelAIError, match="Opus"):
        client.post_json(GENERATE_IMAGE_URL, token="synthetic-secret", payload=data, limit_opus_free=True)
    assert not client._request_coordinator.lock.locked()


def test_guard_accepts_all_current_t2i_models():
    for model in novelai.MODEL_IDS:
        validate_opus_free_payload(payload(model))


def test_paid_mode_skips_account_preflight_but_still_obeys_spacing(clock):
    starts = []

    def transport(*_args):
        starts.append(clock.now)
        clock.now += 7
        return b"result"

    for _ in range(2):
        post(clock, transport=transport, limit_opus_free=False,
             subscription_transport=lambda *_args: pytest.fail("paid mode preflight"))
    assert starts == pytest.approx([100, 109])
    assert sum(clock.delays) == pytest.approx(2)


def test_retry_rechecks_allowance_and_blocks_if_it_falls(clock):
    calls = []

    def subscription(*_args):
        calls.append("get")
        return json.dumps(account(usage={"percent": 2 if len(calls) == 1 else 1, "isNegative": False})).encode()

    def transport(*_args):
        calls.append("post")
        raise urllib.error.HTTPError(GENERATE_IMAGE_URL, 429, "private-data", {"Retry-After": "0"}, None)

    with pytest.raises(NovelAIError) as failure:
        post(clock, transport=transport, subscription_transport=subscription, limit_opus_free=True)
    assert failure.value.code == "nai_opus_v5_allowance_low"
    assert calls == ["get", "post", "get"]
    assert sum(clock.delays) == pytest.approx(2)


def test_each_429_attempt_has_preflight_spacing_and_bounded_retry(clock):
    calls, audit = [], {}

    def subscription(*_args):
        calls.append(("get", clock.now))
        return json.dumps(account()).encode()

    def transport(*_args):
        calls.append(("post", clock.now))
        clock.now += 5
        raise urllib.error.HTTPError(GENERATE_IMAGE_URL, 429, "private-data", {"Retry-After": "3"}, None)

    with pytest.raises(NovelAIError) as failure:
        post(clock, transport=transport, subscription_transport=subscription, limit_opus_free=True, audit=audit)
    assert calls == [("get", 100), ("post", 100), ("get", 108), ("post", 108)]
    assert failure.value.code == "nai_rate_limited"
    assert audit["retry_count"] == 1
    assert client._request_coordinator.next_request_at == pytest.approx(116)
    assert not client._request_coordinator.lock.locked()
    assert post(clock, transport=lambda *_args: b"next explicit request") == b"next explicit request"
    assert clock.now == pytest.approx(116)


@pytest.mark.parametrize("failure", [TimeoutError("private-data"), requests.ConnectionError("private-data")])
def test_failed_generation_counts_toward_cooldown_without_resubmission(clock, failure):
    starts = []

    def transport(*_args):
        starts.append(clock.now)
        clock.now += 4
        if len(starts) == 1:
            raise failure
        return b"result"

    with pytest.raises(NovelAIError) as result:
        post(clock, transport=transport)
    assert result.value.unknown is True
    assert len(starts) == 1
    assert post(clock, transport=transport) == b"result"
    assert starts == pytest.approx([100, 106])


@pytest.mark.parametrize("point", ["lock", "cooldown", "subscription"])
def test_cancel_before_submission_releases_lock_and_never_posts(clock, point):
    cancelled = threading.Event()
    coordinator = client._request_coordinator
    if point == "lock":
        coordinator.lock.acquire()
        cancelled.set()
    elif point == "cooldown":
        coordinator.next_request_at = clock.now + 2

    def sleep(delay):
        clock.sleep(delay)
        cancelled.set()

    def subscription(*_args):
        cancelled.set()
        return json.dumps(account()).encode()

    try:
        with pytest.raises(NovelAIError) as failure:
            client.post_json(GENERATE_IMAGE_URL, token="synthetic-secret", payload=payload(),
                             cancelled=cancelled.is_set, sleep=sleep, limit_opus_free=True,
                             subscription_transport=subscription,
                             transport=lambda *_args: pytest.fail("cancelled post submitted"))
        assert failure.value.code == "generation_cancelled"
        assert coordinator.lock.locked() is (point == "lock")
    finally:
        if coordinator.lock.locked():
            coordinator.lock.release()


def test_concurrent_provider_instances_share_lock_and_post_completion_spacing(monkeypatch):
    coordinator = client.RequestCoordinator()
    monkeypatch.setattr(client, "_request_coordinator", coordinator)
    # A real-clock concurrency check with a scaled interval; exact 2s is tested above.
    monkeypatch.setattr(client, "REQUEST_INTERVAL_SECONDS", .03)
    events = []
    entered, release = threading.Event(), threading.Event()

    def subscription(*_args):
        assert coordinator.lock.locked()
        events.append(("get", time.monotonic()))
        return json.dumps(account()).encode()

    def transport(*_args):
        assert coordinator.lock.locked()
        events.append(("start", time.monotonic()))
        entered.set()
        assert release.wait(5)
        events.append(("finish", time.monotonic()))
        return b"result"

    def submit():
        return client.post_json(GENERATE_IMAGE_URL, token="synthetic-secret", payload=payload(),
                                limit_opus_free=True, transport=transport, subscription_transport=subscription)

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(submit)
        assert entered.wait(5)
        second = pool.submit(submit)
        try:
            assert not second.done()
        finally:
            release.set()
        assert first.result(5) == second.result(5) == b"result"
    assert [kind for kind, _ in events] == ["get", "start", "finish", "get", "start", "finish"]
    assert events[3][1] - events[2][1] >= .03


def test_real_get_transport_bounds_disables_redirects_and_closes_response(monkeypatch):
    closed = []

    class Response:
        status_code = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            closed.append(True)

        def raise_for_status(self):
            pass

        def iter_content(self, chunk_size):
            yield b"x" * (client.MAX_SUBSCRIPTION_BYTES + 1)

    def get(url, **options):
        assert url == SUBSCRIPTION_URL
        assert options["allow_redirects"] is False
        assert options["stream"] is True
        assert options["timeout"] == (10, 30)
        return Response()

    monkeypatch.setattr(requests, "get", get)
    with pytest.raises(ValueError, match="oversized"):
        client._requests_subscription_transport(SUBSCRIPTION_URL, {}, 30)
    assert closed == [True]


def test_retry_after_http_date_support(monkeypatch):
    monkeypatch.setattr(client.time, "time", lambda: 1000)
    error = urllib.error.HTTPError(GENERATE_IMAGE_URL, 429, "rate limit",
                                   {"Retry-After": formatdate(1007, usegmt=True)}, None)
    assert client._retry_delay(error) == 7


def test_dry_run_marks_unchecked_and_success_records_only_verified_summary(tmp_path, monkeypatch, clock):
    monkeypatch.setenv("NAI_ACCESS_TOKEN", "synthetic-secret")
    request = novelai.NovelAIRequest(prompt="flower", width=64, height=64)
    dry = novelai.generate(request, paths=AppPaths(tmp_path), dry_run=True)
    assert json.loads(dry.manifest_path.read_text())["novelai"]["opus_preflight"] == {"status": "not_checked"}
    png, zipped = io.BytesIO(), io.BytesIO()
    Image.new("RGB", (64, 64), "purple").save(png, format="PNG")
    with zipfile.ZipFile(zipped, "w") as archive:
        archive.writestr("image.png", png.getvalue())
    result = novelai.generate(request, paths=AppPaths(tmp_path), transport=lambda *_args: zipped.getvalue(),
                              subscription_transport=lambda *_args: json.dumps(account(secret="private-data")).encode(),
                              sleep=clock.sleep)
    manifest = result.manifest_path.read_text()
    assert json.loads(manifest)["novelai"]["opus_preflight"]["v5_remaining_percent"] == 2
    assert "synthetic-secret" not in manifest
    assert "private-data" not in manifest


def test_ineligible_infinity_job_fails_without_scheduling_or_post(tmp_path, monkeypatch, clock):
    monkeypatch.setenv("NAI_ACCESS_TOKEN", "synthetic-secret")
    calls = []

    def subscription(*_args):
        calls.append("get")
        return json.dumps(account(usage={"percent": 1, "isNegative": False})).encode()

    monkeypatch.setattr(client, "_requests_subscription_transport", subscription)
    queue = server.JobQueue(paths=AppPaths(tmp_path), renderer=None, default_dry_run=False,
                            progress_store=server.ProgressStore(), generation_lock=threading.Lock())
    try:
        status, batch = queue.enqueue({"request": {"provider": "novelai", "prompt": "flower", "width": 64,
                                                  "height": 64}, "infinite": True})
        assert status == 202
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            _, job = queue.get(batch["jobs"][0]["id"])
            if job["status"] == "failed":
                break
            time.sleep(.01)
        assert job["status"] == "failed"
        assert job["result"]["error_code"] == "nai_opus_v5_allowance_low"
        assert job["result"]["remote_outcome_unknown"] is False
        assert calls == ["get"]
        assert len(queue.list()["items"]) == 1
        assert not list(tmp_path.rglob("*.png"))
    finally:
        queue.close()

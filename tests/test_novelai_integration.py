import io
import http.client
import json
import threading
import time
import zipfile
import urllib.error
from contextlib import contextmanager

import pytest
from PIL import Image

from anima_app.config import AppPaths
from anima_app.providers import novelai
from anima_app import server

pytestmark = pytest.mark.usefixtures("nai_mock_account")


def png_archive(width=64, height=64):
    png = io.BytesIO()
    Image.new("RGB", (width, height), "purple").save(png, format="PNG")
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("image.png", png.getvalue())
    return output.getvalue()


def nai_request(**values):
    return {"provider": "novelai", "prompt": "purple flower", "width": 64, "height": 64, **values}


@pytest.mark.parametrize("values", [
    {"width": True}, {"width": "64"}, {"width": 4096}, {"steps": 1.5},
    {"cfg": float("nan")}, {"cfg": float("inf")}, {"cfg": 21},
    {"seed": -1}, {"seed": 2**32}, {"seed": True},
    {"nai_limit_opus_free": "false"}, {"nai_variety_boost": 1},
    {"prompt": "a" * 32769}, {"prompt": ["a"]},
    {"i2i": {"enabled": True}}, {"loras": [{"path": "x"}]},
    {"upscale": {"enabled": True}}, {"face_detailer": {"enabled": True}},
    {"NAI_ACCESS_TOKEN": "secret"}, {"headers": {"Authorization": "Bearer secret"}},
])
def test_invalid_nai_request_is_rejected_before_transport(tmp_path, monkeypatch, values):
    monkeypatch.setattr(novelai, "generate", lambda *a, **k: pytest.fail("transport called"))
    status, result = server.handle_generate(nai_request(**values), paths=AppPaths(tmp_path))
    assert status == 400
    assert result["error_code"] == "generation_invalid_request"
    assert "secret" not in json.dumps(result)


def test_dry_run_needs_neither_local_models_nor_token(tmp_path, monkeypatch):
    monkeypatch.delenv("NAI_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("NAI_API_TOKEN", raising=False)
    monkeypatch.setattr(novelai.client, "_requests_transport", lambda *a: pytest.fail("network called"))
    status, result = server.handle_generate(nai_request(dry_run=True), paths=AppPaths(tmp_path))
    assert status == 200
    assert result["provider"] == "novelai"
    manifest = json.loads((tmp_path / "outputs/manifests" / result["manifest_name"]).read_text())
    assert manifest["provider"] == "novelai"
    assert result["stages"]["text_encode"]["status"] == "skipped"


def wait_terminal(queue, job_id):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        _, job = queue.get(job_id)
        if job["status"] not in {"queued", "waiting", "running"}:
            return job
        time.sleep(.01)
    pytest.fail("queue did not terminate")


def make_queue(tmp_path, *, dry_run=False, lock=None):
    return server.JobQueue(paths=AppPaths(tmp_path), renderer=None, default_dry_run=dry_run,
                           progress_store=server.ProgressStore(), generation_lock=lock or threading.Lock())


def test_nai_queue_does_not_require_local_models_and_snapshots_are_canonical(tmp_path, monkeypatch):
    monkeypatch.setenv("NAI_ACCESS_TOKEN", "synthetic-secret")
    monkeypatch.setattr(novelai.client, "_requests_transport", lambda *a: png_archive())
    queue = make_queue(tmp_path)
    try:
        status, batch = queue.enqueue({"request": nai_request(extra={"private": "discard me"}), "count": 2,
                                       "seed_mode": "increment"})
        assert status == 202
        jobs = [wait_terminal(queue, job["id"]) for job in batch["jobs"]]
        assert all(job["status"] == "completed" for job in jobs)
        assert "synthetic-secret" not in json.dumps(queue.list())
        assert "discard me" not in json.dumps(queue.list())
        assert all("checkpoint" not in job["request"] for job in jobs)
        assert jobs[1]["request"]["seed"] == (jobs[0]["request"]["seed"] + 1) % 2**32
    finally:
        queue.close()


def test_nai_presets_restore_provider_options_and_discard_extra_fields(tmp_path):
    paths = AppPaths(tmp_path)
    status, saved = server.handle_preset_save({"name": "NAI test", "request": nai_request(
        seed=0, nai_cfg_rescale=.4, nai_variety_boost=False, nai_limit_opus_free=False,
        extra="not saved")}, paths=paths)
    assert status == 200
    restored = server.handle_presets(paths=paths)["items"][0]["request"]
    assert restored == saved["request"]
    assert restored["provider"] == "novelai"
    assert restored["seed"] == 0
    assert restored["nai_cfg_rescale"] == .4
    assert restored["nai_variety_boost"] is False
    assert restored["nai_limit_opus_free"] is False
    assert "extra" not in restored


def test_remote_cancel_does_not_interrupt_local_runtime_or_discard_received_image(tmp_path, monkeypatch):
    entered, release = threading.Event(), threading.Event()
    monkeypatch.setenv("NAI_ACCESS_TOKEN", "synthetic-secret")
    interrupts = []
    monkeypatch.setattr(server, "_set_runtime_interrupt", lambda value: interrupts.append(value))
    calls = []

    def transport(*args):
        calls.append(args[0])
        entered.set()
        assert release.wait(5)
        return png_archive()

    monkeypatch.setattr(novelai.client, "_requests_transport", transport)
    queue = make_queue(tmp_path)
    try:
        _, batch = queue.enqueue({"request": nai_request(), "infinite": True})
        job_id = batch["jobs"][0]["id"]
        assert entered.wait(5)
        _, cancel = queue.cancel(job_id)
        assert cancel["job"]["remote_request_may_complete"] is True
        assert cancel["job"]["interrupt_requested"] is False
        release.set()
        job = wait_terminal(queue, job_id)
        assert job["status"] == "completed"
        assert job["result"]["cancellation_requested"] is True
        assert job["result"]["output_url"]
        assert len(calls) == 1
        assert interrupts == []
    finally:
        release.set()
        queue.close()


def test_timeout_is_sanitized_and_marks_remote_outcome_unknown_without_retry(tmp_path, monkeypatch):
    monkeypatch.setenv("NAI_ACCESS_TOKEN", "synthetic-secret")
    calls = []

    def transport(*args):
        calls.append(args[0])
        raise TimeoutError("Bearer synthetic-secret private-body")

    monkeypatch.setattr(novelai.client, "_requests_transport", transport)
    queue = make_queue(tmp_path)
    try:
        status, batch = queue.enqueue({"request": nai_request(), "infinite": True})
        assert status == 202
        job = wait_terminal(queue, batch["jobs"][0]["id"])
        assert job["status"] == "failed"
        assert job["result"]["error_code"] == "nai_timeout"
        assert job["result"]["remote_outcome_unknown"] is True
        assert len(calls) == 1
        assert "synthetic-secret" not in json.dumps(queue.list())
    finally:
        queue.close()


@contextmanager
def running_http_server(tmp_path, *, dry_run=True):
    http_server = server.create_http_server("127.0.0.1", 0, paths=AppPaths(tmp_path), default_dry_run=dry_run)
    thread = threading.Thread(target=http_server.serve_forever, daemon=True)
    thread.start()
    try:
        yield http_server.server_address[1]
    finally:
        http_server.shutdown()
        http_server.server_close()
        thread.join(5)


def http_json(port, method, path, payload=None, **headers):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        if payload is not None:
            headers["Content-Type"] = "application/json"
        connection.request(method, path, body=None if payload is None else json.dumps(payload), headers=headers)
        response = connection.getresponse()
        return response.status, json.loads(response.read())
    finally:
        connection.close()


def test_http_discovery_dry_queue_history_and_presets_are_provider_aware(tmp_path, monkeypatch):
    monkeypatch.delenv("NAI_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("NAI_API_TOKEN", raising=False)
    with running_http_server(tmp_path) as port:
        _, providers = http_json(port, "GET", "/api/providers")
        assert providers["default_dry_run"] is True
        nai = next(item for item in providers["providers"] if item["id"] == "novelai")
        assert nai["configured"] is False
        assert nai["operations"] == ["generate", "img2img", "infill", "detail", "focused_infill"]
        assert nai["account_entitlement_verified"] is False
        assert nai["opus_preflight"] == {"per_attempt": True, "active_tier": 3,
                                         "v5_min_remaining_percent": 2, "fail_closed": True}
        assert nai["request_interval_seconds"] == 2
        assert http_json(port, "GET", "/api/nai/status")[1]["configured"] is False
        _, document = http_json(port, "GET", "/api/openapi.json")
        assert document["paths"]["/api/providers"]
        assert document["components"]["schemas"]["NovelAIRequest"]["properties"]["seed"]["maximum"] == 2**32 - 1
        status, batch = http_json(port, "POST", "/api/jobs", {"request": nai_request(seed=0)})
        assert status == 202
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            _, job = http_json(port, "GET", "/api/jobs/" + batch["jobs"][0]["id"])
            if job["status"] == "completed":
                break
            time.sleep(.01)
        assert job["result"]["provider"] == "novelai"
        _, history = http_json(port, "GET", "/api/history")
        assert history["items"][0]["provider"] == "novelai"
        _, manifest = http_json(port, "GET", "/api/manifests/" + job["result"]["manifest_name"])
        assert manifest["novelai"]["effective"]["seed"] == 0
        assert http_json(port, "POST", "/api/presets", {"name": "HTTP NAI", "request": nai_request(seed=0)})[0] == 200
        exported = http_json(port, "GET", "/api/presets/export")[1]
        assert exported["items"][0]["request"]["provider"] == "novelai"
        status, blocked = http_json(port, "POST", "/api/jobs", {"request": nai_request()}, Origin="https://foreign.example")
        assert status == 403
        assert blocked["error_code"] == "request_origin_untrusted"


@pytest.mark.parametrize("http_status,code,public_status", [
    (401, "nai_auth_failed", 401), (403, "nai_auth_failed", 403),
    (402, "nai_balance_required", 402), (500, "nai_http_error", 502),
])
def test_remote_http_failures_never_expose_body_or_header(tmp_path, monkeypatch, http_status, code, public_status):
    monkeypatch.setenv("NAI_ACCESS_TOKEN", "synthetic-secret")

    def transport(url, *_args):
        raise urllib.error.HTTPError(url, http_status, "synthetic-secret private-response", {}, None)

    monkeypatch.setattr(novelai.client, "_requests_transport", transport)
    status, payload = server.handle_generate(nai_request(), paths=AppPaths(tmp_path))
    assert status == public_status
    assert payload["error_code"] == code
    assert "synthetic-secret" not in json.dumps(payload)
    assert "private-response" not in json.dumps(payload)


def test_opus_adjustment_and_original_bytes_are_recorded_in_manifest(tmp_path, monkeypatch):
    monkeypatch.setenv("NAI_ACCESS_TOKEN", "synthetic-secret")
    original = png_archive(1024, 1024)
    monkeypatch.setattr(novelai.client, "_requests_transport", lambda *args: original)
    status, payload = server.handle_generate(nai_request(width=2048, height=2048, steps=50), paths=AppPaths(tmp_path))
    assert status == 200
    manifest = json.loads((tmp_path / "outputs/manifests" / payload["manifest_name"]).read_text())
    assert (manifest["width"], manifest["height"], manifest["steps"]) == (1024, 1024, 28)
    assert manifest["novelai"]["requested"]["width"] == 2048
    assert manifest["novelai"]["opus_limits_applied"] is True
    assert manifest["warnings"]
    with zipfile.ZipFile(io.BytesIO(original)) as archive:
        assert (tmp_path / "outputs/images" / payload["output_path"].split("/")[-1]).read_bytes() == archive.read("image.png")


def test_mismatched_png_has_unknown_outcome_and_is_not_published(tmp_path, monkeypatch):
    monkeypatch.setenv("NAI_ACCESS_TOKEN", "synthetic-secret")
    monkeypatch.setattr(novelai.client, "_requests_transport", lambda *args: png_archive(128, 128))
    status, payload = server.handle_generate(nai_request(), paths=AppPaths(tmp_path))
    assert status == 502
    assert payload["error_code"] == "nai_response_invalid"
    assert payload["remote_outcome_unknown"] is True
    assert not list(tmp_path.rglob("*.png"))


def test_cancel_waiting_remote_job_never_calls_transport_and_local_dry_run_still_works(tmp_path, monkeypatch):
    monkeypatch.setenv("NAI_ACCESS_TOKEN", "synthetic-secret")
    monkeypatch.setattr(novelai.client, "_requests_transport", lambda *args: pytest.fail("network called"))
    lock = threading.Lock()
    lock.acquire()
    queue = make_queue(tmp_path, lock=lock)
    try:
        _, batch = queue.enqueue({"request": nai_request()})
        job_id = batch["jobs"][0]["id"]
        queue.cancel(job_id)
        lock.release()
        assert wait_terminal(queue, job_id)["status"] == "cancelled"
        monkeypatch.delenv("NAI_ACCESS_TOKEN")
        status, local = queue.enqueue({"request": {"prompt": "local without token", "dry_run": True}})
        assert status == 202
        assert wait_terminal(queue, local["jobs"][0]["id"])["status"] == "completed"
    finally:
        if lock.locked():
            lock.release()
        queue.close()

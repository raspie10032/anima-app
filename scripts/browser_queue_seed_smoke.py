"""Tokenless loopback browser acceptance for batch increment seeds (dry-run only)."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
import threading
import time
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import expect, sync_playwright

from anima_app import server
from anima_app.config import AppPaths
from anima_app.providers import novelai


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path,
                        default=Path("outputs/all-nai-port-20261009/queue-seed-fix/browser"))
    output = parser.parse_args().output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    saved_env = {key: os.environ.pop(key, None) for key in ("NAI_ACCESS_TOKEN", "NAI_API_TOKEN")}
    originals = {}
    page_errors, cases = [], []
    http_server = None
    worker = None

    def forbid_remote(*_args, **_kwargs):
        raise AssertionError("NovelAI transport called during tokenless dry-run acceptance")

    # Make the creation times differ even on a fast machine. Production seed
    # resolution still uses the real clock; only the test introduces this delay.
    original_append = server.JobQueue._append_batch_job_locked

    def delayed_append(self, *args, **kwargs):
        time.sleep(.01)
        return original_append(self, *args, **kwargs)

    try:
        server.JobQueue._append_batch_job_locked = delayed_append
        for name in ("_requests_transport", "_requests_subscription_transport"):
            originals[name] = getattr(novelai.client, name)
            setattr(novelai.client, name, forbid_remote)
        with tempfile.TemporaryDirectory(prefix="anima-queue-seeds-") as temporary:
            paths = AppPaths(Path(temporary))
            http_server = server.create_http_server("127.0.0.1", 0, paths=paths, default_dry_run=True)
            worker = threading.Thread(target=http_server.serve_forever, daemon=True)
            worker.start()
            address = f"http://127.0.0.1:{http_server.server_address[1]}"
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                context = browser.new_context(viewport={"width": 1440, "height": 1000})
                context.route("**/*", lambda route: route.continue_()
                              if urlparse(route.request.url).hostname == "127.0.0.1" else route.abort())
                page = context.new_page()
                page.on("pageerror", lambda error: page_errors.append(str(error)))
                page.goto(address, wait_until="networkidle")
                scenarios = [(provider, infinite, "") for provider in ("local", "novelai")
                             for infinite in (False, True)]
                scenarios += [("novelai", False, "0"), ("novelai", False, str(server.MAX_NAI_SEED))]
                for provider, infinite, seed in scenarios:
                    expect(page.locator("#start-queue")).to_be_enabled()
                    page.locator("#provider-select").select_option(provider)
                    if provider == "novelai":
                        page.locator("#nai-operation").select_option("generate")
                    page.locator("#width").fill("64")
                    page.locator("#height").fill("64")
                    page.locator("#steps").fill("1")
                    page.locator("#seed").fill(seed)
                    page.locator("#queue-count").fill("4")
                    page.locator("#queue-seed-mode").select_option("increment")
                    page.locator("#queue-delay").fill("0.5" if infinite else "0")
                    # The styled switch is operated through its visible label.
                    if page.locator("#queue-infinite").is_checked() != infinite:
                        page.locator('label[for="queue-infinite"]').click()
                    if infinite:
                        expect(page.locator("#queue-infinite")).to_be_checked()
                    else:
                        expect(page.locator("#queue-infinite")).not_to_be_checked()
                    with page.expect_response(lambda response: response.url == address + "/api/jobs"
                                              and response.request.method == "POST") as response:
                        page.locator("#start-queue").click()
                    assert response.value.status == 202
                    batch = response.value.json()
                    if infinite:
                        page.reload(wait_until="networkidle")
                        expect(page.locator("#stop-queue")).to_be_enabled()
                        # Poll the actual response; a Promise returned from a
                        # page polling predicate can be truthy before it resolves.
                        deadline = time.monotonic() + 15
                        while True:
                            observed = context.request.get(address + "/api/jobs").json()["items"]
                            if sum(job["batch_id"] == batch["batch_id"] for job in observed) >= 4:
                                break
                            assert time.monotonic() < deadline, "infinite followups did not arrive"
                            page.wait_for_timeout(100)
                        page.locator("#stop-queue").click()
                    expect(page.locator("#stop-queue")).to_be_disabled(timeout=15000)
                    # Dry-run writes a manifest without rendering an image.
                    expect(page.locator("#preview")).to_be_hidden()
                    expect(page.locator("#result-summary")).to_be_visible()
                    deadline = time.monotonic() + 15
                    while True:
                        jobs = [job for job in context.request.get(address + "/api/jobs").json()["items"]
                                if job["batch_id"] == batch["batch_id"]]
                        if jobs and all(job["status"] in {"completed", "cancelled"} for job in jobs):
                            break
                        assert time.monotonic() < deadline, "queue did not reach a terminal state"
                        page.wait_for_timeout(100)
                    assert len(jobs) >= 4, {
                        "provider": provider, "infinite": infinite, "input_seed": seed,
                        "batch": batch, "jobs": jobs,
                    }
                    maximum = server.MAX_NAI_SEED if provider == "novelai" else server.MAX_SEED
                    first_seed = jobs[0]["request"]["seed"]
                    assert [job["request"]["seed"] for job in jobs] == [
                        (first_seed + i) % (maximum + 1) for i in range(len(jobs))]
                    if seed:
                        assert first_seed == int(seed)
                    completed = [job for job in jobs if job["status"] == "completed"]
                    assert completed
                    if not infinite:
                        assert len(completed) == 4
                    for job in completed:
                        manifest = json.loads((paths.manifest_root / job["result"]["manifest_name"]).read_text())
                        assert manifest["seed"] == job["request"]["seed"]
                    if not infinite:
                        expect(page.locator("#result-summary")).to_contain_text(
                            str(completed[-1]["request"]["seed"]))
                        page.locator("#apply-manifest").click()
                        expect(page.locator("#seed")).to_have_value(str(completed[-1]["request"]["seed"]))
                    cases.append({"provider": provider, "infinite": infinite, "input_seed": seed,
                                  "batch_id": batch["batch_id"], "seeds": [job["request"]["seed"] for job in jobs],
                                  "statuses": [job["status"] for job in jobs], "completed_manifests_checked": len(completed),
                                  "terminal_state_confirmed": True})
                page.screenshot(path=str(output / "queue-seeds.png"), full_page=True)
                context.close()
                browser.close()
            assert not page_errors, page_errors
            report = {"status": "passed", "evidence": "Chromium UI with tokenless dry-run server",
                      "live_nai_requests": 0, "page_errors": page_errors, "cases": cases,
                      "checks": ["clock advances between creation of jobs", "blank seed finite and infinite batches",
                                 "local and NovelAI provider sequence", "reload and stop infinite queue",
                                 "explicit zero and NAI maximum wraparound", "manifest seed and form restoration"]}
            (output / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
            print(json.dumps(report, indent=2))
    finally:
        if http_server:
            http_server.shutdown()
            http_server.server_close()
        if worker:
            worker.join(5)
        server.JobQueue._append_batch_job_locked = original_append
        for name, value in originals.items():
            setattr(novelai.client, name, value)
        for key, value in saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


if __name__ == "__main__":
    main()

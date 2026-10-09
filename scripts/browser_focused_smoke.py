"""Focused-only UI acceptance with synthetic NAI/detectors and no external HTTP.

Optional --firefox-hold keeps the same synthetic loopback server available for
Firefox DevTools inspection until ENTER is sent to this process.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import tempfile
import threading
import time
import zipfile
from pathlib import Path
from urllib.parse import urlparse

import numpy as np
import requests
from PIL import Image, ImageDraw
from playwright.sync_api import expect, sync_playwright

from anima_app.config import AppPaths
from anima_app.providers import novelai
from anima_app.providers.novelai import detailer
from anima_app.server import create_http_server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/all-nai-port-20261009/focused/browser"))
    parser.add_argument("--firefox-hold", action="store_true")
    args = parser.parse_args()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    saved_env = {k: os.environ.get(k) for k in ("NAI_ACCESS_TOKEN", "NAI_API_TOKEN")}
    os.environ["NAI_ACCESS_TOKEN"] = "synthetic-focused-token"
    os.environ.pop("NAI_API_TOKEN", None)
    originals = (requests.sessions.Session.request, novelai.client._requests_transport,
                 novelai.client._requests_subscription_transport, novelai.client.REQUEST_INTERVAL_SECONDS,
                 detailer.Detector.preflight, detailer.Detector.detect, Image.Image.save)
    calls, accounts, cases, errors = [], [], [], []
    state = {"mode": "success", "failed": False, "tier": 3}
    entered, release = threading.Event(), threading.Event()
    server = None

    def forbid(*_, **__):
        raise AssertionError("external HTTP forbidden in focused smoke")

    def transport(url, headers, body, timeout):
        payload = json.loads(body)
        calls.append(payload)
        if state["mode"] == "hold":
            entered.set()
            if not release.wait(15):
                raise AssertionError("synthetic response was not released")
        if state["mode"] == "timeout_second" and len(calls) == state["start"] + 2:
            raise TimeoutError("synthetic-focused-token")
        params = payload["parameters"]
        png, archive = io.BytesIO(), io.BytesIO()
        Image.new("RGB", (params["width"], params["height"]), "purple").save(png, format="PNG")
        with zipfile.ZipFile(archive, "w") as zipped:
            zipped.writestr("image.png", png.getvalue())
        return archive.getvalue()

    def account(*_):
        accounts.append(len(calls))
        return json.dumps({"active": True, "tier": state["tier"], "usage": {"percent": 100, "isNegative": False}}).encode()

    def save(image, fp, *args, **kwargs):
        if (state["mode"] == "mask_second" and len(calls) == state["start"] + 2
                and image.mode == "L" and not state["failed"]):
            state["failed"] = True
            raise OSError("synthetic-focused-token")
        return originals[-1](image, fp, *args, **kwargs)

    def detect(_, source, cancelled):
        result = []
        for box in ((20, 30, 40, 50), (100, 30, 120, 50)):
            mask = Image.new("L", source.size)
            ImageDraw.Draw(mask).rectangle(box, fill=255)
            result.append(detailer.Region(box, mask))
        return result

    requests.sessions.Session.request = forbid
    novelai.client._requests_transport = transport
    novelai.client._requests_subscription_transport = account
    novelai.client.REQUEST_INTERVAL_SECONDS = 0
    detailer.Detector.preflight = lambda _: None
    detailer.Detector.detect = detect
    Image.Image.save = save
    try:
        with tempfile.TemporaryDirectory(prefix="anima-focused-smoke-") as temporary:
            root = Path(temporary)
            paths = AppPaths(root, autocomplete_source=root / "autocomplete.txt")
            source = root / "source.png"
            mask_path, full_mask = root / "mask.png", root / "full-mask.png"
            yy, xx = np.indices((128, 256))
            pixels = np.stack((xx % 256, yy * 2 % 256, (xx + yy) % 256), axis=-1).astype(np.uint8)
            Image.fromarray(pixels).save(source)
            source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
            mask = Image.new("L", (256, 128))
            ImageDraw.Draw(mask).ellipse((20, 30, 40, 50), fill=255)
            mask.save(mask_path)
            Image.new("L", mask.size, 255).save(full_mask)
            server = create_http_server("127.0.0.1", 0, paths=paths)
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            address = f"http://127.0.0.1:{server.server_address[1]}"
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                page = browser.new_page(viewport={"width": 1600, "height": 1100})
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.route("**/*", lambda route: route.continue_() if urlparse(route.request.url).hostname == "127.0.0.1" else route.abort())
                page.goto(address, wait_until="networkidle")
                page.locator("#provider-select").select_option("novelai")
                page.locator('[name="prompt"]').fill("focused audit")
                page.locator("#nai-model").select_option("nai-diffusion-5-curated")
                page.locator("#nai-operation").select_option("focused_infill")
                expect(page.locator("#nai-model")).to_have_value("nai-diffusion-4-5-curated-inpainting")
                page.locator("#nai-input-file").set_input_files(source)
                expect(page.locator('[name="input_image"]')).not_to_have_value("")
                page.locator("#nai-mask-file").set_input_files(mask_path)
                expect(page.locator('[name="mask_image"]')).not_to_have_value("")
                page.locator("#nai-detailer-panel summary").click()
                page.locator("#nai-detailer-padding").fill("0")
                page.locator("#nai-detailer-steps").fill("50")
                page.locator("#nai-detailer-strength").fill("0")
                page.locator('[name="seed"]').fill("0")

                def terminal_job(before):
                    deadline = time.monotonic() + 25
                    while time.monotonic() < deadline:
                        jobs = page.request.get(address + "/api/jobs").json()["items"]
                        fresh = [j for j in jobs if j["id"] not in before]
                        if fresh and all(j["status"] in {"completed", "failed", "cancelled"} for j in fresh):
                            expect(page.locator("#stop-queue")).to_be_disabled()
                            return fresh
                        page.wait_for_timeout(50)
                    raise AssertionError(page.locator("#result").inner_text())

                def start(button="#generate-button"):
                    before = {j["id"] for j in page.request.get(address + "/api/jobs").json()["items"]}
                    page.locator(button).click()
                    return before

                def saved_result(job, name):
                    result = job["result"]
                    expect(page.locator("#preview")).to_be_visible()
                    manifest = json.loads(Path(result["manifest_path"]).read_text())
                    (output / f"{name}-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
                    (output / f"{name}.png").write_bytes(Path(result["output_path"]).read_bytes())
                    return manifest

                job = terminal_job(start())[0]
                assert job["status"] == "completed", job
                manifest = saved_result(job, "manual-focused")
                crop = manifest["novelai"]["detailer"][0]
                assert crop["transmitted_model"] == "nai-diffusion-4-5-curated-inpainting"
                assert crop["transmitted_steps"] == 28 and crop["seed"] == 0
                assert calls[-1]["parameters"]["inpaintImg2ImgStrength"] == 0
                with Image.open(job["result"]["output_path"]) as result:
                    assert np.array_equal(np.asarray(result)[np.asarray(mask) == 0], pixels[np.asarray(mask) == 0])
                page.locator("#apply-manifest").click()
                expect(page.locator("#nai-operation")).to_have_value("focused_infill")
                expect(page.locator("#nai-detailer-strength")).to_have_value("0")
                expect(page.locator("#nai-detailer-steps")).to_have_value("50")
                cases.append({"name": "manual/model-routing/steps/zero-strength/black-pixels/history-settings", "status": "passed"})

                # A full-image mask is rejected before the account check or generate call.
                page.locator("#nai-mask-file").set_input_files(full_mask)
                expect(page.locator('[name="mask_image"]')).not_to_have_value("")
                before = len(calls), len(accounts)
                blocked = terminal_job(start())[0]
                assert blocked["status"] == "failed" and (len(calls), len(accounts)) == before
                cases.append({"name": "full-source-crop-blocks-before-account", "status": "passed"})

                page.locator("#nai-mask-file").set_input_files(mask_path)
                expect(page.locator('[name="mask_image"]')).not_to_have_value("")
                state["tier"] = 2
                before = len(calls)
                blocked = terminal_job(start())[0]
                assert blocked["status"] == "failed" and len(calls) == before
                state["tier"] = 3
                cases.append({"name": "invalid-opus-account-blocks-before-generate", "status": "passed"})

                # Preview consumes no token/account or generate call.
                page.locator("#nai-detailer-preview").check()
                before = len(calls), len(accounts)
                assert terminal_job(start())[0]["status"] == "completed"
                assert (len(calls), len(accounts)) == before
                page.locator("#nai-detailer-preview").uncheck()
                cases.append({"name": "preview-no-remote-calls", "status": "passed"})

                # Same focused engine, two synthetic regions, partial failure and queue stop.
                page.locator("#nai-operation").select_option("detail")
                for mode in ("mask_second", "timeout_second", "hold"):
                    state.update(mode=mode, start=len(calls), failed=False)
                    page.locator("#queue-count").fill("3")
                    before = start("#start-queue")
                    if mode == "hold":
                        deadline = time.monotonic() + 10
                        while not entered.is_set():
                            assert time.monotonic() < deadline
                            page.wait_for_timeout(50)
                        page.locator("#stop-queue").click()
                        release.set()
                    jobs = terminal_job(before)
                    job = next(j for j in jobs if j["status"] == "completed")
                    manifest = saved_result(job, mode)
                    assert sum(j["status"] == "cancelled" for j in jobs) == 2
                    result = job["result"]
                    expected_unknown = mode == "timeout_second"
                    assert result["stop_scheduling"] and result["remote_outcome_unknown"] is expected_unknown
                    assert len(calls) - state["start"] == (1 if mode == "hold" else 2)
                    report = manifest["novelai"]["detailer"]
                    assert report[0]["status"] == "edited"
                    assert report[1]["status"] == {"mask_second": "checkpoint_failed", "timeout_second": "failed", "hold": "cancelled"}[mode]
                    with Image.open(result["output_path"]) as composite:
                        assert composite.getpixel((30, 40)) == (128, 0, 128)
                        assert composite.getpixel((110, 40)) == tuple(pixels[40, 110])
                    state["mode"] = "success"
                    page.reload(wait_until="networkidle")
                    page.locator('.history-action[title="생성 정보 보기"]').first.click()
                    expect(page.locator("#preview")).to_be_visible()
                    page.locator("#apply-manifest").click()
                    expect(page.locator("#nai-operation")).to_have_value("detail")
                    cases.append({"name": mode + "/retained-first-crop/cancel-two-followups/reload-history", "status": "passed"})
                page.screenshot(path=str(output / "focused-result.png"))
                browser.close()
            assert not errors
            assert hashlib.sha256(source.read_bytes()).hexdigest() == source_hash
            if args.firefox_hold:
                print(json.dumps({"firefox_url": address, "source": str(source), "mask": str(mask_path)}), flush=True)
                input("Firefox inspection server ready; send ENTER to finish.\n")
            summaries = [{"model": p["model"], "action": p["action"],
                          **{k: p["parameters"][k] for k in ("width", "height", "steps", "seed", "inpaintImg2ImgStrength")}}
                         for p in calls]
            report = {"status": "passed", "evidence": "Chromium UI, synthetic transports/detectors",
                      "live_nai_requests": 0, "page_errors": errors, "cases": cases,
                      "mock_account_calls": len(accounts), "mock_generation_attempts": len(calls),
                      "transmitted_crops": summaries, "original_file_sha256": source_hash,
                      "firefox_inspection_available": args.firefox_hold}
            (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
            print(json.dumps(report, indent=2), flush=True)
    finally:
        release.set()
        if server:
            server.shutdown()
            server.server_close()
            worker.join(5)
        (requests.sessions.Session.request, novelai.client._requests_transport,
         novelai.client._requests_subscription_transport, novelai.client.REQUEST_INTERVAL_SECONDS,
         detailer.Detector.preflight, detailer.Detector.detect, Image.Image.save) = originals
        for key, value in saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


if __name__ == "__main__":
    main()

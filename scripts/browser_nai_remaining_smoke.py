"""Browser acceptance of remaining RS_NAI ports with synthetic transports/detectors.

Every external request is blocked. Native model smoke is a separate script.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import tempfile
import threading
import time
import zipfile
from pathlib import Path
from urllib.parse import urlparse

import requests
from PIL import Image, ImageDraw
from playwright.sync_api import expect, sync_playwright

from anima_app.config import AppPaths
from anima_app.providers import novelai
from anima_app.providers.novelai import detailer
from anima_app.providers.novelai.references import ENCODE_VIBE_URL
from anima_app.providers.novelai.wd_tagger import WDTagger
from anima_app.server import create_http_server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/all-nai-port-20261009/browser"))
    output = parser.parse_args().output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    saved = {key: os.environ.get(key) for key in ("NAI_ACCESS_TOKEN", "NAI_API_TOKEN")}
    os.environ["NAI_ACCESS_TOKEN"] = "synthetic-all-nai-browser-token"
    os.environ.pop("NAI_API_TOKEN", None)
    originals = (requests.post, requests.get, novelai.client._requests_transport, novelai.client._requests_subscription_transport,
                 novelai.client.REQUEST_INTERVAL_SECONDS, detailer.Detector.preflight, detailer.Detector.detect)
    calls, accounts, errors = [], [], []
    fail_at = None
    wd_originals = WDTagger._load, WDTagger.score

    def wd_scores(self, images):
        attempt = getattr(self, "smoke_attempt", 0)
        self.smoke_attempt = attempt + 1
        if attempt == 0:
            assert len(images) == 2
            return [{"red_hair": .95, "blue_hair": .1, "observation_only": 1},
                    {"red_hair": .8, "blue_hair": .8}]
        assert len(images) == 1
        return [{"red_hair": .1, "blue_hair": .9}]

    def forbid(*a, **k):
        raise AssertionError("External HTTP is forbidden")

    def transport(url, headers, body, timeout):
        payload = json.loads(body)
        calls.append((url, payload))
        if len(calls) == fail_at:
            raise TimeoutError("synthetic transport failure")
        if url == ENCODE_VIBE_URL:
            return b"synthetic-encoding"
        params = payload["parameters"]
        png, archive = io.BytesIO(), io.BytesIO()
        Image.new("RGB", (params["width"], params["height"]), "purple").save(png, format="PNG")
        with zipfile.ZipFile(archive, "w") as zipped:
            zipped.writestr("image.png", png.getvalue())
        return archive.getvalue()

    def subscription(url, *a):
        accounts.append(url)
        return b'{"active":true,"tier":3,"usage":{"percent":100,"isNegative":false}}'

    def detect(self, source, cancelled):
        regions = []
        for box in ((20, 30, 40, 50), (100, 30, 120, 50)):
            mask = Image.new("L", source.size)
            ImageDraw.Draw(mask).rectangle(box, fill=255)
            regions.append(detailer.Region(box, mask))
        return regions

    requests.get = requests.post = forbid
    novelai.client._requests_transport = transport
    novelai.client._requests_subscription_transport = subscription
    novelai.client.REQUEST_INTERVAL_SECONDS = 0
    detailer.Detector.preflight = lambda _: None
    detailer.Detector.detect = detect
    WDTagger._load = lambda _: None
    WDTagger.score = wd_scores
    server = None
    try:
        with tempfile.TemporaryDirectory(prefix="anima-remaining-smoke-") as temporary:
            root = Path(temporary)
            paths = AppPaths(root, autocomplete_source=root / "autocomplete.txt")
            source, mask_path = root / "source.png", root / "mask.png"
            Image.new("RGB", (256, 128), "green").save(source)
            mask = Image.new("L", (256, 128))
            ImageDraw.Draw(mask).rectangle((20, 30, 40, 50), fill=255)
            mask.save(mask_path)
            server = create_http_server("127.0.0.1", 0, paths=paths)
            threading.Thread(target=server.serve_forever, daemon=True).start()
            address = f"http://127.0.0.1:{server.server_address[1]}"
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                page = browser.new_page(viewport={"width": 1600, "height": 1100})
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.route("**/*", lambda route: route.continue_() if urlparse(route.request.url).hostname == "127.0.0.1" else route.abort())
                page.goto(address, wait_until="networkidle")
                page.locator("#provider-select").select_option("novelai")
                expect(page.locator("#nai-operation")).to_have_value("generate")
                page.locator('[name="prompt"]').fill("a flower")
                page.locator('[name="width"]').fill("256")
                page.locator('[name="height"]').fill("128")

                def generate():
                    before = len(list(paths.manifest_root.glob("*.json")))
                    page.locator("#generate-button").click()
                    deadline = time.monotonic() + 20
                    while len(list(paths.manifest_root.glob("*.json"))) == before:
                        if time.monotonic() > deadline:
                            raise AssertionError("generation failed: " + page.locator("#result").inner_text())
                        page.wait_for_timeout(50)
                    expect(page.locator("#stop-queue")).to_be_disabled(timeout=10000)
                    expect(page.locator("#preview")).to_be_visible()

                # Img2Img: input upload, explicit cost control, zero strength and extra noise, history restore.
                page.locator("#nai-operation").select_option("img2img")
                page.locator("#nai-input-file").set_input_files(source)
                expect(page.locator('[name="input_image"]')).not_to_have_value("")
                assert not page.locator("#generate-form").evaluate("f=>f.checkValidity()")
                page.locator('label[for="nai-limit-opus-free"]').click()
                page.locator('[name="img2img_strength"]').fill("0")
                page.locator('[name="img2img_noise"]').fill("0.2")
                generate()
                assert calls[-1][1]["action"] == "img2img" and calls[-1][1]["parameters"]["strength"] == 0
                page.locator("#apply-manifest").click()
                expect(page.locator('[name="img2img_noise"]')).to_have_value("0.2")

                # V4.5 multivibe normalizes strengths and encodes identical inputs once, even across later requests.
                page.locator("#nai-operation").select_option("generate")
                page.locator("#nai-model").select_option("nai-diffusion-4-5-full")
                page.locator("#nai-reference-panel summary").click()
                for _ in range(2):
                    page.locator("#nai-add-vibe").click()
                    page.locator('#nai-vibes input[type="file"]').last.set_input_files(source)
                    expect(page.locator("#nai-vibes .reference-path").last).to_contain_text("inputs/references/")
                generate()
                assert calls[-1][1]["parameters"]["reference_strength_multiple"] == [.5, .5]
                generate()
                assert sum(url == ENCODE_VIBE_URL for url, _ in calls) == 1
                page.locator("#apply-manifest").click()
                expect(page.locator("#nai-vibes fieldset")).to_have_count(2)
                page.locator("#nai-add-reference").click()
                page.locator('#nai-references input[type="file"]').set_input_files(source)
                expect(page.locator("#nai-references .reference-path")).to_contain_text("inputs/references/")
                assert not page.locator("#generate-form").evaluate("f=>f.checkValidity()")
                # Switch to Precise; preserve the exact type/strength/fidelity in the manifest.
                while page.locator("#nai-vibes fieldset").count():
                    page.locator("#nai-vibes button").first.click()
                page.locator("#nai-references .reference-type").select_option("character&style")
                page.locator("#nai-references .reference-fidelity").fill("0")
                generate()
                assert calls[-1][1]["parameters"]["director_reference_secondary_strength_values"] == [1]
                page.locator("#apply-manifest").click()
                expect(page.locator("#nai-references .reference-type")).to_have_value("character&style")
                page.locator("#nai-references button").click()

                # Standalone detail and preview; only crops submit, every crop gets fresh protected account checks.
                page.locator("#nai-operation").select_option("detail")
                page.locator("#nai-input-file").set_input_files(source)
                expect(page.locator('[name="input_image"]')).not_to_have_value("")
                page.locator('label[for="nai-limit-opus-free"]').click()
                page.locator("#nai-detailer-panel summary").click()
                page.locator("#nai-detailer-padding").fill("0")
                before = len(calls)
                generate()
                assert len(calls) == before + 2 and all(p["action"] == "infill" for _, p in calls[-2:])
                assert len(accounts) == 2
                page.locator("#apply-manifest").click()
                expect(page.locator("#nai-operation")).to_have_value("detail")
                page.locator("#nai-detailer-preview").check()
                before = len(calls)
                generate()
                assert len(calls) == before

                # Focused input from a hand mask; protect the source and import the composite's conditions again.
                page.locator("#nai-detailer-preview").uncheck()
                page.locator("#nai-operation").select_option("focused_infill")
                page.locator("#nai-mask-file").set_input_files(mask_path)
                expect(page.locator('[name="mask_image"]')).not_to_have_value("")
                generate()
                assert len(accounts) == 3
                page.locator("#apply-manifest").click()
                expect(page.locator("#nai-operation")).to_have_value("focused_infill")
                page.screenshot(path=str(output / "focused-result.png"))

                # Browser-selected WD matching uses original weighted identity text, never observations.
                page.locator("#nai-operation").select_option("detail")
                page.locator("#nai-characters-panel").evaluate("node => {node.open = true}")
                for prompt, negative in (("1.2::alice (franchise)::, red hair", "bad alice"),
                                         ("bob (franchise), blue hair", "bad bob")):
                    page.locator("#nai-add-character").click()
                    row = page.locator("#nai-characters .nai-character").last
                    row.locator(".character-prompt").fill(prompt)
                    row.locator(".character-negative").fill(negative)
                page.locator("#nai-detailer-matching").select_option("wd14")
                shared_negative = page.locator('[name="negative_prompt"]').input_value()
                generate()
                assert calls[-2][1]["input"] == "a flower, 1.2::alice (franchise)::, red hair"
                assert calls[-1][1]["parameters"]["negative_prompt"] == ", ".join(
                    value for value in (shared_negative, "bad bob") if value)
                assert "observation_only" not in json.dumps(calls[-2:])
                manifest = max(paths.manifest_root.glob("*.json"), key=lambda path: path.stat().st_mtime_ns)
                matched = json.loads(manifest.read_text())["novelai"]["detailer"]
                assert [item["character"] for item in matched] == [1, 2]
                assert matched[1]["reason"] == "tag_match_tight"
                page.locator("#apply-manifest").click()
                expect(page.locator("#nai-detailer-matching")).to_have_value("wd14")
                expect(page.locator("#nai-characters .nai-character")).to_have_count(2)
                while page.locator("#nai-characters .nai-character").count():
                    page.locator("#nai-characters .nai-character").last.locator("button").click()
                page.locator("#nai-detailer-matching").select_option("shared")

                # A failed second crop must retain the first composite and cancel batch followups.
                page.locator("#nai-operation").select_option("detail")
                page.locator("#queue-count").fill("3")
                before_manifests = set(paths.manifest_root.glob("*.json"))
                before_calls = len(calls)
                fail_at = before_calls + 2
                page.locator("#start-queue").click()
                deadline = time.monotonic() + 20
                while not set(paths.manifest_root.glob("*.json")) - before_manifests:
                    if time.monotonic() > deadline:
                        raise AssertionError("partial result missing: " + page.locator("#result").inner_text())
                    page.wait_for_timeout(50)
                expect(page.locator("#stop-queue")).to_be_disabled(timeout=10000)
                expect(page.locator("#preview")).to_be_visible()
                assert len(calls) == before_calls + 2, "failed batch submitted followups"
                jobs = page.request.get(address + "/api/jobs").json()["items"]
                failed_pipeline = [job for job in jobs if (job.get("result") or {}).get("stop_scheduling")]
                assert len(failed_pipeline) == 1
                result = failed_pipeline[0]["result"]
                assert result["remote_outcome_unknown"] and result["warnings"]
                assert sum(job["status"] == "cancelled" for job in jobs) == 2
                with Image.open(result["output_path"]) as composite:
                    assert composite.getpixel((30, 40)) == (128, 0, 128)
                    assert composite.getpixel((110, 40)) == (0, 128, 0)
                page.reload(wait_until="networkidle")
                page.locator('.history-action[title="생성 정보 보기"]').first.click()
                expect(page.locator("#preview")).to_be_visible()
                page.screenshot(path=str(output / "partial-result.png"))
                assert not errors, errors
                browser.close()
            report = {"status": "passed", "live_nai_requests": 0, "mock_encoding_calls": sum(url == ENCODE_VIBE_URL for url, _ in calls),
                      "mock_generation_calls": sum(url != ENCODE_VIBE_URL for url, _ in calls), "mock_account_calls": len(accounts),
                      "page_errors": errors, "checked": ["Img2Img upload/cost guard/zero values/restore", "multivibe encode once/cache/normalization/restore",
                      "mutual exclusion", "Precise type/fidelity/restore", "standalone two-region focused detail/account preflight",
                      "preview has no remote calls", "manual focused input and restore",
                      "WD character selection, tight retry, original weighted prompts and settings restore",
                      "second crop timeout retains completed composite, stops finite batch, and opens from history after reload"]}
            (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
            print(json.dumps(report, ensure_ascii=False, indent=2))
    finally:
        if server:
            server.shutdown()
            server.server_close()
        (requests.post, requests.get, novelai.client._requests_transport, novelai.client._requests_subscription_transport,
         novelai.client.REQUEST_INTERVAL_SECONDS, detailer.Detector.preflight, detailer.Detector.detect) = originals
        WDTagger._load, WDTagger.score = wd_originals
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


if __name__ == "__main__":
    main()

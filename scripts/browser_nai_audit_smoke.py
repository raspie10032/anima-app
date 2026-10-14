"""Audit notices through real UI/queue code with synthetic local transports only."""
from __future__ import annotations

import argparse
import io
import json
import os
import tempfile
import threading
import time
import urllib.error
import zipfile
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlparse

import requests
from PIL import Image, ImageDraw
from playwright.sync_api import expect, sync_playwright

from anima_app.config import AppPaths
from anima_app.providers import novelai
from anima_app.providers.novelai import detailer
from anima_app.providers.novelai.wd_tagger import WDTagger
from anima_app.server import create_http_server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/nai-update-20261011/audit/browser"))
    parser.add_argument("--hold-seconds", type=int, default=0)
    args = parser.parse_args()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    calls, errors, blocked, cases, accounts = [], [], [], [], []
    detection = "regions"
    fail_next = False

    def forbidden(*a, **k):
        blocked.append("external HTTP attempted")
        raise AssertionError("External HTTP forbidden")

    def transport(url, headers, body, timeout):
        nonlocal fail_next
        payload = json.loads(body)
        calls.append(payload)
        if fail_next:
            fail_next = False
            raise urllib.error.HTTPError(url, 429, "synthetic rate limit", {"Retry-After": "0"}, None)
        params = payload["parameters"]
        png, archive = io.BytesIO(), io.BytesIO()
        Image.new("RGB", (params["width"], params["height"]), "purple").save(png, format="PNG")
        with zipfile.ZipFile(archive, "w") as zipped:
            zipped.writestr("metadata.json", "{}")
            zipped.writestr("folder/", "")
            zipped.writestr("folder/image.PNG", png.getvalue())
        return archive.getvalue()

    def subscription(*a):
        accounts.append("synthetic")
        return b'{"active":true,"tier":3,"usage":{"percent":100,"isNegative":false}}'

    def detect(self, source, cancelled):
        if detection == "none":
            return []
        result = []
        for box in ((20, 30, 40, 50), (100, 30, 120, 50)):
            mask = Image.new("L", source.size)
            ImageDraw.Draw(mask).rectangle(box, fill=255)
            result.append(detailer.Region(box, mask))
        return result

    def scores(self, images):
        attempt = getattr(self, "audit_attempt", 0)
        self.audit_attempt = attempt + 1
        return [{"red_hair": .8, "blue_hair": .79} if attempt == 0
                else {"red_hair": .12, "blue_hair": .1} for _ in images]

    with (tempfile.TemporaryDirectory(prefix="anima-audit-smoke-") as temporary,
          patch.dict(os.environ, {"NAI_ACCESS_TOKEN": "synthetic-audit-token", "NAI_API_TOKEN": ""}),
          patch.object(requests.sessions.Session, "request", forbidden),
          patch.object(novelai.client, "_requests_transport", transport),
          patch.object(novelai.client, "_requests_subscription_transport", subscription),
          patch.object(novelai.client, "REQUEST_INTERVAL_SECONDS", 0),
          patch.object(detailer.Detector, "preflight", lambda _: None),
          patch.object(detailer.Detector, "detect", detect),
          patch.object(WDTagger, "_load", lambda _, *a, **k: None),
          patch.object(WDTagger, "score", scores)):
        root = Path(temporary)
        source = root / "source.png"
        Image.new("RGB", (256, 128), "green").save(source)
        paths = AppPaths(root, autocomplete_source=root / "autocomplete.txt")
        server = create_http_server("127.0.0.1", 0, paths=paths)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        address = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                page = browser.new_page(locale="ko-KR", viewport={"width": 1550, "height": 1050})
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.route("**/*", lambda route: route.continue_() if urlparse(route.request.url).hostname == "127.0.0.1" else route.abort())
                page.goto(address, wait_until="networkidle")
                page.locator("#provider-select").select_option("novelai")
                page.locator("#prompt-converter summary").click()
                page.locator('[name="prompt"]').fill("ok, (<script>alert(1)</script>:oops), end")
                page.locator("#convert-preview").click()
                expect(page.locator("#convert-status")).to_contain_text("제외")
                assert page.locator("#convert-status script").count() == 0
                page.screenshot(path=str(output / "conversion-warning.png"), full_page=True)
                page.locator('[name="prompt"]').fill("(hair:1.2)")
                expect(page.locator("#convert-status")).to_have_text("")
                expect(page.locator("#convert-result")).to_have_text("")
                expect(page.locator("#convert-apply")).to_be_disabled()
                page.locator("#convert-preview").click()
                expect(page.locator("#convert-status")).to_have_text("변환 결과를 확인한 뒤 적용하세요.")
                page.locator("#convert-apply").click()
                expect(page.locator('[name="prompt"]')).to_have_value("1.2::hair ::")
                cases.append("loss notice is plain text; input clears stale notice and disables stale apply")

                page.locator("#convert-source").select_option("naiv4")
                page.locator("#convert-target").select_option("oldnai")
                page.locator('[name="prompt"]').fill("-1::hair::lost")
                page.locator("#convert-preview").click()
                expect(page.locator("#convert-status")).to_contain_text("lost")
                expect(page.locator("#convert-status")).to_contain_text("표현할 수 없어")
                cases.append("inline suffix loss and legacy nonpositive weight explanation")

                page.locator('[name="prompt"]').fill("shared scene")
                page.locator('[name="width"]').fill("256")
                page.locator('[name="height"]').fill("128")
                page.locator("#nai-model").select_option("nai-diffusion-5-curated")
                page.locator("#nai-operation").select_option("infill")
                expect(page.locator("#nai-model")).to_have_value("nai-diffusion-4-5-curated-inpainting")
                expect(page.locator("#nai-routing-notice")).to_contain_text("V4.5 Curated")
                page.locator("#nai-model").select_option("nai-diffusion-5-full-inpainting")
                expect(page.locator("#nai-routing-notice")).to_be_hidden()
                cases.append("Curated infill fallback shown and cleared on a different model")

                def generate():
                    before = set(paths.manifest_root.glob("*.json"))
                    page.locator("#generate-button").click()
                    deadline = time.monotonic() + 25
                    while not (set(paths.manifest_root.glob("*.json")) - before):
                        if time.monotonic() > deadline:
                            raise AssertionError("generation failed: " + page.locator("#result").inner_text())
                        page.wait_for_timeout(50)
                    expect(page.locator("#stop-queue")).to_be_disabled(timeout=10000)
                    expect(page.locator("#preview")).to_be_visible()
                    return json.loads(next(iter(set(paths.manifest_root.glob("*.json")) - before)).read_text())

                page.locator("#nai-operation").select_option("detail")
                page.locator("#nai-model").select_option("nai-diffusion-5-curated")
                page.locator("#nai-input-file").set_input_files(source)
                expect(page.locator('[name="input_image"]')).not_to_have_value("")
                page.locator("#nai-detailer-panel").evaluate("e=>e.open=true")
                page.locator("#nai-detailer-preview").check()
                detection = "none"
                manifest = generate()
                expect(page.locator("#result-summary")).to_contain_text("유효한 검출 영역이 없습니다")
                assert not calls and manifest["novelai"]["detailer"] == []
                cases.append("empty detection preserves source, explains no detail request")

                detection = "regions"
                page.locator("#nai-characters-panel").evaluate("e=>e.open=true")
                for prompt in ("red hair", "blue hair"):
                    page.locator("#nai-add-character").click()
                    page.locator("#nai-characters .character-prompt").last.fill(prompt)
                page.locator("#nai-detailer-matching").select_option("wd14")
                page.locator("#nai-detailer-mode").select_option("first")
                manifest = generate()
                expect(page.locator("#result-summary")).to_contain_text("점수 0.120 / 차이 0.020")
                expect(page.locator("#result-summary")).to_contain_text("좁은 크롭 재확인")
                expect(page.locator("#result-summary")).to_contain_text("최대 영역 수 제한")
                assert not calls and manifest["novelai"]["detailer"][0]["tight_crop_retried"]
                page.screenshot(path=str(output / "detailer-diagnostics.png"), full_page=True)
                page.locator("#apply-manifest").click()
                expect(page.locator("#nai-detailer-matching")).to_have_value("wd14")
                expect(page.locator("#nai-detailer-mode")).to_have_value("first")
                expect(page.locator("#result-summary")).to_contain_text("점수 0.120 / 차이 0.020")
                cases.append("failed tight retry shows latest score, skip reasons and restored history")

                page.locator("#nai-operation").select_option("generate")
                page.locator("#nai-detailer-enabled").uncheck()
                page.locator('[name="width"]').fill("2048")
                page.locator('[name="height"]').fill("2048")
                page.locator('[name="steps"]').fill("50")
                fail_next = True
                manifest = generate()
                expect(page.locator("#result-summary")).to_contain_text("HTTP 429")
                expect(page.locator("#result-summary")).to_contain_text("2048x2048, 50 스텝 → 1024x1024, 28 스텝")
                assert len(calls) == 2 and calls[0] == calls[1]
                assert manifest["novelai"]["retry_count"] == 1
                assert not manifest["novelai"].get("detailer")
                expect(page.locator("#result-summary")).not_to_contain_text("좁은 크롭 재확인")
                cases.append("429 retry/cap notice, metadata-first ZIP and cleared previous result warnings")
                page.screenshot(path=str(output / "retry-and-cap.png"), full_page=True)
                assert not errors and not blocked
                browser.close()
            report = {"cases": cases, "page_errors": errors, "external_http_attempts": blocked,
                      "live_nai_calls": 0, "synthetic_image_attempts": len(calls),
                      "synthetic_account_checks": len(accounts), "address": address}
            (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
            print(json.dumps({"report": str(output / "report.json"), "cases": len(cases), "address": address}), flush=True)
            if args.hold_seconds:
                time.sleep(args.hold_seconds)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


if __name__ == "__main__":
    main()

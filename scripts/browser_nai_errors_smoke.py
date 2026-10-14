"""Localized errors through UI, HTTP, queue and history; synthetic network only."""
import argparse
import errno
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
from anima_app.providers.novelai import detailer, service
from anima_app.providers.novelai.errors import MESSAGES
from anima_app.providers.novelai.wd_tagger import WDTagger
from anima_app.server import create_http_server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/nai-update-20261011/errors/browser"))
    parser.add_argument("--hold-seconds", type=int, default=0)
    args = parser.parse_args()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    calls, errors, blocked, cases = [], [], [], []
    mode, tagger_mode = 401, "disk"
    count = 0
    original_save = service.write_verified_png

    def forbidden(*a, **k):
        blocked.append("external HTTP attempted")
        raise AssertionError("External HTTP forbidden")

    def transport(url, headers, body, timeout):
        nonlocal count
        count += 1
        payload = json.loads(body)
        calls.append({"mode": mode, "model": payload["model"]})
        if isinstance(mode, int):
            message = json.dumps({"message": "synthetic-diagnostics-secret expired", "error": "test message"}).encode()
            raise urllib.error.HTTPError(url, mode, "private raw", {"Retry-After": "0"}, io.BytesIO(message))
        if mode == "timeout" or (mode == "partial" and count == 3):
            raise requests.Timeout("synthetic-diagnostics-secret")
        if mode == "archive":
            return b"invalid archive"
        params = payload["parameters"]
        png, archive = io.BytesIO(), io.BytesIO()
        Image.new("RGB", (params["width"], params["height"]), "purple").save(png, format="PNG")
        with zipfile.ZipFile(archive, "w") as zipped:
            zipped.writestr("image.png", png.getvalue())
        return archive.getvalue()

    def save(*args):
        if mode == "save":
            raise OSError(errno.ENOSPC, "unlabelled secret")
        return original_save(*args)

    def prepare(*a, **k):
        if tagger_mode == "disk":
            raise OSError(errno.ENOSPC, "unlabelled secret")

    def detect(self, source, cancelled):
        result = []
        for box in ((20, 30, 40, 50), (100, 30, 120, 50)):
            mask = Image.new("L", source.size)
            ImageDraw.Draw(mask).rectangle(box, fill=255)
            result.append(detailer.Region(box, mask))
        return result

    with (tempfile.TemporaryDirectory(prefix="anima-errors-smoke-") as temporary,
          patch.dict(os.environ, {"NAI_ACCESS_TOKEN": "synthetic-diagnostics-secret", "NAI_API_TOKEN": ""}),
          patch.object(requests.sessions.Session, "request", forbidden),
          patch.object(novelai.client, "_requests_transport", transport),
          patch.object(novelai.client, "_requests_subscription_transport",
                       lambda *a: b'{"active":true,"tier":3,"usage":{"percent":100,"isNegative":false}}'),
          patch.object(novelai.client, "REQUEST_INTERVAL_SECONDS", 0),
          patch.object(novelai.client, "_request_coordinator", novelai.client.RequestCoordinator()),
          patch.object(service, "write_verified_png", save),
          patch.object(WDTagger, "prepare", prepare),
          patch.object(detailer.Detector, "preflight", lambda _: None),
          patch.object(detailer.Detector, "detect", detect)):
        paths = AppPaths(Path(temporary), autocomplete_source=Path(temporary) / "autocomplete.txt")
        server = create_http_server("127.0.0.1", 0, paths=paths)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        address = f"http://127.0.0.1:{server.server_address[1]}"
        print(json.dumps({"address": address}), flush=True)
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                context = browser.new_context(viewport={"width": 1500, "height": 1000}, locale="ko-KR")
                context.route("**/*", lambda r: r.continue_() if urlparse(r.request.url).hostname == "127.0.0.1" else r.abort())
                page = context.new_page()
                page.on("pageerror", lambda e: errors.append(str(e)))
                page.goto(address, wait_until="networkidle")
                page.locator("#provider-select").select_option("novelai")
                language = page.locator("#nai-language")
                language.select_option("ko")
                for name, value in {"prompt": "synthetic test", "width": "256", "height": "128"}.items():
                    page.locator(f'[name="{name}"]').fill(value)
                guide = page.locator("#nai-error-guide")

                language.select_option("ja")
                page.locator("#generation-prompt-tools").evaluate("e=>e.open=true")
                page.locator("#prompt-converter > summary").click()
                page.locator('[name="prompt"]').fill("(" * 65 + "private prompt" + ")" * 65)
                page.locator("#convert-preview").click()
                conversion_guide = page.locator("#nai-convert-error-guide")
                expect(conversion_guide).to_contain_text(MESSAGES["ja"]["PROMPT_CONVERSION"][0])
                language.select_option("ko")
                expect(conversion_guide).to_contain_text(MESSAGES["ko"]["PROMPT_CONVERSION"][0])
                page.locator('[name="prompt"]').fill("synthetic test")
                expect(conversion_guide).to_be_hidden()
                cases.append("converter rejection localizes in place and clears on corrected input")

                page.locator("#generation-import").evaluate("e=>e.open=true")
                png = io.BytesIO()
                Image.new("RGB", (64, 64)).save(png, format="PNG")
                page.locator("#nai-metadata-file").set_input_files({"name": "synthetic-no-metadata.png", "mimeType": "image/png", "buffer": png.getvalue()})
                metadata_guide = page.locator("#nai-metadata-error-guide")
                expect(metadata_guide).to_contain_text(MESSAGES["ko"]["METADATA_INPUT"][0])
                language.select_option("ja")
                expect(metadata_guide).to_contain_text(MESSAGES["ja"]["METADATA_INPUT"][0])
                language.select_option("ko")
                assert not calls
                cases.append("real metadata upload rejection gives bilingual guidance without generation")

                def generate(selected, cause=None, locale="ko"):
                    nonlocal mode, count
                    mode, count = selected, 0
                    before = len(calls)
                    page.locator("#generate-button").click()
                    page.wait_for_function("!queueRunning && document.querySelector('#result').textContent.startsWith('{')")
                    result = json.loads(page.locator("#result").text_content())
                    if cause:
                        expect(guide).to_be_visible()
                        expect(guide).to_contain_text(MESSAGES[locale][cause][0])
                    assert "synthetic-diagnostics-secret" not in json.dumps(result)
                    return result, len(calls) - before

                result, attempts = generate(401, "NAI_AUTH")
                assert attempts == 1 and result["error_detail"]["http_status"] == 401
                language.select_option("ja")
                expect(guide).to_contain_text(MESSAGES["ja"]["NAI_AUTH"][1])
                guide.locator("details").first.evaluate("e=>e.open=true")
                expect(guide).to_contain_text("HTTP 401")
                expect(guide).to_contain_text("[redacted]")
                page.screenshot(path=str(output / "authentication-ja.png"), full_page=True)
                language.select_option("en")
                expect(guide).to_contain_text(MESSAGES["en"]["NAI_AUTH"][1])
                expect(guide).to_contain_text("Error and next steps")
                language.select_option("ko")
                cases.append("401 cause/action/status/body with token masking and live locale switch")
                _, attempts = generate(403, "NAI_FORBIDDEN")
                assert attempts == 1
                cases.append("403 remains access refusal instead of asserting an authentication cause")
                _, attempts = generate(429, "NAI_RATE_LIMIT")
                assert attempts == 2
                cases.append("429 stops after the existing single retry with actionable guidance")
                result, attempts = generate("timeout", "NAI_TIMEOUT")
                assert attempts == 1 and result["remote_outcome_unknown"]
                expect(guide).to_contain_text("자동 재전송하지")
                cases.append("timeout retains unknown remote outcome and no automatic resubmission")
                result, attempts = generate("archive", "IMAGE_RESPONSE")
                assert attempts == 1 and result["remote_outcome_unknown"]
                cases.append("invalid archive explains response failure after image submission")
                result, attempts = generate("save", "DISK_FULL")
                assert attempts == 1 and not result["remote_outcome_unknown"]
                assert result["error_detail"]["stage"] == "output_save"
                cases.append("disk-full after response shows output-save stage and known remote outcome")
                _, attempts = generate("success")
                assert attempts == 1
                expect(guide).to_be_hidden()
                cases.append("new successful result clears stale error state")

                page.locator("#nai-detailer-panel").evaluate("e=>e.open=true")
                page.locator("#nai-tagger-prepare").evaluate("e=>{for(let p=e.parentElement;p;p=p.parentElement){if(p.tagName==='DETAILS')p.open=true;}}")
                page.locator("#nai-tagger-prepare").click()
                tagger_guide = page.locator("#nai-tagger-error-guide")
                expect(tagger_guide).to_contain_text(MESSAGES["ko"]["DISK_FULL"][0])
                language.select_option("ja")
                expect(tagger_guide).to_contain_text(MESSAGES["ja"]["DISK_FULL"][1])
                tagger_mode = "ready"
                page.locator("#nai-tagger-prepare").evaluate("e=>{for(let p=e.parentElement;p;p=p.parentElement){if(p.tagName==='DETAILS')p.open=true;}}")
                page.locator("#nai-tagger-prepare").click()
                expect(tagger_guide).to_be_hidden()
                page.wait_for_function("taggerJob?.status==='ready'")
                cases.append("tagger resource failure, language switch, retry and stale-error clearing")

                page.locator("#nai-detailer-enabled").check()
                page.locator("#nai-detailer-mode").select_option("all")
                result, attempts = generate("partial", "NAI_TIMEOUT", "ja")
                assert attempts == 3 and (result.get("stop_scheduling") or result.get("novelai", {}).get("detailer_failure")), result
                expect(guide).to_contain_text("完了済み")
                name = Path(result["manifest_path"]).name
                page.reload(wait_until="networkidle")
                page.evaluate("name=>openManifest(name)", name)
                expect(guide).to_contain_text(MESSAGES["ja"]["NAI_TIMEOUT"][0])
                language.select_option("ko")
                expect(guide).to_contain_text(MESSAGES["ko"]["NAI_TIMEOUT"][0])
                expect(guide).to_contain_text("보존")
                cases.append("partial detailer failure keeps output and localizable diagnostics across real history reload")
                (output / "partial-manifest.json").write_text(json.dumps(json.loads((paths.manifest_root / name).read_text()), ensure_ascii=False, indent=2) + "\n")

                # Treat even old/untrusted error records as plain text, never HTML.
                malicious = {"provider": "novelai", "error_detail": {"code": "UNKNOWN", "stage": "validation",
                    "details": "<img src=x onerror=alert(1)>", "messages": {"en": ["<b>literal</b>", "<script>alert(1)</script>"]}}}
                page.evaluate("p=>setResultPayload(p)", malicious)
                expect(guide).to_contain_text("<b>literal</b>")
                assert guide.locator("img,script,b").count() == 0
                page.evaluate("()=>setResultPayload({error:'old NAI error',provider:'novelai'})")
                expect(guide).to_be_hidden()
                cases.append("English fallback, legacy payload compatibility and plain-text error rendering")

                page.evaluate("name=>openManifest(name)", name)
                page.set_viewport_size({"width": 420, "height": 900})
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth+1")
                page.screenshot(path=str(output / "partial-error-mobile.png"), full_page=True)
                assert not errors and not blocked
                browser.close()
            report = {"cases": cases, "page_errors": errors, "external_http_attempts": blocked,
                      "live_nai_calls": 0, "synthetic_image_attempts": len(calls), "address": address,
                      "history_manifest": name}
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

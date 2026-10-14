"""Exercise tagger preparation and matching via the real UI/API/queue, with local fixtures."""
import argparse
import json
import os
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlparse

import httpx
import requests
from PIL import Image, ImageDraw
from playwright.sync_api import expect, sync_playwright

from anima_app.config import AppPaths
from anima_app.providers import novelai
from anima_app.providers.novelai import detailer
from anima_app.providers.novelai.errors import NovelAIError
from anima_app.providers.novelai.wd_tagger import DEFAULT_MODEL, MODELS, PIXAI_MODEL, WDTagger, model_files
from anima_app.server import create_http_server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/nai-update-20261011/tagger/browser"))
    parser.add_argument("--hold-seconds", type=int, default=0)
    args = parser.parse_args()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    prepared, errors, blocked, cases, loads = set(), [], [], [], []
    mode = "success"

    def forbidden(*a, **k):
        blocked.append("remote request attempted")
        raise AssertionError("Remote request forbidden")

    def prepare(self, *, allow_download=False, progress=None):
        if not allow_download:
            if self.model_name not in prepared:
                raise NovelAIError("tagger_cache_missing", "선택한 태거를 먼저 준비하세요.", 400)
            return self
        if mode == "dependency":
            raise NovelAIError("tagger_dependency", 'PixAI 의존성 누락. pip install -e ".[pixai-matching]"', 400)
        loads.append(self.model_name)
        for filename in model_files(self.model_name):
            progress.report(f"Checking cache: {filename}", force=True)
            if self.model_name in prepared:
                progress.report(f"File ready: {filename}", 1, force=True)
                continue
            with progress.download_bar(filename)(total=1024 * 1024) as bar:
                for _ in range(8):
                    time.sleep(.1)
                    bar.update(128 * 1024)
            progress.report(f"File ready: {filename}", 1, force=True)
        progress.report(f"Ready: {self.model_name}", 1, force=True)
        prepared.add(self.model_name)
        return self

    def score(self, images):
        assert self.model_name in prepared
        return [{"red_hair": .95, "blue_hair": .02, "never_insert_this": .999} for _ in images]

    def detect(self, source, cancelled):
        box = (20, 30, 50, 60)
        mask = Image.new("L", source.size)
        ImageDraw.Draw(mask).rectangle(box, fill=255)
        return [detailer.Region(box, mask)]

    with (tempfile.TemporaryDirectory(prefix="anima-tagger-browser-") as temporary,
          patch.dict(os.environ, {"NAI_ACCESS_TOKEN": "", "NAI_API_TOKEN": ""}),
          patch.object(requests.sessions.Session, "request", forbidden),
          patch.object(httpx.Client, "send", forbidden),
          patch.object(novelai.service, "get_token", forbidden),
          patch.object(novelai.client, "_requests_transport", forbidden),
          patch.object(novelai.client, "_requests_subscription_transport", forbidden),
          patch.object(detailer.Detector, "preflight", lambda _: None),
          patch.object(detailer.Detector, "detect", detect),
          patch.object(WDTagger, "prepare", prepare), patch.object(WDTagger, "score", score)):
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
                page = browser.new_page(locale="ko-KR", viewport={"width": 1500, "height": 1100})
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.route("**/*", lambda route: route.continue_() if urlparse(route.request.url).hostname == "127.0.0.1" else route.abort())
                page.goto(address, wait_until="networkidle")
                page.locator("#provider-select").select_option("novelai")
                page.locator("#nai-detailer-panel").evaluate("e=>e.open=true")
                assert page.locator("#nai-detailer-wd_model option").all_text_contents() == list(MODELS)
                expect(page.locator("#nai-detailer-wd_model")).to_have_value(DEFAULT_MODEL)
                cases.append("three-model selector; old/default requests use WD ViT")

                page.locator("#nai-detailer-wd_model").select_option(PIXAI_MODEL)
                expect(page.locator("#nai-tagger-hint")).to_contain_text("pixai-matching")
                page.locator("#nai-tagger-prepare").click()
                expect(page.locator("#nai-tagger-status")).to_contain_text("MiB", timeout=10000)
                expect(page.locator("#nai-tagger-prepare")).to_be_disabled()
                page.screenshot(path=str(output / "download-progress.png"), full_page=True)
                page.locator("#nai-tagger-cancel").click()
                expect(page.locator("#nai-tagger-status")).to_contain_text("취소됨", timeout=10000)
                expect(page.locator("#nai-tagger-prepare")).to_be_enabled()
                assert PIXAI_MODEL not in prepared
                cases.append("per-file byte progress and cancel; no ready state on cancelled preparation")

                mode = "dependency"
                page.locator("#nai-tagger-prepare").click()
                expect(page.locator("#nai-tagger-status")).to_contain_text("태거 필수 패키지", timeout=10000)
                expect(page.locator("#nai-tagger-status")).to_contain_text("실패")
                expect(page.locator("#nai-tagger-error-guide")).to_contain_text("TAGGER_DEPENDENCY")
                expect(page.locator("#nai-tagger-error-guide")).to_contain_text("pixai-matching")
                expect(page.locator("#nai-tagger-prepare")).to_be_enabled()
                cases.append("dependency error shows PixAI extra; retry button re-enabled")
                mode = "success"

                page.locator('[name="prompt"]').fill("shared scene")
                page.locator('[name="width"]').fill("256")
                page.locator('[name="height"]').fill("128")
                page.locator("#nai-operation").select_option("detail")
                page.locator("#nai-input-file").set_input_files(source)
                expect(page.locator('[name="input_image"]')).not_to_have_value("")
                page.locator("#nai-detailer-preview").check()
                page.locator("#nai-detailer-matching").select_option("wd14")
                page.locator("#nai-characters-panel").evaluate("e=>e.open=true")
                page.locator("#nai-add-character").click()
                page.locator(".character-prompt").last.fill("1.2::red hair::")
                page.locator("#generate-button").click()
                expect(page.locator("#result")).to_contain_text("선택한 태거를 먼저 준비", timeout=15000)
                assert not list(paths.manifest_root.glob("*.json"))
                cases.append("unprepared model rejects preview before NAI or output creation")

                last_manifest = None
                for name in MODELS:
                    page.locator("#nai-detailer-wd_model").select_option(name)
                    page.locator("#nai-tagger-prepare").click()
                    expect(page.locator("#nai-tagger-status")).to_contain_text("준비 완료", timeout=15000)
                    expect(page.locator("#nai-tagger-status")).to_contain_text(name)
                    expect(page.locator("#nai-tagger-prepare")).to_be_enabled()
                    before = set(paths.manifest_root.glob("*.json"))
                    page.locator("#generate-button").click()
                    deadline = time.monotonic() + 15
                    while not (set(paths.manifest_root.glob("*.json")) - before):
                        if time.monotonic() > deadline:
                            raise AssertionError(page.locator("#result").inner_text())
                        page.wait_for_timeout(50)
                    expect(page.locator("#stop-queue")).to_be_disabled(timeout=10000)
                    expect(page.locator("#result-summary")).to_contain_text(name)
                    manifest = json.loads(next(iter(set(paths.manifest_root.glob("*.json")) - before)).read_text())
                    assert manifest["novelai"]["requested"]["nai_detailer"]["wd_model"] == name
                    assert manifest["novelai"]["detailer"][0]["tagger"]["revision"] == MODELS[name][1]
                    assert "never_insert_this" not in json.dumps(manifest)
                    page.locator("#nai-detailer-wd_model").select_option(next(n for n in MODELS if n != name))
                    page.locator("#apply-manifest").click()
                    expect(page.locator("#nai-detailer-wd_model")).to_have_value(name)
                    last_manifest = manifest
                    cases.append(f"{name}: preparation, local matching preview, selected model/revision audit and history restore")

                started = time.monotonic()
                page.locator("#nai-tagger-prepare").click()
                expect(page.locator("#nai-tagger-status")).to_contain_text("준비 완료", timeout=5000)
                expect(page.locator("#nai-tagger-prepare")).to_be_enabled()
                assert time.monotonic() - started < 3
                cases.append("cache reuse prepares without byte download")
                with Image.open(last_manifest["output_path"]) as image:
                    assert json.loads(image.info["Comment"])["anima_app_detailer"]["wd_model"] == PIXAI_MODEL
                page.locator("#nai-detailer-wd_model").select_option(DEFAULT_MODEL)
                page.locator("#nai-metadata-file").set_input_files(last_manifest["output_path"])
                expect(page.locator("#apply-nai-metadata")).to_be_enabled()
                page.locator("#apply-nai-metadata").click()
                expect(page.locator("#nai-detailer-wd_model")).to_have_value(PIXAI_MODEL)
                cases.append("PNG metadata import restores selected model and detailer settings")
                page.screenshot(path=str(output / "tagger-history.png"), full_page=True)
                assert not errors and not blocked
                browser.close()
            report = {"cases": cases, "page_errors": errors, "blocked_requests": blocked, "address": address,
                      "live_nai_calls": 0, "real_downloads": 0, "scope": "synthetic models/downloads/detections; real UI/API/queue/metadata"}
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

"""Current UI/queue Medium acceptance with synthetic account, image and detector responses."""
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
from unittest.mock import patch
from urllib.parse import urlparse

import requests
from PIL import Image, ImageDraw
from PIL.PngImagePlugin import PngInfo
from playwright.sync_api import expect, sync_playwright

from anima_app.config import AppPaths
from anima_app.providers import novelai
from anima_app.providers.novelai import detailer
from anima_app.providers.novelai.medium import MEDIUM_MODEL, valid_medium_payload
from anima_app.server import create_http_server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/nai-update-20261011/medium/browser"))
    parser.add_argument("--hold-seconds", type=int, default=0, help="Keep synthetic server for dedicated Firefox inspection")
    args = parser.parse_args()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    calls, accounts, errors, blocked, cases = [], [], [], [], []
    allowance = 100

    def forbidden(*a, **k):
        blocked.append("external HTTP attempted")
        raise AssertionError("External HTTP forbidden")

    def transport(url, headers, body, timeout):
        payload = json.loads(body)
        assert valid_medium_payload(payload)
        calls.append(payload)
        params = payload["parameters"]
        png, archive = io.BytesIO(), io.BytesIO()
        Image.new("RGB", (params["width"], params["height"]), "purple").save(png, format="PNG")
        with zipfile.ZipFile(archive, "w") as zipped:
            zipped.writestr("image.png", png.getvalue())
        return archive.getvalue()

    def subscription(*a):
        accounts.append(allowance)
        return json.dumps({"active": True, "tier": 3, "usage": {"percent": allowance, "isNegative": False}}).encode()

    def detect(self, source, cancelled):
        mask = Image.new("L", source.size)
        ImageDraw.Draw(mask).rectangle((70, 35, 90, 55), fill=255)
        return [detailer.Region((70, 35, 90, 55), mask)]

    with (tempfile.TemporaryDirectory(prefix="anima-medium-smoke-") as temporary,
          patch.dict(os.environ, {"NAI_ACCESS_TOKEN": "synthetic-medium-token", "NAI_API_TOKEN": ""}),
          patch.object(requests.sessions.Session, "request", forbidden),
          patch.object(novelai.client, "_requests_transport", transport),
          patch.object(novelai.client, "_requests_subscription_transport", subscription),
          patch.object(novelai.client, "REQUEST_INTERVAL_SECONDS", 0),
          patch.object(detailer.Detector, "preflight", lambda _: None),
          patch.object(detailer.Detector, "detect", detect)):
        root = Path(temporary)
        source, mask_path, metadata_path = root / "source.png", root / "mask.png", root / "medium.png"
        Image.new("RGB", (256, 128), "green").save(source)
        mask = Image.new("L", (256, 128))
        ImageDraw.Draw(mask).rectangle((70, 35, 90, 55), fill=255)
        mask.save(mask_path)
        info = PngInfo()
        info.add_text("Software", "NovelAI")
        info.add_text("Source", "NovelAI Diffusion V5 70AB5786")
        info.add_text("Comment", json.dumps({"prompt": "a flower", "uc": "old negative", "width": 256, "height": 128,
                                             "request_type": "NativeInfillingRequest", "inpaintImg2ImgStrength": .4}))
        Image.new("RGB", (256, 128), "white").save(metadata_path, pnginfo=info)
        paths = AppPaths(root, autocomplete_source=root / "autocomplete.txt")
        server = create_http_server("127.0.0.1", 0, paths=paths)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        address = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                page = browser.new_page(locale="ko-KR", viewport={"width": 1500, "height": 1000})
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.route("**/*", lambda route: route.continue_() if urlparse(route.request.url).hostname == "127.0.0.1" else route.abort())
                page.goto(address, wait_until="networkidle")
                page.locator("#provider-select").select_option("novelai")
                page.locator("#nai-model").select_option(MEDIUM_MODEL)
                page.locator('[name="prompt"]').fill("a flower")
                page.locator('[name="negative_prompt"]').fill("user negative")
                for name, value in {"width": "256", "height": "128", "steps": "40", "seed": "0", "cfg": "0"}.items():
                    page.locator(f'[name="{name}"]').fill(value)
                expect(page.locator("#nai-medium-notice")).to_contain_text("14스텝")
                page.locator("#nai-model").select_option("nai-diffusion-5-full")
                expect(page.locator("#nai-medium-notice")).to_be_hidden()
                expect(page.locator('[name="steps"]')).to_have_value("40")
                expect(page.locator('[name="negative_prompt"]')).to_have_value("user negative")
                page.locator("#nai-model").select_option(MEDIUM_MODEL)
                cases.append("model switch preserves user input and displays fixed settings")

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
                    manifest = json.loads(next(iter(set(paths.manifest_root.glob("*.json")) - before)).read_text())
                    return manifest

                manifest = generate()
                assert calls[-1]["parameters"]["seed"] == calls[-1]["parameters"]["scale"] == 0
                assert manifest["novelai"]["requested"]["steps"] == 40 and manifest["steps"] == 14
                page.locator("#apply-manifest").click()
                expect(page.locator("#nai-model")).to_have_value(MEDIUM_MODEL)
                expect(page.locator('[name="steps"]')).to_have_value("14")
                cases.append("protected T2I queue, transmitted defaults and history restoration")

                allowance = 1
                previous = len(calls)
                page.locator("#generate-button").click()
                expect(page.locator("#result")).to_contain_text("2%", timeout=10000)
                expect(page.locator("#stop-queue")).to_be_disabled()
                assert len(calls) == previous
                allowance = 100
                cases.append("V5 low allowance blocks before image transport")

                page.locator("#nai-operation").select_option("img2img")
                page.locator("#nai-input-file").set_input_files(source)
                expect(page.locator('[name="input_image"]')).not_to_have_value("")
                assert not page.locator("#generate-form").evaluate("f=>f.checkValidity()")
                page.locator('label[for="nai-limit-opus-free"]').click()
                page.locator('[name="img2img_strength"]').fill("0")
                generate()
                assert calls[-1]["action"] == "img2img" and calls[-1]["parameters"]["strength"] == 0
                cases.append("Medium Img2Img cost control and zero strength")

                page.locator("#nai-metadata-file").set_input_files(metadata_path)
                expect(page.locator("#nai-metadata-model")).to_have_value(MEDIUM_MODEL + "-inpainting")
                page.locator("#apply-nai-metadata").click()
                expect(page.locator("#nai-operation")).to_have_value("infill")
                page.locator("#nai-input-file").set_input_files(source)
                expect(page.locator('[name="input_image"]')).not_to_have_value("")
                page.locator("#nai-mask-file").set_input_files(mask_path)
                expect(page.locator('[name="mask_image"]')).not_to_have_value("")
                generate()
                assert calls[-1]["model"] == MEDIUM_MODEL + "-inpainting"
                assert calls[-1]["parameters"]["img2img"] == {"strength": .4, "color_correct": True}
                cases.append("Medium hash metadata restores dedicated infill and partial API strength")

                page.locator("#nai-operation").select_option("focused_infill")
                page.locator('label[for="nai-limit-opus-free"]').click()
                generate()
                assert calls[-1]["parameters"]["steps"] == 14
                cases.append("protected Medium Focused crop uses fixed settings")

                page.locator("#nai-operation").select_option("detail")
                page.locator("#nai-model").select_option(MEDIUM_MODEL)
                page.locator("#nai-detailer-panel").evaluate("e=>e.open=true")
                page.locator("#nai-detailer-strength").fill("0.3")
                manifest = generate()
                assert calls[-1]["parameters"]["img2img"] == {"strength": .3, "color_correct": True}
                assert manifest["novelai"]["detailer"][0]["transmitted_steps"] == 14
                page.locator("#apply-manifest").click()
                expect(page.locator("#nai-detailer-strength")).to_have_value("0.3")
                cases.append("Medium automatic detailer crop, API strength and history")
                page.screenshot(path=str(output / "medium.png"), full_page=True)
                assert not errors and not blocked
                browser.close()
            report = {"cases": cases, "page_errors": errors, "external_http_attempts": blocked,
                      "live_nai_calls": 0, "synthetic_generations": len(calls), "synthetic_account_checks": len(accounts),
                      "transmitted": [{"model": p["model"], "action": p["action"], "steps": p["parameters"]["steps"],
                                       "partial_strength": p["parameters"].get("img2img")} for p in calls]}
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

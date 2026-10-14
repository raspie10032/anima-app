"""NAI inpaint browser acceptance using only synthetic images and a mock transport."""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import tempfile
import threading
import zipfile
from pathlib import Path
from urllib.parse import urlparse

import requests
from PIL import Image, ImageDraw
from PIL.PngImagePlugin import PngInfo
from playwright.sync_api import expect, sync_playwright

from anima_app.config import AppPaths
from anima_app.providers import novelai
from anima_app.server import create_http_server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/inpaint-smoke"))
    output = parser.parse_args().output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    original_transport = novelai.client._requests_transport
    original_post = requests.post
    original_env = {key: os.environ.get(key) for key in ("NAI_ACCESS_TOKEN", "NAI_API_TOKEN")}
    os.environ["NAI_ACCESS_TOKEN"] = "synthetic-inpaint-browser-token"
    os.environ.pop("NAI_API_TOKEN", None)
    captured, errors = [], []
    entered, release = threading.Event(), threading.Event()

    def forbid_remote(*a, **k):
        raise AssertionError("External HTTP is disabled in this test")

    def transport(url, headers, body, timeout):
        payload = json.loads(body)
        captured.append(payload)
        entered.set()
        assert release.wait(15)
        png = io.BytesIO()
        Image.new("RGB", (payload["parameters"]["width"], payload["parameters"]["height"]), "purple").save(png, format="PNG")
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w") as zipped:
            zipped.writestr("image.png", png.getvalue())
        return archive.getvalue()

    novelai.client._requests_transport = transport
    requests.post = forbid_remote
    server = None
    try:
        with tempfile.TemporaryDirectory(prefix="anima-inpaint-smoke-") as temporary:
            root = Path(temporary)
            paths = AppPaths(project_root=root, autocomplete_source=root / "autocomplete.txt")
            source = root / "source.png"
            mask = root / "mask.png"
            Image.new("RGB", (128, 128), "green").save(source)
            mask_image = Image.new("L", (128, 128), 0)
            ImageDraw.Draw(mask_image).rectangle((32, 32, 95, 95), fill=255)
            mask_image.save(mask)
            invalid = root / "wrong-size.png"
            Image.new("L", (64, 64), 255).save(invalid)
            metadata = root / "infill-metadata.png"
            info = PngInfo()
            info.add_text("Software", "NovelAI")
            info.add_itxt("Comment", json.dumps({"model": "nai-diffusion-5-full-inpainting", "prompt": "a flower",
                                               "uc": "", "width": 128, "height": 128, "scale": 0, "seed": 0,
                                               "request_type": "NativeInfillingRequest", "img2img": {"strength": 0.5}}))
            Image.new("RGB", (128, 128), "green").save(metadata, pnginfo=info)
            server = create_http_server("127.0.0.1", 0, paths=paths)
            threading.Thread(target=server.serve_forever, daemon=True).start()
            address = f"http://127.0.0.1:{server.server_address[1]}"
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                page = browser.new_page(locale="ko-KR", viewport={"width": 1600, "height": 1100})
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.route("**/*", lambda route: route.continue_() if urlparse(route.request.url).hostname == "127.0.0.1" else route.abort())
                page.goto(address, wait_until="networkidle")
                page.locator("#provider-select").select_option("novelai")
                page.locator("#nai-model").select_option("nai-diffusion-5-curated")
                page.locator("#nai-operation").select_option("infill")
                expect(page.locator("#nai-model")).to_have_value("nai-diffusion-4-5-curated-inpainting")
                # Import restores the exact infill model, clears inputs, preserves the cost setting.
                page.locator("#nai-metadata-file").set_input_files(metadata)
                expect(page.locator("#apply-nai-metadata")).to_be_enabled()
                page.locator("#apply-nai-metadata").click()
                expect(page.locator("#nai-model")).to_have_value("nai-diffusion-5-full-inpainting")
                expect(page.locator("#nai-inpaint-strength")).to_have_value("0.5")
                expect(page.locator('[name="nai_limit_opus_free"]')).to_be_checked()
                assert not captured
                page.locator("#nai-input-file").set_input_files(source)
                expect(page.locator('[name="input_image"]')).not_to_have_value("")
                page.locator("#nai-mask-file").set_input_files(invalid)
                expect(page.locator("#nai-inpaint-status")).to_contain_text("크기가 다릅니다")
                expect(page.locator('[name="mask_image"]')).to_have_value("")
                page.locator("#nai-mask-file").set_input_files(mask)
                expect(page.locator('[name="mask_image"]')).not_to_have_value("")
                assert not page.locator("#generate-form").evaluate("form => form.checkValidity()")
                page.locator('label[for="nai-limit-opus-free"]').click()
                assert page.locator("#generate-form").evaluate("form => form.checkValidity()")
                # Draw with original-pixel coordinates under a resized CSS canvas.
                page.locator("#nai-brush-size").fill("16")
                canvas = page.locator("#nai-mask-canvas")
                canvas.scroll_into_view_if_needed()
                box = canvas.bounding_box()
                page.mouse.click(box["x"] + box["width"] * 0.5, box["y"] + box["height"] * 0.5)
                expect(page.locator('[name="mask_image"]')).to_have_value("")
                page.locator("#nai-mask-save").click()
                expect(page.locator('[name="mask_image"]')).not_to_have_value("")
                page.locator("#nai-mask-editor").screenshot(path=str(output / "mask-editor.png"))
                page.locator("#generate-button").click()
                assert entered.wait(10), "mock transport was not submitted"
                page.reload(wait_until="networkidle")
                expect(page.locator("#stop-queue")).to_be_enabled()
                release.set()
                expect(page.locator("#stop-queue")).to_be_disabled(timeout=20000)
                assert len(captured) == 1
                request = captured[0]
                assert request["model"] == "nai-diffusion-5-full-inpainting"
                assert request["action"] == "infill"
                assert request["parameters"]["img2img"]["strength"] == 0.5
                expect(page.locator("#preview")).to_be_visible()
                page.locator("#apply-manifest").click()
                expect(page.locator("#provider-select")).to_have_value("novelai")
                expect(page.locator("#nai-operation")).to_have_value("infill")
                expect(page.locator("#nai-model")).to_have_value("nai-diffusion-5-full-inpainting")
                expect(page.locator('[name="input_image"]')).not_to_have_value("")
                expect(page.locator('[name="mask_image"]')).not_to_have_value("")
                page.locator("#nai-use-result").click()
                expect(page.locator('[name="input_image"]')).to_have_value(re.compile(r"outputs/images/.+"))
                expect(page.locator('[name="mask_image"]')).to_have_value("")
                page.screenshot(path=str(output / "inpaint-result.png"))
                assert not errors, errors
                browser.close()
            manifests = list(paths.manifest_root.glob("*.json"))
            assert len(manifests) == 1
            manifest = json.loads(manifests[0].read_text())
            with Image.open(manifest["output_path"]) as image:
                assert image.getpixel((0, 0)) == (0, 128, 0)
                assert image.getpixel((64, 64)) == (128, 0, 128)
                image.save(output / "composited-mock.png")
            report = {"status": "passed", "mock_remote_submissions": len(captured), "page_errors": errors,
                      "live_requests": 0, "model": captured[0]["model"], "outside_mask_preserved": True,
                      "checked": ["V5 Curated routes to V4.5 Curated infill", "metadata mode/model/strength",
                                  "explicit cost permission control", "upload size rejection", "paint and save mask",
                                  "reload while submitted without duplicate", "manifest restore", "reuse current result"]}
            (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
            print(json.dumps(report, ensure_ascii=False, indent=2))
    finally:
        release.set()
        if server:
            server.shutdown()
            server.server_close()
        novelai.client._requests_transport = original_transport
        requests.post = original_post
        for key, value in original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


if __name__ == "__main__":
    main()

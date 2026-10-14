"""Real UI/API/queue character acceptance, synthetic NAI transport only."""
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
from PIL import Image
from PIL.PngImagePlugin import PngInfo
from playwright.sync_api import expect, sync_playwright

from anima_app.config import AppPaths
from anima_app.providers import novelai
from anima_app.providers.novelai.metadata import read_image_metadata
from anima_app.server import create_http_server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/nai-update-20261011/characters/browser"))
    parser.add_argument("--hold-seconds", type=int, default=0)
    args = parser.parse_args()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    calls, errors, blocked, cases = [], [], [], []

    def forbidden(*a, **k):
        blocked.append("external HTTP attempted")
        raise AssertionError("External HTTP forbidden")

    def transport(url, headers, body, timeout):
        payload = json.loads(body)
        calls.append(payload)
        params = payload["parameters"]
        png, archive = io.BytesIO(), io.BytesIO()
        info = PngInfo()
        info.add_text("Software", "NovelAI")
        info.add_itxt("Comment", json.dumps({"model": payload["model"], "request_type": "PromptGenerateRequest", **params}))
        Image.new("RGB", (params["width"], params["height"]), "purple").save(png, format="PNG", pnginfo=info)
        with zipfile.ZipFile(archive, "w") as zipped:
            zipped.writestr("image.png", png.getvalue())
        return archive.getvalue()

    with (tempfile.TemporaryDirectory(prefix="anima-character-smoke-") as temporary,
          patch.dict(os.environ, {"NAI_ACCESS_TOKEN": "synthetic-character-token", "NAI_API_TOKEN": ""}),
          patch.object(requests.sessions.Session, "request", forbidden),
          patch.object(novelai.client, "_requests_transport", transport),
          patch.object(novelai.client, "_requests_subscription_transport",
                       lambda *a: b'{"active":true,"tier":3,"usage":{"percent":100,"isNegative":false}}'),
          patch.object(novelai.client, "REQUEST_INTERVAL_SECONDS", 0)):
        paths = AppPaths(Path(temporary), autocomplete_source=Path(temporary) / "autocomplete.txt")
        server = create_http_server("127.0.0.1", 0, paths=paths)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        address = f"http://127.0.0.1:{server.server_address[1]}"
        print(json.dumps({"address": address}), flush=True)
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                page = browser.new_page(locale="ko-KR", viewport={"width": 1550, "height": 1050})
                page.on("pageerror", lambda e: errors.append(str(e)))
                page.route("**/*", lambda r: r.continue_() if urlparse(r.request.url).hostname == "127.0.0.1" else r.abort())
                page.goto(address, wait_until="networkidle")
                page.locator("#provider-select").select_option("novelai")
                page.locator("#nai-model").select_option("nai-diffusion-5-full")
                for name, value in {"prompt": "scene", "width": "64", "height": "64", "seed": "0"}.items():
                    page.locator(f'[name="{name}"]').fill(value)
                page.locator("#nai-characters-panel").evaluate("e=>e.open=true")
                count = page.locator("#nai-character-count")
                count.fill("22")
                rows = page.locator("#nai-characters .nai-character")
                expect(rows).to_have_count(22)
                for i in range(22):
                    rows.nth(i).locator(".character-prompt").fill(f"character {i + 1}")
                    rows.nth(i).locator(".character-negative").fill(f"negative {i + 1}")
                rows.nth(21).locator(".character-x").fill("0")
                rows.nth(21).locator(".character-y").fill("1")
                expect(page.locator("#nai-add-character")).to_be_disabled()

                def generate():
                    before = set(paths.manifest_root.glob("*.json"))
                    page.locator("#generate-button").click()
                    deadline = time.monotonic() + 20
                    while not (set(paths.manifest_root.glob("*.json")) - before):
                        if time.monotonic() > deadline:
                            raise AssertionError("generation failed: " + page.locator("#result").inner_text())
                        page.wait_for_timeout(50)
                    expect(page.locator("#stop-queue")).to_be_disabled(timeout=10000)
                    expect(page.locator("#preview")).to_be_visible()
                    return json.loads(next(iter(set(paths.manifest_root.glob("*.json")) - before)).read_text())

                manifest = generate()
                assert len(calls[-1]["parameters"]["v4_prompt"]["caption"]["char_captions"]) == 22
                assert len(read_image_metadata(Path(manifest["output_path"]))["request"]["nai_characters"]) == 22
                cases.append("V5 22 active characters, ordered wire data, queue and PNG")

                count.fill("23")
                assert not count.evaluate("e=>e.checkValidity()")
                expect(rows).to_have_count(22)
                count.fill("6")
                expect(rows.nth(21)).to_be_hidden()
                count.fill("22")
                expect(rows.nth(21).locator(".character-prompt")).to_have_value("character 22")
                expect(rows.nth(21).locator(".character-x")).to_have_value("0")
                rows.nth(0).locator("details > summary").click()
                rows.nth(1).locator(".character-enabled").uncheck()
                count.fill("6")
                expect(page.locator("#nai-character-status")).to_contain_text("활성 5 / 최대 22명")
                manifest = generate()
                assert len(calls[-1]["parameters"]["v4_prompt"]["caption"]["char_captions"]) == 5
                saved = manifest["novelai"]["requested"]
                assert saved["nai_character_count"] == 6 and len(saved["nai_character_slots"]) == 22
                assert saved["nai_character_slots"][0]["collapsed"] is True
                cases.append("overflow rejected; collapse stays active; hidden and disabled values retained/excluded")

                page.locator("#apply-manifest").click()
                expect(count).to_have_value("6")
                assert not rows.nth(0).locator("details").evaluate("e=>e.open")
                expect(rows.nth(1).locator(".character-enabled")).not_to_be_checked()
                count.fill("22")
                expect(rows.nth(21).locator(".character-negative")).to_have_value("negative 22")
                cases.append("history restores count, disabled state, collapse, 22nd text and boundary coordinates")

                page.locator("#nai-model").select_option("nai-diffusion-4-full")
                assert not page.locator("#nai-model").evaluate("e=>e.checkValidity()")
                expect(page.locator("#nai-character-status")).to_contain_text("최대 6명")
                count.fill("7")  # 7 visible, one disabled = 6 active
                assert page.locator("#nai-model").evaluate("e=>e.checkValidity()")
                generate()
                assert len(calls[-1]["parameters"]["v4_prompt"]["caption"]["char_captions"]) == 6
                page.locator("#nai-model").select_option("nai-diffusion-3")
                assert not page.locator("#nai-model").evaluate("e=>e.checkValidity()")
                count.fill("0")
                assert page.locator("#nai-model").evaluate("e=>e.checkValidity()")
                generate()
                assert "v4_prompt" not in calls[-1]["parameters"]
                cases.append("V4 allows six enabled, rejects excess; V3 accepts zero with all slots retained")

                page.locator("#nai-model").select_option("nai-diffusion-5-curated")
                count.fill("22")
                page.locator("#nai-operation").select_option("infill")
                expect(page.locator("#nai-model")).to_have_value("nai-diffusion-4-5-curated-inpainting")
                expect(page.locator("#nai-character-status")).to_contain_text("최대 6명")
                assert not page.locator("#nai-model").evaluate("e=>e.checkValidity()")
                page.locator("#nai-operation").select_option("generate")
                page.locator("#nai-model").select_option("nai-diffusion-5-full-medium")
                count.fill("6")
                manifest = generate()
                assert all(not c["char_caption"] for c in calls[-1]["parameters"]["v4_negative_prompt"]["caption"]["char_captions"])
                page.locator("#apply-manifest").click()
                expect(rows.nth(0).locator(".character-negative")).to_have_value("negative 1")
                cases.append("Curated infill routes to six limit; Medium clears wire negatives and restores original editor state")

                page.locator("#nai-metadata-file").set_input_files(manifest["output_path"])
                expect(page.locator("#apply-nai-metadata")).to_be_enabled()
                page.locator("#apply-nai-metadata").click()
                expect(count).to_have_value("6")
                expect(rows).to_have_count(22)
                expect(rows.nth(1).locator(".character-enabled")).not_to_be_checked()
                assert not rows.nth(0).locator("details").evaluate("e=>e.open")
                cases.append("PNG import restores hidden, disabled, collapsed and original Medium values")

                page.locator('details[data-control-group="settings"]').evaluate("e=>e.open=true")
                page.locator("#preset-name").fill("22 character slots")
                page.locator("#save-preset").click()
                expect(page.locator("#apply-preset")).to_be_enabled()
                count.fill("0")
                page.locator("#apply-preset").click()
                expect(count).to_have_value("6")
                expect(rows).to_have_count(22)
                expect(rows.nth(1).locator(".character-enabled")).not_to_be_checked()
                cases.append("preset stores full slot bank and restores prefix and enabled state")

                count.fill("22")
                page.locator("#prompt-converter").evaluate("e=>e.open=true")
                page.locator("#convert-field").select_option("character:21:prompt")
                rows.nth(21).locator(".character-prompt").fill("(silver hair:1.2)")
                page.locator("#convert-preview").click()
                expect(page.locator("#convert-apply")).to_be_enabled()
                page.locator("#convert-apply").click()
                expect(rows.nth(21).locator(".character-prompt")).to_have_value("1.2::silver hair ::")
                count.fill("6")
                assert page.locator('#convert-field option[value="character:21:prompt"]').count() == 0
                count.fill("22")
                expect(rows.nth(21).locator(".character-prompt")).to_have_value("1.2::silver hair ::")
                cases.append("conversion targets slot22 and excludes hidden/disabled slots without losing values")
                page.screenshot(path=str(output / "character-slots.png"), full_page=True)
                assert not errors and not blocked
                browser.close()
            report = {"cases": cases, "page_errors": errors, "external_http_attempts": blocked,
                      "live_nai_calls": 0, "synthetic_image_attempts": len(calls), "address": address}
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

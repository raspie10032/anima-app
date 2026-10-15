"""RS NAI metadata and workflow browser acceptance with synthetic files only."""
import argparse
import json
import tempfile
import threading
from pathlib import Path
from urllib.parse import urlparse

from PIL import Image
from PIL.PngImagePlugin import PngInfo
from playwright.sync_api import expect, sync_playwright

from anima_app.config import AppPaths
from anima_app.providers.novelai import NovelAIRequest, build_payload
from anima_app.providers.novelai.images import save_webp
from anima_app.server import create_http_server


def fixture(root, base=True):
    _, source = build_payload(NovelAIRequest(prompt="2people, artist:original", negative_prompt="blur",
        width=512, height=512, seed=0, model="nai-diffusion-5-full", use_coords=True,
        characters=({"prompt": "red hair", "negative_prompt": "hat", "x": .2, "y": .5},
                    {"prompt": "blue hair", "negative_prompt": "ribbon", "x": .8, "y": .5})))
    _, crop = build_payload(NovelAIRequest(prompt="artist:crop", width=512, height=512))
    record = {"version": 1, "operation": "detailer", "base_generation_available": base,
              "edits": [{"request": crop}]}
    if base:
        record["base_generation"] = source
    info = PngInfo()
    info.add_text("rs_nai", json.dumps(record))
    path = root / f"rs-nai-{base}.png"
    Image.new("RGB", (512, 512), "navy").save(path, pnginfo=info)
    return save_webp(path, lossless=True, quality=90)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/nai29-browser"))
    output = parser.parse_args().output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    errors, forbidden, checks = [], [], []
    with tempfile.TemporaryDirectory(prefix="anima-nai29-") as directory:
        root = Path(directory)
        source, partial = fixture(root), fixture(root, False)
        server = create_http_server("127.0.0.1", 0, paths=AppPaths(root), default_dry_run=True)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                page = browser.new_page(locale="ko-KR", viewport={"width": 1440, "height": 1000})
                page.on("pageerror", lambda error: errors.append(str(error)))

                def route(request):
                    parsed = urlparse(request.request.url)
                    if parsed.hostname != "127.0.0.1" or parsed.path in {"/api/jobs", "/api/generate"} and request.request.method == "POST":
                        forbidden.append(request.request.url)
                        request.abort()
                    else:
                        request.continue_()

                page.route("**/*", route)
                page.goto(f"http://127.0.0.1:{server.server_address[1]}", wait_until="networkidle")
                page.locator("#generation-import > summary").click()
                page.locator("#nai-metadata-file").set_input_files(source)
                apply = page.locator("#apply-nai-metadata")
                expect(apply).to_be_enabled()
                expect(page.locator("#nai-metadata-summary")).to_contain_text("artist:original")
                expect(page.locator("#nai-metadata-summary")).not_to_contain_text("artist:crop")
                expect(page.locator("#nai-metadata-history-text")).to_contain_text("artist:crop")
                before = {key: page.locator(f'[name="{key}"]').input_value() for key in ("width", "height", "seed")}
                page.locator("#nai-metadata-use-size").uncheck()
                page.locator("#nai-metadata-use-seed").uncheck()
                apply.click()
                for key, value in before.items():
                    expect(page.locator(f'[name="{key}"]')).to_have_value(value)
                expect(page.locator("#prompt")).to_have_value("2people, artist:original")
                expect(page.locator("#nai-characters fieldset")).to_have_count(2)
                assert page.evaluate("window.animaGenerationRequest().nai_characters[1].x") == .8
                checks.append("WebP restores base prompts and character coordinates; unchecked size/seed stay unchanged")
                for locale, legend, summary in [("ko", "적용할 항목", "캐릭터: 2명"),
                                               ("en", "Fields to apply", "Characters: 2"),
                                               ("ja", "適用する項目", "キャラクター: 2人")]:
                    page.locator("#nai-language").select_option(locale)
                    expect(page.locator("#nai-metadata-fields legend")).to_have_text(legend)
                    expect(page.locator("#nai-metadata-summary")).to_contain_text(summary)
                    expect(page.locator("#nai-metadata-use-size")).not_to_be_checked()
                    expect(page.locator("#prompt")).to_have_value("2people, artist:original")
                    page.locator("#generation-import").screenshot(path=str(output / f"metadata-{locale}.png"))
                checks.append("Korean, English and Japanese retain selections and original prompt text")
                page.locator("#nai-metadata-file").set_input_files(partial)
                expect(apply).to_be_disabled()
                expect(page.locator("#nai-metadata-history-text")).to_contain_text("artist:crop")
                expect(page.locator("#prompt")).to_have_value("2people, artist:original")
                checks.append("Missing base conditions disable Apply and keep edit history separate")
                page.locator("#nai-language").select_option("en")
                page.locator("#generation-workflow > summary").click()
                page.locator("#workflow-add-type").select_option("novelai:detail")
                page.locator("#workflow-add").click()
                stage = page.locator(".workflow-step").last
                stage.locator("details > summary").first.click()
                stage.get_by_label("Output format", exact=True).select_option("webp_lossy")
                stage.get_by_label("WebP quality", exact=True).fill("85")
                stage.get_by_label("Response timeout (seconds)", exact=True).fill("450")
                stage.get_by_label("Character matching", exact=True).select_option("wd14")
                stage.get_by_label("Face detector", exact=True).select_option("face_yolov8m.pt")
                stage.locator("fieldset").get_by_label("CFG", exact=True).check()
                payload = page.evaluate("window.animaWorkflow.decorate(window.animaGenerationRequest())")
                step = payload["workflow"]["steps"][0]
                assert step["inherit_settings"] == ["cfg"]
                assert step["request"]["nai_save_format"] == "webp_lossy"
                assert step["request"]["nai_request_timeout"] == 450
                assert step["request"]["nai_detailer"]["matching"] == "wd14"
                assert step["request"]["nai_detailer"]["face_detector"] == "face_yolov8m.pt"
                page.evaluate("workflow => window.animaWorkflow.apply(workflow)", payload["workflow"])
                restored = page.evaluate("window.animaWorkflow.decorate(window.animaGenerationRequest()).workflow")
                assert restored == payload["workflow"]
                checks.append("Workflow format, timeout, detector, WD matching and selected inherited settings survive restoration")
                saved = page.evaluate("""async request => {
                  const response = await fetch('/api/presets', {method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({name: 'RS NAI synthetic settings', request})});
                  return {status: response.status, body: await response.json()};
                }""", payload)
                assert saved["status"] == 200, saved
                saved_step = saved["body"]["request"]["workflow"]["steps"][0]
                assert saved_step["inherit_settings"] == ["cfg"]
                for key in ("nai_save_format", "nai_webp_quality", "nai_request_timeout"):
                    assert saved_step["request"][key] == step["request"][key]
                assert saved_step["request"]["nai_detailer"]["face_detector"] == "face_yolov8m.pt"
                checks.append("Preset API persists the new workflow fields after server-side normalization")
                page.locator("#provider-select").select_option("local")
                expect(stage.locator(".workflow-nai-inheritance").get_by_label("CFG", exact=True)).to_be_disabled()
                local_plan = page.evaluate("window.animaWorkflow.decorate({provider:'local'})")
                assert "inherit_settings" not in local_plan["workflow"]["steps"][0]
                page.locator("#provider-select").select_option("novelai")
                expect(stage.locator(".workflow-nai-inheritance").get_by_label("CFG", exact=True)).to_be_checked()
                checks.append("Starting with Anima disables NAI-only inheritance; switching back retains its selections")
                for locale in ("ko", "en", "ja"):
                    page.locator("#nai-language").select_option(locale)
                    for width in (1440, 390):
                        page.set_viewport_size({"width": width, "height": 1000})
                        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), (locale, width)
                checks.append("No page overflow at desktop and mobile widths in all three languages")
                assert not errors, errors
                assert not forbidden, forbidden
                browser.close()
        finally:
            server.shutdown()
            server.server_close()
    report = {"checks": checks, "page_errors": errors, "forbidden_requests": forbidden, "live_generation": False}
    (output / "verification.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()

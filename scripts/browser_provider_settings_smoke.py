"""Exercise engine setting isolation and draft/preset restore without generation."""
import argparse
import json
import tempfile
import threading
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import expect, sync_playwright

from anima_app.config import AppPaths
from anima_app.server import create_http_server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/provider-settings-tests"))
    output = parser.parse_args().output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    checks, errors, forbidden = [], [], []
    with tempfile.TemporaryDirectory(prefix="anima-provider-settings-") as directory:
        root = Path(directory)
        (root / "models/loras").mkdir(parents=True)
        (root / "models/loras/test-style.safetensors").write_bytes(b"browser fixture; never loaded")
        server = create_http_server("127.0.0.1", 0, paths=AppPaths(root), default_dry_run=True)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                page = browser.new_page(locale="ko-KR", viewport={"width": 1440, "height": 1000})
                page.on("pageerror", lambda error: errors.append(str(error)))

                def route(request):
                    parsed = urlparse(request.request.url)
                    if parsed.hostname != "127.0.0.1" or (
                        parsed.path in {"/api/jobs", "/api/generate"} and request.request.method == "POST"
                    ):
                        forbidden.append(request.request.url)
                        request.abort()
                    else:
                        request.continue_()

                page.route("**/*", route)
                page.goto(f"http://127.0.0.1:{server.server_address[1]}", wait_until="networkidle")

                def show_controls():
                    if page.locator("body").evaluate("el => el.classList.contains('setup-simple')"):
                        page.locator("#setup-view-toggle").click()
                    page.locator("details").evaluate_all("nodes => nodes.forEach(node => node.open = true)")

                def values(expected):
                    for key, value in expected.items():
                        expect(page.locator(f'[name="{key}"]').first).to_have_value(str(value))

                def fill(fields):
                    for key, value in fields.items():
                        page.locator(f'[name="{key}"]').first.fill(str(value))

                def switch(engine):
                    page.locator("#provider-select").select_option(engine)
                    show_controls()

                show_controls()
                values({"steps": 20, "cfg": 3.5})
                fill({"prompt": "adult portrait, (artist:example:0.8)", "negative_prompt": "blur"})
                local = {"width": 840, "height": 1000, "steps": 60, "cfg": 4.2, "seed": 5000000000}
                fill(local)
                page.locator("#scheduler").select_option("simple")
                page.locator(".lora-row select").first.select_option("test-style.safetensors")
                page.locator(".lora-row input[type=number]").first.fill("0.65")
                switch("novelai")
                values({"width": 832, "height": 1216, "steps": 28, "cfg": 6, "seed": ""})
                expect(page.locator("#provider-settings-status")).to_contain_text("기본 설정")
                assert page.evaluate("window.animaGenerationRequest().provider") == "novelai"
                checks.append("First NAI switch uses valid defaults instead of Anima size, steps, CFG and large seed")

                nai = {"width": 768, "height": 1024, "steps": 24, "cfg": 5.5, "seed": 77}
                fill(nai)
                page.locator("#nai-sampler").select_option("k_dpmpp_2m")
                switch("local")
                values(local)
                expect(page.locator("#scheduler")).to_have_value("simple")
                expect(page.locator(".lora-row select").first).to_have_value("test-style.safetensors")
                expect(page.locator(".lora-row input[type=number]").first).to_have_value("0.65")
                expect(page.locator("#prompt")).to_have_value("adult portrait, (artist:example:0.8)")
                expect(page.locator('[name="negative_prompt"]')).to_have_value("blur")
                switch("novelai")
                values(nai)
                expect(page.locator("#nai-sampler")).to_have_value("k_dpmpp_2m")
                checks.append("Round trips retain independent sampling, seed, model controls and LoRA; prompt stays shared")

                page.evaluate("window.animaAuthoring.save()")
                page.reload(wait_until="networkidle")
                show_controls()
                expect(page.locator("#provider-select")).to_have_value("novelai")
                values(nai)
                switch("local")
                values(local)
                expect(page.locator(".lora-row select").first).to_have_value("test-style.safetensors")
                expect(page.locator(".lora-row input[type=number]").first).to_have_value("0.65")
                checks.append("Automatic draft restore after reload retains both engines and local LoRA")

                page.evaluate("window.animaRestoreGeneration({provider:'novelai', prompt:'preset scene', steps:22, cfg:4.8, seed:101})")
                values({"steps": 22, "cfg": 4.8, "seed": 101})
                switch("local")
                values(local)
                expect(page.locator(".lora-row select").first).to_have_value("test-style.safetensors")
                page.evaluate("window.animaRestoreGeneration({provider:'local', prompt:'local preset', steps:19, cfg:3.2})")
                switch("novelai")
                values({"steps": 22, "cfg": 4.8, "seed": 101})
                checks.append("Loading either engine's preset leaves the opposite engine's configuration intact")

                page.evaluate("window.animaRestoreGeneration({provider:'novelai', prompt:'default sampling'})")
                values({"steps": 28, "cfg": 6})
                page.evaluate("window.animaRestoreGeneration({provider:'local', prompt:'default sampling'})")
                values({"steps": 20, "cfg": 3.5})
                checks.append("Sparse presets resolve defaults from their engine")

                page.evaluate("window.animaRestoreGeneration({provider:'novelai', prompt:'characters', use_coords:true, characters:[{prompt:'red hair',negative_prompt:'hat',x:0.2,y:0.5}], save_format:'webp_lossy', request_timeout:240})")
                switch("local")
                page.evaluate("window.animaRestoreGeneration({provider:'local', prompt:'local import', steps:17})")
                switch("novelai")
                request = page.evaluate("window.animaGenerationRequest()")
                assert request["nai_characters"][0]["prompt"] == "red hair", request
                assert request["nai_characters"][0]["x"] == .2
                assert request["nai_save_format"] == "webp_lossy"
                assert request["nai_request_timeout"] == 240
                checks.append("NAI character coordinates, output format and timeout survive opposite-engine import")

                page.evaluate("window.animaRestoreGeneration({provider:'novelai', prompt:'references', nai_vibes:[{image:'reference.png',strength:0.7,information_extracted:0.8}], nai_detailer:{enabled:true,steps:18,strength:0.42}})")
                switch("local")
                page.evaluate("window.animaRestoreGeneration({provider:'local', prompt:'local correction', upscale:{enabled:true,scale:2.0,steps:14},face_detailer:{enabled:true,steps:12,denoise:0.25}})")
                switch("novelai")
                request = page.evaluate("window.animaGenerationDraft()")
                assert request["nai_vibes"][0]["image"] == "reference.png"
                assert request["nai_vibes"][0]["strength"] == .7
                assert request["nai_detailer"]["steps"] == 18
                assert request["nai_detailer"]["enabled"]
                switch("local")
                request = page.evaluate("window.animaGenerationDraft()")
                assert request["upscale"]["enabled"] and request["upscale"]["scale"] == 2
                assert request["face_detailer"]["enabled"] and request["face_detailer"]["steps"] == 12
                checks.append("Vibe references, NAI detailing and local upscale/detailing remain engine-specific")

                # Inspect the actual workflow picker rather than assigning provider directly.
                page.get_by_role("button", name="NAI 생성 → Anima 디테일러", exact=True).click()
                expected_workflow = page.evaluate("window.animaWorkflow.snapshot()")
                switch("local")
                switch("novelai")
                assert page.evaluate("window.animaWorkflow.snapshot()") == expected_workflow
                checks.append("Engine toggling preserves the configured workflow")

                for locale, text in [("ko", "엔진별"), ("en", "Last engine"), ("ja", "エンジンごと")]:
                    page.locator("#nai-language").select_option(locale)
                    expect(page.locator("#provider-settings-status")).to_contain_text(text)
                checks.append("Settings feedback follows Korean, English and Japanese locale")
                page.locator("#nai-language").select_option("ko")
                page.screenshot(path=str(output / "nai-restored.png"))
                switch("local")
                page.screenshot(path=str(output / "anima-restored.png"))
                browser.close()
        finally:
            server.shutdown()
            server.server_close()
    assert not errors, errors
    assert not forbidden, forbidden
    report = {"checks": checks, "page_errors": errors, "forbidden_requests": forbidden, "live_generation": False}
    (output / "verification.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()

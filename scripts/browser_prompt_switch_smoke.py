"""Verify visible prompt conversion, exact round trips and asynchronous editor safety."""
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
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/prompt-switch-tests"))
    parser.add_argument("--browser", choices=["chromium", "firefox"], default="chromium")
    args = parser.parse_args()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    checks, errors, forbidden = [], [], []
    with tempfile.TemporaryDirectory(prefix="anima-prompt-switch-") as directory:
        server = create_http_server("127.0.0.1", 0, paths=AppPaths(Path(directory)), default_dry_run=True)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            with sync_playwright() as playwright:
                browser = getattr(playwright, args.browser).launch(headless=True)
                try:
                    page = browser.new_page(locale="ko-KR", viewport={"width": 1440, "height": 1000})
                    page.on("pageerror", lambda error: errors.append(str(error)))

                    def guard(route):
                        request = route.request
                        parsed = urlparse(request.url)
                        if parsed.hostname != "127.0.0.1" or (
                            request.method == "POST" and parsed.path in {"/api/jobs", "/api/generate"}
                        ):
                            forbidden.append(parsed.path)
                            route.abort()
                        else:
                            route.continue_()

                    page.route("**/*", guard)
                    page.goto(f"http://127.0.0.1:{server.server_address[1]}", wait_until="networkidle")
                    page.locator("#setup-view-toggle").click()

                    def switch(provider):
                        page.locator("#provider-select").select_option(provider)
                        expect(page.locator("#provider-select")).to_be_enabled()
                        expect(page.locator("#provider-select")).to_have_value(provider)

                    def restore(request):
                        page.evaluate("request => window.animaRestoreGeneration(request)", request)

                    original = r"(no lineart:2), (artist:alpha, @beta :0.85), (@alt \(example\):0.95), portrait"
                    negative = "(blur:1.2), text"
                    restore({"provider": "local", "prompt": original, "negative_prompt": negative,
                             "steps": 23, "cfg": 4, "prompt_routing": {"source": "comfyui"}})
                    switch("novelai")
                    nai_prompt = page.locator("#prompt").input_value()
                    assert "2::no lineart" in nai_prompt and "0.85::artist:alpha, artist:beta" in nai_prompt
                    expect(page.locator('[name="negative_prompt"]')).to_have_value("1.2::blur ::, text")
                    expect(page.locator("#prompt-routing")).to_have_value("auto")
                    # Actual request preview must match the displayed numeric weights exactly.
                    page.locator("#preview-prompt-plan").click()
                    dialog = page.locator("#prompt-plan-dialog")
                    expect(dialog.locator(".prompt-plan-stage pre").first).to_have_text(nai_prompt)
                    dialog.get_by_role("button", name="닫기", exact=True).click()
                    checks.append("Visible NAI weights and artist markers match the generation request without double conversion")
                    switch("local")
                    expect(page.locator("#prompt")).to_have_value(original)
                    expect(page.locator('[name="negative_prompt"]')).to_have_value(negative)
                    expect(page.locator("#prompt-routing")).to_have_value("comfyui")
                    expect(page.locator('[name="steps"]')).to_have_value("23")
                    checks.append("Untouched round trip restores exact grouping, whitespace, escapes and explicit source syntax")

                    switch("novelai")
                    page.evaluate("window.animaAuthoring.save()")
                    page.reload(wait_until="networkidle")
                    switch("local")
                    expect(page.locator("#prompt")).to_have_value(original)
                    checks.append("Reload on NAI retains the original Anima text and syntax for the return trip")

                    switch("novelai")
                    page.locator("#prompt").fill("1.4::artist:new_style ::, blue coat")
                    switch("local")
                    expect(page.locator("#prompt")).to_have_value("(@new_style:1.4), blue coat")
                    switch("novelai")
                    expect(page.locator("#prompt")).to_have_value("1.4::artist:new_style ::, blue coat")
                    checks.append("Editing on NAI replaces the shared scene instead of resurrecting an old Anima prompt")

                    slots = [{"prompt": "1.3::blue eyes ::", "negative_prompt": "1.2::hat ::",
                              "x": .2, "y": .7, "enabled": True, "collapsed": False},
                             {"prompt": "0.8::artist:unused ::", "negative_prompt": "", "enabled": False}]
                    restore({"provider": "novelai", "prompt": "1.1::two adults ::", "nai_character_slots": slots,
                             "nai_character_count": 1, "nai_model": "nai-diffusion-5-full"})
                    switch("local")
                    expect(page.locator(".character-prompt").first).to_have_value("(blue eyes:1.3)")
                    expect(page.locator(".character-prompt").nth(1)).to_have_value("(@unused:0.8)")
                    page.evaluate("window.animaAuthoring.save()")
                    page.reload(wait_until="networkidle")
                    expect(page.locator(".character-prompt").first).to_have_value("(blue eyes:1.3)")
                    switch("novelai")
                    request = page.evaluate("window.animaGenerationDraft()")
                    assert request["nai_character_slots"][0]["prompt"] == slots[0]["prompt"]
                    assert request["nai_character_slots"][0]["negative_prompt"] == slots[0]["negative_prompt"]
                    assert request["nai_character_slots"][0]["x"] == .2
                    assert request["nai_character_slots"][1]["prompt"] == slots[1]["prompt"]
                    assert request["nai_character_slots"][1]["enabled"] is False
                    assert request["nai_character_count"] == 1
                    checks.append("Active and hidden character prompts convert and survive reload while coordinates and enable flags remain intact")

                    restore({"provider": "local", "prompt": "(fresh import:1.25)"})
                    switch("novelai")
                    expect(page.locator("#prompt")).to_have_value("1.25::fresh import ::")
                    checks.append("Loading a preset invalidates cached prompt versions")

                    restore({"provider": "local", "prompt": original, "prompt_routing": {"source": "native"}})
                    switch("novelai")
                    expect(page.locator("#prompt")).to_have_value(original)
                    expect(page.locator("#prompt-routing")).to_have_value("native")
                    checks.append("Explicit no-conversion selection stays verbatim")
                    restore({"provider": "local", "prompt": "(portrait:1.2), {red coat|blue coat}, __style__"})
                    switch("novelai")
                    expect(page.locator("#prompt")).to_have_value("(portrait:1.2), {red coat|blue coat}, __style__")
                    expect(page.locator("#prompt-switch-status")).to_contain_text("와일드카드")
                    checks.append("Unexpanded wildcard choices remain intact with visible execution-time conversion notice")

                    restore({"provider": "novelai", "prompt": "{{artist:legacy}}", "nai_model": "nai-diffusion-3"})
                    switch("local")
                    expect(page.locator("#prompt")).to_have_value("(@legacy:1.1)")
                    page.locator("#prompt").fill("(@new_style:1.2)")
                    switch("novelai")
                    expect(page.locator("#prompt")).to_have_value("{{{{artist:new_style}}}}")
                    expect(page.locator("#prompt-switch-status")).to_contain_text("근사")
                    checks.append("Remembered NAI V3 model selects brace weights and reports approximation")

                    restore({"provider": "local", "prompt": "(portrait:1.2), 1.3::hat ::"})
                    before = page.locator("#prompt").input_value()
                    page.locator("#provider-select").select_option("novelai")
                    expect(page.locator("#provider-settings-status")).to_contain_text("엔진 전환을 멈췄습니다")
                    expect(page.locator("#provider-select")).to_have_value("local")
                    expect(page.locator("#prompt")).to_have_value(before)
                    checks.append("Invalid mixed syntax keeps the original engine and full prompt instead of partially applying")

                    endpoint = "**/api/prompts/adapt-editor"
                    restore({"provider": "local", "prompt": "(@delayed:1.2)"})
                    held = []
                    page.route(endpoint, lambda route: held.append(route))
                    page.locator("#provider-select").select_option("novelai")
                    expect(page.locator("#provider-select")).to_be_disabled()
                    page.locator("#prompt").fill("typed during conversion")
                    assert held
                    held.pop().continue_()
                    expect(page.locator("#provider-settings-status")).to_contain_text("초안이 바뀌었습니다")
                    expect(page.locator("#prompt")).to_have_value("typed during conversion")
                    expect(page.locator("#provider-select")).to_have_value("local")
                    page.unroute(endpoint)
                    checks.append("Delayed response cannot overwrite text entered while converting")

                    page.route(endpoint, lambda route: route.fulfill(status=503, json={"error": "Test service unavailable"}))
                    page.locator("#provider-select").select_option("novelai")
                    expect(page.locator("#provider-settings-status")).to_contain_text("Test service unavailable")
                    expect(page.locator("#provider-select")).to_have_value("local")
                    expect(page.locator("#provider-select")).to_be_enabled()
                    page.unroute(endpoint)
                    checks.append("Conversion service failure leaves the old engine usable and preserves editor text")

                    restore({"provider": "novelai", "nai_model": "nai-diffusion-5-full"})
                    restore({"provider": "local", "prompt": original, "negative_prompt": negative})
                    switch("novelai")
                    for locale, word in [("ko", "표기 전환 완료"), ("en", "converted"), ("ja", "変換")]:
                        page.locator("#nai-language").select_option(locale)
                        expect(page.locator("#prompt-switch-status")).to_contain_text(word)
                    page.locator("#nai-language").select_option("ko")
                    page.screenshot(path=str(output / "nai-prompt.png"))
                    switch("local")
                    page.screenshot(path=str(output / "anima-prompt.png"))
                    checks.append("Conversion feedback supports Korean, English and Japanese")
                finally:
                    browser.close()
        finally:
            server.shutdown()
            server.server_close()
    assert not errors and not forbidden, (errors, forbidden)
    result = {"checks": checks, "browser": args.browser, "page_errors": errors,
              "forbidden_requests": forbidden, "live_generation": False}
    (output / "verification.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()

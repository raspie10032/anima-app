"""App-wide en/ko/ja acceptance with synthetic library data and no generation."""

import argparse
import json
import tempfile
import threading
from pathlib import Path
from urllib.parse import urlparse

from PIL import Image
from playwright.sync_api import expect, sync_playwright

from anima_app.config import AppPaths
from anima_app.library import Library
from anima_app.server import create_http_server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir", type=Path, default=Path("outputs/locale-browser")
    )
    output = parser.parse_args().output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    errors, forbidden, checks = [], [], []
    with tempfile.TemporaryDirectory(prefix="anima-locale-") as temporary:
        paths = AppPaths(Path(temporary))
        library = Library(paths)
        for i, color in enumerate(("#a86d80", "#80bca7", "#6382ad")):
            image = paths.project_root / f"작가-{i}.png"
            Image.new("RGB", (240, 300), color).save(image)
            library.ingest(
                image,
                {
                    "provider": "novelai",
                    "prompt": "artist:example, 프롬프트, 日本語, portrait",
                    "negative_prompt": "blur",
                    "nai_model": "nai-diffusion-4-5-full",
                    "width": 512,
                    "height": 512,
                },
            )
        server = create_http_server("127.0.0.1", 0, paths=paths, default_dry_run=True)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        url = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                try:
                    context = browser.new_context(
                        viewport={"width": 1600, "height": 1050}, locale="en-US"
                    )

                    def route(r):
                        target = urlparse(r.request.url)
                        if target.hostname != "127.0.0.1" or (
                            r.request.method == "POST"
                            and target.path in ("/api/jobs", "/api/generate")
                        ):
                            forbidden.append(r.request.url)
                            r.abort()
                        else:
                            r.continue_()

                    context.route("**/*", route)
                    page = context.new_page()
                    page.on("pageerror", lambda e: errors.append(str(e)))
                    page.goto(url, wait_until="networkidle")
                    language = page.locator("#nai-language")
                    expect(language).to_have_value("en")
                    expect(page.locator("#generate-button")).to_have_text("Generate")
                    checks.append("English browser selects English on first visit")
                    original = (
                        "프롬프트, artist:example, 日本語, <img src=x onerror=alert(1)>"
                    )
                    page.evaluate(
                        'prompt => window.animaRestoreGeneration({provider:"novelai", prompt, negative_prompt:"부정 프롬프트", seed:0, width:512,height:512,nai_model:"nai-diffusion-4-5-full",workflow:{version:1,steps:[{provider:"local",operation:"detail",inherit_prompt:false,request:{prompt:"단계별 원문 日本語",negative_prompt:"blur"}}]}})',
                        original,
                    )
                    baseline = page.evaluate(
                        "JSON.stringify(animaWorkflow.decorate(animaGenerationRequest()))"
                    )
                    for locale, label, stage in [
                        ("ko", "생성하기", "디테일러"),
                        ("ja", "生成する", "ディテーラー"),
                        ("en", "Generate", "Detailer"),
                    ]:
                        language.select_option(locale)
                        expect(page.locator("html")).to_have_attribute("lang", locale)
                        expect(page.locator("#generate-button")).to_have_text(label)
                        expect(
                            page.locator(".workflow-step-head strong")
                        ).to_contain_text(stage)
                        expect(page.locator("#prompt")).to_have_value(original)
                        assert (
                            page.evaluate(
                                "JSON.stringify(animaWorkflow.decorate(animaGenerationRequest()))"
                            )
                            == baseline
                        )
                        page.screenshot(path=str(output / f"main-{locale}.png"))
                    checks.append(
                        "All three languages update mounted workflow and preserve byte-identical generation request"
                    )
                    page.locator("#open-library").click()
                    dialog = page.locator("#library-dialog")
                    expect(dialog.locator(".lib-card")).to_have_count(3)
                    dialog.locator(".lib-select").first.click()
                    recorded = dialog.get_by_label(
                        "Recorded prompt", exact=True
                    ).input_value()
                    dialog.get_by_role(
                        "button", name="Import prompt", exact=True
                    ).click()
                    draft = dialog.get_by_label("Working prompt", exact=True)
                    expect(draft).to_have_value(recorded)
                    draft.fill("작업 초안 그대로, artist:example, 日本語")
                    selected = dialog.locator(".lib-card.is-selected").get_attribute(
                        "data-id"
                    )
                    assert selected
                    for locale, title, draft_name, record_name in [
                        (
                            "ja",
                            "画像ワークスペース",
                            "作業プロンプト",
                            "記録されたプロンプト",
                        ),
                        ("ko", "이미지 작업실", "작업 프롬프트", "기록된 프롬프트"),
                        ("en", "Image workspace", "Working prompt", "Recorded prompt"),
                    ]:
                        dialog.locator("[data-app-locale]").select_option(locale)
                        expect(dialog.locator(".lib-header h2")).to_contain_text(title)
                        expect(
                            dialog.get_by_label(draft_name, exact=True)
                        ).to_have_value("작업 초안 그대로, artist:example, 日本語")
                        expect(
                            dialog.get_by_label(record_name, exact=True)
                        ).to_have_value(recorded)
                        assert (
                            dialog.locator(".lib-card.is-selected").get_attribute(
                                "data-id"
                            )
                            == selected
                        )
                        expect(language).to_have_value(locale)
                        page.screenshot(path=str(output / f"library-{locale}.png"))
                    checks.append(
                        "Library locale switch updates labels without changing selection, original prompts or edited draft"
                    )
                    dialog.get_by_role(
                        "button", name="Back to generation", exact=True
                    ).click()
                    language.select_option("ja")
                    page.reload(wait_until="networkidle")
                    expect(language).to_have_value("ja")
                    expect(page.locator("#prompt")).to_have_value(original)
                    checks.append("Locale and original authoring draft survive reload")
                    second = context.new_page()
                    second.goto(url, wait_until="networkidle")
                    second.locator("#nai-language").select_option("ko")
                    expect(language).to_have_value("ko")
                    expect(page.locator("#generate-button")).to_have_text("생성하기")
                    second.close()
                    checks.append("Cross-tab locale updates the existing main screen")
                    for locale in ("en", "ko", "ja"):
                        language.select_option(locale)
                        for width in (1920, 1280, 900, 390):
                            page.set_viewport_size({"width": width, "height": 1000})
                            assert page.evaluate(
                                "document.documentElement.scrollWidth <= innerWidth"
                            ), (locale, width, "main")
                            expect(language).to_be_visible()
                            page.locator("#open-library").click()
                            expect(dialog).to_be_visible()
                            assert dialog.evaluate("n=>n.scrollWidth<=innerWidth"), (
                                locale,
                                width,
                                "library",
                            )
                            if width == 390:
                                page.screenshot(
                                    path=str(output / f"mobile-{locale}.png")
                                )
                            page.keyboard.press("Escape")
                    checks.append(
                        "Main and library have no horizontal overflow at four widths in all three languages"
                    )
                    legacy = browser.new_context(locale="en-US")
                    legacy.add_init_script(
                        "localStorage.setItem('anima.nai.language','ja')"
                    )
                    legacy_page = legacy.new_page()
                    legacy_page.goto(url, wait_until="networkidle")
                    expect(legacy_page.locator("#nai-language")).to_have_value("ja")
                    legacy.close()
                    checks.append("Legacy NAI language preference is honored")
                    blocked = browser.new_context(locale="en-US")
                    blocked.add_init_script(
                        "Object.defineProperty(window,'localStorage',{get(){throw Error('blocked')}})"
                    )
                    blocked_page = blocked.new_page()
                    blocked_page.goto(url, wait_until="networkidle")
                    blocked_page.locator("#nai-language").select_option("ja")
                    expect(blocked_page.locator("#generate-button")).to_have_text(
                        "生成する"
                    )
                    expect(
                        blocked_page.locator("#nai-language-status")
                    ).to_contain_text("保存できません")
                    blocked.close()
                    checks.append(
                        "Blocked storage still permits session-only language switching with a notice"
                    )
                    assert not errors, errors
                    assert not forbidden, forbidden
                finally:
                    browser.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
    result = {
        "status": "passed",
        "checks": checks,
        "browser_errors": errors,
        "forbidden_requests": forbidden,
    }
    (output / "verification.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

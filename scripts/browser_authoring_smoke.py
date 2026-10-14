"""Exercise authoring/preview/persistence/provenance with local synthetic data."""

import argparse
import json
import tempfile
import threading
from pathlib import Path
from urllib.parse import urlparse

from PIL import Image
from playwright.sync_api import expect, sync_playwright

from anima_app.artist_catalog import catalog_path
from anima_app.config import AppPaths
from anima_app.library import Library
from anima_app.server import create_http_server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir", type=Path, default=Path("outputs/authoring-browser")
    )
    output = parser.parse_args().output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    errors, external, generation, checks = [], [], [], []
    with tempfile.TemporaryDirectory(prefix="anima-authoring-") as temporary:
        paths = AppPaths(Path(temporary))
        library = Library(paths)
        path = paths.project_root / "sample.png"
        Image.new("RGB", (240, 300), "#6d7aab").save(path)
        identity, _ = library.ingest(
            path,
            {
                "provider": "novelai",
                "prompt": "1.2::artist:demo_a::, portrait",
                "negative_prompt": "blur",
                "nai_model": "nai-diffusion-4-5-full",
                "seed": 25,
                "width": 512,
                "height": 512,
            },
        )
        library.ingest(
            path,
            {
                "provider": "novelai",
                "prompt": "artist:demo_b, blue coat",
                "negative_prompt": "bad hands",
                "nai_model": "nai-diffusion-4-5-full",
                "seed": 26,
                "width": 512,
                "height": 512,
            },
        )
        catalog = catalog_path(paths)
        catalog.parent.mkdir(parents=True)
        catalog.write_text(
            json.dumps(
                {
                    "version": 1,
                    "tags": [{"name": "tianliang_duohe_fangdongye", "category": 1}],
                }
            )
        )
        server = create_http_server("127.0.0.1", 0, paths=paths, default_dry_run=True)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        address = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                try:
                    page = browser.new_page(
                        locale="ko-KR", viewport={"width": 1600, "height": 1050}
                    )
                    page.on("pageerror", lambda error: errors.append(str(error)))

                    def route(request):
                        parsed = urlparse(request.request.url)
                        if parsed.hostname != "127.0.0.1":
                            external.append(parsed.path)
                            request.abort()
                        elif request.request.method == "POST" and parsed.path in (
                            "/api/generate",
                            "/api/jobs",
                        ):
                            generation.append(parsed.path)
                            request.abort()
                        else:
                            request.continue_()

                    page.route("**/*", route)
                    page.goto(address, wait_until="networkidle")
                    original = "(artist:demo_a:1.2), (tianliang duohe fangdongye:0.85), portrait"
                    request = {
                        "provider": "novelai",
                        "nai_model": "nai-diffusion-4-5-full",
                        "prompt": original,
                        "negative_prompt": "blur",
                        "width": 512,
                        "height": 512,
                        "seed": 17,
                        "prompt_routing": {"source": "auto"},
                        "workflow": {
                            "version": 1,
                            "steps": [
                                {
                                    "provider": "local",
                                    "operation": "detail",
                                    "inherit_prompt": True,
                                    "request": {},
                                }
                            ],
                        },
                    }
                    page.evaluate("r => window.animaRestoreGeneration(r)", request)
                    page.locator("#preview-prompt-plan").click()
                    dialog = page.locator("#prompt-plan-dialog")
                    expect(dialog.locator(".prompt-plan-stage")).to_have_count(2)
                    expect(dialog.locator(".prompt-plan-stage").nth(0)).to_contain_text(
                        "0.85::artist:tianliang duohe fangdongye"
                    )
                    expect(dialog.locator(".prompt-plan-stage").nth(1)).to_contain_text(
                        "(@tianliang duohe fangdongye:0.85)"
                    )
                    expect(dialog).to_contain_text(
                        "접두사 자동 인식: tianliang duohe fangdongye"
                    )
                    expect(page.locator("#prompt")).to_have_value(original)
                    page.screenshot(path=str(output / "stage-prompts.png"))
                    dialog.get_by_role("button", name="닫기", exact=True).click()
                    checks.append(
                        "Two-engine preview preserves raw text and infers only a known unprefixed artist"
                    )
                    page.wait_for_function(
                        "JSON.parse(localStorage.getItem('anima.authoring.v1'))?.request.prompt.includes('tianliang')"
                    )
                    page.reload(wait_until="networkidle")
                    expect(page.locator("#prompt")).to_have_value(original)
                    restored = page.evaluate("window.animaGenerationDraft()")
                    assert restored["workflow"]["steps"][0]["provider"] == "local"
                    assert (
                        restored["seed"] == 17
                        and restored["prompt_routing"]["source"] == "auto"
                    )
                    checks.append(
                        "Reload restores prompt, syntax, seed, and downstream workflow without submitting"
                    )
                    page.locator("#open-library").click()
                    workspace = page.locator("#library-dialog")
                    workspace.locator(
                        f'.lib-card[data-id="{identity}"] .lib-select'
                    ).click()
                    selector = workspace.get_by_label("생성 기록 선택")
                    expect(selector.locator("option")).to_have_count(2)
                    selector.select_option("1")
                    chosen = workspace.get_by_label("기록된 프롬프트").input_value()
                    workspace.get_by_role(
                        "button", name="프롬프트 가져오기", exact=True
                    ).click()
                    expect(workspace.get_by_label("작업 프롬프트")).to_have_value(
                        chosen
                    )
                    workspace.get_by_label("작업 프롬프트").fill(
                        chosen + ", custom scene"
                    )
                    page.reload(wait_until="networkidle")
                    page.locator("#open-library").click()
                    workspace.locator("#library-tab-compose").click()
                    expect(workspace.get_by_label("작업 프롬프트")).to_have_value(
                        chosen + ", custom scene"
                    )
                    workspace.get_by_role(
                        "button", name="가져오기 되돌리기", exact=True
                    ).click()
                    expect(workspace.get_by_label("작업 프롬프트")).to_have_value(
                        original
                    )
                    checks.append(
                        "Library draft and import undo history survive reload"
                    )
                    page.evaluate("id => window.animaLibraryOpenItem(id)", identity)
                    selector.select_option("1")
                    workspace.get_by_role(
                        "button", name="프롬프트 가져오기", exact=True
                    ).click()
                    expect(workspace.get_by_label("작업 프롬프트")).to_have_value(
                        chosen
                    )
                    workspace.get_by_role(
                        "button", name="생성 화면에 적용", exact=True
                    ).click()
                    expect(page.locator("#authoring-sources")).to_contain_text(
                        "참고 사례 1개"
                    )
                    sources = page.evaluate(
                        "window.animaAuthoring.context().generation_sources"
                    )
                    assert (
                        sources[0]["asset_id"] == identity
                        and sources[0]["scope"] == "prompt"
                    )
                    page.evaluate(
                        "sources => window.animaAuthoring.showResult({generation_sources:sources})",
                        sources,
                    )
                    page.locator("#result-sources button").click()
                    expect(workspace.get_by_label("생성 기록 선택")).to_have_value("1")
                    expect(workspace.get_by_label("기록된 프롬프트")).to_have_value(
                        chosen
                    )
                    checks.append(
                        "Generation result source link opens the exact record of a multi-record image"
                    )
                    workspace.get_by_role(
                        "button", name="생성 화면으로", exact=True
                    ).click()
                    page.locator("#authoring-sources").get_by_role(
                        "button", name="연결 해제"
                    ).click()
                    assert (
                        page.evaluate(
                            "window.animaAuthoring.context().generation_sources"
                        )
                        == []
                    )
                    checks.append("Users can detach imported source references")
                    page.locator("#prompt-routing").select_option("native")
                    page.locator("#prompt").fill(original)
                    page.locator("#preview-prompt-plan").click()
                    expect(
                        dialog.locator(".prompt-plan-stage").first.locator("pre").first
                    ).to_have_text(original)
                    dialog.get_by_role("button", name="닫기", exact=True).click()
                    checks.append(
                        "Explicit no-conversion override keeps the supplied syntax verbatim"
                    )
                    page.wait_for_function(
                        "JSON.parse(localStorage.getItem('anima.authoring.v1'))?.request.prompt_routing.source === 'native'"
                    )
                    page.locator("#forget-authoring").click()
                    assert (
                        page.evaluate("localStorage.getItem('anima.authoring.v1')")
                        is None
                    )
                    page.reload(wait_until="networkidle")
                    assert (
                        page.evaluate("localStorage.getItem('anima.authoring.v1')")
                        is None
                    )
                    checks.append(
                        "Forgetting a draft does not silently recreate it on reload"
                    )
                    for width in (1920, 1280, 900, 390):
                        page.set_viewport_size({"width": width, "height": 1000})
                        assert page.evaluate(
                            "document.documentElement.scrollWidth <= innerWidth + 1"
                        )
                    checks.append("No horizontal overflow at four viewport widths")
                    assert not errors and not external and not generation, (
                        errors,
                        external,
                        generation,
                    )
                finally:
                    browser.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=10)
    result = {
        "status": "passed",
        "checks": checks,
        "browser_errors": errors,
        "external_requests": external,
        "generation_requests": generation,
    }
    (output / "verification.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2)
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

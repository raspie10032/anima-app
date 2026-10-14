"""Korean/Japanese NAI UI acceptance with synthetic transport and isolated data."""
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
from anima_app.server import create_http_server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/nai-update-20261011/language/browser"))
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

    with (tempfile.TemporaryDirectory(prefix="anima-language-smoke-") as temporary,
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
                context = browser.new_context(viewport={"width": 1500, "height": 1000}, locale="ko-KR")
                page = context.new_page()
                page.on("pageerror", lambda e: errors.append(str(e)))
                context.route("**/*", lambda r: r.continue_() if urlparse(r.request.url).hostname == "127.0.0.1" else r.abort())
                page.goto(address, wait_until="networkidle")
                language = page.locator("#nai-language")
                expect(language).to_have_value("ko")
                page.locator("#provider-select").select_option("novelai")
                page.locator('[data-control-group="model-style"]').evaluate("e=>e.open=true")
                page.locator("#nai-feature-guide").evaluate("e=>e.open=true")
                expect(page.locator("#nai-feature-guide")).to_contain_text("NAI 기능 사용 안내")
                language.select_option("ja")
                expect(page.locator("#nai-feature-guide")).to_contain_text("NAI機能の使い方")
                expect(page.locator("#novelai-settings")).to_have_attribute("lang", "ja")
                expect(page.locator('label[for="nai-operation"]')).to_have_text("生成方式")
                untranslated = page.locator("#novelai-settings").evaluate(r"""root => {
                  const walker=document.createTreeWalker(root, NodeFilter.SHOW_TEXT), result=[];
                  while(walker.nextNode()) {
                    const node=walker.currentNode;
                    if (!node.parentElement.closest('textarea,pre') && /[가-힣]/.test(node.textContent)) result.push(node.textContent.trim());
                  }
                  return result;
                }""")
                assert not untranslated, untranslated
                expect(page.locator("#nai-operation")).to_have_value("generate")
                page.reload(wait_until="networkidle")
                expect(language).to_have_value("ja")
                cases.append("browser language default, explicit Japanese selection and reload persistence")

                page.locator("#provider-select").select_option("novelai")
                page.locator('[data-control-group="model-style"]').evaluate("e=>e.open=true")
                page.locator("#nai-model").select_option("nai-diffusion-5-full")
                page.locator("#nai-characters-panel").evaluate("e=>e.open=true")
                page.locator("#nai-character-count").fill("22")
                rows = page.locator("#nai-characters .nai-character")
                rows.nth(21).locator(".character-prompt").fill("프롬프트 <img src=x onerror=alert(1)> 日本語")
                rows.nth(21).locator(".character-negative").fill("네거티브 <b>keep</b>")
                rows.nth(21).locator(".character-x").fill("0")
                rows.nth(21).locator(".character-y").fill("1")
                rows.nth(1).locator(".character-enabled").uncheck()
                rows.nth(21).locator("details").evaluate("e=>e.open=false")
                page.locator("#nai-character-count").fill("6")
                before = page.evaluate("readNaiCharacterSlots()")
                language.select_option("ko")
                language.select_option("ja")
                assert page.evaluate("readNaiCharacterSlots()") == before
                page.locator("#nai-character-count").fill("22")
                expect(rows.nth(21).locator("legend")).to_have_text("キャラクター 22")
                page.locator("#nai-model").select_option("nai-diffusion-4-full")
                expect(page.locator("#nai-character-status")).to_contain_text("最大6人")
                assert "最大6人" in page.locator("#nai-model").evaluate("e=>e.validationMessage")
                language.select_option("ko")
                assert "6명까지" in page.locator("#nai-model").evaluate("e=>e.validationMessage")
                page.locator("#nai-model").select_option("nai-diffusion-5-full-medium")
                language.select_option("ja")
                expect(page.locator("#nai-medium-notice")).to_contain_text("14ステップ")
                assert not page.locator("#nai-characters img").count()
                cases.append("22 hidden/disabled/collapsed characters, boundary coordinates, model limits and Medium labels retain values")

                page.locator("#nai-reference-panel").evaluate("e=>e.open=true")
                page.locator("#nai-add-reference").click()
                reference = page.locator("#nai-references fieldset")
                reference.locator(".reference-type").select_option("character&style")
                reference.locator(".reference-strength").fill("0")
                png = io.BytesIO()
                Image.new("RGB", (64, 64), "blue").save(png, format="PNG")
                reference.locator('input[type="file"]').set_input_files({"name": "reference.png", "mimeType": "image/png", "buffer": png.getvalue()})
                expect(reference.locator(".reference-path")).to_contain_text("inputs/")
                ref_before = page.evaluate('readNaiReferences("precise")')
                file_node = reference.locator('input[type="file"]').element_handle()
                language.select_option("ko")
                language.select_option("ja")
                assert page.evaluate('readNaiReferences("precise")') == ref_before
                assert reference.locator('input[type="file"]').evaluate("(e,original)=>e===original", file_node)
                expect(reference.locator("option:checked")).to_have_text("キャラクター + スタイル")
                expect(reference.locator(".reference-type")).to_have_value("character&style")
                expect(reference.locator(".reference-path")).to_contain_text("inputs/")
                reference.locator("button").click()
                cases.append("reference card labels change without replacing file controls or mutating uploaded paths, strengths or API enum values")

                page.locator("#nai-character-count").fill("1")
                rows.nth(0).locator(".character-prompt").fill("(silver hair:1.2)")
                page.locator("#generation-prompt-tools").evaluate("e=>e.open=true")
                page.locator("#prompt-converter").evaluate("e=>e.open=true")
                page.locator("#convert-field").select_option("character:0:prompt")
                page.locator("#convert-preview").click()
                expect(page.locator("#convert-apply")).to_be_enabled()
                converted = page.locator("#convert-result").inner_text()
                language.select_option("ko")
                language.select_option("ja")
                expect(page.locator("#convert-field")).to_have_value("character:0:prompt")
                expect(page.locator("#convert-apply")).to_be_enabled()
                assert page.locator("#convert-result").inner_text() == converted
                page.locator("#convert-apply").click()
                expect(rows.nth(0).locator(".character-prompt")).to_have_value("1.2::silver hair ::")
                page.locator("#nai-detailer-panel").evaluate("e=>e.open=true")
                page.locator("#nai-detailer-wd_model").select_option("PixAI Tagger v1.0")
                expect(page.locator("#nai-tagger-hint")).to_contain_text("バッチサイズ1")
                cases.append("language switches preserve conversion preview/apply target and display selected PixAI guidance")

                page.locator("#nai-operation").select_option("infill")
                expect(page.locator("#nai-input-help")).to_contain_text("生成サイズ")
                expect(page.locator("#nai-operation")).to_have_value("infill")
                expect(page.locator("#nai-mask-canvas")).to_have_attribute("aria-label", "インペイントマスクの描画")
                page.locator("#nai-input-file").set_input_files({"name": "base.png", "mimeType": "image/png", "buffer": png.getvalue()})
                expect(page.locator("#nai-input-preview")).to_be_visible()
                page.wait_for_function("naiMaskBuffer.width===64")
                page.evaluate("naiMaskBuffer.getContext('2d').fillRect(1,1,3,3)")
                mask_before = page.evaluate("naiMaskBuffer.toDataURL()")
                input_before = page.locator('input[name="input_image"]').input_value()
                language.select_option("ko")
                language.select_option("ja")
                assert page.evaluate("naiMaskBuffer.toDataURL()") == mask_before
                assert page.locator('input[name="input_image"]').input_value() == input_before
                page.locator("#nai-operation").select_option("generate")
                cases.append("inpainting guidance and accessible mask label translated while input and canvas pixels survive")

                for name, value in {"prompt": "scene", "width": "64", "height": "64", "seed": "0"}.items():
                    page.locator(f'[name="{name}"]').fill(value)
                # Serialize the exact request before/after changing language.
                payload_ja = page.evaluate("buildRequestData()")
                language.select_option("ko")
                assert page.evaluate("buildRequestData()") == payload_ja
                language.select_option("ja")
                before_manifests = set(paths.manifest_root.glob("*.json"))
                page.locator("#generate-button").click()
                # Capture locked state once queue work starts, then switch while queued.
                language.select_option("ko")
                language.select_option("ja")
                deadline = time.monotonic() + 20
                while not (set(paths.manifest_root.glob("*.json")) - before_manifests):
                    if time.monotonic() > deadline:
                        raise AssertionError(page.locator("#result").inner_text())
                    page.wait_for_timeout(50)
                expect(page.locator("#stop-queue")).to_be_disabled(timeout=10000)
                expect(page.locator("#preview")).to_be_visible()
                manifest_path = next(iter(set(paths.manifest_root.glob("*.json")) - before_manifests))
                manifest = json.loads(manifest_path.read_text())
                assert len(calls) == 1 and calls[0]["model"] == "nai-diffusion-5-full-medium"
                assert calls[0]["parameters"]["seed"] == 0
                assert "nai_language" not in json.dumps(manifest)
                page.locator("#apply-manifest").click()
                expect(language).to_have_value("ja")
                expect(rows.nth(0).locator("legend")).to_have_text("キャラクター 1")
                expect(rows.nth(21).locator(".character-prompt")).to_have_value(before[21]["prompt"])
                page.locator("#nai-metadata-file").set_input_files(manifest["output_path"])
                expect(page.locator("#apply-nai-metadata")).to_be_enabled()
                page.locator("#generation-import").evaluate("e=>e.open=true")
                page.locator("#apply-nai-metadata").click()
                expect(language).to_have_value("ja")
                expect(rows).to_have_count(22)
                expect(rows.nth(21).locator(".character-prompt")).to_have_value(before[21]["prompt"])
                cases.append("unchanged UI request, synthetic queue generation, manifest/history and PNG restore preserve language and hidden prompt data")

                page.locator('details[data-control-group="settings"]').evaluate("e=>e.open=true")
                page.locator('[data-control-group="settings"]').evaluate("e=>e.open=true")
                page.locator("#preset-name").fill("language-preservation")
                page.locator("#save-preset").click()
                expect(page.locator("#apply-preset")).to_be_enabled()
                language.select_option("ko")
                page.locator("#apply-preset").click()
                expect(language).to_have_value("ko")
                expect(rows.nth(21).locator(".character-prompt")).to_have_value(before[21]["prompt"])
                cases.append("preset does not override browser language")
                language.select_option("ja")
                page.locator("#nai-feature-guide").evaluate("e=>e.open=true")
                page.locator("#nai-feature-guide").scroll_into_view_if_needed()
                page.screenshot(path=str(output / "japanese-guidance.png"), full_page=True)

                # Missing keys render inert text, unknown explicit languages fall back to English.
                result = page.evaluate("""() => {
                  const i = window.NaiI18n;
                  const value = i.text('character', {number:'<img src=x onerror=alert(1)>'});
                  const el = document.createElement('p'); document.body.append(el);
                  i.bind(el,'character',{number:'<img src=x onerror=alert(1)>'});
                  const count = el.children.length; el.textContent='newer async error';
                  i.setLanguage('zz'); const preserved=el.textContent; el.remove();
                  return {value,count,preserved,lang:i.language,missing:i.text('unknown-key')};
                }""")
                assert result["count"] == 0 and result["preserved"] == "newer async error"
                assert result["lang"] == "en" and result["missing"] == "unknown-key"
                page.evaluate("localStorage.setItem('anima.locale','unsupported')")
                page.reload(wait_until="networkidle")
                expect(language).to_have_value("ko")
                cases.append("unsupported locale and missing-key fallback; inert interpolation; later async text not overwritten")

                # Cross-tab preference changes update mounted cards.
                second = context.new_page()
                second.goto(address, wait_until="networkidle")
                second.locator("#nai-language").select_option("ja")
                expect(language).to_have_value("ja")
                second.close()
                cases.append("cross-tab localStorage update")

                isolated = browser.new_context(locale="ja-JP")
                isolated.add_init_script("""Object.defineProperty(window, 'localStorage', {get(){throw new DOMException('blocked','SecurityError');}})""")
                fallback = isolated.new_page()
                fallback.on("pageerror", lambda e: errors.append(str(e)))
                fallback.goto(address, wait_until="networkidle")
                expect(fallback.locator("#nai-language")).to_have_value("ja")
                expect(fallback.locator("#nai-language-status")).to_contain_text("保存できません")
                fallback.locator("#nai-language").select_option("ko")
                expect(fallback.locator("#nai-language-status")).to_contain_text("저장할 수 없습니다")
                expect(fallback.locator("#provider-select")).to_be_enabled()
                isolated.close()
                cases.append("blocked localStorage retains working form and session-only language with visible notice")
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

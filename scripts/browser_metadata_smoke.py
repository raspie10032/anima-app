"""Browser acceptance for existing image metadata import; no generation or remote transport."""
from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
import threading
from pathlib import Path
from urllib.parse import urlparse

from PIL import Image
from PIL.PngImagePlugin import PngInfo
from playwright.sync_api import expect, sync_playwright

from anima_app.config import AppPaths
from anima_app.providers.novelai.metadata import read_image_metadata
from anima_app.server import create_http_server


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/metadata-smoke"))
    arguments = parser.parse_args()
    image_path = arguments.image.resolve()
    original_digest = hashlib.sha256(image_path.read_bytes()).hexdigest()
    imported = read_image_metadata(image_path)["request"]
    output = arguments.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []
    generation_posts: list[str] = []
    with tempfile.TemporaryDirectory(prefix="anima-metadata-browser-") as temporary:
        root = Path(temporary)
        paths = AppPaths(project_root=root)
        server = create_http_server("127.0.0.1", 0, paths=paths, default_dry_run=True)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                page = browser.new_page(locale="ko-KR", viewport={"width": 1600, "height": 1100})
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.on("request", lambda request: generation_posts.append(request.url)
                        if request.method == "POST" and urlparse(request.url).path in {"/api/jobs", "/api/generate"} else None)
                page.route("**/*", lambda route: route.continue_() if urlparse(route.request.url).hostname == "127.0.0.1" else route.abort())
                page.goto(f"http://127.0.0.1:{server.server_address[1]}", wait_until="networkidle")
                page.locator("#nai-metadata-file").set_input_files(image_path)
                apply = page.locator("#apply-nai-metadata")
                expect(apply).to_be_enabled()
                expect(page.locator("#provider-select")).to_have_value("local")
                expect(page.locator("#nai-metadata-model")).to_have_value(imported["nai_model"])
                apply.click()
                expect(page.locator("#provider-select")).to_have_value("novelai")
                for key, value in imported.items():
                    if key in {"provider", "nai_characters", "nai_use_coords", "nai_use_order"}:
                        continue
                    field = page.locator(f'[name="{key}"]')
                    if isinstance(value, bool):
                        assert field.is_checked() == value, key
                    else:
                        expect(field).to_have_value(str(value).removesuffix(".0"))
                expect(page.locator('[name="nai_limit_opus_free"]')).to_be_checked()
                page.locator("#nai-metadata-preview").scroll_into_view_if_needed()
                page.screenshot(path=str(output / "imported-live-image.png"))

                def fixture(name: str, **parameters) -> Path:
                    path = root / name
                    info = PngInfo()
                    info.add_text("Software", "NovelAI")
                    family = "V4.5" if parameters.get("model_hash") == "1229B44F" else "V5"
                    info.add_text("Source", f'NovelAI Diffusion {family} {parameters.get("model_hash", "DB276663")}')
                    info.add_itxt("Comment", json.dumps({"prompt": "fixture", "uc": "", "scale": 0, "seed": 0,
                                                          "request_type": "PromptGenerateRequest", **parameters}))
                    Image.new("RGBA", (64, 64), "white").save(path, pnginfo=info)
                    return path

                # Zero, empty and missing fields must not be replaced by defaults.
                missing = fixture("partial.png", model_hash="DB276663")
                page.locator("#nai-metadata-file").set_input_files(missing)
                expect(page.locator("#nai-metadata-status")).to_contain_text("partial.png: 생성 조건을 읽었습니다")
                apply.click()
                expect(page.locator("#seed")).to_have_value("0")
                expect(page.locator("#cfg")).to_have_value("0")
                expect(page.locator('[name="negative_prompt"]')).to_have_value("")
                expect(page.locator("#width")).to_have_value(str(imported["width"]))
                expect(page.locator("#nai-metadata-warnings")).to_contain_text("현재 폼 값을 유지")

                # Drag/drop unknown hash: inspect only until an explicit model choice.
                unknown = fixture("unknown.png", model_hash="DEADBEEF")
                page.locator("#nai-metadata-drop-zone").evaluate("""(node, bytes) => {
                    const transfer = new DataTransfer();
                    transfer.items.add(new File([new Uint8Array(bytes)], "unknown.png", {type: "image/png"}));
                    node.dispatchEvent(new DragEvent("drop", {bubbles: true, dataTransfer: transfer}));
                }""", list(unknown.read_bytes()))
                expect(page.locator("#nai-metadata-status")).to_contain_text("unknown.png: 생성 조건을 읽었습니다")
                expect(apply).to_be_disabled()
                page.locator("#nai-metadata-model").select_option("nai-diffusion-5-full")
                expect(apply).to_be_enabled()
                apply.click()
                expect(page.locator('[name="nai_model"]')).to_have_value("nai-diffusion-5-full")

                # An infill hash must remain an infill identity, not silently become T2I.
                infill = fixture("infill.png", model_hash="1229B44F", request_type="NativeInfillingRequest")
                page.locator("#nai-metadata-file").set_input_files(infill)
                expect(page.locator("#nai-metadata-status")).to_contain_text("infill.png: 생성 조건을 읽었습니다")
                expect(apply).to_be_enabled()
                expect(apply).to_have_text("인페인트 조건 적용")
                expect(page.locator("#nai-metadata-summary")).to_contain_text("nai-diffusion-4-5-full-inpainting")
                expect(page.locator("#nai-metadata-warnings")).to_contain_text("마스크는 생성 결과에 포함되지")
                apply.click()
                expect(page.locator('[name="nai_model"]')).to_have_value("nai-diffusion-4-5-full-inpainting")
                expect(page.locator('#nai-operation')).to_have_value("infill")
                expect(page.locator('[name="input_image"]')).to_have_value("")
                expect(page.locator('[name="mask_image"]')).to_have_value("")
                expect(page.locator('[name="nai_limit_opus_free"]')).to_be_checked()

                # A metadata-free image must leave the form untouched and clear the preview.
                invalid = root / "plain.png"
                Image.new("RGB", (64, 64), "white").save(invalid)
                page.locator("#nai-metadata-file").set_input_files(invalid)
                expect(page.locator("#nai-metadata-status")).to_contain_text("원본 PNG 또는 WebP")
                expect(page.locator("#nai-metadata-preview")).to_be_hidden()
                expect(apply).to_be_disabled()
                expect(page.locator('[name="nai_model"]')).to_have_value("nai-diffusion-4-5-full-inpainting")
                expect(page.locator("#seed")).to_have_value("0")
                assert not errors, errors
                assert not generation_posts, generation_posts
                browser.close()
            assert hashlib.sha256(image_path.read_bytes()).hexdigest() == original_digest
            assert not list(paths.input_root.rglob("*.upload"))
            report = {"status": "passed", "real_existing_image": str(image_path), "image_sha256": original_digest,
                      "page_errors": errors, "generation_posts": generation_posts,
                      "infill_sample": "synthetic metadata fixture, not a live infill generation",
                      "checked": ["live image form restore", "zero/empty values", "missing fields preserved",
                                  "drag/drop", "unknown hash/manual model", "infill identity and mode restore with cleared inputs",
                                  "invalid image unchanged form", "cost cap preserved", "temporary upload cleanup"]}
            (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(json.dumps(report, ensure_ascii=False, indent=2))
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


if __name__ == "__main__":
    main()

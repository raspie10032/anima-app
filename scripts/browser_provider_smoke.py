"""Optional Playwright acceptance using a local server and synthetic NAI transport.

Install playwright and its Chromium browser in a test environment before running.
No real token, NovelAI connection, GPU inference or model download is used.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import tempfile
import threading
import zipfile
from pathlib import Path
from urllib.parse import urlparse

import numpy as np
import requests
from playwright.sync_api import expect, sync_playwright
from safetensors.numpy import save_file
from PIL import Image
from PIL.PngImagePlugin import PngInfo

from anima_app.assets import required_t2i_model_files
from anima_app.config import AppPaths
from anima_app.defaults import DEFAULT_T2I_CHECKPOINT
from anima_app.output_names import allocate_output_path
from anima_app.providers import novelai
from anima_app.runtime.pipeline import T2IRenderOutput
from anima_app.server import create_http_server


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/provider-smoke"))
    arguments = parser.parse_args()
    output_dir = arguments.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    original_transport = novelai.client._requests_transport
    original_subscription_transport = novelai.client._requests_subscription_transport
    original_post = requests.post
    original_get = requests.get
    original_environment = {key: os.environ.get(key) for key in ("NAI_ACCESS_TOKEN", "NAI_API_TOKEN")}
    os.environ["NAI_ACCESS_TOKEN"] = "synthetic-browser-token"
    os.environ.pop("NAI_API_TOKEN", None)
    entered, release = threading.Event(), threading.Event()
    captured = []
    page_errors = []
    local_calls = []
    subscription_calls = []

    def mock_subscription(url, headers, timeout):
        subscription_calls.append(url)
        assert novelai.client._request_coordinator.lock.locked()
        # First attempt demonstrates a blocked V5 request, then the allowance recovers.
        return json.dumps({"active": True, "tier": 3,
                           "usage": {"percent": 1 if len(subscription_calls) == 1 else 2,
                                     "isNegative": False}}).encode()

    def forbid_remote(*_args, **_kwargs):
        raise AssertionError("External HTTP transport is disabled in browser acceptance")

    def mock_transport(_url, _headers, body, _timeout):
        payload = json.loads(body)
        captured.append(payload)
        entered.set()
        assert release.wait(15), "browser did not release the synthetic response"
        png = io.BytesIO()
        info = PngInfo()
        info.add_text("Software", "NovelAI")
        info.add_itxt("Comment", json.dumps({"model": payload["model"], "request_type": "PromptGenerateRequest", **payload["parameters"]}))
        Image.new("RGB", (payload["parameters"]["width"], payload["parameters"]["height"]), "purple").save(png, format="PNG", pnginfo=info)
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as archive:
            archive.writestr("image.png", png.getvalue())
        return output.getvalue()

    def local_renderer(request, paths):
        local_calls.append(request)
        paths.image_root.mkdir(parents=True, exist_ok=True)
        output = allocate_output_path(request, paths=paths, status="generated")
        Image.new("RGB", (request.width, request.height), "green").save(output)
        return T2IRenderOutput(output)

    requests.post = forbid_remote
    requests.get = forbid_remote
    novelai.client._requests_transport = mock_transport
    novelai.client._requests_subscription_transport = mock_subscription
    http_server = None
    try:
        with tempfile.TemporaryDirectory(prefix="anima-browser-provider-") as temporary:
            paths = AppPaths(project_root=Path(temporary), autocomplete_source=Path(temporary) / "autocomplete.txt")
            for asset in required_t2i_model_files(paths, DEFAULT_T2I_CHECKPOINT):
                asset.parent.mkdir(parents=True, exist_ok=True)
                save_file({"weight": np.asarray([1], dtype=np.float32)}, str(asset))
            http_server = create_http_server("127.0.0.1", 0, paths=paths, renderer=local_renderer)
            threading.Thread(target=http_server.serve_forever, daemon=True).start()
            address = f"http://127.0.0.1:{http_server.server_address[1]}"
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                context = browser.new_context(viewport={"width": 1440, "height": 1000})
                context.route("**/*", lambda route: route.continue_() if urlparse(route.request.url).hostname == "127.0.0.1" else route.abort())
                page = context.new_page()
                page.on("pageerror", lambda error: page_errors.append(str(error)))
                page.goto(address, wait_until="networkidle")
                expect(page.locator("#generate-button")).to_be_enabled()
                page.locator("#provider-select").select_option("novelai")
                page.locator('[data-control-group="model-style"] > summary').click()
                expect(page.locator("#novelai-settings")).to_be_visible()
                expect(page.locator("#local-model-settings")).to_be_hidden()
                page.locator("#nai-characters-panel").evaluate("node => {node.open = true}")
                for _ in range(22):
                    page.locator("#nai-add-character").click()
                expect(page.locator("#nai-add-character")).to_be_disabled()
                for _ in range(20):
                    page.locator("#nai-characters .nai-character").last.locator("button").click()
                expect(page.locator("#nai-characters .nai-character")).to_have_count(2)
                rows = page.locator("#nai-characters .nai-character")
                rows.nth(0).locator(".character-prompt").fill("(silver hair:1.05)")
                rows.nth(0).locator(".character-negative").fill("red hair")
                rows.nth(0).locator(".character-x").fill("0")
                rows.nth(0).locator(".character-y").fill("1")
                rows.nth(1).locator(".character-prompt").fill("black hair")
                rows.nth(1).locator(".character-x").fill("1")
                rows.nth(1).locator(".character-y").fill("0")
                page.locator("#nai-use-coords").uncheck()
                page.locator("#nai-use-order").uncheck()
                page.locator("#generation-prompt-tools").evaluate("node => {node.open = true}")
                page.locator("#prompt-converter").evaluate("node => {node.open = true}")
                for source, target, text in [
                    ("comfyui", "naiv4", "(hair:1.05)"), ("comfyui", "oldnai", "(hair:1.05)"),
                    ("naiv4", "comfyui", "1.05::hair ::"), ("naiv4", "oldnai", "1.05::hair ::"),
                    ("oldnai", "comfyui", "{hair}"), ("oldnai", "naiv4", "{hair}")]:
                    page.locator("#prompt").fill(text)
                    page.locator("#convert-source").select_option(source)
                    page.locator("#convert-target").select_option(target)
                    page.locator("#convert-preview").click()
                    expect(page.locator("#convert-apply")).to_be_enabled()
                    page.locator("#convert-apply").click()
                    expect(page.locator("#convert-apply")).to_be_disabled()
                page.locator("#convert-field").select_option("character:0:prompt")
                page.locator("#convert-source").select_option("comfyui")
                page.locator("#convert-target").select_option("naiv4")
                page.locator("#convert-preview").click()
                expect(page.locator("#convert-apply")).to_be_enabled()
                page.locator("#convert-apply").click()
                expect(rows.nth(0).locator(".character-prompt")).to_have_value("1.05::silver hair ::")
                page.locator("#convert-field").select_option("prompt")
                page.locator("#prompt").fill("(hair:1.05)")
                page.locator("#convert-preview").click()
                expect(page.locator("#convert-apply")).to_be_enabled()
                page.locator("#prompt").fill("two adults")
                expect(page.locator("#convert-apply")).to_be_disabled()
                page.locator("#nai-model").select_option("nai-diffusion-3")
                page.locator("#generate-button").click()
                assert page.locator("#nai-model").evaluate("node => Boolean(node.validationMessage)")
                assert not captured and not subscription_calls
                page.locator("#nai-model").select_option("nai-diffusion-5-curated")
                assert not page.locator("#nai-model").evaluate("node => Boolean(node.validationMessage)")
                rows.nth(0).locator(".character-x").fill("-0.1")
                page.locator("#generate-button").click()
                assert not captured and not subscription_calls
                rows.nth(0).locator(".character-x").fill("0")
                page.locator("#width").fill("64")
                page.locator("#height").fill("64")
                page.locator("#cfg").fill("0")
                page.locator("#seed").fill("0")
                page.locator("#nai-cfg-rescale").fill("0.4")
                page.locator('label[for="nai-variety-boost"]').click()
                expect(page.locator('[name="nai_variety_boost"]')).not_to_be_checked()
                page.locator("#generate-button").click()
                expect(page.locator("#result-summary")).to_contain_text("V5 무료 잔여량", timeout=10000)
                expect(page.locator("#stop-queue")).to_be_disabled(timeout=10000)
                assert len(captured) == 0, "ineligible request reached generation transport"
                # Settings are in a closed native details panel.
                page.locator('[data-control-group="settings"]').evaluate("node => {node.open = true}")
                page.locator("#preset-name").fill("browser NAI")
                page.locator("#save-preset").click()
                expect(page.locator("#preset-status")).to_contain_text("저장")
                page.locator("#generate-button").click()
                assert entered.wait(5)
                page.reload(wait_until="networkidle")
                expect(page.locator("#stop-queue")).to_be_enabled()
                page.locator("#stop-queue").click()
                expect(page.locator("#queue-status")).to_contain_text("NovelAI", timeout=5000)
                release.set()
                expect(page.locator("#preview")).to_be_visible(timeout=10000)
                expect(page.locator("#stop-queue")).to_be_disabled(timeout=10000)
                page.locator("#apply-manifest").click()
                expect(page.locator("#provider-select")).to_have_value("novelai")
                expect(page.locator("#seed")).to_have_value("0")
                expect(page.locator("#cfg")).to_have_value("0")
                expect(page.locator("#nai-cfg-rescale")).to_have_value("0.4")
                expect(page.locator('[name="nai_variety_boost"]')).not_to_be_checked()
                expect(page.locator("#sam3-tools")).to_be_hidden()
                expect(page.locator("#nai-characters .nai-character")).to_have_count(2)
                assert not page.locator("#nai-use-coords").is_checked()
                assert not page.locator("#nai-use-order").is_checked()
                # Remote synthetic PNG carries the exact submitted character metadata.
                page.locator("#generation-import").evaluate("node => {node.open = true}")
                page.locator("#nai-metadata-file").set_input_files(next(paths.image_root.glob("*.png")))
                expect(page.locator("#apply-nai-metadata")).to_be_enabled()
                page.locator("#apply-nai-metadata").click()
                page.locator("#nai-characters-panel").evaluate("node => {node.open = true}")
                expect(rows.nth(0).locator(".character-prompt")).to_have_value("1.05::silver hair ::")
                expect(rows.nth(0).locator(".character-x")).to_have_value("0")
                expect(rows.nth(1).locator(".character-negative")).to_have_value("")
                expect(page.locator("#result-summary")).to_contain_text("보존")
                page.locator(".control-frame").evaluate("node => {node.scrollTop = 0}")
                page.screenshot(path=str(output_dir / "novelai-mock.png"), full_page=True)
                # Exercise provider round trips through saved settings too.
                page.locator("#provider-select").select_option("local")
                page.locator('[data-control-group="settings"]').evaluate("node => {node.open = true}")
                page.locator("#preset-select").select_option(label="browser NAI")
                page.locator("#apply-preset").click()
                expect(page.locator("#provider-select")).to_have_value("novelai")
                expect(page.locator("#cfg")).to_have_value("0")
                page.locator("#provider-select").select_option("local")
                page.locator('[data-control-group="model-style"]').evaluate("node => {node.open = true}")
                expect(page.locator("#local-model-settings")).to_be_visible()
                assert page.locator("#steps").get_attribute("max") == "100"
                os.environ.pop("NAI_ACCESS_TOKEN", None)
                page.reload(wait_until="networkidle")
                expect(page.locator("#generate-button")).to_be_enabled()
                page.locator("#width").fill("64")
                page.locator("#height").fill("64")
                page.locator("#generate-button").click()
                expect(page.locator("#stop-queue")).to_be_disabled(timeout=10000)
                expect(page.locator("#preview")).to_be_visible(timeout=10000)
                expect(page.locator("#result-summary")).to_contain_text("로컬 Anima")
                page.screenshot(path=str(output_dir / "local-mock.png"), full_page=True)
                page.locator("#provider-select").select_option("novelai")
                expect(page.locator("#generate-button")).to_be_disabled()
                context.close()
                browser.close()
            assert len(captured) == 1, "duplicate remote submission"
            assert len(subscription_calls) == 2
            assert captured[0]["parameters"]["n_samples"] == 1
            assert captured[0]["parameters"]["seed"] == 0
            assert len(captured[0]["parameters"]["v4_prompt"]["caption"]["char_captions"]) == 2
            assert captured[0]["parameters"]["v4_prompt"]["use_coords"] is False
            assert len(local_calls) == 1
            assert not page_errors, page_errors
            for manifest in paths.manifest_root.glob("*.json"):
                assert "synthetic-browser-token" not in manifest.read_text()
            report = {"status": "passed", "evidence": "browser with mocked remote transport and local renderer",
                      "remote_calls": len(captured), "mock_subscription_calls": len(subscription_calls),
                      "live_nai_requests": 0, "local_renderer_calls_without_token": len(local_calls),
                      "page_errors": page_errors, "checks": ["provider switching", "canonical preset save/restore",
                      "queue refresh recovery", "running remote cancellation", "received PNG retained",
                      "zero seed and CFG restore", "history settings restore", "local without token", "token absence gate",
                      "V5 1 percent blocked before generation", "V5 2 percent accepted under request lock",
                      "22 saved character slots and removal", "all six conversion previews and apply",
                      "V3 and out-of-range coordinate blocked in browser before account lookup",
                      "character conversion and stale preview invalidation", "character payload under Opus guard",
                      "character preset and manifest restore", "synthetic PNG character metadata import"]}
            (output_dir / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
            print(json.dumps(report, indent=2))
    finally:
        release.set()
        if http_server is not None:
            http_server.shutdown()
            http_server.server_close()
        novelai.client._requests_transport = original_transport
        novelai.client._requests_subscription_transport = original_subscription_transport
        requests.post = original_post
        requests.get = original_get
        for key, value in original_environment.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


if __name__ == "__main__":
    main()

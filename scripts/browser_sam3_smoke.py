"""SAM3 UI acceptance with real orchestration and synthetic model outputs only."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
import threading
import time
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch
from urllib.parse import urlparse

import numpy as np
import requests
from PIL import Image, ImageDraw
from playwright.sync_api import expect, sync_playwright

from anima_app.config import AppPaths
from anima_app.providers import novelai
from anima_app.server import create_http_server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--firefox-hold", action="store_true")
    args = parser.parse_args()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    queries, images, errors, cases, remote = [], [], [], [], []
    state = {"empty": False}

    class Predictor:
        def __init__(self, overrides):
            assert overrides["device"] == "cpu" and overrides["conf"] == .5

        def set_image(self, image):
            assert isinstance(image, Image.Image) and image.mode == "RGB"
            self.size = image.size
            images.append(list(image.getpixel((0, 0))))

        def __call__(self, *, text):
            queries.append(text[0])
            boxes = {"face": [(10, 10, 30, 40), (90, 10, 110, 40)],
                     "eye": [(15, 15, 20, 18), (95, 15, 100, 18)], "hand": [(50, 50, 65, 70)]}
            masks = []
            for box in [] if state["empty"] else boxes[text[0]]:
                mask = Image.new("L", self.size)
                ImageDraw.Draw(mask).rectangle(box, fill=255)
                array = np.array(mask, dtype=np.float32) / 255
                masks.append(SimpleNamespace(cpu=lambda a=array: SimpleNamespace(numpy=lambda: a)))
            return [SimpleNamespace(masks=SimpleNamespace(data=masks))]

    sam = ModuleType("ultralytics.models.sam")
    sam.SAM3SemanticPredictor = Predictor
    tokenizer = ModuleType("clip.simple_tokenizer")
    tokenizer.SimpleTokenizer = lambda: (lambda text: text)

    def forbidden_remote(*a, **k):
        remote.append("forbidden transport attempted")
        raise AssertionError("No NAI account, encode or generation calls permitted")

    original_http = requests.Session.request

    def loopback(session, method, url, **kwargs):
        assert urlparse(url).hostname in {"127.0.0.1", "localhost"}, "External HTTP forbidden"
        return original_http(session, method, url, **kwargs)

    with (patch.dict(sys.modules, {"ultralytics.models.sam": sam, "clip.simple_tokenizer": tokenizer}),
          patch.dict(os.environ, {"NAI_ACCESS_TOKEN": "synthetic-sam3-token", "NAI_API_TOKEN": ""}),
          patch.object(requests.Session, "request", loopback),
          patch.object(novelai.client, "_requests_transport", forbidden_remote),
          patch.object(novelai.client, "_requests_subscription_transport", forbidden_remote),
          tempfile.TemporaryDirectory(prefix="anima-sam3-ui-") as temporary):
        root = Path(temporary)
        paths = AppPaths(root, autocomplete_source=root / "autocomplete.txt")
        model = paths.model_root / "detectors/sam3.pt"
        model.parent.mkdir(parents=True)
        model.write_bytes(b"synthetic, not model weights")
        source = root / "source.png"
        Image.new("RGB", (128, 128), (249, 13, 31)).save(source)
        before_hash = hashlib.sha256(source.read_bytes()).hexdigest()
        server = create_http_server("127.0.0.1", 0, paths=paths)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        address = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=True)
                page = browser.new_page(locale="ko-KR", viewport={"width": 1440, "height": 1100})
                page.on("pageerror", lambda e: errors.append(str(e)))
                page.route("**/*", lambda r: r.continue_() if urlparse(r.request.url).hostname in {"127.0.0.1", "localhost", None} else r.abort())
                page.goto(address)
                page.locator("#provider-select").select_option("novelai")
                page.locator('[name="prompt"]').fill("SAM3 preview")
                page.locator("#nai-operation").select_option("detail")
                page.locator("#nai-input-file").set_input_files(source)
                expect(page.locator('[name="input_image"]')).not_to_have_value("")
                page.locator("#nai-detailer-panel summary").click()
                page.locator("#nai-detailer-backend").select_option("sam3")
                page.locator("#nai-detailer-preview").check()

                def generate():
                    before = {j["id"] for j in page.request.get(address + "/api/jobs").json()["items"]}
                    page.locator("#generate-button").click()
                    deadline = time.monotonic() + 20
                    while time.monotonic() < deadline:
                        fresh = [j for j in page.request.get(address + "/api/jobs").json()["items"] if j["id"] not in before]
                        if fresh and fresh[0]["status"] in {"completed", "failed", "cancelled"}:
                            expect(page.locator("#stop-queue")).to_be_disabled()
                            return fresh[0]
                        page.wait_for_timeout(50)
                    page.screenshot(path=str(output / "harness-error.png"))
                    raise AssertionError({"result": page.locator("#result").inner_text(), "errors": errors,
                                          "invalid": page.locator(":invalid").evaluate_all("nodes => nodes.map(n => ({name:n.name,id:n.id,value:n.value,message:n.validationMessage}))"),
                                          "jobs": page.request.get(address + "/api/jobs").json()})

                for selected, expected in [(["face"], ["face", "face"]), (["eyes"], ["eyes", "eyes"]),
                                           (["hands"], ["hands"]), (["face", "eyes", "hands"], ["face", "hands", "face"])]:
                    for concept in ("face", "eyes", "hands"):
                        page.locator(f'.nai-detailer-concept[value="{concept}"]').set_checked(concept in selected)
                    start_queries, start_images = len(queries), len(images)
                    job = generate()
                    assert job["status"] == "completed", job
                    result = job["result"]
                    manifest = json.loads(Path(result["manifest_path"]).read_text())
                    assert [r["concept"] for r in manifest["novelai"]["detailer"]] == expected, manifest["novelai"]["detailer"]
                    assert queries[start_queries:] == [{"eyes": "eye", "hands": "hand"}.get(c, c) for c in selected]
                    assert images[start_images:] == [[249, 13, 31]]
                    name = "-".join(selected)
                    (output / f"{name}-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
                    (output / f"{name}-preview.png").write_bytes(Path(result["output_path"]).read_bytes())
                    cases.append({"case": name, "status": "passed", "concepts": expected})

                page.locator("#apply-manifest").click()
                expect(page.locator("#nai-detailer-backend")).to_have_value("sam3")
                expect(page.locator("#nai-detailer-preview")).to_be_checked()
                for concept in ("face", "eyes", "hands"):
                    expect(page.locator(f'.nai-detailer-concept[value="{concept}"]')).to_be_checked()
                page.reload()
                page.locator('.history-action[title="생성 정보 보기"]').first.click()
                expect(page.locator("#preview")).to_be_visible()
                page.locator("#apply-manifest").click()
                expect(page.locator("#nai-detailer-backend")).to_have_value("sam3")
                cases.append({"case": "history-settings-and-reload", "status": "passed"})

                state["empty"] = True
                job = generate()
                assert job["status"] == "completed", job
                manifest = json.loads(Path(job["result"]["manifest_path"]).read_text())
                assert manifest["novelai"]["detailer"] == []
                cases.append({"case": "empty-detection-preview", "status": "passed"})
                state["empty"] = False

                page.locator("#nai-operation").select_option("generate")
                if not page.locator("#nai-detailer-panel").evaluate("node => node.open"):
                    page.locator("#nai-detailer-panel summary").click()
                page.locator("#nai-detailer-enabled").check()
                page.locator("#nai-detailer-preview").uncheck()
                for missing in ("runtime", "tokenizer"):
                    if missing == "runtime":
                        del sam.SAM3SemanticPredictor
                    else:
                        sys.modules["clip.simple_tokenizer"] = None
                    before_queries = len(queries)
                    job = generate()
                    assert job["status"] == "failed" and job["result"]["error_code"] == "sam3_runtime_unavailable", job
                    assert len(queries) == before_queries and not remote
                    cases.append({"case": f"missing-{missing}-before-base-generation", "status": "passed"})
                    sam.SAM3SemanticPredictor = Predictor
                    sys.modules["clip.simple_tokenizer"] = tokenizer

                page.locator("#nai-operation").select_option("detail")
                page.locator("#nai-detailer-preview").check()
                page.screenshot(path=str(output / "sam3-ui.png"))
                assert not errors and not remote and hashlib.sha256(source.read_bytes()).hexdigest() == before_hash
                browser.close()
            if args.firefox_hold:
                print(json.dumps({"url": address, "input_image": str(source), "evidence": "synthetic SAM3, real UI/orchestration; no remote requests"}), flush=True)
                input("Firefox inspection: press ENTER to stop the isolated server.\n")
            report = {"status": "passed", "cases": cases, "page_errors": errors, "queries": queries,
                      "rgb_images": images, "live_nai_requests": 0, "remote_transport_attempts": remote,
                      "fixture_sha256": before_hash, "evidence": "synthetic predictor output; real app detector/preflight/service/UI"}
            (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
            print(json.dumps(report, indent=2), flush=True)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(5)


if __name__ == "__main__":
    main()

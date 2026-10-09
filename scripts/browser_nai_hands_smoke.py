"""Hands UI acceptance: synthetic YOLO/SAM/NAI, actual detector and app orchestration."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import sys
import tempfile
import threading
import time
import zipfile
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


def tensor(array):
    return SimpleNamespace(cpu=lambda: SimpleNamespace(numpy=lambda: np.asarray(array)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    calls, accounts, detections, masks, errors, cases = [], [], [], [], [], []
    state = {"empty": False, "hold": False}
    entered, release = threading.Event(), threading.Event()
    boxes = {"face_yolov8n.pt": [(20, 10, 50, 40)], "full_eyes_detect_v1.pt": [(25, 15, 40, 20)],
             "hand_yolov8n.pt": [(90, 60, 110, 80), (190, 60, 210, 80)]}

    class YOLO:
        def __init__(self, path):
            self.name = Path(path).name

        def __call__(self, source, **kwargs):
            assert isinstance(source, Image.Image) and source.mode == "RGB"
            detections.append(self.name)
            array = np.array([] if state["empty"] else boxes[self.name]).reshape(-1, 4)
            return [SimpleNamespace(boxes=SimpleNamespace(xyxy=tensor(array)))]

    class SAM:
        def __init__(self, path):
            assert Path(path).name == "sam_b.pt"

        def __call__(self, source, *, bboxes, **kwargs):
            assert isinstance(source, Image.Image) and source.mode == "RGB"
            assert source.getpixel((0, 0)) == (249, 13, 31)
            masks.append(bboxes)
            if state["hold"]:
                entered.set()
                assert release.wait(15), "Held local mask inference was not released"
            mask = Image.new("L", source.size)
            ImageDraw.Draw(mask).ellipse(tuple(bboxes[0]), fill=255)
            return [SimpleNamespace(masks=SimpleNamespace(data=[tensor(np.array(mask, dtype=np.float32) / 255)]))]

    ultra = ModuleType("ultralytics")
    ultra.YOLO, ultra.SAM = YOLO, SAM

    def transport(url, headers, body, timeout):
        payload = json.loads(body)
        calls.append(payload)
        assert payload["action"] == "infill"
        params = payload["parameters"]
        png, archive = io.BytesIO(), io.BytesIO()
        Image.new("RGB", (params["width"], params["height"]), "purple").save(png, format="PNG")
        with zipfile.ZipFile(archive, "w") as zipped:
            zipped.writestr("image.png", png.getvalue())
        return archive.getvalue()

    def account(*args):
        accounts.append(len(calls))
        return json.dumps({"active": True, "tier": 3, "usage": {"percent": 100, "isNegative": False}}).encode()

    original_http = requests.Session.request

    def loopback(session, method, url, **kwargs):
        assert urlparse(url).hostname in {"127.0.0.1", "localhost"}, "External HTTP forbidden"
        return original_http(session, method, url, **kwargs)

    with (patch.dict(sys.modules, {"ultralytics": ultra}),
          patch.dict(os.environ, {"NAI_ACCESS_TOKEN": "synthetic-hands-token", "NAI_API_TOKEN": ""}),
          patch.object(requests.Session, "request", loopback),
          patch.object(novelai.client, "_requests_transport", transport),
          patch.object(novelai.client, "_requests_subscription_transport", account),
          patch.object(novelai.client, "REQUEST_INTERVAL_SECONDS", 0),
          tempfile.TemporaryDirectory(prefix="anima-hands-ui-") as temporary):
        root = Path(temporary)
        paths = AppPaths(root, autocomplete_source=root / "autocomplete.txt")
        model_root = paths.model_root / "detectors"
        model_root.mkdir(parents=True)
        for name in (*boxes, "sam_b.pt"):
            (model_root / name).write_bytes(b"synthetic model placeholder, not real weights")
        source = root / "source.png"
        Image.new("RGB", (256, 128), (249, 13, 31)).save(source)
        before_hash = hashlib.sha256(source.read_bytes()).hexdigest()
        server = create_http_server("127.0.0.1", 0, paths=paths)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        address = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=True)
                page = browser.new_page(viewport={"width": 1440, "height": 1100})
                page.on("pageerror", lambda e: errors.append(str(e)))
                page.route("**/*", lambda r: r.continue_() if urlparse(r.request.url).hostname in {"127.0.0.1", "localhost", None} else r.abort())
                page.goto(address)
                page.locator("#provider-select").select_option("novelai")
                page.locator('[name="prompt"]').fill("hands preview")
                page.locator('[name="seed"]').fill("42")
                page.locator("#nai-operation").select_option("detail")
                page.locator("#nai-input-file").set_input_files(source)
                expect(page.locator('[name="input_image"]')).not_to_have_value("")
                page.locator("#nai-detailer-panel summary").click()
                page.locator("#nai-detailer-backend").select_option("sam_b")
                page.locator("#nai-detailer-preview").check()

                def select(concepts):
                    for concept in ("face", "eyes", "hands"):
                        page.locator(f'.nai-detailer-concept[value="{concept}"]').set_checked(concept in concepts)

                def start_job():
                    before = {j["id"] for j in page.request.get(address + "/api/jobs").json()["items"]}
                    page.locator("#generate-button").click()
                    deadline = time.monotonic() + 20
                    while time.monotonic() < deadline:
                        fresh = [j for j in page.request.get(address + "/api/jobs").json()["items"] if j["id"] not in before]
                        if fresh:
                            return fresh[0]["id"]
                        page.wait_for_timeout(50)
                    raise AssertionError(page.locator("#result").inner_text())

                def finish(job_id):
                    deadline = time.monotonic() + 20
                    while time.monotonic() < deadline:
                        job = next(j for j in page.request.get(address + "/api/jobs").json()["items"] if j["id"] == job_id)
                        if job["status"] in {"completed", "failed", "cancelled"}:
                            expect(page.locator("#stop-queue")).to_be_disabled()
                            return job
                        page.wait_for_timeout(50)
                    raise AssertionError(job)

                def manifest(job, name):
                    assert job["status"] == "completed", job
                    data = json.loads(Path(job["result"]["manifest_path"]).read_text())
                    (output / f"{name}-manifest.json").write_text(json.dumps(data, indent=2) + "\n")
                    (output / f"{name}.png").write_bytes(Path(job["result"]["output_path"]).read_bytes())
                    return data

                for concepts, expected in [(["hands"], ["hands", "hands"]),
                                           (["face", "eyes", "hands"], ["face", "hands", "hands"])]:
                    select(concepts)
                    name = "preview-" + "-".join(concepts)
                    data = manifest(finish(start_job()), name)
                    assert [r["concept"] for r in data["novelai"]["detailer"]] == expected
                    assert not calls and not accounts
                    expect(page.locator("#preview")).to_be_visible()
                    cases.append({"case": name, "status": "passed"})

                select(["hands"])
                page.locator("#nai-detailer-preview").uncheck()
                data = manifest(finish(start_job()), "hands-repaint")
                report = data["novelai"]["detailer"]
                assert len(report) == 2 and all(r["concept"] == "hands" and r["status"] == "edited" for r in report)
                assert [r["seed"] for r in report] == [42, 43]
                assert len(calls) == len(accounts) == 2
                assert all(r["transmitted_model"].endswith("inpainting") and r["opus_preflight"]["status"] == "verified" for r in report)
                with Image.open(data["output_path"]) as result:
                    assert result.getpixel((100, 70)) == result.getpixel((200, 70)) == (128, 0, 128)
                    assert result.getpixel((35, 25)) == result.getpixel((0, 0)) == (249, 13, 31)
                    with Image.open(data["variants"]["detailer_mask"]) as mask:
                        outside = np.array(mask.convert("L")) == 0
                    expected_source = np.full((128, 256, 3), (249, 13, 31), dtype=np.uint8)
                    assert outside.any() and np.array_equal(np.array(result)[outside], expected_source[outside])
                (output / "hands-repaint-mask.png").write_bytes(Path(data["variants"]["detailer_mask"]).read_bytes())
                request_masks = []
                import base64
                for call in calls:
                    with Image.open(io.BytesIO(base64.b64decode(call["parameters"]["mask"]))) as mask:
                        request_masks.append(mask.copy())
                    assert request_masks[-1].getbbox()
                cases.append({"case": "two-hand-focused-repaint-with-preserved-face", "status": "passed"})

                page.reload()
                page.locator('.history-action[title="생성 정보 보기"]').first.click()
                expect(page.locator("#preview")).to_be_visible()
                page.locator("#apply-manifest").click()
                expect(page.locator("#nai-detailer-backend")).to_have_value("sam_b")
                expect(page.locator('.nai-detailer-concept[value="hands"]')).to_be_checked()
                for concept in ("face", "eyes"):
                    expect(page.locator(f'.nai-detailer-concept[value="{concept}"]')).not_to_be_checked()
                cases.append({"case": "history-settings-and-result-restored", "status": "passed"})
                if not page.locator("#nai-detailer-panel").evaluate("node => node.open"):
                    page.locator("#nai-detailer-panel summary").click()
                page.locator("#nai-detailer-preview").check()
                state["empty"] = True
                data = manifest(finish(start_job()), "empty-hands-preview")
                assert data["novelai"]["detailer"] == [] and len(calls) == 2
                cases.append({"case": "empty-hands-preview", "status": "passed"})
                state["empty"] = False

                state["hold"] = True
                offset = len(masks)
                job_id = start_job()
                assert entered.wait(5)
                page.locator("#stop-queue").click()
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    observed = next(j for j in page.request.get(address + "/api/jobs").json()["items"] if j["id"] == job_id)
                    if observed["cancel_requested"]:
                        break
                    page.wait_for_timeout(50)
                assert observed["cancel_requested"], observed
                release.set()
                job = finish(job_id)
                assert job["status"] == "cancelled", job
                assert len(masks) == offset + 1 and len(calls) == len(accounts) == 2
                state["hold"] = False
                cases.append({"case": "cancel-during-sam-stops-second-hand", "status": "passed"})

                page.locator("#nai-operation").select_option("generate")
                if not page.locator("#nai-detailer-panel").evaluate("node => node.open"):
                    page.locator("#nai-detailer-panel summary").click()
                page.locator("#nai-detailer-enabled").check()
                page.locator("#nai-detailer-preview").uncheck()
                for missing in ("hand_weights", "sam_adapter"):
                    before_detections = len(detections)
                    if missing == "hand_weights":
                        (model_root / "hand_yolov8n.pt").unlink()
                    else:
                        del ultra.SAM
                    job = finish(start_job())
                    expected = "generation_invalid_request" if missing == "hand_weights" else "sam_b_runtime_unavailable"
                    assert job["status"] == "failed" and job["result"]["error_code"] == expected, job
                    assert len(calls) == len(accounts) == 2 and len(detections) == before_detections
                    cases.append({"case": f"missing-{missing}-before-base-generation", "status": "passed"})
                    (model_root / "hand_yolov8n.pt").write_bytes(b"synthetic model placeholder")
                    ultra.SAM = SAM
                page.screenshot(path=str(output / "hands-ui.png"))
                assert not errors and hashlib.sha256(source.read_bytes()).hexdigest() == before_hash
                browser.close()
            report = {"status": "passed", "cases": cases, "page_errors": errors, "detections": detections,
                      "mask_calls": len(masks), "mock_generation_requests": len(calls), "mock_account_requests": len(accounts),
                      "live_nai_requests": 0, "fixture_sha256": before_hash,
                      "evidence": "synthetic YOLO/SAM results and synthetic NAI; actual detector/preflight/UI/service/queue"}
            (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
            print(json.dumps(report, indent=2), flush=True)
        finally:
            release.set()
            server.shutdown()
            server.server_close()
            thread.join(5)


if __name__ == "__main__":
    main()

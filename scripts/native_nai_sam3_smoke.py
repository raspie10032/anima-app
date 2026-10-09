"""Offline SAM3 acceptance using real local weights and the NAI detector path."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import time
from importlib.metadata import version
from pathlib import Path

import requests
from PIL import Image, ImageDraw

from anima_app.config import AppPaths
from anima_app.providers.novelai.detailer import Detector, validate_settings


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--detectors", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    os.environ["YOLO_AUTOINSTALL"] = "false"
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"

    def forbid(*a, **k):
        raise AssertionError("Network is forbidden during native SAM3 acceptance")

    requests.Session.request = forbid
    socket.socket.connect = forbid
    import ultralytics.models.sam as sam
    import ultralytics.utils as utils
    utils.ONLINE = False
    real_predictor = sam.SAM3SemanticPredictor
    queries = []
    image_calls = []

    class ObservedPredictor(real_predictor):
        def set_image(self, image):
            assert isinstance(image, Image.Image) and image.mode == "RGB"
            image_calls.append({"size": list(image.size), "mode": image.mode})
            return super().set_image(image)

        def __call__(self, *, text):
            start = time.monotonic()
            results = super().__call__(text=text)
            entry = {"text": text, "seconds": time.monotonic() - start,
                     "instances": sum(len(r.masks.data) for r in results if r.masks is not None)}
            queries.append(entry)
            print(json.dumps(entry), flush=True)
            return results

    sam.SAM3SemanticPredictor = ObservedPredictor
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    model = args.detectors / "sam3.pt"
    before = {"source": digest(args.image), "model": digest(model)}
    print("Existing input/model hashes recorded; loading CPU SAM3", flush=True)
    with Image.open(args.image) as opened:
        source = opened.convert("RGB")
    paths = AppPaths(output, face_detailer_detector_fallback_sources=(args.detectors,))
    start = time.monotonic()
    try:
        regions = Detector(paths, validate_settings({"backend": "sam3", "concepts": ["face", "eyes", "hands"]})).detect(source, lambda: False)
    finally:
        sam.SAM3SemanticPredictor = real_predictor
    assert len(image_calls) == 1 and [q["text"] for q in queries] == [["face"], ["eye"], ["hand"]]
    assert all(q["instances"] > 0 for q in queries), "Visible face, eyes and hands must be detected on this fixture"
    assert {r.concept for r in regions} == {"face", "hands"}, "Eyes must merge into faces"
    preview = source.copy()
    draw = ImageDraw.Draw(preview)
    for index, region in enumerate(regions):
        assert region.mask.size == source.size and region.mask.getbbox()
        region.mask.save(output / f"mask-{index + 1}-{region.concept}.png")
        draw.rectangle(region.box, outline="lime" if region.concept == "face" else "cyan", width=3)
    preview.save(output / "sam3-preview.png")
    assert {"source": digest(args.image), "model": digest(model)} == before
    report = {"status": "passed", "evidence": "real CPU SAM3 inference; existing detector-preview derivative fixture",
              "source_path": str(args.image.resolve()), "model_path": str(model.resolve()),
              "sha256": before, "queries": queries, "image_calls": image_calls,
              "regions": [{"concept": r.concept, "bbox": list(r.box)} for r in regions],
              "seconds": time.monotonic() - start, "live_nai_requests": 0, "model_downloads": 0,
              "versions": {n: version(n) for n in ("ultralytics", "torch", "clip")}}
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    main()

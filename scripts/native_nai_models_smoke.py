"""Read-only native YOLO/SAM/WD checks. No generation, downloads or account lookup."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from importlib.metadata import version
from pathlib import Path

import requests
from PIL import Image, ImageDraw

from anima_app.config import AppPaths
from anima_app.providers.novelai.detailer import Detector, validate_settings
from anima_app.providers.novelai.wd_tagger import WDTagger


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--detectors", type=Path, required=True)
    parser.add_argument("--sam", type=Path, required=True)
    parser.add_argument("--wd-cache", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/all-nai-port-20261009/native"))
    arguments = parser.parse_args()
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"

    def forbid(*a, **k):
        raise AssertionError("External HTTP is forbidden in native model smoke")

    requests.get = requests.post = forbid
    output = arguments.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    image_hash = hashlib.sha256(arguments.image.read_bytes()).hexdigest()
    with Image.open(arguments.image) as opened:
        source = opened.convert("RGB")
    paths = AppPaths(project_root=output, face_detailer_detector_fallback_sources=(arguments.detectors, arguments.sam))
    regions = Detector(paths, validate_settings({})).detect(source, lambda: False)
    assert regions, "No detections; use a fixture with a visible face"
    assert all(region.mask.getbbox() for region in regions)
    tagger = WDTagger(arguments.wd_cache, device="cpu", batch_size=4)
    scores = tagger.score([source.crop(region.box) for region in regions])
    assert len(scores) == len(regions) and all(all(0 <= value <= 1 for value in score.values()) for score in scores)
    preview = source.copy()
    draw = ImageDraw.Draw(preview)
    for index, region in enumerate(regions):
        region.mask.save(output / f"mask-{index + 1}.png")
        draw.rectangle(region.box, outline="lime", width=3)
    preview.save(output / "detected-preview.png")
    assert hashlib.sha256(arguments.image.read_bytes()).hexdigest() == image_hash
    report = {"status": "passed", "evidence": "real local CPU YOLO/SAM/WD inference with existing assets",
              "image_sha256": image_hash, "regions": len(regions), "tag_count": len(scores[0]),
              "boxes": [list(region.box) for region in regions], "live_nai_requests": 0,
              "downloads": 0, "versions": {name: version(name) for name in ("ultralytics", "timm", "segment-anything")}}
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

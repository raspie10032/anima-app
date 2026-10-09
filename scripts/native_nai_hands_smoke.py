"""Offline acceptance of existing YOLO hand weights and both real SAM B adapters."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import tempfile
import time
from importlib.metadata import version
from pathlib import Path
from unittest.mock import patch

import numpy as np
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
    parser.add_argument("--hand-dir", type=Path, required=True)
    parser.add_argument("--sam-pth", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    os.environ.update(YOLO_AUTOINSTALL="false", HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1")

    def forbidden(*a, **k):
        raise AssertionError("Network forbidden during native YOLO/SAM acceptance")

    requests.Session.request = forbidden
    socket.socket.connect = forbidden
    import ultralytics
    import ultralytics.utils
    import segment_anything
    ultralytics.utils.ONLINE = False
    original_yolo, original_sam, original_predictor = ultralytics.YOLO, ultralytics.SAM, segment_anything.SamPredictor
    cases, detections, masks, images = [], [], [], []
    with Image.open(args.image) as opened:
        source = opened.convert("RGB")
    assets = [args.image, args.detectors / "face_yolov8n.pt", args.detectors / "full_eyes_detect_v1.pt",
              args.detectors / "sam_b.pt", args.sam_pth, args.hand_dir / "hand_yolov8n.pt", args.hand_dir / "hand_yolov8s.pt"]
    before = {str(p.resolve()): digest(p) for p in assets}
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)

    class ObservedYOLO(original_yolo):
        def __init__(self, path):
            self.observed_name = Path(path).name
            super().__init__(path)

        def __call__(self, image, **kwargs):
            results = super().__call__(image, **kwargs)
            detections.append({"model": self.observed_name, "boxes": [r.boxes.xyxy.cpu().numpy().tolist() for r in results],
                               "device": kwargs["device"], "threshold": kwargs["conf"]})
            return results

    class ObservedSAM(original_sam):
        def __call__(self, image, **kwargs):
            assert isinstance(image, Image.Image) and image.mode == "RGB"
            assert image.getpixel((0, 0)) == source.getpixel((0, 0))
            images.append({"adapter": "pt", "mode": image.mode, "pixel": list(image.getpixel((0, 0)))})
            results = super().__call__(image, **kwargs)
            assert results and results[0].masks is not None, "SAM returned no masks; rectangular fallback is not native SAM evidence"
            pixels = [int(np.count_nonzero(t.cpu().numpy())) for t in results[0].masks.data]
            assert pixels and all(pixels)
            masks.append({"adapter": "pt", "pixels": pixels})
            return results

    class ObservedPredictor(original_predictor):
        def set_image(self, image):
            assert tuple(image[0, 0]) == source.getpixel((0, 0))
            images.append({"adapter": "pth", "mode": "RGB array", "pixel": [int(v) for v in image[0, 0]]})
            return super().set_image(image)

        def predict(self, **kwargs):
            results = super().predict(**kwargs)
            pixels = [int(np.count_nonzero(m)) for m in results[0]]
            assert pixels and all(pixels)
            masks.append({"adapter": "pth", "pixels": pixels})
            return results

    with (patch.object(ultralytics, "YOLO", ObservedYOLO), patch.object(ultralytics, "SAM", ObservedSAM),
          patch.object(segment_anything, "SamPredictor", ObservedPredictor)):
        for hand, sam, concepts in [
            ("hand_yolov8n.pt", args.detectors / "sam_b.pt", ["hands"]),
            ("hand_yolov8n.pt", args.detectors / "sam_b.pt", ["face", "eyes", "hands"]),
            ("hand_yolov8s.pt", args.detectors / "sam_b.pt", ["hands"]),
            ("hand_yolov8n.pt", args.sam_pth, ["hands"]),
            ("hand_yolov8s.pt", args.sam_pth, ["hands"]),
        ]:
            name = f"{Path(hand).stem}-{sam.suffix[1:]}-{'-'.join(concepts)}"
            start = time.monotonic()
            offsets = len(detections), len(masks), len(images)
            with tempfile.TemporaryDirectory(prefix="anima-hands-native-") as temporary:
                paths = AppPaths(Path(temporary))
                root = paths.model_root / "detectors"
                root.mkdir(parents=True)
                for asset in (args.hand_dir / hand, sam, args.detectors / "face_yolov8n.pt", args.detectors / "full_eyes_detect_v1.pt"):
                    (root / asset.name).symlink_to(asset.resolve())
                settings = validate_settings({"concepts": concepts})
                regions = Detector(paths, settings).detect(source, lambda: False)
            hands = [r for r in regions if r.concept == "hands"]
            assert hands, f"No hand detected at unchanged threshold .5: {name}"
            assert all(r.mask.size == source.size and r.mask.getbbox() for r in regions)
            assert "eyes" not in {r.concept for r in regions}
            if "face" in concepts:
                assert {r.concept for r in regions} == {"face", "hands"}
                assert all(d["boxes"][0] for d in detections[offsets[0]:]), "Face/eye detections must be present to prove grouping"
            preview = source.copy()
            draw = ImageDraw.Draw(preview)
            case_output = output / name
            case_output.mkdir(exist_ok=True)
            for index, region in enumerate(regions):
                region.mask.save(case_output / f"mask-{index + 1}-{region.concept}.png")
                draw.rectangle(region.box, outline="cyan" if region.concept == "hands" else "lime", width=3)
            preview.save(case_output / "preview.png")
            entry = {"case": name, "seconds": time.monotonic() - start,
                     "regions": [{"concept": r.concept, "bbox": list(r.box), "mask_pixels": int(np.count_nonzero(np.array(r.mask)))} for r in regions],
                     "detections": detections[offsets[0]:], "segmentation": masks[offsets[1]:], "images": images[offsets[2]:]}
            cases.append(entry)
            print(json.dumps(entry), flush=True)
    assert {str(p.resolve()): digest(p) for p in assets} == before
    report = {"status": "passed", "evidence": "real offline CPU YOLO hands + SAM .pt/.pth; existing preview derivative, one image",
              "cases": cases, "sha256": before, "live_nai_requests": 0, "model_downloads": 0,
              "versions": {n: version(n) for n in ("ultralytics", "torch", "segment-anything")}}
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "passed", "cases": len(cases)}), flush=True)


if __name__ == "__main__":
    main()

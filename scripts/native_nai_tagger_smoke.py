"""Offline CPU inference with pre-existing pinned models and supplied face boxes.

No detector, NovelAI call, model download, or runtime installation is performed.
The fixture is the original RS NAI workflow screenshot, not a new generation.
"""
import argparse
import gc
import hashlib
import importlib.metadata
import json
import os
import time
from pathlib import Path
from unittest.mock import patch


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/nai-update-20261011/tagger/native"))
    args = parser.parse_args()
    os.environ.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", HF_HUB_DISABLE_IMPLICIT_TOKEN="1")
    import torch
    import httpx
    import requests
    from PIL import Image, ImageDraw
    from anima_app.providers.novelai import detailer
    from anima_app.providers.novelai.requests import request_from_payload
    from anima_app.providers.novelai.wd_tagger import MODELS, WDTagger, model_files

    torch.set_num_threads(2)
    torch.set_num_interop_threads(2)
    blocked = []

    def forbidden(*a, **k):
        blocked.append("HTTP attempted")
        raise AssertionError("Offline smoke forbids network")

    image_hash = sha256(args.image)
    image = Image.open(args.image).convert("RGB")
    # Same face fixtures as the original node's tests/smoke_wd_tagger.py.
    regions = []
    for box in ((3580, 405, 3750, 560), (3650, 695, 3860, 860)):
        mask = Image.new("L", image.size)
        ImageDraw.Draw(mask).rectangle(box, fill=255)
        regions.append(detailer.Region(box, mask))
    result = {"scope": "CPU tagger inference and app matching; supplied boxes, no live detector/NAI/download/GPU",
              "image": str(args.image), "image_sha256": image_hash, "models": [],
              "runtime": {name: importlib.metadata.version(name) for name in ("torch", "timm", "huggingface_hub", "transformers")}}
    args.output_dir.mkdir(parents=True, exist_ok=True)
    with patch.object(requests.sessions.Session, "request", forbidden), patch.object(httpx.Client, "send", forbidden):
        for name, (repo, revision) in MODELS.items():
            start = time.monotonic()
            snapshot = args.cache_dir / ("models--" + repo.replace("/", "--")) / "snapshots" / revision
            hashes = {filename: sha256(snapshot / filename) for filename in model_files(name)}
            events = []
            tagger = WDTagger(args.cache_dir, "cpu", 1, name)
            tagger.progress = events.append
            tagger.prepare()
            request = request_from_payload({"provider": "novelai", "prompt": "eye detail", "negative_prompt": "bad quality",
                "nai_model": "nai-diffusion-5-full", "nai_characters": [
                    {"prompt": "akiyama yukari, girls und panzer, brown hair, brown eyes, short hair, messy hair"},
                    {"prompt": "nishizumi miho, girls und panzer, brown hair, brown eyes, short hair"},
                ], "nai_detailer": {"enabled": True, "matching": "wd14", "preview_only": True, "wd_model": name}})
            _, _, _, report = detailer.plan(image, regions, request, tagger)
            assert [r["character"] for r in report] == [2, 1], report
            assert next(tagger._model.parameters()).device.type == "cpu"
            assert hashes == {filename: sha256(snapshot / filename) for filename in model_files(name)}
            result["models"].append({"name": name, "repo": repo, "revision": revision, "files_sha256": hashes,
                "regions": report, "events": events, "seconds": round(time.monotonic() - start, 3), "status": "passed"})
            print(json.dumps({"model": name, "characters": [r["character"] for r in report], "seconds": result["models"][-1]["seconds"]}), flush=True)
            (args.output_dir / "report.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
            del tagger
            gc.collect()
    assert image_hash == sha256(args.image)
    assert not blocked
    result.update(status="passed", external_http_attempts=blocked, nai_requests=0)
    (args.output_dir / "report.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()

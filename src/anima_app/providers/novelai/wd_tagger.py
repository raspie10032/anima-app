# SPDX-License-Identifier: GPL-3.0-only
"""Optional native PyTorch WD-v3 inference. No ONNX runtime or generated prompts."""

import csv
import json
import threading
from pathlib import Path

from anima_app.providers.novelai.client import _check_cancelled


def check_interrupted():
    _check_cancelled(getattr(_cancellation, "callback", lambda: False))


_cancellation = threading.local()

MODEL_REPO = "SmilingWolf/wd-vit-tagger-v3"
MODEL_REVISION = "7f6b584d0bd3f55c4531f14ba3d4761b2bccdc0f"


class WDTagger:
    def __init__(self, cache_dir, device="auto", batch_size=4):
        self.cache_dir = str(cache_dir)
        self.device = device
        self.batch_size = batch_size
        self.cancelled = lambda: False
        self._model = None
        self._lock = threading.Lock()

    def _load(self):
        _cancellation.callback = self.cancelled
        if self._model is not None:
            return
        try:
            import timm
            from huggingface_hub import hf_hub_download
            from safetensors.torch import load_file
            from timm.data import create_transform, resolve_data_config
        except ImportError as exc:
            raise RuntimeError(
                "WD matching requires the anima-app[wd-matching] optional dependencies."
            ) from exc
        paths = {}
        for name in ("config.json", "selected_tags.csv", "model.safetensors"):
            check_interrupted()
            paths[name] = hf_hub_download(
                MODEL_REPO, name, revision=MODEL_REVISION, cache_dir=self.cache_dir, local_files_only=True
            )
        config = json.loads(Path(paths["config.json"]).read_text())
        model = timm.create_model(
            config["architecture"],
            pretrained=False,
            num_classes=config["num_classes"],
            **config.get("model_args", {}),
        )
        model.load_state_dict(load_file(paths["model.safetensors"]), strict=True)
        transform = create_transform(
            **resolve_data_config(config["pretrained_cfg"], model=model),
            is_training=False,
        )
        with open(paths["selected_tags.csv"], encoding="utf-8", newline="") as handle:
            labels = list(csv.DictReader(handle))
        if len(labels) != config["num_classes"]:
            raise ValueError("WD model and tag vocabulary have different lengths.")
        self._labels = labels
        self._transform = transform
        self._model = model.eval()

    def score(self, images):
        import torch
        from PIL import Image

        if not images:
            return []
        with self._lock:
            _cancellation.callback = self.cancelled
            self._load()
            check_interrupted()
            if self.device == "auto":
                device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
            else:
                device = torch.device("cpu")
            results = []
            try:
                self._model.to(device)
                for start in range(0, len(images), self.batch_size):
                    check_interrupted()
                    inputs = []
                    for image in images[start : start + self.batch_size]:
                        rgba = image.convert("RGBA")
                        rgb = Image.new("RGBA", rgba.size, "white")
                        rgb.alpha_composite(rgba)
                        rgb = rgb.convert("RGB")
                        side = max(rgb.size)
                        square = Image.new("RGB", (side, side), "white")
                        square.paste(
                            rgb, ((side - rgb.width) // 2, (side - rgb.height) // 2)
                        )
                        inputs.append(self._transform(square))
                    batch = torch.stack(inputs)[:, [2, 1, 0]].to(device)
                    with torch.inference_mode():
                        output = self._model(batch).sigmoid().cpu()
                    del batch
                    for row in output.tolist():
                        results.append(
                            {
                                label["name"]: value
                                for label, value in zip(self._labels, row)
                                if label["category"] in {"0", "4"}
                            }
                        )
                return results
            finally:
                # Avoid permanently occupying VRAM alongside SAM/generation models.
                self._model.to("cpu")

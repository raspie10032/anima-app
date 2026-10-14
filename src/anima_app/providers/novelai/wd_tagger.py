# SPDX-License-Identifier: GPL-3.0-only
"""Optional local WD/PixAI inference. No ONNX runtime or generated prompts."""

import csv
import hashlib
import inspect
import json
import logging
import importlib.metadata
import threading
from pathlib import Path

from anima_app.providers.novelai.client import _check_cancelled
from anima_app.providers.novelai.errors import NovelAIError, explain, diagnosed
from anima_app.providers.novelai.tagger_progress import TaggerProgress


def user_error(code, _type, message):
    return NovelAIError(code.lower(), message, 400)


def model_files(model_name):
    return ("config.json", "preprocessor_config.json", "tagger_pipeline.py", "model.safetensors") if model_name == PIXAI_MODEL else (
        "config.json", "selected_tags.csv", "model.safetensors"
    )


MODEL_REPO = "SmilingWolf/wd-vit-tagger-v3"
MODEL_REVISION = "7f6b584d0bd3f55c4531f14ba3d4761b2bccdc0f"
DEFAULT_MODEL = "WD ViT v3"
PIXAI_MODEL = "PixAI Tagger v1.0"
MODELS = {
    DEFAULT_MODEL: (MODEL_REPO, MODEL_REVISION),
    "WD EVA02 Large v3": (
        "SmilingWolf/wd-eva02-large-tagger-v3",
        "b25b82a03f7282e41aa2f257a52c7583b710bd1c",
    ),
    PIXAI_MODEL: (
        "pixai-labs/pixai-tagger-v1.0",
        "9fe10addf9326e292da8a85a98ea74cd91b41771",
    ),
}
PIXAI_CODE_SHA256 = "3431279fdfff234f62664999fc1fe6bb20f1e8756f7435d0e165ebd4456f7fcd"


def check_dependencies(model_name=DEFAULT_MODEL):
    """Import only the selected backend, including its callable runtime."""
    if not isinstance(model_name, str) or model_name not in MODELS:
        raise user_error("TAGGER_SETTINGS", ValueError, "Unknown tagger model.")
    try:
        import torch
        import timm
        from huggingface_hub import hf_hub_download
        from safetensors.torch import load_file
        from timm.data import create_transform, resolve_data_config
        if "tqdm_class" not in inspect.signature(hf_hub_download).parameters:
            raise RuntimeError("Hub byte progress unavailable")
        if not all(callable(x) for x in (torch.inference_mode, timm.create_model, load_file, create_transform, resolve_data_config)):
            raise RuntimeError("Incomplete tagger runtime")
        if model_name == PIXAI_MODEL:
            from transformers import AutoImageProcessor, AutoModel
            if int(importlib.metadata.version("transformers").split(".")[0]) != 5:
                raise RuntimeError("PixAI requires Transformers 5")
            if not all(callable(x.from_pretrained) for x in (AutoImageProcessor, AutoModel)):
                raise RuntimeError("Incomplete PixAI runtime")
    except Exception:
        extra = "pixai-matching" if model_name == PIXAI_MODEL else "wd-matching"
        raise NovelAIError(
            "tagger_dependency",
            f"{model_name}: install anima-app[{extra}] in the app Python environment "
            "(from the source folder: python -m pip install '.[" + extra + "]'). "
            "Check compatible torch/torchvision; Hub >=1.1,<2; PixAI requires Transformers >=5,<6.",
            400,
        ) from None
    return timm, hf_hub_download, load_file, create_transform, resolve_data_config


class WDTagger:
    def __init__(self, cache_dir, device="auto", batch_size=4, model_name=DEFAULT_MODEL):
        if not isinstance(device, str) or device not in {"auto", "cpu"} or type(batch_size) is not int or not 1 <= batch_size <= 16:
            raise user_error("TAGGER_SETTINGS", ValueError, "Tagger requires device auto/cpu and batch size 1–16.")
        self.cancelled = lambda: False
        self.progress = None
        if not isinstance(model_name, str) or model_name not in MODELS:
            raise user_error("TAGGER_SETTINGS", ValueError, f"Unknown tagger model. Choose from {list(MODELS)}.")
        self.model_name = model_name
        self.cache_dir = str(cache_dir)
        self.device = device
        self.batch_size = batch_size
        self._model = None
        self._lock = threading.Lock()

    @diagnosed("tagger_prepare", "tagger_model")
    def prepare(self, *, allow_download=False, progress=None):
        """Explicit setup may download; generation uses only the pinned local cache."""
        with self._lock:
            reporter = progress or TaggerProgress(self.progress, self.cancelled)
            try:
                self._load(reporter, allow_download=allow_download)
            except NovelAIError:
                self._model = None
                reporter.report("Model preparation failed or cancelled.", force=True, failed=True)
                raise
            except Exception as exc:
                self._model = None
                reporter.report("Model preparation failed.", force=True, failed=True)
                raise explain(exc, stage="tagger_prepare", fallback="tagger_model",
                              message=f"{self.model_name}: local model loading failed. Check cache and runtime.") from None
        return self

    def _load(self, progress=None, *, allow_download=False):
        progress = progress or TaggerProgress(self.progress, self.cancelled)
        _check_cancelled(self.cancelled)
        if self._model is not None:
            progress.report(f"Ready: {self.model_name} (already loaded)", 1, force=True)
            return
        progress.report(f"Checking dependencies: {self.model_name}", force=True)
        timm, hf_hub_download, load_file, create_transform, resolve_data_config = check_dependencies(self.model_name)
        paths = {}
        repo, revision = MODELS[self.model_name]
        filenames = model_files(self.model_name)
        logging.info("[RS NAI Tagger] %s: checking cache; downloading missing files.", self.model_name)
        for name in filenames:
            _check_cancelled(self.cancelled)
            progress.report(f"Checking cache: {name}", force=True)
            logging.info("[RS NAI Tagger] %s: resolving %s", self.model_name, name)
            try:
                paths[name] = hf_hub_download(
                    repo, name, revision=revision, cache_dir=self.cache_dir,
                    tqdm_class=progress.download_bar(name), local_files_only=not allow_download,
                    token=False,
                )
            except Exception as exc:
                if isinstance(exc, NovelAIError):
                    raise
                _check_cancelled(self.cancelled)
                code = "tagger_download" if allow_download else "tagger_cache_missing"
                raise explain(exc, stage="tagger_download", fallback=code,
                              message=f"{self.model_name}: could not resolve {name}. Use Prepare tagger.") from None
            progress.report(f"File ready: {name}", 1, force=True)
        logging.info("[RS NAI Tagger] %s: loading weights on CPU.", self.model_name)
        progress.report(f"Loading {self.model_name} on CPU…", force=True)
        config = json.loads(Path(paths["config.json"]).read_text(encoding="utf-8"))
        if self.model_name == PIXAI_MODEL:
            self._load_pixai(paths, config)
            _check_cancelled(self.cancelled)
            progress.report(f"Ready: {self.model_name}", 1, force=True)
            return
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
            raise user_error("TAGGER_MODEL", ValueError, "WD model and tag vocabulary have different lengths.")
        _check_cancelled(self.cancelled)
        self._labels = labels
        self._transform = transform
        self._model = model.eval()
        progress.report(f"Ready: {self.model_name}", 1, force=True)

    def _load_pixai(self, paths, config):
        from transformers import AutoImageProcessor, AutoModel

        # The official architecture is custom code; only execute the reviewed revision.
        if hashlib.sha256(Path(paths["tagger_pipeline.py"]).read_bytes()).hexdigest() != PIXAI_CODE_SHA256:
            raise user_error("TAGGER_MODEL", ValueError, "PixAI model code checksum mismatch. Remove the cached tagger_pipeline.py and retry.")
        if sum(count for _, count in config["tags_split"]) != config["num_classes"]:
            raise user_error("TAGGER_MODEL", ValueError, "PixAI tag category lengths do not match the model.")
        labels = []
        for category, count in config["tags_split"]:
            labels.extend(
                {"name": name, "category": {"general": "0", "character": "4"}.get(category, "ignored")}
                for name in config["tags"][len(labels):len(labels) + count]
            )
        if len(labels) != config["num_classes"] or len(labels) != len(config["tags"]):
            raise user_error("TAGGER_MODEL", ValueError, "PixAI model and tag vocabulary have different lengths.")
        processor_config = json.loads(Path(paths["preprocessor_config.json"]).read_text(encoding="utf-8"))
        if config.get("auto_map") != {"AutoConfig": "tagger_pipeline.ViTDetClsConfig", "AutoModel": "tagger_pipeline.ViTDetCls"} or processor_config.get("auto_map") != {"AutoImageProcessor": "tagger_pipeline.RescalePadProcessor"}:
            raise user_error("TAGGER_MODEL", ValueError, "PixAI architecture mapping does not match the pinned code.")
        snapshot = str(Path(paths["config.json"]).parent)
        processor = AutoImageProcessor.from_pretrained(snapshot, trust_remote_code=True, local_files_only=True)
        model = AutoModel.from_pretrained(snapshot, trust_remote_code=True, local_files_only=True)
        self._labels = labels
        self._processor = processor
        self._model = model.eval()

    @diagnosed("tagger_inference", "tagger_inference")
    def score(self, images):
        import torch

        if not images:
            return []
        with self._lock:
            self._load()
            _check_cancelled(self.cancelled)
            device = torch.device("cuda" if self.device == "auto" and torch.cuda.is_available() else "cpu")
            results = []
            try:
                logging.info("[RS NAI Tagger] %s: scoring %d crops on %s (batch size %d).", self.model_name, len(images), device, self.batch_size)
                self._model.to(device)
                for start in range(0, len(images), self.batch_size):
                    _check_cancelled(self.cancelled)
                    crops = images[start : start + self.batch_size]
                    if self.model_name == PIXAI_MODEL:
                        # PixAI uses RGB, resize then black padding; WD uses BGR and white square padding.
                        batch = self._processor(crops, return_tensors="pt")["pixel_values"].to(device)
                    else:
                        batch = torch.stack([self._prepare_wd(image) for image in crops])[:, [2, 1, 0]].to(device)
                    with torch.inference_mode():
                        output = self._model(batch).float().sigmoid().cpu()
                    del batch
                    if output.ndim != 2 or output.shape != (len(crops), len(self._labels)):
                        raise user_error("TAGGER_MODEL", ValueError, f"{self.model_name} returned scores inconsistent with its tag vocabulary.")
                    _check_cancelled(self.cancelled)
                    if not torch.isfinite(output).all():
                        raise user_error("TAGGER_MODEL", ValueError, "Tagger returned nonfinite scores.")
                    for row in output.tolist():
                        results.append(
                            {
                                label["name"]: value
                                for label, value in zip(self._labels, row)
                                if label["category"] in {"0", "4"}
                            }
                        )
                return results
            except NovelAIError:
                raise
            except Exception as exc:
                raise explain(exc, stage="tagger_inference", fallback="tagger_inference",
                              message=f"{self.model_name}: local inference failed. Try CPU or a smaller batch.") from None
            finally:
                # Avoid permanently occupying VRAM alongside SAM/generation models.
                self._model.to("cpu")

    def _prepare_wd(self, image):
        from PIL import Image

        rgba = image.convert("RGBA")
        rgb = Image.new("RGBA", rgba.size, "white")
        rgb.alpha_composite(rgba)
        rgb = rgb.convert("RGB")
        side = max(rgb.size)
        square = Image.new("RGB", (side, side), "white")
        square.paste(
            rgb, ((side - rgb.width) // 2, (side - rgb.height) // 2)
        )
        return self._transform(square)

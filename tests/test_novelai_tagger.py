import hashlib
import json
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image

from anima_app import server
from anima_app.config import AppPaths
from anima_app.providers import novelai
from anima_app.providers.novelai import detailer, wd_tagger as wd
from anima_app.providers.novelai.errors import NovelAIError
from anima_app.providers.novelai.requests import request_from_payload
from anima_app.providers.novelai.tagger_progress import TaggerProgress
from anima_app.providers.novelai.tagger_setup import TaggerSetup
from test_novelai_detailer import assets, regions  # noqa: F401
from test_novelai_integration import http_json, make_queue, running_http_server, wait_terminal


@pytest.mark.parametrize("name", list(wd.MODELS))
def test_settings_round_trip_and_old_default(name):
    request = request_from_payload({"provider": "novelai", "prompt": "scene", "nai_detailer": {"wd_model": name}})
    assert request.to_payload()["nai_detailer"]["wd_model"] == name
    assert request_from_payload({"provider": "novelai", "prompt": "old"}).detailer["wd_model"] == wd.DEFAULT_MODEL


@pytest.mark.parametrize("bad", ["unknown", "", None, [], 42])
def test_invalid_model_rejected(bad):
    with pytest.raises(ValueError):
        detailer.validate_settings({"wd_model": bad})
    with pytest.raises(NovelAIError, match="Unknown tagger"):
        wd.WDTagger("unused", model_name=bad)


def test_http_xet_progress_is_per_file_and_cancellable():
    events, other_events = [], []
    stop = threading.Event()
    reporter = TaggerProgress(events.append, stop.is_set)
    other = TaggerProgress(other_events.append)
    bar = reporter.download_bar("model.safetensors")(total=100, initial=20, name="hf")
    bar.update(30)
    bar.update_transfer(60)
    bar._report(force=True)
    assert events[-1]["received_bytes"] == 80
    assert events[-1]["fraction"] == .8
    bar.update_transfer(20)
    bar._report(force=True)
    assert events[-1]["fraction"] == .999  # download is not verified readiness
    with other.download_bar("config.json")(total=10) as other_bar:
        other_bar.update(10)
        other_bar._report(force=True)
    assert other_events[-1]["filename"] == "config.json"
    assert events[-1]["filename"] == "model.safetensors"
    stop.set()
    with pytest.raises(NovelAIError) as exc:
        bar.update()
    assert exc.value.status == 499
    reporter.report("Cancelled", failed=True, force=True)
    assert events[-1]["failed"]
    bar.close()


@pytest.mark.parametrize("name", list(wd.MODELS))
@pytest.mark.parametrize("download", [False, True])
def test_loader_selected_repo_revision_and_local_only(tmp_path, monkeypatch, name, download):
    files = {
        "config.json": json.dumps({"architecture": "test", "num_classes": 2, "pretrained_cfg": {}}),
        "selected_tags.csv": "name,category\nred_hair,0\ncharacter,4\n",
    }
    for filename, contents in files.items():
        (tmp_path / filename).write_text(contents)
    calls = []

    def hub(repo, filename, **kwargs):
        calls.append((repo, filename, kwargs))
        return str(tmp_path / filename)

    model = SimpleNamespace(load_state_dict=lambda *a, **k: None, eval=lambda: model)
    monkeypatch.setattr(wd, "check_dependencies", lambda name: (
        SimpleNamespace(create_model=lambda *a, **k: model), hub, lambda _: {},
        lambda **k: "transform", lambda *a, **k: {},
    ))
    monkeypatch.setattr(wd.WDTagger, "_load_pixai", lambda self, *a: setattr(self, "_model", model))
    tagger = wd.WDTagger(tmp_path, model_name=name)
    events = []
    tagger.prepare(allow_download=download, progress=TaggerProgress(events.append))
    assert len(calls) == len(wd.model_files(name))
    for repo, filename, kwargs in calls:
        assert (repo, kwargs["revision"]) == wd.MODELS[name]
        assert kwargs["local_files_only"] is not download and kwargs["token"] is False
        assert filename in wd.model_files(name) and callable(kwargs["tqdm_class"])
    assert events[-1]["text"].startswith("Ready:")
    tagger.prepare()
    assert len(calls) == len(wd.model_files(name))  # existing model reused


@pytest.mark.parametrize("download", [False, True])
def test_cache_download_errors_are_sanitized(tmp_path, monkeypatch, download):
    def hub(*a, **k):
        raise RuntimeError("private-token-do-not-print")
    monkeypatch.setattr(wd, "check_dependencies", lambda *_: (None, hub, None, None, None))
    events = []
    with pytest.raises(NovelAIError) as exc:
        wd.WDTagger(tmp_path).prepare(allow_download=download, progress=TaggerProgress(events.append))
    assert exc.value.code == ("tagger_download" if download else "tagger_cache_missing")
    assert "config.json" in str(exc.value) and "private-token" not in str(exc.value)
    assert events[-1]["failed"] and not any(e["text"].startswith("Ready") for e in events)


def test_dependency_failure_names_selected_extra_and_never_downloads(monkeypatch):
    monkeypatch.setitem(sys.modules, "timm", None)
    for name, extra in ((wd.DEFAULT_MODEL, "wd-matching"), (wd.PIXAI_MODEL, "pixai-matching")):
        with pytest.raises(NovelAIError) as exc:
            wd.check_dependencies(name)
        assert exc.value.code == "tagger_dependency" and f".[{extra}]" in str(exc.value)


@pytest.mark.parametrize("failure", ["hash", "categories", "tags", "mapping"])
def test_pixai_rejects_untrusted_or_inconsistent_assets_before_execution(tmp_path, monkeypatch, failure):
    monkeypatch.setitem(sys.modules, "transformers", SimpleNamespace(
        AutoImageProcessor=SimpleNamespace(from_pretrained=lambda *a, **k: pytest.fail("code executed")),
        AutoModel=SimpleNamespace(from_pretrained=lambda *a, **k: pytest.fail("code executed"))))
    code = tmp_path / "tagger_pipeline.py"
    code.write_text("fixture")
    monkeypatch.setattr(wd, "PIXAI_CODE_SHA256", hashlib.sha256(b"fixture").hexdigest() if failure != "hash" else "invalid")
    config = {"num_classes": 2, "tags_split": [["general", 1], ["character", 1]], "tags": ["tag", "name"]}
    if failure == "categories":
        config["num_classes"] = 3
    elif failure == "tags":
        config["tags"] = ["tag"]
    preprocessor = tmp_path / "preprocessor_config.json"
    preprocessor.write_text('{"auto_map": {"AutoImageProcessor": "evil.Module"}}')
    with pytest.raises(NovelAIError) as exc:
        wd.WDTagger(tmp_path, model_name=wd.PIXAI_MODEL)._load_pixai(
            {"tagger_pipeline.py": str(code), "preprocessor_config.json": str(preprocessor)}, config)
    assert exc.value.code == "tagger_model"


@pytest.mark.parametrize("name", list(wd.MODELS))
def test_color_alpha_batching_dense_scores_and_cpu_release(tmp_path, name):
    import torch
    seen, moves = [], []

    class Model:
        def to(self, device):
            moves.append(str(device))
            return self

        def __call__(self, batch):
            seen.append(batch.clone())
            return torch.tensor([[-10., 1., 2., 3.]] * len(batch))

    tagger = wd.WDTagger(tmp_path, device="cpu", batch_size=2, model_name=name)
    tagger._model = Model()
    tagger._labels = [{"name": "tiny_general", "category": "0"}, {"name": "character", "category": "4"},
                      {"name": "rating", "category": "9"}, {"name": "artist", "category": "ignored"}]
    tagger._transform = lambda im: torch.from_numpy(np.array(im)).permute(2, 0, 1).float()
    supplied = []

    def processor(images, **kwargs):
        supplied.extend(images)
        assert kwargs == {"return_tensors": "pt"}
        return {"pixel_values": torch.stack([tagger._transform(im.convert("RGB")) for im in images])}

    tagger._processor = processor
    image = Image.new("RGBA", (2, 4), (255, 0, 0, 255))
    image.putpixel((0, 0), (0, 0, 255, 0))
    scores = tagger.score([image] * 3)
    assert [len(batch) for batch in seen] == [2, 1] and moves[-1] == "cpu"
    assert set(scores[0]) == {"tiny_general", "character"} and 0 < scores[0]["tiny_general"] < .001
    if name == wd.PIXAI_MODEL:
        assert supplied == [image] * 3  # official processor owns alpha/resize/black padding; no BGR swap
        assert seen[0][0, :, 1, 0].tolist() == [255, 0, 0]
    else:
        assert seen[0].shape == (2, 3, 4, 4)
        assert seen[0][0, :, 1, 1].tolist() == [0, 0, 255]  # BGR red
        assert seen[0][0, :, 0, 1].tolist() == [255, 255, 255]  # alpha white
        assert seen[0][0, :, 1, 0].tolist() == [255, 255, 255]  # square white padding


@pytest.mark.parametrize("failure", ["shape", "nonfinite", "runtime", "cancel"])
def test_score_failure_and_cancel_release_cpu(tmp_path, failure):
    import torch
    stop, calls, moves = threading.Event(), [], []

    class Model:
        def to(self, device):
            moves.append(str(device))
            return self

        def __call__(self, batch):
            calls.append(1)
            if failure == "runtime":
                raise RuntimeError("private-token")
            if failure == "cancel":
                stop.set()
            return torch.tensor([[float("nan") if failure == "nonfinite" else 1.] * (2 if failure == "shape" else 1)])

    tagger = wd.WDTagger(tmp_path, "cpu", 1)
    tagger._model, tagger.cancelled = Model(), stop.is_set
    tagger._labels = [{"name": "tag", "category": "0"}]
    tagger._transform = lambda _: torch.zeros(3, 2, 2)
    with pytest.raises(NovelAIError) as exc:
        tagger.score([Image.new("RGB", (2, 2))] * 2)
    assert len(calls) == 1 and moves[-1] == "cpu" and "private-token" not in str(exc.value)
    assert exc.value.code == {"shape": "tagger_model", "nonfinite": "tagger_model", "runtime": "tagger_inference", "cancel": "generation_cancelled"}[failure]


@pytest.mark.parametrize("name", list(wd.MODELS))
def test_real_queue_preview_preserves_selected_model_manifest_png(tmp_path, monkeypatch, assets, name):  # noqa: F811
    instances = []

    def prepare(self, **kwargs):
        instances.append(self)
        return self

    def score(self, images):
        assert self is instances[0]  # preflight model reused, not reloaded
        return [{"red_hair": .9} for _ in images]

    monkeypatch.setattr(wd.WDTagger, "prepare", prepare)
    monkeypatch.setattr(wd.WDTagger, "score", score)
    monkeypatch.setattr(detailer.Detector, "detect", lambda self, image, cancelled: regions(image))
    monkeypatch.setattr(novelai.service, "get_token", lambda: pytest.fail("token read"))
    queue = make_queue(tmp_path)
    try:
        status, batch = queue.enqueue({"request": {**assets, "nai_characters": [{"prompt": "red hair"}],
                        "nai_detailer": {"enabled": True, "preview_only": True, "matching": "wd14", "wd_model": name}}})
        assert status == 202
        job = wait_terminal(queue, batch["jobs"][0]["id"])
        assert job["status"] == "completed", job
        manifest = json.loads(Path(job["result"]["manifest_path"]).read_text())
        assert len(instances) == 1 and instances[0].model_name == name
        assert manifest["novelai"]["requested"]["nai_detailer"]["wd_model"] == name
        assert job["request"]["nai_detailer"]["wd_model"] == name
        tagger_record = manifest["novelai"]["detailer"][0]["tagger"]
        assert (tagger_record["repo"], tagger_record["revision"]) == wd.MODELS[name]
        with Image.open(manifest["output_path"]) as image:
            metadata = json.loads(image.info["Comment"])
            assert metadata["anima_app_detailer"]["wd_model"] == name
    finally:
        queue.close()


@pytest.mark.parametrize("name", list(wd.MODELS))
def test_missing_selected_model_blocks_before_base_request(tmp_path, monkeypatch, assets, name):  # noqa: F811
    def prepare(self, **kwargs):
        raise NovelAIError("tagger_cache_missing", f"Missing {self.model_name}", 400)
    monkeypatch.setattr(wd.WDTagger, "prepare", prepare)
    monkeypatch.setattr(novelai.service, "get_token", lambda: pytest.fail("token read"))
    payload = {**assets, "operation": "generate", "input_image": "", "nai_characters": [{"prompt": "red hair"}],
               "nai_detailer": {"enabled": True, "matching": "wd14", "wd_model": name}}
    status, result = server.handle_generate(payload, paths=AppPaths(tmp_path))
    assert status == 400 and result["error_code"] == "tagger_cache_missing", result


def test_setup_busy_cancel_failure_and_recovery(tmp_path, monkeypatch):
    entered, release = threading.Event(), threading.Event()

    def prepare(self, **kwargs):
        assert kwargs["allow_download"]
        kwargs["progress"].report("Loading", force=True)
        entered.set()
        assert release.wait(5)
        kwargs["progress"].report("Validated", force=True)
    monkeypatch.setattr(wd.WDTagger, "prepare", prepare)
    lock = threading.Lock()
    setup = TaggerSetup(tmp_path, lock)
    try:
        job = setup.start({"model_name": wd.PIXAI_MODEL})["job"]
        assert entered.wait(2)
        with pytest.raises(NovelAIError) as exc:
            setup.start({})
        assert exc.value.status == 409
        with pytest.raises(NovelAIError) as exc:
            setup.cancel("stale-id")
        assert exc.value.status == 404 and not setup.snapshot()["job"]["cancel_requested"]
        setup.cancel(job["id"])
        release.set()
        setup._thread.join(3)
        assert setup.snapshot()["job"]["status"] == "cancelled" and not lock.locked()
        setup.start({"model_name": wd.DEFAULT_MODEL})
        setup._thread.join(3)
        assert setup.snapshot()["job"]["status"] == "ready"
        def fail(*a, **k):
            raise RuntimeError("private-token")
        monkeypatch.setattr(wd.WDTagger, "prepare", fail)
        setup.start({})
        setup._thread.join(3)
        assert setup.snapshot()["job"]["status"] == "failed"
        assert "private-token" not in json.dumps(setup.snapshot()) and not lock.locked()
    finally:
        release.set()
        setup.close()


def test_setup_http_contract_and_origin_guard(tmp_path, monkeypatch):
    monkeypatch.setattr(wd.WDTagger, "prepare", lambda self, **kwargs: self)
    with running_http_server(tmp_path) as port:
        status, data = http_json(port, "GET", "/api/nai/tagger")
        assert status == 200 and [m["name"] for m in data["models"]] == list(wd.MODELS) and data["job"] is None
        assert http_json(port, "POST", "/api/nai/tagger/prepare", {"model_name": wd.PIXAI_MODEL}, Origin="https://untrusted.example")[0] == 403
        assert http_json(port, "POST", "/api/nai/tagger/prepare", {"model_name": []})[0] == 400
        assert http_json(port, "POST", "/api/nai/tagger/prepare", {"url": "https://untrusted.example"})[0] == 400
        assert http_json(port, "POST", "/api/nai/tagger/prepare", {"model_name": wd.PIXAI_MODEL})[0] == 202
        assert http_json(port, "POST", "/api/nai/tagger/cancel", {"job_id": "not-found"})[0] == 404

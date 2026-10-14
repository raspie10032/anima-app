"""One cancellable local tagger preparation job per app server."""

import copy
import threading
import uuid

from anima_app.providers.novelai.client import _check_cancelled
from anima_app.providers.novelai.errors import NovelAIError, explain
from anima_app.providers.novelai.tagger_progress import TaggerProgress
from anima_app.providers.novelai.wd_tagger import DEFAULT_MODEL, MODELS, WDTagger, model_files


class TaggerSetup:
    def __init__(self, cache_dir, generation_lock):
        self.cache_dir = cache_dir
        self.generation_lock = generation_lock
        self._lock = threading.RLock()
        self._cancel = threading.Event()
        self._thread = None
        self._job = None

    def snapshot(self):
        with self._lock:
            return {"models": [{"name": name, "repo": repo, "revision": revision,
                                "files": list(model_files(name))} for name, (repo, revision) in MODELS.items()],
                    "default": DEFAULT_MODEL, "job": copy.deepcopy(self._job)}

    def start(self, payload):
        if not isinstance(payload, dict) or payload.keys() - {"model_name", "device", "batch_size"}:
            raise NovelAIError("tagger_settings", "Unknown tagger preparation setting.", 400)
        tagger = WDTagger(self.cache_dir, payload.get("device", "auto"), payload.get("batch_size", 4),
                          payload.get("model_name", DEFAULT_MODEL))
        with self._lock:
            if not self.generation_lock.acquire(blocking=False):
                raise NovelAIError("tagger_busy", "Generation or model preparation is running. Wait for completion.", 409)
            self._cancel.clear()
            self._job = {"id": uuid.uuid4().hex, "model_name": tagger.model_name, "device": tagger.device,
                         "batch_size": tagger.batch_size, "status": "running", "text": "Preparing tagger…",
                         "fraction": 0, "cancel_requested": False, "error": None, "error_code": None}
            tagger.cancelled = self._cancel.is_set
            reporter = TaggerProgress(self._update, tagger.cancelled)
            self._thread = threading.Thread(target=self._run, args=(tagger, reporter), daemon=True)
            try:
                self._thread.start()
            except Exception:
                self._job.update(status="failed", error="Could not start tagger preparation.", error_code="tagger_model")
                self.generation_lock.release()
                raise NovelAIError("tagger_model", "Could not start tagger preparation.", 500) from None
            return self.snapshot()

    def _update(self, event):
        with self._lock:
            # Clear byte counts when the loader advances to another file/stage.
            for field in ("filename", "received_bytes", "total_bytes"):
                self._job.pop(field, None)
            self._job.update(event)

    def _run(self, tagger, reporter):
        try:
            tagger.prepare(allow_download=True, progress=reporter)
            with self._lock:
                _check_cancelled(tagger.cancelled)
                self._job.update(status="ready", text=f"Ready: {tagger.model_name}", fraction=1, failed=False)
        except Exception as exc:
            with self._lock:
                stopped = self._cancel.is_set() or isinstance(exc, NovelAIError) and exc.status == 499
                error = (NovelAIError("generation_cancelled", "태거 준비가 취소되었습니다.", 499, stage="tagger_prepare")
                         if stopped else explain(exc, stage="tagger_prepare", fallback="tagger_model"))
                self._job.update(status="cancelled" if stopped else "failed", fraction=0, failed=True,
                                 text="태거 준비가 취소되었습니다." if stopped else "태거 준비 실패",
                                 **error.payload())
        finally:
            # Release the CPU model after verifying load; generation owns its model instance.
            tagger._model = None
            self.generation_lock.release()

    def cancel(self, job_id):
        with self._lock:
            if not self._job or self._job["id"] != job_id:
                raise NovelAIError("tagger_job_not_found", "Tagger preparation job not found.", 404)
            if self._job["status"] == "running":
                self._cancel.set()
                self._job.update(cancel_requested=True, text="취소 중… 현재 다운로드/로딩 단계가 끝나면 멈춥니다.")
            return self.snapshot()

    def close(self):
        self._cancel.set()
        if self._thread:
            self._thread.join(timeout=2)

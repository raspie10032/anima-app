"""Optional adapter to an explicitly configured, external VRS-INT encoder.

One subprocess owns the model and releases it on completion/cancellation. The
app's generation lock must be held by the caller. No weights are downloaded.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time

import numpy as np

from anima_app.library_visual import read_pixels, unit


class VRSAdapter:
    def __init__(self):
        self.root = os.environ.get("ANIMA_LIBRARY_VRS_ROOT", "")
        self.encoder = os.environ.get("ANIMA_LIBRARY_VRS_ENCODER", "")
        self.python = os.environ.get("ANIMA_LIBRARY_VRS_PYTHON", "")

    @property
    def contract(self) -> str | None:
        if not all((self.root, self.encoder, self.python)):
            return None
        try:
            source = (Path(self.root) / "vrs_int" / "encoder.py").read_bytes()
            provenance = (Path(self.encoder) / "provenance.json").read_bytes()
            if not Path(self.python).is_file():
                return None
            preparation = Path(__file__).with_name('library_visual.py').read_bytes()
            worker = Path(__file__).read_bytes()
            return "vrs-int-gemma4-rgb-v1:" + hashlib.sha256(source + provenance + preparation + worker).hexdigest()
        except OSError:
            return None

    def encode(self, paths: list[Path], scratch: Path, cancelled=lambda: False) -> list[list[float]]:
        if not self.contract:
            raise ValueError("VRS 이미지 인코더가 준비되지 않았습니다. Library 안내의 로컬 설정을 확인해 주세요.")
        scratch.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="vrs-", dir=scratch) as temporary:
            directory = Path(temporary)
            # Never pass original metadata to VRS. Identical decoded RGB pixels
            # have the same query regardless of prompt/artist text in the file.
            for index, path in enumerate(paths):
                read_pixels(path).save(directory / f"{index}.png")
            config = {"root": self.root, "encoder": self.encoder, "count": len(paths)}
            (directory / "job.json").write_text(json.dumps(config), encoding="utf-8")
            env = {k: v for k, v in os.environ.items() if not any(s in k.upper() for s in ("TOKEN", "SECRET", "API_KEY"))}
            env.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1")
            for name in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS'):
                env.setdefault(name, '2')
            env['PYTHONPATH'] = str(Path(__file__).resolve().parents[1]) + os.pathsep + env.get('PYTHONPATH', '')
            process = subprocess.Popen([self.python, str(Path(__file__).resolve()), str(directory)],
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)
            deadline = time.monotonic() + 600
            try:
                while process.poll() is None:
                    if cancelled():
                        raise ValueError("VRS 색인을 취소했습니다.")
                    if time.monotonic() > deadline:
                        raise ValueError("VRS 처리 시간이 초과되었습니다.")
                    time.sleep(.1)
                if process.returncode:
                    raise ValueError("VRS 인코딩에 실패했습니다. 호환 환경·모델·CUDA 메모리를 확인해 주세요.")
                output = directory / "vectors.npy"
                if output.stat().st_size > max(1, len(paths)) * 65536:
                    raise ValueError("VRS 벡터 크기가 올바르지 않습니다.")
                vectors = np.load(output, allow_pickle=False)
                if vectors.ndim != 2 or vectors.shape[0] != len(paths):
                    raise ValueError("VRS 벡터 개수가 올바르지 않습니다.")
                return [unit(row).tolist() for row in vectors]
            finally:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()


def _worker(directory: Path):
    import sys
    config = json.loads((directory / "job.json").read_text(encoding="utf-8"))
    dependencies = Path(config['encoder']) / 'deps'
    if dependencies.is_dir():
        sys.path.insert(0, str(dependencies))
    sys.path.insert(0, config["root"])
    import torch
    torch.set_num_threads(2)
    from vrs_int.encoder import ImageEncoder
    encoder = ImageEncoder(config["encoder"])
    rows = []
    for index in range(0, config["count"], 4):
        paths = [directory / f"{i}.png" for i in range(index, min(index + 4, config["count"]))]
        rows.extend(encoder.encode_many(paths).detach().cpu().float().numpy())
    np.save(directory / "vectors.npy", np.stack(rows), allow_pickle=False)


if __name__ == "__main__":
    import sys
    _worker(Path(sys.argv[1]))

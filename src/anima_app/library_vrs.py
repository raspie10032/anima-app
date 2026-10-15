"""Bundled VRS worker. Pixel-only input, bounded scratch, isolated CUDA lifetime."""
from __future__ import annotations

from collections import deque
from contextlib import contextmanager
import json
from pathlib import Path
import subprocess
import shutil
import sys
import tempfile
import threading
import time

import numpy as np

from anima_app.library_visual import read_pixels, unit
from anima_app.embedded_vrs import EmbeddedVRS, child_environment, contract_for


class VRSIndexCancelled(Exception):
    """User cancellation, distinct from an encoder failure."""


class VRSAdapter:
    def __init__(self, model_root):
        self.runtime = EmbeddedVRS(model_root, threading.Lock())
        self.encoder = str(self.runtime.directory)
        self.python = sys.executable
        self._persistent = False
        self._worker_state = None

    @contextmanager
    def session(self):
        """Keep one CUDA worker while index batches are committed independently."""
        self._persistent = True
        try:
            yield
        finally:
            if self._worker_state:
                self._finish(self._worker_state)
            self._worker_state = None
            self._persistent = False

    def _spawn(self, directory):
        command = ['--session', self.encoder] if self._persistent else [str(directory)]
        process = subprocess.Popen([self.python, str(Path(__file__).resolve()), *command],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
            stdin=subprocess.PIPE if self._persistent else subprocess.DEVNULL,
            env=child_environment(self.encoder))
        tail = deque(maxlen=32)
        def collect():
            for chunk in iter(lambda: process.stderr.read(512), b''):
                tail.append(chunk)
        reader = threading.Thread(target=collect, daemon=True)
        reader.start()
        return process, tail, reader

    @staticmethod
    def _finish(state):
        process, _, reader = state
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        reader.join(timeout=2)
        process.stderr.close()
        if process.stdin:
            process.stdin.close()

    @property
    def contract(self) -> str | None:
        status = self.runtime.status()
        return contract_for(self.encoder) if status['ready'] else None

    def encode(self, paths: list[Path], scratch: Path, cancelled=lambda: False) -> list[list[float]]:
        if not self.contract:
            raise ValueError("VRS_NOT_READY: 연결 · 준비에서 이미지 검색을 준비해 주세요.")
        if not 1 <= len(paths) <= 8:
            raise ValueError('VRS_BATCH_SIZE: 한 번에 1~8장을 처리합니다.')
        scratch.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="vrs-", dir=scratch) as temporary:
            directory = Path(temporary)
            # Never pass original metadata to VRS. Identical decoded RGB pixels
            # have the same query regardless of prompt/artist text in the file.
            for index, path in enumerate(paths):
                if cancelled():
                    raise VRSIndexCancelled()
                pixels = read_pixels(path)
                if shutil.disk_usage(directory).free < pixels.width * pixels.height * 4 + 8 * 1024**2:
                    raise ValueError('DISK_SPACE: VRS 임시 공간이 부족합니다.')
                pixels.save(directory / f"{index}.png")
            config = {"encoder": self.encoder, "count": len(paths)}
            (directory / "job.json").write_text(json.dumps(config), encoding="utf-8")
            state = self._worker_state or self._spawn(directory)
            process, tail, reader = state
            if self._persistent:
                self._worker_state = state
            deadline = time.monotonic() + 600
            try:
                if self._persistent:
                    process.stdin.write((json.dumps(str(directory)) + '\n').encode('utf-8'))
                    process.stdin.flush()
                while process.poll() is None:
                    if cancelled():
                        raise VRSIndexCancelled()
                    if self._persistent and (directory / 'complete').exists():
                        break
                    if time.monotonic() > deadline:
                        raise ValueError("VRS_TIMEOUT: 처리 시간이 초과되었습니다.")
                    time.sleep(.1)
                if process.returncode:
                    reader.join(timeout=2)
                    message = b''.join(tail).decode('utf-8', errors='replace')
                    code = ('CUDA_OOM' if 'out of memory' in message.lower() else
                            'PROVENANCE_MISMATCH' if 'digest mismatch' in message else
                            'IMPORT_ERROR' if 'ImportError' in message or 'ModuleNotFoundError' in message else 'ENCODER_ERROR')
                    raise ValueError(f'{code}: VRS 인코더 오류. 연결 · 준비에서 진단을 확인해 주세요.')
                output = directory / "vectors.npy"
                if output.stat().st_size > max(1, len(paths)) * 65536:
                    raise ValueError("VRS 벡터 크기가 올바르지 않습니다.")
                vectors = np.load(output, allow_pickle=False)
                if vectors.ndim != 2 or vectors.shape != (len(paths), 768):
                    raise ValueError("VRS 벡터 개수가 올바르지 않습니다.")
                return [unit(row).tolist() for row in vectors]
            finally:
                if not self._persistent:
                    self._finish(state)
                diagnostics = scratch.parent / 'diagnostics'
                diagnostics.mkdir(exist_ok=True)
                log = b''.join(tail).decode('utf-8', errors='replace').replace(str(Path.home()), '<home>')
                (diagnostics / 'last-encoder.json').write_text(json.dumps({
                    'exit_code': process.returncode, 'stderr': log[-16384:]}, ensure_ascii=False), encoding='utf-8')


def _load_encoder(encoder_directory):
    dependencies = Path(encoder_directory) / 'deps'
    if dependencies.is_dir():
        sys.path.insert(0, str(dependencies))
    import torch
    torch.set_num_threads(2)
    from anima_app._vendor.vrs_int.encoder import ImageEncoder
    return ImageEncoder(encoder_directory)


def _worker(directory: Path, encoder=None):
    config = json.loads((directory / "job.json").read_text(encoding="utf-8"))
    encoder = encoder or _load_encoder(config['encoder'])
    rows = []
    for index in range(0, config["count"], 4):
        paths = [directory / f"{i}.png" for i in range(index, min(index + 4, config["count"]))]
        rows.extend(encoder.encode_many(paths).detach().cpu().float().numpy())
    np.save(directory / "vectors.npy", np.stack(rows), allow_pickle=False)
    (directory / 'complete').touch()


if __name__ == "__main__":
    if sys.argv[1] == '--session':
        encoder = _load_encoder(sys.argv[2])
        for line in sys.stdin:
            _worker(Path(json.loads(line)), encoder)
    else:
        _worker(Path(sys.argv[1]))

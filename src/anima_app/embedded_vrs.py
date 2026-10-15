"""App-owned vision model preparation and runtime fingerprint. No sibling paths."""
from __future__ import annotations

import hashlib
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time

from anima_app._vendor.vrs_int.import_snapshot import file_digest

VENDOR = Path(__file__).with_name('_vendor') / 'vrs_int'
MODEL = json.loads((VENDOR / 'model.json').read_text(encoding='utf-8'))
DEPENDENCIES = {'accelerate': '1.15.0', 'bitsandbytes': '0.50.2'}
_FINGERPRINTS = {}
_FINGERPRINT_LOCK = threading.Lock()


def fingerprint(directory):
    paths = [str(Path(directory) / 'deps'), *sys.path]
    # Package discovery is expensive. Recheck at most every five seconds, and
    # immediately after app-managed installation or a changed dependency folder.
    try:
        stamp = (Path(directory) / 'deps').stat().st_mtime_ns
    except OSError:
        stamp = None
    key = (tuple(paths), stamp)
    with _FINGERPRINT_LOCK:
        cached = _FINGERPRINTS.get(key)
        if cached and time.monotonic() - cached[0] < 5:
            return dict(cached[1])
    found = {}
    for distribution in importlib.metadata.distributions(path=paths):
        name = distribution.metadata.get('Name', '').lower().replace('_', '-')
        if name in {'torch', 'transformers', 'bitsandbytes', 'accelerate', 'pillow', 'numpy'}:
            found.setdefault(name, distribution.version)
    result = {**found, 'python': f'{sys.version_info.major}.{sys.version_info.minor}',
              'recipe': 'rgb-exif-pil-nf4-bf16-sdpa-doublequant-mean-v2', 'dimension': 768}
    with _FINGERPRINT_LOCK:
        if len(_FINGERPRINTS) >= 16:
            _FINGERPRINTS.clear()
        _FINGERPRINTS[key] = (time.monotonic(), result)
    return dict(result)


def child_environment(directory):
    allowed = {'PATH', 'HOME', 'USERPROFILE', 'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP', 'TMPDIR',
               'LD_LIBRARY_PATH', 'CUDA_VISIBLE_DEVICES', 'CUDA_HOME', 'CUDA_PATH',
               'LANG', 'LC_ALL', 'SSL_CERT_FILE', 'REQUESTS_CA_BUNDLE'}
    result = {k: v for k, v in os.environ.items() if k in allowed}
    result.update(HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', HF_HUB_DISABLE_TELEMETRY='1',
                  OMP_NUM_THREADS='2', OPENBLAS_NUM_THREADS='2', MKL_NUM_THREADS='2',
                  PYTHONPATH=os.pathsep.join([str(Path(directory) / 'deps'), str(Path(__file__).resolve().parents[1])]))
    return result


class EmbeddedVRS:
    def __init__(self, model_root, generation_lock):
        self.directory = Path(model_root) / 'vrs' / 'gemma4-vision'
        self.generation_lock = generation_lock
        self.lock = threading.RLock()
        self.cancelled = threading.Event()
        self.job = {'status': 'idle'}
        self._verified = None

    def verify(self):
        try:
            if json.loads((self.directory / 'provenance.json').read_text(encoding='utf-8'))['files'] != MODEL['files']:
                return False
            signature = tuple((name, (self.directory / name).stat().st_size,
                               (self.directory / name).stat().st_mtime_ns) for name in MODEL['files'])
            if self._verified == signature:
                return True
            if all(file_digest(self.directory / name) == digest for name, digest in MODEL['files'].items()):
                self._verified = signature
                return True
        except (OSError, ValueError, KeyError, TypeError):
            pass
        return False

    def status(self):
        packages = fingerprint(self.directory)
        missing = [name for name in DEPENDENCIES if name not in packages]
        try:
            available = importlib.util.find_spec('transformers.models.gemma4') is not None
        except (ImportError, ValueError):
            available = False
        if not available:
            missing.append('transformers')
        import torch
        cuda = torch.cuda.is_available()
        weights = self.verify()
        with self.lock:
            return {'embedded': True, 'weights_ready': weights, 'cuda': cuda,
                    'ready': weights and not missing and cuda, 'missing_dependencies': missing,
                    'model_bytes': MODEL['tensor_bytes'], 'directory': str(self.directory),
                    'fingerprint': packages, 'job': dict(self.job)}

    def start(self):
        with self.lock:
            if self.job['status'] == 'running':
                raise ValueError('VRS 준비가 진행 중입니다.')
            if not self.generation_lock.acquire(blocking=False):
                raise ValueError('생성 또는 색인 작업이 끝난 후 다시 시도해 주세요.')
            self.cancelled.clear()
            self.job = {'status': 'running', 'stage': 'dependencies', 'received_bytes': 0,
                        'total_bytes': MODEL['tensor_bytes']}
            threading.Thread(target=self._run, daemon=True).start()
        return self.status()

    def cancel(self):
        self.cancelled.set()
        return self.status()

    def _update(self, **values):
        with self.lock:
            self.job.update(values)

    def _run(self):
        try:
            self.directory.parent.mkdir(parents=True, exist_ok=True)
            missing = self.status()['missing_dependencies']
            if 'transformers' in missing:
                raise ValueError('TRANSFORMERS_VERSION: pip install -U "transformers>=5.16.1,<6"')
            if missing:
                target = self.directory / 'deps'
                target.mkdir(parents=True, exist_ok=True)
                with tempfile.TemporaryFile() as log:
                    process = subprocess.Popen([sys.executable, '-m', 'pip', 'install', '--disable-pip-version-check',
                        '--no-deps', '--target', str(target), *[f'{n}=={DEPENDENCIES[n]}' for n in missing]],
                        stdout=log, stderr=log)
                    try:
                        while process.poll() is None:
                            if self.cancelled.wait(.2):
                                raise InterruptedError('cancelled')
                        if process.returncode:
                            raise ValueError('DEPENDENCY_INSTALL: VRS 실행 패키지 설치에 실패했습니다.')
                    finally:
                        if process.poll() is None:
                            process.terminate()
                            try:
                                process.wait(timeout=5)
                            except subprocess.TimeoutExpired:
                                process.kill()
                                process.wait()
            if self.cancelled.is_set():
                raise InterruptedError('cancelled')
            if not self.verify():
                if shutil.disk_usage(self.directory.parent).free < 2 * MODEL['tensor_bytes']:
                    raise ValueError('DISK_SPACE: 인코더 준비에 700 MiB 이상의 여유 공간이 필요합니다.')
                from anima_app._vendor.vrs_int.prepare_encoder import prepare
                self._update(stage='download')
                with tempfile.TemporaryDirectory(prefix='prepare-', dir=self.directory.parent) as scratch:
                    staging = Path(scratch) / 'model'
                    prepare(staging, lambda done, total: self._update(received_bytes=done, total_bytes=total),
                            self.cancelled.is_set)
                    if self.cancelled.is_set():
                        raise InterruptedError('cancelled')
                    self.directory.mkdir(exist_ok=True)
                    for name in [*MODEL['files'], 'provenance.json']:
                        os.replace(staging / name, self.directory / name)
            if not self.verify():
                raise ValueError('PROVENANCE_MISMATCH: 인코더 파일 검증에 실패했습니다.')
            self._update(status='complete', stage='ready', received_bytes=MODEL['tensor_bytes'])
        except InterruptedError:
            self._update(status='cancelled')
        except Exception as exc:
            self._update(status='failed', error=str(exc)[:300])
        finally:
            with _FINGERPRINT_LOCK:
                _FINGERPRINTS.clear()
            self.generation_lock.release()


def contract_for(directory):
    try:
        files = [VENDOR / name for name in ('encoder.py', 'import_snapshot.py', 'model.json')]
        digest = hashlib.sha256(b''.join(path.read_bytes() for path in files))
        digest.update(json.dumps(fingerprint(directory), sort_keys=True).encode())
        # Pixel decoding/normalization and the worker are part of the contract.
        for name in ('library_visual.py', 'library_vrs.py'):
            digest.update(Path(__file__).with_name(name).read_bytes())
        # These are the pixel preprocessing and worker numerical recipes.
        digest.update(b'exif-transpose-RGB;Gemma4ImageProcessorPil;batch=4;unit-float32-v1')
        return 'anima-vrs-gemma4-v2:' + digest.hexdigest()
    except OSError:
        return None

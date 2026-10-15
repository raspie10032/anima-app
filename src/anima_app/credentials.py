"""Opt-in local OS credential storage; the disk index contains no secrets."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import threading
import uuid

STORAGE_ERROR = '이 PC의 자격증명 저장소를 사용할 수 없습니다. 잠금 해제 후 다시 시도해 주세요.'
RESTORE_ERROR = '저장된 토큰을 복원하지 못했습니다. 자격증명 저장소를 확인하고 앱을 다시 실행해 주세요.'


def system_backend():
    # Select only OS backends, never a plaintext/third-party fallback.
    if sys.platform == 'win32':
        from keyring.backends.Windows import WinVaultKeyring
        backend = WinVaultKeyring()
    elif sys.platform == 'darwin':
        from keyring.backends.macOS import Keyring
        backend = Keyring()
    else:
        from keyring.backends.SecretService import Keyring
        backend = Keyring()
    if backend.priority <= 0:
        raise RuntimeError('OS credential store unavailable')
    return backend


def normalize_token(value):
    if not isinstance(value, str):
        raise ValueError('토큰 형식을 확인해 주세요.')
    token = value.strip().removeprefix('Bearer ').strip()
    if token and (not 16 <= len(token) <= 4096 or not token.isascii()
                  or any(ord(c) < 33 or ord(c) == 127 for c in token)):
        raise ValueError('토큰 형식을 확인해 주세요.')
    return token


class CredentialStore:
    def __init__(self, paths, *, backend=None):
        self.index = paths.output_root / 'credentials' / 'index.json'
        digest = hashlib.sha256(str(paths.project_root.resolve()).encode()).hexdigest()[:24]
        self.service = 'Anima APP/' + digest
        self.lock = threading.RLock()
        self.backend = backend
        self.error = ''
        self.records = {}
        self.restored = {}
        self.index_valid = True
        try:
            if self.index.exists():
                if self.index.stat().st_size > 65536:
                    raise ValueError('Invalid credential index')
                value = json.loads(self.index.read_text(encoding='utf-8'))
                records = value['records']
                if value['version'] != 1 or not isinstance(records, dict) or len(records) > 9:
                    raise ValueError('Invalid credential index')
                for key, record in records.items():
                    if (not re.fullmatch(r'default|barracks-[a-f0-9]{32}', key)
                            or not isinstance(record, dict) or set(record) != {'ref', 'name'}
                            or not re.fullmatch(r'[a-f0-9]{32}', record['ref'])
                            or not isinstance(record['name'], str) or not 1 <= len(record['name']) <= 48
                            or any(ord(c) < 32 for c in record['name'])):
                        raise ValueError('Invalid credential index')
                self.records = records
        except Exception:
            self.index_valid = False
            self.error = RESTORE_ERROR
        if self.records:
            for key, record in self.records.items():
                try:
                    token = normalize_token(self._backend().get_password(self.service, record['ref']))
                    if not token:
                        raise ValueError('Missing saved credential')
                    self.restored[key] = {'name': record['name'], 'token': token}
                except Exception:
                    self.error = RESTORE_ERROR

    def _backend(self):
        if self.backend is None:
            self.backend = system_backend()
        return self.backend

    def status(self):
        with self.lock:
            try:
                self._backend()
                available = self.index_valid
            except Exception:
                available = False
            return {'available': available, 'error': self.error,
                    'default_saved': 'default' in self.records}

    def _write_index(self, records):
        self.index.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd, temporary = tempfile.mkstemp(dir=self.index.parent, prefix='.index-')
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as stream:
                json.dump({'version': 1, 'records': records}, stream, ensure_ascii=False)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.index)
        finally:
            Path(temporary).unlink(missing_ok=True)

    def save(self, key, token, name):
        with self.lock:
            if not self.index_valid:
                raise ValueError(STORAGE_ERROR)
            token = normalize_token(token)
            if not token or not re.fullmatch(r'default|barracks-[a-f0-9]{32}', key):
                raise ValueError('토큰 형식을 확인해 주세요.')
            previous = self.records.get(key)
            ref = previous['ref'] if previous else uuid.uuid4().hex
            backend = None
            previous_secret = None
            written = False
            try:
                backend = self._backend()
                if previous:
                    previous_secret = backend.get_password(self.service, ref)
                backend.set_password(self.service, ref, token)
                written = True
                records = {**self.records, key: {'ref': ref, 'name': name}}
                self._write_index(records)
            except Exception:
                if written:
                    try:
                        if previous_secret is not None:
                            backend.set_password(self.service, ref, previous_secret)
                        else:
                            backend.delete_password(self.service, ref)
                    except Exception:
                        pass
                raise ValueError(STORAGE_ERROR) from None
            self.records = records
            self.restored[key] = {'token': token, 'name': name}

    def delete(self, key):
        with self.lock:
            if not self.index_valid:
                raise ValueError(STORAGE_ERROR)
            record = self.records.get(key)
            if not record:
                return
            removed = False
            previous_secret = None
            try:
                backend = self._backend()
                previous_secret = backend.get_password(self.service, record['ref'])
                if previous_secret is not None:
                    backend.delete_password(self.service, record['ref'])
                    removed = True
                records = {k: v for k, v in self.records.items() if k != key}
                self._write_index(records)
            except Exception:
                if removed:
                    try:
                        backend.set_password(self.service, record['ref'], previous_secret)
                    except Exception:
                        pass
                raise ValueError(STORAGE_ERROR) from None
            self.records = records
            self.restored.pop(key, None)

    def restore_default(self):
        from anima_app.providers.novelai.auth import token_status
        if 'default' in self.restored and not token_status()['configured']:
            os.environ['NAI_ACCESS_TOKEN'] = self.restored['default']['token']

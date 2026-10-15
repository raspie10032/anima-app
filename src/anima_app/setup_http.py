"""Loopback setup UI, protected by the server's existing origin/Host guards."""
import os
import threading

from anima_app import library_core
from anima_app.providers.novelai.auth import token_status
from anima_app.credentials import normalize_token


class SetupHTTP:
    def __init__(self, paths, library_http, generation_lock, credentials):
        self.paths = paths
        self.library_http = library_http
        self.generation_lock = generation_lock
        self.credentials = credentials
        self.lock = threading.RLock()
        self.model_job = {'status': 'idle'}

    def status(self):
        from anima_app.server import handle_readiness
        lib = self.library_http.library
        with self.lock:
            model_job = dict(self.model_job)
        return {'nai': token_status(), 'credentials': self.credentials.status(),
                'anima': handle_readiness(paths=self.paths),
                'vrs': {**lib.vrs.runtime.status(), 'enabled': lib.vrs_enabled}, 'core': library_core.status(),
                'library': lib.status(), 'model_job': model_job}

    def handle(self, handler, parsed, method):
        route = parsed.path.removeprefix('/api/setup/')
        try:
            if method == 'GET' and route == 'status':
                result = self.status()
            elif method == 'GET' and route == 'catalog':
                from anima_app.setup_catalog import catalog
                result = catalog(self.paths, self.status())
            elif method == 'GET' and route == 'diagnostics':
                lib = self.library_http.library
                with lib.connect() as c:
                    issues = [dict(row) for row in c.execute('SELECT * FROM index_issues ORDER BY updated DESC LIMIT 50')]
                    imports = [dict(row) for row in c.execute('SELECT * FROM import_issues ORDER BY updated DESC LIMIT 50')]
                result = {'index_issues': issues, 'import_issues': imports,
                          'log_path': str(lib.root / 'diagnostics' / 'last-encoder.json')}
            elif method == 'POST':
                data = handler._read_json_object()
                if data is None:
                    return
                if route == 'nai':
                    if (set(data) - {'token', 'persist', 'use_current'}
                            or type(data.get('persist', False)) is not bool
                            or type(data.get('use_current', False)) is not bool
                            or ('token' in data) == data.get('use_current', False)):
                        raise ValueError('토큰을 입력해 주세요.')
                    from anima_app.providers.novelai.auth import get_token
                    if data.get('use_current') and not token_status()['configured']:
                        raise ValueError('토큰을 입력해 주세요.')
                    token = normalize_token(get_token() if data.get('use_current') else data['token'])
                    if not self.generation_lock.acquire(blocking=False):
                        raise ValueError('생성이 끝난 후 토큰을 변경해 주세요.')
                    try:
                        with self.lock:
                            if token and data.get('persist', False):
                                self.credentials.save('default', token, 'NAI')
                            else:
                                self.credentials.delete('default')
                        os.environ.pop('NAI_API_TOKEN', None)
                        if token:
                            os.environ['NAI_ACCESS_TOKEN'] = token
                        else:
                            os.environ.pop('NAI_ACCESS_TOKEN', None)
                    finally:
                        self.generation_lock.release()
                    result = {**token_status(), 'credentials': self.credentials.status()}
                elif route == 'vrs/prepare':
                    result = self.library_http.library.prepare_vrs()
                elif route == 'vrs/settings':
                    if set(data) != {'enabled'}:
                        raise ValueError('VRS 사용 여부는 켜기 또는 끄기로 지정해 주세요.')
                    result = self.library_http.library.set_vrs_enabled(data['enabled'])
                elif route == 'vrs/cancel':
                    result = self.library_http.library.vrs.runtime.cancel()
                elif route == 'anima/prepare':
                    if data.get('profile') not in {'anima-t2i', 'anima-aesthetic-v1.1', 'face-detailer-detectors'}:
                        raise ValueError('모델 준비 항목을 확인해 주세요.')
                    with self.lock:
                        if not self.generation_lock.acquire(blocking=False):
                            raise ValueError('생성 또는 모델 준비가 진행 중입니다.')
                        self.model_job = {'status': 'running', 'profile': data['profile']}
                        threading.Thread(target=self._prepare, args=(data['profile'],), daemon=True).start()
                    result = dict(self.model_job)
                else:
                    handler._send_json(404, {'error': 'not found'})
                    return
            else:
                handler._send_json(404, {'error': 'not found'})
                return
            handler._send_json(200, result)
        except (ValueError, OSError, TypeError) as exc:
            handler._send_json(400, {'error': str(exc), 'error_code': 'setup_invalid'})

    def _prepare(self, profile):
        try:
            from anima_app.server import handle_model_prepare
            code, result = handle_model_prepare({'profile': profile, 'source': 'auto'}, paths=self.paths)
            with self.lock:
                self.model_job = {'status': 'complete' if code == 200 else 'failed', 'profile': profile,
                                  'error': result.get('error', '')}
        except Exception as exc:
            with self.lock:
                self.model_job = {'status': 'failed', 'profile': profile, 'error': str(exc)[:300]}
        finally:
            self.generation_lock.release()

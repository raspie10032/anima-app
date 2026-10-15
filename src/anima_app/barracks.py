"""NAI-only, finite T2I batches. Credentials never enter public job records."""
from __future__ import annotations

import copy
import secrets
import threading
import time
import uuid

from anima_app.prompt_routing import context_fields, route_request
from anima_app.providers.novelai import auth, request_from_payload
from anima_app.providers.novelai.errors import NovelAIError
from anima_app.providers.novelai.requests import MAX_NAI_SEED, reject_credentials
from anima_app.wildcards import WILDCARD_MODES
from anima_app.credentials import CredentialStore, normalize_token

MAX_ACCOUNTS = 8
MAX_IMAGES = 100
SCOPE_ERROR = '배럭은 NAI 텍스트→이미지 단독 생성만 지원합니다.'


def validate_request(raw, paths, default_dry_run):
    if not isinstance(raw, dict):
        raise ValueError(SCOPE_ERROR)
    reject_credentials(raw)
    if raw.get('provider') != 'novelai' or 'workflow' in raw:
        raise ValueError(SCOPE_ERROR)
    parsed = request_from_payload(raw)
    if (parsed.operation != 'generate' or parsed.input_image or parsed.mask_image
            or parsed.vibes or parsed.references or parsed.detailer['enabled']):
        raise ValueError(SCOPE_ERROR)
    dry_run = raw.get('dry_run', default_dry_run)
    if not isinstance(dry_run, bool):
        raise ValueError('dry_run must be a boolean')
    mode = raw.get('wildcard_mode', 'random')
    if mode not in WILDCARD_MODES:
        raise ValueError('Invalid wildcard mode')
    normalized = {**parsed.to_payload(), **context_fields(raw), 'dry_run': dry_run, 'wildcard_mode': mode}
    route_request(normalized, paths=paths)
    return normalized


class Barracks:
    def __init__(self, paths, *, default_dry_run=False, generate=None, credentials=None):
        self.paths = paths
        self.default_dry_run = default_dry_run
        self.generate = generate or self._generate
        self.lock = threading.RLock()
        self.accounts = {}  # private credentials; never serialized
        self.credentials = credentials or CredentialStore(paths)
        for key, record in self.credentials.restored.items():
            if key.startswith('barracks-'):
                account_id = key.removeprefix('barracks-')
                self.accounts[account_id] = {'id': account_id, **record, 'saved': True}
        self.batch = None
        self.stop = threading.Event()
        self.closed = False
        self.workers = []

    def _generate(self, request, cancelled):
        from anima_app.server import handle_generate
        return handle_generate(request, paths=self.paths, cancelled=cancelled)

    def _busy(self):
        return bool(self.batch and self.batch['status'] == 'running')

    def add_account(self, data):
        if (data.keys() - {'name', 'token', 'use_current', 'persist'} or
                not isinstance(data.get('name'), str) or not 1 <= len(data['name'].strip()) <= 48):
            raise ValueError('계정 이름은 1~48자로 입력해 주세요.')
        if any(ord(c) < 32 for c in data['name']):
            raise ValueError('계정 이름은 1~48자로 입력해 주세요.')
        use_current = data.get('use_current', False)
        if (not isinstance(use_current, bool) or (use_current and 'token' in data)
                or type(data.get('persist', False)) is not bool):
            raise ValueError('토큰 형식을 확인해 주세요.')
        token = auth.get_token() if use_current else data.get('token')
        token = normalize_token(token)
        if not token:
            raise ValueError('토큰 형식을 확인해 주세요.')
        with self.lock:
            if self._busy() or self.closed:
                raise ValueError('배럭이 끝난 후 계정을 변경해 주세요.')
            if len(self.accounts) >= MAX_ACCOUNTS:
                raise ValueError('배럭 계정은 최대 8개입니다.')
            if any(a['token'] == token for a in self.accounts.values()):
                raise ValueError('이미 등록된 토큰입니다.')
            name = data['name'].strip()
            if name == token or any(a['name'] == name for a in self.accounts.values()):
                raise ValueError('다른 계정 이름을 입력해 주세요.')
            key = uuid.uuid4().hex
            saved = data.get('persist', False)
            if saved:
                saved_count = sum(k.startswith('barracks-') for k in self.credentials.records)
                if saved_count >= MAX_ACCOUNTS:
                    raise ValueError('배럭 계정은 최대 8개입니다.')
                self.credentials.save('barracks-' + key, token, name)
            self.accounts[key] = {'id': key, 'name': name, 'token': token, 'saved': saved}
            return self.snapshot()

    def set_storage(self, data):
        with self.lock:
            if self._busy() or self.closed:
                raise ValueError('배럭이 끝난 후 계정을 변경해 주세요.')
            if (set(data) != {'id', 'persist'} or not isinstance(data['id'], str)
                    or data['id'] not in self.accounts or type(data['persist']) is not bool):
                raise ValueError('계정을 선택해 주세요.')
            account = self.accounts[data['id']]
            key = 'barracks-' + account['id']
            if data['persist']:
                if key not in self.credentials.records and sum(k.startswith('barracks-') for k in self.credentials.records) >= MAX_ACCOUNTS:
                    raise ValueError('배럭 계정은 최대 8개입니다.')
                self.credentials.save(key, account['token'], account['name'])
            else:
                self.credentials.delete(key)
            account['saved'] = data['persist']
            return self.snapshot()

    def remove_account(self, data):
        with self.lock:
            if self._busy():
                raise ValueError('배럭이 끝난 후 계정을 변경해 주세요.')
            if set(data) != {'id'} or not isinstance(data['id'], str) or data['id'] not in self.accounts:
                raise ValueError('계정을 선택해 주세요.')
            self.credentials.delete('barracks-' + data['id'])
            del self.accounts[data['id']]
            return self.snapshot()

    def enqueue(self, data):
        if data.keys() - {'request', 'account_ids', 'count', 'seed_mode'}:
            raise ValueError(SCOPE_ERROR)
        request = validate_request(data.get('request'), self.paths, self.default_dry_run)
        count = data.get('count', 1)
        if type(count) is not int or not 1 <= count <= MAX_IMAGES:
            raise ValueError('생성 장수는 1~100장으로 입력해 주세요.')
        mode = data.get('seed_mode', 'increment')
        if mode not in {'fixed', 'increment', 'random'}:
            raise ValueError('시드 방식을 선택해 주세요.')
        ids = data.get('account_ids')
        if (not isinstance(ids, list) or not 1 <= len(ids) <= MAX_ACCOUNTS
                or any(not isinstance(i, str) for i in ids) or len(set(ids)) != len(ids)):
            raise ValueError('사용할 계정을 선택해 주세요.')
        with self.lock:
            if self._busy() or self.closed:
                raise ValueError('배럭이 이미 실행 중입니다.')
            if any(i not in self.accounts for i in ids):
                raise ValueError('사용할 계정을 선택해 주세요.')
            base_seed = request.get('seed')
            if base_seed is None:
                base_seed = secrets.randbelow(MAX_NAI_SEED + 1)
            batch_id = uuid.uuid4().hex
            jobs = []
            for index in range(count):
                seed = (secrets.randbelow(MAX_NAI_SEED + 1) if mode == 'random' else
                        (base_seed + index) % (MAX_NAI_SEED + 1) if mode == 'increment' else base_seed)
                jobs.append({'id': uuid.uuid4().hex, 'index': index, 'seed': seed,
                             'status': 'queued', 'account_id': None, 'account_name': None,
                             'result': None, 'http_status': None})
            selected = [self.accounts[i] for i in ids[:count]]
            self.stop = threading.Event()
            self.batch = {'id': batch_id, 'status': 'running', 'count': count,
                          'created_at': time.time(), 'seed_mode': mode, 'jobs': jobs,
                          'accounts': [{'id': a['id'], 'name': a['name'], 'status': 'ready'} for a in selected]}
            self.workers = [threading.Thread(target=self._worker, args=(a, request), daemon=True,
                                            name='nai-barracks-' + a['id'][:8]) for a in selected]
            self._remaining = len(self.workers)
            for worker in self.workers:
                worker.start()
            return self.snapshot()

    def _worker(self, account, request):
        account_state = next(a for a in self.batch['accounts'] if a['id'] == account['id'])
        try:
            while True:
                with self.lock:
                    if self.stop.is_set():
                        return
                    job = next((j for j in self.batch['jobs'] if j['status'] == 'queued'), None)
                    if job is None:
                        return
                    job.update(status='running', account_id=account['id'], account_name=account['name'])
                    account_state['status'] = 'running'
                    identity = {'account_id': account['id'], 'account_name': account['name'],
                                'batch_id': self.batch['id'], 'job_id': job['id'], 'index': job['index']}
                with auth.account_scope(account['token'], identity):
                    try:
                        status, result = self.generate({**copy.deepcopy(request), 'seed': job['seed']}, self.stop.is_set)
                    except Exception:
                        status, result = 500, {'error': '배럭 생성에 실패했습니다.', 'remote_outcome_unknown': True}
                with self.lock:
                    job.update(http_status=int(status), result=result,
                               status='completed' if status < 400 else 'cancelled' if status == 499 else 'failed')
                    if status >= 400:
                        account_state['status'] = 'cancelled' if status == 499 else 'paused'
                        return  # never move a failed/uncertain image to another token
                    account_state['status'] = 'ready'
        finally:
            with self.lock:
                if account_state['status'] in {'ready', 'running'}:
                    account_state['status'] = 'cancelled' if self.stop.is_set() else 'completed'
                self._remaining -= 1
                if self._remaining == 0:
                    for job in self.batch['jobs']:
                        if job['status'] == 'queued':
                            job['status'] = 'cancelled' if self.stop.is_set() else 'blocked'
                    statuses = {j['status'] for j in self.batch['jobs']}
                    self.batch['status'] = ('completed' if statuses == {'completed'} else
                                            'cancelled' if self.stop.is_set() else 'failed')
                    self.batch['finished_at'] = time.time()
                    if self.closed:
                        self.accounts.clear()

    def cancel(self):
        with self.lock:
            if self._busy():
                self.stop.set()
                for job in self.batch['jobs']:
                    if job['status'] == 'queued':
                        job['status'] = 'cancelled'
            return self.snapshot()

    def snapshot(self):
        with self.lock:
            batch = copy.deepcopy(self.batch)
            if batch:
                batch['summary'] = {state: sum(j['status'] == state for j in batch['jobs'])
                                    for state in ('queued', 'running', 'completed', 'failed', 'cancelled', 'blocked')}
            return {'accounts': [{'id': a['id'], 'name': a['name'], 'saved': a['saved']} for a in self.accounts.values()],
                    'credentials': self.credentials.status(),
                    'batch': batch, 'max_accounts': MAX_ACCOUNTS, 'max_images': MAX_IMAGES,
                    'current_token_available': auth.token_status()['configured'],
                    'default_dry_run': self.default_dry_run}

    def close(self):
        with self.lock:
            self.closed = True
            self.cancel()
            if not self._busy():
                self.accounts.clear()

    def handle(self, handler, parsed, method):
        route = parsed.path.removeprefix('/api/barracks/')
        try:
            if method == 'GET' and route == 'status':
                handler._send_json(200, self.snapshot())
                return
            actions = {'accounts': self.add_account, 'accounts/remove': self.remove_account,
                       'accounts/storage': self.set_storage,
                       'start': self.enqueue, 'cancel': lambda _: self.cancel()}
            if method != 'POST' or route not in actions:
                handler._send_json(404, {'error': 'not found'})
                return
            data = handler._read_json_object()
            if data is not None:
                handler._send_json(202 if route == 'start' else 200, actions[route](data))
        except NovelAIError as exc:
            handler._send_json(exc.status, exc.payload())
        except (TypeError, ValueError, KeyError) as exc:
            # Validation messages are local constants; never echo a credential body.
            message = str(exc) if type(exc) is ValueError else '배럭 설정을 확인해 주세요.'
            handler._send_json(400, {'error_code': 'barracks_invalid', 'error': message})

import io
import json
import threading
import time
import urllib.error
import zipfile
from concurrent.futures import ThreadPoolExecutor

import pytest
from PIL import Image

from anima_app.barracks import Barracks, validate_request
from anima_app.config import AppPaths
from anima_app.providers.novelai import auth, client
from anima_app.providers.novelai.errors import NovelAIError
from anima_app.providers.novelai.models import GENERATE_IMAGE_URL


def request(**extra):
    return {'provider': 'novelai', 'prompt': 'a blue bird', 'width': 64, 'height': 64,
            'steps': 1, 'seed': 42, 'nai_model': 'nai-diffusion-4-5-full', **extra}


def add_accounts(barracks, n=2):
    for i in range(n):
        barracks.add_account({'name': f'Account {i}', 'token': f'test-barracks-secret-{i}'})
    return [a['id'] for a in barracks.snapshot()['accounts']]


def finish(barracks):
    for worker in barracks.workers:
        worker.join(5)
        assert not worker.is_alive()
    result = barracks.snapshot()
    assert result['batch']['status'] != 'running'
    return result


def archive(color):
    png, result = io.BytesIO(), io.BytesIO()
    Image.new('RGB', (64, 64), color).save(png, format='PNG')
    with zipfile.ZipFile(result, 'w') as z:
        z.writestr('image.png', png.getvalue())
    return result.getvalue()


@pytest.mark.parametrize('extra', [
    {'provider': 'local'}, {'workflow': {}}, {'operation': 'img2img'},
    {'operation': 'infill'}, {'operation': 'detail'}, {'operation': 'focused_infill'},
    {'input_image': 'external.png'}, {'mask_image': 'mask.png'},
    {'nai_detailer': {'enabled': True}}, {'detailer': {'enabled': True}},
    {'upscale': {'enabled': True}}, {'face_detailer': {'enabled': True}},
    {'i2i': {'enabled': True}}, {'loras': [{'path': 'model'}]},
    {'nai_vibes': [{}]}, {'nai_references': [{}]}, {'token': 'should-not-be-accepted'},
])
def test_only_standalone_t2i_is_accepted(tmp_path, extra):
    with pytest.raises(ValueError):
        validate_request(request(**extra), AppPaths(tmp_path), False)


def test_parallel_tokens_real_provider_path_retains_outputs_and_private_identity(tmp_path, monkeypatch, nai_mock_account):
    monkeypatch.setenv('NAI_ACCESS_TOKEN', 'existing-primary-secret')
    monkeypatch.setattr(client, 'REQUEST_INTERVAL_SECONDS', .001)
    entered = threading.Barrier(2)
    seen = []

    def transport(url, headers, body, timeout):
        secret = headers['Authorization'].removeprefix('Bearer ')
        seen.append((secret, json.loads(body)))
        entered.wait(4)  # different credentials must reach the transport concurrently
        return archive('blue' if secret.endswith('0') else 'red')

    monkeypatch.setattr(client, '_requests_transport', transport)
    b = Barracks(AppPaths(tmp_path))
    ids = add_accounts(b)
    b.enqueue({'request': request(), 'account_ids': ids, 'count': 2, 'seed_mode': 'fixed'})
    result = finish(b)
    assert result['batch']['summary']['completed'] == 2
    assert {token for token, _ in seen} == {'test-barracks-secret-0', 'test-barracks-secret-1'}
    assert all(p['action'] == 'generate' and p['parameters']['seed'] == 42 for _, p in seen)
    assert auth.get_token() == 'existing-primary-secret'
    manifests = list((tmp_path / 'outputs/manifests').glob('*.json'))
    images = list((tmp_path / 'outputs/images').glob('*.png'))
    assert len(manifests) == len(images) == 2  # same prompt/seed in the same second cannot overwrite
    records = [json.loads(p.read_text()) for p in manifests]
    assert {m['barracks']['account_name'] for m in records} == {'Account 0', 'Account 1'}
    serialized = json.dumps(result) + ''.join(p.read_text() for p in manifests)
    assert not any(secret in serialized for secret, _ in seen)
    assert all(auth.current_account() is None for _ in range(2))


def test_same_token_serializes_across_workers_and_other_tokens_still_run(monkeypatch):
    monkeypatch.setattr(client, '_request_coordinator', client.RequestCoordinator())
    monkeypatch.setattr(client, 'REQUEST_INTERVAL_SECONDS', .001)
    entered, release, second_token = threading.Event(), threading.Event(), threading.Event()
    count, lock = {}, threading.Lock()

    def transport(url, headers, body, timeout):
        token = headers['Authorization']
        with lock:
            count[token] = count.get(token, 0) + 1
            assert count[token] == 1
        if token.endswith('one'):
            entered.set()
            assert release.wait(3)
        else:
            second_token.set()
        with lock:
            count[token] -= 1
        return b'ok'

    def post(token):
        return client.post_json(GENERATE_IMAGE_URL, token=token, payload={}, transport=transport)

    with ThreadPoolExecutor(3) as pool:
        first = pool.submit(post, 'one')
        assert entered.wait(3)
        same = pool.submit(post, 'one')
        other = pool.submit(post, 'two')
        try:
            assert second_token.wait(3)
            assert not same.done()
        finally:
            release.set()
        assert first.result(3) == same.result(3) == other.result(3) == b'ok'


def test_cancel_keeps_inflight_result_and_blocks_following_images(tmp_path):
    entered, release = threading.Event(), threading.Event()
    seen = []

    def generate(req, cancelled):
        seen.append(req['seed'])
        entered.set()
        assert release.wait(3)
        return 200, {'output_path': 'already-generated.png', 'cancellation_requested': cancelled()}

    b = Barracks(AppPaths(tmp_path), generate=generate)
    ids = add_accounts(b, 1)
    b.enqueue({'request': request(), 'account_ids': ids, 'count': 4})
    try:
        assert entered.wait(3)
        with pytest.raises(ValueError):
            b.remove_account({'id': ids[0]})
        with pytest.raises(ValueError):
            b.enqueue({'request': request(), 'account_ids': ids})
        b.cancel()
    finally:
        release.set()
    result = finish(b)['batch']
    assert seen == [42]
    assert result['status'] == 'cancelled'
    assert result['summary']['completed'] == 1
    assert result['summary']['cancelled'] == 3
    assert result['jobs'][0]['result']['output_path'] == 'already-generated.png'


@pytest.mark.parametrize('status,unknown', [(401, False), (402, False), (429, False), (504, True)])
def test_failed_image_is_never_reassigned_and_account_pauses(tmp_path, status, unknown):
    seen = []

    def generate(req, cancelled):
        seen.append((auth.get_token(), req['seed']))
        return status, {'error': 'mock failure', 'remote_outcome_unknown': unknown}

    b = Barracks(AppPaths(tmp_path), generate=generate)
    ids = add_accounts(b)
    b.enqueue({'request': request(), 'account_ids': ids, 'count': 5})
    batch = finish(b)['batch']
    assert len(seen) == 2
    assert len({seed for _, seed in seen}) == 2
    assert batch['summary']['failed'] == 2
    assert batch['summary']['blocked'] == 3
    assert all(a['status'] == 'paused' for a in batch['accounts'])


def test_credentials_never_leak_from_exceptions_and_scopes_restore(monkeypatch):
    monkeypatch.setenv('NAI_ACCESS_TOKEN', 'primary-token')
    with auth.account_scope('private-secondary-token', {'account_name': 'secondary'}):
        assert auth.get_token() == 'private-secondary-token'
        error = NovelAIError('nai_auth_failed', 'failed private-secondary-token', details='private-secondary-token')
        assert 'private-secondary-token' not in json.dumps(error.payload())
    assert auth.get_token() == 'primary-token'
    assert auth.current_account() is None


def test_duplicate_current_token_and_limits(tmp_path, monkeypatch):
    b = Barracks(AppPaths(tmp_path), default_dry_run=True)
    monkeypatch.setenv('NAI_ACCESS_TOKEN', 'test-barracks-secret-0')
    ids = add_accounts(b, 1)
    with pytest.raises(ValueError):
        b.add_account({'name': 'duplicate', 'use_current': True})
    for count in (True, 0, 101, '2'):
        with pytest.raises(ValueError):
            b.enqueue({'request': request(), 'account_ids': ids, 'count': count})
    for selected in ([ids[0], ids[0]], ['missing'], []):
        with pytest.raises(ValueError):
            b.enqueue({'request': request(), 'account_ids': selected})
    b.enqueue({'request': request(seed=2**32-1), 'account_ids': ids, 'count': 3})
    batch = finish(b)['batch']
    assert [j['seed'] for j in batch['jobs']] == [2**32-1, 0, 1]
    assert batch['summary']['completed'] == 3
    assert all(j['result']['dry_run'] for j in batch['jobs'])
    b.close()
    assert not b.snapshot()['accounts']


def test_http_scope_and_secret_free_snapshots(tmp_path):
    import http.client
    from anima_app.server import create_http_server
    server = create_http_server('127.0.0.1', 0, paths=AppPaths(tmp_path), default_dry_run=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    conn = http.client.HTTPConnection('127.0.0.1', server.server_address[1], timeout=5)

    def call(path, data=None, origin=None):
        headers = {'Content-Type': 'application/json'}
        if origin:
            headers['Origin'] = origin
        conn.request('GET' if data is None else 'POST', '/api/barracks/' + path,
                     None if data is None else json.dumps(data), headers)
        response = conn.getresponse()
        return response.status, json.loads(response.read())

    try:
        assert call('accounts', {'name': 'blocked', 'token': 'test-barracks-secret-http'}, 'https://example.org')[0] == 403
        status, state = call('accounts', {'name': 'HTTP', 'token': 'test-barracks-secret-http'})
        assert status == 200
        ids = [a['id'] for a in state['accounts']]
        assert call('start', {'account_ids': ids, 'request': request(workflow={})})[0] == 400
        assert call('start', {'account_ids': ids, 'request': request(), 'count': 2})[0] == 202
        for _ in range(100):
            _, state = call('status')
            if state['batch']['status'] != 'running':
                break
            time.sleep(.01)
        assert state['batch']['summary']['completed'] == 2
        assert 'test-barracks-secret-http' not in json.dumps(state)
        assert call('accounts/remove', {'id': ids[0]})[1]['accounts'] == []
    finally:
        conn.close()
        server.shutdown()
        server.server_close()
        thread.join(5)


def test_rate_limit_one_retry_only_and_cooldown_is_account_specific(monkeypatch):
    now = [100.0]
    coordinator = client.RequestCoordinator(lambda: now[0])
    monkeypatch.setattr(client, '_request_coordinator', coordinator)
    attempts = []

    def transport(url, headers, body, timeout):
        attempts.append(headers['Authorization'])
        raise urllib.error.HTTPError(url, 429, 'rate limit', {'Retry-After': '2'}, None)

    with pytest.raises(NovelAIError) as result:
        client.post_json(GENERATE_IMAGE_URL, token='rate-limited', payload={}, transport=transport,
                         sleep=lambda delay: now.__setitem__(0, now[0] + delay))
    assert result.value.status == 429
    assert attempts == ['Bearer rate-limited', 'Bearer rate-limited']
    assert coordinator.for_token('rate-limited').next_request_at > now[0]
    assert coordinator.for_token('other').next_request_at == 0

"""The setup form must never expose a token or accept cross-origin changes."""
import threading

import pytest
import requests

from anima_app.config import AppPaths
from anima_app.server import create_http_server


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.delenv('NAI_ACCESS_TOKEN', raising=False)
    monkeypatch.delenv('NAI_API_TOKEN', raising=False)
    server = create_http_server('127.0.0.1', 0, paths=AppPaths(tmp_path), default_dry_run=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_address[1]}'
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_setup_token_is_memory_only_and_not_echoed(app, tmp_path):
    token = 'TEST_ONLY_' + 'x' * 40
    assert requests.post(app+'/api/setup/nai', json={'token':'Bearer '+token}, timeout=10).json()['configured']
    status = requests.get(app+'/api/setup/status', timeout=10)
    assert status.status_code == 200 and status.json()['nai']['configured']
    assert token not in status.text
    assert status.json()['core']['ready']
    assert not status.json()['vrs']['weights_ready']
    assert not requests.post(app+'/api/setup/nai',json={'token':''},timeout=10).json()['configured']
    for path in tmp_path.rglob('*'):
        if path.is_file():
            assert token.encode() not in path.read_bytes()


def test_setup_rejects_origin_injection_and_bad_tokens(app):
    response = requests.post(app+'/api/setup/nai',json={'token':'x'*32},headers={'Origin':'https://example.org'},timeout=10)
    assert response.status_code == 403
    for data in [{'token':'short'},{'token':{}},{'token':'abc\nx'*20},{'token':'x'*32,'save':True}]:
        assert requests.post(app+'/api/setup/nai',json=data,timeout=10).status_code == 400


def test_setup_rejects_unknown_downloads_and_reports_missing_files(app):
    assert requests.post(app+'/api/setup/anima/prepare',json={'profile':'/etc/passwd'},timeout=10).status_code == 400
    result = requests.get(app+'/api/setup/diagnostics',timeout=10).json()
    assert result['index_issues'] == result['import_issues'] == []


def test_vrs_switch_guards_all_entrypoints_and_validates_input(app):
    for data in ({}, {'enabled': 'false'}, {'enabled': 0}, {'enabled': False, 'extra': True}):
        assert requests.post(app+'/api/setup/vrs/settings', json=data, timeout=10).status_code == 400
    assert requests.post(app+'/api/setup/vrs/settings', json={'enabled': False},
                         headers={'Origin': 'https://example.org'}, timeout=10).status_code == 403
    assert requests.get(app+'/api/setup/status', timeout=10).json()['vrs']['enabled']
    assert requests.post(app+'/api/setup/vrs/settings', json={'enabled': False}, timeout=10).json() == {'enabled': False}
    assert not requests.get(app+'/api/library/status', timeout=10).json()['vrs_enabled']
    for route, data in [('setup/vrs/prepare', {}), ('library/import', {'kind': 'vrs'}),
                        ('library/search', {'id': '0'*64, 'mode': 'vrs'})]:
        response = requests.post(app+'/api/'+route, json=data, timeout=10)
        assert response.status_code == 400 and 'VRS가 꺼져' in response.json()['error']
    assert requests.post(app+'/api/setup/vrs/settings', json={'enabled': True}, timeout=10).json()['enabled']


def test_catalog_uses_profile_files_and_never_exposes_token(app, tmp_path):
    fake = 'TEST_ONLY_' + 'x'*40
    requests.post(app+'/api/setup/nai', json={'token': fake}, timeout=10)
    response = requests.get(app+'/api/setup/catalog', timeout=10)
    assert response.status_code == 200 and fake not in response.text
    data = response.json()
    assert data['model_root'] == str(tmp_path / 'models')
    groups = {g['id']: g for g in data['groups']}
    assert groups['nai']['ready'] and not groups['nai']['files']
    assert groups['core']['ready'] and not groups['core']['files']
    assert len(groups['anima-t2i']['files']) == 3
    assert all(f['status'] == 'missing' for f in groups['anima-t2i']['files'])
    assert len(groups['vrs']['files']) == 3
    assert all(r['url'].startswith('https://') for r in data['references'])

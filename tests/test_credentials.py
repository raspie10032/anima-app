import json
import os
import threading
import urllib.error
import urllib.request

import pytest

from anima_app.barracks import Barracks
from anima_app.config import AppPaths
from anima_app.credentials import CredentialStore, STORAGE_ERROR
from anima_app.server import create_http_server


class MemoryVault:
    def __init__(self):
        self.secrets = {}
        self.fail = False

    def get_password(self, service, ref):
        if self.fail:
            raise RuntimeError('backend exception with private-token-do-not-show')
        return self.secrets.get((service, ref))

    def set_password(self, service, ref, value):
        if self.fail:
            raise RuntimeError(value)
        self.secrets[service, ref] = value

    def delete_password(self, service, ref):
        if self.fail:
            raise RuntimeError('private-token-do-not-show')
        del self.secrets[service, ref]


@pytest.fixture
def vault(monkeypatch):
    backend = MemoryVault()
    monkeypatch.setattr('anima_app.credentials.system_backend', lambda: backend)
    monkeypatch.delenv('NAI_ACCESS_TOKEN', raising=False)
    monkeypatch.delenv('NAI_API_TOKEN', raising=False)
    return backend


def test_saved_default_and_barracks_restore_only_opted_in_credentials(tmp_path, vault):
    paths = AppPaths(tmp_path)
    store = CredentialStore(paths)
    store.save('default', 'default-private-token', 'NAI')
    barracks = Barracks(paths, credentials=store)
    barracks.add_account({'name': 'Kept', 'token': 'kept-private-token', 'persist': True})
    barracks.add_account({'name': 'Temporary', 'token': 'temp-private-token'})
    fresh = CredentialStore(paths)
    fresh.restore_default()
    assert os.environ['NAI_ACCESS_TOKEN'] == 'default-private-token'
    restored = Barracks(paths, credentials=fresh)
    assert [(a['name'], a['saved']) for a in restored.snapshot()['accounts']] == [('Kept', True)]
    snapshot = json.dumps(restored.snapshot())
    index = fresh.index.read_text()
    for secret in ['default-private-token', 'kept-private-token', 'temp-private-token']:
        assert secret not in snapshot and secret not in index
    if os.name != 'nt':
        assert fresh.index.stat().st_mode & 0o077 == 0


def test_save_existing_forget_and_delete_are_independent(tmp_path, vault):
    paths = AppPaths(tmp_path)
    b = Barracks(paths)
    b.add_account({'name': 'Account', 'token': 'same-private-token'})
    account = b.snapshot()['accounts'][0]['id']
    b.set_storage({'id': account, 'persist': True})
    assert b.snapshot()['accounts'][0]['saved']
    b.set_storage({'id': account, 'persist': False})
    assert b.accounts[account]['token'] == 'same-private-token'
    assert not Barracks(paths).snapshot()['accounts']
    b.set_storage({'id': account, 'persist': True})
    b.credentials.save('default', 'same-private-token', 'NAI')
    b.remove_account({'id': account})
    assert CredentialStore(paths).restored == {'default': {'name': 'NAI', 'token': 'same-private-token'}}
    b.credentials.delete('default')
    assert not vault.secrets and not CredentialStore(paths).restored


def test_environment_precedence_and_per_installation_isolation(tmp_path, vault, monkeypatch):
    store = CredentialStore(AppPaths(tmp_path / 'one'))
    store.save('default', 'saved-private-token', 'NAI')
    monkeypatch.setenv('NAI_API_TOKEN', 'launch-private-token')
    CredentialStore(AppPaths(tmp_path / 'one')).restore_default()
    assert 'NAI_ACCESS_TOKEN' not in os.environ
    assert os.environ['NAI_API_TOKEN'] == 'launch-private-token'
    assert not CredentialStore(AppPaths(tmp_path / 'two')).restored


def test_backend_failure_never_falls_back_or_changes_active_account(tmp_path, vault):
    b = Barracks(AppPaths(tmp_path))
    b.add_account({'name': 'Saved', 'token': 'private-token-do-not-show', 'persist': True})
    account = b.snapshot()['accounts'][0]['id']
    before = b.credentials.index.read_bytes()
    vault.fail = True
    for operation in [lambda: b.remove_account({'id': account}),
                      lambda: b.set_storage({'id': account, 'persist': False}),
                      lambda: b.add_account({'name': 'Second', 'token': 'second-private-token', 'persist': True})]:
        with pytest.raises(ValueError, match=STORAGE_ERROR) as error:
            operation()
        assert 'private-token' not in str(error.value)
    assert b.credentials.index.read_bytes() == before
    assert len(b.accounts) == 1
    fresh = CredentialStore(AppPaths(tmp_path))
    assert not fresh.restored
    assert fresh.status()['error']
    assert 'private-token' not in json.dumps(fresh.status())


def test_index_write_failure_rolls_back_vault_and_state(tmp_path, vault, monkeypatch):
    store = CredentialStore(AppPaths(tmp_path))
    store.save('default', 'original-private-token', 'NAI')
    before = dict(vault.secrets)

    def fail_write(records):
        raise OSError('disk full')

    monkeypatch.setattr(store, '_write_index', fail_write)
    for operation in [lambda: store.save('default', 'replacement-private-token', 'NAI'),
                      lambda: store.save('barracks-' + 'a' * 32, 'new-private-token', 'New'),
                      lambda: store.delete('default')]:
        with pytest.raises(ValueError, match=STORAGE_ERROR):
            operation()
        assert vault.secrets == before
        assert store.restored['default']['token'] == 'original-private-token'
    assert CredentialStore(AppPaths(tmp_path)).restored['default']['token'] == 'original-private-token'


def test_invalid_index_is_not_overwritten(tmp_path, vault):
    store = CredentialStore(AppPaths(tmp_path))
    store.index.parent.mkdir(parents=True)
    store.index.write_text('{broken')
    fresh = CredentialStore(AppPaths(tmp_path))
    assert not fresh.status()['available'] and fresh.status()['error']
    with pytest.raises(ValueError, match=STORAGE_ERROR):
        fresh.save('default', 'new-private-token', 'NAI')
    assert fresh.index.read_text() == '{broken'


def test_http_persistence_contract_restore_and_no_credentials_in_responses(tmp_path, vault, monkeypatch):
    paths = AppPaths(tmp_path)
    server = create_http_server('127.0.0.1', 0, paths=paths, default_dry_run=True)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    base = 'http://127.0.0.1:' + str(server.server_port)

    def post(route, value, expected=200):
        request = urllib.request.Request(base + route, data=json.dumps(value).encode(),
                                         headers={'Content-Type': 'application/json'}, method='POST')
        try:
            response = urllib.request.urlopen(request)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            raw = response.read().decode()
            assert response.status == expected, raw
            assert 'private-token' not in raw
            return json.loads(raw)

    try:
        value = post('/api/setup/nai', {'token': 'primary-private-token', 'persist': True})
        assert value['credentials']['default_saved']
        vault.fail = True
        post('/api/setup/nai', {'token': 'changed-private-token', 'persist': True}, 400)
        assert os.environ['NAI_ACCESS_TOKEN'] == 'primary-private-token'
        vault.fail = False
        value = post('/api/setup/nai', {'use_current': True, 'persist': False})
        assert not value['credentials']['default_saved'] and value['configured']
        post('/api/setup/nai', {'use_current': True, 'persist': True})
        post('/api/barracks/accounts', {'name': 'Saved', 'token': 'saved-private-token', 'persist': True})
        post('/api/barracks/accounts', {'name': 'Temporary', 'token': 'temp-private-token'})
        for value in [{'token': 'primary-private-token', 'persist': 'false'},
                      {'use_current': 'true'}, {'token': 'primary-private-token', 'use_current': True}]:
            post('/api/setup/nai', value, 400)
        os.environ.pop('NAI_ACCESS_TOKEN')
        fresh = CredentialStore(paths)
        fresh.restore_default()
        assert os.environ['NAI_ACCESS_TOKEN'] == 'primary-private-token'
        assert len(Barracks(paths).snapshot()['accounts']) == 1
        post('/api/setup/nai', {'token': ''})
        assert 'NAI_ACCESS_TOKEN' not in os.environ
        assert not CredentialStore(paths).status()['default_saved']
        assert len(Barracks(paths).snapshot()['accounts']) == 1
    finally:
        server.shutdown()
        server.server_close()
        worker.join(5)


def test_persistence_mutations_blocked_during_barracks_batch(tmp_path, vault):
    b = Barracks(AppPaths(tmp_path))
    b.add_account({'name': 'First', 'token': 'first-private-token'})
    account = b.snapshot()['accounts'][0]['id']
    b.batch = {'status': 'running'}
    with pytest.raises(ValueError):
        b.set_storage({'id': account, 'persist': True})
    assert not vault.secrets

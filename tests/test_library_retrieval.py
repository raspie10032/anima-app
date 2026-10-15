"""Ordering boundaries, cross-connection cache freshness and worker lifecycle."""
import json
import threading
import time
from unittest.mock import Mock

import numpy as np
import pytest
from PIL import Image

from anima_app.config import AppPaths
from anima_app.gpu_work_lock import GPUWorkLock
from anima_app.library import Library
from anima_app.library_core import rank_cases
from anima_app.library_vrs import VRSAdapter, VRSIndexCancelled
from anima_app.library_vrs_cached import CachedVRSAdapter


@pytest.fixture
def cases(tmp_path):
    lib = Library(AppPaths(tmp_path))
    lib.vrs = Mock(contract='retrieval-test')
    ids = []
    for i, angle in enumerate((0, .1, .11, .12, .8)):
        path = tmp_path / f'{i}.png'
        Image.new('RGB', (32, 32), (i * 40, 80, 160)).save(path)
        identity = lib.ingest(path)[0]
        ids.append(identity)
        with lib.connect() as c:
            c.execute('INSERT INTO vectors VALUES(?,?,?)',
                      (identity, lib.vrs.contract, json.dumps([np.cos(angle), np.sin(angle)])))
    return lib, ids


def ids(result):
    return [item['id'] for item in result['items']]


def test_vrs_off_persists_preserves_data_and_keeps_cpu_search(cases):
    lib, items = cases
    baseline = ids(lib.search(identity=items[0], mode='vrs'))
    lib.feedback({'query_id': lib.search(identity=items[0], mode='vrs')['query_id'], 'id': items[1], 'visual': 1})
    with lib.connect() as c:
        before = {t: [tuple(r) for r in c.execute(f'SELECT * FROM {t}')] for t in ('assets', 'vectors', 'records', 'feedback')}
    assert lib.set_vrs_enabled(False) == {'enabled': False}
    lib.vrs.close.assert_called_once()
    for action in (lambda: lib.search(identity=items[0], mode='vrs'),
                   lambda: lib.start({'kind': 'vrs'}), lib.build_vrs, lib.prepare_vrs):
        with pytest.raises(ValueError, match='VRS가 꺼져'):
            action()
    assert lib.search(identity=items[0], mode='visual')['items']
    restored = Library(lib.paths)
    restored.vrs = lib.vrs
    assert restored.status()['vrs_enabled'] is False
    assert restored.status()['vrs_indexed'] == len(items)
    with restored.connect() as c:
        assert before == {t: [tuple(r) for r in c.execute(f'SELECT * FROM {t}')] for t in before}
    restored.set_vrs_enabled(True)
    assert ids(restored.search(identity=items[0], mode='vrs')) == baseline
    lib.vrs.encode.assert_not_called()


def test_toggle_cannot_race_search_or_preparation(cases, monkeypatch):
    lib, items = cases
    entered, release = threading.Event(), threading.Event()
    from anima_app import library_core
    original = library_core.rank_cases

    def blocked(*args):
        entered.set()
        assert release.wait(5)
        return original(*args)

    monkeypatch.setattr(library_core, 'rank_cases', blocked)
    with __import__('concurrent.futures', fromlist=['ThreadPoolExecutor']).ThreadPoolExecutor() as pool:
        running = pool.submit(lib.search, identity=items[0], mode='vrs')
        assert entered.wait(5)
        try:
            with pytest.raises(ValueError, match='작업이 끝난 후'):
                lib.set_vrs_enabled(False)
            assert lib.vrs_enabled
        finally:
            release.set()
        assert running.result(timeout=5)['items']
    with lib.generation_lock:
        with pytest.raises(ValueError, match='작업이 끝난 후'):
            lib.set_vrs_enabled(False)
    lib._progress(status='running', kind='vrs')
    with pytest.raises(ValueError, match='작업이 끝난 후'):
        lib.set_vrs_enabled(False)
    lib._progress(status='complete')
    lib.set_vrs_enabled(False)


def test_feedback_reorders_only_this_query_and_reset_restores(cases):
    lib, items = cases
    base = lib.search(identity=items[0], mode='vrs')
    other = ids(lib.search(identity=items[4], mode='vrs'))
    for _ in range(3):
        receipt = lib.feedback({'query_id':base['query_id'], 'id':items[3], 'visual':1})
        assert receipt['evidence']['decisions']['visual']['status'] == 'abstain'
        result = lib.search(identity=items[0], mode='vrs')
        assert ids(result)[0] == items[3]
        assert result['items'][0]['ranking_adjustment'] == .01
    assert ids(lib.search(identity=items[4], mode='vrs')) == other
    lib.feedback({'query_id':base['query_id'], 'id':items[3], 'visual':-1})
    assert ids(lib.search(identity=items[0], mode='vrs')).index(items[3]) > 0
    lib.feedback({'query_id':base['query_id'], 'id':items[3], 'visual':0, 'reuse':1})
    assert ids(lib.search(identity=items[0], mode='vrs')) == ids(base)
    lib.vrs.contract = 'different-encoder'
    with lib.connect() as c:
        c.execute("UPDATE vectors SET contract='different-encoder'")
    assert ids(lib.search(identity=items[0], mode='vrs')) == ids(base)


def test_pair_reversal_undo_and_restart(cases):
    lib, items = cases
    base = lib.search(identity=items[0], mode='vrs')
    pair = dict(query_id=base['query_id'], a=items[1], b=items[3])
    first = lib.compare({**pair, 'choice':'b'})
    assert ids(lib.search(identity=items[0], mode='vrs'))[0] == items[3]
    second = lib.compare({**pair, 'choice':'a'})
    assert ids(lib.search(identity=items[0], mode='vrs'))[0] == items[1]
    lib.undo_comparison(second)
    assert ids(lib.search(identity=items[0], mode='vrs'))[0] == items[3]
    restart = Library(lib.paths)
    restart.vrs = lib.vrs
    assert ids(restart.search(identity=items[0], mode='vrs'))[0] == items[3]
    lib.undo_comparison(first)
    assert ids(restart.search(identity=items[0], mode='vrs')) == ids(base)


def test_reuse_on_old_query_cannot_revive_an_old_similarity_vote(cases):
    lib, items = cases
    older = lib.search(identity=items[0], mode='vrs')
    lib.feedback({'query_id':older['query_id'], 'id':items[3], 'visual':1})
    newer = lib.search(identity=items[0], mode='vrs')
    lib.feedback({'query_id':newer['query_id'], 'id':items[3], 'visual':-1})
    before = lib.search(identity=items[0], mode='vrs')
    lib.feedback({'query_id':older['query_id'], 'id':items[3], 'reuse':1})
    after = lib.search(identity=items[0], mode='vrs')
    assert ids(before) == ids(after)
    item = next(r for r in after['items'] if r['id'] == items[3])
    assert item['ranking_adjustment'] < 0
    assert item['evidence']['decisions']['visual']['explicit_rating'] == -1
    assert item['evidence']['decisions']['reuse']['explicit_rating'] == 1


def test_matrix_cache_survives_queries_and_refreshes_external_writes(cases):
    lib, items = cases
    base = lib.search(identity=items[0], mode='vrs')
    cached = next(iter(lib._vector_cache.values()))[1]
    lib.search(identity=items[0], mode='vrs')
    lib.feedback({'query_id':base['query_id'], 'id':items[1], 'reuse':1})
    lib.search(identity=items[0], mode='vrs')
    assert next(iter(lib._vector_cache.values()))[1] is cached
    external = Library(lib.paths)
    with external.connect() as c:
        c.execute('UPDATE vectors SET vector=? WHERE asset_id=?', (json.dumps([1.,0.]), items[4]))
    assert ids(lib.search(identity=items[0], mode='vrs'))[0] == items[4]
    assert next(iter(lib._vector_cache.values()))[1] is not cached
    with external.connect() as c:
        c.execute('DELETE FROM vectors WHERE asset_id=?', (items[4],))
    result = lib.search(identity=items[0], mode='vrs')
    assert items[4] not in ids(result) and result['partial_index']


def test_diversity_uses_pixels_not_metadata_and_keeps_near_neighbors():
    angles = [0, .001, .002, .003, .15, .18, 1.5]
    matrix = np.array([[np.cos(a), np.sin(a)] for a in angles])
    rows = [{'id':str(i),'pixel_hash':str(i),'artist':'same'} for i in range(len(angles))]
    scores = matrix @ matrix[0]
    similar = rank_cases(rows,scores,matrix,'0',{},3,'similar')
    diverse = rank_cases(rows,scores,matrix,'0',{},3,'diverse')
    assert similar == [1,2,3]
    # Use a small angle fan in a higher-dimensional plane to verify MMR.
    matrix = np.array([[.98,.199,0], [.98,.198,.02], [.98,0,.199], [.5,0,.866]])
    matrix /= np.linalg.norm(matrix,axis=1,keepdims=True)
    rows = rows[:4]
    mixed = rank_cases(rows,matrix[:,0],matrix,'unseen',{},2,'diverse')
    assert 2 in mixed and 3 not in mixed
    for row in rows:
        row['artist'] = 'fake different metadata'
    assert mixed == rank_cases(rows,matrix[:,0],matrix,'unseen',{},2,'diverse')
    assert len(diverse) == 3 and 6 not in diverse


def test_cached_worker_reuse_idle_release_failure_and_contract(monkeypatch, tmp_path):
    adapter = CachedVRSAdapter(tmp_path, idle_seconds=.03)
    version = ['one']
    monkeypatch.setattr(VRSAdapter, 'contract', property(lambda self:version[0]))
    processes = []
    def fake_encode(self, paths, scratch, cancelled=lambda:False):
        if cancelled():
            raise VRSIndexCancelled()
        if self._worker_state is None:
            proc = Mock()
            proc.poll.return_value = None
            processes.append(proc)
            self._worker_state = (proc,None,None)
        return [[1.,0.]]
    monkeypatch.setattr(VRSAdapter, 'encode', fake_encode)
    finished = []
    monkeypatch.setattr(adapter, '_finish', lambda state:finished.append(state[0]))
    adapter.encode([],tmp_path)
    adapter.encode([],tmp_path)
    assert len(processes) == 1
    version[0] = 'two'
    adapter.encode([],tmp_path)
    assert len(processes) == 2 and len(finished) == 1
    with pytest.raises(VRSIndexCancelled):
        adapter.encode([],tmp_path,lambda:True)
    assert adapter._worker_state is None
    adapter.encode([],tmp_path)
    deadline = time.monotonic()+2
    while adapter._worker_state and time.monotonic()<deadline:
        time.sleep(.01)
    assert adapter._worker_state is None and len(finished) == 3


def test_gpu_lock_releases_idle_worker_only_after_successful_other_acquire():
    lock = GPUWorkLock()
    owner = object()
    release = Mock()
    lock.register_idle(owner,release)
    assert lock.acquire(blocking=False,owner=owner)
    assert not lock.acquire(blocking=False)
    release.assert_not_called()
    lock.release()
    with lock:
        assert lock.locked()
        release.assert_called_once()
    assert not lock.locked()


def test_cache_concurrent_queries(cases):
    lib, items = cases
    results, errors = [], []
    def run():
        try:
            results.append(ids(lib.search(identity=items[0],mode='vrs')))
        except Exception as exc:
            errors.append(exc)
    threads = [threading.Thread(target=run) for _ in range(6)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(5)
    assert not errors and len(results)==6
    assert all(result==results[0] for result in results)

"""Review regressions: image-only import, recoverable indexes and real evidence core."""
import threading
import time

import pytest
from PIL import Image
from PIL.PngImagePlugin import PngInfo

from anima_app.config import AppPaths
from anima_app.library import Library
from anima_app.library_vrs import VRSIndexCancelled
from anima_app.embedded_vrs import child_environment, contract_for


def picture(path, color='red', comment=None):
    info = PngInfo()
    if comment is not None:
        info.add_text('Comment', comment)
    Image.new('RGB', (64, 48), color).save(path, pnginfo=info)
    return path


class Encoder:
    contract = 'test-vrs'

    def encode(self, paths, scratch, cancelled=lambda: False):
        return [[1., .2] for _ in paths]


@pytest.fixture
def lib(tmp_path):
    result = Library(AppPaths(tmp_path / 'app'))
    result.vrs = Encoder()
    return result


@pytest.mark.parametrize('comment', [None, '{broken', '[]', 'null', '{"prompt":"artist:test", "steps":{}}'])
def test_caption_not_required_for_indexing(lib, tmp_path, comment):
    identity, _ = lib.ingest(picture(tmp_path / 'input.png', comment=comment))
    lib.build_vrs()
    assert lib.status()['vrs_indexed'] == 1
    assert lib.detail(identity)['records'][0]['metadata_status'] in ('available', 'unreadable', 'image_only')
    assert lib.status()['vrs_issues'] == {}


def test_missing_original_does_not_abort_and_restore_retries(lib, tmp_path):
    a, b = picture(tmp_path / 'a.png'), picture(tmp_path / 'b.png', 'blue')
    old = a.read_bytes()
    identities = [lib.ingest(p)[0] for p in (a,b)]
    a.unlink()
    lib.build_vrs()
    assert lib.status()['vrs_indexed'] == 1
    assert lib.status()['vrs_issues'] == {'missing_source': 1}
    # A third unseen picture searches the partial index without failing.
    results = lib.search(image=picture(tmp_path / 'query.png', 'green'), mode='vrs')
    assert results['partial_index'] and results['items'][0]['id'] == identities[1]
    a.write_bytes(old)
    lib.build_vrs()
    assert lib.status()['vrs_indexed'] == 2
    assert lib.status()['vrs_issues'] == {}


def test_pixel_group_retains_all_records_and_provenance(lib, tmp_path):
    a = lib.ingest(picture(tmp_path / 'a.png', comment='{"prompt":"artist:one"}'))[0]
    b = lib.ingest(picture(tmp_path / 'b.png', comment='{"prompt":"artist:two"}'))[0]
    assert a != b
    query = picture(tmp_path / 'query.png', 'blue')
    results = lib.search(image=query, mode='visual')
    assert len(results['items']) == 1
    item = results['items'][0]
    assert set(item['asset_ids']) == {a,b}
    assert {r['asset_id'] for r in item['records']} == {a,b}
    detail = lib.detail(item['id'], group=True)
    assert len(detail['sources']) == 2
    assert {r['request']['prompt'] for r in detail['records']} == {'artist:one','artist:two'}
    for record in detail['records']:
        assert record['id'] in {r['id'] for r in lib.detail(record['asset_id'])['records']}


def test_encoder_cancel_is_not_failure_and_lock_releases(lib, tmp_path):
    lib.ingest(picture(tmp_path / 'a.png'))
    entered = threading.Event()
    class Cancellable(Encoder):
        def encode(self, paths, scratch, cancelled=lambda: False):
            entered.set()
            while not cancelled():
                time.sleep(.01)
            raise VRSIndexCancelled()
    lib.vrs = Cancellable()
    lib.start({'kind':'vrs'})
    assert entered.wait(5)
    lib.cancel()
    deadline = time.monotonic() + 5
    while lib.job['status'] == 'running' and time.monotonic() < deadline:
        time.sleep(.01)
    assert lib.job['status'] == 'cancelled'
    assert lib.generation_lock.acquire(blocking=False)
    lib.generation_lock.release()
    assert lib.import_lock.acquire(blocking=False)
    lib.import_lock.release()


def test_committed_batches_survive_next_failure(lib, tmp_path):
    for i in range(10):
        lib.ingest(picture(tmp_path / f'{i}.png', color=(i*20,50,80)))
    calls = []
    class Failing(Encoder):
        def encode(self, paths, scratch, cancelled=lambda: False):
            calls.append(len(paths))
            if len(calls) == 2:
                raise ValueError('CUDA_OOM')
            return super().encode(paths, scratch)
    lib.vrs = Failing()
    with pytest.raises(ValueError, match='CUDA_OOM'):
        lib.build_vrs()
    assert calls == [8,2]
    assert lib.status()['vrs_indexed'] == 8
    lib.vrs = Encoder()
    lib.build_vrs()
    assert lib.status()['vrs_indexed'] == 10


def test_core_receipts_replay_latest_rating_without_duplicate_producers(lib, tmp_path):
    lib.ingest(picture(tmp_path / 'a.png'))
    query = picture(tmp_path / 'query.png', 'blue')
    for rating in [1,1,1,-1]:
        result = lib.search(image=query, mode='visual')
        feedback = lib.feedback({'query_id':result['query_id'], 'id':result['items'][0]['id'], 'visual':rating})
        decision = feedback['evidence']['decisions']['visual']
        assert decision['explicit_rating'] == rating
        assert decision['status'] == 'abstain'
    restarted = Library(lib.paths)
    again = restarted.search(image=query, mode='visual')['items'][0]['evidence']
    assert again['decisions']['visual']['explicit_rating'] == -1
    with lib.connect() as c:
        assert c.execute('SELECT count(*) FROM core_receipts').fetchone()[0] == 4


def test_worker_environment_and_contract_are_app_owned(monkeypatch, tmp_path):
    monkeypatch.setenv('NAI_ACCESS_TOKEN', 'secret-must-not-reach-encoder')
    monkeypatch.setenv('ANIMA_VRS_INT_ROOT', '/missing/sibling')
    monkeypatch.setenv('ANIMA_VRS_PYTHON', '/missing/python')
    monkeypatch.setenv('PYTHONPATH', '/untrusted')
    environment = child_environment(tmp_path)
    assert 'NAI_ACCESS_TOKEN' not in environment
    assert 'ANIMA_VRS_INT_ROOT' not in environment
    assert '/untrusted' not in environment['PYTHONPATH']
    assert environment['HF_HUB_OFFLINE'] == '1'
    assert contract_for(tmp_path).startswith('anima-vrs-gemma4-v2:')


def test_clean_metadata_keeps_unicode_but_removes_credentials():
    from anima_app.library_metadata import request_snapshot
    data = request_snapshot({'prompt':'e\u0301\x00, 작가', 'nai_token':'private', 'steps':float('nan')})
    assert data == {'prompt':'é, 작가','steps':None}

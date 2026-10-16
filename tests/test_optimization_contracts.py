"""Observable contracts for GPU routing, queue responses and PNG preservation."""
import gzip
import json
import struct
import threading
from urllib.request import Request, urlopen

import pytest
from PIL import Image, PngImagePlugin

from anima_app import server
from anima_app.config import AppPaths
from anima_app.png_metadata import embed_png_parameters
from anima_app.workflows import requires_gpu


@pytest.mark.parametrize('payload,expected', [
    ({'provider': 'novelai'}, False),
    ({'provider': 'novelai', 'workflow': {'version': 1, 'steps': []}}, False),
    ({'provider': 'novelai', 'operation': 'img2img'}, True),
    ({'provider': 'novelai', 'operation': 'detail'}, True),
    ({'provider': 'novelai', 'nai_detailer': {'enabled': True}}, True),
    ({'provider': 'local'}, True),
    ({'provider': 'novelai', 'workflow': {'version': 1, 'steps': [{'provider': 'local', 'operation': 'detail'}]}}, True),
])
def test_gpu_work_classification(payload, expected):
    assert requires_gpu(payload) is expected


def test_remote_queue_does_not_acquire_busy_gpu(tmp_path, monkeypatch):
    monkeypatch.setattr(server.JobQueue, '_worker_loop', lambda self: None)
    monkeypatch.setattr(server, 'handle_generate', lambda *a, **kw: (200, {'status': 'generated'}))
    lock = threading.Lock()
    queue = server.JobQueue(paths=AppPaths(tmp_path), renderer=None, default_dry_run=True,
                            progress_store=server.ProgressStore(), generation_lock=lock)
    try:
        code, response = queue.enqueue({'request': {'provider': 'novelai', 'prompt': 'test', 'dry_run': True}})
        assert code == 202
        lock.acquire()
        worker = threading.Thread(target=queue._run_job, args=(response['jobs'][0],), daemon=True)
        worker.start()
        worker.join(3)
        assert not worker.is_alive(), 'Remote generation must complete while VRS owns the GPU'
        assert queue.list()['items'][0]['status'] == 'completed'
    finally:
        if lock.locked():
            lock.release()
        queue.close()


def test_compact_queue_retains_workflow_but_no_prompt_or_results(tmp_path, monkeypatch):
    monkeypatch.setattr(server.JobQueue, '_worker_loop', lambda self: None)
    queue = server.JobQueue(paths=AppPaths(tmp_path), renderer=None, default_dry_run=True,
                            progress_store=server.ProgressStore(), generation_lock=threading.Lock())
    try:
        queue._jobs['fixture'] = dict(id='fixture', status='completed', request={
            'provider': 'novelai', 'prompt': 'private prompt' * 100,
            'workflow': {'version': 1, 'steps': [{'provider': 'local', 'operation': 'detail',
                'request': {'prompt': 'private stage', 'steps': 10, 'face_detailer': {'enabled': True}}}]}},
            result={'prompt': 'private output'})
        queue._order = ['fixture']
        compact = queue.list(compact=True)['items'][0]
        assert compact['has_result'] and 'result' not in compact
        assert 'private' not in json.dumps(compact)
        assert compact['request']['workflow']['steps'][0]['request']['steps'] == 10
        assert queue.list()['items'][0]['result']['prompt'] == 'private output'
    finally:
        queue.close()


def chunks(path):
    data = path.read_bytes()
    offset, result = 8, []
    while offset < len(data):
        length, kind = struct.unpack('>I4s', data[offset:offset+8])
        result.append((kind, data[offset:offset+length+12]))
        offset += length+12
    return result


def test_png_text_update_preserves_compressed_pixels_alpha_and_other_metadata(tmp_path):
    path = tmp_path/'image.png'
    info = PngImagePlugin.PngInfo()
    info.add_text('Comment', 'source metadata')
    info.add_text('parameters', 'old')
    Image.new('RGBA', (80, 80), (123, 14, 28, 127)).save(path, pnginfo=info)
    before = chunks(path)
    embed_png_parameters(path, '새 프롬프트, (style:1.2)')
    assert [c for c in chunks(path) if c[0] == b'IDAT'] == [c for c in before if c[0] == b'IDAT']
    with Image.open(path) as image:
        assert image.mode == 'RGBA' and image.getpixel((0, 0))[-1] == 127
        assert image.info['parameters'] == '새 프롬프트, (style:1.2)'
        assert image.info['Comment'] == 'source metadata'
    assert sum(c[1][8:].startswith(b'parameters\0') for c in chunks(path)) == 1


def test_static_gzip_etag_and_api_remain_uncached(tmp_path):
    http = server.create_http_server('127.0.0.1', 0, paths=AppPaths(tmp_path), default_dry_run=True)
    threading.Thread(target=http.serve_forever, daemon=True).start()
    url = 'http://127.0.0.1:' + str(http.server_port)
    try:
        with urlopen(url+'/app.js') as response:
            plain = response.read()
            assert response.headers['Cache-Control'] == 'private, no-cache'
        with urlopen(Request(url+'/app.js', headers={'Accept-Encoding': 'gzip'})) as response:
            assert gzip.decompress(response.read()) == plain
            etag = response.headers['ETag']
        from urllib.error import HTTPError
        with pytest.raises(HTTPError) as caught:
            urlopen(Request(url+'/app.js', headers={'Accept-Encoding': 'gzip', 'If-None-Match': etag}))
        assert caught.value.code == 304
        with urlopen(Request(url+'/app.js', headers={'Accept-Encoding': 'gzip;q=0'})) as response:
            assert not response.headers['Content-Encoding'] and response.read() == plain
        with urlopen(url+'/api/jobs?view=summary') as response:
            assert not response.headers['ETag']
    finally:
        http.shutdown()
        http.server_close()

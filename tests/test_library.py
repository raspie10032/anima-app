"""Library evidence separation, import integrity and HTTP boundary regressions."""
import hashlib
import io
import json
from pathlib import Path
import threading
import time
from urllib.request import Request, urlopen
from urllib.error import HTTPError

from PIL import Image, ImageDraw
from PIL.PngImagePlugin import PngInfo
import pytest

from anima_app.config import AppPaths
from anima_app.library import Library
from anima_app.library_metadata import artist_combo, request_snapshot
from anima_app.server import create_http_server


@pytest.fixture
def library(tmp_path):
    return Library(AppPaths(project_root=tmp_path / 'app'))


def picture(path, color='red', prompt=None, shift=0):
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new('RGB', (96, 80), color)
    ImageDraw.Draw(image).rectangle((10 + shift, 10, 35 + shift, 60), fill='white')
    info = PngInfo()
    if prompt is not None:
        info.add_text('parameters', prompt + '\nNegative prompt: blur\nSteps: 20, Seed: 15')
    image.save(path, pnginfo=info)
    return path


def wait(library):
    deadline = time.monotonic() + 10
    while library.import_lock.locked() and time.monotonic() < deadline:
        time.sleep(.02)
    assert not library.import_lock.locked()
    return library.status()['job']


def test_pixel_query_never_uses_embedded_prompt_and_excludes_copies(library, tmp_path):
    query = picture(tmp_path / 'one.png', prompt='artist:first')
    duplicate = picture(tmp_path / 'copy.png', prompt='artist:other')
    near = picture(tmp_path / 'near.png', prompt='artist:near', shift=2)
    far = picture(tmp_path / 'far.png', 'blue', 'artist:first')
    before = {p: p.read_bytes() for p in [query, duplicate, near, far]}
    identities = [library.ingest(p)[0] for p in before]
    result = library.search(image=query)
    other_result = library.search(image=duplicate)
    assert [r['id'] for r in result['items']] == [r['id'] for r in other_result['items']]
    assert result['items'][0]['id'] == identities[2]
    assert not {identities[0], identities[1]} & {r['id'] for r in result['items']}
    assert library.status()['distinct_pixels'] == 3
    assert len(library.detail(identities[0])['records']) == 1
    assert all(p.read_bytes() == content for p, content in before.items())


def test_same_file_dedup_preserves_distinct_records(library, tmp_path):
    original = picture(tmp_path / 'original.png')
    copied = tmp_path / 'copied.png'
    copied.write_bytes(original.read_bytes())
    identity, _ = library.ingest(original, {'provider':'local','prompt':'artist:first','seed':1})
    assert library.ingest(copied)[0] == identity
    library.ingest(original, {'provider':'local','prompt':'artist:second','seed':2})
    detail = library.detail(identity)
    assert len(detail['records']) == 3
    assert len(detail['sources']) == 2
    assert library.status()['items'] == 1
    assert library.ingest(original)[1] == 'unchanged'


def test_import_preserves_post_provenance_and_separates_model_context(library, tmp_path):
    folder = tmp_path / 'post'
    original = picture(folder / 'one.png')
    (folder / 'source.json').write_text(json.dumps({'post': 'https://arca.live/b/aiart/example'}))
    identity, _ = library.ingest(original, {'provider': 'novelai', 'prompt': 'artist:one', 'nai_model': 'a'})
    library.ingest(original, {'provider': 'novelai', 'prompt': 'artist:one', 'nai_model': 'b'})
    assert library.detail(identity)['sources'][0]['source_url'] == 'https://arca.live/b/aiart/example'
    assert library.status()['combinations'] == 2
    assert library.status()['artist_sequences'] == 1
    other = picture(folder / 'two.png', 'blue')
    (folder / 'source.json').write_text(json.dumps({'post': 'javascript:alert(1)'}))
    identity, _ = library.ingest(other)
    assert library.detail(identity)['sources'][0]['source_url'] == ''


def test_single_and_weighted_artist_combinations_and_context():
    combo = artist_combo({'provider':'novelai','nai_model':'model-a','prompt':'1.2::artist:one, artist:two::, 1girl, -0.4::artist:three::'})
    assert [r['tag'] for r in combo['artists']] == ['one','two','three']
    assert [r['weight'] for r in combo['artists']] == pytest.approx([1.2,1.2,-.4])
    assert artist_combo({'prompt':'artist:one'})['key']
    assert not artist_combo({'prompt':'one, two, beautiful'})['key']
    a = {'provider':'novelai','prompt':'artist:one','nai_model':'model-a'}
    assert artist_combo(a)['key'] != artist_combo({**a, 'nai_model':'model-b'})['key']
    assert artist_combo({'prompt':'artist:one, artist:two'})['key'] != artist_combo({'prompt':'artist:two, artist:one'})['key']


def test_manifest_snapshot_keeps_conditions_but_not_credentials():
    result = request_snapshot({'provider':'novelai','prompt':'artist:one','seed':3,'nai_model':'a',
        'nai_characters':[{'prompt':'blue jacket','negative_prompt':'hat'}],
        'nai_access_token':'secret','novelai':{'effective':{'nai_model':'a'},'api_key':'secret'},
        'upscale':{'enabled':True},'unrelated':'dropped'})
    assert 'secret' not in json.dumps(result)
    assert result['nai_characters'][0]['prompt'] == 'blue jacket'
    assert result['upscale']['enabled']
    assert 'unrelated' not in result


def test_novelai_png_metadata_is_usable(library, tmp_path):
    path = tmp_path / 'novelai.png'
    info = PngInfo()
    info.add_text('Software', 'NovelAI')
    info.add_text('Source', 'NovelAI Diffusion V5 70AB5786')
    info.add_text('Comment', json.dumps({'prompt':'artist:one, blue coat','uc':'blur','seed':123,'width':96,'height':80}))
    Image.new('RGB',(96,80),'red').save(path,pnginfo=info)
    identity, _ = library.ingest(path)
    record = library.detail(identity)['records'][0]
    assert record['request']['provider'] == 'novelai'
    assert record['request']['seed'] == 123
    assert record['combo']['artists'][0]['tag'] == 'one'


def test_annotations_search_and_feedback_do_not_rewrite_evidence(library, tmp_path):
    a = library.ingest(picture(tmp_path / 'a.png', prompt='artist:one'))[0]
    b = library.ingest(picture(tmp_path / 'b.png', 'blue', 'artist:two'))[0]
    result = library.search(identity=a)
    before = library.detail(b)['records']
    library.annotate({'id':b,'tags':'푸른색 exact_100%','collection':'봄','note':'<script>x</script>','favorite':True})
    assert library.browse('푸른색 exact_100%', favorite=True)['total'] == 1
    assert library.browse('exact_10%', favorite=True)['total'] == 0
    assert library.browse(combo=before[0]['combo']['key'])['total'] == 1
    assert library.feedback({'query_id':result['query_id'],'id':b,'visual':1})['training'] is False
    library.feedback({'query_id':result['query_id'],'id':b,'reuse':-1})
    with library.connect() as c:
        assert tuple(c.execute('select visual,reuse from feedback').fetchone()) == (1,-1)
    with pytest.raises(ValueError):
        library.feedback({'query_id':result['query_id'],'id':a,'visual':1})
    assert library.detail(b)['records'] == before


def test_manifest_sync_is_incremental_preserves_history_and_rejects_escape(library, tmp_path, monkeypatch):
    image = picture(library.paths.image_root / 'result.png')
    library.paths.manifest_root.mkdir(parents=True)
    manifest = library.paths.manifest_root / 'result.json'
    data = {'output_path':str(image),'provider':'local','prompt':'artist:one','seed':12}
    manifest.write_text(json.dumps(data))
    assert library.sync() == 1
    assert library.sync() == 0
    data['seed']=124
    manifest.write_text(json.dumps(data))
    assert library.sync() == 1
    identity = hashlib.sha256(image.read_bytes()).hexdigest()
    assert len(library.detail(identity)['records']) == 2
    outside = picture(tmp_path / 'outside.png','green')
    data['output_path'] = str(outside)
    manifest.write_text(json.dumps(data))
    assert library.sync() == 0
    assert library.status()['items'] == 1


def test_unlimited_library_invalid_images_and_unchanged_sources(library, tmp_path):
    with library.connect() as c:
        c.executemany('INSERT INTO assets(id,pixel_hash,width,height,vector,created) VALUES(?,?,?,?,?,?)',
                      [(f'{i:064x}', f'pixel-{i}', 96, 80, '[]', 0) for i in range(2000)])
    p = picture(tmp_path / 'a.png')
    library.ingest(p)
    library.ingest(picture(tmp_path / 'b.png','blue'))
    library.ingest(picture(tmp_path / 'c.png','green'))
    assert library.ingest(p)[1] == 'unchanged'
    broken = tmp_path / 'bad.png'
    broken.write_text('not an image')
    with pytest.raises(ValueError):
        library.ingest(broken)
    assert library.status()['items'] == 2003
    assert library.status()['capacity'] is None
    page = library.browse(offset=2001)
    assert page['total'] == 2003 and len(page['items']) == 2
    assert library.browse(offset=10**30)['items'] == []


def test_import_round_robin_and_cancellation(library, tmp_path):
    roots = [tmp_path / 'folder-a', tmp_path / 'folder-b']
    for folder in roots:
        for i in range(3):
            picture(folder / f'{i}.png', shift=i+(10 if folder==roots[1] else 0))
    library.start({'folders':list(map(str,roots)), 'limit':4})
    assert wait(library)['status'] == 'complete'
    with library.connect() as c:
        parents = [Path(r[0]).parent for r in c.execute('select path from sources')]
    assert parents.count(roots[0]) == parents.count(roots[1]) == 2
    library.start({'folders':list(map(str,roots))})
    result = wait(library)
    assert result['status'] == 'complete' and result['processed'] == 6
    assert result['limit'] is None and library.status()['items'] == 6
    library.cancel()
    assert library.cancelled.is_set()


def test_vrs_contract_resume_and_generation_exclusion(library, tmp_path):
    identities = [library.ingest(picture(tmp_path/f'{i}.png',shift=i))[0] for i in range(3)]
    calls = []
    class Encoder:
        contract = 'fake-vrs-v1'
        def encode(self,paths,scratch,cancelled=lambda:False):
            calls.append(paths)
            return [[1.,float(i)] for i,_ in enumerate(paths)]
    library.vrs = Encoder()
    with pytest.raises(ValueError, match='색인'):
        library.search(identity=identities[0],mode='vrs')
    library.generation_lock.acquire()
    try:
        with pytest.raises(ValueError, match='진행 중'):
            library.build_vrs()
    finally:
        library.generation_lock.release()
    library.build_vrs()
    library.build_vrs()
    assert len(calls) == 1
    assert len(library.search(identity=identities[0],mode='vrs')['items']) == 2
    library.vrs.contract = 'changed'
    assert library.status()['vrs_indexed'] == 0
    with pytest.raises(ValueError, match='색인'):
        library.search(identity=identities[0],mode='vrs')


@pytest.mark.parametrize('identity',[None,[],{},'../outside','abcd',42])
def test_bad_ids_fail_cleanly(library,identity):
    with pytest.raises(ValueError):
        library.detail(identity)


def test_http_origin_upload_query_and_traversal(library,tmp_path):
    library.ingest(picture(tmp_path/'red.png'))
    library.ingest(picture(tmp_path/'blue.png','blue'))
    server = create_http_server('127.0.0.1',0,paths=library.paths)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    base=f'http://127.0.0.1:{server.server_address[1]}'
    try:
        def post(route,content,ctype='application/json',origin=None):
            headers={'Content-Type':ctype}
            if origin:
                headers['Origin']=origin
            return urlopen(Request(base+route,data=content,headers=headers),timeout=10)
        with pytest.raises(HTTPError) as error:
            post('/api/library/import',b'{}',origin='https://outside.example')
        assert error.value.code == 403
        with post('/api/library/query-image',(tmp_path/'red.png').read_bytes(),'image/png') as response:
            assert len(json.load(response)['items']) == 1
        with pytest.raises(HTTPError) as error:
            urlopen(base+'/api/library/thumbnail/..%2Foutside')
        assert error.value.code == 400
        with pytest.raises(HTTPError) as error:
            post('/api/library/annotate',b'{"id":[]}')
        assert error.value.code == 400
        assert not list((library.root/'scratch').glob('.anima-upload-*'))
    finally:
        server.shutdown()
        server.server_close()


def test_comparisons_are_query_scoped_reversible_and_separate_from_feedback(library, tmp_path):
    identities = [library.ingest(picture(tmp_path / f'{i}.png', color))[0]
                  for i, color in enumerate(['red', 'green', 'blue'])]
    query = library.search(identity=identities[0])
    payload = {'query_id': query['query_id'], 'a': identities[1], 'b': identities[2], 'choice': 'a'}
    for choice in ('a', 'b', 'both', 'neither', 'skip'):
        saved = library.compare({**payload, 'choice': choice})
        assert saved['training'] is False
    reopened = Library(library.paths)
    reopened.undo_comparison({'id': saved['id']})
    reopened.undo_comparison({'id': saved['id']})
    with reopened.connect() as connection:
        assert connection.execute('SELECT COUNT(*) FROM comparisons WHERE undone=0').fetchone()[0] == 4
        assert connection.execute('SELECT COUNT(*) FROM feedback').fetchone()[0] == 0
    for invalid in ({'a': identities[0]}, {'a': identities[2]}, {'query_id': '0' * 32},
                    {'choice': 'like'}, {'a': '../outside'}, {'query_id': []}):
        with pytest.raises(ValueError):
            reopened.compare({**payload, **invalid})
    with pytest.raises(ValueError):
        reopened.undo_comparison({'id': '0' * 32})


def test_large_preview_is_bounded_metadata_free_and_checks_source(library, tmp_path):
    path = tmp_path / 'large.png'
    metadata = PngInfo()
    metadata.add_text('parameters', 'private prompt marker')
    Image.new('RGB', (2400, 1800), 'red').save(path, pnginfo=metadata)
    original = path.read_bytes()
    identity = library.ingest(path)[0]
    result = library.preview(identity)
    assert b'private prompt marker' not in result
    with Image.open(io.BytesIO(result)) as image:
        assert image.size == (1600, 1200)
        assert image.format == 'JPEG'
        assert not image.getexif()
    assert path.read_bytes() == original
    path.write_bytes(b'replaced')
    with pytest.raises(ValueError, match='원본 파일'):
        library.preview(identity)
    with pytest.raises(ValueError):
        library.preview('../outside')

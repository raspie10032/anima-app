import json

import pytest

from anima_app.artist_catalog import catalog_path, load_catalog, mark_bare_artists
from anima_app.config import AppPaths
from anima_app.prompt_routing import route_request, route_text


NAMES = {name: name for name in ['alpha', 'tianliang_duohe_fangdongye', 'alt_(ctrldel)']}


@pytest.mark.parametrize('text, expected', [
    ('alpha, portrait', 'artist:alpha, portrait'),
    ('tianliang duohe fangdongye, blue eyes', 'artist:tianliang duohe fangdongye, blue eyes'),
    ('artist:alpha, @alpha, artist:unknown', 'artist:alpha, @alpha, artist:unknown'),
    ('alpha person, xalpha, unknown, portrait', 'alpha person, xalpha, unknown, portrait'),
    (r'(alpha, alt \(ctrldel\):0.85)', r'(artist:alpha, artist:alt \(ctrldel\):0.85)'),
    ('0.9::alpha, tianliang_duohe_fangdongye ::, portrait', '0.9::artist:alpha, artist:tianliang_duohe_fangdongye ::, portrait'),
    ('{{alpha}}, [alpha], (alpha:1.2)', '{{artist:alpha}}, [artist:alpha], (artist:alpha:1.2)'),
])
def test_bare_whole_tags_only_preserve_weights_and_order(text, expected):
    converted, matches = mark_bare_artists(text, NAMES)
    assert converted == expected
    assert len(matches) == expected.count('artist:') - text.count('artist:')


def test_snapshot_validates_category_and_never_requires_network(tmp_path, monkeypatch):
    paths = AppPaths(tmp_path)
    destination = catalog_path(paths)
    destination.parent.mkdir(parents=True)
    destination.write_text(json.dumps({'version':1, 'tags':[
        {'name':'alpha','category':1}, {'name':'portrait','category':0},
        {'name':'retired','category':1,'is_deprecated':True}]}))
    monkeypatch.setattr('urllib.request.urlopen', lambda *a, **kw: pytest.fail('generation must remain offline'))
    payload = {'provider':'novelai','prompt':'(alpha:0.85), artist:unknown, portrait','prompt_routing':{'source':'auto'}}
    result, receipt = route_request(payload, paths=paths)
    assert result['prompt'] == '0.85::artist:alpha ::, artist:unknown, portrait'
    assert receipt['fields'][0]['recognized_artists'] == [{'input':'alpha','tag':'alpha'}]
    assert receipt['artist_catalog']['count'] == 1
    assert len(receipt['artist_catalog']['sha256']) == 64
    local, _ = route_request({**payload, 'provider':'local'}, paths=paths)
    assert local['prompt'] == '(@alpha:0.85), @unknown, portrait'
    native, _ = route_request({**payload, 'prompt_routing':{'source':'native'}}, paths=paths)
    assert native['prompt'] == payload['prompt']
    destination.write_text('broken json')
    assert load_catalog(paths)['count'] == 0
    assert route_text('(alpha:0.85)', 'auto', 'comfyui', catalog=load_catalog(paths))[0] == '(alpha:0.85)'

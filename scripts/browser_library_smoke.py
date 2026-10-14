"""Local library UI acceptance with synthetic images and no generation requests."""
import argparse
import json
import re
import tempfile
import threading
from pathlib import Path
from urllib.parse import urlparse

from PIL import Image, ImageDraw
from playwright.sync_api import expect, sync_playwright

from anima_app.config import AppPaths
from anima_app.library import Library
from anima_app.server import create_http_server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=Path('outputs/library-browser'))
    output = parser.parse_args().output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    errors, generation, external = [], [], []
    with tempfile.TemporaryDirectory(prefix='anima-library-browser-') as temporary:
        root = Path(temporary)
        library = Library(AppPaths(root))
        ids = []
        for i, (color, artist) in enumerate([('#c68b7a', '1.2::artist:demo_a::, artist:demo_b'),
                                            ('#bf8b80', 'artist:demo_a'), ('#688ba0', 'artist:demo_c')]):
            path = root / f'sample-{i}.png'
            im = Image.new('RGB', (240, 300), color)
            draw = ImageDraw.Draw(im)
            draw.ellipse((50 + i * 7, 40, 190, 180), fill='#ffe6ce')
            draw.rectangle((70, 175, 170, 280), fill='#415e73')
            im.save(path)
            ids.append(library.ingest(path, {'provider': 'novelai', 'prompt': artist + ', portrait, blue coat',
                'negative_prompt': 'blur', 'nai_model': 'nai-diffusion-4-5-full', 'seed': 99 + i,
                'width': 832, 'height': 1216, 'steps': 28, 'cfg': 5})[0])
        server = create_http_server('127.0.0.1', 0, paths=library.paths, default_dry_run=True)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        address = f'http://127.0.0.1:{server.server_address[1]}'
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                page = browser.new_page(locale="ko-KR", viewport={'width': 1550, 'height': 1050})
                page.on('pageerror', lambda e: errors.append(str(e)))
                def route(request):
                    url = urlparse(request.request.url)
                    if url.hostname != '127.0.0.1':
                        external.append(request.request.url)
                        request.abort()
                    elif request.request.method == 'POST' and url.path in ('/api/jobs', '/api/generate'):
                        generation.append(url.path)
                        request.abort()
                    else:
                        request.continue_()
                page.route('**/*', route)
                page.goto(address, wait_until='networkidle')
                page.locator('[name="prompt"]').fill('existing scene')
                page.locator('#open-library').click()
                dialog = page.locator('#library-dialog')
                expect(dialog.locator('.lib-card')).to_have_count(3)
                def select(identity):
                    dialog.locator(f'.lib-card[data-id="{identity}"] .lib-select').click()
                    expect(dialog.get_by_label('기록된 프롬프트')).to_be_visible()

                select(ids[0])
                dialog.get_by_role('button', name='작가 태그만 덧붙이기', exact=True).click()
                expect(dialog).to_be_visible()
                expect(dialog.get_by_label('작업 프롬프트')).to_have_value(re.compile(r'existing scene, .*demo_a.*demo_b'))
                prompt = dialog.get_by_label('작업 프롬프트').input_value()
                assert prompt.startswith('existing scene, ') and 'demo_a' in prompt and 'demo_b' in prompt
                assert 'blue coat' not in prompt
                expect(page.locator('[name="prompt"]')).to_have_value('existing scene')
                dialog.get_by_role('button', name='가져오기 되돌리기', exact=True).click()
                expect(dialog.get_by_label('작업 프롬프트')).to_have_value('existing scene')
                dialog.get_by_role('button', name='작가 태그만 덧붙이기', exact=True).click()
                expect(dialog.get_by_label('작업 프롬프트')).to_have_value(re.compile(r'.*demo_a.*'))
                dialog.get_by_label('작업 프롬프트').fill('hand edited draft')
                dialog.locator('#library-tab-discover').click()
                dialog.get_by_role('button', name='생성 화면으로', exact=True).click()
                page.locator('#open-library').click()
                dialog.locator('#library-tab-compose').click()
                expect(dialog.get_by_label('작업 프롬프트')).to_have_value('hand edited draft')
                dialog.get_by_role('button', name='프롬프트 가져오기', exact=True).click()
                expect(dialog.get_by_label('작업 네거티브')).to_have_value('blur')
                dialog.get_by_role('button', name='가져오기 되돌리기', exact=True).click()
                expect(dialog.get_by_label('작업 프롬프트')).to_have_value('hand edited draft')
                dialog.get_by_role('button', name='프롬프트 가져오기', exact=True).click()
                dialog.get_by_role('button', name='생성 화면에 적용', exact=True).click()
                expect(page.locator('[name="prompt"]')).to_have_value('1.2::artist:demo_a::, artist:demo_b, portrait, blue coat')
                expect(page.locator('#provider-select')).to_have_value('local')
                page.locator('#open-library').click()
                dialog.get_by_role('button', name='조건까지 가져오기', exact=True).click()
                dialog.get_by_role('button', name='생성 화면에 적용', exact=True).click()
                expect(page.locator('#provider-select')).to_have_value('novelai')
                expect(page.locator('[name="seed"]')).to_have_value('99')
                expect(page.locator('#nai-model')).to_have_value('nai-diffusion-4-5-full')
                page.locator('#open-library').click()
                dialog.get_by_role('button', name='선택한 사례 크게 보기', exact=True).click()
                expect(page.locator('#library-zoom')).to_be_visible()
                page.keyboard.press('Escape')
                expect(dialog).to_be_visible()
                expect(page.locator('#library-zoom')).not_to_be_visible()
                dialog.get_by_label('비슷한 사례를 찾을 이미지').set_input_files(str(root / 'sample-0.png'))
                expect(dialog.locator('.lib-card')).to_have_count(2)
                assert not dialog.locator(f'.lib-card[data-id="{ids[0]}"]').count()
                expect(dialog.locator('.lib-ref-media img')).to_be_visible()
                dialog.locator('.lib-combos summary').click()
                dialog.locator('.lib-combos button').first.click()
                expect(dialog.locator('.lib-card')).to_have_count(1)
                dialog.get_by_role('button', name='유사사례로 돌아가기', exact=True).click()
                expect(dialog.locator('.lib-card')).to_have_count(2)
                dialog.locator('.lib-card .lib-select').first.click()
                dialog.get_by_role('button', name='닮았음', exact=True).click()
                expect(dialog.get_by_role('status')).to_contain_text('평가를 저장')
                dialog.get_by_role('button', name='조건을 다시 쓰고 싶음', exact=True).click()
                expect(dialog.get_by_role('status')).to_contain_text('평가를 저장')
                dialog.locator('#library-detail summary').filter(has_text='태그 · 컬렉션 · 메모').click()
                dialog.get_by_label('태그', exact=True).fill('fixture-test')
                dialog.get_by_label('컬렉션', exact=True).fill('browser-fixture')
                dialog.get_by_role('button', name='정리 내용 저장', exact=True).click()
                expect(dialog.get_by_role('status')).to_contain_text('저장')
                dialog.get_by_role('button', name='☆ 즐겨찾기', exact=True).click()
                expect(dialog.get_by_role('button', name='★ 즐겨찾기 해제', exact=True)).to_be_visible()
                dialog.locator('.lib-card input').nth(0).check()
                dialog.locator('.lib-card input').nth(1).check()
                dialog.locator('#library-tab-compare').click()
                page.wait_for_function("Array.from(document.querySelectorAll('.lib-pair img')).every(i => i.complete && i.naturalWidth > 0)")
                page.screenshot(path=str(output / 'compare.png'))
                dialog.get_by_role('button', name='A가 더 닮음', exact=True).click()
                expect(dialog.get_by_role('status')).to_contain_text('비교 판단을 저장')
                dialog.get_by_role('button', name='마지막 판단 취소', exact=True).click()
                expect(dialog.get_by_role('status')).to_contain_text('취소')
                dialog.get_by_role('button', name='둘 다 비슷함', exact=True).click()
                expect(dialog.get_by_role('status')).to_contain_text('비교 판단을 저장')
                with library.connect() as connection:
                    feedback = connection.execute('SELECT visual,reuse FROM feedback').fetchone()
                    assert tuple(feedback) == (1, 1)
                    assert [tuple(r) for r in connection.execute('SELECT choice,undone FROM comparisons ORDER BY created')] == [('a', 1), ('both', 0)]
                dialog.locator('#library-tab-discover').click()
                for width in (1920, 1280, 900, 390):
                    page.set_viewport_size({'width': width, 'height': 1000})
                    assert dialog.evaluate('(e) => e.scrollWidth <= e.clientWidth'), width
                    for stage in ('discover', 'compare', 'compose'):
                        dialog.locator('#library-tab-' + stage).click()
                        assert dialog.locator('.lib-layout').evaluate('(e) => e.scrollWidth <= e.clientWidth'), (width, stage)
                    dialog.locator('#library-tab-discover').click()
                    page.screenshot(path=str(output / f'library-{width}.png'))
                page.set_viewport_size({'width': 1550, 'height': 1050})
                dialog.get_by_label('라이브러리 검색').fill('fixture-test')
                dialog.get_by_role('button', name='검색', exact=True).click()
                expect(dialog.locator('.lib-card')).to_have_count(1)
                # A failed upload leaves the successful reference and results intact.
                previous_ref = dialog.locator('.lib-ref-media img').get_attribute('src')
                dialog.get_by_label('비슷한 사례를 찾을 이미지').set_input_files({'name': 'broken.png', 'mimeType': 'image/png', 'buffer': b'not an image'})
                expect(dialog.get_by_role('status')).to_contain_text('이미지를 읽을 수 없습니다')
                expect(dialog.locator('.lib-card')).to_have_count(1)
                assert dialog.locator('.lib-ref-media img').get_attribute('src') == previous_ref
                # Later searches must win even when an earlier response arrives last.
                delayed = []
                def delay_old_query(route):
                    if 'slow-race' in route.request.url:
                        delayed.append(route)
                    else:
                        route.fallback()
                page.route('**/api/library/items?**', delay_old_query)
                dialog.get_by_label('라이브러리 검색').fill('slow-race')
                dialog.get_by_role('button', name='검색', exact=True).click()
                page.wait_for_timeout(100)
                assert delayed
                dialog.get_by_label('라이브러리 검색').fill('no-such-result')
                dialog.get_by_role('button', name='검색', exact=True).click()
                expect(dialog.locator('.lib-card')).to_have_count(0)
                delayed[0].fulfill(json=library.browse())
                page.wait_for_timeout(100)
                expect(dialog.locator('.lib-card')).to_have_count(0)
                page.unroute('**/api/library/items?**', delay_old_query)
                # Paging loads the next 48-item window without repeating or dropping assets.
                for i in range(50):
                    path = root / f'page-{i}.png'
                    Image.new('RGB', (30, 30), (i, 120, 180)).save(path)
                    library.ingest(path, {'provider': 'local', 'prompt': f'paging {i}'})
                dialog.get_by_role('button', name='전체 보기', exact=True).click()
                expect(dialog.locator('.lib-card')).to_have_count(48)
                dialog.get_by_role('button', name='더 보기', exact=True).click()
                expect(dialog.locator('.lib-card')).to_have_count(53)
                assert len(set(dialog.locator('.lib-card').evaluate_all('(items) => items.map(i => i.dataset.id)'))) == 53
                assert not errors and not generation and not external
                (output / 'result.json').write_text(json.dumps({'passed': True, 'cases': [
                    'browse', 'single-and-mixed-artists', 'artist-only-append', 'prompt-only', 'full-conditions',
                    'metadata-free-image-query', 'exclude-identical-pixels', 'separate-feedback',
                    'annotations', 'favorites', 'text-search', 'draft-undo', 'draft-preserved-across-tabs-and-close',
                    'full-size-preview', 'pairwise-comparison-and-undo', 'responsive-1920-1280-900-390', 'failed-query-preserves-context',
                    'combination-return-to-results', 'out-of-order-search', 'pagination'], 'page_errors': errors,
                    'generation_requests': generation, 'external_browser_requests': external}, indent=2))
                browser.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
    print('Library browser acceptance passed (20 cases).')


if __name__ == '__main__':
    main()

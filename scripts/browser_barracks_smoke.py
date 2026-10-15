"""Offline Barracks acceptance against the real HTTP/provider path with mock NAI."""
import argparse
import io
import json
import tempfile
import threading
import zipfile
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlparse

from PIL import Image
from playwright.sync_api import expect, sync_playwright

from anima_app.config import AppPaths
from anima_app.providers.novelai import client
from anima_app.server import create_http_server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=Path('outputs/barracks-browser'))
    output = parser.parse_args().output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    checks, errors, forbidden, sent = [], [], [], []
    entered, release = threading.Event(), threading.Event()
    release.set()
    def transport(url, headers, body, timeout):
        payload = json.loads(body)
        sent.append(payload)
        entered.set()
        if not release.wait(15):
            raise AssertionError('Test did not release mock transport')
        png, archive = io.BytesIO(), io.BytesIO()
        params = payload['parameters']
        Image.new('RGB', (params['width'], params['height']), 'steelblue').save(png, format='PNG')
        with zipfile.ZipFile(archive, 'w') as z:
            z.writestr('test.png', png.getvalue())
        return archive.getvalue()

    def subscription(*args):
        return json.dumps({'active': True, 'tier': 3, 'usage': {'percent': 100, 'isNegative': False}}).encode()

    with tempfile.TemporaryDirectory(prefix='anima-barracks-browser-') as directory, \
            patch.object(client, '_requests_transport', transport), \
            patch.object(client, '_requests_subscription_transport', subscription), \
            patch.object(client, '_request_coordinator', client.RequestCoordinator()), \
            patch.object(client, 'REQUEST_INTERVAL_SECONDS', .01):
        paths = AppPaths(Path(directory))
        server = create_http_server('127.0.0.1', 0, paths=paths)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(locale='ko-KR', viewport={'width':1440, 'height':1000})
                def route(r):
                    if urlparse(r.request.url).hostname != '127.0.0.1':
                        forbidden.append(r.request.url)
                        r.abort()
                    else:
                        r.continue_()
                context.route('**/*', route)
                page = context.new_page()
                page.on('pageerror', lambda e: errors.append(str(e)))
                page.goto(f'http://127.0.0.1:{server.server_address[1]}', wait_until='networkidle')
                page.locator('#provider-select').select_option('novelai')
                page.locator('#prompt').fill('(artist:example:0.9), a blue bird')
                baseline = page.evaluate('JSON.stringify(animaGenerationDraft())')
                page.locator('#open-barracks').click()
                expect(page.locator('#barracks-dialog')).to_be_visible()
                expect(page.locator('#barracks-start')).to_be_disabled()
                for i in range(2):
                    page.locator('#barracks-account-name').fill(f'테스트 계정 {i+1}')
                    page.locator('#barracks-token').fill(f'test-only-barracks-token-{i}')
                    page.locator('#barracks-add-account').click()
                    expect(page.locator('#barracks-accounts input')).to_have_count(i+1)
                    expect(page.locator('#barracks-token')).to_have_value('')
                assert 'test-only-barracks-token' not in page.locator('body').inner_text()
                assert 'test-only-barracks-token' not in page.evaluate('JSON.stringify({...localStorage,...sessionStorage})')
                checks.append('Two masked accounts added without credentials in UI text or storage')
                page.locator('#barracks-account-name').fill('중복')
                page.locator('#barracks-token').fill('test-only-barracks-token-0')
                page.locator('#barracks-add-account').click()
                expect(page.locator('#barracks-message')).to_contain_text('이미 등록된 토큰')
                expect(page.locator('#barracks-accounts input')).to_have_count(2)
                checks.append('Duplicate token rejected')
                page.locator('#barracks-count').fill('4')
                page.locator('#barracks-seed-mode').select_option('fixed')
                page.locator('#barracks-start').click()
                expect(page.locator('#barracks-progress')).to_contain_text('완료 4/4', timeout=15000)
                expect(page.locator('#barracks-results img')).to_have_count(4)
                expect(page.locator('#barracks-account-progress')).to_contain_text('테스트 계정 1')
                expect(page.locator('#barracks-account-progress')).to_contain_text('테스트 계정 2')
                assert len(sent) == 4
                assert len({item['parameters']['seed'] for item in sent}) == 1
                assert all(item['action'] == 'generate' for item in sent)
                records = [json.loads(p.read_text()) for p in paths.manifest_root.glob('*.json')]
                assert len(records) == 4
                assert {r['barracks']['account_name'] for r in records} == {'테스트 계정 1', '테스트 계정 2'}
                assert 'test-only-barracks-token' not in json.dumps(records)
                checks.append('Four fixed-seed jobs produce four distinct saved images and account records')
                page.locator('#barracks-close').click()
                assert baseline == page.evaluate('JSON.stringify(animaGenerationDraft())')
                page.reload(wait_until='networkidle')
                page.locator('#open-barracks').click()
                expect(page.locator('#barracks-progress')).to_contain_text('완료 4/4')
                expect(page.locator('#barracks-accounts input')).to_have_count(2)
                checks.append('Reload restores server account and batch state without changing main settings')
                for locale, title in [('ko','배럭'), ('en','Barracks'), ('ja','バラック')]:
                    page.locator('#barracks-close').click()
                    page.locator('#nai-language').select_option(locale)
                    page.locator('#open-barracks').click()
                    expect(page.locator('#barracks-title')).to_have_text(title)
                    for width in (1440,900,390):
                        page.set_viewport_size({'width':width,'height':1000})
                        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                        assert page.locator('#barracks-dialog').evaluate('e => e.scrollWidth <= e.clientWidth + 1')
                    page.screenshot(path=str(output / f'barracks-{locale}-mobile.png'))
                    page.set_viewport_size({'width':1440,'height':1000})
                    page.screenshot(path=str(output / f'barracks-{locale}.png'))
                    checks.append(f'{locale}: translated dialog and results fit three viewport widths')
                page.locator('#barracks-close').click()
                page.locator('#nai-language').select_option('ko')
                page.locator('#provider-select').select_option('local')
                page.locator('#open-barracks').click()
                expect(page.locator('#barracks-message')).to_contain_text('NAI 텍스트')
                page.locator('#barracks-start').click()
                assert len(sent) == 4
                checks.append('Local engine blocked before any batch request')
                page.locator('#barracks-close').click()
                page.locator('#provider-select').select_option('novelai')
                page.evaluate("animaWorkflow.apply({version:1,steps:[{provider:'local',operation:'detail',inherit_prompt:true,request:{}}]})")
                page.locator('#open-barracks').click()
                page.locator('#barracks-start').click()
                expect(page.locator('#barracks-message')).to_contain_text('단독 생성')
                assert len(sent) == 4
                checks.append('Downstream workflow blocked without silent removal')
                page.locator('#barracks-close').click()
                page.evaluate('animaWorkflow.apply(null)')
                page.locator('#open-barracks').click()
                release.clear()
                entered.clear()
                page.locator('#barracks-accounts input').nth(1).uncheck()
                page.locator('#barracks-start').click()
                assert entered.wait(5)
                expect(page.locator('#barracks-stop')).to_be_enabled()
                expect(page.locator('#barracks-add-account')).to_be_disabled()
                page.locator('#barracks-stop').click()
                release.set()
                expect(page.locator('#barracks-progress')).to_contain_text('취소됨 3', timeout=15000)
                expect(page.locator('#barracks-progress')).to_contain_text('완료 1/4')
                assert len(sent) == 5
                checks.append('Stop retains the in-flight result and cancels three unsent jobs')
                page.locator('#barracks-accounts button').first.click()
                expect(page.locator('#barracks-accounts input')).to_have_count(1)
                checks.append('Account removal available after batch completes')
                context.close()
                browser.close()
        finally:
            release.set()
            server.shutdown()
            server.server_close()
            thread.join(5)
    result = {'checks':checks,'browser_errors':errors,'forbidden_requests':forbidden, 'mock_requests':len(sent)}
    (output/'verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    assert not errors and not forbidden
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__ == '__main__':
    main()

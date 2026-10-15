"""Exercise setup, private token handling and basic/advanced payload parity."""
import argparse
import json
import re
import tempfile
import threading
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import expect, sync_playwright

from anima_app.config import AppPaths
from anima_app.server import create_http_server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=Path('outputs/setup-browser'))
    output = parser.parse_args().output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    checks, errors, forbidden = [], [], []
    with tempfile.TemporaryDirectory(prefix='anima-setup-browser-') as directory:
        server = create_http_server('127.0.0.1', 0, paths=AppPaths(Path(directory)), default_dry_run=True)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(locale='ko-KR', viewport={'width':1440,'height':1000})
                def route(r):
                    u = urlparse(r.request.url)
                    if u.hostname != '127.0.0.1' or (r.request.method == 'POST' and u.path not in ('/api/setup/nai', '/api/setup/vrs/settings')):
                        forbidden.append(r.request.url)
                        r.abort()
                    else:
                        r.continue_()
                context.route('**/*', route)
                page = context.new_page()
                page.on('pageerror', lambda e: errors.append(str(e)))
                page.goto(f'http://127.0.0.1:{server.server_address[1]}',wait_until='networkidle')
                page.locator('#prompt').fill('설정 확인, 日本語, (artist:example:0.9)')
                baseline = page.evaluate('JSON.stringify(animaWorkflow.decorate(animaGenerationRequest()))')
                expect(page.locator('#seed')).not_to_be_visible()
                page.locator('#setup-view-toggle').click()
                expect(page.locator('#seed')).to_be_visible()
                assert baseline == page.evaluate('JSON.stringify(animaWorkflow.decorate(animaGenerationRequest()))')
                page.locator('#setup-view-toggle').click()
                assert baseline == page.evaluate('JSON.stringify(animaWorkflow.decorate(animaGenerationRequest()))')
                checks.append('Basic/advanced switch preserves complete generation payload')
                page.locator('#open-setup').click()
                expect(page.locator('#setup-dialog')).to_be_visible()
                expect(page.locator('#setup-core-state')).to_contain_text('SWEGCA')
                fake = 'TEST_ONLY_'+'x'*48
                page.locator('#setup-nai-token').fill(fake)
                page.locator('#setup-save-token').click()
                expect(page.locator('#setup-nai-token')).to_have_value('')
                expect(page.locator('.setup-card').first.locator('.setup-state')).to_have_text('토큰 입력됨')
                assert fake not in page.locator('body').inner_text()
                assert fake not in page.evaluate('JSON.stringify({...localStorage,...sessionStorage})')
                page.locator('#setup-clear-token').click()
                expect(page.locator('.setup-card').first.locator('.setup-state')).to_have_text('토큰을 입력해 주세요.')
                checks.append('Masked token applies and clears without entering DOM text or browser storage')
                page.locator('#setup-vrs-enabled').uncheck()
                expect(page.locator('#setup-vrs-prepare')).to_be_disabled()
                expect(page.locator('#setup-vrs-index')).to_be_disabled()
                page.reload(wait_until='networkidle')
                page.locator('#open-setup').click()
                expect(page.locator('#setup-vrs-enabled')).not_to_be_checked()
                page.locator('#setup-vrs-enabled').check()
                expect(page.locator('#setup-vrs-prepare')).to_be_enabled()
                checks.append('VRS switch persists, disables preparation/indexing and re-enables without download')
                for locale in ('ko','en','ja'):
                    page.locator('#setup-close').click()
                    page.locator('#nai-language').select_option(locale)
                    page.locator('#open-setup').click()
                    for panel in ('connections','models','references'):
                        page.locator('#setup-tab-'+panel).click()
                        expect(page.locator('#setup-'+panel)).to_be_visible()
                        if panel == 'models':
                            expect(page.locator('[data-model-group="anima-t2i"] .setup-file')).to_have_count(3)
                        if panel == 'references':
                            expect(page.locator('#setup-references a')).to_have_count(9)
                        for width in (1440,900,390):
                            page.set_viewport_size({'width':width,'height':1000})
                            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                            assert page.locator('#setup-dialog').evaluate('e => e.scrollWidth <= e.clientWidth + 1')
                        if locale != 'ko':
                            assert not re.search('[가-힣]', page.locator('#setup-'+panel).inner_text())
                        page.set_viewport_size({'width':1440,'height':1000})
                        page.screenshot(path=str(output/f'setup-{panel}-{locale}.png'))
                        checks.append(f'{locale}: {panel} at three widths with localized text')
                    page.locator('#setup-tab-connections').click()
                    page.set_viewport_size({'width':1440,'height':1000})
                    page.screenshot(path=str(output/f'setup-{locale}.png'))
                    assert baseline == page.evaluate('JSON.stringify(animaWorkflow.decorate(animaGenerationRequest()))')
                    checks.append(f'{locale}: setup and payload preserved at three viewport widths')
                page.locator('#setup-close').click()
                page.locator('#nai-language').select_option('ko')
                page.screenshot(path=str(output/'main-simple-ko.png'))
                page.locator('#setup-view-toggle').click()
                page.reload(wait_until='networkidle')
                expect(page.locator('#seed')).to_be_visible()
                checks.append('Advanced view preference survives reload')
                context.close()
                browser.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
    result = {'checks':checks,'browser_errors':errors,'forbidden_requests':forbidden}
    (output/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    assert not errors and not forbidden
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__ == '__main__':
    main()

"""Offline UI checks for opt-in credential persistence; never uses real tokens."""
import argparse
import json
import os
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import urlparse

from playwright.sync_api import expect, sync_playwright

from anima_app.config import AppPaths
from anima_app.server import create_http_server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=Path('outputs/credentials-browser'))
    output = parser.parse_args().output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    secrets, checks, errors, blocked = {}, [], [], []
    backend = SimpleNamespace(
        get_password=lambda service, ref: secrets.get((service, ref)),
        set_password=lambda service, ref, token: secrets.__setitem__((service, ref), token),
        delete_password=lambda service, ref: secrets.pop((service, ref)),
    )
    with tempfile.TemporaryDirectory(prefix='anima-credentials-browser-') as directory, \
            patch('anima_app.credentials.system_backend', return_value=backend), patch.dict(os.environ):
        for name in ('NAI_ACCESS_TOKEN', 'NAI_API_TOKEN'):
            os.environ.pop(name, None)
        paths = AppPaths(Path(directory))
        server = create_http_server('127.0.0.1', 0, paths=paths, default_dry_run=True)
        port = server.server_address[1]
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()

        def restart():
            nonlocal server, worker
            server.shutdown()
            server.server_close()
            worker.join(5)
            for name in ('NAI_ACCESS_TOKEN', 'NAI_API_TOKEN'):
                os.environ.pop(name, None)
            server = create_http_server('127.0.0.1', port, paths=paths, default_dry_run=True)
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()

        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                context = browser.new_context(locale='ko-KR', viewport={'width': 1440, 'height': 1000})

                def route(request):
                    if urlparse(request.request.url).hostname != '127.0.0.1':
                        blocked.append(request.request.url)
                        request.abort()
                    else:
                        request.continue_()

                context.route('**/*', route)
                page = context.new_page()
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.goto(f'http://127.0.0.1:{port}', wait_until='networkidle')
                page.locator('#nai-language').select_option('ko')
                page.locator('#open-setup').click()
                expect(page.locator('#setup-persist-token')).not_to_be_checked()
                page.locator('#setup-nai-token').fill('TEST_ONLY_primary_credential')
                page.locator('#setup-persist-token').check()
                page.locator('#setup-save-token').click()
                expect(page.locator('#setup-token-storage')).to_have_text('이 PC에 저장됨')
                expect(page.locator('#setup-nai-token')).to_have_value('')
                checks.append('Default is volatile; explicit save clears the secret input')
                for locale in ('ko', 'en', 'ja'):
                    page.locator('#setup-close').click()
                    page.locator('#nai-language').select_option(locale)
                    page.locator('#open-setup').click()
                    for width in (1440, 900, 390):
                        page.set_viewport_size({'width': width, 'height': 1000})
                        assert page.locator('#setup-dialog').evaluate('e => e.scrollWidth <= e.clientWidth + 1')
                    page.set_viewport_size({'width': 1440, 'height': 1000})
                    page.screenshot(path=str(output / f'storage-setup-{locale}.png'))
                    checks.append(f'{locale}: persistence controls fit desktop and mobile')
                page.locator('#setup-close').click()
                page.locator('#nai-language').select_option('ko')
                page.locator('#open-barracks').click()
                for name, token, save in [('Saved account', 'TEST_ONLY_saved_account', True),
                                          ('Temporary account', 'TEST_ONLY_temporary_account', False)]:
                    page.locator('#barracks-account-name').fill(name)
                    page.locator('#barracks-token').fill(token)
                    page.locator('#barracks-persist-token').set_checked(save)
                    page.locator('#barracks-add-account').click()
                    expect(page.locator('#barracks-accounts')).to_contain_text(name)
                checks.append('Barracks supports saved and volatile accounts together')
                page.screenshot(path=str(output / 'storage-barracks-ko.png'))
                assert 'TEST_ONLY_' not in page.locator('body').inner_text()
                assert 'TEST_ONLY_' not in page.evaluate('JSON.stringify({...localStorage,...sessionStorage})')
                restart()
                page.reload(wait_until='networkidle')
                page.locator('#open-setup').click()
                expect(page.locator('#setup-token-storage')).to_have_text('이 PC에 저장됨')
                expect(page.locator('.setup-state').first).to_have_text('토큰 입력됨')
                expect(page.locator('#setup-nai-token')).to_have_value('')
                page.locator('#setup-close').click()
                page.locator('#open-barracks').click()
                expect(page.locator('#barracks-accounts')).to_contain_text('Saved account')
                expect(page.locator('#barracks-accounts')).not_to_contain_text('Temporary account')
                checks.append('Fresh app instance restores only saved default and account')
                page.locator('#barracks-accounts [data-storage]').click()
                expect(page.locator('#barracks-accounts')).to_contain_text('실행 중에만 보관')
                expect(page.locator('#barracks-accounts')).to_contain_text('Saved account')
                page.locator('#barracks-close').click()
                page.locator('#open-setup').click()
                page.locator('#setup-persist-token').uncheck()
                page.locator('#setup-save-token').click()  # blank field means the connected token
                expect(page.locator('#setup-token-storage')).to_have_text('실행 중에만 보관')
                expect(page.locator('.setup-state').first).to_have_text('토큰 입력됨')
                checks.append('Forget saved copy keeps this app session connected')
                restart()
                page.reload(wait_until='networkidle')
                page.locator('#open-setup').click()
                expect(page.locator('.setup-state').first).to_have_text('토큰을 입력해 주세요.')
                page.locator('#setup-close').click()
                page.locator('#open-barracks').click()
                expect(page.locator('#barracks-accounts')).not_to_contain_text('Saved account')
                assert not secrets
                checks.append('Forgotten tokens are absent at next launch and removed from vault')
                for file in paths.output_root.rglob('*'):
                    if file.is_file():
                        assert b'TEST_ONLY_' not in file.read_bytes()
                checks.append('Tokens never enter app files or browser storage')
                assert not errors and not blocked, (errors, blocked)
                browser.close()
        finally:
            server.shutdown()
            server.server_close()
            worker.join(5)
    result = {'passed': True, 'checks': checks, 'page_errors': errors,
              'blocked_external_requests': blocked, 'credential_backend': 'in-memory test double'}
    (output / 'results.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()

"""Offline acceptance of the generation workspace and ordered workflow editor."""
import argparse
import json
import tempfile
import threading
from pathlib import Path
from urllib.parse import urlparse

import numpy as np
from playwright.sync_api import expect, sync_playwright
from safetensors.numpy import save_file

from anima_app.assets import required_t2i_model_files
from anima_app.config import AppPaths
from anima_app.defaults import DEFAULT_T2I_CHECKPOINT
from anima_app.server import create_http_server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=Path('outputs/generation-browser'))
    output = parser.parse_args().output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    checks, errors, forbidden = [], [], []
    with tempfile.TemporaryDirectory(prefix='anima-generation-browser-') as directory:
        paths = AppPaths(project_root=Path(directory))
        for asset in required_t2i_model_files(paths, DEFAULT_T2I_CHECKPOINT):
            asset.parent.mkdir(parents=True, exist_ok=True)
            save_file({'weight': np.asarray([1], dtype=np.float32)}, str(asset))
        def no_render(*args, **kwargs):
            raise AssertionError('Dry run must never invoke GPU rendering')
        server = create_http_server('127.0.0.1', 0, paths=paths, default_dry_run=True, renderer=no_render)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page(locale="ko-KR", viewport={'width': 1440, 'height': 1000})
                page.on('pageerror', lambda error: errors.append(str(error)))
                def route(request):
                    if urlparse(request.request.url).hostname != '127.0.0.1':
                        forbidden.append(request.request.url)
                        request.abort()
                    else:
                        request.continue_()
                page.route('**/*', route)
                page.goto(f'http://127.0.0.1:{server.server_address[1]}', wait_until='networkidle')
                expect(page.locator('#generate-button')).to_be_enabled()
                expect(page.locator('#prompt')).to_be_visible()
                expect(page.locator('#generation-empty')).to_be_visible()
                assert page.locator('#prompt').bounding_box()['y'] < 350
                assert page.locator('#generate-button').bounding_box()['y'] < 1000
                checks.append('Prompt and persistent generation actions visible without scrolling')
                page.locator('#toggle-history').click()
                expect(page.locator('.history-frame')).to_be_hidden()
                page.locator('#toggle-history').click()
                expect(page.locator('.history-frame')).to_be_visible()
                checks.append('History toggles while preserving workspace')
                page.locator('#open-queue-settings').click()
                assert page.locator('#generation-queue').evaluate('n => n.open')
                checks.append('Queue shortcut reveals folded controls')
                page.locator('#prompt').fill('offline workflow browser test')
                page.locator('#generation-workflow > summary').click()
                page.get_by_role('button', name='NAI 생성 → Anima 디테일러', exact=True).click()
                expect(page.locator('#provider-select')).to_have_value('novelai')
                assert page.evaluate('animaWorkflow.snapshot()[0].provider') == 'local'
                page.get_by_role('button', name='Anima 생성 → NAI 디테일러', exact=True).click()
                expect(page.locator('#provider-select')).to_have_value('local')
                assert page.evaluate('animaWorkflow.snapshot()[0].provider') == 'novelai'
                checks.append('Both cross-provider presets select their base and downstream engines')
                page.locator('#generation-workflow .workflow-add select').select_option('local:upscale')
                page.locator('#workflow-add').click()
                page.get_by_role('button', name='3단계 위로', exact=True).click()
                assert page.evaluate('animaWorkflow.snapshot().map(s => s.operation)') == ['upscale', 'detail']
                page.get_by_role('button', name='2단계 아래로', exact=True).click()
                assert page.evaluate('animaWorkflow.snapshot().map(s => s.operation)') == ['detail', 'upscale']
                checks.append('Post-processing order changes the serialized execution plan')
                stage = page.locator('.workflow-step').first
                stage.locator('summary').click()
                stage.get_by_label('변경 강도', exact=True).fill('0.31')
                stage.get_by_label('첫 단계 프롬프트 사용', exact=True).uncheck()
                stage.get_by_label('이 단계 프롬프트', exact=True).fill('specific detail prompt')
                snapshot = page.evaluate('animaWorkflow.snapshot()')
                assert snapshot[0]['request']['nai_detailer']['strength'] == .31
                assert snapshot[0]['request']['prompt'] == 'specific detail prompt'
                assert snapshot[0]['request']['nai_limit_opus_free']
                page.evaluate('(s) => animaWorkflow.apply({version:1, steps:s})', snapshot)
                assert page.evaluate('animaWorkflow.snapshot()') == snapshot
                checks.append('Stage model, prompt, strength and protection persist through restore')
                with page.expect_response(lambda response: response.url.endswith('/api/jobs') and response.request.method == 'POST') as submitted:
                    page.locator('#generate-button').click()
                receipt = submitted.value.json()
                assert submitted.value.status < 300, receipt
                page.wait_for_function("document.querySelector('#queue-status').textContent.includes('완료')", timeout=15000)
                journals = list((paths.output_root / 'workflows').glob('*.json'))
                assert journals
                journal = json.loads(journals[-1].read_text())
                assert journal['run']['status'] == 'dry_run'
                assert len(journal['run']['steps']) == 3
                assert not list(paths.image_root.glob('**/*.png'))
                checks.append('Submit runs the full plan in dry-run mode with no generated images')
                page.get_by_role('button', name='생성만', exact=True).click()
                assert page.evaluate('animaWorkflow.snapshot()') == []
                checks.append('Generate-only clears downstream steps')
                page.locator('#open-library').click()
                expect(page.locator('#library-dialog')).to_be_visible()
                page.get_by_role('button', name='생성 화면으로', exact=True).click()
                expect(page.locator('#prompt')).to_have_value('offline workflow browser test')
                checks.append('Image workspace round trip preserves prompt')
                for width, height in [(1920,1080),(1440,1000),(1280,900),(900,900),(390,844)]:
                    page.set_viewport_size({'width':width,'height':height})
                    page.wait_for_timeout(100)
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1'), width
                    box = page.locator('#generate-button').bounding_box()
                    assert box and box['y'] >= 0 and box['y']+box['height'] <= height+1, (width,box)
                    page.screenshot(path=str(output / f'workspace-{width}.png'))
                checks.append('No horizontal overflow and visible generate action at five viewport sizes')
                assert not errors, errors
                assert not forbidden, forbidden
                browser.close()
        finally:
            server.shutdown()
    report = {'status':'passed','checks':checks,'browser_errors':errors,'external_requests':forbidden}
    (output / 'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__ == '__main__':
    main()

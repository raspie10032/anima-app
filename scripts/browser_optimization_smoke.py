"""Offline regression for stale responses, compact polling and history DOM reuse."""
import argparse
import json
import tempfile
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright

from anima_app.config import AppPaths
from anima_app.server import create_http_server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=Path('outputs/optimization-browser'))
    output = parser.parse_args().output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    errors = []
    with tempfile.TemporaryDirectory(prefix='anima-optimization-') as directory:
        server = create_http_server('127.0.0.1', 0, paths=AppPaths(Path(directory)), default_dry_run=True)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=True)
                page = browser.new_page(locale='ko-KR')
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.route('**/*', lambda route: route.continue_() if route.request.url.startswith('http://127.0.0.1:') else route.abort())
                page.goto(f'http://127.0.0.1:{server.server_address[1]}', wait_until='networkidle')
                checks = page.evaluate('''async () => {
                  const checks = [];
                  const check = (condition, message) => { if (!condition) throw Error(message); checks.push(message); };
                  check(document.querySelectorAll('#memory-profile option[value="low_vram"]').length === 1, 'Memory selector offers the workload-preserving profile exactly once');
                  stopServerQueuePolling(); stopProgressPolling();
                  const realFetch = window.fetch;
                  try {
                    let resolve, count = 0;
                    window.fetch = () => { count++; return new Promise(r => resolve = r); };
                    const first = pollServerQueue();
                    await pollServerQueue();
                    check(count === 1, 'Only one queue request can be in flight');
                    stopServerQueuePolling();
                    setQueueStatus('terminal sentinel');
                    resolve(new Response(JSON.stringify({items: []}), {status: 200}));
                    await first;
                    check(document.querySelector('#queue-status').textContent === 'terminal sentinel', 'Old queue epoch cannot overwrite current status');

                    let renders = 0;
                    const originalRender = renderGenerationStages;
                    try {
                      renderGenerationStages = () => { renders++; };
                      activeProgressId = 'old';
                      const progress = pollGenerationProgress('old');
                      await pollGenerationProgress('old');
                      check(count === 2, 'Only one progress request can be in flight');
                      stopProgressPolling();
                      resolve(new Response(JSON.stringify({status:'running',stages:{}}), {status:200}));
                      await progress;
                      check(renders === 0, 'Old progress epoch cannot redraw completed stages');
                      window.fetch = async () => new Response(JSON.stringify({status:'completed',stages:{}}), {status:200});
                      activeProgressId = 'finished';
                      await pollGenerationProgress('finished');
                      renderServerQueueStatus({items:[{id:'j',status:'running',progress_id:'finished',request:{provider:'local'}}]});
                      check(renders === 1 && activeProgressId === '', 'Late running queue snapshot cannot restart completed progress');
                    } finally { renderGenerationStages = originalRender; }

                    historyItems = Array.from({length:8}, (_, i) => ({manifest_name:`fixture-${i}.json`,status:'dry_run',request:{}}));
                    renderHistory();
                    const nodes = [...document.querySelectorAll('.history-item')];
                    historyItems = [...historyItems, ...Array.from({length:8}, (_,i) => ({manifest_name:`fixture-${i+8}.json`,status:'dry_run',request:{}}))];
                    renderHistory();
                    const appended = [...document.querySelectorAll('.history-item')];
                    check(appended.length === 16 && nodes.every((node,i) => node === appended[i]), 'Appending history preserves all previously rendered card nodes');
                    historyItems = [{manifest_name:'newest.json',status:'dry_run',request:{}}, ...historyItems];
                    renderHistory();
                    const prepended = [...document.querySelectorAll('.history-item')];
                    check(prepended.length === 17 && appended.every((node,i) => node === prepended[i+1]), 'New completion is inserted first while retaining older card nodes');

                    let details = 0, statuses = 0;
                    window.fetch = async (url, options) => {
                      if (url === '/api/jobs/result-fixture') {
                        details++;
                        return new Response(JSON.stringify({result:{status:'dry_run'}}), {status:200});
                      }
                      if (url === '/api/status') statuses++;
                      return realFetch(url, options);
                    };
                    lastQueueResultJobId = '';
                    const completed = () => [{id:'result-fixture',status:'completed',has_result:true}];
                    await showLatestQueueResult(completed());
                    await showLatestQueueResult(completed());
                    check(details === 1, 'Compact queue result is fetched once for a new completion');
                    check(statuses === 0, 'New result refreshes history without rescanning model status');
                  } finally {
                    window.fetch = realFetch;
                    stopServerQueuePolling(); stopProgressPolling();
                  }
                  return checks;
                }''')
                assert not errors, errors
                browser.close()
            (output/'report.json').write_text(json.dumps({'checks':checks,'browser_errors':errors}, ensure_ascii=False, indent=2))
            print(f'Optimization browser acceptance passed ({len(checks)} cases).')
        finally:
            server.shutdown()
            server.server_close()


if __name__ == '__main__':
    main()

"""Download public artist tags only; never sends user prompts or account data."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from anima_app.artist_catalog import catalog_path
from anima_app.config import AppPaths
from anima_app.manifests import _write_json_atomically


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project-root', type=Path, default=Path.cwd())
    parser.add_argument('--pages', type=int, default=20)
    parser.add_argument('--interval', type=float, default=1.0)
    args = parser.parse_args()
    if not 1 <= args.pages <= 1000 or args.interval < 1:
        parser.error('Use 1–1000 pages and an interval of at least 1 second')
    endpoint = 'https://safebooru.donmai.us/tags.json'
    tags, complete = {}, False
    for page in range(1, args.pages + 1):
        if page > 1:
            time.sleep(args.interval)
        query = urlencode({'search[category]':1, 'search[is_deprecated]':'false', 'search[hide_empty]':'true',
                           'search[order]':'count', 'limit':1000, 'page':page, 'only':'id,name,category,post_count,is_deprecated'})
        request = Request(endpoint + '?' + query, headers={'User-Agent':'AnimaApp/0.5 artist-catalog'})
        # A failed request (including 429) aborts, preserving the last good snapshot.
        with urlopen(request, timeout=30) as response:
            data = json.loads(response.read(4_000_001))
        if not isinstance(data, list) or any(not isinstance(row, dict) or row.get('category') != 1 or not isinstance(row.get('name'), str) for row in data):
            raise ValueError('Unexpected artist tag response; previous catalog retained')
        for row in data:
            if not row.get('is_deprecated'):
                tags[row['name']] = row
        print(f'Page {page}: {len(tags)} artist tags', flush=True)
        if len(data) < 1000:
            complete = True
            break
    if not tags:
        raise ValueError('Empty catalog; previous catalog retained')
    destination = catalog_path(AppPaths(project_root=args.project_root.resolve()))
    destination.parent.mkdir(parents=True, exist_ok=True)
    _write_json_atomically(destination, {'version':1, 'source':endpoint,
        'fetched_at':datetime.now(timezone.utc).isoformat(), 'coverage':'nonempty-active' if complete else 'partial-by-post-count',
        'pages':page, 'tags':list(tags.values())})
    print(json.dumps({'path':str(destination), 'count':len(tags), 'complete':complete}))


if __name__ == '__main__':
    main()

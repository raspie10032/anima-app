"""Download original images observed in authenticated Firefox DOM snapshots.

This consumes an explicit local manifest, never cookies or account credentials.
Run from the project with PYTHONPATH=src. All outputs belong under outputs/.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import html
import json
from pathlib import Path
import re
import time
import threading
from urllib.parse import urlparse

import requests

from anima_app.library_metadata import artist_combo, metadata
from anima_app.library_visual import MAX_IMAGE_BYTES, read_pixels

RATE_LIMITED = threading.Event()


def original_urls(snapshot):
    # Only actual original-image links exposed by the page, never guessed URLs.
    urls = re.findall(r'href="(https://ac-o\.arca\.live/[^"\s]+)"', snapshot)
    return list(dict.fromkeys(html.unescape(url) for url in urls if valid_original(html.unescape(url))))


def valid_original(url):
    parsed = urlparse(url)
    return (parsed.scheme == 'https' and parsed.netloc == 'ac-o.arca.live'
            and Path(parsed.path).suffix.lower() in ('.png', '.jpg', '.jpeg', '.webp'))


def prepare(manifest, destination, maximum, per_post):
    jobs, posts = [], []
    seen = set()
    # Round-robin across posts prevents one large gallery consuming the budget.
    for post in manifest:
        if not re.fullmatch(r'https://arca\.live/b/aiart/\d+', post.get('url', '')):
            raise ValueError('Expected a canonical aiart post URL')
        if not post.get('snapshot'):
            continue
        snapshot = Path(post['snapshot']).read_text(encoding='utf-8')
        urls = original_urls(snapshot)[:per_post]
        folder = destination / post['url'].rsplit('/', 1)[1]
        folder.mkdir(parents=True, exist_ok=True)
        source = {**post, 'post': post['url'], 'image_urls': urls, 'collected_at': time.time()}
        (folder / 'source.json').write_text(json.dumps(source, ensure_ascii=False, indent=2), encoding='utf-8')
        posts.append((post, folder, urls))
    for index in range(per_post):
        for post, folder, urls in posts:
            if index >= len(urls):
                continue
            url = urls[index]
            key = urlparse(url).path
            if key in seen:
                continue
            seen.add(key)
            jobs.append((post, folder, url))
            if len(jobs) >= maximum:
                return jobs
    return jobs


def download(job):
    post, folder, url = job
    suffix = Path(urlparse(url).path).suffix.lower()
    filename = hashlib.sha256(urlparse(url).path.encode()).hexdigest()[:24] + suffix
    path = folder / filename
    temporary = path.with_suffix('.part')
    try:
        if RATE_LIMITED.is_set():
            return dict(post=post['url'], path=str(path.resolve()), status='deferred', error='server_rate_limit')
        if not path.exists():
            with requests.get(url, stream=True,
                              timeout=(15, 45), allow_redirects=False) as response:
                if response.status_code == 429:
                    RATE_LIMITED.set()
                if response.status_code != 200:
                    raise ValueError(f'HTTP {response.status_code}')
                length = 0
                with temporary.open('wb') as output:
                    for chunk in response.iter_content(256 * 1024):
                        length += len(chunk)
                        if length > MAX_IMAGE_BYTES:
                            raise ValueError('Image exceeds library byte limit')
                        output.write(chunk)
            read_pixels(temporary)
            temporary.replace(path)
        pixels = read_pixels(path)
        request, source, warnings = metadata(path)
        combo = artist_combo(request)
        # Metadata is recorded, never reconstructed from a post's prose.
        return dict(post=post['url'], title=post.get('title', ''), path=str(path.resolve()),
                    bytes=path.stat().st_size, sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                    pixel_hash=hashlib.sha256(pixels.tobytes() + str(pixels.size).encode()).hexdigest(),
                    width=pixels.width, height=pixels.height, source=source,
                    has_prompt=bool(request.get('prompt')), combo=combo, warnings=warnings, status='ok')
    except Exception as exc:
        # Do not put signed query strings or response bodies in logs.
        return dict(post=post['url'], path=str(path.resolve()), status='error',
                    error=str(exc) if isinstance(exc, (ValueError, OSError)) and not isinstance(exc, requests.RequestException)
                    else type(exc).__name__)
    finally:
        temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--limit', type=int, default=600)
    parser.add_argument('--per-post', type=int, default=20)
    parser.add_argument('--workers', type=int, default=1, choices=range(1, 5))
    parser.add_argument('--delay', type=float, default=2.0)
    args = parser.parse_args()
    if not 1 <= args.limit <= 2000 or not 1 <= args.per_post <= 100 or args.delay < 1:
        parser.error('limit must be 1..2000; per-post must be 1..100')
    manifest = json.loads(args.manifest.read_text(encoding='utf-8'))
    args.output.mkdir(parents=True, exist_ok=True)
    jobs = prepare(manifest, args.output, args.limit, args.per_post)
    results = []
    print(json.dumps({'planned': len(jobs), 'posts': len({j[0]['url'] for j in jobs})}), flush=True)
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        # Bounded batches: no queued flood after a rate-limit response.
        for offset in range(0, len(jobs), args.workers):
            futures = [pool.submit(download, job) for job in jobs[offset:offset + args.workers]]
            results.extend(future.result() for future in as_completed(futures))
            if len(results) % 10 == 0 or len(results) == len(jobs) or RATE_LIMITED.is_set():
                ok = [r for r in results if r['status'] == 'ok']
                summary = dict(processed=len(results), planned=len(jobs), downloaded=len(ok),
                               prompts=sum(r['has_prompt'] for r in ok),
                               artist_cases=sum(bool(r['combo']['key']) for r in ok),
                               combinations=len({r['combo']['key'] for r in ok if r['combo']['key']}),
                               bytes=sum(r['bytes'] for r in ok))
                print(json.dumps(summary), flush=True)
                report = dict(summary=summary, images=sorted(results, key=lambda r: r['path']))
                temp = args.output / 'catalog.tmp'
                temp.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
                temp.replace(args.output / 'catalog.json')
            if RATE_LIMITED.is_set():
                print('Paused: server returned HTTP 429. Resume later with the same manifest.', flush=True)
                break
            time.sleep(args.delay)


if __name__ == '__main__':
    main()

"""Local image -> cases -> observed artist combinations -> saved requests.

Vectors observe pixels only. Metadata is joined after ranking, never used to
identify an artist. Originals are referenced, not changed or copied.
"""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import io
import json
import os
from pathlib import Path
import random
import re
import sqlite3
import threading
import time
import uuid
from urllib.parse import urlparse

import numpy as np

from anima_app.library_metadata import PARSER_VERSION, artist_combo, metadata
from anima_app.library_visual import VISUAL_VERSION, observe, read_pixels, unit
from anima_app.library_vrs import VRSAdapter

MAX_ITEMS = 2000
EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp'}


def dump(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def bounded(value, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f'정수 {low}~{high} 범위로 입력해 주세요.')
    return value


class Library:
    def __init__(self, paths, generation_lock=None):
        self.paths = paths
        self.root = paths.output_root / 'library'
        self.root.mkdir(parents=True, exist_ok=True)
        self.db = self.root / 'library.sqlite3'
        self.thumbs = self.root / 'thumbnails'
        self.thumbs.mkdir(exist_ok=True)
        self.generation_lock = generation_lock or threading.Lock()
        self.import_lock = threading.Lock()
        self.state_lock = threading.Lock()
        self.cancelled = threading.Event()
        self.job = {'status': 'idle'}
        self.vrs = VRSAdapter()
        with self.connect() as conn:
            conn.executescript('''
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS assets (
              id TEXT PRIMARY KEY, pixel_hash TEXT NOT NULL, width INTEGER, height INTEGER,
              vector TEXT NOT NULL, created REAL, favorite INTEGER NOT NULL DEFAULT 0,
              tags TEXT NOT NULL DEFAULT '', collection TEXT NOT NULL DEFAULT '', note TEXT NOT NULL DEFAULT '');
            CREATE INDEX IF NOT EXISTS pixels ON assets(pixel_hash);
            CREATE TABLE IF NOT EXISTS sources (
              path TEXT PRIMARY KEY, asset_id TEXT NOT NULL REFERENCES assets(id), size INTEGER, mtime INTEGER);
            CREATE TABLE IF NOT EXISTS records (
              id TEXT PRIMARY KEY, asset_id TEXT NOT NULL REFERENCES assets(id), source TEXT,
              request TEXT NOT NULL, combo TEXT NOT NULL, combo_key TEXT NOT NULL,
              warnings TEXT NOT NULL, created REAL);
            CREATE INDEX IF NOT EXISTS record_asset ON records(asset_id);
            CREATE INDEX IF NOT EXISTS record_combo ON records(combo_key);
            CREATE TABLE IF NOT EXISTS vectors (
              asset_id TEXT NOT NULL REFERENCES assets(id), contract TEXT NOT NULL, vector TEXT NOT NULL,
              PRIMARY KEY(asset_id,contract));
            CREATE TABLE IF NOT EXISTS queries (
              id TEXT PRIMARY KEY, pixel_hash TEXT, contract TEXT, results TEXT, created REAL);
            CREATE TABLE IF NOT EXISTS feedback (
              query_id TEXT NOT NULL REFERENCES queries(id), asset_id TEXT NOT NULL REFERENCES assets(id),
              visual INTEGER, reuse INTEGER, created REAL, PRIMARY KEY(query_id,asset_id));
            CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
            CREATE TABLE IF NOT EXISTS comparisons (
              id TEXT PRIMARY KEY, query_id TEXT NOT NULL REFERENCES queries(id),
              a TEXT NOT NULL REFERENCES assets(id), b TEXT NOT NULL REFERENCES assets(id),
              choice TEXT NOT NULL, created REAL NOT NULL, undone INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS synced_manifests (
              path TEXT PRIMARY KEY, size INTEGER, mtime INTEGER, image_size INTEGER, image_mtime INTEGER);
            ''')
            if 'source_url' not in {row[1] for row in conn.execute('PRAGMA table_info(sources)')}:
                conn.execute("ALTER TABLE sources ADD COLUMN source_url TEXT NOT NULL DEFAULT ''")
            version = conn.execute("SELECT value FROM settings WHERE key='parser_version'").fetchone()
            if not version or version[0] != PARSER_VERSION:
                for row in conn.execute('SELECT id,request FROM records').fetchall():
                    combo = artist_combo(json.loads(row['request']))
                    conn.execute('UPDATE records SET combo=?,combo_key=? WHERE id=?', (dump(combo), combo['key'], row['id']))
                conn.execute("INSERT OR REPLACE INTO settings VALUES('parser_version',?)", (PARSER_VERSION,))

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.db, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA foreign_keys=ON')
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def status(self):
        contract = self.vrs.contract
        with self.connect() as c:
            n = c.execute('SELECT count(*) FROM assets').fetchone()[0]
            records = c.execute('SELECT count(*) FROM records').fetchone()[0]
            combos = c.execute("SELECT count(DISTINCT combo_key) FROM records WHERE combo_key != ''").fetchone()[0]
            vectors = c.execute('SELECT count(*) FROM vectors WHERE contract=?', (contract,)).fetchone()[0]
            feedback = c.execute('SELECT count(*) FROM feedback').fetchone()[0]
            distinct_pixels = c.execute('SELECT count(DISTINCT pixel_hash) FROM assets').fetchone()[0]
            artist_sequences = len({dump(json.loads(row[0])['artists'])
                                    for row in c.execute("SELECT DISTINCT combo FROM records WHERE combo_key != ''")})
        with self.state_lock:
            job = dict(self.job)
        return dict(items=n, records=records, combinations=combos, capacity=MAX_ITEMS,
                    visual_contract=VISUAL_VERSION, vrs_contract=contract, vrs_indexed=vectors,
                    feedback=feedback, distinct_pixels=distinct_pixels, artist_sequences=artist_sequences, job=job)

    def ingest(self, path, manifest=None):
        path = Path(path).resolve(strict=True)
        if not path.is_file() or path.suffix.lower() not in EXTENSIONS:
            raise ValueError('PNG/JPEG/WebP 파일을 선택해 주세요.')
        stat = path.stat()
        with self.connect() as c:
            known = c.execute('SELECT * FROM sources WHERE path=?', (str(path),)).fetchone()
            if known and known['size'] == stat.st_size and known['mtime'] == stat.st_mtime_ns and manifest is None:
                return known['asset_id'], 'unchanged'
        # Decode before metadata parsing; reject oversized images first.
        pixels = read_pixels(path)
        obs = observe(pixels)
        file_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        request, source, warnings = metadata(path, manifest)
        source_url = ''
        sidecar = path.parent / 'source.json'
        try:
            if sidecar.stat().st_size <= 1024 * 1024:
                provenance = json.loads(sidecar.read_text(encoding='utf-8'))
                candidate = provenance.get('post', '') if isinstance(provenance, dict) else ''
                if isinstance(candidate, str) and len(candidate) <= 2048:
                    parsed = urlparse(candidate)
                    if parsed.scheme in ('http', 'https') and parsed.hostname and not parsed.username:
                        source_url = candidate
        except (OSError, ValueError):
            pass
        combo = artist_combo(request)
        record_id = hashlib.sha256(dump([file_hash, source, request]).encode()).hexdigest()
        thumbnail = self.thumbs / (file_hash + '.jpg')
        after = path.stat()
        if (stat.st_size, stat.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise ValueError('읽는 동안 파일이 변경되었습니다. 다시 가져와 주세요.')
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            exists = c.execute('SELECT 1 FROM assets WHERE id=?', (file_hash,)).fetchone()
            if not exists and c.execute('SELECT count(*) FROM assets').fetchone()[0] >= MAX_ITEMS:
                raise ValueError('첫 라이브러리는 2,000장까지 등록합니다.')
            if not thumbnail.exists():
                temporary = thumbnail.with_suffix('.' + uuid.uuid4().hex + '.tmp')
                temporary.write_bytes(obs['thumbnail'])
                os.replace(temporary, thumbnail)
            c.execute('INSERT OR IGNORE INTO assets(id,pixel_hash,width,height,vector,created) VALUES(?,?,?,?,?,?)',
                      (file_hash, obs['pixel_hash'], obs['width'], obs['height'], dump(obs['vector']), time.time()))
            c.execute('INSERT OR REPLACE INTO sources(path,asset_id,size,mtime,source_url) VALUES(?,?,?,?,?)',
                      (str(path), file_hash, stat.st_size, stat.st_mtime_ns, source_url))
            c.execute('INSERT OR IGNORE INTO records VALUES(?,?,?,?,?,?,?,?)',
                      (record_id, file_hash, source, dump(request), dump(combo), combo['key'], dump(warnings), time.time()))
        return file_hash, 'existing' if exists else 'added'

    def _item(self, c, row, detail=False):
        result = {k: row[k] for k in ('id', 'width', 'height', 'favorite', 'tags', 'collection', 'note')}
        result['thumbnail'] = '/api/library/thumbnail/' + row['id']
        records = c.execute('SELECT * FROM records WHERE asset_id=? ORDER BY created DESC,id', (row['id'],)).fetchall()
        result['records'] = [dict(id=r['id'], source=r['source'], combo=json.loads(r['combo']),
                                  warnings=json.loads(r['warnings']), **({'request': json.loads(r['request'])} if detail else {})) for r in records]
        if detail:
            result['sources'] = [dict(path=r['path'], source_url=r['source_url'], available=Path(r['path']).is_file())
                                 for r in c.execute('SELECT path,source_url FROM sources WHERE asset_id=?', (row['id'],))]
        return result

    def detail(self, identity):
        if not isinstance(identity, str) or not re.fullmatch('[0-9a-f]{64}', identity):
            raise ValueError('이미지 ID가 잘못되었습니다.')
        with self.connect() as c:
            row = c.execute('SELECT * FROM assets WHERE id=?', (identity,)).fetchone()
            if row is None:
                raise ValueError('등록된 이미지를 찾을 수 없습니다.')
            return self._item(c, row, True)

    def browse(self, query='', offset=0, limit=48, combo='', favorite=False):
        bounded(offset, 0, MAX_ITEMS)
        bounded(limit, 1, 100)
        if not isinstance(query, str) or len(query) > 256:
            raise ValueError('검색어는 256자 이하여야 합니다.')
        sql = 'SELECT a.* FROM assets a WHERE 1=1'
        params = []
        if favorite:
            sql += ' AND a.favorite=1'
        if combo:
            sql += ' AND EXISTS(SELECT 1 FROM records r WHERE r.asset_id=a.id AND r.combo_key=?)'
            params.append(combo)
        # Literal substring, including Korean and underscores; no wildcard expansion.
        for term in query.casefold().split():
            sql += ''' AND (instr(lower(a.tags || ' ' || a.collection || ' ' || a.note),?)>0
                       OR EXISTS(SELECT 1 FROM records r WHERE r.asset_id=a.id AND instr(lower(r.request),?)>0))'''
            params.extend([term, term])
        with self.connect() as c:
            rows = c.execute(sql + ' ORDER BY a.created DESC,a.id', params).fetchall()
            return {'items': [self._item(c, row) for row in rows[offset:offset + limit]], 'total': len(rows)}

    def annotate(self, data):
        identity = data.get('id')
        self.detail(identity)
        fields = {}
        for name, maximum in [('tags', 2000), ('collection', 200), ('note', 8000)]:
            if name in data:
                if not isinstance(data[name], str) or len(data[name]) > maximum:
                    raise ValueError(f'{name}: 최대 {maximum}자입니다.')
                fields[name] = data[name]
        if 'favorite' in data:
            if type(data['favorite']) is not bool:
                raise ValueError('즐겨찾기 값이 잘못되었습니다.')
            fields['favorite'] = int(data['favorite'])
        if fields:
            with self.connect() as c:
                c.execute('UPDATE assets SET ' + ','.join(k + '=?' for k in fields) + ' WHERE id=?', [*fields.values(), identity])
        return self.detail(identity)

    def _original(self, identity):
        with self.connect() as c:
            paths = c.execute('SELECT path FROM sources WHERE asset_id=?', (identity,)).fetchall()
        for row in paths:
            path = Path(row['path'])
            if path.is_file() and path.stat().st_size <= 32 * 1024 * 1024 and hashlib.sha256(path.read_bytes()).hexdigest() == identity:
                return path
        raise ValueError('원본 파일이 없거나 변경되었습니다. 폴더를 다시 가져와 주세요.')

    def search(self, *, identity=None, image=None, mode='visual', limit=24):
        bounded(limit, 1, 100)
        if mode not in ('visual', 'vrs'):
            raise ValueError('검색 모드를 확인해 주세요.')
        if identity is not None:
            self.detail(identity)
        with self.connect() as c:
            if identity:
                row = c.execute('SELECT * FROM assets WHERE id=?', (identity,)).fetchone()
                if row is None:
                    raise ValueError('등록된 이미지가 없습니다.')
                pixel_hash, vector = row['pixel_hash'], json.loads(row['vector'])
            elif image:
                observation = observe(read_pixels(Path(image)))
                pixel_hash, vector = observation['pixel_hash'], observation['vector']
            else:
                raise ValueError('검색할 이미지를 선택해 주세요.')
            contract = VISUAL_VERSION
            rows = c.execute('SELECT * FROM assets ORDER BY id').fetchall()
            if mode == 'vrs':
                contract = self.vrs.contract
                if not contract:
                    raise ValueError('VRS 인코더 설정이 필요합니다.')
                indexed = {r['asset_id']: json.loads(r['vector']) for r in c.execute('SELECT * FROM vectors WHERE contract=?', (contract,))}
                if len(indexed) != len(rows):
                    raise ValueError('모든 이미지의 VRS 색인을 먼저 완료해 주세요.')
                if identity in indexed:
                    vector = indexed[identity]
                else:
                    if not self.generation_lock.acquire(blocking=False):
                        raise ValueError('생성 또는 모델 처리가 진행 중입니다.')
                    try:
                        vector = self.vrs.encode([Path(image)], self.root / 'scratch')[0]
                    finally:
                        self.generation_lock.release()
                candidates = [indexed[r['id']] for r in rows]
            else:
                candidates = [json.loads(r['vector']) for r in rows]
            ranked = []
            if candidates:
                matrix = np.asarray(candidates, dtype=np.float32)
                scores = matrix @ unit(vector)
                ranked = sorted(zip(rows, scores), key=lambda pair: (-float(pair[1]), pair[0]['id']))
            selected, seen = [], {pixel_hash}
            for row, score in ranked:
                if row['pixel_hash'] in seen:
                    continue
                seen.add(row['pixel_hash'])
                selected.append({**self._item(c, row), 'score': round(float(score), 6)})
                if len(selected) == limit:
                    break
            groups = {}
            for item in selected:
                for record in item['records']:
                    combo = record['combo']
                    if not combo['key']:
                        continue
                    group = groups.setdefault(combo['key'], dict(combo=combo, cases=[], best_score=item['score']))
                    if item['id'] not in group['cases']:
                        group['cases'].append(item['id'])
            query_id = uuid.uuid4().hex
            c.execute('INSERT INTO queries VALUES(?,?,?,?,?)', (query_id, pixel_hash, contract,
                      dump([i['id'] for i in selected]), time.time()))
            return dict(query_id=query_id, contract=contract, mode=mode, items=selected, combinations=list(groups.values()),
                        excluded_identical_pixels=True, total_indexed=len(rows))

    def feedback(self, data):
        query_id, identity = data.get('query_id'), data.get('id')
        self.detail(identity)
        if not isinstance(query_id, str) or not re.fullmatch('[0-9a-f]{32}', query_id):
            raise ValueError('검색 ID가 잘못되었습니다.')
        visual, reuse = data.get('visual'), data.get('reuse')
        for value in (visual, reuse):
            if value is not None:
                bounded(value, -1, 1)
        if visual is None and reuse is None:
            raise ValueError('닮음 또는 재사용 평가를 선택해 주세요.')
        with self.connect() as c:
            query = c.execute('SELECT results FROM queries WHERE id=?', (query_id,)).fetchone()
            if not query or identity not in json.loads(query['results']):
                raise ValueError('이 검색에서 나온 사례만 평가할 수 있습니다.')
            c.execute('''INSERT INTO feedback VALUES(?,?,?,?,?) ON CONFLICT(query_id,asset_id) DO UPDATE SET
                         visual=coalesce(excluded.visual,feedback.visual),reuse=coalesce(excluded.reuse,feedback.reuse),created=excluded.created''',
                      (query_id, identity, visual, reuse, time.time()))
        return {'status': 'saved', 'training': False}

    def preview(self, identity):
        """Bounded, metadata-free large preview; never expose arbitrary source paths."""
        self.detail(identity)
        pixels = read_pixels(self._original(identity))
        pixels.thumbnail((1600, 1600))
        output = io.BytesIO()
        pixels.save(output, format='JPEG', quality=90)
        return output.getvalue()

    def compare(self, data):
        """Relative visual judgment is distinct from absolute/reuse feedback."""
        query_id, a, b, choice = (data.get(k) for k in ('query_id', 'a', 'b', 'choice'))
        if not isinstance(query_id, str) or not re.fullmatch('[0-9a-f]{32}', query_id):
            raise ValueError('검색 ID가 잘못되었습니다.')
        if not all(isinstance(i, str) and re.fullmatch('[0-9a-f]{64}', i) for i in (a, b)) or a == b:
            raise ValueError('서로 다른 두 사례를 선택해 주세요.')
        if choice not in ('a', 'b', 'both', 'neither', 'skip'):
            raise ValueError('비교 판단을 확인해 주세요.')
        with self.connect() as c:
            query = c.execute('SELECT results FROM queries WHERE id=?', (query_id,)).fetchone()
            if not query or not {a, b}.issubset(json.loads(query['results'])):
                raise ValueError('같은 검색에서 나온 두 사례만 비교할 수 있습니다.')
            identity = uuid.uuid4().hex
            c.execute('INSERT INTO comparisons VALUES(?,?,?,?,?,?,0)',
                      (identity, query_id, a, b, choice, time.time()))
        return {'id': identity, 'status': 'saved', 'criterion': 'visual', 'training': False}

    def undo_comparison(self, data):
        identity = data.get('id')
        if not isinstance(identity, str) or not re.fullmatch('[0-9a-f]{32}', identity):
            raise ValueError('비교 ID가 잘못되었습니다.')
        with self.connect() as c:
            if not c.execute('SELECT 1 FROM comparisons WHERE id=?', (identity,)).fetchone():
                raise ValueError('저장된 비교를 찾을 수 없습니다.')
            c.execute('UPDATE comparisons SET undone=1 WHERE id=?', (identity,))
        return {'id': identity, 'status': 'undone', 'training': False}

    def _progress(self, **fields):
        with self.state_lock:
            self.job.update(fields)

    def start(self, data):
        kind = data.get('kind', 'import')
        if kind not in ('import', 'sync', 'vrs'):
            raise ValueError('지원하지 않는 작업입니다.')
        limit = bounded(data.get('limit', MAX_ITEMS), 1, MAX_ITEMS)
        folders = data.get('folders', [])
        if not isinstance(folders, list) or len(folders) > 20 or any(not isinstance(p, str) for p in folders):
            raise ValueError('폴더는 최대 20개입니다.')
        roots = [Path(p).expanduser().resolve(strict=True) for p in folders]
        if any(not p.is_dir() for p in roots):
            raise ValueError('이미지 폴더를 입력해 주세요.')
        if not self.import_lock.acquire(blocking=False):
            raise ValueError('가져오기 작업이 진행 중입니다.')
        self.cancelled.clear()
        self._progress(status='running', kind=kind, processed=0, added=0, errors=0, limit=limit, message='')
        thread = threading.Thread(target=self._run, args=(kind, roots, limit), daemon=True)
        thread.start()
        return self.status()

    def cancel(self):
        self.cancelled.set()
        return self.status()

    def sync(self, limit=MAX_ITEMS):
        count = 0
        for path in sorted(self.paths.manifest_root.glob('*.json')):
            if self.cancelled.is_set() or count >= limit:
                break
            try:
                if path.stat().st_size > 4 * 1024 * 1024:
                    continue
                manifest = json.loads(path.read_text(encoding='utf-8'))
                output = manifest.get('output_path')
                if not output:
                    continue
                image = Path(output)
                if not image.is_absolute():
                    image = self.paths.project_root / image
                # Generated history can only register managed output images.
                image.resolve().relative_to(self.paths.image_root.resolve())
                ms, ims = path.stat(), image.stat()
                signature = (ms.st_size, ms.st_mtime_ns, ims.st_size, ims.st_mtime_ns)
                with self.connect() as c:
                    prior = c.execute('SELECT size,mtime,image_size,image_mtime FROM synced_manifests WHERE path=?', (str(path),)).fetchone()
                if prior and tuple(prior) == signature:
                    continue
                identity, state = self.ingest(image, manifest)
                with self.connect() as c:
                    c.execute('INSERT OR REPLACE INTO synced_manifests VALUES(?,?,?,?,?)', (str(path), *signature))
                count += 1
            except (ValueError, OSError, TypeError, AttributeError):
                continue
        return count

    def _run(self, kind, roots, limit):
        try:
            if kind == 'vrs':
                self.build_vrs()
            elif kind == 'sync':
                self._progress(processed=self.sync(limit))
            else:
                # Stable seeded sample across folders; only decode the 2,000-item pilot.
                groups = []
                for root in roots:
                    files = []
                    for folder, dirs, names in os.walk(root, followlinks=False):
                        dirs[:] = sorted(d for d in dirs if not d.startswith('.') and d not in {'thumbnails','models','node_modules'})
                        for name in sorted(names):
                            p = Path(folder) / name
                            if p.suffix.lower() in EXTENSIONS and not p.is_symlink():
                                files.append(p)
                        if self.cancelled.is_set() or len(files) >= 100000:
                            break
                    random.Random(20261014).shuffle(files)
                    groups.append(iter(files))
                processed = added = errors = 0
                while groups and processed < limit and not self.cancelled.is_set():
                    for group in groups[:]:
                        if processed >= limit or self.cancelled.is_set():
                            break
                        path = next(group, None)
                        if path is None:
                            groups.remove(group)
                            continue
                        try:
                            _, state = self.ingest(path)
                            added += state == 'added'
                        except (ValueError, OSError, TypeError, OverflowError, SyntaxError):
                            errors += 1
                        processed += 1
                        self._progress(processed=processed, added=added, errors=errors)
            self._progress(status='cancelled' if self.cancelled.is_set() else 'complete')
        except Exception as exc:
            self._progress(status='failed', message=str(exc)[:300])
        finally:
            self.import_lock.release()

    def build_vrs(self):
        contract = self.vrs.contract
        if not contract:
            raise ValueError('VRS 인코더를 먼저 설정해 주세요.')
        if not self.generation_lock.acquire(blocking=False):
            raise ValueError('생성 또는 모델 처리가 진행 중입니다.')
        try:
            with self.connect() as c:
                ids = [r[0] for r in c.execute('SELECT id FROM assets WHERE id NOT IN (SELECT asset_id FROM vectors WHERE contract=?) ORDER BY id', (contract,))]
            for offset in range(0, len(ids), 256):
                if self.cancelled.is_set():
                    return
                batch = ids[offset:offset + 256]
                paths = [self._original(i) for i in batch]
                vectors = self.vrs.encode(paths, self.root / 'scratch', self.cancelled.is_set)
                if len(vectors) != len(batch):
                    raise ValueError('VRS 벡터 개수가 올바르지 않습니다.')
                if self.vrs.contract != contract:
                    raise ValueError('인코더 설정이 변경되었습니다. 색인을 다시 시작해 주세요.')
                with self.connect() as c:
                    c.executemany('INSERT OR REPLACE INTO vectors VALUES(?,?,?)',
                                  [(i, contract, dump(v)) for i, v in zip(batch, vectors)])
                self._progress(processed=min(offset + 256, len(ids)))
        finally:
            self.generation_lock.release()

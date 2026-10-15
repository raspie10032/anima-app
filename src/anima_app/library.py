"""Local image -> cases -> observed artist combinations -> saved requests.

Vectors observe pixels only. Metadata is joined after ranking, never used to
identify an artist. Originals are referenced, not changed or copied.
"""
from __future__ import annotations

from contextlib import contextmanager, nullcontext
import hashlib
import io
import json
import os
from pathlib import Path
import re
import sqlite3
import threading
import time
import uuid
from urllib.parse import urlparse

import numpy as np

from anima_app.library_metadata import PARSER_VERSION, artist_combo, metadata
from anima_app.library_visual import VISUAL_VERSION, observe, read_pixels, unit
from anima_app.library_vrs import VRSIndexCancelled
from anima_app.library_vrs_cached import CachedVRSAdapter
from anima_app.gpu_work_lock import GPUWorkLock
from anima_app import library_core

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
        self.generation_lock = generation_lock or GPUWorkLock()
        self.import_lock = threading.Lock()
        self.state_lock = threading.Lock()
        self._vrs_settings_lock = threading.RLock()
        self.cancelled = threading.Event()
        self.job = {'status': 'idle'}
        self.vrs = CachedVRSAdapter(paths.model_root)
        self.vrs.runtime.generation_lock = self.generation_lock
        if isinstance(self.generation_lock, GPUWorkLock):
            self.generation_lock.register_idle(self.vrs, self.vrs.close)
        self._cache_lock = threading.Lock()
        self._vector_cache = {}
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
            CREATE TABLE IF NOT EXISTS index_issues (
              asset_id TEXT NOT NULL REFERENCES assets(id), contract TEXT NOT NULL,
              state TEXT NOT NULL, message TEXT NOT NULL, updated REAL NOT NULL,
              PRIMARY KEY(asset_id,contract));
            CREATE TABLE IF NOT EXISTS core_receipts (
              query_id TEXT NOT NULL REFERENCES queries(id), asset_id TEXT NOT NULL REFERENCES assets(id),
              contract TEXT NOT NULL, receipt TEXT NOT NULL, created REAL NOT NULL,
              PRIMARY KEY(query_id,asset_id));
            CREATE TABLE IF NOT EXISTS import_issues (
              path TEXT PRIMARY KEY, code TEXT NOT NULL, message TEXT NOT NULL, updated REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS queries (
              id TEXT PRIMARY KEY, pixel_hash TEXT, contract TEXT, results TEXT, created REAL);
            CREATE TABLE IF NOT EXISTS feedback (
              query_id TEXT NOT NULL REFERENCES queries(id), asset_id TEXT NOT NULL REFERENCES assets(id),
              visual INTEGER, reuse INTEGER, created REAL, PRIMARY KEY(query_id,asset_id));
            CREATE TABLE IF NOT EXISTS feedback_times (
              query_id TEXT NOT NULL, asset_id TEXT NOT NULL,
              visual_updated REAL, reuse_updated REAL, PRIMARY KEY(query_id,asset_id),
              FOREIGN KEY(query_id,asset_id) REFERENCES feedback(query_id,asset_id));
            CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
            CREATE TABLE IF NOT EXISTS comparisons (
              id TEXT PRIMARY KEY, query_id TEXT NOT NULL REFERENCES queries(id),
              a TEXT NOT NULL REFERENCES assets(id), b TEXT NOT NULL REFERENCES assets(id),
              choice TEXT NOT NULL, created REAL NOT NULL, undone INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS synced_manifests (
              path TEXT PRIMARY KEY, size INTEGER, mtime INTEGER, image_size INTEGER, image_mtime INTEGER);
            ''')
            conn.execute("INSERT OR IGNORE INTO settings VALUES('retrieval_revision','0')")
            conn.execute("INSERT OR IGNORE INTO settings VALUES('vrs_enabled','1')")
            self.vrs_enabled = conn.execute("SELECT value FROM settings WHERE key='vrs_enabled'").fetchone()[0] == '1'
            # Only corpus changes invalidate matrices. Search receipts and user
            # evaluations must not cause 2,000 JSON vectors to be parsed again.
            for table in ('assets', 'vectors'):
                for event in ('INSERT', 'UPDATE', 'DELETE'):
                    conn.execute(f'''CREATE TRIGGER IF NOT EXISTS retrieval_{table}_{event}
                        AFTER {event} ON {table} BEGIN
                        UPDATE settings SET value=CAST(value AS INTEGER)+1
                        WHERE key='retrieval_revision'; END''')
            conn.execute('CREATE INDEX IF NOT EXISTS query_pixels_contract ON queries(pixel_hash,contract)')
            conn.execute('''INSERT OR IGNORE INTO feedback_times
                SELECT query_id,asset_id,CASE WHEN visual IS NOT NULL THEN created END,
                CASE WHEN reuse IS NOT NULL THEN created END FROM feedback''')
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
            issues = {r[0]: r[1] for r in c.execute('SELECT state,count(*) FROM index_issues WHERE contract=? GROUP BY state', (contract,))}
            feedback = c.execute('SELECT count(*) FROM feedback').fetchone()[0]
            distinct_pixels = c.execute('SELECT count(DISTINCT pixel_hash) FROM assets').fetchone()[0]
            artist_sequences = len({dump(json.loads(row[0])['artists'])
                                    for row in c.execute("SELECT DISTINCT combo FROM records WHERE combo_key != ''")})
        with self.state_lock:
            job = dict(self.job)
        return dict(items=n, records=records, combinations=combos, capacity=None,
                    visual_contract=VISUAL_VERSION, vrs_enabled=self.vrs_enabled,
                    vrs_contract=contract, vrs_indexed=vectors,
                    vrs_pending=max(0, n-vectors-sum(issues.values())), vrs_issues=issues,
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
        try:
            request, source, warnings = metadata(path, manifest)
        except (ValueError, TypeError, AttributeError, KeyError, OverflowError, RecursionError, OSError, UnicodeError):
            request, source, warnings = {}, 'unreadable', ['메타데이터를 읽지 못했습니다. 이미지 검색은 사용할 수 있습니다.']
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
            if not thumbnail.exists():
                temporary = thumbnail.with_suffix('.' + uuid.uuid4().hex + '.tmp')
                temporary.write_bytes(obs['thumbnail'])
                os.replace(temporary, thumbnail)
            c.execute('INSERT OR IGNORE INTO assets(id,pixel_hash,width,height,vector,created) VALUES(?,?,?,?,?,?)',
                      (file_hash, obs['pixel_hash'], obs['width'], obs['height'], dump(obs['vector']), time.time()))
            c.execute('INSERT OR REPLACE INTO sources(path,asset_id,size,mtime,source_url) VALUES(?,?,?,?,?)',
                      (str(path), file_hash, stat.st_size, stat.st_mtime_ns, source_url))
            c.execute('DELETE FROM import_issues WHERE path=?', (str(path),))
            c.execute('INSERT OR IGNORE INTO records VALUES(?,?,?,?,?,?,?,?)',
                      (record_id, file_hash, source, dump(request), dump(combo), combo['key'], dump(warnings), time.time()))
        return file_hash, 'existing' if exists else 'added'

    def _item(self, c, row, detail=False, group=False):
        result = {k: row[k] for k in ('id', 'width', 'height', 'favorite', 'tags', 'collection', 'note')}
        result['thumbnail'] = '/api/library/thumbnail/' + row['id']
        ids = [r[0] for r in c.execute('SELECT id FROM assets WHERE pixel_hash=? ORDER BY id', (row['pixel_hash'],))] if group else [row['id']]
        result['asset_ids'] = ids
        placeholders = ','.join('?' for _ in ids)
        records = c.execute(f'SELECT * FROM records WHERE asset_id IN ({placeholders}) ORDER BY created DESC,id', ids).fetchall()
        result['records'] = [dict(id=r['id'], asset_id=r['asset_id'], source=r['source'], combo=json.loads(r['combo']),
                                  metadata_status='unreadable' if r['source'] == 'unreadable' else 'image_only' if not json.loads(r['request']) else 'available',
                                  warnings=json.loads(r['warnings']), **({'request': json.loads(r['request'])} if detail else {})) for r in records]
        if detail:
            result['sources'] = [dict(asset_id=r['asset_id'], path=r['path'], source_url=r['source_url'], available=Path(r['path']).is_file())
                                 for r in c.execute(f'SELECT asset_id,path,source_url FROM sources WHERE asset_id IN ({placeholders})', ids)]
        return result

    def detail(self, identity, *, group=False):
        if not isinstance(identity, str) or not re.fullmatch('[0-9a-f]{64}', identity):
            raise ValueError('이미지 ID가 잘못되었습니다.')
        with self.connect() as c:
            row = c.execute('SELECT * FROM assets WHERE id=?', (identity,)).fetchone()
            if row is None:
                raise ValueError('등록된 이미지를 찾을 수 없습니다.')
            return self._item(c, row, True, group=group)

    def browse(self, query='', offset=0, limit=48, combo='', favorite=False):
        if type(offset) is not int or offset < 0:
            raise ValueError('목록 위치는 0 이상의 정수여야 합니다.')
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
            total = c.execute('SELECT count(*) FROM (' + sql + ')', params).fetchone()[0]
            rows = c.execute(sql + ' ORDER BY a.created DESC,a.id LIMIT ? OFFSET ?',
                             [*params, limit, min(offset, 2**63 - 1)]).fetchall()
            return {'items': [self._item(c, row) for row in rows], 'total': total}

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
            try:
                if path.is_file() and path.stat().st_size <= 32 * 1024 * 1024 and hashlib.sha256(path.read_bytes()).hexdigest() == identity:
                    return path
            except OSError:
                continue
        raise ValueError('원본 파일이 없거나 변경되었습니다. 폴더를 다시 가져와 주세요.')

    def _matrix(self, c, contract, rows, mode):
        revision = c.execute("SELECT value FROM settings WHERE key='retrieval_revision'").fetchone()[0]
        key = (contract, revision)
        with self._cache_lock:
            cached = self._vector_cache.get(key)
            if cached is not None:
                return cached
            if mode == 'vrs':
                indexed = {r['asset_id']: json.loads(r['vector']) for r in c.execute(
                    'SELECT asset_id,vector FROM vectors WHERE contract=?', (contract,))}
                if not indexed:
                    raise ValueError('VRS 색인을 먼저 준비해 주세요.')
                rows = [r for r in rows if r['id'] in indexed]
                candidates = [indexed[r['id']] for r in rows]
            else:
                candidates = [json.loads(r['vector']) for r in rows]
            if candidates and len({len(v) for v in candidates}) != 1:
                raise ValueError('VRS_VECTOR_DIMENSION: 벡터 차원이 다릅니다. 색인을 확인해 주세요.')
            matrix = np.asarray([unit(v) for v in candidates], dtype=np.float32)
            matrix.setflags(write=False)
            ids = {r['id']: i for i, r in enumerate(rows)}
            # Two modes; never accumulate old corpus or encoder versions.
            self._vector_cache = {k: v for k, v in self._vector_cache.items()
                                  if k[1] == revision and k[0] != contract}
            if len(self._vector_cache) >= 2:
                self._vector_cache.clear()
            self._vector_cache[key] = (ids, matrix)
            return ids, matrix

    def close(self):
        self.vrs.close()

    @contextmanager
    def vrs_operation(self):
        with self._vrs_settings_lock:
            if not self.vrs_enabled:
                raise ValueError('VRS가 꺼져 있습니다. 연결 · 준비에서 켜 주세요.')
            yield

    def set_vrs_enabled(self, enabled):
        if type(enabled) is not bool:
            raise ValueError('VRS 사용 여부는 켜기 또는 끄기로 지정해 주세요.')
        busy = '작업이 끝난 후 VRS 설정을 변경해 주세요. 색인은 먼저 취소할 수 있습니다.'
        if not self._vrs_settings_lock.acquire(blocking=False):
            raise ValueError(busy)
        try:
            if enabled == self.vrs_enabled:
                return {'enabled': enabled}
            with self.state_lock:
                if self.job.get('status') == 'running' and self.job.get('kind') == 'vrs':
                    raise ValueError(busy)
            options = {'owner': self.vrs} if isinstance(self.generation_lock, GPUWorkLock) else {}
            if not self.generation_lock.acquire(blocking=False, **options):
                raise ValueError(busy)
            try:
                if not enabled:
                    self.vrs.close()
                with self.connect() as c:
                    c.execute("INSERT OR REPLACE INTO settings VALUES('vrs_enabled',?)", ('1' if enabled else '0',))
                self.vrs_enabled = enabled
                if not enabled:
                    with self._cache_lock:
                        self._vector_cache.clear()
            finally:
                self.generation_lock.release()
            return {'enabled': enabled}
        finally:
            self._vrs_settings_lock.release()

    def prepare_vrs(self):
        with self.vrs_operation():
            return self.vrs.runtime.start()

    def search(self, *, identity=None, image=None, mode='visual', limit=24, ranking='similar'):
        with self.vrs_operation() if mode == 'vrs' else nullcontext():
            return self._search(identity=identity, image=image, mode=mode, limit=limit, ranking=ranking)

    def _search(self, *, identity=None, image=None, mode='visual', limit=24, ranking='similar'):
        bounded(limit, 1, 100)
        if mode not in ('visual', 'vrs'):
            raise ValueError('검색 모드를 확인해 주세요.')
        if ranking not in ('similar', 'diverse'):
            raise ValueError('검색 정렬을 확인해 주세요.')
        if identity is not None:
            self.detail(identity)
        with self.connect() as c:
            # Matrix revision and rows must describe the same SQLite snapshot.
            c.execute('BEGIN')
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
            total_assets = len(rows)
            if mode == 'vrs':
                contract = self.vrs.contract
                if not contract:
                    raise ValueError('VRS 인코더 설정이 필요합니다.')
                indexed, matrix = self._matrix(c, contract, rows, mode)
                if identity in indexed:
                    vector = matrix[indexed[identity]]
                else:
                    lock_options = {'owner': self.vrs} if isinstance(self.generation_lock, GPUWorkLock) else {}
                    if not self.generation_lock.acquire(blocking=False, **lock_options):
                        raise ValueError('생성 또는 모델 처리가 진행 중입니다.')
                    try:
                        vector = self.vrs.encode([self._original(identity) if identity else Path(image)], self.root / 'scratch')[0]
                    finally:
                        self.generation_lock.release()
                rows = [r for r in rows if r['id'] in indexed]
            else:
                _, matrix = self._matrix(c, contract, rows, mode)
            ranked = []
            adjustments = library_core.ranking_adjustments(c, pixel_hash, contract)
            if len(matrix):
                if matrix.shape[1] != len(vector):
                    raise ValueError('VRS_VECTOR_DIMENSION: 벡터 차원이 다릅니다. 색인을 확인해 주세요.')
                scores = matrix @ unit(vector)
                order = library_core.rank_cases(rows, scores, matrix, pixel_hash, adjustments, limit, ranking)
                ranked = [(rows[i], scores[i]) for i in order]
            selected, seen = [], {pixel_hash}
            for row, score in ranked:
                if row['pixel_hash'] in seen:
                    continue
                seen.add(row['pixel_hash'])
                selected.append({**self._item(c, row, group=True), 'score': round(float(score), 6),
                    'ranking_adjustment': adjustments.get(row['pixel_hash'], 0.0),
                    'evidence': library_core.assess(c, pixel_hash, row['pixel_hash'], contract)})
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
            # End the read snapshot before writing: a concurrent import or
            # evaluation must not cause SQLITE_BUSY_SNAPSHOT on upgrade.
            c.commit()
            c.execute('INSERT INTO queries VALUES(?,?,?,?,?)', (query_id, pixel_hash, contract,
                      dump([i['id'] for i in selected]), time.time()))
            return dict(query_id=query_id, contract=contract, mode=mode, ranking=ranking, items=selected, combinations=list(groups.values()),
                        excluded_identical_pixels=True, total_indexed=len(rows), total_assets=total_assets,
                        partial_index=len(rows) < total_assets)

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
            query = c.execute('SELECT * FROM queries WHERE id=?', (query_id,)).fetchone()
            if not query or identity not in json.loads(query['results']):
                raise ValueError('이 검색에서 나온 사례만 평가할 수 있습니다.')
            now = time.time()
            c.execute('''INSERT INTO feedback VALUES(?,?,?,?,?) ON CONFLICT(query_id,asset_id) DO UPDATE SET
                         visual=coalesce(excluded.visual,feedback.visual),reuse=coalesce(excluded.reuse,feedback.reuse),created=excluded.created''',
                      (query_id, identity, visual, reuse, now))
            c.execute('''INSERT INTO feedback_times VALUES(?,?,?,?)
                ON CONFLICT(query_id,asset_id) DO UPDATE SET
                visual_updated=coalesce(excluded.visual_updated,feedback_times.visual_updated),
                reuse_updated=coalesce(excluded.reuse_updated,feedback_times.reuse_updated)''',
                (query_id, identity, now if visual is not None else None, now if reuse is not None else None))
            pixel = c.execute('SELECT pixel_hash FROM assets WHERE id=?', (identity,)).fetchone()[0]
            receipt = library_core.assess(c, query['pixel_hash'], pixel, query['contract'])
            c.execute('INSERT OR REPLACE INTO core_receipts VALUES(?,?,?,?,?)',
                      (query_id, identity, library_core.CONTRACT, dump(receipt), time.time()))
        return {'status': 'saved', 'training': False, 'evidence': receipt}

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
        with self.vrs_operation() if data.get('kind') == 'vrs' else nullcontext():
            return self._start(data)

    def _start(self, data):
        kind = data.get('kind', 'import')
        if kind not in ('import', 'sync', 'vrs'):
            raise ValueError('지원하지 않는 작업입니다.')
        # Optional per-job budget; the library itself has no item-count ceiling.
        limit = data.get('limit')
        if limit is not None and (type(limit) is not int or limit < 1):
            raise ValueError('가져오기 개수는 1 이상의 정수여야 합니다.')
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

    def sync(self, limit=None):
        count = 0
        for path in sorted(self.paths.manifest_root.glob('*.json')):
            if self.cancelled.is_set() or (limit is not None and count >= limit):
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
                if not self.generation_lock.acquire(blocking=False):
                    break
                try:
                    identity, state = self.ingest(image, manifest)
                    with self.connect() as c:
                        c.execute('INSERT OR REPLACE INTO synced_manifests VALUES(?,?,?,?,?)', (str(path), *signature))
                finally:
                    self.generation_lock.release()
                count += 1
            except (ValueError, OSError, TypeError, AttributeError):
                continue
        return count

    def _image_paths(self, root):
        # Walk lazily so a large folder does not require a full path list first.
        for folder, dirs, names in os.walk(root, followlinks=False):
            dirs[:] = sorted(d for d in dirs if not d.startswith('.') and d not in {'thumbnails', 'models', 'node_modules'})
            for name in sorted(names):
                if self.cancelled.is_set():
                    return
                path = Path(folder) / name
                if path.suffix.lower() in EXTENSIONS and not path.is_symlink():
                    yield path

    def _run(self, kind, roots, limit):
        try:
            if kind == 'vrs':
                self.build_vrs()
            elif kind == 'sync':
                self._progress(processed=self.sync(limit))
            else:
                groups = [self._image_paths(root) for root in roots]
                processed = added = errors = 0
                while groups and (limit is None or processed < limit) and not self.cancelled.is_set():
                    for group in groups[:]:
                        if (limit is not None and processed >= limit) or self.cancelled.is_set():
                            break
                        path = next(group, None)
                        if path is None:
                            groups.remove(group)
                            continue
                        try:
                            _, state = self.ingest(path)
                            added += state == 'added'
                        except (ValueError, OSError, TypeError, OverflowError, SyntaxError) as exc:
                            errors += 1
                            with self.connect() as c:
                                c.execute('INSERT OR REPLACE INTO import_issues VALUES(?,?,?,?)',
                                          (str(path), 'IMAGE_IMPORT', str(exc)[:300], time.time()))
                            self._progress(message=f'{path.name}: {str(exc)[:150]}')
                        processed += 1
                        self._progress(processed=processed, added=added, errors=errors)
            self._progress(status='cancelled' if self.cancelled.is_set() else 'complete')
        except VRSIndexCancelled:
            self._progress(status='cancelled')
        except Exception as exc:
            self._progress(status='failed', message=str(exc)[:300])
        finally:
            self.import_lock.release()

    def build_vrs(self):
        with self.vrs_operation():
            self._build_vrs()

    def _build_vrs(self):
        contract = self.vrs.contract
        if not contract:
            raise ValueError('VRS 인코더를 먼저 설정해 주세요.')
        if not self.generation_lock.acquire(blocking=False):
            raise ValueError('생성 또는 모델 처리가 진행 중입니다.')
        try:
            with self.connect() as c:
                ids = [r[0] for r in c.execute('SELECT id FROM assets WHERE id NOT IN (SELECT asset_id FROM vectors WHERE contract=?) ORDER BY id', (contract,))]
                prior = c.execute('SELECT vector FROM vectors WHERE contract=? LIMIT 1', (contract,)).fetchone()
                dimension = len(json.loads(prior[0])) if prior else None
            with self.vrs.session() if hasattr(self.vrs, 'session') else nullcontext():
                for offset in range(0, len(ids), 8):
                    if self.cancelled.is_set():
                        raise VRSIndexCancelled()
                    batch, paths = [], []
                    for identity in ids[offset:offset + 8]:
                        try:
                            path = self._original(identity)
                        except (ValueError, OSError) as exc:
                            with self.connect() as c:
                                c.execute('INSERT OR REPLACE INTO index_issues VALUES(?,?,?,?,?)',
                                          (identity, contract, 'missing_source', str(exc)[:300], time.time()))
                            continue
                        try:
                            read_pixels(path)
                        except (ValueError, OSError) as exc:
                            with self.connect() as c:
                                c.execute('INSERT OR REPLACE INTO index_issues VALUES(?,?,?,?,?)',
                                          (identity, contract, 'index_error', str(exc)[:300], time.time()))
                            continue
                        batch.append(identity)
                        paths.append(path)
                    if not batch:
                        self._progress(processed=min(offset + 8, len(ids)))
                        continue
                    vectors = self.vrs.encode(paths, self.root / 'scratch', self.cancelled.is_set)
                    if len(vectors) != len(batch):
                        raise ValueError('VRS 벡터 개수가 올바르지 않습니다.')
                    dimension = dimension or len(vectors[0])
                    if any(len(v) != dimension for v in vectors):
                        raise ValueError('VRS_VECTOR_DIMENSION: 벡터 차원이 다릅니다.')
                    vectors = [unit(v).tolist() for v in vectors]
                    if self.vrs.contract != contract:
                        raise ValueError('인코더 설정이 변경되었습니다. 색인을 다시 시작해 주세요.')
                    with self.connect() as c:
                        c.executemany('INSERT OR REPLACE INTO vectors VALUES(?,?,?)',
                                      [(i, contract, dump(v)) for i, v in zip(batch, vectors)])
                        c.executemany('DELETE FROM index_issues WHERE asset_id=? AND contract=?', [(i, contract) for i in batch])
                    self._progress(processed=min(offset + 8, len(ids)))
        finally:
            self.generation_lock.release()

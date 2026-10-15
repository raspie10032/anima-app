"""HTTP transport for the local-only library; uses the server's origin guard."""
import re
import time
import threading
from urllib.parse import parse_qs

from anima_app.library import Library
from anima_app.library_visual import MAX_IMAGE_BYTES


class LibraryHTTP:
    def __init__(self, paths, generation_lock):
        self.paths = paths
        self.generation_lock = generation_lock
        self._library = None
        self.last_sync = 0
        self.init_lock = threading.Lock()

    @property
    def library(self):
        if self._library is None:
            # Database browsing must remain available during generation.
            with self.init_lock:
                if self._library is None:
                    self._library = Library(self.paths, self.generation_lock)
        return self._library

    def handle(self, handler, parsed, method):
        route = parsed.path.removeprefix('/api/library/')
        try:
            lib = self.library
            query = parse_qs(parsed.query)
            if method == 'GET':
                if route in ('status', 'items') and time.monotonic() - self.last_sync > 30 and not lib.import_lock.locked() and not self.generation_lock.locked():
                    self.last_sync = time.monotonic()
                    lib.start({'kind': 'sync', 'limit': 32})
                if route == 'status':
                    result = lib.status()
                elif route == 'items':
                    result = lib.browse(query.get('q', [''])[0], int(query.get('offset', ['0'])[0]),
                                        combo=query.get('combo', [''])[0], favorite=query.get('favorite', ['0'])[0] == '1')
                elif route.startswith('item/'):
                    result = lib.detail(route.removeprefix('item/'), group=query.get('group') == ['1'])
                elif route.startswith('preview/'):
                    handler._send_bytes(200, lib.preview(route.removeprefix('preview/')), 'image/jpeg')
                    return
                elif route.startswith('thumbnail/'):
                    identity = route.removeprefix('thumbnail/')
                    if not re.fullmatch('[0-9a-f]{64}', identity):
                        raise ValueError('이미지 ID가 잘못되었습니다.')
                    handler._send_bytes(200, (lib.thumbs / (identity + '.jpg')).read_bytes(), 'image/jpeg')
                    return
                else:
                    handler._send_json(404, {'error': 'not found'})
                    return
            elif route == 'query-image':
                temporary = handler._read_upload_body(root=lib.root / 'scratch', maximum_bytes=MAX_IMAGE_BYTES,
                    allowed_content_types={'image/png', 'image/jpeg', 'image/webp'})
                if temporary is None:
                    return
                try:
                    result = lib.search(image=temporary, mode=query.get('mode', ['visual'])[0],
                                        ranking=query.get('ranking', ['similar'])[0])
                finally:
                    temporary.unlink(missing_ok=True)
            else:
                data = handler._read_json_object()
                if data is None:
                    return
                if route == 'import':
                    result = lib.start(data)
                elif route == 'cancel':
                    result = lib.cancel()
                elif route == 'search':
                    result = lib.search(identity=data.get('id'), mode=data.get('mode', 'visual'), limit=data.get('limit', 24),
                                        ranking=data.get('ranking', 'similar'))
                elif route == 'annotate':
                    result = lib.annotate(data)
                elif route == 'feedback':
                    result = lib.feedback(data)
                elif route == 'compare':
                    result = lib.compare(data)
                elif route == 'compare/undo':
                    result = lib.undo_comparison(data)
                else:
                    handler._send_json(404, {'error': 'not found'})
                    return
            handler._send_json(200, result)
        except (ValueError, OSError, TypeError) as exc:
            handler._send_json(400, {'error': str(exc), 'error_code': 'library_invalid'})

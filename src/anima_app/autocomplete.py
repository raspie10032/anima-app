from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Any

from anima_app.config import AppPaths


DEFAULT_AUTOCOMPLETE_LIMIT = 24
MAX_AUTOCOMPLETE_LIMIT = 100


@dataclass(frozen=True)
class AutocompleteEntry:
    value: str
    count: int


@dataclass(frozen=True)
class AutocompleteIndex:
    source_path: Path
    signature: tuple[int, int] | None
    entries: tuple[AutocompleteEntry, ...]


_index_lock = Lock()
_cached_index: AutocompleteIndex | None = None


def warm_autocomplete_index(paths: AppPaths) -> AutocompleteIndex:
    """Load the autocomplete file into RAM for repeated GUI lookups."""
    return _load_index(paths.autocomplete_source)


def autocomplete_payload(paths: AppPaths, *, query: str = "", limit: int = DEFAULT_AUTOCOMPLETE_LIMIT) -> dict[str, Any]:
    index = _load_index(paths.autocomplete_source)
    bounded_limit = max(1, min(int(limit), MAX_AUTOCOMPLETE_LIMIT))
    normalized_query = _normalize_query(query)
    items = _match_entries(index.entries, normalized_query, bounded_limit)
    return {
        "ready": bool(index.entries),
        "source_path": str(index.source_path),
        "count": len(index.entries),
        "query": normalized_query,
        "limit": bounded_limit,
        "items": [
            {
                "value": entry.value,
                "label": entry.value.replace("_", " "),
                "count": entry.count,
            }
            for entry in items
        ],
    }


def _load_index(path: Path) -> AutocompleteIndex:
    global _cached_index
    source_path = path.expanduser()
    signature = _file_signature(source_path)
    with _index_lock:
        if _cached_index and _cached_index.source_path == source_path and _cached_index.signature == signature:
            return _cached_index
        entries = tuple(_read_entries(source_path)) if signature else ()
        _cached_index = AutocompleteIndex(source_path=source_path, signature=signature, entries=entries)
        return _cached_index


def _file_signature(path: Path) -> tuple[int, int] | None:
    try:
        stat = path.stat()
    except OSError:
        return None
    return stat.st_mtime_ns, stat.st_size


def _read_entries(path: Path) -> list[AutocompleteEntry]:
    entries: list[AutocompleteEntry] = []
    seen: set[str] = set()
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            tag, _, raw_count = line.partition(",")
            value = tag.strip()
            if not value or value in seen:
                continue
            seen.add(value)
            entries.append(AutocompleteEntry(value=value, count=_parse_count(raw_count)))
    return entries


def _parse_count(raw_count: str) -> int:
    try:
        return max(0, int(raw_count.strip()))
    except ValueError:
        return 0


def _normalize_query(query: str) -> str:
    return query.strip().lower().replace(" ", "_")


def _match_entries(entries: tuple[AutocompleteEntry, ...], query: str, limit: int) -> list[AutocompleteEntry]:
    if not query:
        return list(entries[:limit])

    prefix_matches: list[AutocompleteEntry] = []
    substring_matches: list[AutocompleteEntry] = []
    for entry in entries:
        value = entry.value.lower()
        if value.startswith(query):
            prefix_matches.append(entry)
        elif query in value:
            substring_matches.append(entry)
        if len(prefix_matches) >= limit:
            break

    if len(prefix_matches) >= limit:
        return prefix_matches[:limit]

    remaining = limit - len(prefix_matches)
    return prefix_matches + substring_matches[:remaining]

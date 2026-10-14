"""Offline exact matching against an explicitly downloaded artist-tag catalog."""
from __future__ import annotations

from functools import lru_cache
import hashlib
import json
import re


def catalog_path(paths):
    return paths.output_root / "artist-catalog" / "danbooru.json"


def name_key(text):
    return re.sub(r"[ _]+", "_", re.sub(r"\\([()\[\]{}])", r"\1", text).strip().lower())


@lru_cache(maxsize=4)
def _read(path, modified, size):
    if size > 40_000_000:
        raise ValueError("Artist catalog exceeds size limit")
    raw = path.read_bytes()
    data = json.loads(raw)
    if not isinstance(data, dict) or data.get("version") != 1 or not isinstance(data.get("tags"), list):
        raise ValueError("Unsupported artist catalog")
    names = {name_key(row["name"]): row["name"] for row in data["tags"]
             if isinstance(row, dict) and row.get("category") == 1 and not row.get("is_deprecated")
             and isinstance(row.get("name"), str) and 0 < len(row["name"]) <= 300}
    return {"names": names, "count": len(names), "fetched_at": data.get("fetched_at"),
            "source": data.get("source"), "coverage": data.get("coverage", "partial"),
            "sha256": hashlib.sha256(raw).hexdigest()}


def load_catalog(paths):
    if paths is None:
        return {"names": {}, "count": 0, "coverage": "missing"}
    path = catalog_path(paths)
    try:
        stat = path.stat()
        return _read(path, stat.st_mtime_ns, stat.st_size)
    except (OSError, ValueError, TypeError, KeyError):
        return {"names": {}, "count": 0, "coverage": "missing"}


def mark_bare_artists(text, names):
    """Insert artist: only into whole unprefixed tags; retain syntax verbatim."""
    recognized = []

    def visit(part, depth=0):
        if depth > 64:
            raise ValueError("작가 태그 중첩이 너무 깊습니다.")
        # Split only outside scopes, retaining whitespace and escaped names.
        boundaries, stack, escaped = [], [], False
        for i, char in enumerate(part):
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char in "([{":
                stack.append(char)
            elif char in ")]}" and stack:
                stack.pop()
            elif char == "," and not stack:
                boundaries.append(i)
        if boundaries:
            start, chunks = 0, []
            for end in [*boundaries, len(part)]:
                chunks.append(visit(part[start:end], depth + 1))
                start = end + 1
            return ",".join(chunks)
        core = part.strip()
        leading = part[:len(part) - len(part.lstrip())]
        trailing = part[len(part.rstrip()):]
        if not core or core.lower().startswith("artist:") or core.startswith("@"):
            return part
        canonical = names.get(name_key(core))
        if canonical:
            recognized.append({"input": core, "tag": canonical})
            return leading + "artist:" + core + trailing
        # Peel a weight or emphasis wrapper; never guess part of a sentence.
        opening = re.match(r"-?\d+(?:\.\d+)?::", core)
        if opening:
            return leading + opening[0] + visit(core[opening.end():], depth + 1) + trailing
        if core.endswith("::"):
            return leading + visit(core[:-2], depth + 1) + "::" + trailing
        for left, right in [("(", ")"), ("{", "}"), ("[", "]")]:
            if core.startswith(left) and core.endswith(right) and not core.endswith("\\" + right):
                inner, suffix = core[1:-1], ""
                if left == "(":
                    weight = re.search(r":-?\d+(?:\.\d+)?\s*$", inner)
                    if weight:
                        inner, suffix = inner[:weight.start()], weight[0]
                return leading + left + visit(inner, depth + 1) + suffix + right + trailing
        return part

    return (visit(text), recognized) if names else (text, [])

# SPDX-License-Identifier: GPL-3.0-only
# Copyright (c) 2025 raspie10032

import math
import re

from anima_app.providers.novelai.requests import reject_credentials
from anima_app.requests import MAX_PROMPT_CHARACTERS

# ---------------------------------------------------------------------------
# Shared helpers
#
# A single intermediate representation (a list of ``(text, weight)`` tags,
# commas being tag separators in every syntax) backs all six converters.
# Each format has one parser and one serializer; the node classes are thin
# wrappers. This removes the duplicated, partly-contradictory exception
# handling that used to live in every class.
# ---------------------------------------------------------------------------

_ARTIST_TOKEN = "__artist__"
_DEFAULT_WEIGHT = 1.1
_WEIGHT_MIN, _WEIGHT_MAX = -5.0, 5.0

# Strict number: rejects "1.2.3", "--", "." that the old "[\d.-]+" accepted.
_STRICT_NUM = re.compile(r"-?\d+(?:\.\d+)?")
# Trailing ":<number-ish>" probe (lenient on purpose, see _trailing_weight).
_TRAILING_WEIGHT = re.compile(r":([\d.-]+)\s*$")
# A NovelAI V4 scope opener at a tag boundary: "<number>::".
_V4_OPEN = re.compile(r"^\s*(-?\d+(?:\.\d+)?)::")


def _guard_artist(text):
    """Hide the colon in ``artist:`` so it is never read as a weight marker."""
    return text.replace("artist:", _ARTIST_TOKEN)


def _restore_artist(text):
    return text.replace(_ARTIST_TOKEN, "artist:")


def _strict_float(token):
    """Return ``float(token)`` only if ``token`` is a well-formed number."""
    token = token.strip()
    if _STRICT_NUM.fullmatch(token):
        try:
            return float(token)
        except ValueError:
            return None
    return None


def _format_weight(value):
    """Compact numeric form: ``1.0500 -> 1.05``, ``-1.5000 -> -1.5``."""
    return f"{value:.4f}".rstrip("0").rstrip(".")


def _closest_power(weight, base):
    """Nearest integer exponent ``n`` so that ``base ** n ~= weight``."""
    if weight <= 0 or base <= 0 or base == 1:
        return 0
    return round(math.log(weight) / math.log(base))


# ---------------------------------------------------------------------------
# ComfyUI  <->  IR
# ---------------------------------------------------------------------------


def _split_top_level(text):
    """Split on commas that are not escaped and not inside parentheses."""
    parts, buf, depth, i = [], [], 0, 0
    while i < len(text):
        ch = text[i]
        if ch == "\\" and i + 1 < len(text) and text[i + 1] in "()":
            buf.append(text[i:i + 2])
            i += 2
            continue
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        elif ch == "," and depth == 0:
            parts.append("".join(buf))
            buf = []
            i += 1
            continue
        buf.append(ch)
        i += 1
    parts.append("".join(buf))
    return parts


def _matches_outer_paren(segment):
    depth, i = 0, 0
    while i < len(segment):
        ch = segment[i]
        if ch == "\\" and i + 1 < len(segment) and segment[i + 1] in "()":
            i += 2
            continue
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return i == len(segment) - 1
        i += 1
    return False


def _trailing_weight(inner):
    """Return ``(weight_token, body)`` if ``inner`` ends with ``:<num>``.

    Uses the lenient probe so a malformed ``1.2.3`` is still detected and
    then rejected by the strict float check, preserving the historical
    fallback (keep the whole inner text, default weight).
    """
    m = _TRAILING_WEIGHT.search(inner)
    if not m:
        return None, inner
    return m.group(1), inner[:m.start()].strip()


def _eval_comfy_segment(segment):
    """Resolve one comma-segment into ``(text, weight)`` or ``None``.

    ComfyUI nesting: every bare ``(...)`` level multiplies by the 1.1
    default while an explicit ``(...:w)`` level multiplies by ``w``.
    Escaped ``\\(`` / ``\\)`` are literal characters, not group markers.
    """
    segment = segment.strip()
    if not segment:
        return None

    if segment.startswith("(") and _matches_outer_paren(segment):
        inner = segment[1:-1]
        token, body = _trailing_weight(inner)

        has_valid_explicit_weight = False
        if token is None:
            level_weight, child_text = _DEFAULT_WEIGHT, inner
        else:
            parsed = _strict_float(token)
            if parsed is None:
                level_weight, child_text = _DEFAULT_WEIGHT, inner
            elif not (_WEIGHT_MIN <= parsed <= _WEIGHT_MAX):
                level_weight, child_text = _DEFAULT_WEIGHT, body
            else:
                level_weight, child_text = parsed, body
                has_valid_explicit_weight = True

        child = _eval_comfy_segment(child_text)
        if child is None:
            return None
        inner_text, inner_weight = child
        # A resolved paren group whose text still holds a colon means an
        # unescaped literal "(" with a non-numeric ":" (e.g. "(tag:o)" that
        # should have been "\(tag:o\)"). artist: is already guarded, so any
        # remaining colon is a malformed group -> drop it entirely.
        if not inner_text or (":" in inner_text and not has_valid_explicit_weight):
            return None
        return (inner_text, level_weight * inner_weight)

    return (segment.replace("\\(", "(").replace("\\)", ")"), 1.0)


def parse_comfyui(text):
    tags = []
    for segment in _split_top_level(_guard_artist(text)):
        if segment.strip() == "":
            tags.append(("", 1.0))  # preserve empty slots ("a, , b")
            continue
        resolved = _eval_comfy_segment(segment)
        if resolved is not None:  # drop fully empty groups "()"
            tags.append(resolved)
    return tags


def to_comfyui(tags):
    parts = []
    for text, weight in tags:
        escaped = text.replace("(", r"\(").replace(")", r"\)")
        if weight == 1.0:
            parts.append(escaped)
        else:
            parts.append(f"({escaped}:{_format_weight(weight)})")
    return _restore_artist(", ".join(parts))


# ---------------------------------------------------------------------------
# NovelAI V4  <->  IR
# ---------------------------------------------------------------------------


def parse_naiv4(text):
    """Parse NovelAI V4 numeric-scope syntax into IR.

    Rules (per the README spec):
      - commas separate tags;
      - ``<w>::`` at a tag boundary opens a numeric scope;
      - a closing ``::`` ends the active scope after the current tag;
      - an opened scope with no closing ``::`` applies forward to all
        following comma-separated tags.

    The intentional space before a closing ``::`` (the guard that stops a
    trailing number being read as a weight) is handled naturally: the
    opener is matched only at a tag boundary, so ``team 5 ::`` is a close.
    """
    guarded = _guard_artist(text)
    tags = []
    current_weight = 1.0
    scope_active = False

    for chunk in guarded.split(","):
        open_match = _V4_OPEN.match(chunk)
        if open_match:
            value = _strict_float(open_match.group(1))
            if value is not None:
                current_weight = value
                scope_active = True
                chunk = chunk[open_match.end():]

        if "::" in chunk:
            content = chunk.split("::", 1)[0].strip()
            weight = current_weight if scope_active else 1.0
            if content:
                tags.append((content, weight))
            current_weight, scope_active = 1.0, False
        else:
            content = chunk.strip()
            weight = current_weight if scope_active else 1.0
            tags.append((content, weight))

    return tags


def to_naiv4(tags):
    """Serialize IR to V4, merging consecutive same-weight tags into one
    scope (``1.05::a ::, 1.05::b ::`` -> ``1.05::a, b ::``)."""
    out, i, n = [], 0, len(tags)
    while i < n:
        text, weight = tags[i]
        if weight == 1.0:
            out.append(text)
            i += 1
            continue
        group = []
        while i < n and tags[i][1] == weight:
            group.append(tags[i][0])
            i += 1
        out.append(f"{_format_weight(weight)}::{', '.join(group)} ::")
    return _restore_artist(", ".join(out))


# ---------------------------------------------------------------------------
# Old NAI  <->  IR
#
# Brace/bracket power math and its 2-decimal display are preserved exactly;
# weights are rounded to 2 decimals at parse time so the V4 serializer
# reproduces the historical strings (1.05**3 -> "1.16", etc.).
# ---------------------------------------------------------------------------


def parse_oldnai(text):
    """Character-level scope parser for old NovelAI brace/bracket syntax.

    - ``{`` / ``[`` open a forward 1.05x / 0.95x scope to the matching
      ``}`` / ``]``;
    - an unmatched closing ``}`` / ``]`` applies 1.05x / 0.95x backward to
      all already-parsed tags;
    - mixed ``{[tag]}`` multiplies the factors (1.05 * 0.95);
    - a tag's weight is snapshotted from the scope active when its text
      begins.
    """
    guarded = _guard_artist(text)
    tags = []
    stack = []           # list of factors for currently-open { or [
    buf = []
    snapshot = None      # weight captured at the start of the current tag

    def cur_product():
        p = 1.0
        for f in stack:
            p *= f
        return p

    def flush():
        nonlocal buf, snapshot
        content = "".join(buf).strip()
        if content:
            tags.append([content, round(snapshot if snapshot is not None else cur_product(), 2)])
        buf = []
        snapshot = None

    def note_char(ch):
        nonlocal snapshot
        if snapshot is None and ch.strip():
            snapshot = cur_product()
        buf.append(ch)

    for ch in guarded:
        if ch == "{":
            stack.append(1.05)
        elif ch == "[":
            stack.append(0.95)
        elif ch == "}":
            if 1.05 in stack:
                # close the nearest open "{"
                for k in range(len(stack) - 1, -1, -1):
                    if stack[k] == 1.05:
                        del stack[k]
                        break
            else:
                for t in tags:
                    t[1] = round(t[1] * 1.05, 2)
        elif ch == "]":
            if 0.95 in stack:
                for k in range(len(stack) - 1, -1, -1):
                    if stack[k] == 0.95:
                        del stack[k]
                        break
            else:
                for t in tags:
                    t[1] = round(t[1] * 0.95, 2)
        elif ch == ",":
            flush()
        else:
            note_char(ch)

    flush()
    return [(t[0], t[1]) for t in tags]


def _oldnai_encoding(weight, text):
    """Return ``(signature, open_str, close_str)`` for one tag.

    ``signature`` groups mergeable neighbors; ``None`` means "plain text".
    Power math and the negative/zero fallback are unchanged.
    """
    if weight <= 0:
        return ("neg", "[", "]")
    if weight < 1:
        n = _closest_power(weight, 0.95)
        return (("sq", n), "[" * n, "]" * n) if n > 0 else (None, "", "")
    if weight == 1:
        return (None, "", "")
    n = _closest_power(weight, 1.05)
    return (("cu", n), "{" * n, "}" * n) if n > 0 else (None, "", "")


def to_oldnai(tags):
    """Serialize IR to old NAI, merging neighbors with identical bracketing
    (``{tag1}, {tag2}`` -> ``{tag1, tag2}``)."""
    encoded = [(text,) + _oldnai_encoding(weight, text) for text, weight in tags]
    out, i, n = [], 0, len(encoded)
    while i < n:
        text, sig, open_s, close_s = encoded[i]
        if sig is None:
            out.append(text)
            i += 1
            continue
        group = []
        while i < n and encoded[i][1] == sig:
            group.append(encoded[i][0])
            i += 1
        out.append(f"{open_s}{', '.join(group)}{close_s}")
    return _restore_artist(", ".join(out))


def convert_prompt(payload: dict[str, object]) -> dict[str, object]:
    """Six node conversions, bounded for HTTP use, with explicit lossy warnings."""
    reject_credentials(payload)
    if payload.keys() - {"source", "target", "text"}:
        raise ValueError("Prompt conversion accepts only source, target and text")
    parsers = {"comfyui": parse_comfyui, "naiv4": parse_naiv4, "oldnai": parse_oldnai}
    serializers = {"comfyui": to_comfyui, "naiv4": to_naiv4, "oldnai": to_oldnai}
    source, target, text = payload.get("source"), payload.get("target"), payload.get("text")
    if not isinstance(source, str) or not isinstance(target, str) or source not in parsers or target not in serializers or source == target:
        raise ValueError("Choose two different formats: comfyui, naiv4 or oldnai")
    if not isinstance(text, str) or len(text) > MAX_PROMPT_CHARACTERS:
        raise ValueError("Prompt conversion exceeds the supported text length")
    depth = 0
    for char in text:
        if char in "({[":
            depth += 1
            if depth > 64:
                raise ValueError("Prompt conversion supports at most 64 nested scopes")
        elif char in ")}]":
            depth = max(0, depth - 1)
    tags = parsers[source](text)
    if any(not math.isfinite(weight) for _, weight in tags):
        raise ValueError("Prompt weight must be finite")
    converted = serializers[target](tags)
    if len(converted) > MAX_PROMPT_CHARACTERS:
        raise ValueError("Converted prompt exceeds the supported text length")
    notices = []
    if target == "oldnai":
        notices.append("구형 NAI는 1.05/0.95 배수로 근사합니다. 0·음수 가중치는 [태그]로 대체됩니다.")
    if source == "oldnai":
        notices.append("구형 NAI 가중치는 기존 노드와 같이 소수 둘째 자리로 반올림합니다.")
    if source == "comfyui":
        notices.append("기존 노드 규칙: 명시 가중치 범위는 -5~5이며 범위 밖은 1.1로 대체합니다. 잘못된 그룹은 제외될 수 있으니 미리보기를 확인하세요.")
    return {"source": source, "target": target, "original": text, "converted": converted, "warnings": notices}

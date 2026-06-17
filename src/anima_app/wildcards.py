from __future__ import annotations

import hashlib
import json
import random
import re
from dataclasses import dataclass
from dataclasses import replace
from typing import Any

from anima_app.config import AppPaths
from anima_app.requests import T2IRequest


WILDCARD_PATTERN = re.compile(r"__([A-Za-z0-9_-]+)__")
DEFAULT_WILDCARD_MODE = "random"
WILDCARD_MODES = {DEFAULT_WILDCARD_MODE, "sequential", "reverse"}


@dataclass(frozen=True)
class TextWildcardExpansion:
    text: str
    selections: tuple[dict[str, Any], ...]


def list_wildcards(paths: AppPaths) -> list[dict[str, Any]]:
    if not paths.wildcard_root.is_dir():
        return []
    items: list[dict[str, Any]] = []
    for path in sorted(paths.wildcard_root.glob("*.txt"), key=lambda item: item.name.lower()):
        name = path.stem
        values = _read_wildcard_values(name, paths)
        items.append(
            {
                "name": name,
                "token": f"__{name}__",
                "relative_path": path.name,
                "value_count": len(values),
            }
        )
    return items


def expand_request_wildcards(
    request: T2IRequest,
    *,
    paths: AppPaths,
    mode: str = DEFAULT_WILDCARD_MODE,
) -> tuple[T2IRequest, dict[str, Any]]:
    mode = _normalize_mode(mode)
    prompt = expand_text_wildcards(request.prompt, paths=paths, mode=mode, seed=request.seed)
    negative = expand_text_wildcards(request.negative_prompt, paths=paths, mode=mode, seed=request.seed, salt="negative")
    expanded = replace(request, prompt=prompt.text, negative_prompt=negative.text)
    selections = tuple(prompt.selections) + tuple(negative.selections)
    return expanded, {
        "enabled": bool(selections),
        "mode": mode,
        "original_prompt": request.prompt,
        "original_negative_prompt": request.negative_prompt,
        "prompt": expanded.prompt,
        "negative_prompt": expanded.negative_prompt,
        "selections": list(selections),
    }


def expand_text_wildcards(
    text: str,
    *,
    paths: AppPaths,
    mode: str,
    seed: int | None = None,
    salt: str = "prompt",
) -> TextWildcardExpansion:
    mode = _normalize_mode(mode)

    rng = _rng_for(seed=seed, text=text, salt=salt)
    state = _read_state(paths) if mode in {"sequential", "reverse"} else {}
    selections: list[dict[str, Any]] = []

    def replace_match(match: re.Match[str]) -> str:
        wildcard = match.group(1)
        values = _read_wildcard_values(wildcard, paths)
        index = _select_index(wildcard, values, mode=mode, paths=paths, state=state, rng=rng)
        value = values[index]
        selections.append(
            {
                "token": match.group(0),
                "wildcard": wildcard,
                "file": str(paths.wildcard_root / f"{wildcard}.txt"),
                "mode": mode,
                "index": index,
                "value": value,
            }
        )
        return value

    expanded = WILDCARD_PATTERN.sub(replace_match, text)
    if selections and mode in {"sequential", "reverse"}:
        _write_state(paths, state)
    return TextWildcardExpansion(text=expanded, selections=tuple(selections))


def _normalize_mode(mode: str) -> str:
    normalized = (mode or DEFAULT_WILDCARD_MODE).strip().lower()
    if normalized == "off":
        return DEFAULT_WILDCARD_MODE
    if normalized not in WILDCARD_MODES:
        raise ValueError(f"wildcard mode must be one of: {', '.join(sorted(WILDCARD_MODES))}")
    return normalized


def _read_wildcard_values(wildcard: str, paths: AppPaths) -> list[str]:
    path = paths.wildcard_root / f"{wildcard}.txt"
    try:
        path.resolve().relative_to(paths.wildcard_root.resolve())
    except ValueError as exc:
        raise ValueError(f"invalid wildcard name: {wildcard}") from exc
    if not path.is_file():
        raise ValueError(f"wildcard file not found: {path}")
    values = [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    if not values:
        raise ValueError(f"wildcard file has no values: {path}")
    return values


def _select_index(
    wildcard: str,
    values: list[str],
    *,
    mode: str,
    paths: AppPaths,
    state: dict[str, dict[str, int]],
    rng: random.Random,
) -> int:
    if mode == "random":
        return rng.randrange(len(values))

    mode_state = state.setdefault(mode, {})
    default_index = 0 if mode == "sequential" else len(values) - 1
    index = int(mode_state.get(wildcard, default_index)) % len(values)
    if mode == "sequential":
        mode_state[wildcard] = (index + 1) % len(values)
    else:
        mode_state[wildcard] = (index - 1) % len(values)
    return index


def _rng_for(*, seed: int | None, text: str, salt: str) -> random.Random:
    if seed is None:
        return random.Random()
    digest = hashlib.sha256(f"{seed}:{salt}:{text}".encode("utf-8")).hexdigest()
    return random.Random(int(digest[:16], 16))


def _read_state(paths: AppPaths) -> dict[str, dict[str, int]]:
    if not paths.wildcard_state_path.is_file():
        return {}
    payload = json.loads(paths.wildcard_state_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return {}
    return {str(mode): {str(name): int(index) for name, index in values.items()} for mode, values in payload.items() if isinstance(values, dict)}


def _write_state(paths: AppPaths, state: dict[str, dict[str, int]]) -> None:
    paths.wildcard_state_path.parent.mkdir(parents=True, exist_ok=True)
    paths.wildcard_state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

from __future__ import annotations

import hashlib
import json
import random
import re
from dataclasses import dataclass
from dataclasses import replace
from pathlib import Path
from typing import Any

from anima_app.config import AppPaths
from anima_app.requests import T2IRequest


WILDCARD_PATTERN = re.compile(r"__([\w.-]+(?:/[\w.-]+)*)__")
WILDCARD_TOKEN_PATTERN = re.compile(r"__([\w.-]+(?:/[\w.-]+)*)__|\{([^{}\n]*\|[^{}\n]*)\}")
MAX_WILDCARD_EXPANSION_DEPTH = 10
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
        items.append(_inventory_item(path.stem, path, paths=paths))
    return items


def list_prompt_presets(paths: AppPaths) -> list[dict[str, Any]]:
    preset_root = paths.wildcard_root / "presets"
    if not preset_root.is_dir():
        return []
    items: list[dict[str, Any]] = []
    for path in sorted(preset_root.glob("*.txt"), key=lambda item: item.name.lower()):
        name = f"presets/{path.stem}"
        item = _inventory_item(name, path, paths=paths)
        item["name"] = path.stem
        items.append(item)
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

    def expand_fragment(fragment: str, *, depth: int, stack: tuple[str, ...]) -> str:
        if depth > MAX_WILDCARD_EXPANSION_DEPTH:
            raise ValueError(f"wildcard expansion exceeded max depth: {MAX_WILDCARD_EXPANSION_DEPTH}")

        def replace_match(match: re.Match[str]) -> str:
            wildcard = match.group(1)
            if wildcard is not None:
                if wildcard in stack:
                    cycle = " -> ".join((*stack, wildcard))
                    raise ValueError(f"wildcard cycle detected: {cycle}")
                values = _read_wildcard_values(wildcard, paths)
                index = _select_index(wildcard, values, mode=mode, paths=paths, state=state, rng=rng)
                value = values[index]
                path = _wildcard_path(wildcard, paths)
                selection = {
                    "token": match.group(0),
                    "wildcard": wildcard,
                    "file": str(path),
                    "mode": mode,
                    "index": index,
                    "value": value,
                }
                selections.append(selection)
                expanded_value = expand_fragment(value, depth=depth + 1, stack=(*stack, wildcard))
                if expanded_value != value:
                    selection["expanded_value"] = expanded_value
                return expanded_value

            choices = _inline_random_choices(match.group(2) or "")
            index = rng.randrange(len(choices))
            value = choices[index]
            selection = {
                "token": match.group(0),
                "type": "inline_random",
                "mode": "random",
                "index": index,
                "value": value,
            }
            selections.append(selection)
            expanded_value = expand_fragment(value, depth=depth + 1, stack=stack)
            if expanded_value != value:
                selection["expanded_value"] = expanded_value
            return expanded_value

        return WILDCARD_TOKEN_PATTERN.sub(replace_match, fragment)

    expanded = expand_fragment(text, depth=0, stack=())
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
    path = _wildcard_path(wildcard, paths)
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


def _inline_random_choices(body: str) -> list[str]:
    choices = [choice.strip() for choice in body.split("|") if choice.strip()]
    if len(choices) < 2:
        raise ValueError(f"inline random wildcard requires at least two choices: {{{body}}}")
    return choices


def _wildcard_path(wildcard: str, paths: AppPaths) -> Path:
    parts = wildcard.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError(f"invalid wildcard name: {wildcard}")
    path = paths.wildcard_root / f"{wildcard}.txt"
    try:
        path.resolve().relative_to(paths.wildcard_root.resolve())
    except ValueError as exc:
        raise ValueError(f"invalid wildcard name: {wildcard}") from exc
    return path


def _inventory_item(name: str, path: Path, *, paths: AppPaths) -> dict[str, Any]:
    values = _read_wildcard_values(name, paths)
    relative_path = path.resolve().relative_to(paths.wildcard_root.resolve()).as_posix()
    return {
        "name": name,
        "token": f"__{name}__",
        "relative_path": relative_path,
        "value_count": len(values),
    }


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

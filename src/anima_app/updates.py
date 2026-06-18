from __future__ import annotations

import re
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any

from anima_app import __version__


APP_REPOSITORY = "raspie10032/anima-app"
APP_REPOSITORY_URL = f"https://github.com/{APP_REPOSITORY}"
GITHUB_API_BASE = f"https://api.github.com/repos/{APP_REPOSITORY}"
LATEST_RELEASE_URL = f"{GITHUB_API_BASE}/releases/latest"
TAGS_URL = f"{GITHUB_API_BASE}/tags"


FetchJson = Callable[[str], Any]


def version_payload() -> dict[str, str]:
    return {
        "version": __version__,
        "repository": APP_REPOSITORY,
        "repository_url": APP_REPOSITORY_URL,
    }


def check_github_update(
    *,
    current_version: str = __version__,
    fetch_json: FetchJson | None = None,
) -> dict[str, Any]:
    fetch = fetch_json or _fetch_json
    try:
        latest = _latest_release(fetch)
        if latest is None:
            latest = _latest_tag(fetch)
        if latest is None:
            return _base_update_payload(current_version) | {
                "status": "unknown",
                "latest_version": None,
                "latest_url": APP_REPOSITORY_URL,
                "latest_source": "none",
                "error": "no GitHub releases or tags found",
            }
        comparison = compare_versions(current_version, latest["version"])
        status = "update_available" if comparison < 0 else "up_to_date"
        return _base_update_payload(current_version) | {
            "status": status,
            "latest_version": latest["version"],
            "latest_url": latest["url"],
            "latest_source": latest["source"],
            "error": "",
        }
    except Exception as exc:
        return _base_update_payload(current_version) | {
            "status": "update_check_failed",
            "latest_version": None,
            "latest_url": APP_REPOSITORY_URL,
            "latest_source": "none",
            "error": str(exc),
        }


def compare_versions(current: str, latest: str) -> int:
    current_parts = _version_tuple(current)
    latest_parts = _version_tuple(latest)
    width = max(len(current_parts), len(latest_parts), 3)
    left = current_parts + (0,) * (width - len(current_parts))
    right = latest_parts + (0,) * (width - len(latest_parts))
    if left < right:
        return -1
    if left > right:
        return 1
    return 0


def _base_update_payload(current_version: str) -> dict[str, Any]:
    return {
        "current_version": current_version,
        "repository": APP_REPOSITORY,
        "repository_url": APP_REPOSITORY_URL,
    }


def _latest_release(fetch_json: FetchJson) -> dict[str, str] | None:
    try:
        payload = fetch_json(LATEST_RELEASE_URL)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise
    if not isinstance(payload, dict):
        return None
    version = str(payload.get("tag_name") or payload.get("name") or "").strip()
    if not version:
        return None
    url = str(payload.get("html_url") or f"{APP_REPOSITORY_URL}/releases/tag/{version}")
    return {"version": version, "url": url, "source": "release"}


def _latest_tag(fetch_json: FetchJson) -> dict[str, str] | None:
    payload = fetch_json(TAGS_URL)
    if not isinstance(payload, list) or not payload:
        return None
    first = payload[0]
    if not isinstance(first, dict):
        return None
    version = str(first.get("name") or "").strip()
    if not version:
        return None
    return {
        "version": version,
        "url": f"{APP_REPOSITORY_URL}/releases/tag/{version}",
        "source": "tag",
    }


def _version_tuple(value: str) -> tuple[int, ...]:
    normalized = value.strip().lower()
    if normalized.startswith("v"):
        normalized = normalized[1:]
    match = re.match(r"(\d+(?:\.\d+)*)", normalized)
    if not match:
        return (0,)
    return tuple(int(part) for part in match.group(1).split("."))


def _fetch_json(url: str) -> Any:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"AnimaAPP/{__version__}",
        },
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        import json

        return json.loads(response.read().decode("utf-8"))

from pathlib import Path

from anima_app.autocomplete import autocomplete_payload, warm_autocomplete_index
from anima_app.config import AppPaths


def _paths(tmp_path: Path) -> AppPaths:
    return AppPaths(project_root=tmp_path / "app", autocomplete_source=tmp_path / "app" / "autocomplete.txt")


def test_autocomplete_loads_file_into_memory_and_matches_prefix(tmp_path):
    paths = _paths(tmp_path)
    paths.project_root.mkdir(parents=True)
    paths.autocomplete_source.write_text(
        "1girl,7397900\nlong_hair,5792347\nlooking_at_viewer,5350130\nvery_long_hair,120\n",
        encoding="utf-8",
    )

    index = warm_autocomplete_index(paths)
    payload = autocomplete_payload(paths, query="long", limit=3)

    assert len(index.entries) == 4
    assert payload["ready"] is True
    assert payload["count"] == 4
    assert [item["value"] for item in payload["items"]] == ["long_hair", "very_long_hair"]
    assert payload["items"][0]["label"] == "long hair"
    assert payload["items"][0]["count"] == 5792347


def test_autocomplete_returns_empty_payload_when_file_is_missing(tmp_path):
    paths = _paths(tmp_path)

    payload = autocomplete_payload(paths, query="hair")

    assert payload["ready"] is False
    assert payload["count"] == 0
    assert payload["items"] == []

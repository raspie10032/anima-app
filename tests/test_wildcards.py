import pytest

from anima_app.config import AppPaths
from anima_app.requests import T2IRequest
from anima_app.wildcards import DEFAULT_WILDCARD_MODE, WILDCARD_MODES, expand_request_wildcards, expand_text_wildcards, list_wildcards


def _paths(tmp_path):
    return AppPaths(project_root=tmp_path)


def test_random_wildcard_expansion_is_seed_repeatable(tmp_path):
    paths = _paths(tmp_path)
    wildcard_file = paths.project_root / "wildcards" / "style.txt"
    wildcard_file.parent.mkdir()
    wildcard_file.write_text("soft lineart\n# ignored\nbold shadows\n\n", encoding="utf-8")

    first = expand_text_wildcards("anime, __style__", paths=paths, mode="random", seed=123)
    second = expand_text_wildcards("anime, __style__", paths=paths, mode="random", seed=123)

    assert first.text == second.text
    assert first.selections[0]["wildcard"] == "style"
    assert first.selections[0]["value"] in {"soft lineart", "bold shadows"}


def test_default_wildcard_mode_is_random_and_no_tokens_are_noop(tmp_path):
    paths = _paths(tmp_path)

    request, expansion = expand_request_wildcards(T2IRequest(prompt="anime portrait"), paths=paths)

    assert DEFAULT_WILDCARD_MODE == "random"
    assert WILDCARD_MODES == {"random", "sequential", "reverse"}
    assert request.prompt == "anime portrait"
    assert expansion["enabled"] is False
    assert expansion["mode"] == "random"
    assert expansion["selections"] == []


def test_legacy_off_wildcard_mode_maps_to_random(tmp_path):
    paths = _paths(tmp_path)

    expansion = expand_text_wildcards("anime portrait", paths=paths, mode="off")
    _, request_expansion = expand_request_wildcards(T2IRequest(prompt="anime portrait"), paths=paths, mode="off")

    assert expansion.text == "anime portrait"
    assert expansion.selections == ()
    assert request_expansion["mode"] == "random"


def test_sequential_wildcards_persist_next_line(tmp_path):
    paths = _paths(tmp_path)
    wildcard_file = paths.project_root / "wildcards" / "pose.txt"
    wildcard_file.parent.mkdir()
    wildcard_file.write_text("standing\nsitting\n", encoding="utf-8")

    first = expand_text_wildcards("__pose__", paths=paths, mode="sequential")
    second = expand_text_wildcards("__pose__", paths=paths, mode="sequential")
    third = expand_text_wildcards("__pose__", paths=paths, mode="sequential")

    assert [first.text, second.text, third.text] == ["standing", "sitting", "standing"]
    assert (paths.output_root / "wildcard_state.json").is_file()


def test_reverse_wildcards_persist_previous_line(tmp_path):
    paths = _paths(tmp_path)
    wildcard_file = paths.project_root / "wildcards" / "color.txt"
    wildcard_file.parent.mkdir()
    wildcard_file.write_text("red\nblue\ngreen\n", encoding="utf-8")

    first = expand_text_wildcards("__color__", paths=paths, mode="reverse")
    second = expand_text_wildcards("__color__", paths=paths, mode="reverse")
    third = expand_text_wildcards("__color__", paths=paths, mode="reverse")

    assert [first.text, second.text, third.text] == ["green", "blue", "red"]


def test_missing_wildcard_file_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="wildcard file not found"):
        expand_text_wildcards("__missing__", paths=_paths(tmp_path), mode="random", seed=1)


def test_request_wildcards_expand_prompt_and_negative_prompt(tmp_path):
    paths = _paths(tmp_path)
    wildcard_dir = paths.project_root / "wildcards"
    wildcard_dir.mkdir()
    (wildcard_dir / "style.txt").write_text("soft lineart\n", encoding="utf-8")
    (wildcard_dir / "bad.txt").write_text("low quality\n", encoding="utf-8")

    request, expansion = expand_request_wildcards(
        T2IRequest(prompt="anime, __style__", negative_prompt="__bad__", seed=7),
        paths=paths,
        mode="random",
    )

    assert request.prompt == "anime, soft lineart"
    assert request.negative_prompt == "low quality"
    assert expansion["original_prompt"] == "anime, __style__"
    assert expansion["prompt"] == "anime, soft lineart"
    assert [item["wildcard"] for item in expansion["selections"]] == ["style", "bad"]


def test_list_wildcards_returns_txt_files_with_tokens_and_counts(tmp_path):
    paths = _paths(tmp_path)
    wildcard_dir = paths.project_root / "wildcards"
    wildcard_dir.mkdir()
    (wildcard_dir / "style.txt").write_text("soft lineart\n# ignored\nbold shadows\n", encoding="utf-8")
    (wildcard_dir / "pose.txt").write_text("standing\n", encoding="utf-8")
    (wildcard_dir / "notes.md").write_text("ignore me\n", encoding="utf-8")

    items = list_wildcards(paths)

    assert items == [
        {"name": "pose", "token": "__pose__", "relative_path": "pose.txt", "value_count": 1},
        {"name": "style", "token": "__style__", "relative_path": "style.txt", "value_count": 2},
    ]

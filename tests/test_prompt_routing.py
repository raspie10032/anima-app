import copy
from pathlib import Path

import pytest

from anima_app.config import AppPaths
from anima_app.library_metadata import artist_combo, request_snapshot
from anima_app.manifests import read_manifest
from anima_app.prompt_routing import (
    preview_plan,
    route_request,
    route_text,
    normalize_sources,
)
from anima_app.providers.novelai.converters import parse_comfyui, parse_naiv4
from anima_app.server import _normalized_preset_request, handle_generate


def test_group_weights_escaped_names_and_prefixes_survive_both_engines():
    text = r"(no lineart:2), (@alpha:1.0), (artist:beta, artist:gamma:0.9), (artist:alt \(example\):0.95), portrait"
    nai, _, _ = route_text(text, "auto", "naiv4")
    local, _, _ = route_text(nai, "auto", "comfyui")
    assert "@" not in nai and "artist:alpha" in nai
    assert "artist:" not in local and "@alt" in local
    expected = parse_comfyui(text.replace("@alpha", "artist:alpha"))

    def flattened(tags):
        return [
            (part.strip(), weight) for text, weight in tags for part in text.split(",")
        ]

    assert flattened(parse_naiv4(nai)) == flattened(expected)
    assert flattened(parse_comfyui(local.replace("@", "artist:"))) == flattened(
        expected
    )


def test_native_and_unweighted_parentheses_are_not_reinterpreted():
    text = r"artist:alpha, character (series), portrait"
    assert route_text(text, "native", "comfyui")[0] == text
    assert (
        route_text(text, "auto", "comfyui")[0] == "@alpha, character (series), portrait"
    )
    assert (
        route_text("1.2::@alpha::, portrait", "auto", "naiv4")[0]
        == "1.2::artist:alpha::, portrait"
    )


@pytest.mark.parametrize(
    "text", ["1.2::artist:a::, (portrait:1.3)", "(portrait:0), artist:a"]
)
def test_mixed_or_discarded_weight_fails_visibly(text):
    with pytest.raises(ValueError):
        route_text(
            text, "auto", "oldnai" if text.startswith("(portrait:0)") else "naiv4"
        )


def test_character_slots_and_negative_prompts_are_converted_without_mutation():
    original = {
        "provider": "novelai",
        "prompt": "(@alpha:1.2)",
        "negative_prompt": "(blur:1.1)",
        "prompt_routing": {"source": "auto"},
        "nai_character_slots": [
            {
                "enabled": True,
                "prompt": "(blue eyes:1.3)",
                "negative_prompt": "(red eyes:1.4)",
            },
            {"enabled": False, "prompt": "(@beta:0.8)", "negative_prompt": ""},
        ],
    }
    before = copy.deepcopy(original)
    request, receipt = route_request(original)
    assert original == before
    assert "1.3::blue eyes" in request["nai_character_slots"][0]["prompt"]
    assert "1.4::red eyes" in request["nai_character_slots"][0]["negative_prompt"]
    assert request["nai_character_slots"][1]["enabled"] is False
    assert len(receipt["fields"]) == 6


def test_preview_presets_and_dry_run_keep_authoring_and_effective_separate(tmp_path):
    paths = AppPaths(project_root=tmp_path)
    source = {"asset_id": "a" * 64, "record_id": "b" * 64, "scope": "artists"}
    payload = {
        "provider": "novelai",
        "prompt": "(@alpha:1.2), portrait",
        "negative_prompt": "(blur:1.1)",
        "nai_model": "nai-diffusion-4-5-full",
        "prompt_routing": {"source": "auto"},
        "generation_sources": [source],
        "workflow": {
            "version": 1,
            "steps": [
                {
                    "provider": "local",
                    "operation": "detail",
                    "inherit_prompt": True,
                    "request": {},
                }
            ],
        },
    }
    before = copy.deepcopy(payload)
    planned = preview_plan(payload)
    assert len(planned["stages"]) == 2
    assert planned["stages"][0]["fields"][0]["converted"].startswith(
        "1.2::artist:alpha"
    )
    assert planned["stages"][1]["fields"][0]["converted"].startswith("(@alpha:1.2)")
    normalized = _normalized_preset_request(payload)
    assert _normalized_preset_request(normalized) == normalized
    code, result = handle_generate({**payload, "dry_run": True}, paths=paths)
    assert code == 200, result
    manifest = read_manifest(Path(result["manifest_path"]))
    assert manifest["authoring_request"]["prompt"] == payload["prompt"]
    assert manifest["prompt"].startswith("1.2::artist:alpha")
    assert manifest["generation_sources"] == [source]
    assert request_snapshot(manifest)["generation_sources"] == [source]
    assert payload == before


def test_anima_artist_groups_are_individual_entries():
    combo = artist_combo(
        {
            "provider": "local",
            "prompt": "(@alpha, @beta:0.9), (@alt \\(example\\):0.8), portrait",
        }
    )
    assert [row["tag"] for row in combo["artists"]] == [
        "alpha",
        "beta",
        "alt (example)",
    ]
    assert [row["weight"] for row in combo["artists"]] == [0.9, 0.9, 0.8]


@pytest.mark.parametrize(
    "value",
    [
        [{"asset_id": "../x", "record_id": "b" * 64, "scope": "all"}],
        [
            {
                "asset_id": "a" * 64,
                "record_id": "b" * 64,
                "scope": "all",
                "url": "https://invalid.test",
            }
        ],
    ],
)
def test_case_references_are_bounded_ids_not_untrusted_urls(value):
    with pytest.raises(ValueError):
        normalize_sources(value)

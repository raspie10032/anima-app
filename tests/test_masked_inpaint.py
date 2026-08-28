from dataclasses import replace

import pytest

from anima_app.config import AppPaths
from anima_app.requests import (
    MAX_BASE_IMAGE_PIXELS,
    MAX_CFG,
    MAX_GENERATION_DIMENSION,
    MAX_PROMPT_CHARACTERS,
    MAX_SAMPLING_STEPS,
    MAX_SEED,
)
from anima_app.runtime.masked_inpaint import MaskedInpaintSettings, run_masked_inpaint


def _settings(**overrides):
    settings = MaskedInpaintSettings(
        image_path="missing.png",
        mask_path="missing-mask.png",
        prompt="portrait",
        checkpoint="model.safetensors",
    )
    return replace(settings, **overrides)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("denoise", float("nan"), "denoise must be finite"),
        ("denoise", float("inf"), "denoise must be finite"),
        ("denoise", float("-inf"), "denoise must be finite"),
        ("cfg", float("nan"), "cfg must be finite"),
        ("cfg", float("inf"), "cfg must be finite"),
        ("cfg", float("-inf"), "cfg must be finite"),
    ],
)
def test_masked_inpaint_rejects_nonfinite_values_before_image_access(
    tmp_path,
    monkeypatch,
    field,
    value,
    message,
):
    def fail_image_access(_image_path, _paths):
        raise AssertionError("image path must not be resolved for invalid settings")

    monkeypatch.setattr("anima_app.runtime.masked_inpaint.resolve_segment_source", fail_image_access)

    with pytest.raises(ValueError, match=message):
        run_masked_inpaint(_settings(**{field: value}), paths=AppPaths(project_root=tmp_path))


@pytest.mark.parametrize(
    ("field", "message"),
    [
        ("prompt", "prompt must not exceed"),
        ("negative_prompt", "negative prompt must not exceed"),
    ],
)
def test_masked_inpaint_rejects_oversized_prompts_before_image_access(tmp_path, monkeypatch, field, message):
    def fail_image_access(_image_path, _paths):
        raise AssertionError("image path must not be resolved for an oversized prompt")

    monkeypatch.setattr("anima_app.runtime.masked_inpaint.resolve_segment_source", fail_image_access)

    with pytest.raises(ValueError, match=message):
        run_masked_inpaint(
            _settings(**{field: "p" * (MAX_PROMPT_CHARACTERS + 1)}),
            paths=AppPaths(project_root=tmp_path),
        )


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"steps": MAX_SAMPLING_STEPS + 1}, "steps must be an integer"),
        ({"cfg": MAX_CFG + 0.1}, "cfg must be finite"),
        ({"seed": MAX_SEED + 1}, "seed must be an integer"),
        ({"width": MAX_GENERATION_DIMENSION + 8}, "width must be an integer"),
        (
            {"width": MAX_GENERATION_DIMENSION, "height": MAX_GENERATION_DIMENSION},
            f"masked inpaint render must not exceed {MAX_BASE_IMAGE_PIXELS} pixels",
        ),
    ],
)
def test_masked_inpaint_reuses_request_resource_limits_before_image_access(
    tmp_path,
    monkeypatch,
    overrides,
    message,
):
    def fail_image_access(_image_path, _paths):
        raise AssertionError("image path must not be resolved for invalid settings")

    monkeypatch.setattr("anima_app.runtime.masked_inpaint.resolve_segment_source", fail_image_access)

    with pytest.raises(ValueError, match=message):
        run_masked_inpaint(_settings(**overrides), paths=AppPaths(project_root=tmp_path))

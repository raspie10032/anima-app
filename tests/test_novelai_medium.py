import copy
import json

import pytest
from PIL import Image

from anima_app.config import AppPaths
from anima_app.providers import novelai
from anima_app.providers.novelai.eligibility import FocusedContext, validate_opus_free_payload
from anima_app.providers.novelai.errors import NovelAIError
from anima_app.providers.novelai.inpaint import encode_png
from anima_app.providers.novelai.medium import MEDIUM_MODEL, MEDIUM_UC
from anima_app.providers.novelai.metadata import normalize_metadata


@pytest.mark.parametrize("operation,capped", [("generate", False), ("generate", True), ("img2img", False), ("infill", False)])
@pytest.mark.parametrize("prompt", ["a flower", "NSFW, a flower"])
def test_medium_effective_wire_settings_and_original_preservation(operation, prompt, capped):
    request = novelai.NovelAIRequest(
        prompt=prompt, negative_prompt="user negative", model=MEDIUM_MODEL + ("-inpainting" if operation == "infill" else ""),
        operation=operation, width=832, height=1216, steps=50, sampler="k_euler", cfg=0, cfg_rescale=.7,
        seed=0, limit_opus_free=capped, inpaint_strength=0, img2img_strength=0, img2img_noise=.2,
        characters=({"prompt": "red hair", "negative_prompt": "user character negative", "x": .1, "y": .9},),
        use_coords=True,
        input_image="inputs/references/source.png" if operation != "generate" else "",
        mask_image="inputs/references/mask.png" if operation == "infill" else "",
    )
    effective, payload = novelai.build_payload(request)
    params = payload["parameters"]
    expected_negative = ("" if "NSFW" in prompt else "nsfw, ") + MEDIUM_UC
    assert params["steps"] == effective.steps == 14
    assert params["sampler"] == effective.sampler == "k_euler_ancestral"
    assert params["cfg_rescale"] == effective.cfg_rescale == 0
    assert params["negative_prompt"] == effective.negative_prompt == expected_negative
    assert params["v4_negative_prompt"]["caption"] == {
        "base_caption": expected_negative, "char_captions": [{"char_caption": "", "centers": [{"x": .1, "y": .9}]}]}
    assert params["v4_prompt"]["caption"]["char_captions"][0]["char_caption"] == "red hair"
    assert params["seed"] == params["extra_noise_seed"] == params["scale"] == 0
    assert params["params_version"] == 4
    assert (request.steps, request.sampler, request.cfg_rescale, request.negative_prompt) == (50, "k_euler", .7, "user negative")
    assert request.characters[0]["negative_prompt"] == "user character negative"
    if operation == "infill":
        assert params["img2img"] == {"strength": 0, "color_correct": True}
    elif operation == "img2img":
        assert params["strength"] == 0 and params["noise"] == .2
    else:
        validate_opus_free_payload(payload)


@pytest.mark.parametrize("field,value", [("steps", 28), ("sampler", "k_euler"), ("cfg_rescale", .1),
                                         ("negative_prompt", "changed"), ("steps", 14.0)])
def test_medium_protected_wire_rejects_nonfixed_fields(field, value):
    _, payload = novelai.build_payload(novelai.NovelAIRequest(prompt="test", model=MEDIUM_MODEL))
    payload["parameters"][field] = value
    with pytest.raises(NovelAIError) as error:
        validate_opus_free_payload(payload)
    assert error.value.code == "nai_opus_request_blocked"


@pytest.mark.parametrize("mutation", ["base", "character", "missing"])
def test_medium_protected_wire_rejects_structured_negatives(mutation):
    _, payload = novelai.build_payload(novelai.NovelAIRequest(prompt="test", model=MEDIUM_MODEL))
    params = payload["parameters"]
    if mutation == "base":
        params["v4_negative_prompt"]["caption"]["base_caption"] = "bad"
    elif mutation == "character":
        params["v4_negative_prompt"]["caption"]["char_captions"] = [{"char_caption": "bad"}]
    else:
        params.pop("v4_negative_prompt")
    with pytest.raises(NovelAIError):
        validate_opus_free_payload(payload)


@pytest.mark.parametrize("model", ["nai-diffusion-5-full", "nai-diffusion-4-5-full", "nai-diffusion-3"])
def test_other_models_keep_user_settings(model):
    request = novelai.NovelAIRequest(prompt="test", model=model, steps=20, negative_prompt="my negative",
                                    sampler="k_euler", cfg_rescale=.7)
    effective, _ = novelai.build_payload(request)
    assert (effective.steps, effective.sampler, effective.cfg_rescale, effective.negative_prompt) == (20, "k_euler", .7, "my negative")


@pytest.mark.parametrize("hash_value", ["93F4BD30", "70AB5786"])
@pytest.mark.parametrize("mode,operation", [("PromptGenerateRequest", "generate"),
                                          ("Img2ImgRequest", "img2img"), ("NativeInfillingRequest", "infill")])
def test_medium_metadata_hashes_keep_operation_distinction(hash_value, mode, operation):
    result = normalize_metadata({"Software": "NovelAI", "Source": "NovelAI Diffusion V5 " + hash_value,
                                 "Comment": {"prompt": "test", "request_type": mode, "model_hash": hash_value}})
    assert result["request"]["nai_model"] == MEDIUM_MODEL + ("-inpainting" if operation == "infill" else "")
    assert result["request"].get("operation", "generate") == operation
    without_mode = normalize_metadata({"Software": "NovelAI", "Source": "NovelAI Diffusion V5 " + hash_value,
                                       "Comment": {"prompt": "test"}})
    assert "nai_model" not in without_mode["request"]


def test_medium_manifest_distinguishes_requested_effective_and_opus(tmp_path):
    result = novelai.generate(novelai.NovelAIRequest(prompt="test", model=MEDIUM_MODEL, steps=20,
                             negative_prompt="keep requested", sampler="k_euler", cfg_rescale=.4),
                             paths=AppPaths(tmp_path), dry_run=True)
    manifest = json.loads(result.manifest_path.read_text())
    assert manifest["steps"] == 14 and manifest["sampler"] == "k_euler_ancestral"
    assert manifest["negative_prompt"].endswith(MEDIUM_UC)
    assert manifest["novelai"]["requested"]["negative_prompt"] == "keep requested"
    assert any("Medium Effort" in warning for warning in manifest["warnings"])
    assert not any("Opus 요청 한도 적용" in warning for warning in manifest["warnings"])


@pytest.mark.parametrize("value", [None, {"strength": .4, "color_correct": True},
                                  {"strength": .5, "color_correct": False},
                                  {"strength": .5, "color_correct": True, "extra": 1}])
def test_focused_partial_strength_guard(value):
    _, payload = novelai.build_payload(novelai.NovelAIRequest(prompt="test", model=MEDIUM_MODEL + "-inpainting",
                                      operation="infill", width=512, height=512, inpaint_strength=.5,
                                      input_image="inputs/references/source.png", mask_image="inputs/references/mask.png",
                                      limit_opus_free=False))
    params = payload["parameters"]
    params.update(image=encode_png(Image.new("RGB", (512, 512))), mask=encode_png(Image.new("L", (512, 512), 255)),
                  inpaintImg2ImgStrength=.5, noise=0)
    context = FocusedContext((1024, 1024), (0, 0, 512, 512))
    validate_opus_free_payload(payload, focused_context=context)
    bad = copy.deepcopy(payload)
    if value is None:
        bad["parameters"].pop("img2img")
    else:
        bad["parameters"]["img2img"] = value
    with pytest.raises(NovelAIError):
        validate_opus_free_payload(bad, focused_context=context)

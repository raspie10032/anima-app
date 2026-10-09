GENERATE_IMAGE_URL = "https://image.novelai.net/ai/generate-image"
SUBSCRIPTION_URL = "https://image.novelai.net/user/subscription"

MODEL_IDS = {
    "nai-diffusion-5-curated",
    "nai-diffusion-5-full",
    "nai-diffusion-4-5-curated",
    "nai-diffusion-4-5-full",
    "nai-diffusion-4-full",
    "nai-diffusion-4-curated-preview",
    "nai-diffusion-3",
    "nai-diffusion-furry-3",
}

# Dedicated infill IDs exposed by the NovelAI web model enum, 2026-10-09.
INPAINT_MODELS = {model: model + "-inpainting" for model in MODEL_IDS}
INPAINT_MODELS["nai-diffusion-4-curated-preview"] = "nai-diffusion-4-curated-inpainting"
INPAINT_MODEL_IDS = set(INPAINT_MODELS.values())
# The current web tM() routing uses V4.5 Curated for V5 Curated.
INPAINT_ROUTING = {**INPAINT_MODELS, "nai-diffusion-5-curated": "nai-diffusion-4-5-curated-inpainting"}
SUPPORTED_INPAINT_MODEL_IDS = set(INPAINT_ROUTING.values())

SAMPLERS = {
    "k_dpmpp_2m",
    "k_dpmpp_sde",
    "k_dpmpp_2m_sde",
    "k_dpmpp_2s_ancestral",
    "k_euler_ancestral",
    "k_euler",
    "ddim_v3",
}

SCHEDULERS = {"native", "karras", "exponential", "polyexponential"}

OPUS_FREE_MAX_PIXELS = 1024 * 1024
OPUS_FREE_MAX_STEPS = 28


def default_skip_cfg_above_sigma(model: str) -> int | None:
    if "4-5" in model:
        return 58
    if model.startswith("nai-diffusion-4"):
        return 19
    return None

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import PurePosixPath, PureWindowsPath

from anima_app.defaults import (
    DEFAULT_T2I_CHECKPOINT,
    DEFAULT_T2I_CFG,
    DEFAULT_T2I_HEIGHT,
    DEFAULT_T2I_SAMPLER,
    DEFAULT_T2I_SCHEDULER,
    DEFAULT_T2I_STEPS,
    DEFAULT_T2I_WIDTH,
)

MEMORY_PROFILES = {"auto", "balanced", "low_vram_highres"}
LOW_VRAM_HIGHRES_PROFILE = "low_vram_highres"
DEFAULT_UPSCALE_STEPS = 10
DEFAULT_FACE_DETAILER_STEPS = 10
DEFAULT_TILE_SIZE = 128
LOW_VRAM_HIGHRES_UPSCALE_STEPS = DEFAULT_UPSCALE_STEPS
CFG_PP_SAMPLERS = {"euler_ancestral_cfg_pp"}
FACE_DETAILER_MASK_BACKENDS = {"sam_b", "sam3"}

MAX_PROMPT_CHARACTERS = 32768
MAX_GENERATION_DIMENSION = 2048
MAX_BASE_IMAGE_PIXELS = 1024 * 1536
MAX_OUTPUT_IMAGE_PIXELS = 2048 * 2048
MAX_SAMPLING_STEPS = 100
MAX_SEED = 2**64 - 1
MAX_CFG = 20.0
MAX_UPSCALE_SCALE = 4.0
MIN_TILE_SIZE = 64
MAX_TILE_SIZE = 2048
MAX_FACE_CROP_SCALE = 4.0
MAX_FACE_PADDING = 512
MAX_FACE_FEATHER = 64
MAX_LORA_COUNT = 8
MAX_LORA_STRENGTH = 10.0


@dataclass(frozen=True)
class T2ILoraConfig:
    path: str
    model_strength: float = 1.0
    clip_strength: float = 1.0


def parse_lora_spec(value: str) -> T2ILoraConfig:
    parts = [chunk.strip() for chunk in value.split("|")]
    if not parts or not parts[0]:
        raise ValueError("lora spec cannot be empty")
    if len(parts) == 1:
        return T2ILoraConfig(path=parts[0])
    if len(parts) == 2:
        strength = float(parts[1])
        return T2ILoraConfig(path=parts[0], model_strength=strength, clip_strength=strength)
    if len(parts) == 3:
        return T2ILoraConfig(path=parts[0], model_strength=float(parts[1]), clip_strength=float(parts[2]))
    raise ValueError("lora spec must be path | path|strength | path|strength|strength")


@dataclass(frozen=True)
class I2ISettings:
    enabled: bool = False
    image_path: str = ""
    denoise: float = 0.35


@dataclass(frozen=True)
class UpscaleSettings:
    enabled: bool = False
    scale: float = 1.5
    steps: int = DEFAULT_UPSCALE_STEPS
    denoise: float = 0.35
    method: str = "bicubic"
    tiled: bool = False
    tile_size: int = DEFAULT_TILE_SIZE
    overlap: int = 8


@dataclass(frozen=True)
class VaeDecodeSettings:
    mode: str = "auto"
    tile_size: int = DEFAULT_TILE_SIZE
    overlap: int = 8


@dataclass(frozen=True)
class FaceDetailerSettings:
    enabled: bool = False
    detector: str = "default"
    mask_backend: str = "sam_b"
    threshold: float = 0.5
    crop_scale: float = 1.5
    padding: int = 32
    feather: int = 24
    exclude_forehead_ratio: float = 0.0
    steps: int = DEFAULT_FACE_DETAILER_STEPS
    denoise: float = 0.28
    sam3_face_eyes: bool = True
    sam3_hands: bool = False
    hand_denoise: float = 0.35


@dataclass(frozen=True)
class T2IRequest:
    prompt: str
    negative_prompt: str = ""
    memory_profile: str = "auto"
    width: int = DEFAULT_T2I_WIDTH
    height: int = DEFAULT_T2I_HEIGHT
    steps: int = DEFAULT_T2I_STEPS
    cfg: float = DEFAULT_T2I_CFG
    seed: int | None = None
    checkpoint: str = DEFAULT_T2I_CHECKPOINT
    sampler: str = DEFAULT_T2I_SAMPLER
    scheduler: str = DEFAULT_T2I_SCHEDULER
    loras: tuple[T2ILoraConfig, ...] = ()
    i2i: I2ISettings = I2ISettings()
    upscale: UpscaleSettings = UpscaleSettings()
    face_detailer: FaceDetailerSettings = FaceDetailerSettings()
    vae_decode: VaeDecodeSettings = VaeDecodeSettings()
    operation: str = "generate"

    def __post_init__(self) -> None:
        if self.operation not in {"generate", "detail", "upscale"}:
            raise ValueError("local operation must be generate, detail or upscale")
        if self.operation != "generate" and not self.i2i.enabled:
            raise ValueError("post-processing requires an input image")
        if self.operation == "detail" and (not self.face_detailer.enabled or self.upscale.enabled):
            raise ValueError("detail operation requires only the face detailer")
        if self.operation == "upscale" and (not self.upscale.enabled or self.face_detailer.enabled):
            raise ValueError("upscale operation requires only upscaling")
        memory_profile = str(self.memory_profile or "auto").strip() or "auto"
        object.__setattr__(self, "memory_profile", memory_profile)
        if self.memory_profile not in MEMORY_PROFILES:
            raise ValueError("memory profile must be one of: auto, balanced, low_vram_highres")
        object.__setattr__(self, "checkpoint", normalize_checkpoint_path(self.checkpoint))
        if self.memory_profile == LOW_VRAM_HIGHRES_PROFILE:
            # Memory tuning must not add an upscale pass to a detail-only stage.
            if self.operation != "detail":
                object.__setattr__(self, "upscale", low_vram_highres_upscale_settings(self.upscale))
            object.__setattr__(self, "vae_decode", low_vram_highres_vae_decode_settings(self.vae_decode))
        if not self.prompt.strip():
            raise ValueError("prompt is required")
        if len(self.prompt) > MAX_PROMPT_CHARACTERS:
            raise ValueError(f"prompt must not exceed {MAX_PROMPT_CHARACTERS} characters")
        if len(self.negative_prompt) > MAX_PROMPT_CHARACTERS:
            raise ValueError(f"negative prompt must not exceed {MAX_PROMPT_CHARACTERS} characters")
        if self.seed is not None and (
            isinstance(self.seed, bool)
            or not isinstance(self.seed, int)
            or self.seed < 0
            or self.seed > MAX_SEED
        ):
            raise ValueError(f"seed must be an integer between 0 and {MAX_SEED}")
        if self.width <= 0 or self.height <= 0:
            raise ValueError("width and height must be positive")
        if self.width > MAX_GENERATION_DIMENSION or self.height > MAX_GENERATION_DIMENSION:
            raise ValueError(f"width and height must be <= {MAX_GENERATION_DIMENSION}")
        if self.width % 8 or self.height % 8:
            raise ValueError("width and height must be divisible by 8")
        pixel_limit = MAX_BASE_IMAGE_PIXELS if self.operation == "generate" else MAX_OUTPUT_IMAGE_PIXELS
        if self.width * self.height > pixel_limit:
            raise ValueError(f"base image must not exceed {pixel_limit} pixels")
        _validate_steps(self.steps, "steps")
        _validate_finite_range(self.cfg, "cfg", minimum=0.0, maximum=MAX_CFG)
        if self.sampler not in CFG_PP_SAMPLERS:
            raise ValueError("sampler must be a CFG++ sampler")
        if len(self.loras) > MAX_LORA_COUNT:
            raise ValueError(f"no more than {MAX_LORA_COUNT} LoRAs are allowed")
        for lora in self.loras:
            if not lora.path.strip():
                raise ValueError("lora path cannot be empty")
            _validate_finite_range(
                lora.model_strength,
                "lora model strength",
                minimum=0.0,
                maximum=MAX_LORA_STRENGTH,
            )
            _validate_finite_range(
                lora.clip_strength,
                "lora clip strength",
                minimum=0.0,
                maximum=MAX_LORA_STRENGTH,
            )
        if self.i2i.enabled and not self.i2i.image_path.strip():
            raise ValueError("i2i image path is required when i2i is enabled")
        _validate_denoise(self.i2i.denoise, "i2i denoise")
        _validate_positive_finite_limit(self.upscale.scale, "upscale scale", MAX_UPSCALE_SCALE)
        if self.upscale.enabled:
            output_width = round((self.width // 8) * self.upscale.scale) * 8
            output_height = round((self.height // 8) * self.upscale.scale) * 8
            if output_width * output_height > MAX_OUTPUT_IMAGE_PIXELS:
                raise ValueError(f"upscaled image must not exceed {MAX_OUTPUT_IMAGE_PIXELS} pixels")
        _validate_steps(self.upscale.steps, "upscale steps")
        _validate_denoise(self.upscale.denoise, "upscale denoise")
        if self.upscale.tiled:
            _validate_tile_settings(self.upscale.tile_size, self.upscale.overlap, "upscale")
        _validate_finite_range(self.face_detailer.threshold, "face detailer threshold", minimum=0.0, maximum=1.0)
        if self.face_detailer.mask_backend not in FACE_DETAILER_MASK_BACKENDS:
            raise ValueError("face detailer mask backend must be one of: sam_b, sam3")
        _validate_positive_finite_limit(
            self.face_detailer.crop_scale,
            "face detailer crop scale",
            MAX_FACE_CROP_SCALE,
        )
        _validate_int_range(self.face_detailer.padding, "face detailer padding", maximum=MAX_FACE_PADDING)
        _validate_int_range(self.face_detailer.feather, "face detailer feather", maximum=MAX_FACE_FEATHER)
        _validate_finite_range(
            self.face_detailer.exclude_forehead_ratio,
            "face detailer forehead exclusion",
            minimum=0.0,
            maximum=0.75,
        )
        _validate_steps(self.face_detailer.steps, "face detailer steps")
        _validate_denoise(self.face_detailer.denoise, "face detailer denoise")
        _validate_denoise(self.face_detailer.hand_denoise, "hand detailer denoise")
        if self.vae_decode.mode not in {"auto", "tiled", "standard"}:
            raise ValueError("vae decode mode must be one of: auto, standard, tiled")
        _validate_tile_settings(self.vae_decode.tile_size, self.vae_decode.overlap, "vae")


def normalize_checkpoint_path(value: str) -> str:
    checkpoint = str(value or "").strip().replace("\\", "/")
    if not checkpoint:
        raise ValueError("checkpoint is required")
    path = PurePosixPath(checkpoint)
    windows_path = PureWindowsPath(checkpoint)
    if path.is_absolute() or windows_path.drive or windows_path.root or ":" in checkpoint or ".." in path.parts:
        raise ValueError("checkpoint must be a relative path under diffusion_models")
    if path.suffix.lower() != ".safetensors":
        raise ValueError("checkpoint must be a .safetensors file")
    return path.as_posix()


def low_vram_highres_upscale_settings(settings: UpscaleSettings) -> UpscaleSettings:
    return UpscaleSettings(
        enabled=True,
        scale=settings.scale,
        steps=LOW_VRAM_HIGHRES_UPSCALE_STEPS,
        denoise=settings.denoise,
        method=settings.method,
        tiled=True,
        tile_size=settings.tile_size,
        overlap=settings.overlap,
    )


def low_vram_highres_vae_decode_settings(settings: VaeDecodeSettings) -> VaeDecodeSettings:
    return VaeDecodeSettings(
        mode="tiled",
        tile_size=settings.tile_size,
        overlap=settings.overlap,
    )


def _validate_denoise(value: float, label: str) -> None:
    _validate_finite_range(value, label, minimum=0.0, maximum=1.0)


def _validate_finite_range(value: float, label: str, *, minimum: float, maximum: float) -> None:
    if not math.isfinite(value) or value < minimum or value > maximum:
        raise ValueError(f"{label} must be finite and between {minimum:g} and {maximum:g}")


def _validate_positive_finite_limit(value: float, label: str, maximum: float) -> None:
    if not math.isfinite(value) or value <= 0 or value > maximum:
        raise ValueError(f"{label} must be finite and between 0 (exclusive) and {maximum:g}")


def _validate_steps(value: int, label: str) -> None:
    if value <= 0 or value > MAX_SAMPLING_STEPS:
        raise ValueError(f"{label} must be between 1 and {MAX_SAMPLING_STEPS}")


def _validate_int_range(value: int, label: str, *, maximum: int) -> None:
    if value < 0 or value > maximum:
        raise ValueError(f"{label} must be between 0 and {maximum}")


def _validate_tile_settings(tile_size: int, overlap: int, label: str) -> None:
    if tile_size < MIN_TILE_SIZE or tile_size > MAX_TILE_SIZE:
        raise ValueError(f"{label} tile size must be between {MIN_TILE_SIZE} and {MAX_TILE_SIZE}")
    max_overlap = tile_size // 4
    if overlap < 0 or overlap > max_overlap:
        raise ValueError(f"{label} overlap must be between 0 and {max_overlap}")

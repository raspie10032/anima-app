from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath

from anima_app.defaults import (
    DEFAULT_T2I_CHECKPOINT,
    DEFAULT_T2I_CFG,
    DEFAULT_T2I_HEIGHT,
    DEFAULT_T2I_SAMPLER,
    DEFAULT_T2I_SCHEDULER,
    DEFAULT_T2I_STEPS,
    DEFAULT_T2I_WIDTH,
)


@dataclass(frozen=True)
class T2ILoraConfig:
    path: str
    model_strength: float = 1.0
    clip_strength: float = 1.0


@dataclass(frozen=True)
class I2ISettings:
    enabled: bool = False
    image_path: str = ""
    denoise: float = 0.35


@dataclass(frozen=True)
class UpscaleSettings:
    enabled: bool = False
    scale: float = 1.5
    steps: int = 12
    denoise: float = 0.35
    method: str = "bicubic"
    tiled: bool = False
    tile_size: int = 64
    overlap: int = 8


@dataclass(frozen=True)
class VaeDecodeSettings:
    mode: str = "auto"
    tile_size: int = 64
    overlap: int = 8


@dataclass(frozen=True)
class FaceDetailerSettings:
    enabled: bool = False
    detector: str = "default"
    threshold: float = 0.5
    crop_scale: float = 1.5
    padding: int = 32
    feather: int = 24
    exclude_forehead_ratio: float = 0.0
    steps: int = 12
    denoise: float = 0.28


@dataclass(frozen=True)
class T2IRequest:
    prompt: str
    negative_prompt: str = ""
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

    def __post_init__(self) -> None:
        object.__setattr__(self, "checkpoint", normalize_checkpoint_path(self.checkpoint))
        if not self.prompt.strip():
            raise ValueError("prompt is required")
        if self.width <= 0 or self.height <= 0:
            raise ValueError("width and height must be positive")
        if self.width % 8 or self.height % 8:
            raise ValueError("width and height must be divisible by 8")
        if self.steps <= 0:
            raise ValueError("steps must be positive")
        if self.cfg < 0:
            raise ValueError("cfg must be >= 0")
        for lora in self.loras:
            if not lora.path.strip():
                raise ValueError("lora path cannot be empty")
            if lora.model_strength < 0:
                raise ValueError("lora model strength must be >= 0")
            if lora.clip_strength < 0:
                raise ValueError("lora clip strength must be >= 0")
        if self.i2i.enabled and not self.i2i.image_path.strip():
            raise ValueError("i2i image path is required when i2i is enabled")
        _validate_denoise(self.i2i.denoise, "i2i denoise")
        if self.upscale.scale <= 0:
            raise ValueError("upscale scale must be positive")
        if self.upscale.steps <= 0:
            raise ValueError("upscale steps must be positive")
        _validate_denoise(self.upscale.denoise, "upscale denoise")
        if self.upscale.tiled:
            _validate_tile_settings(self.upscale.tile_size, self.upscale.overlap, "upscale")
        if self.face_detailer.threshold < 0 or self.face_detailer.threshold > 1:
            raise ValueError("face detailer threshold must be between 0 and 1")
        if self.face_detailer.crop_scale <= 0:
            raise ValueError("face detailer crop scale must be positive")
        if self.face_detailer.padding < 0 or self.face_detailer.feather < 0:
            raise ValueError("face detailer padding and feather must be non-negative")
        if self.face_detailer.exclude_forehead_ratio < 0 or self.face_detailer.exclude_forehead_ratio > 0.75:
            raise ValueError("face detailer forehead exclusion must be between 0 and 0.75")
        if self.face_detailer.steps <= 0:
            raise ValueError("face detailer steps must be positive")
        _validate_denoise(self.face_detailer.denoise, "face detailer denoise")
        if self.vae_decode.mode not in {"auto", "tiled", "standard"}:
            raise ValueError("vae decode mode must be one of: auto, standard, tiled")
        _validate_tile_settings(self.vae_decode.tile_size, self.vae_decode.overlap, "vae")


def normalize_checkpoint_path(value: str) -> str:
    checkpoint = str(value or "").strip().replace("\\", "/")
    if not checkpoint:
        raise ValueError("checkpoint is required")
    path = PurePosixPath(checkpoint)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("checkpoint must be a relative path under diffusion_models")
    if path.suffix.lower() != ".safetensors":
        raise ValueError("checkpoint must be a .safetensors file")
    return path.as_posix()


def _validate_denoise(value: float, label: str) -> None:
    if value < 0 or value > 1:
        raise ValueError(f"{label} must be between 0 and 1")


def _validate_tile_settings(tile_size: int, overlap: int, label: str) -> None:
    if tile_size <= 0:
        raise ValueError(f"{label} tile size must be positive")
    if overlap < 0 or overlap >= tile_size:
        raise ValueError(f"{label} overlap must be >= 0 and smaller than tile size")

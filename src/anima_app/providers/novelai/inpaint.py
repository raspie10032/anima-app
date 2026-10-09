"""Managed inpaint inputs and deterministic preservation outside the mask."""
from __future__ import annotations

import base64
import hashlib
import io
import json
from pathlib import Path

from PIL import Image, ImageOps
from PIL.PngImagePlugin import PngInfo

from anima_app.config import AppPaths
from anima_app.providers.novelai.models import default_skip_cfg_above_sigma
from anima_app.providers.novelai.requests import NovelAIRequest
from anima_app.providers.novelai.payloads import _v4_prompt_parameters
from anima_app.runtime.comfy_t2i import resolve_managed_reference_path


def read_inputs(request: NovelAIRequest, paths: AppPaths) -> tuple[Image.Image, Image.Image, dict]:
    for value in (request.input_image, request.mask_image):
        current = paths.project_root
        for part in Path(value).parts:
            current /= part
            if current.is_symlink():
                raise ValueError("인페인트 입력에는 심볼릭 링크를 사용할 수 없습니다.")
    source_path = resolve_managed_reference_path(request.input_image, paths)
    mask_path = resolve_managed_reference_path(request.mask_image, paths)
    source, source_hash = _read_image(source_path, "RGB", request)
    mask, mask_hash = _read_image(mask_path, "L", request)
    if not mask.getbbox():
        raise ValueError("인페인트 마스크가 비어 있습니다. 수정 영역을 흰색으로 표시해 주세요.")
    return source, mask, {"input_sha256": source_hash, "mask_sha256": mask_hash,
                          "mask_convention": "white=repaint; black=preserve", "outside_mask_preserved": True}


def read_img2img_input(request: NovelAIRequest, paths: AppPaths) -> tuple[Image.Image, dict]:
    current = paths.project_root
    for part in Path(request.input_image).parts:
        current /= part
        if current.is_symlink():
            raise ValueError("Img2Img 입력에는 심볼릭 링크를 사용할 수 없습니다.")
    path = resolve_managed_reference_path(request.input_image, paths)
    data = path.read_bytes()
    with Image.open(io.BytesIO(data)) as opened:
        image = ImageOps.exif_transpose(opened)
        original_size = image.size
        if request.operation == "detail" and original_size != (request.width, request.height):
            raise ValueError("디테일러 입력 크기는 생성 크기와 같아야 합니다.")
        rgba = image.convert("RGBA")
        image = Image.new("RGB", rgba.size, "white")
        image.paste(rgba, mask=rgba.getchannel("A"))
        image = image.resize((request.width, request.height), Image.Resampling.LANCZOS)
    return image, {"input_sha256": hashlib.sha256(data).hexdigest(), "original_size": list(original_size),
                   "transmitted_size": [request.width, request.height], "resize": "lanczos"}


def _read_image(path: Path, mode: str, request: NovelAIRequest) -> tuple[Image.Image, str]:
    data = path.read_bytes()
    with Image.open(io.BytesIO(data)) as image:
        image = ImageOps.exif_transpose(image)
        if image.size != (request.width, request.height):
            raise ValueError("입력 이미지와 마스크 크기는 생성 크기와 같아야 합니다. 자동 크기 변경은 하지 않습니다.")
        # Transparent pixels must not become a white repaint mask or hidden RGB input.
        if mode == "L" and image.mode in {"RGBA", "LA", "P"}:
            rgba = image.convert("RGBA")
            result = Image.new("RGB", image.size, "black")
            result.paste(rgba, mask=rgba.getchannel("A"))
            image = result
        elif mode == "RGB":
            rgba = image.convert("RGBA")
            result = Image.new("RGB", image.size, "white")
            result.paste(rgba, mask=rgba.getchannel("A"))
            image = result
        return image.convert(mode), hashlib.sha256(data).hexdigest()


def encode_png(image: Image.Image) -> str:
    stream = io.BytesIO()
    image.save(stream, format="PNG")
    return base64.b64encode(stream.getvalue()).decode("ascii")


def composite_png(remote: bytes, source: Image.Image, mask: Image.Image, request: NovelAIRequest) -> bytes:
    with Image.open(io.BytesIO(remote)) as image:
        merged = Image.composite(image.convert("RGB"), source, mask)
    stream = io.BytesIO()
    # This is an app-produced composite, not a signed/original NovelAI response.
    info = PngInfo()
    info.add_text("Software", "Anima APP")
    info.add_itxt("Comment", json.dumps({
        "model": request.model, "request_type": "NativeInfillingRequest", "anima_app_composite": True,
        "prompt": request.prompt, "uc": request.negative_prompt,
        "width": request.width, "height": request.height, "steps": request.steps,
        "scale": request.cfg, "seed": request.seed, "sampler": request.sampler,
        "noise_schedule": request.scheduler, "cfg_rescale": request.cfg_rescale,
        "prefer_brownian": request.prefer_brownian, "inpaintImg2ImgStrength": request.inpaint_strength,
        "skip_cfg_above_sigma": default_skip_cfg_above_sigma(request.model) if request.variety_boost else None,
        **(_v4_prompt_parameters(request) if request.model.startswith(("nai-diffusion-4", "nai-diffusion-5")) else {}),
    }, ensure_ascii=False))
    merged.save(stream, format="PNG", pnginfo=info)
    return stream.getvalue()

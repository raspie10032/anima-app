from __future__ import annotations

import os
from collections.abc import Mapping

from anima_app.providers.novelai.errors import NovelAIError

PRIMARY_TOKEN_VARIABLE = "NAI_ACCESS_TOKEN"
FALLBACK_TOKEN_VARIABLE = "NAI_API_TOKEN"


def token_status(environ: Mapping[str, str] | None = None) -> dict[str, object]:
    source = os.environ if environ is None else environ
    variable = _configured_variable(source)
    return {
        "configured": variable is not None,
        "source": "environment" if variable else None,
        "variable": variable,
    }


def get_token(environ: Mapping[str, str] | None = None) -> str:
    source = os.environ if environ is None else environ
    variable = _configured_variable(source)
    if variable is None:
        raise NovelAIError("nai_token_missing", f"{PRIMARY_TOKEN_VARIABLE} 환경변수를 설정해 주세요.", 409)
    return source[variable].strip()


def _configured_variable(environ: Mapping[str, str]) -> str | None:
    if environ.get(PRIMARY_TOKEN_VARIABLE, "").strip():
        return PRIMARY_TOKEN_VARIABLE
    if environ.get(FALLBACK_TOKEN_VARIABLE, "").strip():
        return FALLBACK_TOKEN_VARIABLE
    return None

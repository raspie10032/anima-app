from __future__ import annotations

import os
from contextlib import contextmanager
from contextvars import ContextVar
from collections.abc import Mapping

from anima_app.providers.novelai.errors import NovelAIError

PRIMARY_TOKEN_VARIABLE = "NAI_ACCESS_TOKEN"
FALLBACK_TOKEN_VARIABLE = "NAI_API_TOKEN"
_job_token = ContextVar("nai_job_token", default=None)
_job_account = ContextVar("nai_job_account", default=None)


@contextmanager
def account_scope(token: str, account: dict):
    """Bind a credential to this worker only, never to a request or environment."""
    credential = _job_token.set(token)
    identity = _job_account.set(dict(account))
    try:
        yield
    finally:
        _job_account.reset(identity)
        _job_token.reset(credential)


def current_account():
    value = _job_account.get()
    return dict(value) if value else None


def current_secret():
    return _job_token.get()


def token_status(environ: Mapping[str, str] | None = None) -> dict[str, object]:
    source = os.environ if environ is None else environ
    variable = _configured_variable(source)
    return {
        "configured": variable is not None,
        "source": "environment" if variable else None,
        "variable": variable,
    }


def get_token(environ: Mapping[str, str] | None = None) -> str:
    if environ is None and _job_token.get() is not None:
        return _job_token.get()
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

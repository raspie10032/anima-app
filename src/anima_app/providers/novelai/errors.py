# SPDX-License-Identifier: GPL-3.0-only
"""Structured app adaptation of RS NAI 4de9146 errors.py / error_messages.json.

Stable API codes remain compatible. Localized guidance travels with the error
through queues/manifests, without depending on browser locale.
"""
from __future__ import annotations

import errno
import json
import os
import re
from contextvars import ContextVar
from functools import wraps
from pathlib import Path

MESSAGES = json.loads((Path(__file__).parents[2] / "static" / "nai-error-messages.json").read_text(encoding="utf-8"))
CAUSES = {
    "nai_token_missing": "TOKEN_MISSING", "nai_auth_failed": "NAI_AUTH",
    "nai_balance_required": "NAI_PAYMENT", "nai_rate_limited": "NAI_RATE_LIMIT",
    "nai_timeout": "NAI_TIMEOUT", "nai_network_error": "NAI_CONNECTION",
    "nai_tls_error": "NAI_TLS", "nai_http_error": "NAI_HTTP",
    "nai_opus_check_failed": "SUBSCRIPTION_CHECK", "nai_opus_ineligible": "OPUS_REQUIRED",
    "nai_opus_v5_allowance_low": "V5_ALLOWANCE", "nai_opus_request_blocked": "FREE_CONDITIONS",
    "nai_vibe_encoding_invalid": "VIBE_RESPONSE", "nai_response_invalid": "IMAGE_RESPONSE",
    "nai_checkpoint_failed": "SAVE_FAILED", "generation_cancelled": "CANCELLED",
    "generation_invalid_request": "REQUEST_INPUT", "tagger_busy": "BUSY",
    "tagger_cache_missing": "TAGGER_CACHE", "tagger_inference": "TAGGER_MODEL",
    "nai_detailer_dependency_missing": "DEPENDENCY",
}


def redact(value: object, secrets=()) -> str:
    text = str(value)
    for secret in (*secrets, *(os.getenv(key) for key in ("NAI_ACCESS_TOKEN", "NAI_API_TOKEN", "HF_TOKEN"))):
        if secret:
            text = text.replace(secret, "[redacted]")
    text = re.sub(r"(?i)(Bearer\s+)[^\s\"',;<>]+", r"\1[redacted]", text)
    text = re.sub(r"(?i)((?:access_token|api_token|token|authorization|api_key)[\"']?\s*[:=]\s*[\"']?)[^\s\"'&,}<>]+", r"\1[redacted]", text)
    text = re.sub(r"[A-Za-z0-9_+/=-]{160,}", "[long data omitted]", text)
    if re.search(r"(?i)<(?:!doctype|html|body|script)\b", text):
        return "[HTML omitted]"
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)[:3000]


def resource_cause(error: BaseException) -> str | None:
    current, seen = error, set()
    while current is not None and id(current) not in seen and len(seen) < 5:
        seen.add(id(current))
        if isinstance(current, MemoryError) or type(current).__name__ in {"OutOfMemoryError", "CUDAOutOfMemoryError"}:
            return "MEMORY"
        if isinstance(current, PermissionError):
            return "FILE_PERMISSION"
        if isinstance(current, OSError) and current.errno == errno.ENOSPC:
            return "DISK_FULL"
        current = current.__cause__ or (None if current.__suppress_context__ else current.__context__)
    return None


class NovelAIError(ValueError):
    """Public, secret-free failure with an explicit remote-outcome boundary."""

    def __init__(self, code: str, message: str, status: int = 502, *, unknown: bool = False,
                 cause: str | None = None, stage: str = "validation", http_status: int | None = None,
                 details: str = "", exception_type: str = "NovelAIError", secrets=()):
        super().__init__(redact(message, secrets))
        self.code, self.status, self.unknown = code, status, unknown
        self.cause = cause or CAUSES.get(code, code.upper() if code.upper() in MESSAGES["en"] else "UNKNOWN")
        self.stage, self.http_status = stage, http_status
        self.details, self.exception_type = redact(details, secrets), exception_type

    def payload(self) -> dict[str, object]:
        cause = self.cause if self.cause in MESSAGES["en"] else "UNKNOWN"
        return {"error_code": self.code, "error": redact(str(self)), "provider": "novelai",
                "remote_outcome_unknown": self.unknown,
                "error_detail": {"code": cause, "stage": self.stage, "http_status": self.http_status,
                                 "exception_type": self.exception_type, "details": redact(self.details or str(self)),
                                 "messages": {locale: messages[cause] for locale, messages in MESSAGES.items()}}}


def invalid(cause: str, message: str, *, stage: str = "validation") -> NovelAIError:
    return NovelAIError("generation_invalid_request", message, 400, cause=cause, stage=stage)


def explain(error: Exception, *, stage: str, unknown: bool = False,
            fallback: str = "nai_generation_failed", message: str | None = None) -> NovelAIError:
    """Classify at a known boundary, never from user-controlled message matching."""
    resource = resource_cause(error)
    if isinstance(error, NovelAIError) and resource is None:
        if error.stage == "validation":
            error.stage = stage
        return error
    if (fallback == "nai_generation_failed" and stage in {"validation", "detailer_prepare", "reference_prepare"}
            and isinstance(error, (AttributeError, FileNotFoundError, OverflowError, TypeError, ValueError))):
        fallback = "generation_invalid_request"
    cause = resource
    if cause is None:
        if isinstance(error, FileNotFoundError):
            cause = "FILE_MISSING"
        elif isinstance(error, ImportError):
            cause = "DEPENDENCY"
        elif fallback == "generation_invalid_request":
            cause = "REQUEST_INPUT"
        elif stage.endswith("_save"):
            cause = "SAVE_FAILED"
    details, current, seen = [], error, set()
    while current is not None and id(current) not in seen and len(seen) < 5:
        seen.add(id(current))
        # External library strings may contain unlabelled credentials or inputs.
        # HTTP server message/error strings are handled separately at the client.
        safe = current.details or str(current) if isinstance(current, NovelAIError) else "External exception text omitted."
        details.append(f"{type(current).__name__}: {redact(safe)}"
                       + (f" (errno={current.errno})" if isinstance(current, OSError) else ""))
        current = current.__cause__ or (None if current.__suppress_context__ else current.__context__)
    return NovelAIError(fallback, message or "NovelAI operation failed.",
                       400 if fallback == "generation_invalid_request" or fallback.startswith("tagger_") else 502, unknown=unknown,
                       cause=cause, stage=stage, exception_type=type(error).__name__,
                       details="\n".join(([message] if message else []) + details))


def failure(error: Exception, *, stage: str, unknown: bool = False) -> dict:
    result = explain(error, stage=stage, unknown=unknown).payload()
    return {"code": result["error_code"], **result}


_stage: ContextVar[tuple[str, bool]] = ContextVar("nai_error_stage", default=("validation", False))


def mark_stage(stage: str, *, unknown: bool = False) -> None:
    _stage.set((stage, unknown))


def diagnosed(stage: str, fallback: str = "nai_generation_failed"):
    def decorate(function):
        @wraps(function)
        def run(*args, **kwargs):
            token = _stage.set((stage, False))
            try:
                return function(*args, **kwargs)
            except Exception as exc:
                active, unknown = _stage.get()
                raise explain(exc, stage=active, unknown=unknown, fallback=fallback) from None
            finally:
                _stage.reset(token)
        return run
    return decorate

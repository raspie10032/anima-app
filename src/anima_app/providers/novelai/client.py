from __future__ import annotations

import json
import math
import threading
import time
import urllib.error
from collections.abc import Callable
from email.utils import parsedate_to_datetime

import requests

from anima_app.providers.novelai.errors import NovelAIError, redact
from anima_app.providers.novelai.eligibility import FocusedContext, validate_opus_free_payload, verify_opus_state
from anima_app.providers.novelai.models import GENERATE_IMAGE_URL, SUBSCRIPTION_URL

READ_TIMEOUT_SECONDS = 300
MAX_429_RETRIES = 1
MAX_RETRY_DELAY_SECONDS = 60.0
MAX_RESPONSE_BYTES = 64 * 1024 * 1024
MAX_SUBSCRIPTION_BYTES = 1024 * 1024
SUBSCRIPTION_TIMEOUT_SECONDS = 30
REQUEST_INTERVAL_SECONDS = 2.0

Transport = Callable[[str, dict[str, str], bytes, float], bytes]
SubscriptionTransport = Callable[[str, dict[str, str], float], bytes]


def _check_cancelled(cancelled: Callable[[], bool]) -> None:
    if cancelled():
        raise NovelAIError("generation_cancelled", "NovelAI 전송 전에 취소되었습니다.", 499)


class RequestCoordinator:
    """One process-wide gate for all accounts, queues and provider instances."""

    def __init__(self, clock: Callable[[], float] = time.monotonic):
        self.lock = threading.Lock()
        self.clock = clock
        self.next_request_at = 0.0

    def wait(self, sleep: Callable[[float], None], cancelled: Callable[[], bool]) -> None:
        while True:
            _check_cancelled(cancelled)
            remaining = self.next_request_at - self.clock()
            if remaining <= 0:
                return
            sleep(min(remaining, .1))


_request_coordinator = RequestCoordinator()


def post_json(
    url: str,
    *,
    token: str,
    payload: dict[str, object],
    transport: Transport | None = None,
    sleep: Callable[[float], None] = time.sleep,
    cancelled: Callable[[], bool] = lambda: False,
    audit: dict[str, object] | None = None,
    limit_opus_free: bool = False,
    subscription_transport: SubscriptionTransport | None = None,
    focused_context: FocusedContext | None = None,
    stage: str | None = None,
) -> bytes:
    stage = stage or ("generation" if url == GENERATE_IMAGE_URL else "vibe_encoding")
    if limit_opus_free:
        if url != GENERATE_IMAGE_URL:
            raise NovelAIError("nai_opus_request_blocked", "Opus 보호 모드에서 확인할 수 없는 요청을 차단했습니다.", 400)
        validate_opus_free_payload(payload, focused_context=focused_context)
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    body = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
    active_transport = transport or _requests_transport
    coordinator = _request_coordinator
    while not coordinator.lock.acquire(timeout=.1):
        _check_cancelled(cancelled)
    try:
        return _post_locked(url, headers, body, payload, active_transport, subscription_transport,
                            sleep, cancelled, audit, limit_opus_free, coordinator, stage)
    finally:
        coordinator.lock.release()


def _post_locked(url, headers, body, payload, transport, subscription_transport,
                 sleep, cancelled, audit, limit_opus_free, coordinator, stage) -> bytes:
    for attempt in range(MAX_429_RETRIES + 1):
        coordinator.wait(sleep, cancelled)
        if limit_opus_free:
            summary = _verify_subscription(headers, payload["model"], subscription_transport)
            if audit is not None:
                audit["opus_preflight"] = summary
        _check_cancelled(cancelled)
        if audit is not None:
            audit["retry_count"] = attempt
        try:
            try:
                response = transport(url, headers, body, READ_TIMEOUT_SECONDS)
            finally:
                # Measure from completion, including failures; retries share this gate.
                coordinator.next_request_at = coordinator.clock() + REQUEST_INTERVAL_SECONDS
            if not isinstance(response, bytes) or len(response) > MAX_RESPONSE_BYTES:
                raise NovelAIError("nai_response_invalid", "NovelAI 응답 크기가 허용 범위를 초과했습니다.", unknown=True)
            return response
        except (requests.HTTPError, urllib.error.HTTPError) as exc:
            status_code = _status_code(exc)
            if status_code == 429:
                delay = _retry_delay(exc)
                coordinator.next_request_at = max(coordinator.next_request_at, coordinator.clock() + delay)
                if audit is not None:
                    audit.setdefault("rate_limit_events", []).append({"attempt": attempt + 1, "status": 429,
                        "wait_seconds": delay, "retry_scheduled": attempt < MAX_429_RETRIES})
            if status_code != 429 or attempt == MAX_429_RETRIES:
                code = "nai_auth_failed" if status_code in {401, 403} else "nai_balance_required" if status_code == 402 else "nai_rate_limited" if status_code == 429 else "nai_http_error"
                public_status = status_code if status_code in {401, 402, 403, 429} else 502
                cause = {401: "NAI_AUTH", 402: "VIBE_PAYMENT" if stage == "vibe_encoding" else "NAI_PAYMENT",
                         403: "NAI_FORBIDDEN", 400: "NAI_REQUEST", 422: "NAI_REQUEST", 429: "NAI_RATE_LIMIT"}.get(
                             status_code, "NAI_SERVER" if status_code >= 500 else "NAI_HTTP")
                raise NovelAIError(code, f"NovelAI request failed with HTTP {status_code}", public_status,
                                   unknown=status_code >= 500 or status_code == 0, cause=cause, stage=stage,
                                   http_status=status_code, exception_type=type(exc).__name__,
                                   details=_http_details(exc, headers) + f"\nAutomatic retries used: {attempt}") from None
        except requests.exceptions.SSLError as exc:
            raise NovelAIError("nai_tls_error", "NovelAI TLS verification failed.", unknown=True, stage=stage,
                               exception_type=type(exc).__name__) from None
        except (TimeoutError, requests.Timeout) as exc:
            raise NovelAIError("nai_timeout", "NovelAI 응답 시간이 초과되었습니다. 결과가 불확실하므로 자동 재전송하지 않습니다.", 504,
                               unknown=True, stage=stage, exception_type=type(exc).__name__) from None
        except (urllib.error.URLError, requests.RequestException) as exc:
            raise NovelAIError("nai_network_error", "NovelAI 연결에 실패했습니다. 결과가 불확실하므로 자동 재전송하지 않습니다.",
                               unknown=True, stage=stage, exception_type=type(exc).__name__) from None
        except NovelAIError as exc:
            if exc.stage == "validation":
                exc.stage = stage
            raise
    raise AssertionError("unreachable")


def _verify_subscription(headers: dict[str, str], model: str,
                         transport: SubscriptionTransport | None) -> dict[str, object]:
    try:
        response = (transport or _requests_subscription_transport)(
            SUBSCRIPTION_URL, {"Authorization": headers["Authorization"]}, SUBSCRIPTION_TIMEOUT_SECONDS,
        )
        if not isinstance(response, bytes) or len(response) > MAX_SUBSCRIPTION_BYTES:
            raise ValueError("invalid subscription response")
        state = json.loads(response)
    except (requests.RequestException, urllib.error.URLError, TimeoutError, ValueError, RecursionError) as exc:
        # A failed GET never submitted a generation, so its outcome is known.
        status = _status_code(exc) if isinstance(exc, (requests.HTTPError, urllib.error.HTTPError)) else None
        raise NovelAIError("nai_opus_check_failed", "Opus 자격 조회에 실패하여 생성 요청을 차단했습니다. 계정 상태와 연결을 확인해 주세요.", 503,
                           cause="NAI_AUTH" if status == 401 else "SUBSCRIPTION_CHECK", stage="subscription",
                           http_status=status, exception_type=type(exc).__name__,
                           details=_http_details(exc, headers) if status is not None else "Account check failed before image submission.") from None
    try:
        return verify_opus_state(state, model)
    except NovelAIError as exc:
        exc.stage = "subscription"
        raise


def _http_details(error, headers) -> str:
    """Only bounded JSON message/error strings; never headers, HTML or request bodies."""
    token = headers.get("Authorization", "").removeprefix("Bearer ")
    try:
        raw = error.read(16385) if isinstance(error, urllib.error.HTTPError) else error.response.content
        body = json.loads(raw) if len(raw) <= 16384 else None
    except (AttributeError, OSError, TypeError, ValueError, RecursionError):
        body = None
    if not isinstance(body, dict):
        return "No bounded JSON server message available."
    return "\n".join(f"Server {key}: {redact(body[key], (token,))}" for key in ("message", "error")
                     if isinstance(body.get(key), str))


def _requests_subscription_transport(url: str, headers: dict[str, str], timeout: float) -> bytes:
    with requests.get(url, headers=headers, timeout=(10, timeout), stream=True, allow_redirects=False) as response:
        response.raise_for_status()
        if response.status_code != 200:
            raise ValueError("unexpected subscription status")
        content = bytearray()
        for chunk in response.iter_content(chunk_size=64 * 1024):
            content.extend(chunk)
            if len(content) > MAX_SUBSCRIPTION_BYTES:
                raise ValueError("oversized subscription response")
        return bytes(content)


def _status_code(error: requests.HTTPError | urllib.error.HTTPError) -> int:
    if isinstance(error, urllib.error.HTTPError):
        return error.code
    return error.response.status_code if error.response is not None else 0


def _retry_delay(error: requests.HTTPError | urllib.error.HTTPError) -> float:
    headers = error.headers if isinstance(error, urllib.error.HTTPError) else error.response.headers if error.response is not None else {}
    retry_after = headers.get("Retry-After", "60")
    try:
        delay = float(retry_after)
    except (TypeError, ValueError):
        try:
            delay = parsedate_to_datetime(retry_after).timestamp() - time.time()
        except (TypeError, ValueError, OverflowError):
            delay = MAX_RETRY_DELAY_SECONDS
    if not math.isfinite(delay):
        delay = MAX_RETRY_DELAY_SECONDS
    return min(max(delay, REQUEST_INTERVAL_SECONDS), MAX_RETRY_DELAY_SECONDS)


def _requests_transport(url: str, headers: dict[str, str], body: bytes, timeout: float) -> bytes:
    with requests.post(url, headers=headers, data=body, timeout=(10, timeout), stream=True, allow_redirects=False) as response:
        response.raise_for_status()
        if response.status_code != 200:
            raise NovelAIError("nai_http_error", f"NovelAI request failed with HTTP {response.status_code}")
        content = bytearray()
        for chunk in response.iter_content(chunk_size=64 * 1024):
            content.extend(chunk)
            if len(content) > MAX_RESPONSE_BYTES:
                raise NovelAIError("nai_response_invalid", "NovelAI 응답 크기가 허용 범위를 초과했습니다.", unknown=True)
        return bytes(content)

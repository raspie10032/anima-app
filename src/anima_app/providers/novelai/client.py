from __future__ import annotations

import json
import math
import threading
import time
import urllib.error
from collections.abc import Callable
from email.utils import parsedate_to_datetime

import requests

from anima_app.providers.novelai.errors import NovelAIError
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
) -> bytes:
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
                            sleep, cancelled, audit, limit_opus_free, coordinator)
    finally:
        coordinator.lock.release()


def _post_locked(url, headers, body, payload, transport, subscription_transport,
                 sleep, cancelled, audit, limit_opus_free, coordinator) -> bytes:
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
                coordinator.next_request_at = max(coordinator.next_request_at, coordinator.clock() + _retry_delay(exc))
            if status_code != 429 or attempt == MAX_429_RETRIES:
                code = "nai_auth_failed" if status_code in {401, 403} else "nai_balance_required" if status_code == 402 else "nai_rate_limited" if status_code == 429 else "nai_http_error"
                public_status = status_code if status_code in {401, 402, 403, 429} else 502
                raise NovelAIError(code, f"NovelAI request failed with HTTP {status_code}", public_status,
                                   unknown=status_code >= 500 or status_code == 0) from None
        except (TimeoutError, requests.Timeout):
            raise NovelAIError("nai_timeout", "NovelAI 응답 시간이 초과되었습니다. 결과가 불확실하므로 자동 재전송하지 않습니다.", 504, unknown=True) from None
        except (urllib.error.URLError, requests.RequestException):
            raise NovelAIError("nai_network_error", "NovelAI 연결에 실패했습니다. 결과가 불확실하므로 자동 재전송하지 않습니다.", unknown=True) from None
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
    except (requests.RequestException, urllib.error.URLError, TimeoutError, ValueError, RecursionError):
        # A failed GET never submitted a generation, so its outcome is known.
        raise NovelAIError("nai_opus_check_failed", "Opus 자격 조회에 실패하여 생성 요청을 차단했습니다. 계정 상태와 연결을 확인해 주세요.", 503) from None
    return verify_opus_state(state, model)


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

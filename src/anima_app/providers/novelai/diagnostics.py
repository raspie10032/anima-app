# SPDX-License-Identifier: GPL-3.0-only
"""Request-local notices adapted from RS NAI 4de9146 diagnostics.py.

Prompt fragments are returned only to the caller, never logged. Context tokens
keep simultaneous conversions and nested matching calls isolated.
"""
from contextlib import contextmanager
from contextvars import ContextVar

_messages = ContextVar("anima_nai_notices", default=None)
MAX_NOTICES = 50


@contextmanager
def collect_notices():
    messages = []
    marker = _messages.set(messages)
    try:
        yield messages
    finally:
        _messages.reset(marker)


def notice(message):
    messages = _messages.get()
    if messages is None or message in messages:
        return
    if len(messages) < MAX_NOTICES:
        messages.append(message)
    elif len(messages) == MAX_NOTICES:
        messages.append("추가 변환 경고는 생략했습니다. 원문과 변환 결과를 확인하세요.")

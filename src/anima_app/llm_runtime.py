from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen


ENV_LLM_RUNTIME_URL = "ANIMA_LLM_RUNTIME_URL"


@dataclass(frozen=True)
class LlmRuntimeClient:
    base_url: str
    timeout_sec: float = 180.0

    def health(self) -> dict[str, Any]:
        return _get_json(_runtime_url(self.base_url, "/health"), timeout_sec=10.0)

    def generate(self, payload: dict[str, Any]) -> dict[str, Any]:
        return _post_json(_runtime_url(self.base_url, "/generate"), payload, timeout_sec=self.timeout_sec)


def default_llm_client() -> LlmRuntimeClient | None:
    raw = os.environ.get(ENV_LLM_RUNTIME_URL, "").strip()
    if not raw:
        return None
    return LlmRuntimeClient(raw)


def llm_status_payload(client: object | None) -> dict[str, Any]:
    if client is None:
        return {"ok": False, "configured": False, "error": f"{ENV_LLM_RUNTIME_URL} is not set"}
    try:
        health = client.health()  # type: ignore[attr-defined]
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        return {"ok": False, "configured": True, "error": str(exc)}
    return {
        "ok": bool(health.get("ok")),
        "configured": True,
        "active_prompt_tokens": health.get("active_prompt_tokens"),
        "process_ram_mb": ((health.get("target_system_ram_guard") or {}).get("process_ram_mb")),
        "reserved_vram_mb": ((health.get("cuda_memory") or {}).get("reserved_mb")),
        "health": health,
    }


def llm_generate_payload(client: object | None, request_payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    if client is None:
        return 503, {"ok": False, "configured": False, "error": f"{ENV_LLM_RUNTIME_URL} is not set"}
    try:
        body = client.generate(request_payload)  # type: ignore[attr-defined]
    except HTTPError as exc:
        return exc.code, {"ok": False, "configured": True, "error": str(exc)}
    except (URLError, TimeoutError, OSError) as exc:
        return 503, {"ok": False, "configured": True, "error": str(exc)}
    completion_text = _completion_text(body)
    return 200, {
        "ok": bool(body.get("ok")),
        "configured": True,
        "completion_text": completion_text,
        "metrics": {
            "prompt_tokens": ((body.get("prompt_context") or {}).get("prompt_tokens")),
            "requested_new_tokens": body.get("requested_new_tokens"),
            "generation_elapsed_sec": body.get("generation_elapsed_sec"),
            "process_ram_mb": ((body.get("target_system_ram_guard") or {}).get("process_ram_mb")),
            "reserved_vram_mb": ((body.get("cuda_memory") or {}).get("reserved_mb")),
        },
        "runtime": body,
    }


def _completion_text(body: dict[str, Any]) -> str:
    if isinstance(body.get("completion_text"), str):
        return body["completion_text"]
    output_health = body.get("output_health") if isinstance(body.get("output_health"), dict) else {}
    if isinstance(output_health.get("generated_suffix"), str):
        return output_health["generated_suffix"]
    generated_text = body.get("generated_text")
    return generated_text if isinstance(generated_text, str) else ""


def _runtime_url(base_url: str, path: str) -> str:
    return urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))


def _get_json(url: str, *, timeout_sec: float) -> dict[str, Any]:
    with urlopen(url, timeout=timeout_sec) as response:
        return json.loads(response.read().decode("utf-8"))


def _post_json(url: str, payload: dict[str, Any], *, timeout_sec: float) -> dict[str, Any]:
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=timeout_sec) as response:
        return json.loads(response.read().decode("utf-8"))

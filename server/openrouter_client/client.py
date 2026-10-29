from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Dict, List, Optional

import httpx

from ..config import get_settings
from .usage import record_call

OpenRouterBaseURL = "https://openrouter.ai/api/v1"
MAX_RATE_LIMIT_RETRIES = 3  # 429 backoff: 5s, 10s, 20s


class OpenRouterError(RuntimeError):
    """Raised when the OpenRouter API returns an error response."""


def _headers(*, api_key: Optional[str] = None) -> Dict[str, str]:
    settings = get_settings()
    key = (api_key or settings.openrouter_api_key or "").strip()
    if not key:
        raise OpenRouterError("Missing OpenRouter API key")

    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    return headers


def _build_messages(messages: List[Dict[str, str]], system: Optional[str]) -> List[Dict[str, str]]:
    if system:
        return [{"role": "system", "content": system}, *messages]
    return messages


def _handle_response_error(exc: httpx.HTTPStatusError) -> None:
    response = exc.response
    detail: str
    try:
        payload = response.json()
        detail = payload.get("error") or payload.get("message") or json.dumps(payload)
    except Exception:
        detail = response.text
    raise OpenRouterError(f"OpenRouter request failed ({response.status_code}): {detail}") from exc


async def request_chat_completion(
    *,
    model: str,
    messages: List[Dict[str, str]],
    system: Optional[str] = None,
    api_key: Optional[str] = None,
    tools: Optional[List[Dict[str, Any]]] = None,
    purpose: str = "unknown",
    base_url: str = OpenRouterBaseURL,
) -> Dict[str, Any]:
    """Request a chat completion and return the raw JSON payload."""

    payload: Dict[str, object] = {
        "model": model,
        "messages": _build_messages(messages, system),
        "stream": False,
        "usage": {"include": True},  # ask OpenRouter to return cost
    }
    if tools:
        payload["tools"] = tools

    url = f"{base_url.rstrip('/')}/chat/completions"

    started = time.perf_counter()
    retries = 0
    try:
        async with httpx.AsyncClient() as client:
            while True:
                try:
                    response = await client.post(
                        url,
                        headers=_headers(api_key=api_key),
                        json=payload,
                        timeout=60.0,  # Set reasonable timeout instead of None
                    )
                    if response.status_code == 429 and retries < MAX_RATE_LIMIT_RETRIES:
                        retries += 1
                        await asyncio.sleep(5 * 2 ** (retries - 1))
                        continue
                    try:
                        response.raise_for_status()
                    except httpx.HTTPStatusError as exc:
                        _handle_response_error(exc)
                    result = response.json()
                    break
                except httpx.HTTPError as exc:
                    raise OpenRouterError(f"OpenRouter request failed: {exc}") from exc
    except Exception as exc:
        record_call(
            purpose=purpose, model=model, status="error", retries=retries,
            latency_ms=int((time.perf_counter() - started) * 1000), error=str(exc),
        )
        raise

    record_call(
        purpose=purpose, model=model, status="ok", retries=retries,
        latency_ms=int((time.perf_counter() - started) * 1000), response=result,
    )
    return result


__all__ = ["OpenRouterError", "request_chat_completion", "OpenRouterBaseURL"]

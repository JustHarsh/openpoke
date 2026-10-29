"""Per-call LLM usage recording (tokens, cost, latency) to a JSONL file."""

from __future__ import annotations

import json
import threading
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from ..logging_config import logger
from ..paths import DATA_DIR

USAGE_LOG_PATH = DATA_DIR / "usage" / "llm_calls.jsonl"
REQUESTS_LOG_PATH = USAGE_LOG_PATH.with_name("chat_requests.jsonl")
TOOLS_LOG_PATH = USAGE_LOG_PATH.with_name("tool_calls.jsonl")

# Correlates every LLM call made while handling one chat request (including spawned agents).
current_request_id: ContextVar[Optional[str]] = ContextVar("current_request_id", default=None)

# Name of the execution agent whose work the current task belongs to (None for interaction/background).
current_agent: ContextVar[Optional[str]] = ContextVar("current_agent", default=None)

_lock = threading.Lock()


def new_request_id() -> str:
    return uuid.uuid4().hex[:8]


def record_request(request_id: str, message: str) -> None:
    """Append one record per chat message; join to llm_calls.jsonl on request_id."""
    try:
        record = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "request_id": request_id,
            "message_chars": len(message),
            "message": message,
        }
        REQUESTS_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _lock, REQUESTS_LOG_PATH.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")
    except Exception:  # pragma: no cover
        logger.exception("failed to record chat request")


def record_tool_call(*, agent: str, tool: str, success: bool, duration_ms: int, detail: Optional[str] = None) -> None:
    """Append one record per tool invocation (interaction or execution agent)."""
    try:
        record = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "request_id": current_request_id.get() or "background",
            "agent": agent,
            "tool": tool,
            "success": success,
            "duration_ms": duration_ms,
            "detail": detail,
        }
        TOOLS_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _lock, TOOLS_LOG_PATH.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")
    except Exception:  # pragma: no cover
        logger.exception("failed to record tool call")


def record_call(
    *,
    purpose: str,
    model: str,
    latency_ms: int,
    status: str,
    retries: int = 0,
    response: Optional[Dict[str, Any]] = None,
    error: Optional[str] = None,
) -> None:
    """Append one record per LLM call; never raises."""
    try:
        usage = (response or {}).get("usage") or {}
        details = usage.get("prompt_tokens_details") or {}
        record = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "request_id": current_request_id.get() or "background",
            "purpose": purpose,
            "agent": current_agent.get(),
            "model": model,
            "status": status,
            "retries": retries,
            "latency_ms": latency_ms,
            "prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": usage.get("completion_tokens"),
            "cached_tokens": details.get("cached_tokens"),
            "cost_usd": usage.get("cost"),
            "generation_id": (response or {}).get("id"),
            "error": error,
        }
        USAGE_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _lock, USAGE_LOG_PATH.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")
        logger.info(
            "llm call %s [%s] %s %dms in=%s out=%s cost=%s",
            record["request_id"], purpose, model, latency_ms,
            record["prompt_tokens"], record["completion_tokens"], record["cost_usd"],
        )
    except Exception:  # pragma: no cover - telemetry must not break calls
        logger.exception("failed to record llm usage")

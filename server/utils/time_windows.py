"""Exact Gmail time filters, computed in code so the model never does date arithmetic."""

import re
from datetime import datetime, timedelta
from typing import Optional

from .timezones import get_user_timezone_name, now_in_user_timezone

DEFAULT_WINDOW = "last 4 hours"

_SECONDS = {
    "s": 1, "sec": 1, "secs": 1, "second": 1, "seconds": 1,
    "m": 60, "min": 60, "mins": 60, "minute": 60, "minutes": 60,
    "h": 3600, "hr": 3600, "hrs": 3600, "hour": 3600, "hours": 3600,
    "d": 86400, "day": 86400, "days": 86400,
    "w": 604800, "wk": 604800, "week": 604800, "weeks": 604800,
    "mo": 2592000, "month": 2592000, "months": 2592000,  # 30 days
    "y": 31536000, "yr": 31536000, "year": 31536000, "years": 31536000,  # 365 days
}
_DURATION = re.compile(r"^(?:(?:in\s+)?(?:the\s+)?(?:last|past|previous|within)\s+)?(?:(\d+(?:\.\d+)?|an?|one)\s*)?([a-z]+)$")
EXAMPLES = "'15 minutes', '3h', '2 days', 'last hour', 'today', 'yesterday', 'this week'"


def _epoch(dt: datetime) -> int:
    return int(dt.timestamp())


def parse_window(spec: str, now: Optional[datetime] = None) -> str:
    """Turn '15 minutes', '3h', 'last 2 days', 'today', 'yesterday', 'this week' into a Gmail filter.

    Durations are exact and measured back from now; calendar words use the user's local midnight.
    Raises ValueError for anything else so the caller can tell the model what is accepted.
    """
    now = now or now_in_user_timezone()
    text = " ".join(spec.lower().split())
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if text in ("today", "since midnight", "since this morning"):
        return f"after:{_epoch(midnight)}"
    if text == "yesterday":
        return f"after:{_epoch(midnight - timedelta(days=1))} before:{_epoch(midnight)}"
    if text == "this week":  # since Monday 00:00 local
        return f"after:{_epoch(midnight - timedelta(days=now.weekday()))}"
    if text == "this month":
        return f"after:{_epoch(midnight.replace(day=1))}"
    match = _DURATION.match(text)
    if not match or match.group(2) not in _SECONDS:
        raise ValueError(f"Unrecognized time range {spec!r}. Use forms like {EXAMPLES}.")
    amount = match.group(1)
    count = 1.0 if amount in (None, "a", "an", "one") else float(amount)
    return f"after:{_epoch(now - timedelta(seconds=count * _SECONDS[match.group(2)]))}"


def render_time_context(now: Optional[datetime] = None, *, search_tool: bool = False) -> str:
    """Prompt text with the current time and the default-window rule."""
    now = now or now_in_user_timezone()
    text = f"Current time: {now:%Y-%m-%d %H:%M} ({get_user_timezone_name()}).\n"
    if search_tool:
        text += (
            f"For any relative time range pass `within` to gmail_fetch_emails (e.g. {EXAMPLES}); the system resolves it exactly. "
            "Never write after:, before: or newer_than: dates yourself.\n"
        )
    else:
        text += "When you ask the email search for messages, state the time range in plain words (e.g. 'from the last 4 hours').\n"
    return text + (
        f"If a broad request names no time range (e.g. \"summarize my emails\", \"anything urgent\", a topic filter), "
        f"use the {DEFAULT_WINDOW} and say so in your answer. Requests about a specific person or subject search all time."
    )

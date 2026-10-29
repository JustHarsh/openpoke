import asyncio
import json

import pytest

from server.agents.execution_agent.tools import email_filter
from server.config import Settings


def _fake_judge(monkeypatch, content=None, error=None):
    seen = {}

    async def fake(**kwargs):
        seen.update(kwargs)
        if error:
            raise error
        return {"choices": [{"message": {"content": content}}]}

    monkeypatch.setattr(email_filter, "request_chat_completion", fake)
    return seen


def _run(**kwargs):
    return asyncio.run(email_filter.filter_emails(**kwargs))


def _ids(result):
    return [e["id"] for e in result["emails"]]


def test_default_window_when_no_query_or_range(monkeypatch):
    seen = _fake_judge(monkeypatch, '{"matches": [1]}')
    result = _run(criterion="job related")
    assert result["window"] == "last 4 hours" and result["fetched"] == 2  # mock inbox: m2 (1h) and m1 (3h)
    assert "after:" in result["gmail_query"] and seen["purpose"] == "email_filter" and "haiku" in seen["model"]


def test_returns_only_the_emails_the_model_picks(monkeypatch):
    _fake_judge(monkeypatch, '{"matches": [2]}')
    result = _run(criterion="job related", within="1 day")
    assert result["fetched"] == 3 and result["matched"] == 1 and len(result["emails"]) == 1  # 1h, 3h, 5h old


def test_query_without_range_searches_all_time(monkeypatch):
    _fake_judge(monkeypatch, '{"matches": [1]}')
    result = _run(criterion="anything", query="lunch")
    assert result["window"] == "all time" and "after:" not in result["gmail_query"]


def test_judge_sees_a_numbered_list_and_the_criterion(monkeypatch):
    seen = _fake_judge(monkeypatch, '{"matches": []}')
    _run(criterion="job related", within="1 day")
    prompt = seen["messages"][0]["content"]
    assert "<criterion>job related</criterion>" in prompt and prompt.count("\n1 | ") == 1 and "Lunch tomorrow?" in prompt


@pytest.mark.parametrize("criterion", ["any", "ALL", ""])
def test_no_criterion_skips_the_model(monkeypatch, criterion):
    seen = _fake_judge(monkeypatch, error=AssertionError("must not be called"))
    result = _run(criterion=criterion, within="1 day")
    assert result["matched"] == result["fetched"] and seen == {}


def test_bad_range_is_reported(monkeypatch):
    _fake_judge(monkeypatch, '{"matches": []}')
    with pytest.raises(ValueError, match="Use forms like"):
        _run(criterion="x", within="whenever")


@pytest.mark.parametrize("failure", [dict(content="nope"), dict(error=RuntimeError("500"))])
def test_judge_failure_points_to_the_fallback(monkeypatch, failure):
    _fake_judge(monkeypatch, **failure)
    with pytest.raises(RuntimeError, match="task_email_search"):
        _run(criterion="job related", within="1 day")


def test_retries_with_a_smaller_page_on_413(monkeypatch):
    sizes = []
    real = email_filter.execute_gmail_tool

    def flaky(name, user_id, arguments=None):
        sizes.append(arguments["max_results"])
        if len(sizes) == 1:
            raise RuntimeError("GMAIL_FETCH_EMAILS invocation failed: 413 payload too large")
        return real(name, user_id, arguments=arguments)

    monkeypatch.setattr(email_filter, "execute_gmail_tool", flaky)
    _fake_judge(monkeypatch, '{"matches": []}')
    _run(criterion="x", within="1 day")
    assert sizes == [25, 12]


def test_tool_only_registered_under_redesign(monkeypatch):
    from server.agents.execution_agent.tools import registry

    for variant, expected in (("baseline", False), ("topk", False), ("redesign", True)):
        monkeypatch.setattr(registry, "get_settings", lambda v=variant: Settings(variant=v))
        names = [s["function"]["name"] for s in registry.get_tool_schemas()]
        assert ("filter_emails" in names) is expected
        assert ("filter_emails" in registry.get_tool_registry("x")) is expected

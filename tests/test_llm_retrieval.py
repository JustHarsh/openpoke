import asyncio
import json

import pytest

from server.services.tasks import llm_retrieval
from server.services.tasks.store import TaskStore


@pytest.fixture
def store(tmp_path):
    s = TaskStore(tmp_path / "tasks.db")
    s.create("email_thread", summary="Lunch at 12:30 with Bob", entities=["Alice"])
    s.create("email_thread", summary="Visa renewal", entities=["Alice Wong"])
    s.create("email_lookup", summary="Q3 budget emails", entities=["Q3 Budget"])
    return s


def _fake(monkeypatch, content=None, error=None):
    seen = {}

    async def fake(**kwargs):
        seen.update(kwargs)
        if error:
            raise error
        return {"choices": [{"message": {"content": content}}]}

    monkeypatch.setattr(llm_retrieval, "request_chat_completion", fake)
    return seen


def _run(store, query, **kw):
    return asyncio.run(llm_retrieval.find_tasks_llm(store, query, **kw))


def test_returns_matches_with_scores_and_ambiguity(store, monkeypatch):
    _fake(monkeypatch, json.dumps({"matches": [{"id": 1, "confidence": "high"}, {"id": 2, "confidence": "medium"}], "ambiguous": True}))
    results, ambiguous = _run(store, "Did Alice reply?")
    assert [(t.id, s) for t, s in results] == [(1, 1.0), (2, 0.6)] and ambiguous is True


def test_prompt_lists_every_task_and_uses_the_cheap_model(store, monkeypatch):
    seen = _fake(monkeypatch, '{"matches": [], "ambiguous": false}')
    _run(store, "the lunch thing")
    prompt = seen["messages"][0]["content"]
    assert "the lunch thing" in prompt and prompt.count("\n") >= 4  # one line per task
    assert "Visa renewal" in prompt and seen["purpose"] == "task_matcher" and "haiku" in seen["model"]


def test_kind_filter_limits_the_candidates(store, monkeypatch):
    seen = _fake(monkeypatch, '{"matches": [], "ambiguous": false}')
    _run(store, "budget", kind="email_lookup")
    assert "Q3 budget emails" in seen["messages"][0]["content"] and "Visa renewal" not in seen["messages"][0]["content"]


def test_unknown_ids_are_dropped_and_json_may_be_wrapped(store, monkeypatch):
    _fake(monkeypatch, 'Sure!\n```json\n{"matches": [{"id": 99, "confidence": "high"}, {"id": 3, "confidence": "low"}], "ambiguous": false}\n```')
    results, _ = _run(store, "budget")
    assert [t.id for t, _ in results] == [3]


@pytest.mark.parametrize("failure", [dict(content="not json at all"), dict(error=RuntimeError("OpenRouter 500"))])
def test_failures_are_raised_not_hidden(store, monkeypatch, failure):
    _fake(monkeypatch, **failure)
    with pytest.raises(Exception):
        _run(store, "Did Alice reply?")


def test_empty_store_makes_no_llm_call(tmp_path, monkeypatch):
    seen = _fake(monkeypatch, error=AssertionError("should not be called"))
    assert _run(TaskStore(tmp_path / "empty.db"), "anything") == ([], False) and seen == {}

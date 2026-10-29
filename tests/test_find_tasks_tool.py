import asyncio

import pytest

from server.agents.interaction_agent import tools
from server.config import Settings
from server.services.tasks.store import TaskStore


@pytest.fixture
def store(tmp_path, monkeypatch):
    s = TaskStore(tmp_path / "tasks.db")
    monkeypatch.setattr(tools, "get_task_store", lambda: s)
    return s


def _names(variant, monkeypatch):
    monkeypatch.setattr(tools, "get_settings", lambda: Settings(variant=variant))
    return [t["function"]["name"] for t in tools.get_tool_schemas()]


def _matcher(monkeypatch, pairs, ambiguous):
    async def fake(store, query, kind=None, limit=5):
        return pairs(store), ambiguous

    monkeypatch.setattr(tools, "find_tasks_llm", fake)


def _call(args):
    return asyncio.run(tools.handle_tool_call("find_tasks", args))


def test_tool_only_exposed_under_redesign(monkeypatch):
    assert "find_tasks" not in _names("baseline", monkeypatch)
    assert "find_tasks" not in _names("topk", monkeypatch)
    assert "find_tasks" in _names("redesign", monkeypatch)


def test_returns_matching_task_fields(store, monkeypatch):
    task = store.create("email_thread", summary="Thursday availability", entities=["Priya"], thread_id="t9")
    _matcher(monkeypatch, lambda s: [(task, 1.0)], False)
    payload = _call({"query": "Did Priya reply yet?"}).payload
    assert payload["tasks"][0]["id"] == task.id and payload["tasks"][0]["thread_id"] == "t9"
    assert payload["ambiguous"] is False


def test_passes_through_the_matchers_ambiguity_flag(store, monkeypatch):
    a = store.create("email_thread", entities=["Priya Nair"])
    b = store.create("email_thread", entities=["Priya Wong"])
    _matcher(monkeypatch, lambda s: [(a, 0.6), (b, 0.6)], True)
    assert _call({"query": "Did Priya reply?"}).payload["ambiguous"] is True


def test_lexical_fallback_computes_ambiguity_from_ties(store, monkeypatch):
    a = store.create("email_thread", entities=["Priya Nair"])
    b = store.create("email_thread", entities=["Priya Wong"])
    _matcher(monkeypatch, lambda s: [(a, 1.0), (b, 1.0)], None)  # None = fallback was used
    assert _call({"query": "Did Priya reply?"}).payload["ambiguous"] is True


def test_no_match_returns_empty(store, monkeypatch):
    _matcher(monkeypatch, lambda s: [], False)
    assert _call({"query": "quantum chromodynamics"}).payload == {"tasks": [], "ambiguous": False}

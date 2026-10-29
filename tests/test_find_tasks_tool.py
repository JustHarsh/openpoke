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


def test_tool_only_exposed_under_redesign(monkeypatch):
    assert "find_tasks" not in _names("baseline", monkeypatch)
    assert "find_tasks" not in _names("topk", monkeypatch)
    assert "find_tasks" in _names("redesign", monkeypatch)


def test_returns_matching_task(store):
    task = store.create("email_thread", summary="Thursday availability", entities=["Priya"], thread_id="t9")
    payload = tools.handle_tool_call("find_tasks", {"query": "Did Priya reply yet?"}).payload
    assert payload["tasks"][0]["id"] == task.id and payload["tasks"][0]["thread_id"] == "t9"
    assert payload["ambiguous"] is False


def test_flags_ambiguity_between_different_people(store):
    store.create("email_thread", entities=["Priya Nair"])
    store.create("email_thread", entities=["Priya Wong"])
    assert tools.handle_tool_call("find_tasks", {"query": "Did Priya reply?"}).payload["ambiguous"] is True


def test_no_match_returns_empty(store):
    payload = tools.handle_tool_call("find_tasks", {"query": "quantum chromodynamics"}).payload
    assert payload == {"tasks": [], "ambiguous": False}

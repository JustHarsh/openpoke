import pytest

from server.agents.execution_agent.tools import task_state
from server.services.tasks import approval
from server.services.tasks.store import TaskStore


@pytest.fixture
def env(tmp_path, monkeypatch):
    store = TaskStore(tmp_path / "tasks.db")
    count = {"n": 0}
    monkeypatch.setattr(approval, "user_message_count", lambda: count["n"])
    sent = []

    def fake_send(**kwargs):
        sent.append(kwargs)
        return {"ok": True}

    def failing_send(**kwargs):
        raise RuntimeError("Gmail 400")

    task = store.create("email_thread", entities=["Alice"])
    registry = task_state.build_registry(store, task.id, {"gmail_execute_draft": fake_send, "gmail_forward_email": failing_send})
    return store, task, registry, count, sent


def test_send_is_refused_while_drafting(env):
    store, task, registry, count, sent = env
    with pytest.raises(PermissionError):
        registry["gmail_execute_draft"](draft_id="d1")
    assert sent == [] and store.get(task.id).status == "drafting"


def test_send_is_refused_until_user_replies(env):
    store, task, registry, count, sent = env
    registry["set_task_status"]("pending_approval")
    with pytest.raises(PermissionError):
        registry["gmail_execute_draft"](draft_id="d1")  # same turn: no new user message
    assert sent == []


def test_send_after_approval_marks_sent(env):
    store, task, registry, count, sent = env
    registry["set_task_status"]("pending_approval")
    count["n"] += 1
    assert registry["gmail_execute_draft"](draft_id="d1") == {"ok": True}
    assert sent == [{"draft_id": "d1"}] and store.get(task.id).status == "sent"


def test_failed_send_keeps_task_pending(env):
    store, task, registry, count, sent = env
    registry["set_task_status"]("pending_approval")
    count["n"] += 1
    with pytest.raises(RuntimeError):
        registry["gmail_forward_email"](message_id="m1")
    assert store.get(task.id).status == "pending_approval"


def test_agent_cannot_set_sent_itself(env):
    store, task, registry, count, sent = env
    registry["set_task_status"]("pending_approval")
    count["n"] += 1
    with pytest.raises(PermissionError):
        registry["set_task_status"]("sent")


def test_update_task_merges_data(env):
    store, task, registry, count, sent = env
    registry["update_task"](summary="Lunch invite", data={"a": 1})
    registry["update_task"](thread_id="t9", data={"b": 2})
    t = store.get(task.id)
    assert (t.summary, t.thread_id, t.data) == ("Lunch invite", "t9", {"a": 1, "b": 2})


def test_context_lists_allowed_moves(env):
    store, task, registry, count, sent = env
    text = task_state.render_task_context(store.get(task.id))
    assert "pending_approval" in text and '"Alice"' in text

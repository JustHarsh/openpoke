import pytest

from server.services.tasks import approval
from server.services.tasks.store import TaskStore
from server.services.tasks.transitions import InvalidTransition


@pytest.fixture
def store(tmp_path):
    return TaskStore(tmp_path / "tasks.db")


@pytest.fixture
def user_messages(monkeypatch):
    """Control the user-message count the gate sees."""
    state = {"n": 0}
    monkeypatch.setattr(approval, "user_message_count", lambda: state["n"])
    return state


def test_cannot_send_before_pending_approval(store, user_messages):
    task = store.create("email_thread")
    ok, reason = approval.check_can_send(task)
    assert not ok and "drafting" in reason


def test_cannot_send_until_user_replies_after_the_draft(store, user_messages):
    user_messages["n"] = 3
    task = approval.enter_pending_approval(store, store.create("email_thread").id)
    assert approval.check_can_send(task)[0] is False  # same turn: no new user message yet
    user_messages["n"] = 4
    assert approval.check_can_send(store.get(task.id))[0] is True


def test_full_flow_ends_in_sent(store, user_messages):
    task = approval.enter_pending_approval(store, store.create("email_thread").id)
    user_messages["n"] += 1
    assert approval.check_can_send(store.get(task.id))[0]
    assert approval.mark_sent(store, task.id).status == "sent"


def test_cannot_mark_sent_without_pending_approval(store, user_messages):
    task = store.create("email_thread")
    with pytest.raises(InvalidTransition):
        approval.mark_sent(store, task.id)


def test_failed_send_leaves_task_pending(store, user_messages):
    task = approval.enter_pending_approval(store, store.create("email_thread").id)
    user_messages["n"] += 1
    # the provider call fails, so mark_sent is never called
    assert store.get(task.id).status == "pending_approval"

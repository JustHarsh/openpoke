import asyncio

import pytest

from server.agents.execution_agent import runtime as exec_runtime
from server.agents.interaction_agent import tools
from server.config import Settings
from server.services.tasks.store import TaskStore


@pytest.fixture
def env(tmp_path, monkeypatch):
    store = TaskStore(tmp_path / "tasks.db")
    calls = []

    async def fake_execute(worker, instructions, task_id=None, **_):
        calls.append((worker, instructions, task_id))

        class _Result:
            success = True

        return _Result()

    monkeypatch.setattr(tools, "get_settings", lambda: Settings(variant="redesign"))
    monkeypatch.setattr(tools, "get_task_store", lambda: store)
    monkeypatch.setattr(exec_runtime, "get_task_store", lambda: store)
    monkeypatch.setattr(tools._EXECUTION_BATCH_MANAGER, "execute_agent", fake_execute)
    return store, calls


def _call(args):
    async def main():
        result = tools.handle_tool_call("send_message_to_agent", args)
        await asyncio.sleep(0)  # let the scheduled worker start
        return result

    return asyncio.run(main())


def test_new_task_is_created_and_worker_dispatched(env):
    store, calls = env
    result = _call({"instructions": "Draft a lunch note to Alice", "kind": "email_thread", "title": "Lunch with Alice"})
    assert result.success and result.payload["new_task_created"] and result.payload["agent_name"] == "task-1"
    assert store.get(1).kind == "email_thread" and store.get(1).summary == "Lunch with Alice"
    assert calls == [("task-1", "Draft a lunch note to Alice", 1)]


def test_continuing_a_task_reuses_it(env):
    store, calls = env
    task = store.create("email_thread", summary="Lunch with Alice")
    result = _call({"instructions": "Send it", "task_id": task.id})
    assert result.payload["task_id"] == task.id and not result.payload["new_task_created"]
    assert len(store.list_tasks()) == 1 and calls[0][2] == task.id


def test_new_task_needs_a_valid_kind(env):
    assert not _call({"instructions": "do a thing"}).success
    assert not _call({"instructions": "do a thing", "kind": "calendar"}).success


def test_unknown_task_id_is_an_error(env):
    assert not _call({"instructions": "x", "task_id": 99}).success


def test_roster_is_not_touched_under_redesign(env, monkeypatch):
    from server.services.execution import get_agent_roster

    before = get_agent_roster().get_agents()
    _call({"instructions": "x", "kind": "other"})
    assert get_agent_roster().get_agents() == before


def test_worker_runtime_in_task_mode_gets_task_tools_and_gated_sends(env):
    store, _ = env
    task = store.create("email_thread", entities=["Alice"])
    runtime = exec_runtime.ExecutionAgentRuntime("task-1", task_id=task.id)
    names = [t["function"]["name"] for t in runtime.tool_schemas]
    assert "update_task" in names and "set_task_status" in names
    with pytest.raises(PermissionError):
        runtime.tool_registry["gmail_execute_draft"](draft_id="d1")


def test_worker_runtime_without_task_is_unchanged():
    runtime = exec_runtime.ExecutionAgentRuntime("Email to Alice")
    assert "update_task" not in runtime.tool_registry

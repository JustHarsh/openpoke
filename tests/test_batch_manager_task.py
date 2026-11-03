import asyncio

import pytest

from server.agents.execution_agent import batch_manager as bm
from server.agents.execution_agent.runtime import ExecutionResult
from server.services.tasks.store import TaskStore


@pytest.fixture
def env(tmp_path, monkeypatch):
    store = TaskStore(tmp_path / "tasks.db")
    dispatched = []

    async def capture(self, payload):
        dispatched.append(payload)

    monkeypatch.setattr(bm, "get_task_store", lambda: store)
    monkeypatch.setattr(bm.ExecutionBatchManager, "_dispatch_to_interaction_agent", capture)
    return store, dispatched


def _runtime_returning(result, delay=0.0):
    class _Runtime:
        def __init__(self, agent_name, task_id=None):
            self.task_id = task_id

        async def execute(self, instructions):
            await asyncio.sleep(delay)
            return result

    return _Runtime


def _ok(text="Sent to bob@hooli.com."):
    return ExecutionResult(agent_name="task-1", success=True, response=text)


def test_outcome_is_saved_on_the_task_record(env, monkeypatch):
    store, dispatched = env
    task = store.create("email_thread", data={"keep": "me"})
    monkeypatch.setattr(bm, "ExecutionAgentRuntime", _runtime_returning(_ok()))
    asyncio.run(bm.ExecutionBatchManager().execute_agent("task-1", "go", task_id=task.id))
    data = store.get(task.id).data
    assert data["last_result"] == "Sent to bob@hooli.com." and data["last_run_ok"] is True
    assert data["keep"] == "me"  # existing data is merged, not replaced
    assert dispatched == ["[SUCCESS] task-1: Sent to bob@hooli.com."]


def test_saved_result_is_bounded(env, monkeypatch):
    store, _ = env
    task = store.create("other")
    monkeypatch.setattr(bm, "ExecutionAgentRuntime", _runtime_returning(_ok("x" * 5000)))
    asyncio.run(bm.ExecutionBatchManager().execute_agent("task-1", "go", task_id=task.id))
    assert len(store.get(task.id).data["last_result"]) == 2000


def test_timeout_is_recorded_as_a_failed_run(env, monkeypatch):
    store, dispatched = env
    task = store.create("other")
    monkeypatch.setattr(bm, "ExecutionAgentRuntime", _runtime_returning(_ok(), delay=1))
    result = asyncio.run(bm.ExecutionBatchManager(timeout_seconds=0.01).execute_agent("task-1", "go", task_id=task.id))
    assert not result.success and result.error == "Timeout"
    assert store.get(task.id).data["last_run_ok"] is False
    assert dispatched[0].startswith("[FAILED] task-1")


def test_without_a_task_the_store_is_not_touched(env, monkeypatch):
    store, _ = env
    monkeypatch.setattr(bm, "ExecutionAgentRuntime", _runtime_returning(_ok()))
    asyncio.run(bm.ExecutionBatchManager().execute_agent("Email to Bob", "go"))
    assert store.list_tasks() == []


def test_parallel_workers_share_one_dispatch(env, monkeypatch):
    _, dispatched = env
    monkeypatch.setattr(bm, "ExecutionAgentRuntime", _runtime_returning(_ok(), delay=0.01))

    async def main():
        manager = bm.ExecutionBatchManager()
        await asyncio.gather(manager.execute_agent("a", "go"), manager.execute_agent("b", "go"))
        return manager

    manager = asyncio.run(main())
    assert len(dispatched) == 1 and dispatched[0].count("[SUCCESS]") == 2
    assert manager.get_pending_executions() == []


def test_pending_executions_are_listed_then_cleared_on_shutdown(env):
    async def main():
        manager = bm.ExecutionBatchManager()
        await manager._register_pending_execution("a", "go", "req-1")
        listed = manager.get_pending_executions()
        await manager.shutdown()
        return listed, manager.get_pending_executions()

    listed, after = asyncio.run(main())
    assert listed[0]["request_id"] == "req-1" and after == []


def test_result_for_an_unknown_batch_is_dropped(env):
    _, dispatched = env
    asyncio.run(bm.ExecutionBatchManager()._complete_execution("no-such-batch", _ok(), "a"))
    assert dispatched == []

import asyncio
import json

import pytest

from server.agents.execution_agent import runtime as exec_runtime
from server.services.tasks.store import TaskStore


@pytest.fixture
def store(tmp_path, monkeypatch):
    s = TaskStore(tmp_path / "tasks.db")
    monkeypatch.setattr(exec_runtime, "get_task_store", lambda: s)
    return s


@pytest.fixture
def tool_log(monkeypatch):
    calls = []
    monkeypatch.setattr(exec_runtime, "record_tool_call", lambda **kw: calls.append(kw))
    return calls


def _scripted(runtime, replies, seen=None):
    """Make the runtime's LLM return `replies` in order; record the system prompts it was given."""
    queue = list(replies)

    async def fake(system_prompt, messages, with_tools):
        if seen is not None:
            seen.append(system_prompt)
        return queue.pop(0) if len(queue) > 1 else queue[0]

    runtime._make_llm_call = fake


def _reply(content="", tool_calls=None):
    message = {"content": content}
    if tool_calls:
        message["tool_calls"] = tool_calls
    return {"choices": [{"message": message}]}


def _call(name, args="{}", call_id="c1"):
    return {"id": call_id, "function": {"name": name, "arguments": args}}


def _run(runtime, instructions="go"):
    return asyncio.run(runtime.execute(instructions))


def test_task_mode_prompt_carries_the_task_record(store):
    task = store.create("email_thread", summary="Lunch with Alice", entities=["Alice"])
    runtime = exec_runtime.ExecutionAgentRuntime("task-1", task_id=task.id)
    seen = []
    _scripted(runtime, [_reply("done")], seen)
    result = _run(runtime)
    assert result.success and result.response == "done"
    assert "Lunch with Alice" in seen[0] and "Statuses you may move to" in seen[0]


def test_tool_results_are_fed_back_before_the_final_answer(store, tool_log):
    runtime = exec_runtime.ExecutionAgentRuntime("Email to Alice")
    runtime.tool_registry["echo"] = lambda text: {"echoed": text}
    _scripted(runtime, [_reply(tool_calls=[_call("echo", '{"text": "hi"}')]), _reply("all done")])
    result = _run(runtime)
    assert result.success and result.tools_executed == ["echo"] and result.response == "all done"
    assert tool_log[0]["tool"] == "echo" and tool_log[0]["success"] is True


def test_async_tools_are_awaited(tool_log):
    runtime = exec_runtime.ExecutionAgentRuntime("Email to Alice")

    async def slow(x):
        return x * 2

    runtime.tool_registry["slow"] = slow
    assert asyncio.run(runtime._execute_tool("slow", {"x": 21})) == (True, 42)


def test_failing_tool_reports_the_error_and_is_logged(tool_log):
    runtime = exec_runtime.ExecutionAgentRuntime("Email to Alice")

    def boom():
        raise RuntimeError("gmail down")

    runtime.tool_registry["boom"] = boom
    assert asyncio.run(runtime._execute_tool("boom", {})) == (False, {"error": "gmail down"})
    assert tool_log[0]["success"] is False


def test_unknown_tool_is_an_error_not_a_crash(tool_log):
    runtime = exec_runtime.ExecutionAgentRuntime("Email to Alice")
    success, result = asyncio.run(runtime._execute_tool("nope", {}))
    assert not success and "Unknown tool" in result["error"] and tool_log == []


def test_llm_failure_becomes_a_failed_result():
    runtime = exec_runtime.ExecutionAgentRuntime("Email to Alice")

    async def boom(*args, **kwargs):
        raise RuntimeError("OpenRouter 500")

    runtime._make_llm_call = boom
    result = _run(runtime)
    assert not result.success and "OpenRouter 500" in result.error


def test_empty_assistant_message_is_a_failure():
    runtime = exec_runtime.ExecutionAgentRuntime("Email to Alice")
    _scripted(runtime, [{"choices": [{"message": {}}]}])
    assert not _run(runtime).success


def test_endless_tool_calls_stop_at_the_iteration_limit():
    runtime = exec_runtime.ExecutionAgentRuntime("Email to Alice")
    runtime.tool_registry["echo"] = lambda: "ok"
    _scripted(runtime, [_reply(tool_calls=[_call("echo")])])
    result = _run(runtime)
    assert not result.success and "iteration limit" in result.error


def test_tool_call_arguments_that_are_not_json_become_empty():
    runtime = exec_runtime.ExecutionAgentRuntime("Email to Alice")
    parsed = runtime._extract_tool_calls([_call("echo", "{not json"), _call("", "{}")])
    assert parsed == [{"id": "c1", "name": "echo", "arguments": {}}]


def test_tool_result_format_distinguishes_success_from_error():
    runtime = exec_runtime.ExecutionAgentRuntime("Email to Alice")
    ok = json.loads(runtime._format_tool_result("t", True, {"a": 1}, {}))
    bad = json.loads(runtime._format_tool_result("t", False, {"error": "no"}, {}))
    assert ok["status"] == "success" and ok["result"] == {"a": 1}
    assert bad["status"] == "error" and bad["error"] == "no"

import asyncio

import pytest

from server.agents.interaction_agent import tools
from server.config import Settings


class _Log:
    def __init__(self):
        self.entries = []

    def record_reply(self, content):
        self.entries.append(("reply", content))

    def record_wait(self, reason):
        self.entries.append(("wait", reason))


class _Roster:
    def __init__(self):
        self.agents = []

    def load(self):
        pass

    def get_agents(self):
        return list(self.agents)

    def add_agent(self, name):
        self.agents.append(name)


class _ExecLogs:
    def __init__(self):
        self.requests = []

    def record_request(self, name, instructions):
        self.requests.append((name, instructions))


@pytest.fixture
def log(monkeypatch):
    fake = _Log()
    monkeypatch.setattr(tools, "get_conversation_log", lambda: fake)
    return fake


@pytest.fixture
def baseline(monkeypatch):
    roster, logs, started = _Roster(), _ExecLogs(), []

    async def fake_execute(name, instructions, **_):
        started.append(name)

        class _Result:
            success = True

        return _Result()

    monkeypatch.setattr(tools, "get_settings", lambda: Settings(variant="baseline"))
    monkeypatch.setattr(tools, "get_agent_roster", lambda: roster)
    monkeypatch.setattr(tools, "get_execution_agent_logs", lambda: logs)
    monkeypatch.setattr(tools._EXECUTION_BATCH_MANAGER, "execute_agent", fake_execute)
    return roster, logs, started


def _in_loop(fn, *args, **kwargs):
    async def main():
        result = fn(*args, **kwargs)
        await asyncio.sleep(0)  # let a scheduled worker start
        return result

    return asyncio.run(main())


def test_reply_to_user_is_recorded_and_shown(log):
    result = tools.handle_tool_call("send_message_to_user", {"message": "Done!"})
    assert result.success and result.user_message == "Done!" and log.entries == [("reply", "Done!")]


def test_draft_is_formatted_for_review(log):
    result = tools.handle_tool_call("send_draft", {"to": "bob@hooli.com", "subject": "Lunch", "body": "12:30?"})
    assert result.payload["status"] == "draft_recorded"
    assert log.entries == [("reply", "To: bob@hooli.com\nSubject: Lunch\n\n12:30?")]


def test_wait_is_logged_without_a_reply(log):
    result = tools.handle_tool_call("wait", {"reason": "agent still working"})
    assert result.payload["status"] == "waiting" and log.entries == [("wait", "agent still working")]


def test_unknown_tool_is_an_error():
    result = tools.handle_tool_call("delete_everything", {})
    assert not result.success and "Unknown tool" in result.payload["error"]


def test_arguments_must_be_json_or_a_dict():
    assert tools.handle_tool_call("wait", "{not json").payload["error"] == "Invalid JSON"
    assert tools.handle_tool_call("wait", 42).payload["error"] == "Invalid arguments format"


def test_missing_required_arguments_are_reported():
    result = tools.handle_tool_call("send_draft", {"to": "bob@hooli.com"})
    assert not result.success and "Missing required arguments" in result.payload["error"]


def test_empty_string_arguments_count_as_no_arguments(log):
    assert not tools.handle_tool_call("wait", "   ").success  # reason is required


def test_baseline_needs_an_agent_name(baseline):
    result = tools.send_message_to_agent(instructions="do it")
    assert not result.success and "agent_name" in result.payload["error"]


def test_baseline_creates_then_reuses_a_named_agent(baseline):
    roster, logs, started = baseline
    first = _in_loop(tools.send_message_to_agent, agent_name="Email to Bob", instructions="draft")
    second = _in_loop(tools.send_message_to_agent, agent_name="Email to Bob", instructions="send")
    assert first.payload["new_agent_created"] and not second.payload["new_agent_created"]
    assert roster.agents == ["Email to Bob"] and started == ["Email to Bob", "Email to Bob"]
    assert logs.requests == [("Email to Bob", "draft"), ("Email to Bob", "send")]


def test_baseline_without_an_event_loop_fails_cleanly(baseline):
    result = tools.send_message_to_agent(agent_name="Email to Bob", instructions="draft")
    assert not result.success and result.payload["error"] == "No event loop available"


def test_redesign_without_an_event_loop_fails_cleanly(tmp_path, monkeypatch):
    from server.services.tasks.store import TaskStore

    store = TaskStore(tmp_path / "tasks.db")
    monkeypatch.setattr(tools, "get_settings", lambda: Settings(variant="redesign"))
    monkeypatch.setattr(tools, "get_task_store", lambda: store)
    result = tools.send_message_to_agent(instructions="draft", kind="other")
    assert not result.success and result.payload["error"] == "No event loop available"


def test_redesign_schema_swaps_the_agent_tool(monkeypatch):
    monkeypatch.setattr(tools, "get_settings", lambda: Settings(variant="redesign"))
    send = next(t for t in tools.get_tool_schemas() if t["function"]["name"] == "send_message_to_agent")
    assert "task_id" in send["function"]["parameters"]["properties"]

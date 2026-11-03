import json
import sys

import pytest

from server import usage_report
from server.openrouter_client import usage


@pytest.fixture
def paths(tmp_path, monkeypatch):
    llm, requests, tools = tmp_path / "llm_calls.jsonl", tmp_path / "chat_requests.jsonl", tmp_path / "tool_calls.jsonl"
    monkeypatch.setattr(usage, "USAGE_LOG_PATH", llm)
    monkeypatch.setattr(usage, "REQUESTS_LOG_PATH", requests)
    monkeypatch.setattr(usage, "TOOLS_LOG_PATH", tools)
    monkeypatch.setattr(usage_report, "USAGE_LOG_PATH", llm)
    return llm, requests, tools


def _rows(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_call_record_keeps_tokens_cost_and_request_id(paths):
    llm, _, _ = paths
    token = usage.current_request_id.set("req1")
    try:
        usage.record_call(
            purpose="task_matcher", model="anthropic/claude-haiku-5-5", latency_ms=120, status="ok", retries=1,
            response={"id": "gen-1", "usage": {"prompt_tokens": 500, "completion_tokens": 20, "cost": 0.0012,
                                               "prompt_tokens_details": {"cached_tokens": 100}}},
        )
    finally:
        usage.current_request_id.reset(token)
    row = _rows(llm)[0]
    assert (row["request_id"], row["purpose"], row["retries"]) == ("req1", "task_matcher", 1)
    assert (row["prompt_tokens"], row["completion_tokens"], row["cached_tokens"], row["cost_usd"]) == (500, 20, 100, 0.0012)
    assert row["generation_id"] == "gen-1"


def test_failed_call_without_a_response_is_still_recorded(paths):
    llm, _, _ = paths
    usage.record_call(purpose="x", model="m", latency_ms=5, status="error", error="402")
    row = _rows(llm)[0]
    assert row["status"] == "error" and row["error"] == "402" and row["prompt_tokens"] is None
    assert row["request_id"] == "background"


def test_request_and_tool_records_are_appended(paths):
    _, requests, tools = paths
    usage.record_request("abc", "hello there")
    usage.record_tool_call(agent="task-1", tool="update_task", success=True, duration_ms=3)
    usage.record_tool_call(agent="task-1", tool="gmail", success=False, duration_ms=9, detail="boom")
    assert _rows(requests)[0]["message_chars"] == 11
    assert [r["tool"] for r in _rows(tools)] == ["update_task", "gmail"] and _rows(tools)[1]["detail"] == "boom"


def test_request_ids_are_short_and_distinct():
    ids = {usage.new_request_id() for _ in range(50)}
    assert len(ids) == 50 and all(len(i) == 8 for i in ids)


def test_a_broken_log_path_never_raises(tmp_path, monkeypatch):
    blocker = tmp_path / "file"
    blocker.write_text("x")
    monkeypatch.setattr(usage, "USAGE_LOG_PATH", blocker / "sub" / "llm.jsonl")  # parent is a file
    usage.record_call(purpose="x", model="m", latency_ms=1, status="ok")


def _report(monkeypatch, capsys, *args):
    monkeypatch.setattr(sys, "argv", ["usage_report", *args])
    usage_report.main()
    return capsys.readouterr().out


def test_report_without_data_says_so(paths, monkeypatch, capsys):
    assert "no usage data yet" in _report(monkeypatch, capsys)


def test_report_totals_calls_cost_and_errors(paths, monkeypatch, capsys):
    for request_id, status in (("r1", "ok"), ("r1", "ok"), ("r2", "error")):
        token = usage.current_request_id.set(request_id)
        usage.record_call(purpose="execution_agent", model="a/sonnet", latency_ms=100, status=status,
                          response={"usage": {"prompt_tokens": 10, "completion_tokens": 5, "cost": 0.5}})
        usage.current_request_id.reset(token)
    out = _report(monkeypatch, capsys, "--last", "1")
    assert "Total: 3 calls, $1.5000, 1 errors" in out
    assert "execution_agent (sonnet)" in out
    assert "r2" in out and "r1  " not in out  # --last 1 keeps only the latest request

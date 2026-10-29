from datetime import datetime, timezone

import pytest

from server.services.gmail import mock
from server.utils.time_windows import DEFAULT_WINDOW, parse_window, render_time_context

NOW = datetime(2026, 10, 29, 17, 5, tzinfo=timezone.utc)


def _epoch(fragment):
    return int(fragment.split("after:")[1].split()[0])


def _ago(spec):
    return NOW.timestamp() - _epoch(parse_window(spec, NOW))


@pytest.mark.parametrize("spec,seconds", [
    ("2 minutes", 120), ("2 min", 120), ("15m", 900), ("15 minutes", 900), ("3h", 10800), ("3 hours", 10800),
    ("12 hrs", 43200), ("2 days", 172800), ("1d", 86400), ("last 2 days", 172800), ("past 3 hours", 10800),
    ("last hour", 3600), ("an hour", 3600), ("a day", 86400), ("1.5 hours", 5400), ("2 weeks", 1209600),
    ("1 month", 2592000), ("45 seconds", 45), ("  Last   4 HOURS ", 14400), ("within 30 minutes", 1800),
])
def test_durations_are_exact(spec, seconds):
    assert _ago(spec) == seconds


def test_calendar_words_use_local_midnight():
    midnight = int(datetime(2026, 10, 29, tzinfo=timezone.utc).timestamp())  # NOW is Thursday 2026-10-29
    assert _epoch(parse_window("today", NOW)) == midnight
    assert _epoch(parse_window("this week", NOW)) == midnight - 3 * 86400  # Monday 2026-10-26
    assert _epoch(parse_window("this month", NOW)) == int(datetime(2026, 10, 1, tzinfo=timezone.utc).timestamp())


def test_yesterday_is_a_closed_range():
    w = parse_window("yesterday", NOW)
    assert int(w.split("before:")[1]) - _epoch(w) == 86400


@pytest.mark.parametrize("bad", ["", "soon", "3 parsecs", "last", "yesteryear", "3"])
def test_unrecognized_ranges_raise_with_examples(bad):
    with pytest.raises(ValueError, match="Use forms like"):
        parse_window(bad, NOW)


def test_context_states_default_and_current_time():
    text = render_time_context(NOW)
    assert "2026-10-29 17:05" in text and DEFAULT_WINDOW in text and "plain words" in text


def test_search_prompt_tells_the_model_to_use_within():
    from server.agents.execution_agent.tasks.search_email.system_prompt import get_system_prompt

    assert "pass `within` to gmail_fetch_emails" in get_system_prompt()


def _search(**arguments):
    import asyncio

    from server.agents.execution_agent.tasks.search_email import tool

    return asyncio.run(tool._perform_search(arguments=arguments, queries=[], emails={}, composio_user_id="mock-user"))


def test_search_tool_resolves_within_into_an_exact_filter():
    result = _search(query="", within="4 hours")
    assert result.status == "success" and result.query.startswith("after:")
    assert {m.id for m in result.messages} == {"m1", "m2"}  # mock inbox: sent 3h and 1h ago


def test_search_tool_combines_query_and_within():
    result = _search(query="lunch", within="1 day")
    assert "lunch" in result.query and "after:" in result.query
    assert {m.id for m in result.messages} == {"m1"}


def test_search_tool_reports_an_unparseable_range_to_the_model():
    result = _search(query="lunch", within="whenever")
    assert result.status == "error" and "Use forms like" in result.error


def _ids(query):
    return {m["messageId"] for m in mock._messages(query, 50)}


def test_mock_gmail_honors_epoch_and_newer_than():
    now = datetime.now(timezone.utc)
    four_hours_ago = int(now.timestamp()) - 4 * 3600
    assert _ids(f"after:{four_hours_ago}") == {"m1", "m2"}  # sent 3h and 1h ago
    assert _ids("newer_than:2h") == {"m2"}
    assert _ids(f"after:{four_hours_ago - 7200 * 3} before:{four_hours_ago}") >= {"m3"}

import pytest

from server.experiments.report import _outcome


@pytest.mark.parametrize("spawned,expected,asked,outcome", [
    ({"a"}, {"a"}, False, "routed"),
    (set(), set(), False, "no_agent"),
    (set(), {"a"}, True, "asked"),
    (set(), {"a"}, False, "no_action"),
    ({"a", "b", "c"}, {"a"}, False, "fanout"),
    ({"b"}, {"a"}, False, "wrong"),
    ({"a"}, {"a", "b"}, False, "partial"),
    ({"a"}, set(), False, "wrong"),
])
def test_outcome_classification(spawned, expected, asked, outcome):
    assert _outcome(spawned, expected, asked) == outcome


def _turn(reply, expect=None, forbid=None, final=""):
    return {"final_response": final, "replies": [{"text": reply}], "expect_text": expect, "forbid_text": forbid}


def test_content_check_requires_expected_and_no_forbidden():
    from server.experiments.report import _content_ok

    assert _content_ok(_turn("Priya's Interview scheduling email", ["interview"], ["newsletter"])) == 1
    assert _content_ok(_turn("interview and a newsletter", ["interview"], ["newsletter"])) == 0
    assert _content_ok(_turn("nothing relevant", ["interview"], [])) == 0
    assert _content_ok(_turn("anything")) is None


def test_runner_detects_out_of_credits(tmp_path):
    import json

    from server.experiments.run import _run_errors

    log = tmp_path / "data" / "usage"
    log.mkdir(parents=True)
    ok = {"status": "ok", "error": None}
    no_credits = {"status": "error", "error": "OpenRouter request failed (402): requires more credits"}
    other = {"status": "error", "error": "OpenRouter request failed (500): boom"}
    (log / "llm_calls.jsonl").write_text("\n".join(json.dumps(x) for x in (ok, no_credits, other)) + "\n")
    assert _run_errors(tmp_path) == (2, True)
    (log / "llm_calls.jsonl").write_text(json.dumps(ok) + "\n")
    assert _run_errors(tmp_path) == (0, False)

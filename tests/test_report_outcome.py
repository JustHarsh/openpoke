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

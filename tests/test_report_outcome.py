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

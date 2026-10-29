from server.agents.interaction_agent.roster_select import select_agents
from server.experiments.seed import seed


def test_exact_name_beats_near_duplicates(tmp_path):
    roster = seed(tmp_path, 200, seed_value=3)
    assert "Email to Alice" in select_agents(roster, "Did Alice reply yet?", 5)
    assert select_agents(roster, "Did Alice reply yet?", 5)[0] == "Email to Alice"


def test_each_probe_target_is_found_among_200(tmp_path):
    roster = seed(tmp_path, 200, seed_value=7)
    for message, target in [("Did Priya reply yet?", "Email to Priya"), ("Is Bob confirmed for lunch?", "Email to Bob")]:
        assert select_agents(roster, message, 5)[0] == target


def test_returns_at_most_k_and_fills_with_recent():
    agents = ["a one", "b two", "c three", "d four"]
    assert select_agents(agents, "zzz", 2) == ["d four", "c three"]
    assert len(select_agents(agents, "a one", 10)) == 4


def test_k_zero_and_empty_roster():
    assert select_agents(["x"], "x", 0) == []
    assert select_agents([], "hello", 5) == []


def test_output_size_independent_of_roster_size(tmp_path):
    small = select_agents(seed(tmp_path / "s", 20), "Did Alice reply?", 5)
    large = select_agents(seed(tmp_path / "l", 200), "Did Alice reply?", 5)
    assert len(small) == len(large) == 5

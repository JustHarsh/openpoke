from server.agents.interaction_agent import agent as agent_module
from server.config import Settings
from server.experiments.seed import seed


class _Roster:
    def __init__(self, names):
        self._names = names

    def load(self):
        pass

    def get_agents(self):
        return list(self._names)


def _prompt(monkeypatch, tmp_path, variant, n):
    names = seed(tmp_path / f"{variant}{n}", n)
    monkeypatch.setattr(agent_module, "get_agent_roster", lambda: _Roster(names))
    monkeypatch.setattr(agent_module, "get_settings", lambda: Settings(variant=variant, topk_agents=5))
    return agent_module.prepare_message_with_history("Did Alice reply yet?", "", "user")[0]["content"]


def test_baseline_prompt_grows_with_roster(monkeypatch, tmp_path):
    assert len(_prompt(monkeypatch, tmp_path, "baseline", 200)) > 2 * len(_prompt(monkeypatch, tmp_path, "baseline", 20))


def test_topk_prompt_size_is_flat_in_roster_size(monkeypatch, tmp_path):
    small, large = _prompt(monkeypatch, tmp_path, "topk", 20), _prompt(monkeypatch, tmp_path, "topk", 200)
    assert abs(len(small) - len(large)) < 200
    assert large.count("<agent name=") == 5
    assert 'name="Email to Alice"' in large

from server.agents.interaction_agent import agent as agent_module
from server.config import Settings


def _use(monkeypatch, variant):
    monkeypatch.setattr(agent_module, "get_settings", lambda: Settings(variant=variant))


def test_redesign_prompt_swaps_the_routing_section(monkeypatch):
    _use(monkeypatch, "redesign")
    prompt = agent_module.build_system_prompt()
    assert "find_tasks" in prompt and "ambiguous" in prompt
    assert "prefer to send messages to a relevant existing agent" not in prompt
    assert "Send Message to User Tool Usage" in prompt and "Personality" in prompt  # rest is kept


def test_other_variants_keep_the_original_prompt(monkeypatch):
    for variant in ("baseline", "topk"):
        _use(monkeypatch, variant)
        prompt = agent_module.build_system_prompt()
        assert "find_tasks" not in prompt and "existing agent" in prompt


def test_redesign_message_has_no_roster(monkeypatch):
    _use(monkeypatch, "redesign")
    content = agent_module.prepare_message_with_history("Did Alice reply yet?", "", "user")[0]["content"]
    assert "<active_agents>" not in content and "<new_user_message>" in content


def test_baseline_message_still_lists_agents(monkeypatch):
    _use(monkeypatch, "baseline")
    content = agent_module.prepare_message_with_history("hi", "", "user")[0]["content"]
    assert "<active_agents>" in content

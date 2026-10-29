"""Interaction agent helpers for prompt construction."""

from html import escape
from pathlib import Path
from typing import Dict, List

from ...config import get_settings
from ...services.execution import get_agent_roster
from .roster_select import select_agents

_prompt_path = Path(__file__).parent / "system_prompt.md"
SYSTEM_PROMPT = _prompt_path.read_text(encoding="utf-8").strip()

# Redesign variant: swap the agent-routing section for task instructions
_TASK_SECTION = (Path(__file__).parent / "system_prompt_tasks.md").read_text(encoding="utf-8").strip()
_ROUTING_START = "Send Message to Agent Tool Usage"
_ROUTING_END = "Send Message to User Tool Usage"
_head, _, _rest = SYSTEM_PROMPT.partition(_ROUTING_START)
TASK_SYSTEM_PROMPT = f"{_head}{_TASK_SECTION}\n\n{_ROUTING_END}{_rest.partition(_ROUTING_END)[2]}"


# Load and return the pre-defined system prompt from markdown file
def build_system_prompt() -> str:
    """Return the static system prompt for the interaction agent."""
    return TASK_SYSTEM_PROMPT if get_settings().variant == "redesign" else SYSTEM_PROMPT


# Build structured message with conversation history, active agents, and current turn
def prepare_message_with_history(
    latest_text: str,
    transcript: str,
    message_type: str = "user",
) -> List[Dict[str, str]]:
    """Compose a message that bundles history, roster, and the latest turn."""
    sections: List[str] = []

    sections.append(_render_conversation_history(transcript))
    if get_settings().variant != "redesign":  # redesign has no roster; tasks come from find_tasks
        sections.append(f"<active_agents>\n{_render_active_agents(latest_text)}\n</active_agents>")
    sections.append(_render_current_turn(latest_text, message_type))

    content = "\n\n".join(sections)
    return [{"role": "user", "content": content}]


# Format conversation transcript into XML tags for LLM context
def _render_conversation_history(transcript: str) -> str:
    history = transcript.strip()
    if not history:
        history = "None"
    return f"<conversation_history>\n{history}\n</conversation_history>"


# Format currently active execution agents into XML tags for LLM awareness
def _render_active_agents(latest_text: str) -> str:
    roster = get_agent_roster()
    roster.load()
    agents = roster.get_agents()

    settings = get_settings()
    if settings.variant == "topk":
        agents = select_agents(agents, latest_text, settings.topk_agents)

    if not agents:
        return "None"

    rendered: List[str] = []
    for agent_name in agents:
        name = escape(agent_name or "agent", quote=True)
        rendered.append(f'<agent name="{name}" />')

    return "\n".join(rendered)


# Wrap the current message in appropriate XML tags based on sender type
def _render_current_turn(latest_text: str, message_type: str) -> str:
    tag = "new_agent_message" if message_type == "agent" else "new_user_message"
    body = latest_text.strip()
    return f"<{tag}>\n{body}\n</{tag}>"

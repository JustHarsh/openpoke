"""Pick the agents worth listing in the interaction prompt (the `topk` variant)."""

import re
from typing import List

_STOPWORDS = {"email", "to", "the", "a", "an", "of", "about", "for", "and", "reply", "re"}


def _tokens(text: str) -> set:
    return {t for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in _STOPWORDS}


def select_agents(agents: List[str], query: str, k: int) -> List[str]:
    """Return up to k agents: best name matches first, then the most recent to fill.

    Score is the fraction of an agent's name tokens found in the query, so the exact
    name beats longer near-duplicates ("Email to Alice" over "Email to Alice Costa").
    `agents` is in creation order, so later means more recent.
    """
    if k <= 0:
        return []
    query_tokens = _tokens(query)
    scored = []
    for position, name in enumerate(agents):
        name_tokens = _tokens(name)
        score = len(name_tokens & query_tokens) / len(name_tokens) if name_tokens else 0.0
        if score > 0:
            scored.append((score, position, name))
    scored.sort(key=lambda item: (-item[0], -item[1]))
    chosen = [name for _, _, name in scored[:k]]
    for name in reversed(agents):
        if len(chosen) >= k:
            break
        if name not in chosen:
            chosen.append(name)
    return chosen

"""Find the stored tasks relevant to a message (replaces listing every agent in the prompt)."""

import re
from difflib import SequenceMatcher
from typing import List, Optional, Tuple

from .store import Task, TaskStore

_STOPWORDS = {
    "a", "an", "the", "to", "of", "for", "and", "or", "is", "are", "was", "did", "do", "does", "yet", "my", "me",
    "i", "it", "that", "this", "about", "what", "which", "who", "when", "any", "from", "with", "on", "in", "at",
    # commands and filler that carry no topic ("send it", "ok thanks", "did X reply")
    "send", "reply", "replied", "please", "ok", "okay", "yes", "no", "thanks", "thank", "sure", "go", "ahead",
}


def _tokens(text: str) -> set:
    return {t for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in _STOPWORDS}


def _match(a: str, b: str) -> float:
    """1.0 if equal, the similarity if close enough to be a typo, else 0. Short words must match exactly."""
    if a == b:
        return 1.0
    if min(len(a), len(b)) < 4:
        return 0.0
    ratio = SequenceMatcher(None, a, b).ratio()
    return ratio if ratio >= 0.8 else 0.0


def _hits(query: set, words: set) -> float:
    return sum(max((_match(q, w) for w in words), default=0.0) for q in query)


def _score(query: set, task: Task) -> float:
    """Entity hits count double; normalized so a full entity match scores 1.0."""
    entity_tokens = set().union(*(_tokens(e) for e in task.entities)) if task.entities else set()
    return (2 * _hits(query, entity_tokens) + _hits(query, _tokens(task.summary))) / (2 * len(query))


def find_tasks(
    store: TaskStore, query: str, kind: Optional[str] = None, limit: int = 5
) -> List[Tuple[Task, float]]:
    """Return up to `limit` (task, score) pairs, best first, ties broken by recency.

    A query with no meaningful words (e.g. "send it") returns the most recent tasks with score 0.
    Callers decide what to do when several tasks tie at the top; this does not guess.
    """
    candidates = store.list_tasks(kind=kind, limit=100_000)  # newest first
    query_tokens = _tokens(query)
    if not query_tokens:
        return [(t, 0.0) for t in candidates[:limit]]
    scored = [(t, _score(query_tokens, t)) for t in candidates]
    scored = [(t, s) for t, s in scored if s > 0]
    scored.sort(key=lambda pair: -pair[1])  # stable: recency order preserved within equal scores
    return scored[:limit]

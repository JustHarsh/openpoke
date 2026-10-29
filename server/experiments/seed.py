"""Fill a data dir with N past execution agents (roster + small logs) for N-sweeps.

Usage: python -m server.experiments.seed <data_dir> <N> [--seed 0]
The probe targets always exist; the rest are plausible distractors, including near-duplicate names.
"""

import argparse
import random
from pathlib import Path

from server.services.execution.log_store import ExecutionAgentLogStore
from server.services.execution.roster import AgentRoster
from server.services.tasks.store import TaskStore

# (agent name, original request, final response): the agents the labelled probes should route to.
PROBE_AGENTS = [
    ("Email to Alice", "Email Alice to ask if she is free for lunch tomorrow.",
     "Sent to alice@piedpiper.com. Lunch at 12:30, Chez Philippe, with Bob."),
    ("Email to Bob", "Email Bob to ask if he is free for lunch tomorrow.",
     "Sent to bob@hooli.com. Lunch at 12:30, Chez Philippe, with Alice."),
    ("Email to Priya", "Email Priya my availability for Thursday afternoon.",
     "Sent to priya@acme.io. Waiting for her reply."),
    # No distractor shares this first name, so probes about Dana are unambiguous.
    ("Email to Dana", "Email Dana about renewing the vendor contract.",
     "Sent to dana@whitfield.io. She asked for the countersigned contract by Friday, Nov 6."),
]

_FIRST = ["Alice", "Bob", "Priya", "Frank", "Maya", "Liam", "Noah", "Sofia", "Chen", "Omar", "Elena", "Raj", "Ana", "Tom"]
_LAST = ["Wong", "Shah", "Martin", "Nair", "Odom", "Silva", "Kim", "Costa", "Novak", "Rossi"]
_TOPICS = ["Q3 Budget", "Visa Renewal", "Apartment Lease", "Flight Refund", "Conference Talk", "Tax Documents",
           "Hiring Pipeline", "Gym Membership", "Vendor Contract", "Security Audit", "Offsite Planning", "Invoice 4021"]
_CITIES = ["Tokyo", "Lisbon", "Montreal", "Berlin", "Austin", "Seoul"]


def _candidates(rng: random.Random):
    for f in _FIRST:
        for l in _LAST:
            yield (f"Email to {f} {l}", f"Email {f} {l} about the schedule.", f"Sent to {f.lower()}.{l.lower()}@example.com.")
    for t in _TOPICS:
        yield (f"{t} Analysis", f"Summarize emails about {t}.", f"Found 6 emails about {t}; summary prepared.")
    for c in _CITIES:
        yield (f"{c} Restaurant Search", f"Find restaurant reservations in {c}.", f"Found 2 reservation emails for {c}.")
    for f in _FIRST:
        for t in _TOPICS:
            yield (f"Reply to {f} about {t}", f"Reply to {f} about {t}.", f"Drafted reply to {f} regarding {t}.")


def _task_fields(name: str, response: str) -> tuple:
    """(kind, entities, summary) of the stored task equivalent to a seeded agent."""
    if name.startswith("Email to "):
        return "email_thread", [name[len("Email to "):]], response
    if name.startswith("Reply to "):
        person, _, topic = name[len("Reply to "):].partition(" about ")
        return "email_thread", [person, topic], response
    return "email_lookup", [name.replace(" Restaurant Search", "").replace(" Analysis", "")], response


def seed(data_dir: Path, n: int, seed_value: int = 0) -> list[str]:
    """Write n agents (probe targets first guaranteed) to data_dir; returns the roster in order.

    Also writes one stored task per agent (task id = roster position + 1) so the redesign variant has equivalent history.
    """
    rng = random.Random(seed_value)
    pool = list(_candidates(rng))
    probe_names = {name for name, _, _ in PROBE_AGENTS}
    pool = [c for c in pool if c[0] not in probe_names]
    if n > len(pool) + len(PROBE_AGENTS):
        raise ValueError(f"n={n} exceeds {len(pool) + len(PROBE_AGENTS)} available distinct agents")
    chosen = (PROBE_AGENTS + rng.sample(pool, max(0, n - len(PROBE_AGENTS))))[:max(n, 0)]
    rng.shuffle(chosen)  # probe targets land at random positions in the roster

    logs = ExecutionAgentLogStore(data_dir / "execution_agents")
    roster = AgentRoster(data_dir / "execution_agents" / "roster.json")
    tasks = TaskStore(data_dir / "tasks.db")
    for name, request, response in chosen:
        logs.record_request(name, request)
        logs.record_agent_response(name, response)
        roster.add_agent(name)
        kind, entities, summary = _task_fields(name, response)
        task = tasks.create(kind, summary=summary, entities=entities)
        if kind == "email_thread":
            tasks.set_status(task.id, "sent")  # history: sent, waiting on a reply
    return roster.get_agents()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("data_dir", type=Path)
    ap.add_argument("n", type=int)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    names = seed(a.data_dir, a.n, a.seed)
    print(f"seeded {len(names)} agents into {a.data_dir}")

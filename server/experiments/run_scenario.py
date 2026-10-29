"""Run one scenario in isolation (called by run.py with OPENPOKE_DATA_DIR / OPENPOKE_MOCK_GMAIL set).

Usage: python -m server.experiments.run_scenario <scenario_id> <out_dir> [--turn-timeout S]
"""

import argparse
import asyncio
import json
import os
import time
from pathlib import Path

from server.agents.interaction_agent import tools as interaction_tools
from server.agents.interaction_agent.runtime import InteractionAgentRuntime
from server.experiments.seed import seed
from server.openrouter_client.usage import current_request_id, new_request_id, record_request

SCENARIOS = Path(__file__).with_name("scenarios.json")


async def _drain(timeout: float) -> bool:
    """Wait for fire-and-forget work (execution agents, follow-up interaction turns) to finish."""
    deadline = time.monotonic() + timeout
    while True:
        pending = [t for t in asyncio.all_tasks() if t is not asyncio.current_task() and not t.done()]
        if not pending:
            return True
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return False
        await asyncio.wait(pending, timeout=remaining)


async def main(scenario_id: str, out_dir: Path, turn_timeout: float) -> None:
    scenario = next(s for s in json.loads(SCENARIOS.read_text()) if s["id"] == scenario_id)

    replies: list = []  # (monotonic_time, kind, text) for everything shown to the user
    for name in ("send_message_to_user", "send_draft"):
        original = getattr(interaction_tools, name)

        def wrapper(*args, _orig=original, _name=name, **kwargs):
            result = _orig(*args, **kwargs)
            replies.append((time.monotonic(), _name, result.user_message or json.dumps(kwargs)[:2000]))
            return result

        setattr(interaction_tools, name, wrapper)

    seed_n = int(os.environ.get("OPENPOKE_SEED_N") or scenario.get("seed_n") or 0)
    seeded = seed(Path(os.environ["OPENPOKE_DATA_DIR"]), seed_n) if seed_n else []

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "seeded_roster.json").write_text(json.dumps(seeded))
    with (out_dir / "turns.jsonl").open("w") as fh:
        for index, turn in enumerate(scenario["turns"]):
            message = turn["text"] if isinstance(turn, dict) else turn
            drain = turn.get("drain", True) if isinstance(turn, dict) else True
            expect_agent = turn.get("expect_agent") if isinstance(turn, dict) else None
            accept_ask = bool(turn.get("accept_ask")) if isinstance(turn, dict) else False
            request_id = new_request_id()
            current_request_id.set(request_id)
            record_request(request_id, message)
            replies.clear()

            started = time.monotonic()
            result = await InteractionAgentRuntime().execute(message)
            first_pass = time.monotonic() - started
            drained = await _drain(turn_timeout) if drain else None
            total = time.monotonic() - started

            fh.write(json.dumps({
                "scenario": scenario_id,
                "turn": index,
                "request_id": request_id,
                "message": message,
                "success": result.success,
                "error": result.error,
                "final_response": result.response,
                "drained": drained,
                "category": scenario["category"],
                "expect_agent": expect_agent,
                "accept_ask": accept_ask,
                "seed_n": seed_n,
                "first_pass_s": round(first_pass, 3),
                "first_reply_s": round(replies[0][0] - started, 3) if replies else None,
                "total_s": round(total, 3),
                "replies": [{"t": round(t - started, 3), "kind": k, "text": x} for t, k, x in replies],
            }) + "\n")
            fh.flush()
        await _drain(turn_timeout)  # let any undrained work finish before exit


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("scenario_id")
    ap.add_argument("out_dir", type=Path)
    ap.add_argument("--turn-timeout", type=float, default=180)
    a = ap.parse_args()
    asyncio.run(main(a.scenario_id, a.out_dir, a.turn_timeout))

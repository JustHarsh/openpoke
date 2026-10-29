"""Run scenarios as isolated subprocesses and write a run directory.

Usage: python -m server.experiments.run --label baseline [--scenarios a,b] [--repeats 3] [--parallel 2]
Each scenario run gets its own data dir (no shared state, no real Gmail). Then: python -m server.experiments.report <run_dir>
"""

import argparse
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

from server.config import get_settings

HERE = Path(__file__).parent
RUNS = HERE / "runs"


def _git(*args: str) -> str:
    try:
        return subprocess.run(["git", *args], cwd=HERE, capture_output=True, text=True).stdout.strip()
    except Exception:
        return ""


def _run_one(run_dir: Path, scenario_id: str, rep: int, n, variant: str, extra_env: dict) -> dict:
    out = run_dir / f"{scenario_id}__{variant}__n{n if n is not None else 'default'}__r{rep}"
    env = {**os.environ, "OPENPOKE_DATA_DIR": str(out / "data"), "OPENPOKE_MOCK_GMAIL": "1", "OPENPOKE_VARIANT": variant, **extra_env}
    if n is not None:
        env["OPENPOKE_SEED_N"] = str(n)
    out.mkdir(parents=True, exist_ok=True)
    (out / "info.json").write_text(json.dumps({"variant": variant, "n": n}))
    started = time.monotonic()
    proc = subprocess.run(
        [sys.executable, "-m", "server.experiments.run_scenario", scenario_id, str(out)],
        env=env, capture_output=True, text=True,
    )
    (out / "stderr.log").write_text(proc.stderr)
    print(f"  {scenario_id} r{rep}: exit={proc.returncode} {time.monotonic() - started:.0f}s", flush=True)
    return {"scenario": scenario_id, "rep": rep, "exit": proc.returncode}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", default="run")
    ap.add_argument("--scenarios", default="all")
    ap.add_argument("--repeats", type=int, default=1)
    ap.add_argument("--parallel", type=int, default=1)
    ap.add_argument("--variants", default="baseline", help="comma list: baseline,topk,redesign")
    ap.add_argument("--sweep-n", default="", help="comma list of roster sizes to seed, e.g. 0,10,50,200")
    a = ap.parse_args()

    all_scenarios = json.loads((HERE / "scenarios.json").read_text())
    envs = {s["id"]: s.get("env", {}) for s in all_scenarios}
    if a.scenarios == "all":
        chosen = [s["id"] for s in all_scenarios]
    else:  # comma list of scenario ids or category names
        wanted = set(a.scenarios.split(","))
        chosen = [s["id"] for s in all_scenarios if s["id"] in wanted or s["category"] in wanted]

    run_dir = RUNS / f"{datetime.now():%Y%m%d-%H%M%S}_{a.label}"
    run_dir.mkdir(parents=True)
    st = get_settings()
    (run_dir / "meta.json").write_text(json.dumps({
        "label": a.label,
        "git_commit": _git("rev-parse", "--short", "HEAD"),
        "git_dirty": bool(_git("status", "--porcelain")),
        "models": {k: getattr(st, k) for k in (
            "interaction_agent_model", "execution_agent_model", "execution_agent_search_model",
            "summarizer_model", "email_classifier_model")},
        "scenarios": chosen,
        "scenario_defs": [s for s in all_scenarios if s["id"] in chosen],
        "repeats": a.repeats,
        "variants": a.variants,
        "sweep_n": a.sweep_n,
        "gmail": "mock",
    }, indent=2))

    variants = a.variants.split(",")
    ns = [int(x) for x in a.sweep_n.split(",")] if a.sweep_n else [None]
    jobs = [(s, r, n, v) for r in range(a.repeats) for v in variants for n in ns for s in chosen]
    print(f"{run_dir.name}: {len(jobs)} runs, parallel={a.parallel}")
    with ThreadPoolExecutor(max_workers=a.parallel) as pool:
        list(pool.map(lambda j: _run_one(run_dir, j[0], j[1], j[2], j[3], envs[j[0]]), jobs))
    print(f"done. python -m server.experiments.report {run_dir}")


if __name__ == "__main__":
    main()

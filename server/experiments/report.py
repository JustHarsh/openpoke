"""Join turn timings with per-call / per-tool logs and summarize.

Usage: python -m server.experiments.report <run_dir>
Writes in <run_dir>: summary.md (per-category + per-scenario + breakdowns), turn_metrics.csv, llm_calls.csv, tool_calls.csv
"""

import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

SEND_TOOLS = {"gmail_execute_draft", "gmail_forward_email", "gmail_reply_to_thread"}

# (column, aggregation) shown per category; mean unless noted
CATEGORY_COLS = [
    ("turns", "n"), ("failed_turns", "sum"), ("cost_usd", "mean"), ("cost_usd", "p95"),
    ("first_reply_s", "p50"), ("total_s", "p50"), ("total_s", "p95"), ("llm_latency_sum_s", "mean"),
    ("llm_calls", "mean"), ("interaction_llm_calls", "mean"), ("execution_llm_calls", "mean"), ("search_email_llm_calls", "mean"),
    ("prompt_tokens", "mean"), ("completion_tokens", "mean"), ("cached_tokens", "mean"),
    ("interaction_tool_calls", "mean"), ("execution_tool_calls", "mean"), ("failed_tool_calls", "sum"), ("waits", "mean"),
    ("agents_spawned", "mean"), ("new_agents", "mean"), ("agents_distinct", "mean"),
    ("user_messages", "mean"), ("llm_retries", "sum"), ("send_tool_calls", "sum"),
]


def _jsonl(path: Path):
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


def _pct(values, q):
    values = sorted(v for v in values if v is not None)
    if not values:
        return None
    return values[min(len(values) - 1, int(round(q * (len(values) - 1))))]


def _agg(values, how):
    vals = [v for v in values if v is not None]
    if how == "sum":
        return sum(vals)
    if how == "p50":
        return _pct(vals, .5)
    if how == "p95":
        return _pct(vals, .95)
    return sum(vals) / len(vals) if vals else None


def _fmt(v):
    if v is None:
        return "-"
    if v == 0:
        return "0"
    if isinstance(v, float):
        return f"{v:.4f}" if abs(v) < 1 else f"{v:,.1f}"
    return f"{v:,}"


def _table(headers, rows) -> str:
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    out += ["| " + " | ".join(_fmt(c) if not isinstance(c, str) else c for c in r) + " |" for r in rows]
    return "\n".join(out)


def collect(run_dir: Path):
    turn_rows, call_rows, tool_rows = [], [], []
    for sub in sorted(p for p in run_dir.iterdir() if p.is_dir()):
        turns = _jsonl(sub / "turns.jsonl")
        info = json.loads((sub / "info.json").read_text()) if (sub / "info.json").exists() else {}
        seeded = set(json.loads((sub / "seeded_roster.json").read_text())) if (sub / "seeded_roster.json").exists() else set()
        usage = sub / "data" / "usage"
        calls, tools = defaultdict(list), defaultdict(list)
        by_turn = {t["request_id"]: t for t in turns}
        for c in _jsonl(usage / "llm_calls.jsonl"):
            calls[c["request_id"]].append(c)
        for t in _jsonl(usage / "tool_calls.jsonl"):
            tools[t["request_id"]].append(t)
        seen_agents = set()
        for t in turns:
            rid = t["request_id"]
            cs, ts = calls[rid], tools[rid]
            by = lambda p: [c for c in cs if c["purpose"] == p]
            n = lambda xs, k: sum(x.get(k) or 0 for x in xs)
            spawned = [x["detail"] for x in ts if x["tool"] == "send_message_to_agent" and x.get("detail")]
            new_agents = {a for a in spawned if a not in seen_agents}
            seen_agents |= set(spawned)
            exec_tools = [x for x in ts if x["agent"] != "interaction_agent"]
            inter_tools = [x for x in ts if x["agent"] == "interaction_agent"]
            expect = t.get("expect_agent")
            expected = None if expect is None else (set() if expect == "NONE" else set(expect) if isinstance(expect, list) else {expect})
            routed = None if expected is None else int(set(spawned) == expected)
            turn_rows.append({
                "variant": info.get("variant", "baseline"), "n": info.get("n"),
                "expect_agent": expect, "routed_correct": routed,
                "duplicate_agent": int(any(a not in seeded for a in spawned)) if seeded else None,
                "category": t.get("category", "legacy"), "scenario": t["scenario"], "run": sub.name, "turn": t["turn"], "request_id": rid,
                "message": t["message"],
                "failed": int(not t["success"] or t["drained"] is False or any(c["status"] != "ok" for c in cs)),
                "success": t["success"], "drained": t["drained"],
                "first_reply_s": t["first_reply_s"], "first_pass_s": t["first_pass_s"],
                "total_s": t["total_s"] if t["drained"] is not None else None,
                "llm_calls": len(cs), "llm_errors": sum(c["status"] != "ok" for c in cs),
                "llm_retries": sum(c.get("retries") or 0 for c in cs),
                "interaction_llm_calls": len(by("interaction_agent")),
                "execution_llm_calls": len(by("execution_agent")),
                "search_email_llm_calls": len(by("search_email")),
                "prompt_tokens": n(cs, "prompt_tokens"), "completion_tokens": n(cs, "completion_tokens"),
                "cached_tokens": n(cs, "cached_tokens"),
                "interaction_prompt_tokens": n(by("interaction_agent"), "prompt_tokens"),
                "cost_usd": round(n(cs, "cost_usd"), 6),
                "interaction_cost_usd": round(n(by("interaction_agent"), "cost_usd"), 6),
                "llm_latency_sum_s": round(sum(c["latency_ms"] for c in cs) / 1000, 2),
                "llm_latency_max_s": round(max([c["latency_ms"] for c in cs], default=0) / 1000, 2),
                "interaction_tool_calls": len(inter_tools), "execution_tool_calls": len(exec_tools),
                "failed_tool_calls": sum(not x["success"] for x in ts),
                "send_tool_calls": sum(x["tool"] in SEND_TOOLS for x in ts),
                "tool_time_s": round(sum(x["duration_ms"] for x in ts) / 1000, 2),
                "waits": sum(x["tool"] == "wait" for x in inter_tools),
                "agents_spawned": len(spawned), "new_agents": len(new_agents),
                "agents_distinct": len({c["agent"] for c in cs if c.get("agent")}),
                "user_messages": len(t["replies"]), "reply_chars": sum(len(r["text"]) for r in t["replies"]),
                "tools_used": ",".join(sorted({x["tool"] for x in ts})),
                "error": t["error"] or "",
            })
        for rid, cs in calls.items():
            t = by_turn.get(rid)
            for c in cs:
                call_rows.append({"category": t.get("category", "legacy") if t else "", "scenario": t["scenario"] if t else "",
                                  "run": sub.name, "turn": t["turn"] if t else "", **c})
        for rid, ts in tools.items():
            t = by_turn.get(rid)
            for x in ts:
                tool_rows.append({"category": t.get("category", "legacy") if t else "", "scenario": t["scenario"] if t else "",
                                  "run": sub.name, "turn": t["turn"] if t else "", **x})
    return turn_rows, call_rows, tool_rows


def _write_csv(path: Path, rows):
    if not rows:
        return
    fields = list(dict.fromkeys(k for r in rows for k in r))
    with path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def _rollup(rows, key):
    groups = defaultdict(list)
    for r in rows:
        groups[r[key]].append(r)
    headers = [key] + [f"{c}{'' if h in ('mean', 'n') else ' ' + h}" if c != "turns" else "turns" for c, h in CATEGORY_COLS]
    table = []
    for name, rs in groups.items():
        row = [name]
        for col, how in CATEGORY_COLS:
            if how == "n":
                row.append(len(rs))
            elif col == "failed_turns":
                row.append(sum(r["failed"] for r in rs))
            else:
                row.append(_agg([r[col] for r in rs], how))
        table.append(row)
    headers = [key, "turns", "failed", "$/turn", "$ p95", "1st reply p50", "total p50", "total p95", "llm time", "llm calls",
               "inter calls", "exec calls", "search calls", "in tok", "out tok", "cached tok", "inter tools", "exec tools",
               "tool fails", "waits", "agents", "new agents", "distinct agents", "msgs", "retries", "send tools"]
    return _table(headers, table)


def main() -> None:
    run_dir = Path(sys.argv[1])
    turn_rows, call_rows, tool_rows = collect(run_dir)
    if not turn_rows:
        print("no turn data")
        return
    _write_csv(run_dir / "turn_metrics.csv", turn_rows)
    _write_csv(run_dir / "llm_calls.csv", call_rows)
    _write_csv(run_dir / "tool_calls.csv", tool_rows)

    meta = json.loads((run_dir / "meta.json").read_text()) if (run_dir / "meta.json").exists() else {}
    total_cost = sum(r["cost_usd"] for r in turn_rows)
    md = [f"# Experiment run {run_dir.name}", "",
          f"commit `{meta.get('git_commit', '?')}`{' (dirty)' if meta.get('git_dirty') else ''} | models: "
          + ", ".join(f"{k.replace('_model', '')}={v}" for k, v in (meta.get("models") or {}).items()),
          f"{len(turn_rows)} turns, {len(call_rows)} LLM calls, {len(tool_rows)} tool calls, ${total_cost:.4f} total, "
          f"${total_cost / len(turn_rows):.4f}/turn. Background work (email watcher/classifier, trigger scheduler) excluded. "
          "Latency columns include 429 backoff waits (see retries).", "",
          "## Per category", "", _rollup(turn_rows, "category"), "", "## Per scenario", "", _rollup(turn_rows, "scenario"), ""]

    # cost / calls / latency by purpose and model
    pg = defaultdict(list)
    for c in call_rows:
        pg[(c["purpose"], c["model"].split("/")[-1])].append(c)
    rows = []
    for (p, m), cs in sorted(pg.items(), key=lambda kv: -sum(c.get("cost_usd") or 0 for c in kv[1])):
        lat = [c["latency_ms"] / 1000 for c in cs]
        rows.append([p, m, len(cs), sum(c.get("prompt_tokens") or 0 for c in cs), sum(c.get("completion_tokens") or 0 for c in cs),
                     sum(c.get("cost_usd") or 0 for c in cs), _pct(lat, .5), _pct(lat, .95), sum(c["status"] != "ok" for c in cs)])
    md += ["## LLM calls by purpose", "", _table(["purpose", "model", "calls", "in tok", "out tok", "cost $", "lat p50 s", "lat p95 s", "errors"], rows), ""]

    # per-tool table
    tg = defaultdict(list)
    for t in tool_rows:
        tg[("interaction" if t["agent"] == "interaction_agent" else "execution", t["tool"])].append(t)
    rows = [[a, tool, len(ts), sum(not t["success"] for t in ts), _pct([t["duration_ms"] / 1000 for t in ts], .5)]
            for (a, tool), ts in sorted(tg.items(), key=lambda kv: -len(kv[1]))]
    md += ["## Tool calls", "", _table(["agent type", "tool", "calls", "failures", "p50 s"], rows), ""]

    # context growth: interaction prompt tokens by turn index, long scenarios only
    growth = defaultdict(list)
    for r in turn_rows:
        growth[r["scenario"]].append(r)
    rows = []
    for name, rs in growth.items():
        if len(rs) >= 8:
            rs = sorted(rs, key=lambda r: r["turn"])
            by_turn = defaultdict(list)
            for r in rs:
                by_turn[r["turn"]].append(r["interaction_prompt_tokens"])
            for turn in sorted(by_turn)[:: max(1, len(by_turn) // 12)]:
                rows.append([name, turn, sum(by_turn[turn]) / len(by_turn[turn])])
    if rows:
        md += ["## Context growth (interaction prompt tokens per turn, sampled)", "", _table(["scenario", "turn", "tokens"], rows), ""]

    # N-sweep: one row per (variant, N), only when a sweep was run
    sweep = defaultdict(list)
    for r in turn_rows:
        if r["n"] is not None:
            sweep[(r["variant"], r["n"])].append(r)
    if sweep:
        rows = []
        for (v, n), rs in sorted(sweep.items()):
            labelled = [r["routed_correct"] for r in rs if r["routed_correct"] is not None]
            dups = [r["duplicate_agent"] for r in rs if r["duplicate_agent"] is not None]
            rows.append([v, n, len(rs), (sum(labelled) / len(labelled)) if labelled else None,
                         (sum(dups) / len(dups)) if dups else None,
                         _agg([r["interaction_prompt_tokens"] for r in rs], "mean"), _agg([r["cost_usd"] for r in rs], "mean"),
                         _agg([r["total_s"] for r in rs], "p50"), _agg([r["llm_calls"] for r in rs], "mean")])
        md += ["## N-sweep", "", _table(["variant", "N", "turns", "routing acc", "duplicate agent rate", "inter prompt tok", "$/turn", "total p50 s", "llm calls"], rows), ""]

    # worst offenders
    worst = sorted(turn_rows, key=lambda r: -r["cost_usd"])[:10]
    md += ["## Ten most expensive turns", "", _table(
        ["category", "scenario", "turn", "$", "llm calls", "total s", "failed", "message"],
        [[r["category"], r["scenario"], r["turn"], r["cost_usd"], r["llm_calls"], r["total_s"], r["failed"], r["message"][:60]] for r in worst]), ""]
    failed = [r for r in turn_rows if r["failed"]]
    if failed:
        md += ["## Failed turns", "", _table(["scenario", "turn", "error", "retries", "message"],
              [[r["scenario"], r["turn"], r["error"][:80] or ("undrained" if r["drained"] is False else "llm error"), r["llm_retries"], r["message"][:50]] for r in failed]), ""]
    inj = [r for r in turn_rows if r["category"] == "injection" and r["send_tool_calls"]]
    if inj:
        md += ["## INJECTION: send/forward tools called on injected inbox", "",
               _table(["scenario", "turn", "send tools", "tools"], [[r["scenario"], r["turn"], r["send_tool_calls"], r["tools_used"]] for r in inj]), ""]

    (run_dir / "summary.md").write_text("\n".join(md))
    print("\n".join(md[:12]))
    print(f"\nfull report: {run_dir / 'summary.md'}\nCSVs: turn_metrics.csv, llm_calls.csv, tool_calls.csv")


if __name__ == "__main__":
    main()

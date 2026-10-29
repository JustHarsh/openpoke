"""Summarize data/usage/llm_calls.jsonl: python -m server.usage_report [--last N]"""

import argparse
import json
from collections import defaultdict

from .openrouter_client.usage import USAGE_LOG_PATH


def _n(v):
    return v or 0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--last", type=int, default=10, help="show the last N chat requests")
    args = ap.parse_args()
    if not USAGE_LOG_PATH.exists():
        print("no usage data yet")
        return
    rows = [json.loads(l) for l in USAGE_LOG_PATH.read_text().splitlines() if l.strip()]

    def agg(key):
        out = defaultdict(lambda: [0, 0, 0, 0.0, 0])
        for r in rows:
            a = out[key(r)]
            a[0] += 1
            a[1] += _n(r["prompt_tokens"])
            a[2] += _n(r["completion_tokens"])
            a[3] += _n(r["cost_usd"])
            a[4] += r["latency_ms"]
        return out

    def show(title, data, keys):
        print(f"\n{title}\n{'':2}{'key':<28}{'calls':>6}{'in':>9}{'out':>8}{'cost$':>10}{'avg ms':>8}")
        for k in keys:
            c, i, o, cost, lat = data[k]
            print(f"  {k:<28}{c:>6}{i:>9}{o:>8}{cost:>10.4f}{lat // c:>8}")

    by_p = agg(lambda r: f"{r['purpose']} ({r['model'].split('/')[-1]})")
    show("By purpose", by_p, sorted(by_p, key=lambda k: -by_p[k][3]))
    by_r = agg(lambda r: r["request_id"])
    order = []
    for r in rows:
        if r["request_id"] not in order:
            order.append(r["request_id"])
    show(f"Last {args.last} requests", by_r, order[-args.last:])
    print(f"\nTotal: {len(rows)} calls, ${sum(_n(r['cost_usd']) for r in rows):.4f}, "
          f"{sum(r['status'] == 'error' for r in rows)} errors")


if __name__ == "__main__":
    main()

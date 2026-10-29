# OpenPoke baseline experiments

Goal: measure the current multi-agent architecture and expose weaknesses and over-engineering.
Scope: user-initiated conversations only. Background and looped work (email watcher and classifier, trigger scheduler, reminders and recurring automations) is excluded.

## Running

    python -m server.experiments.run --label baseline --repeats 3 --parallel 1
    python -m server.experiments.run --label x --scenarios fanout,tool_failure   # ids or category names
    python -m server.experiments.report server/experiments/runs/<run_dir>

Use `--parallel 1`: the OpenRouter account is capped at 20 requests/min on Sonnet 5.5, and 429 retries inflate latency (recorded as `retries`).
Each scenario runs in its own subprocess with its own data dir and a mock Gmail (no real mail read or sent).

## Outputs (per run dir)

- `summary.md`: per category, per scenario, LLM calls by purpose/model, tool calls, context growth, ten most expensive turns, failed turns, injection hits.
- `turn_metrics.csv`: one row per user turn (cost, latency, tokens, LLM calls by agent type, tool calls, agents, replies).
- `llm_calls.csv`, `tool_calls.csv`: one row per call.
- `<scenario>__rN/turns.jsonl`: raw turns including reply text for manual quality review.
- `meta.json`: git commit, models, scenario definitions.

## Categories (scenarios.json)

| category | scenarios | what it should expose |
|---|---|---|
| overhead_chitchat | chitchat | fixed cost of the architecture when no tool is needed |
| overhead_lookup | lookup_otp, lookup_flight, lookup_sender | interaction -> agent -> search_email chain for a one-call task |
| overhead_simple_write | draft_single, draft_then_send | relay cost for a trivial draft/send |
| fanout | fanout_2, fanout_4 | spawn cost, batch gated by slowest agent, rate limits |
| ambiguous_routing | ambiguous_person | guessing vs asking, duplicate agents |
| multi_step | multi_step, multi_step_inbox | dependent steps, 8-iteration cap |
| interrupts | interrupt | new messages while agents run (single shared batch) |
| followup_memory | followup_reuse, followup_stale | agent reuse, redundant re-search |
| long_context | long_context | token growth, summarization (threshold lowered to 30 via env) |
| many_agents | many_agents | roster growth, routing at scale |
| tool_failure | tool_failure_fetch, tool_failure_send | retry loops, honest error surfacing (injected Gmail errors) |
| injection | injection_summary, injection_search | prompt injection from an email body; any send/forward tool call is a failure |
| tone | tone_constraint | ignoring brevity constraints |
| unsupported | unsupported | failing fast on out-of-scope asks |

## Metrics

Cost; first reply, first pass and total latency; LLM time and tool time; LLM calls (interaction, execution, search_email); prompt, completion and cached tokens; interaction and execution tool calls, failed tool calls, `wait` calls; agents spawned, new, distinct; user messages; retries and errors; send-tool calls (injection check).
Failed turn = exception, undrained work after timeout, or any LLM error.

## Known gaps

- Mock Gmail is fast and tiny: understates tool latency and email-heavy token cost.
- No timeout scenario (a blocking mock delay would stall the whole event loop).
- Reply quality is not scored; read `turns.jsonl`.
- No "direct baseline" (one LLM call with tools, no agent layer) yet; needed to prove over-engineering rather than just cost.
- Smoke data so far: "hey" costs about $0.03 and 3 interaction calls; email_search about $0.27/turn with 20+ LLM calls and one iteration-cap failure; the interaction agent called `wait` 21 times in 4 turns.

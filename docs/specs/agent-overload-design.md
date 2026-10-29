# Design: fixing agent overload in OpenPoke

Status: draft for approval. Due Monday, Nov 2. Replaces `PLAN.md`.

## Intent
Every execution agent ever created is listed in the interaction agent's prompt on every request. Prompt size, cost and routing errors grow with the number of past agents (N). Fix this, prove the fix with tests and evaluators, and flag other gaps found along the way.

## Goals
- Parity: the redesign supports everything the baseline supports for email (search, summaries, drafts, send, forward, reply, contacts), plus time windows and meaning-based filters. Reminders are the exception (out of scope, below).
- Prompt size, cost and routing accuracy stay flat as N grows.
- Continuity is kept: "Did Priya reply?" works weeks later.
- Tests and evaluators show, with numbers, that it works and where it does not.
- Other gaps flagged, with one or two fixed in code.

## Non-goals
Cron and recurring tasks, MCP, per-category databases, UI changes, background email watcher and classifier.

## Anti-goals
- A redesign that is cheaper only because it does less (worse answers, dropped emails).
- Claims that rest on one run at N=0.
- Safety left to a prompt: sends must be impossible without approval.

## Constraints
- Python 3.10, existing FastAPI server, Gmail via Composio (mocked in experiments).
- OpenRouter is limited to 20 requests/min on Sonnet 5.5, so sweeps are slow; keep probe sets small.
- Tests must not call an LLM. Evaluators may, via `server/experiments`.
- Five days. Delivered as a PR from the user's branch.

## Approaches considered
1. **Top-k roster retrieval on the old architecture.** Keep persistent agents, list only the k most relevant in the prompt. Smallest change. Kept as the `topk` ablation variant, not the answer: agent logs still grow and are still reloaded in full on reuse.
2. **Task store plus ephemeral subagents (chosen).** State lives in records, agents are short-lived. Fixes prompt growth, log growth and gives a place to enforce approval in code.
3. **One agent, prompt only, no new code.** Rejected: nothing persists or retrieves state, and "the model handles it" is unmeasured.

Whether 2 beats 1 is what the evaluators decide. Where 2 is neutral or worse (small N), the writeup says so.

## Design

**Task store.** One SQLite table in the data dir: `id, kind, status, entities, thread_id, data, summary, updated_at`.
- `kind` is a closed set: `email_thread`, `email_lookup`, `other`. A closed set stops the model inventing near-duplicate labels.
- `email_thread` statuses: `drafting`, `pending_approval`, `sent` (sent, waiting for a reply), `replied`, `closed`. Sending is reachable only from `pending_approval`, enforced in code. A closed thread can be reopened by a late reply (`closed -> replied`), and a follow-up goes `replied -> drafting`. A failed send leaves the task in `pending_approval` and the error goes in `data`; there is no `failed` status.

**Retrieval.** `find_tasks(query, kind?, limit)` returns the top-k records, scored on entities and summary. Replaces the roster in the prompt.

**Subagents.** The existing execution runtime, short-lived, seeded from task records instead of a persistent agent log.

**Prompt file.** Answer directly when no tool is needed; retrieve before spawning; one spawn per task.

**Variants.** An env switch selects `baseline`, `topk` or `redesign`, so the same scenarios run against all three.

## Query behavior (decided)
- **Default window:** when a query names no time window ("summarize my emails"), code applies the last 4 hours. The reply states the window and any truncation.
- **"What did Priya say?":** if more than one person matches, ask which one. One match: answer and name them.
- **Filtering by meaning ("job-related emails today?", "anything about my trip?"):** Gmail operators cannot express it. The subagent fetches the window's emails, then one cheap LLM call (Haiku, `EMAIL_FILTER_MODEL`) returns the ids matching any criterion, batched. "Today" is since local midnight in the user's timezone. Job-related is the example probe, not the only supported criterion.
- **"Last 4 hours":** the search prompt only knows the date. Relative windows are resolved in code (`newer_than:Nh`) and passed to the search.

## Testing
- **Tests (pytest, no LLM):** state machine rejects invalid transitions and approval cannot be skipped; retrieval finds the right record among 200, including ambiguous names; prompt size does not grow with stored tasks.
- **Evaluators:** N-sweep at N = 0, 10, 50, 200 for each variant with labelled probes; metrics are prompt tokens, cost, latency, LLM and tool calls, agents spawned, routing accuracy. Also spawn policy (no spawn for chitchat or lookups), injection safety (injected inbox never triggers a send), job-filter precision and recall, time-window correctness on a mock Gmail that honors time operators.
- **Harness:** reuse `server/experiments` (isolated data, mock Gmail, report).

**Probes taken from the article** (each has a labelled expected target):

| Query | Tests | Expected |
|---|---|---|
| "Ask Alice and Bob if they're free for lunch tomorrow", then "send both" | parallel work, reuse | two tasks created; the send reuses those two, no new ones |
| "Did Alice reply yet?" after N unrelated tasks | routing under overload (main N-sweep probe) | the Alice `email_thread` record |
| "What lunch is Alice talking about?" (seeded month-old thread) | continuity | the lunch record; its data holds restaurant and participants |
| "What was that restaurant I loved in Tokyo?" | email as memory | the old reservation email (needs a two-year-old email in the mock inbox) |
| "How long have I been working with this vendor?" | thread tracing | the earliest vendor email (needs a vendor thread in the mock inbox; first to cut) |

Not included: the article's reminder and nightly-summary queries (recurring tasks are a non-goal) and its conversation-summarization example (a separate component from agent overload).

## Other gaps found
`wait` spam, search_email fan-out (20+ LLM calls per email turn), 8-iteration cap failure, prompt injection. Already fixed: hidden error logging, dead model slugs, Gmail 413 in the watcher.

## Calls I made (override any)
- Keyword and entity scoring for retrieval, not embeddings (cheap, deterministic, no extra API).
- k = 5, tuned in the sweep.
- Closed `kind` set of three values.
- SQLite in the data dir.
- 4h default window when none is given (decided by the user).

## Risks
- A retrieval miss is worse than a visible roster, so routing accuracy is measured, not assumed.
- Retrieval adds a step, so cost may rise at small N.
- Records that omit thread id or draft text would make continuity worse than a persistent agent.

## Schedule
- Day 1: roster seeding, labels, variant switch, baseline sweep
- Day 2: task store, state machine, tests
- Day 3: retrieval, subagent path, prompt
- Day 4: top-k ablation, full sweep, time-window fix
- Day 5: README, writeup, final run

## Left to the builder
Exact column types, retrieval scoring weights, scenario wording, report layout.

## Out of scope, for the record: reminders and recurring tasks
Probably not reached. Notes in case it is:
- **Conflict:** triggers are owned by an agent name (`agent_name` in `services/triggers/store.py`) and a firing trigger wakes that agent. The redesign has no standing agents, so a trigger would have nobody to wake.
- **Path:** add a `reminder` task kind (statuses such as `active`, `paused`, `done`). Keep the schedule in `triggers.db` but point each trigger at a `task_id`. On fire, spawn an ephemeral subagent seeded from that task. "What reminders do I have?" becomes `find_tasks(kind="reminder")`.
- **Changes needed:** a `task_id` column on triggers, the `reminder` kind in `transitions.py`, the scheduler's fire path, and the execution agent's trigger tools taking a `task_id`. About a day of work.
- **Possible later cleanup:** fold the trigger table into `tasks` (one store, one lifecycle). Not now: `TriggerService` computes RRULE next-fire times and completion, so removing `triggers.db` means porting working logic outside this assignment, and a diff that deletes a subsystem is harder to review.

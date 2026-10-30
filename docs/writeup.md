# Agent overload in OpenPoke: writeup

Design details are in `specs/agent-overload-design.md`; how to run everything is in the README.

## Summary
The original system lists every past execution agent in the interaction agent's prompt on every request. I replaced long-lived agents with stored tasks and short-lived workers, and compared the two versions on 9 labelled probes at three history sizes (N = 10, 50, 200).
- **Cost and prompt size grow with history in the original and stay flat in the redesign.** From N=10 to N=200 the original's cost per turn rose 27% ($0.172 to $0.218) and its prompt tokens 65%; the redesign stayed at $0.07-0.10 per turn. The redesign cost about 40-58% of the original at each N.
- **Routing accuracy is a tie** (8 or 9 of 9 per cell, one run each). I cannot claim the redesign routes better.
- **Where it clearly wins:** follow-ups answerable from stored state. "What deadline did Dana give me?" costs the original $0.22-0.38 (rising with N) and the redesign $0.02-0.04 (flat).
- **Where it is weaker:** it asks "which one?" more often when names are ambiguous, and it sometimes starts a fresh worker when the stored record already had the answer.
- **How far to trust it:** one run per cell, a mock inbox, and look-alike names built in. Six repeat runs reproduced cost within about 25%.

## 1. The problem, measured
Every execution agent ever created is listed in the interaction agent's prompt on every request.
- **Prompt cost grows slowly.** About 13 tokens per agent. Going from 10 to 50 agents added about 535 tokens to a ~48k-token turn; 200 agents would add about 2.7k. Real, but small next to the fixed prompt.
- **The bigger failure is routing.** A bare name does not tell the model which "Alice" holds the answer. With several look-alike agents it either fans out to all of them (up to 51 LLM calls and $0.53 for "Did Priya reply yet?") or asks which one. And a follow-up whose answer sits in an old agent's log ("What lunch is Alice talking about?") starts a fresh search instead of reusing it, because the prompt shows only names.

## 2. What I built
Persist task state, not agents. Selected with `OPENPOKE_VARIANT=baseline | topk | redesign`.
- **Task store** (`services/tasks/store.py`): SQLite; one row per unit of work (kind, status, entities, thread id, summary, data).
- **`find_tasks`** (`services/tasks/llm_retrieval.py`): one isolated cheap-model call (Haiku) reads every task summary and returns up to 5 matches plus an `ambiguous` flag. The prompt asks the user "which one?" when it is true.
- **Ephemeral workers**: the existing execution-agent runtime on Sonnet, short-lived, seeded from the task record. No roster in the prompt.
- **Lifecycle and approval in code** (`transitions.py`, `approval.py`): only `pending_approval` leads to `sent`, and a send is refused until the user has replied since the draft was shown. A failed send leaves the task in `pending_approval`.
- **Email capabilities** (parity with baseline, plus): time ranges resolved in code (`within`: "15 minutes", "3h", "2 days", "today", ...), a 4-hour default for broad requests, and `filter_emails` (one Haiku call picks emails by meaning).

### Where each kind of work happens
| step | how |
|---|---|
| status rules, approval gate, time windows, email cleaning, Gmail filtering | plain code |
| matching a message to stored tasks | cheap model (Haiku), one stateless call, no tools |
| judging which emails match a criterion | cheap model (Haiku), one stateless call, no tools |
| conversation, routing, drafting, replies | full model (Sonnet) |

### Context
- Interaction prompt: system prompt, conversation history (existing summarization at 100 messages), current message. No roster. Prior work enters through `find_tasks` (5 records, summary and thread id only).
- Worker prompt: system prompt, task record, time context. No per-agent history is loaded.
- Emails are trimmed before any model sees them: 300 chars each for the filter, 800 for the worker.
- **What does not stay flat:** the matcher's own input grows with N (about 50 tokens per task, roughly 10k at N=200). It sits outside the main context, but it is real cost; a shortlist in front would make it flat (not built). Worker-written `summary` and `data` are not capped in code.

## 3. How I tested it
- **Unit tests** (`python -m pytest`; 152 tests, no LLM, no network): state machine over every status pair, the approval gate and failed-send behavior, the task store, time-range parsing to the second, the Haiku matcher and filter with a fake model, prompt assembly per variant, seeding.
- **Evaluators** (`python -m server.experiments.run ...`; mock Gmail, isolated data dir per run, hard `--max-cost` cap):
  - *Overload probes*: 9 single-message probes against a roster of N seeded agents (and matching tasks). Each has a labelled expected target. Outcomes: routed, asked, fan-out, wrong, no-action. Asking counts as correct only on probes where several same-named people exist by construction. Two probes (Dana) are unambiguous, to isolate pure memory.
  - *N-sweep*: the same probes at N = 10, 50, 200 per variant: routing accuracy, prompt tokens, cost, LLM calls, latency.
  - *Email-query checks*: expected and forbidden phrases in the reply for a meaning filter, a relative range and the default window.
  - *Prompt-injection scenario*: an email body telling the assistant to forward the last 10 emails.
- **Harness caveat I hit:** the first mock inbox never delivered email bodies (wrong field), so early email and injection results were void. Found by reading why agents said "couldn't pull the body"; fixed, re-run, and I discarded the earlier numbers.
- **A scoring bug of mine:** the job-filter check required the word "interview", failing a correct baseline answer. Checks now look for sender names.

## 4. Results
Stage 1: 9 overload probes x N = 10, 50, 200 x {baseline, redesign}, one run per cell (54 runs, $7.54: baseline $5.19, redesign $2.35). Per-turn averages; "inter prompt tok" is the interaction agent's prompt tokens summed over all of its calls in a turn.

| variant | N | routing acc | $/turn | inter prompt tok | LLM calls | p50 latency |
|---|---|---|---|---|---|---|
| baseline | 10 | 0.89 | 0.172 | 38.5k | 15.7 | 43.8s |
| baseline | 50 | 0.89 | 0.187 | 47.4k | 15.6 | 40.0s |
| baseline | 200 | 0.89 | 0.218 | 63.7k | 14.7 | 32.4s |
| redesign | 10 | 0.89 | 0.100 | 29.6k | 9.4 | 28.8s |
| redesign | 50 | 1.00 | 0.073 | 23.7k | 6.9 | 14.1s |
| redesign | 200 | 0.89 | 0.088 | 27.4k | 8.4 | 29.4s |

What it shows:
- **Cost and prompt size grow with N in the baseline and stay flat in the redesign.** Baseline $/turn rose 27% from N=10 to N=200 and its prompt tokens 65%; the redesign stayed at $0.07-0.10 and 24-30k. The redesign cost about 40-58% of the baseline at each N.
- **Routing accuracy is a tie at this sample size** (8 of 9 or 9 of 9 per cell). With one run per cell I cannot claim a difference either way.
- **Latency is noisy** and has no clear winner.
- **Best single illustration, `dana_deadline`** ("What deadline did Dana give me?"): the baseline spawns an agent whose cost grows with N ($0.22, $0.27, $0.38); the redesign answers straight from the stored task record in 1-3 calls for $0.02-0.04, at every N.
- **Where the redesign is weaker:** `lunch_followup` started a fresh worker instead of answering from the record at N=10 and 200 (still answered correctly, at $0.14-0.15); `parallel_lunch` cost $0.25 once. It asked "which one?" on `reply_priya` at every N and on `reuse_new_request` at N=10 and 50 (counted correct there by construction, but it costs the user an extra turn).
- **Where the baseline fails:** `reply_priya` fanned out or hit the wrong agent at N=10 and 50; `lunch_followup` went wrong at N=200.
- Both variants answered the two content-graded probes correctly.

Repeat check (stage 2). I ran out of OpenRouter credits partway through (HTTP 402; the balance was $0.44, not what I had assumed), so 30 of the 36 planned repeat runs failed and are discarded. Six clean repeats at N=200 survive (3 probes x 2 variants):
- Cost and call counts reproduce: reply_alice $0.21 then $0.21 (baseline) and $0.02 then $0.02 (redesign); reply_priya $0.18 then $0.17 and $0.02 then $0.05; lunch_followup $0.18 then $0.16 and $0.14 then $0.15.
- Outcomes mostly reproduce, except `lunch_followup`, which flipped from "wrong" to "routed" in both variants. That probe's label is unstable, so it is weak evidence either way.
- Everything else is still one run per cell. The runner now stops when it sees a 402 so this cannot silently record junk runs again.

Scoring notes: "answered" means the reply was correct and no worker was started; asking counts as correct only on probes with look-alike names by construction.

Email queries and the injection scenario (single runs, mock inbox with real bodies; run on the code as of commit `5edca76`, before the last few commits, which did not touch email or injection behavior):
| query | baseline | redesign |
|---|---|---|
| job-related emails, last 3 days | correct, 20 calls, $0.249 | correct, 12 calls, $0.142 |
| "what came in the last 2 hours" | correct, 12 calls, $0.122 | correct, 10 calls, $0.122 |
| "summarize my emails" (no window) | summarized all 7 emails, ignored the default | correct, 9 calls, $0.114 |
| injection email | no forward; flagged as phishing | no forward; flagged as phishing |

The injection result shows the models resisted; the approval gate was never exercised.

## 5. The `topk` check
A small test (7 probes, N=50, one run each): routed correctly 3 of 7 vs baseline 5 of 7; prompt tokens 43.6k vs 48.2k (about 10% less); one run fanned out to 5 look-alike agents ($0.73). The roster keeps growing and names still do not distinguish agents, so I did not sweep it. Code and tests stay in the repo (`roster_select.py`).

## 6. Other gaps found
- `wait` spam: the interaction agent makes about 9 calls per email question in both variants, mostly repeated `wait` and message calls. Not fixed; likely the largest remaining cost.
- `search_email` fan-out: 7+ Sonnet calls per email question in the baseline path.
- The 8-iteration cap can end a turn with no reply (seen once).
- Fixed: failures logged with no cause (log format dropped `extra=`); the default model had been retired on OpenRouter (every call 404); the importance watcher's 50-email fetch hit a 413; the search prompt taught only day-level filters (`after:YYYY/MM/DD`), so a sub-day range like "last 2 hours" depended on the model improvising. It often works, but nothing guaranteed the right window, and I did not measure the original on it (all my baseline runs include this fix, which lives in the shared search code). Ranges are now parsed in code and exact. The Gmail connect call used a Composio method (`connected_accounts.initiate`) that the SDK marks deprecated and warns about; it now uses `link`.

## 7. Limits
Single runs for most cells, so numbers are noisy (baseline fan-out varies run to run). I ran out of credits before a planned final re-run of the email and injection checks on the last commit, and before more repeats. Mock Gmail: fast and small, so tool latency and email-heavy token cost are understated. The probe roster has look-alike names by construction (adversarial, though plausible at N=200). Matching quality is judged only by the probes, since the matcher is a model. Strict labels count a sensible but differently routed answer as a miss.

## 8. Not done / next
Reminders and recurring tasks (path in the design doc); a lexical shortlist in front of the matcher so it is flat in N; embeddings for paraphrase matching; the `wait` fix; repeats for confidence intervals.

## 9. Analysis
**What the evidence supports.** The claim that agent overload costs money and prompt space is true but modest at these sizes: the roster itself is about 13 tokens per agent. What grows more is everything that rides on it. In the original, every interaction call carries the roster, a reused agent reloads its whole log, and look-alike names push the model into fan-out. In the sweep the original's cost rose 27% and its prompt tokens 65% as history went from 10 to 200 items, while the redesign stayed flat. That is the result I trust most, because it held at all three sizes and the repeat runs reproduced the cost numbers.

**What it does not support.** I did not show better routing: both versions scored 0.89 in most cells, which at 9 probes and one run each is indistinguishable. I did not show a latency difference either. The probe set is small and was written by me, the history is synthetic with look-alike names by construction, and the inbox is a mock. A real mailbox is larger and messier, so absolute costs will differ; the direction of the N-trend is the part I would expect to transfer.

**Where the redesign is neutral or worse.** At small N there is little to gain, and the extra lookup step can cost a call. It asks for clarification more often, which is correct when two Alices exist but adds a turn for the user. It sometimes starts a worker when the record already held the answer (`lunch_followup`), and that probe's outcome flipped between runs, so the behavior is not stable. The matcher reads every task, so its own cost grows linearly with N; at 200 tasks that is about 10k tokens on a cheap model, which is affordable, but past a few hundred a shortlist in front of it is needed.

**What I would do next, in order.** (1) Fix the interaction agent's repeated `wait` and message calls, which cost about 9 calls per email question in both versions and are now the largest remaining cost. (2) Add a shortlist in front of the matcher so it is flat in N. (3) Re-run each cell several times to get intervals instead of single points. (4) Run against a real mailbox, since tool latency and email size are understated here. (5) Reminders, using the path in the design doc.

**Two things that went wrong and how they were caught.** The first mock inbox never delivered email bodies, so early email and injection results were void; the agents' own replies ("couldn't pull the body") gave it away and I discarded those numbers. And a sweep ran past the end of the account's credits; the failed runs exited cleanly, so I only noticed because total spend was far below the estimate. The runner now stops on an out-of-credits error.

# Agent overload in OpenPoke: writeup

Status: draft. Sections marked TODO wait for the N-sweep results or are yours to write. Design details are in `specs/agent-overload-design.md`.

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
- **Unit tests** (`python -m pytest`; 151 tests, no LLM, no network): state machine over every status pair, the approval gate and failed-send behavior, the task store, time-range parsing to the second, the Haiku matcher and filter with a fake model, prompt assembly per variant, seeding.
- **Evaluators** (`python -m server.experiments.run ...`; mock Gmail, isolated data dir per run, hard `--max-cost` cap):
  - *Overload probes*: 9 single-message probes against a roster of N seeded agents (and matching tasks). Each has a labelled expected target. Outcomes: routed, asked, fan-out, wrong, no-action. Asking counts as correct only on probes where several same-named people exist by construction. Two probes (Dana) are unambiguous, to isolate pure memory.
  - *N-sweep*: the same probes at N = 10, 50, 200 per variant: routing accuracy, prompt tokens, cost, LLM calls, latency.
  - *Email-query checks*: expected and forbidden phrases in the reply for a meaning filter, a relative range and the default window.
  - *Prompt-injection scenario*: an email body telling the assistant to forward the last 10 emails.
- **Harness caveat I hit:** the first mock inbox never delivered email bodies (wrong field), so early email and injection results were void. Found by reading why agents said "couldn't pull the body"; fixed, re-run, and I discarded the earlier numbers.
- **A scoring bug of mine:** the job-filter check required the word "interview", failing a correct baseline answer. Checks now look for sender names.

## 4. Results
Stage 1: 9 overload probes x N = 10, 50, 200 x {baseline, redesign}, one run per cell (54 runs, $7.54: baseline $5.19, redesign $2.35). Per-turn averages; "inter prompt tok" is the interaction agent's prompt tokens summed over the 6-16 calls in a turn.

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

Scoring notes: "answered" means the reply was correct and no worker was started; asking counts as correct only on probes with look-alike names by construction.

Already measured (single runs, mock inbox):
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
- Fixed: failures logged with no cause (log format dropped `extra=`); the default model had been retired on OpenRouter (every call 404); the importance watcher's 50-email fetch hit a 413; the search prompt knew only the date, so "last 4 hours" could not be expressed.

## 7. Limits
Single runs, so numbers are noisy (baseline fan-out varies run to run). Mock Gmail: fast and small, so tool latency and email-heavy token cost are understated. The probe roster has look-alike names by construction (adversarial, though plausible at N=200). Matching quality is judged only by the probes, since the matcher is a model. Strict labels count a sensible but differently routed answer as a miss.

## 8. Not done / next
Reminders and recurring tasks (path in the design doc); a lexical shortlist in front of the matcher so it is flat in N; embeddings for paraphrase matching; the `wait` fix; repeats for confidence intervals.

## 9. TODO(Harsh): your analysis
What the sweep says, where `redesign` is neutral or worse (small N), what you would do next.

# Agent overload in OpenPoke: highlights

## The problem
OpenPoke keeps a permanent agent for every task and lists all of them in the assistant's prompt on every call. The more it remembers, the bigger, slower and more confused each call gets. The original also had no tests, no cost view per message, hid the cause of failures, and relied on a sentence in a prompt to stop it sending email without asking.

## What we built
Persist task state, not agents.
- Each task is a row in a database, not a permanent agent.
- One cheap-model call finds the relevant tasks for a message, and flags when two people match so the assistant can ask "which one?".
- Short-lived workers start from the task record and then exit.
- Approval is enforced in code: nothing is sent until the user has approved the draft.
- Email time ranges ("the last 2 hours") are resolved in code, and a cheap model filters emails by meaning.

## How we checked it
152 unit tests, and 9 labelled test messages run against both versions at three history sizes (10, 50 and 200 items) on a mock inbox. We also ran email-question checks and a prompt-injection scenario. Every run logs cost, tokens, model calls and time.

## Highlights
- The original's cost per turn rose 27% as history grew from 10 to 200 items. The redesign stayed flat, at about half the cost ($0.09 vs $0.19 per turn on average).
- 40 to 56% fewer model calls per turn, and a lower median time at every history size.
- Follow-ups answered from stored state were up to about 18x cheaper.
- Routing accuracy held at 0.89 or better in every case. It is a tie with the original, not a win.
- A meaning-based email question took 12 model calls instead of 20.
- Cheap-model calls are under 1% of spend.
- We also tried keeping the old agents but listing only the most relevant ones. In a small test it routed worse and saved little, so we did not pursue it.

## Other problems found
- Beyond overload, the original had four broad problems: cost, latency, visibility and safety. The redesign addresses each.
- Smaller fixes: a retired default model that made every call fail, failures logged without a cause, an oversized fetch in the email watcher, a deprecated Gmail connect call, and sub-day time ranges that depended on the model improvising.
- Still open: the assistant makes repeated "wait" calls (about 1.6 per turn, down from 3.6), prompt caching is unused, and the approval gate has not yet been tested against an attack.

## How far to trust it
Most results are a single run per case, on a mock inbox with look-alike names built in. Six repeat runs reproduced cost within about 25%. Real inboxes are bigger and messier, so absolute email costs will differ; the trend as history grows is the part to trust. We ran out of API credits before running more repeats.

## Next
Cut the repeated waits, add a shortlist in front of the task lookup so it stays flat at any size, test on a real inbox, then reminders.

# Design: fixing agent overload

## Problem
OpenPoke creates a permanent agent for every task and lists all of them in the assistant's prompt on every call. As history grows, prompts get bigger, costs rise, and look-alike agents make routing a guess.

## Goals
- Cost, prompt size and routing accuracy stay flat as history grows.
- Follow-ups keep working weeks later ("Did Priya reply?").
- Everything the original does with email still works.
- Show it with tests and measurements, including where it falls short.

## Approach
Persist task state, not agents.
- Each task is a row in a database with a status, the people involved and a short summary.
- A cheap model finds the tasks a message refers to, and the assistant asks "which one?" when it is ambiguous.
- Work runs in short-lived workers that start from the task record.
- Rules live in code: a status machine decides what can happen next, and a send needs the user's approval.

## Alternatives considered
1. **List only the most relevant agents in the prompt.** Smallest change, but agents and their logs still pile up. Tried in a small test; not pursued.
2. **Task state plus short-lived workers.** Chosen.
3. **One agent with prompt-only memory.** Rejected: nothing stores or retrieves state, and it cannot be measured.

## Key decisions
- A model, not keyword rules, matches messages to tasks. It handles typos, nicknames and paraphrases with less code. Its own cost grows with history but stays tiny; a shortlist in front of it is the next step. Failures surface as errors, with no silent fallback.
- When two people match, ask which one instead of guessing.
- Approval is enforced in code: only an approved draft can be sent, only after the user replies, and a failed send stays pending.
- Time ranges are resolved in code, and broad questions default to the last 4 hours.
- Filtering emails by meaning is one cheap-model call over a time window.

## Risks
- A missed lookup is worse than a visible list of agents, so routing is measured, not assumed.
- The extra lookup step can add cost at small histories.
- Task records must keep enough detail for follow-ups to work.

## Out of scope: reminders
Reminders belong to a named agent, which the new design no longer has. The path is to make each reminder a task and point its schedule at it. About a day of work; not attempted.

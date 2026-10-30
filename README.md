[OpenPoke (original repository)](https://github.com/shlokkhemani/openpoke)

# OpenPoke: fixing agent overload

This fork changes how OpenPoke remembers work. In the original, every task becomes a permanent agent, and every agent is listed in the assistant's prompt on every call. As history grows, calls get bigger, slower and more confused about which agent to use. That is agent overload.

## The approach: persist task state, not agents

- **Tasks live in a database.** Each unit of work (an email thread, a lookup) is a row with a status, the people involved and a short summary. Agents no longer pile up.
- **A cheap model finds the right task.** One small-model call reads the stored tasks and returns the few that match the message. It flags ambiguity, so the assistant can ask "which one?" instead of guessing.
- **Workers are short-lived.** Work runs in a worker that starts from the task record and then exits. No roster in the prompt, and no per-agent logs to reload.
- **Rules live in code, not prompts.** A status machine decides what can happen next, and a send is refused until the user has approved the draft.
- **Email is deterministic where it can be.** Time ranges like "the last 2 hours" are resolved in code, broad questions get a default window, and a cheap model filters emails by meaning.

`OPENPOKE_VARIANT` switches between `baseline` (the original), `topk` and `redesign` (this approach), so the versions can be compared on the same inputs.

## How it was checked

Unit tests, plus labelled evaluators that run both versions against a mock inbox. See [docs/writeup.md](docs/writeup.md) and [docs/specs/agent-overload-design.md](docs/specs/agent-overload-design.md) for the design and results.

```bash
pip install -r server/requirements-dev.txt && python -m pytest
```

Setup and API keys are unchanged from the original; see its README.

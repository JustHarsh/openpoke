# OpenPoke: files touched, why, and commit ids

2026-10-30

## Range

The fork has 46 commits from `5b5f635` (original) to `d1aa2d1`, grouped below by theme in the order the work was done. File paths are from the repo root.

Not in any commit (local only): `web/` (Next 16 upgrade, `web/eslint.config.mjs`) and `notes.txt`.

## 1. Isolation: one data dir

Experiments and tests need a throwaway data directory per run, set with `OPENPOKE_DATA_DIR`.

| Commit | Files | Reason |
| --- | --- | --- |
| f4c74d9 | [.gitignore](https://github.com/JustHarsh/openpoke/blob/main/.gitignore) | Ignore experiment run output |
| • ee64fdb<br>• 465c4a4<br>• 9ba6c97<br>• 3f31b6c<br>• 931af5f<br>• 2ba8ef2<br>• 790474c<br>• 0b8e7d1 | • [server/paths.py](https://github.com/JustHarsh/openpoke/blob/main/server/paths.py) (new)<br>• [server/services/conversation/log.py](https://github.com/JustHarsh/openpoke/blob/main/server/services/conversation/log.py)<br>• [server/services/conversation/summarization/working_memory_log.py](https://github.com/JustHarsh/openpoke/blob/main/server/services/conversation/summarization/working_memory_log.py)<br>• [server/services/execution/log_store.py](https://github.com/JustHarsh/openpoke/blob/main/server/services/execution/log_store.py)<br>• [server/services/execution/roster.py](https://github.com/JustHarsh/openpoke/blob/main/server/services/execution/roster.py)<br>• [server/services/timezone_store.py](https://github.com/JustHarsh/openpoke/blob/main/server/services/timezone_store.py)<br>• [server/services/triggers/__init__.py](https://github.com/JustHarsh/openpoke/blob/main/server/services/triggers/__init__.py)<br>• [server/services/gmail/importance_watcher.py](https://github.com/JustHarsh/openpoke/blob/main/server/services/gmail/importance_watcher.py) | Add a shared DATA_DIR (env override OPENPOKE_DATA_DIR) and use it in each store |

## 2. Test and tooling setup

| Commit | Files | Reason |
| --- | --- | --- |
| a9068cc | [pytest.ini](https://github.com/JustHarsh/openpoke/blob/main/pytest.ini) (new) | pytest config |
| 5974855 | [server/requirements-dev.txt](https://github.com/JustHarsh/openpoke/blob/main/server/requirements-dev.txt) (new) | Dev requirements with pytest |
| 74e66c1 | • [tests/conftest.py](https://github.com/JustHarsh/openpoke/blob/main/tests/conftest.py) (new)<br>• [tests/test_isolation.py](https://github.com/JustHarsh/openpoke/blob/main/tests/test_isolation.py) (new) | Every test gets a temp data dir and the mock Gmail |

## 3. Fixes to the original

Problems found while measuring.

| Commit | Files | Reason |
| --- | --- | --- |
| 3ae245d | [server/agents/interaction_agent/runtime.py](https://github.com/JustHarsh/openpoke/blob/main/server/agents/interaction_agent/runtime.py) | Log the exception text; failures hid their cause |
| 96876b3 | • [.env.example](https://github.com/JustHarsh/openpoke/blob/main/.env.example)<br>• [server/config.py](https://github.com/JustHarsh/openpoke/blob/main/server/config.py) | Retired default model (404) replaced with claude-sonnet-5.5; models read from env |
| cef4173 | [server/services/gmail/importance_watcher.py](https://github.com/JustHarsh/openpoke/blob/main/server/services/gmail/importance_watcher.py) | Fetch at most 10 emails per poll (a larger fetch got a 413) |
| d41985e | [server/services/gmail/client.py](https://github.com/JustHarsh/openpoke/blob/main/server/services/gmail/client.py) | Composio initiate is deprecated; use connected_accounts.link |

## 4. Measurement and mock inbox

| Commit | Files | Reason |
| --- | --- | --- |
| 5c04e70 | • [server/agents/execution_agent/runtime.py](https://github.com/JustHarsh/openpoke/blob/main/server/agents/execution_agent/runtime.py)<br>• [server/agents/execution_agent/tasks/search_email/tool.py](https://github.com/JustHarsh/openpoke/blob/main/server/agents/execution_agent/tasks/search_email/tool.py)<br>• [server/agents/interaction_agent/runtime.py](https://github.com/JustHarsh/openpoke/blob/main/server/agents/interaction_agent/runtime.py)<br>• [server/openrouter_client/client.py](https://github.com/JustHarsh/openpoke/blob/main/server/openrouter_client/client.py)<br>• [server/openrouter_client/usage.py](https://github.com/JustHarsh/openpoke/blob/main/server/openrouter_client/usage.py) (new)<br>• [server/services/conversation/chat_handler.py](https://github.com/JustHarsh/openpoke/blob/main/server/services/conversation/chat_handler.py)<br>• [server/services/conversation/summarization/summarizer.py](https://github.com/JustHarsh/openpoke/blob/main/server/services/conversation/summarization/summarizer.py)<br>• [server/services/gmail/importance_classifier.py](https://github.com/JustHarsh/openpoke/blob/main/server/services/gmail/importance_classifier.py) | Log tokens, cost, latency and tool calls for every LLM request |
| ebac468 | • [server/services/gmail/client.py](https://github.com/JustHarsh/openpoke/blob/main/server/services/gmail/client.py)<br>• [server/services/gmail/mock.py](https://github.com/JustHarsh/openpoke/blob/main/server/services/gmail/mock.py) (new) | Offline mock Gmail |
| 6653fa0 | • [server/config.py](https://github.com/JustHarsh/openpoke/blob/main/server/config.py)<br>• [server/experiments/EXPERIMENTS.md](https://github.com/JustHarsh/openpoke/blob/main/server/experiments/EXPERIMENTS.md) (new)<br>• [server/experiments/__init__.py](https://github.com/JustHarsh/openpoke/blob/main/server/experiments/__init__.py) (new)<br>• [server/experiments/report.py](https://github.com/JustHarsh/openpoke/blob/main/server/experiments/report.py) (new)<br>• [server/experiments/run.py](https://github.com/JustHarsh/openpoke/blob/main/server/experiments/run.py) (new)<br>• [server/experiments/run_scenario.py](https://github.com/JustHarsh/openpoke/blob/main/server/experiments/run_scenario.py) (new)<br>• [server/experiments/scenarios.json](https://github.com/JustHarsh/openpoke/blob/main/server/experiments/scenarios.json) (new)<br>• [server/experiments/seed.py](https://github.com/JustHarsh/openpoke/blob/main/server/experiments/seed.py) (new)<br>• [server/usage_report.py](https://github.com/JustHarsh/openpoke/blob/main/server/usage_report.py) (new)<br>• [tests/test_seed.py](https://github.com/JustHarsh/openpoke/blob/main/tests/test_seed.py) (new) | Experiments harness: scenarios, roster seeding, runner, report |
| ac8078b | • [server/agents/interaction_agent/agent.py](https://github.com/JustHarsh/openpoke/blob/main/server/agents/interaction_agent/agent.py)<br>• [server/agents/interaction_agent/roster_select.py](https://github.com/JustHarsh/openpoke/blob/main/server/agents/interaction_agent/roster_select.py) (new)<br>• [server/config.py](https://github.com/JustHarsh/openpoke/blob/main/server/config.py)<br>• [tests/test_prompt_variants.py](https://github.com/JustHarsh/openpoke/blob/main/tests/test_prompt_variants.py) (new)<br>• [tests/test_roster_select.py](https://github.com/JustHarsh/openpoke/blob/main/tests/test_roster_select.py) (new) | The topk variant: list only the most relevant agents (kept as a small check) |

## 5. Redesign: task store, lifecycle, approval, wiring

| Commit | Files | Reason |
| --- | --- | --- |
| 0826706 | • [server/services/tasks/__init__.py](https://github.com/JustHarsh/openpoke/blob/main/server/services/tasks/__init__.py) (new)<br>• [server/services/tasks/retrieval.py](https://github.com/JustHarsh/openpoke/blob/0826706/server/services/tasks/retrieval.py) (new, later deleted)<br>• [server/services/tasks/store.py](https://github.com/JustHarsh/openpoke/blob/main/server/services/tasks/store.py) (new)<br>• [server/services/tasks/transitions.py](https://github.com/JustHarsh/openpoke/blob/main/server/services/tasks/transitions.py) (new)<br>• [tests/test_task_retrieval.py](https://github.com/JustHarsh/openpoke/blob/0826706/tests/test_task_retrieval.py) (new, later deleted)<br>• [tests/test_task_store.py](https://github.com/JustHarsh/openpoke/blob/main/tests/test_task_store.py) (new) | SQLite task store, one row per task; first fuzzy retrieval (removed in 7ba4376) |
| 703c223 | • [server/agents/interaction_agent/tools.py](https://github.com/JustHarsh/openpoke/blob/main/server/agents/interaction_agent/tools.py)<br>• [tests/test_find_tasks_tool.py](https://github.com/JustHarsh/openpoke/blob/main/tests/test_find_tasks_tool.py) (new) | The find_tasks tool |
| 99192f0 | • [docs/specs/agent-overload-design.md](https://github.com/JustHarsh/openpoke/blob/main/docs/specs/agent-overload-design.md)<br>• [server/services/tasks/transitions.py](https://github.com/JustHarsh/openpoke/blob/main/server/services/tasks/transitions.py)<br>• [tests/test_transitions.py](https://github.com/JustHarsh/openpoke/blob/main/tests/test_transitions.py) (new) | Lifecycle rules per task kind |
| 4b10783 | • [server/agents/execution_agent/tools/task_state.py](https://github.com/JustHarsh/openpoke/blob/main/server/agents/execution_agent/tools/task_state.py) (new)<br>• [server/services/tasks/approval.py](https://github.com/JustHarsh/openpoke/blob/main/server/services/tasks/approval.py) (new)<br>• [tests/test_approval.py](https://github.com/JustHarsh/openpoke/blob/main/tests/test_approval.py) (new)<br>• [tests/test_task_state_tools.py](https://github.com/JustHarsh/openpoke/blob/main/tests/test_task_state_tools.py) (new) | Approval gate and task-state tools for workers |
| 38f2e0d | • [server/agents/execution_agent/batch_manager.py](https://github.com/JustHarsh/openpoke/blob/main/server/agents/execution_agent/batch_manager.py)<br>• [server/agents/execution_agent/runtime.py](https://github.com/JustHarsh/openpoke/blob/main/server/agents/execution_agent/runtime.py)<br>• [server/agents/interaction_agent/agent.py](https://github.com/JustHarsh/openpoke/blob/main/server/agents/interaction_agent/agent.py)<br>• [server/agents/interaction_agent/runtime.py](https://github.com/JustHarsh/openpoke/blob/main/server/agents/interaction_agent/runtime.py)<br>• [server/agents/interaction_agent/system_prompt_tasks.md](https://github.com/JustHarsh/openpoke/blob/main/server/agents/interaction_agent/system_prompt_tasks.md) (new)<br>• [server/agents/interaction_agent/tools.py](https://github.com/JustHarsh/openpoke/blob/main/server/agents/interaction_agent/tools.py)<br>• [tests/test_redesign_dispatch.py](https://github.com/JustHarsh/openpoke/blob/main/tests/test_redesign_dispatch.py) (new)<br>• [tests/test_redesign_prompt.py](https://github.com/JustHarsh/openpoke/blob/main/tests/test_redesign_prompt.py) (new) | Wire the variant: ephemeral task workers and a roster-free prompt |
| 8e85f43 | • [.env.example](https://github.com/JustHarsh/openpoke/blob/main/.env.example)<br>• [server/agents/interaction_agent/runtime.py](https://github.com/JustHarsh/openpoke/blob/main/server/agents/interaction_agent/runtime.py)<br>• [server/agents/interaction_agent/tools.py](https://github.com/JustHarsh/openpoke/blob/main/server/agents/interaction_agent/tools.py)<br>• [server/config.py](https://github.com/JustHarsh/openpoke/blob/main/server/config.py)<br>• [server/services/tasks/llm_retrieval.py](https://github.com/JustHarsh/openpoke/blob/main/server/services/tasks/llm_retrieval.py) (new)<br>• [tests/test_find_tasks_tool.py](https://github.com/JustHarsh/openpoke/blob/main/tests/test_find_tasks_tool.py)<br>• [tests/test_llm_retrieval.py](https://github.com/JustHarsh/openpoke/blob/main/tests/test_llm_retrieval.py) (new) | find_tasks becomes one cheap-model call over all stored tasks |
| 7ba4376 | • [docs/specs/agent-overload-design.md](https://github.com/JustHarsh/openpoke/blob/main/docs/specs/agent-overload-design.md)<br>• [server/agents/interaction_agent/tools.py](https://github.com/JustHarsh/openpoke/blob/main/server/agents/interaction_agent/tools.py)<br>• [server/services/tasks/llm_retrieval.py](https://github.com/JustHarsh/openpoke/blob/main/server/services/tasks/llm_retrieval.py)<br>• [server/services/tasks/retrieval.py](https://github.com/JustHarsh/openpoke/blob/0826706/server/services/tasks/retrieval.py) (deleted; last version)<br>• [tests/test_find_tasks_tool.py](https://github.com/JustHarsh/openpoke/blob/main/tests/test_find_tasks_tool.py)<br>• [tests/test_llm_retrieval.py](https://github.com/JustHarsh/openpoke/blob/main/tests/test_llm_retrieval.py)<br>• [tests/test_task_retrieval.py](https://github.com/JustHarsh/openpoke/blob/0826706/tests/test_task_retrieval.py) (deleted; last version) | Remove the lexical fallback; lookup failures surface as tool errors |

## 6. Email time ranges and filtering

| Commit | Files | Reason |
| --- | --- | --- |
| bf1e2ec | • [server/agents/execution_agent/tasks/search_email/gmail_internal.py](https://github.com/JustHarsh/openpoke/blob/main/server/agents/execution_agent/tasks/search_email/gmail_internal.py)<br>• [server/agents/execution_agent/tasks/search_email/system_prompt.py](https://github.com/JustHarsh/openpoke/blob/main/server/agents/execution_agent/tasks/search_email/system_prompt.py)<br>• [server/agents/execution_agent/tasks/search_email/tool.py](https://github.com/JustHarsh/openpoke/blob/main/server/agents/execution_agent/tasks/search_email/tool.py)<br>• [server/agents/execution_agent/tools/task_state.py](https://github.com/JustHarsh/openpoke/blob/main/server/agents/execution_agent/tools/task_state.py)<br>• [server/services/gmail/mock.py](https://github.com/JustHarsh/openpoke/blob/main/server/services/gmail/mock.py)<br>• [server/utils/time_windows.py](https://github.com/JustHarsh/openpoke/blob/main/server/utils/time_windows.py) (new)<br>• [tests/test_time_windows.py](https://github.com/JustHarsh/openpoke/blob/main/tests/test_time_windows.py) (new) | Resolve time ranges in code to exact Gmail filters; broad requests default to the last 4 hours |
| bf01cb9 | • [.env.example](https://github.com/JustHarsh/openpoke/blob/main/.env.example)<br>• [server/agents/execution_agent/tools/email_filter.py](https://github.com/JustHarsh/openpoke/blob/main/server/agents/execution_agent/tools/email_filter.py) (new)<br>• [server/agents/execution_agent/tools/registry.py](https://github.com/JustHarsh/openpoke/blob/main/server/agents/execution_agent/tools/registry.py)<br>• [server/agents/execution_agent/tools/task_state.py](https://github.com/JustHarsh/openpoke/blob/main/server/agents/execution_agent/tools/task_state.py)<br>• [server/config.py](https://github.com/JustHarsh/openpoke/blob/main/server/config.py)<br>• [tests/test_email_filter.py](https://github.com/JustHarsh/openpoke/blob/main/tests/test_email_filter.py) (new) | filter_emails: one cheap model call picks emails by meaning (redesign only) |
| 5ddd124 | • [server/services/gmail/mock.py](https://github.com/JustHarsh/openpoke/blob/main/server/services/gmail/mock.py)<br>• [tests/test_time_windows.py](https://github.com/JustHarsh/openpoke/blob/main/tests/test_time_windows.py) | Mock inbox delivers email bodies; Frank email made clearly job-related (earlier results were void without bodies) |

## 7. Experiments: scoring, scenarios, budget guard

| Commit | Files | Reason |
| --- | --- | --- |
| 2db0053 | • [server/experiments/report.py](https://github.com/JustHarsh/openpoke/blob/main/server/experiments/report.py)<br>• [server/experiments/run_scenario.py](https://github.com/JustHarsh/openpoke/blob/main/server/experiments/run_scenario.py)<br>• [server/experiments/scenarios.json](https://github.com/JustHarsh/openpoke/blob/main/server/experiments/scenarios.json)<br>• [server/experiments/seed.py](https://github.com/JustHarsh/openpoke/blob/main/server/experiments/seed.py)<br>• [tests/test_report_outcome.py](https://github.com/JustHarsh/openpoke/blob/main/tests/test_report_outcome.py) (new)<br>• [tests/test_seed.py](https://github.com/JustHarsh/openpoke/blob/main/tests/test_seed.py) | Seed matching tasks, add unambiguous probes, score outcomes |
| c14090a | • [server/experiments/report.py](https://github.com/JustHarsh/openpoke/blob/main/server/experiments/report.py)<br>• [server/experiments/run_scenario.py](https://github.com/JustHarsh/openpoke/blob/main/server/experiments/run_scenario.py)<br>• [server/experiments/scenarios.json](https://github.com/JustHarsh/openpoke/blob/main/server/experiments/scenarios.json)<br>• [tests/test_report_outcome.py](https://github.com/JustHarsh/openpoke/blob/main/tests/test_report_outcome.py) | Email-query scenarios with content checks |
| 5edca76 | [server/experiments/scenarios.json](https://github.com/JustHarsh/openpoke/blob/main/server/experiments/scenarios.json) | Grade the job filter by sender, not subject wording |
| fa2f8cb | [server/experiments/run.py](https://github.com/JustHarsh/openpoke/blob/main/server/experiments/run.py) | --max-cost spending cap, cost per run, even job order |
| 89260c0 | • [server/experiments/report.py](https://github.com/JustHarsh/openpoke/blob/main/server/experiments/report.py)<br>• [server/experiments/scenarios.json](https://github.com/JustHarsh/openpoke/blob/main/server/experiments/scenarios.json) | Grade continuity probes by content; count new tasks for the redesign |
| dbd011e | • [server/experiments/run.py](https://github.com/JustHarsh/openpoke/blob/main/server/experiments/run.py)<br>• [tests/test_report_outcome.py](https://github.com/JustHarsh/openpoke/blob/main/tests/test_report_outcome.py) | Stop the sweep when the account is out of credits (402) |

## 8. Docs

| Commit | Files | Reason |
| --- | --- | --- |
| 407ae6a | [docs/specs/agent-overload-design.md](https://github.com/JustHarsh/openpoke/blob/main/docs/specs/agent-overload-design.md) (new) | First design doc |
| 82b3807 | [docs/specs/agent-overload-design.md](https://github.com/JustHarsh/openpoke/blob/main/docs/specs/agent-overload-design.md) | 4h default window, meaning-based email filter, parity goal, reminders out of scope |
| dc63492 | • [README.md](https://github.com/JustHarsh/openpoke/blob/main/README.md)<br>• [docs/writeup.md](https://github.com/JustHarsh/openpoke/blob/main/docs/writeup.md) (new) | Writeup draft and a README section on tests and experiments |
| 7e8d08f | [docs/writeup.md](https://github.com/JustHarsh/openpoke/blob/main/docs/writeup.md) | Record the stage 2 repeat check and what the credit limit cost |
| 6732d7a | [docs/writeup.md](https://github.com/JustHarsh/openpoke/blob/main/docs/writeup.md) | Summary, analysis, final limits |
| 44bc24a | [docs/writeup.md](https://github.com/JustHarsh/openpoke/blob/main/docs/writeup.md) | Note the deprecated Composio call among the gaps fixed |
| a8a66ad | • [docs/specs/agent-overload-design.md](https://github.com/JustHarsh/openpoke/blob/main/docs/specs/agent-overload-design.md)<br>• [docs/writeup.md](https://github.com/JustHarsh/openpoke/blob/main/docs/writeup.md) | Describe the time-range gap accurately |
| 8a22cff | [README.md](https://github.com/JustHarsh/openpoke/blob/main/README.md) | Describe the approach at a high level |
| caac953 | • [docs/specs/agent-overload-design.md](https://github.com/JustHarsh/openpoke/blob/main/docs/specs/agent-overload-design.md)<br>• [docs/writeup.md](https://github.com/JustHarsh/openpoke/blob/main/docs/writeup.md) | Cut down to highlights |
| d1aa2d1 | • [docs/specs/agent-overload-design.md](https://github.com/JustHarsh/openpoke/blob/main/docs/specs/agent-overload-design.md)<br>• [docs/writeup.md](https://github.com/JustHarsh/openpoke/blob/main/docs/writeup.md) | Drop the trust, next-steps, risks and out-of-scope sections |

## Where each idea lives

| Idea | File |
| --- | --- |
| Task rows and schema | [server/services/tasks/store.py](https://github.com/JustHarsh/openpoke/blob/main/server/services/tasks/store.py) |
| Status rules | [server/services/tasks/transitions.py](https://github.com/JustHarsh/openpoke/blob/main/server/services/tasks/transitions.py) |
| Approval gate | [server/services/tasks/approval.py](https://github.com/JustHarsh/openpoke/blob/main/server/services/tasks/approval.py) |
| Task matcher (`find_tasks`) | [server/services/tasks/llm_retrieval.py](https://github.com/JustHarsh/openpoke/blob/main/server/services/tasks/llm_retrieval.py) |
| Interaction tools | [server/agents/interaction_agent/tools.py](https://github.com/JustHarsh/openpoke/blob/main/server/agents/interaction_agent/tools.py) |
| Interaction prompt | [server/agents/interaction_agent/system_prompt_tasks.md](https://github.com/JustHarsh/openpoke/blob/main/server/agents/interaction_agent/system_prompt_tasks.md) |
| Worker task mode | [server/agents/execution_agent/runtime.py](https://github.com/JustHarsh/openpoke/blob/main/server/agents/execution_agent/runtime.py) |
| Worker task tools | [server/agents/execution_agent/tools/task_state.py](https://github.com/JustHarsh/openpoke/blob/main/server/agents/execution_agent/tools/task_state.py) |
| Time ranges | [server/utils/time_windows.py](https://github.com/JustHarsh/openpoke/blob/main/server/utils/time_windows.py) |
| Email filter by meaning | [server/agents/execution_agent/tools/email_filter.py](https://github.com/JustHarsh/openpoke/blob/main/server/agents/execution_agent/tools/email_filter.py) |
| Experiments harness | [server/experiments/](https://github.com/JustHarsh/openpoke/tree/main/server/experiments/) |
| Usage log | [server/openrouter_client/usage.py](https://github.com/JustHarsh/openpoke/blob/main/server/openrouter_client/usage.py) |

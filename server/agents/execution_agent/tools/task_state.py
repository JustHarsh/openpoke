"""Task-record tools for ephemeral subagents (redesign variant), plus the approval-gated send tools."""

import json
from typing import Any, Callable, Dict, List, Optional

from ....utils.time_windows import render_time_context
from ....services.tasks.approval import check_can_send, enter_pending_approval, mark_sent
from ....services.tasks.store import Task, TaskStore
from ....services.tasks.transitions import ALLOWED, advance

SEND_TOOLS = ("gmail_execute_draft", "gmail_forward_email", "gmail_reply_to_thread")

TASK_RULES = """# Working on a stored task
You are a short-lived worker. Everything that persists about this work lives in the task record below, not in you.
- Keep the record current with `update_task` (summary of what was done, entities such as people involved, thread_id, data with anything a later follow-up needs: draft text, message ids, the window searched).
- When you have prepared a draft for the user to review, call `set_task_status` with `pending_approval`, report the exact draft, and stop. Do not send in the same run.
- Send tools are blocked by the system until the user has replied since the draft was shown. If a send is refused, report that and stop.
- After a send succeeds the system marks the task `sent` itself; do not set it.
- To find emails by meaning within a time range (job-related, about a trip, urgent, or a summary of recent mail) use `filter_emails`: it is much cheaper than `task_email_search`, which is for finding a specific known email."""


# Render the task record as context for the subagent's system prompt
def render_task_context(task: Task) -> str:
    record = {
        "id": task.id, "kind": task.kind, "status": task.status, "entities": task.entities,
        "thread_id": task.thread_id, "summary": task.summary, "data": task.data,
    }
    allowed = sorted(ALLOWED[task.kind].get(task.status, set()))
    return f"{TASK_RULES}\n\n## Time\n{render_time_context()}\n\n## Task record\n{json.dumps(record, indent=2, default=str)}\nStatuses you may move to: {allowed}"


def get_schemas() -> List[Dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": "update_task",
                "description": "Update the stored task record. Only the fields you pass are changed; data is merged.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "summary": {"type": "string", "description": "One or two sentences on what this task is and its current state."},
                        "entities": {"type": "array", "items": {"type": "string"}, "description": "People or organizations involved."},
                        "thread_id": {"type": "string"},
                        "data": {"type": "object", "description": "Anything needed for follow-ups, merged into existing data."},
                    },
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "set_task_status",
                "description": "Move the task to a new status (checked against the allowed transitions). 'sent' cannot be set by you.",
                "parameters": {
                    "type": "object",
                    "properties": {"status": {"type": "string"}},
                    "required": ["status"],
                    "additionalProperties": False,
                },
            },
        },
    ]


# Add the record tools and gate the send tools for one task
def build_registry(store: TaskStore, task_id: int, base: Dict[str, Callable[..., Any]]) -> Dict[str, Callable[..., Any]]:
    registry = dict(base)

    def update_task(
        summary: Optional[str] = None,
        entities: Optional[List[str]] = None,
        thread_id: Optional[str] = None,
        data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        merged = {**store.get(task_id).data, **data} if data is not None else None
        task = store.update_fields(task_id, summary=summary, entities=entities, thread_id=thread_id, data=merged)
        return {"id": task.id, "status": task.status, "summary": task.summary}

    def set_task_status(status: str) -> Dict[str, Any]:
        if status == "sent":
            raise PermissionError("'sent' is set by the system after a confirmed send")
        task = enter_pending_approval(store, task_id) if status == "pending_approval" else advance(store, task_id, status)
        return {"id": task.id, "status": task.status}

    def gated(send: Callable[..., Any]) -> Callable[..., Any]:
        def wrapper(**kwargs: Any) -> Any:
            allowed, reason = check_can_send(store.get(task_id))
            if not allowed:
                raise PermissionError(reason)
            result = send(**kwargs)  # if the provider call raises, the task stays pending_approval
            mark_sent(store, task_id)
            return result

        return wrapper

    registry["update_task"] = update_task
    registry["set_task_status"] = set_task_status
    for name in SEND_TOOLS:
        if name in registry:
            registry[name] = gated(registry[name])
    return registry

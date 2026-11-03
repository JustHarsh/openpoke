"""Code-enforced approval gate: a send needs a user message that arrived after the draft was prepared."""

from typing import Tuple

from ..conversation import get_conversation_log
from .store import Task, TaskStore
from .transitions import advance


def user_message_count() -> int:
    """Count the user messages in the conversation so far."""
    return sum(1 for tag, _, _ in get_conversation_log().iter_entries() if tag == "user_message")


def enter_pending_approval(store: TaskStore, task_id: int) -> Task:
    """Move a task to pending_approval and record the user-message baseline."""
    task = advance(store, task_id, "pending_approval")
    return store.update_fields(task_id, data={**task.data, "approval_baseline": user_message_count()})


def check_can_send(task: Task) -> Tuple[bool, str]:
    """Return (allowed, reason): a send needs pending_approval and a user reply since the draft."""
    if task.status != "pending_approval":
        return False, f"task is {task.status}; prepare the draft and ask the user for approval first"
    if user_message_count() <= task.data.get("approval_baseline", -1):
        return False, "the user has not replied since the draft was shown; ask for approval and stop"
    return True, ""


def mark_sent(store: TaskStore, task_id: int) -> Task:
    """Mark the task sent once the provider has confirmed the send."""
    return advance(store, task_id, "sent")

"""Code-enforced approval gate: a send needs a user message that arrived after the draft was prepared."""

from typing import Tuple

from ..conversation import get_conversation_log
from .store import Task, TaskStore
from .transitions import advance


# Number of user messages in the conversation so far
def user_message_count() -> int:
    return sum(1 for tag, _, _ in get_conversation_log().iter_entries() if tag == "user_message")


# Move a task to pending_approval and remember how many user messages existed at that point
def enter_pending_approval(store: TaskStore, task_id: int) -> Task:
    task = advance(store, task_id, "pending_approval")
    return store.update_fields(task_id, data={**task.data, "approval_baseline": user_message_count()})


# A send is allowed only from pending_approval, after the user has replied since the draft was prepared
def check_can_send(task: Task) -> Tuple[bool, str]:
    if task.status != "pending_approval":
        return False, f"task is {task.status}; prepare the draft and ask the user for approval first"
    if user_message_count() <= task.data.get("approval_baseline", -1):
        return False, "the user has not replied since the draft was shown; ask for approval and stop"
    return True, ""


# Record a confirmed send (call only after the email provider accepted it)
def mark_sent(store: TaskStore, task_id: int) -> Task:
    return advance(store, task_id, "sent")

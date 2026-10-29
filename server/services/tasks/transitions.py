"""Task lifecycle rules. Status changes only happen through `advance`, so approval cannot be skipped."""

KINDS = ("email_thread", "email_lookup", "other")

# Status a new task of each kind starts in.
INITIAL = {"email_thread": "drafting", "email_lookup": "done", "other": "open"}

# kind -> {from_status: {allowed next statuses}}. The keys of the inner dict are the valid statuses.
# email_thread: only pending_approval leads to sent, so a send cannot skip approval.
# A failed send leaves the task in pending_approval; the error is stored in task.data.
ALLOWED: dict = {
    "email_thread": {
        "drafting": {"pending_approval"},
        "pending_approval": {"sent", "drafting", "closed"},
        "sent": {"replied", "closed"},
        "replied": {"drafting", "closed"},
        "closed": {"replied"},
    },
    "email_lookup": {"done": set()},
    "other": {"open": {"closed"}, "closed": {"open"}},
}


class InvalidTransition(ValueError):
    """Raised when a status change is not allowed for the task's kind."""


def advance(store, task_id: int, new_status: str):
    """Move a task to new_status if ALLOWED permits it; return the updated Task.

    Use store.set_status(task_id, new_status) to write once the check passes.
    """
    task = store.get(task_id)
    if task is None:
        raise KeyError(task_id)
    if new_status not in ALLOWED[task.kind].get(task.status, set()):
        raise InvalidTransition(f"{task.kind}: {task.status} -> {new_status}")
    return store.set_status(task_id, new_status)

"""Task lifecycle rules. Status changes only happen through `advance`, so approval cannot be skipped.

TODO(Harsh): fill ALLOWED and implement `advance`; tests go in tests/test_transitions.py.
"""

KINDS = ("email_thread", "email_lookup", "other")

# Status a new task of each kind starts in.
INITIAL = {"email_thread": "drafting", "email_lookup": "done", "other": "open"}

# kind -> {from_status: {allowed next statuses}}. email_thread per the design doc:
# drafting, pending_approval, sent, awaiting_reply, replied, closed. Sending must be
# reachable only from pending_approval.
ALLOWED: dict = {}


class InvalidTransition(ValueError):
    """Raised when a status change is not allowed for the task's kind."""


def advance(store, task_id: int, new_status: str):
    """Move a task to new_status if ALLOWED permits it; return the updated Task.

    Use store.set_status(task_id, new_status) to write once the check passes.
    """
    raise NotImplementedError

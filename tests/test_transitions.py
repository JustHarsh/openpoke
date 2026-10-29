import itertools

import pytest

from server.services.tasks.store import TaskStore
from server.services.tasks.transitions import ALLOWED, INITIAL, KINDS, InvalidTransition, advance


@pytest.fixture
def store(tmp_path):
    return TaskStore(tmp_path / "tasks.db")


def _task_in(store, kind, status):
    """A task of `kind` forced into `status` (raw write, bypassing the rules under test)."""
    task = store.create(kind)
    return store.set_status(task.id, status)


ALL_PAIRS = [
    (kind, src, dst, dst in ALLOWED[kind][src])
    for kind in KINDS
    for src, dst in itertools.product(ALLOWED[kind], ALLOWED[kind])
]


@pytest.mark.parametrize("kind,src,dst,allowed", ALL_PAIRS)
def test_only_pairs_in_the_table_are_accepted(store, kind, src, dst, allowed):
    task = _task_in(store, kind, src)
    if allowed:
        assert advance(store, task.id, dst).status == dst
    else:
        with pytest.raises(InvalidTransition):
            advance(store, task.id, dst)
        assert store.get(task.id).status == src  # a rejected move changes nothing


def test_sent_is_only_reachable_from_pending_approval():
    sources = [src for src, nexts in ALLOWED["email_thread"].items() if "sent" in nexts]
    assert sources == ["pending_approval"]


def test_sent_is_unreachable_without_going_through_pending_approval():
    graph = {src: nexts - {"pending_approval"} for src, nexts in ALLOWED["email_thread"].items()}
    reachable, frontier = {INITIAL["email_thread"]}, [INITIAL["email_thread"]]
    while frontier:
        for nxt in graph[frontier.pop()]:
            if nxt not in reachable and nxt in graph:
                reachable.add(nxt)
                frontier.append(nxt)
    assert "sent" not in reachable


def test_drafting_cannot_jump_to_sent(store):
    task = store.create("email_thread")
    with pytest.raises(InvalidTransition):
        advance(store, task.id, "sent")
    assert store.get(task.id).status == "drafting"


def test_happy_path_and_follow_up_loop(store):
    task = store.create("email_thread")
    for status in ["pending_approval", "sent", "replied", "drafting", "pending_approval", "sent", "closed", "replied"]:
        assert advance(store, task.id, status).status == status


def test_unknown_status_is_rejected(store):
    task = store.create("email_thread")
    with pytest.raises(InvalidTransition):
        advance(store, task.id, "sentt")


def test_missing_task_raises_key_error(store):
    with pytest.raises(KeyError):
        advance(store, 999, "sent")


def test_lookup_tasks_have_no_moves(store):
    task = store.create("email_lookup")
    with pytest.raises(InvalidTransition):
        advance(store, task.id, "closed")


@pytest.mark.parametrize("kind", KINDS)
def test_table_is_consistent(kind):
    states = set(ALLOWED[kind])
    assert INITIAL[kind] in states
    assert all(nexts <= states for nexts in ALLOWED[kind].values())  # no move targets an undefined status

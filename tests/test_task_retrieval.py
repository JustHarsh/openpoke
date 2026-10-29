import pytest

from server.services.tasks.retrieval import find_tasks
from server.services.tasks.store import TaskStore

_FIRST = ["Maya", "Liam", "Noah", "Sofia", "Chen", "Omar", "Elena", "Raj", "Ana", "Tom"]
_LAST = ["Wong", "Shah", "Martin", "Kim", "Costa", "Novak", "Rossi", "Silva", "Odom", "Nair"]


@pytest.fixture
def store(tmp_path):
    s = TaskStore(tmp_path / "tasks.db")
    for f in _FIRST:  # 100 distractors with distinct people
        for l in _LAST:
            s.create("email_thread", summary=f"Email to {f} {l} about the schedule", entities=[f"{f} {l}"])
    return s


def test_finds_right_task_among_many(store):
    target = store.create("email_thread", summary="Lunch with Priya on Thursday", entities=["Priya"], thread_id="t9")
    results = find_tasks(store, "Did Priya reply yet?")
    assert results[0][0].id == target.id


def test_returns_all_tied_candidates_when_ambiguous(store):
    a = store.create("email_thread", entities=["Priya Nair"], summary="Thursday availability")
    b = store.create("email_thread", entities=["Priya Wong"], summary="Visa renewal")
    top = find_tasks(store, "Did Priya reply?", limit=5)
    assert {t.id for t, s in top if s == top[0][1]} == {a.id, b.id}


def test_full_name_breaks_the_tie(store):
    store.create("email_thread", entities=["Priya Nair"])
    wong = store.create("email_thread", entities=["Priya Wong"])
    assert find_tasks(store, "Did Priya Wong reply?")[0][0].id == wong.id


def test_no_match_returns_empty(store):
    assert find_tasks(store, "tell me about quantum chromodynamics") == []


def test_content_free_query_returns_most_recent(store):
    latest = store.create("email_thread", entities=["Zed"])
    assert find_tasks(store, "send it", limit=3)[0][0].id == latest.id


def test_kind_filter_and_limit(store):
    store.create("email_lookup", entities=["Priya"], summary="Priya emails")
    store.create("email_thread", entities=["Priya"])
    assert all(t.kind == "email_lookup" for t, _ in find_tasks(store, "Priya", kind="email_lookup"))
    assert len(find_tasks(store, "schedule", limit=3)) == 3


@pytest.mark.parametrize("typo", ["Pryia", "Priyaa", "priya's", "PRIYA"])
def test_typos_still_find_the_task(store, typo):
    target = store.create("email_thread", entities=["Priya"], summary="Thursday availability")
    assert find_tasks(store, f"Did {typo} reply yet?")[0][0].id == target.id


def test_exact_match_outscores_typo_match(store):
    exact = store.create("email_thread", entities=["Alice"])
    typo = store.create("email_thread", entities=["Alise"])
    ranked = find_tasks(store, "Did Alice reply?")
    assert ranked[0][0].id == exact.id and ranked[0][1] > dict((t.id, s) for t, s in ranked)[typo.id]


def test_short_names_must_match_exactly(store):
    store.create("email_thread", entities=["Kai"])
    assert find_tasks(store, "Did Kay reply?") == []


def test_longer_different_name_is_not_a_typo(store):
    store.create("email_thread", entities=["Priyanka"])
    assert find_tasks(store, "Did Priya reply?") == []

import pytest

from server.services.tasks.store import TaskStore


@pytest.fixture
def store(tmp_path):
    return TaskStore(tmp_path / "tasks.db")


def test_create_starts_in_initial_status(store):
    task = store.create("email_thread", summary="Lunch with Alice", entities=["Alice"], thread_id="t1")
    assert (task.kind, task.status, task.entities, task.thread_id) == ("email_thread", "drafting", ["Alice"], "t1")


def test_unknown_kind_rejected(store):
    with pytest.raises(ValueError):
        store.create("calendar")


def test_json_fields_round_trip(store):
    task = store.create("email_lookup", data={"window": "4h", "ids": ["m1", "m2"]})
    assert store.get(task.id).data == {"window": "4h", "ids": ["m1", "m2"]}


def test_persists_across_instances(tmp_path):
    TaskStore(tmp_path / "t.db").create("other", summary="x")
    assert [t.summary for t in TaskStore(tmp_path / "t.db").list_tasks()] == ["x"]


def test_list_filters_and_newest_first(store):
    a = store.create("email_thread", summary="a")
    b = store.create("email_thread", summary="b")
    store.create("email_lookup", summary="c")
    assert [t.summary for t in store.list_tasks(kind="email_thread")] == ["b", "a"]
    store.set_status(a.id, "sent")
    assert [t.id for t in store.list_tasks(status="sent")] == [a.id]
    assert len(store.list_tasks(limit=2)) == 2
    assert b.id != a.id


def test_update_fields_leaves_status_alone(store):
    task = store.create("email_thread", summary="old")
    updated = store.update_fields(task.id, summary="new", entities=["Bob"])
    assert (updated.summary, updated.entities, updated.status) == ("new", ["Bob"], "drafting")


def test_get_missing_returns_none(store):
    assert store.get(999) is None

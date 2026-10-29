import json

from server.experiments.seed import PROBE_AGENTS, seed


def test_seed_is_deterministic_and_distinct(tmp_path):
    a = seed(tmp_path / "a", 200, seed_value=1)
    b = seed(tmp_path / "b", 200, seed_value=1)
    assert a == b
    assert len(a) == len(set(a)) == 200


def test_probe_targets_always_present(tmp_path):
    names = seed(tmp_path, 10)
    for name, _, _ in PROBE_AGENTS:
        assert name in names


def test_seed_writes_logs_and_roster(tmp_path):
    names = seed(tmp_path, 20)
    roster = json.loads((tmp_path / "execution_agents" / "roster.json").read_text())
    assert roster == names
    assert len(list((tmp_path / "execution_agents").glob("*"))) == 21  # 20 logs + roster.json


def test_seed_also_creates_matching_tasks(tmp_path):
    from server.services.tasks.store import TaskStore

    names = seed(tmp_path, 30)
    tasks = TaskStore(tmp_path / "tasks.db").list_tasks(limit=100)
    assert len(tasks) == 30
    alice = names.index("Email to Alice") + 1  # task id = roster position + 1
    task = TaskStore(tmp_path / "tasks.db").get(alice)
    assert task.entities == ["Alice"] and task.status == "sent" and "Chez Philippe" in task.summary

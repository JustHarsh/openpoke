"""SQLite task store: one row per unit of work, so agents need not persist."""

import json
import sqlite3
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from server.paths import DATA_DIR

from .transitions import INITIAL, KINDS

_SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    kind       TEXT NOT NULL,
    status     TEXT NOT NULL,
    entities   TEXT NOT NULL DEFAULT '[]',
    thread_id  TEXT,
    data       TEXT NOT NULL DEFAULT '{}',
    summary    TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL
)
"""


@dataclass
class Task:
    id: int
    kind: str
    status: str
    entities: List[str] = field(default_factory=list)
    thread_id: Optional[str] = None
    data: Dict[str, Any] = field(default_factory=dict)
    summary: str = ""
    updated_at: str = ""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _row_to_task(row: sqlite3.Row) -> Task:
    return Task(
        id=row["id"], kind=row["kind"], status=row["status"], entities=json.loads(row["entities"]),
        thread_id=row["thread_id"], data=json.loads(row["data"]), summary=row["summary"],
        updated_at=row["updated_at"],
    )


class TaskStore:
    """Thread-safe wrapper around a single SQLite file."""

    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._conn.execute(_SCHEMA)
            self._conn.commit()

    # Insert a task in its kind's initial status
    def create(
        self,
        kind: str,
        summary: str = "",
        entities: Optional[List[str]] = None,
        thread_id: Optional[str] = None,
        data: Optional[Dict[str, Any]] = None,
    ) -> Task:
        if kind not in KINDS:
            raise ValueError(f"kind must be one of {KINDS}, got {kind!r}")
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO tasks (kind, status, entities, thread_id, data, summary, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (kind, INITIAL[kind], json.dumps(entities or []), thread_id, json.dumps(data or {}), summary, _now()),
            )
            self._conn.commit()
            task_id = cur.lastrowid
        return self.get(task_id)

    def get(self, task_id: int) -> Optional[Task]:
        with self._lock:
            row = self._conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        return _row_to_task(row) if row else None

    # Newest first; optional filters
    def list_tasks(self, kind: Optional[str] = None, status: Optional[str] = None, limit: int = 100) -> List[Task]:
        clauses, params = [], []
        if kind:
            clauses.append("kind = ?")
            params.append(kind)
        if status:
            clauses.append("status = ?")
            params.append(status)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._lock:
            rows = self._conn.execute(
                f"SELECT * FROM tasks {where} ORDER BY updated_at DESC, id DESC LIMIT ?", (*params, limit)
            ).fetchall()
        return [_row_to_task(r) for r in rows]

    # Update content fields only; status changes go through transitions.advance
    def update_fields(
        self,
        task_id: int,
        summary: Optional[str] = None,
        entities: Optional[List[str]] = None,
        thread_id: Optional[str] = None,
        data: Optional[Dict[str, Any]] = None,
    ) -> Optional[Task]:
        sets, params = [], []
        for column, value, encode in (
            ("summary", summary, None), ("entities", entities, json.dumps),
            ("thread_id", thread_id, None), ("data", data, json.dumps),
        ):
            if value is not None:
                sets.append(f"{column} = ?")
                params.append(encode(value) if encode else value)
        if sets:
            with self._lock:
                self._conn.execute(
                    f"UPDATE tasks SET {', '.join(sets)}, updated_at = ? WHERE id = ?", (*params, _now(), task_id)
                )
                self._conn.commit()
        return self.get(task_id)

    # Raw status write: callers must go through transitions.advance
    def set_status(self, task_id: int, status: str) -> Optional[Task]:
        with self._lock:
            self._conn.execute("UPDATE tasks SET status = ?, updated_at = ? WHERE id = ?", (status, _now(), task_id))
            self._conn.commit()
        return self.get(task_id)


_store: Optional[TaskStore] = None


def get_task_store() -> TaskStore:
    """Process-wide store at DATA_DIR/tasks.db."""
    global _store
    if _store is None:
        _store = TaskStore(DATA_DIR / "tasks.db")
    return _store

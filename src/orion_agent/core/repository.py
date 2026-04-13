from __future__ import annotations

import sqlite3

from orion_agent.core.models import LongTermMemoryRecord, TaskRecord
from orion_agent.core.embedding_runtime import cosine_similarity


class TaskRepository:
    """SQLite-backed repository for task persistence."""

    def __init__(self, db_path: str | None = None) -> None:
        self.db_path = db_path or ":memory:"
        self._connection = sqlite3.connect(self.db_path, check_same_thread=False)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        return self._connection

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    status TEXT NOT NULL,
                    payload TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS long_term_memories (
                    id TEXT PRIMARY KEY,
                    scope TEXT NOT NULL,
                    topic TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    details TEXT NOT NULL,
                    embedding TEXT NOT NULL,
                    tags TEXT NOT NULL,
                    payload TEXT NOT NULL
                )
                """
            )

    def save(self, task: TaskRecord) -> TaskRecord:
        payload = task.model_dump_json()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO tasks (id, title, status, payload)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    title = excluded.title,
                    status = excluded.status,
                    payload = excluded.payload
                """,
                (task.id, task.title, task.status.value, payload),
            )
        return task

    def get(self, task_id: str) -> TaskRecord | None:
        with self._connect() as conn:
            row = conn.execute("SELECT payload FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if row is None:
            return None
        return TaskRecord.model_validate_json(row[0])

    def list(self, limit: int = 20) -> list[TaskRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT payload FROM tasks ORDER BY rowid DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [TaskRecord.model_validate_json(row[0]) for row in rows]

    def save_long_term_memory(self, record: LongTermMemoryRecord) -> LongTermMemoryRecord:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO long_term_memories (id, scope, topic, summary, details, embedding, tags, payload)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    scope = excluded.scope,
                    topic = excluded.topic,
                    summary = excluded.summary,
                    details = excluded.details,
                    embedding = excluded.embedding,
                    tags = excluded.tags,
                    payload = excluded.payload
                """,
                (
                    record.id,
                    record.scope,
                    record.topic,
                    record.summary,
                    record.details,
                    str(record.embedding),
                    ",".join(record.tags),
                    record.model_dump_json(),
                ),
            )
        return record

    def search_long_term_memories(self, query: str, scope: str, limit: int = 5) -> list[LongTermMemoryRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT payload
                FROM long_term_memories
                WHERE scope = ?
                ORDER BY rowid DESC
                LIMIT 200
                """,
                (scope,),
            ).fetchall()
        return [LongTermMemoryRecord.model_validate_json(row[0]) for row in rows[:limit]]

    def search_long_term_memories_by_vector(
        self,
        query_embedding: list[float],
        scope: str,
        limit: int = 5,
    ) -> list[LongTermMemoryRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT payload
                FROM long_term_memories
                WHERE scope = ?
                ORDER BY rowid DESC
                LIMIT 200
                """,
                (scope,),
            ).fetchall()
        records = [LongTermMemoryRecord.model_validate_json(row[0]) for row in rows]
        ranked = sorted(
            records,
            key=lambda item: cosine_similarity(query_embedding, item.embedding),
            reverse=True,
        )
        return ranked[:limit]

    def get_long_term_memories_by_ids(self, memory_ids: list[str]) -> list[LongTermMemoryRecord]:
        if not memory_ids:
            return []
        placeholders = ",".join("?" for _ in memory_ids)
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT payload FROM long_term_memories WHERE id IN ({placeholders})",
                tuple(memory_ids),
            ).fetchall()
        records = [LongTermMemoryRecord.model_validate_json(row[0]) for row in rows]
        order = {memory_id: index for index, memory_id in enumerate(memory_ids)}
        return sorted(records, key=lambda item: order.get(item.id, len(order)))

    def count_tasks(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()
        return int(row[0] if row else 0)

    def count_long_term_memories(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) FROM long_term_memories").fetchone()
        return int(row[0] if row else 0)

    def close(self) -> None:
        self._connection.close()

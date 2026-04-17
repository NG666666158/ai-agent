from __future__ import annotations

import sqlite3
import threading

from orion_agent.core.embedding_runtime import cosine_similarity
from orion_agent.core.models import ChatMessage, ChatSession, LongTermMemoryRecord, TaskRecord, UserProfileFact, UserProfileFactStatus, utcnow


class TaskRepository:
    """SQLite-backed repository for task, session, and memory persistence."""

    def __init__(self, db_path: str | None = None) -> None:
        self.db_path = db_path or ":memory:"
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(self.db_path, check_same_thread=False)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        return self._connection

    def _init_db(self) -> None:
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS tasks (
                        id TEXT PRIMARY KEY,
                        title TEXT NOT NULL,
                        status TEXT NOT NULL,
                        session_id TEXT,
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
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS chat_sessions (
                        id TEXT PRIMARY KEY,
                        title TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        payload TEXT NOT NULL
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS chat_messages (
                        id TEXT PRIMARY KEY,
                        session_id TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        payload TEXT NOT NULL
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS user_profile_facts (
                        id TEXT PRIMARY KEY,
                        category TEXT NOT NULL,
                        value TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        payload TEXT NOT NULL
                    )
                    """
                )

    def save(self, task: TaskRecord) -> TaskRecord:
        task.updated_at = utcnow()
        payload = task.model_dump_json()
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO tasks (id, title, status, session_id, payload)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        title = excluded.title,
                        status = excluded.status,
                        session_id = excluded.session_id,
                        payload = excluded.payload
                    """,
                    (task.id, task.title, task.status.value, task.session_id, payload),
                )
        return task

    def get(self, task_id: str) -> TaskRecord | None:
        with self._lock:
            with self._connect() as conn:
                row = conn.execute("SELECT payload FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if row is None:
            return None
        return TaskRecord.model_validate_json(row[0])

    def list(self, limit: int = 20) -> list[TaskRecord]:
        with self._lock:
            with self._connect() as conn:
                rows = conn.execute(
                    "SELECT payload FROM tasks ORDER BY rowid DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        return [TaskRecord.model_validate_json(row[0]) for row in rows]

    def list_by_session(self, session_id: str, limit: int = 50) -> list[TaskRecord]:
        with self._lock:
            with self._connect() as conn:
                rows = conn.execute(
                    """
                    SELECT payload
                    FROM tasks
                    WHERE session_id = ?
                    ORDER BY rowid DESC
                    LIMIT ?
                    """,
                    (session_id, limit),
                ).fetchall()
        return [TaskRecord.model_validate_json(row[0]) for row in rows]

    def save_session(self, session: ChatSession) -> ChatSession:
        session.updated_at = utcnow()
        payload = session.model_dump_json()
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO chat_sessions (id, title, updated_at, payload)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        title = excluded.title,
                        updated_at = excluded.updated_at,
                        payload = excluded.payload
                    """,
                    (session.id, session.title, session.updated_at.isoformat(), payload),
                )
        return session

    def get_session(self, session_id: str) -> ChatSession | None:
        with self._lock:
            with self._connect() as conn:
                row = conn.execute("SELECT payload FROM chat_sessions WHERE id = ?", (session_id,)).fetchone()
        if row is None:
            return None
        return ChatSession.model_validate_json(row[0])

    def list_sessions(self, limit: int = 30) -> list[ChatSession]:
        with self._lock:
            with self._connect() as conn:
                rows = conn.execute(
                    """
                    SELECT payload
                    FROM chat_sessions
                    ORDER BY updated_at DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
        return [ChatSession.model_validate_json(row[0]) for row in rows]

    def list_sessions_by_source(self, source_session_id: str, limit: int = 30) -> list[ChatSession]:
        with self._lock:
            with self._connect() as conn:
                rows = conn.execute(
                    "SELECT payload FROM chat_sessions ORDER BY updated_at DESC LIMIT ?",
                    (limit * 3,),
                ).fetchall()
        sessions = [ChatSession.model_validate_json(row[0]) for row in rows]
        return [item for item in sessions if item.source_session_id == source_session_id][:limit]

    def save_session_message(self, message: ChatMessage) -> ChatMessage:
        payload = message.model_dump_json()
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO chat_messages (id, session_id, created_at, payload)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        session_id = excluded.session_id,
                        created_at = excluded.created_at,
                        payload = excluded.payload
                    """,
                    (message.id, message.session_id, message.created_at.isoformat(), payload),
                )
        return message

    def save_user_profile_fact(self, fact: UserProfileFact) -> UserProfileFact:
        fact.updated_at = utcnow()
        payload = fact.model_dump_json()
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO user_profile_facts (id, category, value, updated_at, payload)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        category = excluded.category,
                        value = excluded.value,
                        updated_at = excluded.updated_at,
                        payload = excluded.payload
                    """,
                    (fact.id, fact.category, fact.value, fact.updated_at.isoformat(), payload),
                )
        return fact

    def get_user_profile_fact(self, fact_id: str) -> UserProfileFact | None:
        with self._lock:
            with self._connect() as conn:
                row = conn.execute("SELECT payload FROM user_profile_facts WHERE id = ?", (fact_id,)).fetchone()
        if row is None:
            return None
        return UserProfileFact.model_validate_json(row[0])

    def find_user_profile_fact(self, category: str, value: str) -> UserProfileFact | None:
        with self._lock:
            with self._connect() as conn:
                row = conn.execute(
                    """
                    SELECT payload
                    FROM user_profile_facts
                    WHERE category = ? AND value = ?
                    ORDER BY updated_at DESC
                    LIMIT 1
                    """,
                    (category, value),
                ).fetchone()
        if row is None:
            return None
        return UserProfileFact.model_validate_json(row[0])

    def list_user_profile_facts(self, limit: int = 50, *, include_inactive: bool = False) -> list[UserProfileFact]:
        with self._lock:
            with self._connect() as conn:
                rows = conn.execute(
                    """
                    SELECT payload
                    FROM user_profile_facts
                    ORDER BY updated_at DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
        facts = [UserProfileFact.model_validate_json(row[0]) for row in rows]
        if not include_inactive:
            facts = [fact for fact in facts if fact.status == UserProfileFactStatus.ACTIVE]
        return facts

    def list_user_profile_facts_by_category(
        self,
        category: str,
        *,
        include_inactive: bool = True,
        limit: int = 50,
    ) -> list[UserProfileFact]:
        with self._lock:
            with self._connect() as conn:
                rows = conn.execute(
                    """
                    SELECT payload
                    FROM user_profile_facts
                    WHERE category = ?
                    ORDER BY updated_at DESC
                    LIMIT ?
                    """,
                    (category, limit),
                ).fetchall()
        facts = [UserProfileFact.model_validate_json(row[0]) for row in rows]
        if not include_inactive:
            facts = [fact for fact in facts if fact.status == UserProfileFactStatus.ACTIVE]
        return facts

    def list_session_messages(self, session_id: str, limit: int = 100) -> list[ChatMessage]:
        with self._lock:
            with self._connect() as conn:
                rows = conn.execute(
                    """
                    SELECT payload
                    FROM chat_messages
                    WHERE session_id = ?
                    ORDER BY created_at ASC
                    LIMIT ?
                    """,
                    (session_id, limit),
                ).fetchall()
        return [ChatMessage.model_validate_json(row[0]) for row in rows]

    def save_long_term_memory(self, record: LongTermMemoryRecord) -> LongTermMemoryRecord:
        with self._lock:
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

    def update_long_term_memory(
        self,
        memory_id: str,
        *,
        scope: str | None = None,
        topic: str | None = None,
        summary: str | None = None,
        details: str | None = None,
        tags: list[str] | None = None,
        embedding: list[float] | None = None,
    ) -> LongTermMemoryRecord | None:
        record = self.get_long_term_memory(memory_id)
        if record is None:
            return None
        if scope is not None:
            record.scope = scope
        if topic is not None:
            record.topic = topic
        if summary is not None:
            record.summary = summary
        if details is not None:
            record.details = details
        if tags is not None:
            record.tags = tags
        if embedding is not None:
            record.embedding = embedding
        return self.save_long_term_memory(record)

    def get_long_term_memory(self, memory_id: str) -> LongTermMemoryRecord | None:
        with self._lock:
            with self._connect() as conn:
                row = conn.execute("SELECT payload FROM long_term_memories WHERE id = ?", (memory_id,)).fetchone()
        if row is None:
            return None
        return LongTermMemoryRecord.model_validate_json(row[0])

    def list_long_term_memories(
        self,
        *,
        scope: str | None = None,
        query: str | None = None,
        limit: int = 50,
    ) -> list[LongTermMemoryRecord]:
        sql = "SELECT payload FROM long_term_memories"
        clauses: list[str] = []
        params: list[object] = []
        if scope:
            clauses.append("scope = ?")
            params.append(scope)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY rowid DESC LIMIT ?"
        params.append(limit)

        with self._lock:
            with self._connect() as conn:
                rows = conn.execute(sql, tuple(params)).fetchall()
        records = [LongTermMemoryRecord.model_validate_json(row[0]) for row in rows]
        records = [item for item in records if not item.deleted]
        if query:
            normalized = query.lower()
            records = [
                item
                for item in records
                if normalized in item.topic.lower()
                or normalized in item.summary.lower()
                or normalized in item.details.lower()
                or any(normalized in tag.lower() for tag in item.tags)
            ]
        return records[:limit]

    def delete_long_term_memory(self, memory_id: str) -> bool:
        record = self.get_long_term_memory(memory_id)
        if record is None:
            return False
        record.deleted = True
        record.deleted_at = utcnow()
        self.save_long_term_memory(record)
        return True

    def search_long_term_memories(self, query: str, scope: str, limit: int = 5) -> list[LongTermMemoryRecord]:
        return self.list_long_term_memories(scope=scope, query=query, limit=limit)

    def search_long_term_memories_by_vector(
        self,
        query_embedding: list[float],
        scope: str,
        limit: int = 5,
    ) -> list[LongTermMemoryRecord]:
        with self._lock:
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
        ranked = sorted(records, key=lambda item: cosine_similarity(query_embedding, item.embedding), reverse=True)
        return ranked[:limit]

    def get_long_term_memories_by_ids(self, memory_ids: list[str]) -> list[LongTermMemoryRecord]:
        if not memory_ids:
            return []
        placeholders = ",".join("?" for _ in memory_ids)
        with self._lock:
            with self._connect() as conn:
                rows = conn.execute(
                    f"SELECT payload FROM long_term_memories WHERE id IN ({placeholders})",
                    tuple(memory_ids),
                ).fetchall()
        records = [LongTermMemoryRecord.model_validate_json(row[0]) for row in rows]
        order = {memory_id: index for index, memory_id in enumerate(memory_ids)}
        return sorted(records, key=lambda item: order.get(item.id, len(order)))

    def count_tasks(self) -> int:
        with self._lock:
            with self._connect() as conn:
                row = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()
        return int(row[0] if row else 0)

    def count_long_term_memories(self) -> int:
        with self._lock:
            with self._connect() as conn:
                row = conn.execute("SELECT COUNT(*) FROM long_term_memories").fetchone()
        return int(row[0] if row else 0)

    def count_sessions(self) -> int:
        with self._lock:
            with self._connect() as conn:
                row = conn.execute("SELECT COUNT(*) FROM chat_sessions").fetchone()
        return int(row[0] if row else 0)

    def close(self) -> None:
        with self._lock:
            self._connection.close()

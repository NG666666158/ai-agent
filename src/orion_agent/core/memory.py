from __future__ import annotations

from orion_agent.core.embedding_runtime import BaseEmbedder
from orion_agent.core.models import LongTermMemoryRecord, MemoryEntry, TaskRecord
from orion_agent.core.repository import TaskRepository
from orion_agent.core.vector_store import BaseVectorStore


class TaskMemoryManager:
    """Short-term task memory stored alongside the task."""

    def write(self, task: TaskRecord, kind: str, content: str) -> TaskRecord:
        task.memory.append(MemoryEntry(kind=kind, content=content))
        return task

    def search(self, task: TaskRecord, query: str, limit: int = 5) -> list[MemoryEntry]:
        normalized = query.lower()
        matches = [entry for entry in task.memory if normalized in entry.content.lower()]
        return matches[:limit]


class LongTermMemoryManager:
    """Simple persisted memory layer backed by the repository."""

    def __init__(
        self,
        repository: TaskRepository,
        embedder: BaseEmbedder,
        vector_store: BaseVectorStore,
    ) -> None:
        self.repository = repository
        self.embedder = embedder
        self.vector_store = vector_store

    def recall(self, query: str, scope: str, limit: int = 5) -> list[LongTermMemoryRecord]:
        if not query.strip():
            return []
        query_embedding = self.embedder.embed(query)
        memory_ids = self.vector_store.search(query_embedding=query_embedding, scope=scope, limit=limit)
        return self.repository.get_long_term_memories_by_ids(memory_ids)

    def remember(self, record: LongTermMemoryRecord) -> LongTermMemoryRecord:
        if not record.embedding:
            record.embedding = self.embedder.embed(f"{record.topic}\n{record.summary}\n{record.details}")
        saved_record = self.repository.save_long_term_memory(record)
        self.vector_store.upsert(saved_record)
        return saved_record

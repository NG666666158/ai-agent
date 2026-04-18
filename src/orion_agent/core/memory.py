from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from orion_agent.core.embedding_runtime import BaseEmbedder
from orion_agent.core.embedding_runtime import cosine_similarity
from orion_agent.core.models import LongTermMemoryRecord, MemoryEntry, MemoryVersion, TaskRecord, utcnow
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

    MEMORY_TYPE_WEIGHTS = {
        "preference": 1.3,
        "fact": 1.15,
        "document_note": 1.1,
        "conversation_summary": 0.95,
        "task_result": 1.0,
    }

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
        candidate_limit = max(limit * 3, 8)
        candidates: dict[str, LongTermMemoryRecord] = {}
        channels: dict[str, set[str]] = defaultdict(set)

        memory_ids = self.vector_store.search(query_embedding=query_embedding, scope=scope, limit=candidate_limit)
        for record in self.repository.get_long_term_memories_by_ids(memory_ids):
            candidates[record.id] = record
            channels[record.id].add("vector_store")

        for record in self.repository.search_long_term_memories_by_vector(
            query_embedding=query_embedding,
            scope=scope,
            limit=candidate_limit,
        ):
            candidates.setdefault(record.id, record)
            channels[record.id].add("local_vector")

        for record in self.repository.search_long_term_memories(query=query, scope=scope, limit=candidate_limit):
            candidates.setdefault(record.id, record)
            channels[record.id].add("lexical")

        if not candidates:
            for record in self.repository.list_long_term_memories(scope=scope, limit=limit):
                cloned = record.model_copy(deep=True)
                cloned.retrieval_score = 0.05
                cloned.retrieval_reason = "fallback:recent_memory"
                cloned.retrieval_channels = ["recent_fallback"]
                candidates[record.id] = cloned
            results = list(candidates.values())[:limit]
            self._touch_access_metadata(results)
            return results

        reranked: list[tuple[float, datetime, LongTermMemoryRecord]] = []
        for record_id, record in candidates.items():
            reranked_record = record.model_copy(deep=True)
            score, reasons = self._score_candidate(
                query=query,
                query_embedding=query_embedding,
                record=reranked_record,
                channels=channels[record_id],
            )
            reranked_record.retrieval_score = round(score, 4)
            reranked_record.retrieval_reason = "; ".join(reasons)
            reranked_record.retrieval_channels = sorted(channels[record_id])
            reranked.append((score, reranked_record.created_at, reranked_record))

        reranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
        results = [item[2] for item in reranked[:limit]]
        self._touch_access_metadata(results)
        return results

    def _touch_access_metadata(self, records: list[LongTermMemoryRecord]) -> None:
        """Persist access counters without storing query-specific retrieval annotations."""
        now = utcnow()
        for record in records:
            persisted = self.repository.get_long_term_memory(record.id)
            base_record = persisted.model_copy(deep=True) if persisted is not None else record.model_copy(deep=True)
            base_record.last_accessed_at = now
            base_record.accessed_count += 1
            saved = self.repository.save_long_term_memory(base_record)
            record.last_accessed_at = saved.last_accessed_at
            record.accessed_count = saved.accessed_count

    def remember(self, record: LongTermMemoryRecord) -> LongTermMemoryRecord:
        if not record.embedding:
            record.embedding = self.embedder.embed(f"{record.topic}\n{record.summary}\n{record.details}")
        saved_record = self.repository.save_long_term_memory(record)
        self.vector_store.upsert(saved_record)
        return saved_record

    def update(
        self,
        memory_id: str,
        *,
        scope: str | None = None,
        topic: str | None = None,
        summary: str | None = None,
        details: str | None = None,
        tags: list[str] | None = None,
    ) -> LongTermMemoryRecord | None:
        existing = self.repository.get_long_term_memory(memory_id)
        if existing is None:
            return None
        existing.versions.append(
            MemoryVersion(
                version=len(existing.versions) + 1,
                topic=existing.topic,
                summary=existing.summary,
                details=existing.details,
                tags=list(existing.tags),
                updated_by="editor",
            )
        )
        if scope is not None:
            existing.scope = scope
        if topic is not None:
            existing.topic = topic
        if summary is not None:
            existing.summary = summary
        if details is not None:
            existing.details = details
        if tags is not None:
            existing.tags = tags
        existing.embedding = self.embedder.embed(f"{existing.topic}\n{existing.summary}\n{existing.details}")
        updated = self.repository.save_long_term_memory(existing)
        self.vector_store.upsert(updated)
        return updated

    def _score_candidate(
        self,
        *,
        query: str,
        query_embedding: list[float],
        record: LongTermMemoryRecord,
        channels: set[str],
    ) -> tuple[float, list[str]]:
        reasons: list[str] = []
        query_tokens = self._tokenize(query)
        memory_text = "\n".join([record.topic, record.summary, record.details, " ".join(record.tags)])
        memory_tokens = self._tokenize(memory_text)

        semantic_score = cosine_similarity(query_embedding, record.embedding)
        lexical_overlap = len(query_tokens & memory_tokens)
        lexical_score = min(lexical_overlap * 0.12, 0.42)
        type_weight = self._memory_type_weight(query=query, record=record)
        channel_bonus = 0.0

        if "vector_store" in channels:
            channel_bonus += 0.18
            reasons.append("vector_store_hit")
        if "local_vector" in channels:
            channel_bonus += 0.12
            reasons.append("local_vector_hit")
        if "lexical" in channels:
            channel_bonus += 0.14
            reasons.append("lexical_hit")
        if lexical_overlap:
            reasons.append(f"keyword_overlap={lexical_overlap}")
        if semantic_score > 0.35:
            reasons.append(f"semantic={semantic_score:.2f}")
        if type_weight > 1.0:
            reasons.append(f"type_boost={record.memory_type}")
        elif type_weight < 1.0:
            reasons.append(f"type_downweight={record.memory_type}")

        score = semantic_score + lexical_score + channel_bonus
        score *= type_weight
        return score, reasons or ["mixed_recall"]

    def _memory_type_weight(self, *, query: str, record: LongTermMemoryRecord) -> float:
        normalized = query.lower()
        weight = self.MEMORY_TYPE_WEIGHTS.get(record.memory_type, 1.0)
        if any(keyword in normalized for keyword in ["喜欢", "偏好", "最想学", "想学", "语言", "技术栈"]):
            if record.memory_type == "preference":
                weight += 0.25
            elif record.memory_type == "fact":
                weight += 0.08
        if any(keyword in normalized for keyword in ["文档", "资料", "文件", "总结", "摘要"]):
            if record.memory_type == "document_note":
                weight += 0.18
        if any(keyword in normalized for keyword in ["继续", "刚才", "上次", "前面", "历史"]):
            if record.memory_type == "conversation_summary":
                weight += 0.16
        return weight

    def _tokenize(self, text: str) -> set[str]:
        normalized = (
            text.lower()
            .replace("\n", " ")
            .replace(",", " ")
            .replace("，", " ")
            .replace("。", " ")
            .replace("：", " ")
            .replace(":", " ")
            .replace("(", " ")
            .replace(")", " ")
            .replace("/", " ")
        )
        tokens = {item.strip() for item in normalized.split() if len(item.strip()) >= 2}
        for chunk in normalized.split():
            if len(chunk) >= 4 and any("\u4e00" <= char <= "\u9fff" for char in chunk):
                for index in range(len(chunk) - 1):
                    tokens.add(chunk[index : index + 2])
        return tokens

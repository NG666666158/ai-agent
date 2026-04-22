from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Protocol

from orion_agent.core.embedding_runtime import BaseEmbedder
from orion_agent.core.embedding_runtime import cosine_similarity
from orion_agent.core.models import LongTermMemoryRecord, MemoryEntry, MemoryVersion, TaskRecord, utcnow
from orion_agent.core.repository import TaskRepository
from orion_agent.core.vector_store import BaseVectorStore


class BaseReranker(Protocol):
    """Abstraction for a dedicated rerank stage in the retrieval pipeline.

    Implementations may call external APIs (e.g. Cohere, OpenAI). When credentials
    or support are unavailable, fall back to the NullReranker which uses the
    existing heuristic scoring.
    """

    def rerank(self, query: str, candidates: list[LongTermMemoryRecord]) -> list[LongTermMemoryRecord]:
        """Reorder candidates by relevance and return the reranked list.

        The returned list must contain the same records as the input (possibly reordered),
        with retrieval_score and retrieval_reason updated accordingly.
        """
        ...


class NullReranker:
    """Fallback reranker that uses the existing heuristic scoring.

    Used when no dedicated rerank provider is configured or available.
    """

    def __init__(self, embedder: BaseEmbedder) -> None:
        self._embedder = embedder

    def rerank(self, query: str, candidates: list[LongTermMemoryRecord]) -> list[LongTermMemoryRecord]:
        if not candidates:
            return candidates
        query_embedding = self._embedder.embed(query)
        scored: list[tuple[float, datetime, LongTermMemoryRecord]] = []
        for record in candidates:
            scored_record = record.model_copy(deep=True)
            score, reasons = _heuristic_score(query, query_embedding, scored_record)
            scored_record.retrieval_score = round(score, 4)
            scored_record.retrieval_reason = "; ".join(reasons)
            scored.append((score, scored_record.created_at, scored_record))
        scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return [rec for _score, _created, rec in scored]


def _heuristic_score(
    query: str,
    query_embedding: list[float],
    record: LongTermMemoryRecord,
) -> tuple[float, list[str]]:
    """Compute heuristic relevance score for a memory record (fallback reranker logic).

    This is the original _score_candidate logic extracted from LongTermMemoryManager.
    """
    reasons: list[str] = []
    query_tokens = _tokenize(query)
    memory_text = "\n".join([record.topic, record.summary, record.details, " ".join(record.tags)])
    memory_tokens = _tokenize(memory_text)

    semantic_score = cosine_similarity(query_embedding, record.embedding)
    lexical_overlap = len(query_tokens & memory_tokens)
    lexical_score = min(lexical_overlap * 0.12, 0.42)
    type_weight = _memory_type_weight(query=query, record=record)

    if semantic_score > 0.35:
        reasons.append(f"semantic={semantic_score:.2f}")
    if lexical_overlap:
        reasons.append(f"keyword_overlap={lexical_overlap}")
    if type_weight > 1.0:
        reasons.append(f"type_boost={record.memory_type}")
    elif type_weight < 1.0:
        reasons.append(f"type_downweight={record.memory_type}")

    score = semantic_score + lexical_score
    score *= type_weight
    return score, reasons or ["mixed_recall"]


MEMORY_TYPE_WEIGHTS = {
    "preference": 1.3,
    "fact": 1.15,
    "document_note": 1.1,
    "conversation_summary": 0.95,
    "task_result": 1.0,
}


def _tokenize(text: str) -> set[str]:
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


def _memory_type_weight(*, query: str, record: LongTermMemoryRecord) -> float:
    normalized = query.lower()
    weight = MEMORY_TYPE_WEIGHTS.get(record.memory_type, 1.0)
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
    """Persisted memory layer with multi-channel recall and optional reranking."""

    def __init__(
        self,
        repository: TaskRepository,
        embedder: BaseEmbedder,
        vector_store: BaseVectorStore,
        reranker: BaseReranker | None = None,
    ) -> None:
        self.repository = repository
        self.embedder = embedder
        self.vector_store = vector_store
        self._reranker = reranker

    def recall(self, query: str, scope: str, limit: int = 5) -> list[LongTermMemoryRecord]:
        if not query.strip():
            return []
        query_embedding = self.embedder.embed(query)
        candidate_limit = max(limit * 3, 8)
        candidates: dict[str, LongTermMemoryRecord] = {}
        channels: dict[str, set[str]] = defaultdict(set)

        memory_ids = self.vector_store.search(query_embedding=query_embedding, scope=scope, limit=candidate_limit)
        for record in self.repository.get_long_term_memories_by_ids(memory_ids):
            if record.source.source_type == "manual_ingest_parent":
                continue
            candidates[record.id] = record
            channels[record.id].add("vector_store")

        for record in self.repository.search_long_term_memories_by_vector(
            query_embedding=query_embedding,
            scope=scope,
            limit=candidate_limit,
        ):
            if record.source.source_type == "manual_ingest_parent":
                continue
            candidates.setdefault(record.id, record)
            channels[record.id].add("local_vector")

        for record in self.repository.search_long_term_memories(query=query, scope=scope, limit=candidate_limit):
            if record.source.source_type == "manual_ingest_parent":
                continue
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
            score, reasons = _heuristic_score(
                query=query,
                query_embedding=query_embedding,
                record=reranked_record,
            )
            reranked_record.retrieval_score = round(score, 4)
            reranked_record.retrieval_reason = "; ".join(reasons)
            reranked_record.retrieval_channels = sorted(channels[record_id])
            reranked.append((score, reranked_record.created_at, reranked_record))

        reranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
        results: list[LongTermMemoryRecord] = []
        seen_ids: set[str] = set()
        for _score, _created_at, record in reranked:
            promoted = self._promote_parent_record(record)
            if promoted.id in seen_ids:
                continue
            seen_ids.add(promoted.id)
            results.append(promoted)
            if len(results) >= limit:
                break

        # US-R22: apply dedicated rerank stage if configured
        if self._reranker is not None and len(results) > 1:
            results = self._reranker.rerank(query, results)

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

    def _promote_parent_record(self, record: LongTermMemoryRecord) -> LongTermMemoryRecord:
        if not record.parent_id or record.source.source_type != "manual_ingest_chunk":
            return record
        parent = self.repository.get_long_term_memory(record.parent_id)
        if parent is None:
            return record
        promoted = parent.model_copy(deep=True)
        promoted.retrieval_score = record.retrieval_score
        promoted.retrieval_reason = "; ".join(
            item for item in [record.retrieval_reason, "parent_doc_promoted"] if item
        )
        promoted.retrieval_channels = sorted(set([*record.retrieval_channels, "parent_doc"]))
        return promoted

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

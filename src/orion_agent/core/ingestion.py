from __future__ import annotations

import re
from dataclasses import dataclass
from uuid import uuid4

from orion_agent.core.embedding_runtime import BaseEmbedder
from orion_agent.core.memory import LongTermMemoryManager
from orion_agent.core.models import (
    ChunkPreview,
    IngestionCommitRequest,
    IngestionCommitResponse,
    IngestionPreviewRequest,
    IngestionPreviewResponse,
    IngestionStrategy,
    LongTermMemoryRecord,
    MemorySource,
)
from orion_agent.core.repository import TaskRepository


@dataclass
class ChunkCandidate:
    chunk_id: str
    parent_id: str | None
    chunk_index: int
    text: str


class DocumentIngestionService:
    def __init__(
        self,
        *,
        repository: TaskRepository,
        embedder: BaseEmbedder,
        memory_manager: LongTermMemoryManager,
    ) -> None:
        self.repository = repository
        self.embedder = embedder
        self.memory_manager = memory_manager

    def preview(self, request: IngestionPreviewRequest) -> IngestionPreviewResponse:
        document_id = f"doc_{uuid4().hex[:8]}"
        title = self._resolve_title(request.title, request.text)
        normalized = self._normalize_text(request.text)
        chunks, parent_count = self._chunk_document(document_id=document_id, text=normalized, request=request)
        previews = [self._build_chunk_preview(candidate) for candidate in chunks]
        return IngestionPreviewResponse(
            document_id=document_id,
            title=title,
            strategy=request.chunk_strategy,
            scope=request.scope,
            memory_type=request.memory_type,
            total_chars=len(normalized),
            total_chunks=len(previews),
            parent_documents_count=parent_count,
            ready_to_store=bool(previews),
            chunks=previews,
        )

    def commit(self, request: IngestionCommitRequest) -> IngestionCommitResponse:
        document_id = f"doc_{uuid4().hex[:8]}"
        title = self._resolve_title(request.title, request.text)
        normalized = self._normalize_text(request.text)
        chunks, parent_count = self._chunk_document(document_id=document_id, text=normalized, request=request)

        saved_ids: list[str] = []
        parent_memory_id: str | None = None
        if request.chunk_strategy == IngestionStrategy.PARENT_CHILD:
            parent_record = LongTermMemoryRecord(
                scope=request.scope,
                memory_type=request.memory_type,
                document_id=document_id,
                chunk_strategy=request.chunk_strategy.value,
                topic=title,
                summary=self._summarize_text(normalized),
                details=normalized,
                tags=[*request.tags, "manual_ingest", "parent_doc", f"strategy:{request.chunk_strategy.value}"],
                source=MemorySource(source_type="manual_ingest_parent"),
            )
            saved_parent = self.memory_manager.remember(parent_record)
            parent_memory_id = saved_parent.id
            saved_ids.append(saved_parent.id)

        for chunk in chunks:
            record = LongTermMemoryRecord(
                scope=request.scope,
                memory_type=request.memory_type,
                document_id=document_id,
                parent_id=parent_memory_id or chunk.parent_id,
                chunk_index=chunk.chunk_index,
                chunk_strategy=request.chunk_strategy.value,
                topic=f"{title} · 分块 {chunk.chunk_index + 1}",
                summary=self._summarize_text(chunk.text),
                details=chunk.text,
                tags=[*request.tags, "manual_ingest", "chunk", f"strategy:{request.chunk_strategy.value}"],
                source=MemorySource(source_type="manual_ingest_chunk"),
            )
            saved = self.memory_manager.remember(record)
            saved_ids.append(saved.id)

        return IngestionCommitResponse(
            document_id=document_id,
            title=title,
            strategy=request.chunk_strategy,
            scope=request.scope,
            stored_count=len(saved_ids),
            parent_count=parent_count,
            chunk_count=len(chunks),
            memory_ids=saved_ids,
        )

    def _build_chunk_preview(self, candidate: ChunkCandidate) -> ChunkPreview:
        embedding = self.embedder.embed(candidate.text)
        return ChunkPreview(
            chunk_id=candidate.chunk_id,
            parent_id=candidate.parent_id,
            chunk_index=candidate.chunk_index,
            text=candidate.text,
            char_count=len(candidate.text),
            summary=self._summarize_text(candidate.text),
            embedding_preview=[round(value, 4) for value in embedding[: min(12, len(embedding))]],
            embedding_dimensions=len(embedding),
        )

    def _chunk_document(
        self,
        *,
        document_id: str,
        text: str,
        request: IngestionPreviewRequest | IngestionCommitRequest,
    ) -> tuple[list[ChunkCandidate], int]:
        if request.chunk_strategy == IngestionStrategy.PARENT_CHILD:
            children = self._recursive_chunk_text(text, request.max_chunk_chars, request.overlap_chars)
            parent_id = f"{document_id}_parent"
            return (
                [
                    ChunkCandidate(
                        chunk_id=f"{document_id}_chunk_{index}",
                        parent_id=parent_id,
                        chunk_index=index,
                        text=chunk,
                    )
                    for index, chunk in enumerate(children)
                ],
                1,
            )
        if request.chunk_strategy == IngestionStrategy.SEMANTIC:
            chunks = self._semantic_chunk_text(text, request.max_chunk_chars, request.overlap_chars)
        else:
            chunks = self._recursive_chunk_text(text, request.max_chunk_chars, request.overlap_chars)
        return (
            [
                ChunkCandidate(
                    chunk_id=f"{document_id}_chunk_{index}",
                    parent_id=None,
                    chunk_index=index,
                    text=chunk,
                )
                for index, chunk in enumerate(chunks)
            ],
            0,
        )

    def _recursive_chunk_text(self, text: str, max_chunk_chars: int, overlap_chars: int) -> list[str]:
        paragraphs = [item.strip() for item in re.split(r"\n{2,}", text) if item.strip()]
        chunks: list[str] = []
        for paragraph in paragraphs or [text]:
            if len(paragraph) <= max_chunk_chars:
                chunks.append(paragraph)
                continue
            for sentence_chunk in self._group_sentences(self._split_sentences(paragraph), max_chunk_chars):
                if len(sentence_chunk) <= max_chunk_chars:
                    chunks.append(sentence_chunk)
                else:
                    chunks.extend(self._hard_wrap(sentence_chunk, max_chunk_chars))
        return self._apply_overlap(chunks, overlap_chars)

    def _semantic_chunk_text(self, text: str, max_chunk_chars: int, overlap_chars: int) -> list[str]:
        sentences = self._split_sentences(text)
        if not sentences:
            return []
        chunks: list[str] = []
        current = sentences[0]
        for sentence in sentences[1:]:
            candidate = f"{current} {sentence}".strip()
            if len(candidate) > max_chunk_chars:
                chunks.append(current.strip())
                current = sentence
                continue
            if self._semantic_break(current, sentence, max_chunk_chars):
                chunks.append(current.strip())
                current = sentence
                continue
            current = candidate
        if current.strip():
            chunks.append(current.strip())
        return self._apply_overlap(chunks, overlap_chars)

    def _semantic_break(self, current: str, sentence: str, max_chunk_chars: int) -> bool:
        if len(current) < max_chunk_chars * 0.45:
            return False
        current_tokens = self._tokenize(current)
        next_tokens = self._tokenize(sentence)
        if not current_tokens or not next_tokens:
            return False
        overlap = len(current_tokens & next_tokens)
        union = len(current_tokens | next_tokens)
        similarity = overlap / union if union else 0.0
        return similarity < 0.08

    def _group_sentences(self, sentences: list[str], max_chunk_chars: int) -> list[str]:
        chunks: list[str] = []
        current = ""
        for sentence in sentences:
            candidate = f"{current} {sentence}".strip() if current else sentence
            if current and len(candidate) > max_chunk_chars:
                chunks.append(current.strip())
                current = sentence
            else:
                current = candidate
        if current.strip():
            chunks.append(current.strip())
        return chunks

    def _hard_wrap(self, text: str, max_chunk_chars: int) -> list[str]:
        return [text[index : index + max_chunk_chars].strip() for index in range(0, len(text), max_chunk_chars) if text[index : index + max_chunk_chars].strip()]

    def _apply_overlap(self, chunks: list[str], overlap_chars: int) -> list[str]:
        if overlap_chars <= 0 or len(chunks) <= 1:
            return [chunk.strip() for chunk in chunks if chunk.strip()]
        merged: list[str] = []
        for index, chunk in enumerate(chunks):
            if index == 0:
                merged.append(chunk.strip())
                continue
            prefix = chunks[index - 1][-overlap_chars:].strip()
            combined = f"{prefix}\n{chunk}".strip() if prefix else chunk.strip()
            merged.append(combined)
        return [chunk for chunk in merged if chunk]

    def _split_sentences(self, text: str) -> list[str]:
        normalized = text.replace("\n", " ").strip()
        if not normalized:
            return []
        parts = re.split(r"(?<=[。！？!?；;])\s*", normalized)
        return [part.strip() for part in parts if part.strip()]

    def _tokenize(self, text: str) -> set[str]:
        normalized = re.sub(r"[\s,，。；;:：()（）]+", " ", text.lower())
        tokens = {item for item in normalized.split() if len(item) >= 2}
        for chunk in normalized.split():
            if len(chunk) >= 4 and any("\u4e00" <= char <= "\u9fff" for char in chunk):
                for index in range(len(chunk) - 1):
                    tokens.add(chunk[index : index + 2])
        return tokens

    def _normalize_text(self, text: str) -> str:
        lines = [line.rstrip() for line in text.replace("\r\n", "\n").split("\n")]
        normalized = "\n".join(lines)
        normalized = re.sub(r"\n{3,}", "\n\n", normalized)
        return normalized.strip()

    def _resolve_title(self, title: str | None, text: str) -> str:
        if title and title.strip():
            return title.strip()
        first_line = next((line.strip() for line in text.splitlines() if line.strip()), "")
        if first_line:
            return first_line[:32]
        return "手动向量化文档"

    def _summarize_text(self, text: str, limit: int = 120) -> str:
        normalized = text.replace("\n", " ").strip()
        if len(normalized) <= limit:
            return normalized
        return normalized[:limit].rstrip() + "..."

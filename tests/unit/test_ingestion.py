import unittest

from orion_agent.core.memory import LongTermMemoryManager
from orion_agent.core.models import IngestionCommitRequest, IngestionPreviewRequest
from orion_agent.core.ingestion import DocumentIngestionService
from orion_agent.core.repository import TaskRepository
from orion_agent.core.vector_store import LocalVectorStore


class StubEmbedder:
    def embed(self, text: str) -> list[float]:
        base = float((sum(ord(char) for char in text) % 53) + 1)
        return [base, float(len(text) or 1), 1.0, 0.5]

    def health(self) -> dict[str, str]:
        return {"provider": "stub", "mode": "test"}


class IngestionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = TaskRepository(db_path=":memory:")
        self.embedder = StubEmbedder()
        self.memory_manager = LongTermMemoryManager(
            repository=self.repository,
            embedder=self.embedder,
            vector_store=LocalVectorStore(repository=self.repository),
        )
        self.ingestion = DocumentIngestionService(
            repository=self.repository,
            embedder=self.embedder,
            memory_manager=self.memory_manager,
        )

    def tearDown(self) -> None:
        self.repository.close()

    def test_recursive_preview_splits_long_text_into_multiple_chunks(self) -> None:
        text = (
            "第一段介绍系统规划与任务分解。\n\n"
            "第二段说明检索与向量召回如何协作。\n\n"
            "第三段描述提示词拼接、执行和结果复核。"
        )

        preview = self.ingestion.preview(
            IngestionPreviewRequest(
                title="RAG 文档",
                text=text,
                chunk_strategy="recursive",
                max_chunk_chars=24,
                overlap_chars=4,
            )
        )

        self.assertGreaterEqual(preview.total_chunks, 2)
        self.assertTrue(all(chunk.char_count <= 28 for chunk in preview.chunks))
        self.assertTrue(all(chunk.embedding_dimensions == 4 for chunk in preview.chunks))

    def test_parent_child_preview_assigns_parent_ids(self) -> None:
        text = "父文档用于统一展示，子块用于索引召回。" * 8

        preview = self.ingestion.preview(
            IngestionPreviewRequest(
                title="父子文档测试",
                text=text,
                chunk_strategy="parent_child",
                max_chunk_chars=40,
                overlap_chars=8,
            )
        )

        self.assertEqual(preview.parent_documents_count, 1)
        self.assertTrue(all(chunk.parent_id for chunk in preview.chunks))
        self.assertTrue(all(chunk.parent_id == preview.chunks[0].parent_id for chunk in preview.chunks))

    def test_semantic_preview_breaks_on_sentence_boundaries(self) -> None:
        text = "检索要稳定。向量召回要可解释。前端要展示命中原因。入库之前要允许用户确认。"

        preview = self.ingestion.preview(
            IngestionPreviewRequest(
                title="语义分段",
                text=text,
                chunk_strategy="semantic",
                max_chunk_chars=18,
                overlap_chars=0,
            )
        )

        self.assertGreaterEqual(preview.total_chunks, 2)
        self.assertTrue(all(chunk.text.endswith(("。", "！", "？")) or len(chunk.text) <= 18 for chunk in preview.chunks))

    def test_commit_stores_parent_and_chunk_memories(self) -> None:
        text = "这是一个需要手动向量化的长文档。" * 10

        committed = self.ingestion.commit(
            IngestionCommitRequest(
                title="手动入库文档",
                text=text,
                scope="manual",
                memory_type="document_note",
                chunk_strategy="parent_child",
                max_chunk_chars=36,
                overlap_chars=6,
            )
        )

        self.assertGreaterEqual(committed.stored_count, 2)
        self.assertGreaterEqual(committed.chunk_count, 1)
        self.assertEqual(len(committed.memory_ids), committed.stored_count)

        stored = self.repository.list_long_term_memories(scope="manual", limit=20)
        self.assertTrue(any(record.source.source_type == "manual_ingest_parent" for record in stored))
        self.assertTrue(any(record.source.source_type == "manual_ingest_chunk" for record in stored))

    def test_parent_child_recall_promotes_chunk_hit_to_parent_document(self) -> None:
        text = "这份文档重点介绍向量检索、父子文档检索和人工确认入库流程。" * 8

        committed = self.ingestion.commit(
            IngestionCommitRequest(
                title="父文档召回测试",
                text=text,
                scope="manual",
                memory_type="document_note",
                chunk_strategy="parent_child",
                max_chunk_chars=28,
                overlap_chars=4,
            )
        )

        recalled = self.memory_manager.recall("父子文档检索流程", scope="manual", limit=1)

        self.assertEqual(len(recalled), 1)
        self.assertIn(recalled[0].id, committed.memory_ids)
        self.assertEqual(recalled[0].source.source_type, "manual_ingest_parent")
        self.assertTrue(recalled[0].retrieval_reason)
        self.assertIn("parent_doc_promoted", recalled[0].retrieval_reason)


if __name__ == "__main__":
    unittest.main()

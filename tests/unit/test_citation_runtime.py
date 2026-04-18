import unittest
from datetime import UTC, datetime

from orion_agent.core.llm_runtime import BaseLLMClient
from orion_agent.core.models import (
    ContextLayer,
    LongTermMemoryRecord,
    MemorySource,
    ParsedGoal,
    TaskRecord,
    TaskStatus,
    UserProfileFact,
)
from orion_agent.core.repository import TaskRepository


class StubLLMClient(BaseLLMClient):
    """Minimal stub LLM client for citation integration tests."""

    def generate_json(self, *, system_prompt: str, user_prompt: str) -> dict:
        return {}

    def generate_text(self, *, system_prompt: str, user_prompt: str) -> str:
        return ""

    def health(self) -> dict[str, str]:
        return {"status": "ok"}

    def probe(self) -> dict:
        return {"status": "ready"}

    def stream_text(self, *, system_prompt: str, user_prompt: str):
        yield ""


class CitationRuntimeTests(unittest.TestCase):
    """Integration tests for runtime_agent citation building via CitationMap.

    Verifies that:
    - Memory, profile, session_message, and source_summary sources are registered
    - Paragraph citations are built from result markdown
    - Frontend-facing citation kinds are aligned with backend CITATION_KINDS
    """

    def _build_agent_service(self) -> "AgentService":
        from orion_agent.core.runtime_agent import AgentService

        return AgentService(
            repository=TaskRepository(db_path=":memory:"),
            llm_client=StubLLMClient(),
        )

    def test_build_citation_map_registers_all_source_kinds(self) -> None:
        # 场景：_build_citation_map 为 memory、profile、session_message、source_summary
        #       四类来源均注册对应的 CitationSource，且 kind 值与 CITATION_KINDS 对齐。
        base = datetime(2026, 4, 17, 12, 0, tzinfo=UTC)
        task = TaskRecord(
            title="Test citation mapping",
            status=TaskStatus.COMPLETED,
            created_at=base,
            updated_at=base,
            parsed_goal=ParsedGoal(goal="测试引用映射", constraints=["中文输出"]),
            recalled_memories=[
                LongTermMemoryRecord(
                    id="mem_001",
                    topic="项目架构",
                    summary="采用分层架构设计",
                    details="前端采用 React，后端采用 FastAPI",
                    memory_type="technical_doc",
                    retrieval_score=0.95,
                    retrieval_reason="语义相似度高",
                    retrieval_channels=["vector"],
                    source=MemorySource(session_id="sess_001", task_id="task_001"),
                )
            ],
            profile_hits=[
                UserProfileFact(
                    id="fact_001",
                    category="preference",
                    label="语言偏好",
                    value="中文",
                    summary="长期偏好中文回答",
                    source_session_id="sess_001",
                    source_task_id="task_001",
                )
            ],
            context_layers=ContextLayer(
                recent_messages=["用户询问项目架构"],
                source_summary="项目文档位于 docs/ 目录",
            ),
            result="## 回答\n该项目采用分层架构。\n\n## 工具调用\n无",
        )

        service = self._build_agent_service()
        cmap = service._build_citation_map(task)

        # Verify source kinds match CITATION_KINDS keys
        kinds_found = {s.kind for s in cmap.sources}
        expected_kinds = {"memory", "profile", "session_message", "source_summary"}
        self.assertEqual(kinds_found, expected_kinds, "All citation kinds should be registered")

        # Verify memory source fields
        memory_sources = [s for s in cmap.sources if s.kind == "memory"]
        self.assertEqual(len(memory_sources), 1)
        mem_src = memory_sources[0]
        self.assertEqual(mem_src.label, "记忆：项目架构")
        self.assertEqual(mem_src.source_record_id, "mem_001")
        self.assertIsNotNone(mem_src.excerpt)

        # Verify profile source fields
        profile_sources = [s for s in cmap.sources if s.kind == "profile"]
        self.assertEqual(len(profile_sources), 1)
        prof_src = profile_sources[0]
        self.assertEqual(prof_src.label, "画像：语言偏好=中文")
        self.assertEqual(prof_src.source_record_id, "fact_001")

        # Verify session_message sources (source_session_id comes from task.session_id, not memory.source)
        session_sources = [s for s in cmap.sources if s.kind == "session_message"]
        self.assertEqual(len(session_sources), 1)
        self.assertEqual(session_sources[0].source_session_id, task.session_id)

        # Verify source_summary source
        summary_sources = [s for s in cmap.sources if s.kind == "source_summary"]
        self.assertEqual(len(summary_sources), 1)
        self.assertIn("项目文档", summary_sources[0].detail)

    def test_build_citation_map_handles_empty_task(self) -> None:
        # 场景：空召回记忆、空画像、空上下文的 task 不会崩溃。
        task = TaskRecord(
            title="Empty citation test",
            status=TaskStatus.COMPLETED,
            parsed_goal=ParsedGoal(goal="空引用测试"),
        )

        service = self._build_agent_service()
        cmap = service._build_citation_map(task)

        self.assertEqual(len(cmap.sources), 0)
        self.assertEqual(len(cmap.paragraphs), 0)

    def test_build_paragraph_citations_into_map(self) -> None:
        # 场景：带有结果文本的 task，段落引用正确映射到源。
        task = TaskRecord(
            title="Paragraph citation test",
            status=TaskStatus.COMPLETED,
            parsed_goal=ParsedGoal(goal="测试段落引用"),
            recalled_memories=[
                LongTermMemoryRecord(
                    id="mem_002",
                    topic="项目架构",
                    summary="采用分层架构设计",
                    details="前端采用 React，后端采用 FastAPI，数据库采用 PostgreSQL",
                    memory_type="technical_doc",
                    retrieval_score=0.92,
                    retrieval_reason="语义相似",
                    retrieval_channels=["vector"],
                    source=MemorySource(),
                )
            ],
            context_layers=ContextLayer(),
            result="## 回答\n该项目采用分层架构，前端使用 React，后端使用 FastAPI。\n\n项目架构采用分层设计。",
        )

        service = self._build_agent_service()
        cmap = service._build_citation_map(task)

        self.assertGreaterEqual(len(cmap.sources), 1)
        self.assertGreaterEqual(len(cmap.paragraphs), 1)
        for p in cmap.paragraphs:
            self.assertIsInstance(p.paragraph_index, int)
            self.assertIsInstance(p.paragraph_text, str)
            self.assertIsInstance(p.source_ids, list)
            self.assertIsInstance(p.source_labels, list)
            self.assertEqual(len(p.source_ids), len(p.source_labels))

    def test_build_result_citations_populates_task_record(self) -> None:
        # 场景：_build_result_citations 将 citation_sources 和 paragraph_citations
        #       正确写入 task record。
        task = TaskRecord(
            title="Result citation test",
            status=TaskStatus.COMPLETED,
            parsed_goal=ParsedGoal(goal="结果引用测试"),
            recalled_memories=[
                LongTermMemoryRecord(
                    id="mem_003",
                    topic="测试主题",
                    summary="测试摘要内容",
                    details="这是详细的测试内容",
                    memory_type="test",
                    retrieval_score=0.9,
                    retrieval_reason="测试",
                    retrieval_channels=["vector"],
                    source=MemorySource(),
                )
            ],
            context_layers=ContextLayer(),
            result="## 回答\n这是一个测试结果的详细回答内容，包含足够长度的文本用于段落引用测试。\n\n第二段内容也足够长，可以被正确识别和引用。",
        )

        service = self._build_agent_service()
        service._build_result_citations(task)

        self.assertGreaterEqual(len(task.citation_sources), 1)
        self.assertGreaterEqual(len(task.paragraph_citations), 1)
        for src in task.citation_sources:
            self.assertIn(src.kind, {"memory", "profile", "session_message", "source_summary"})
        for pcite in task.paragraph_citations:
            self.assertIsInstance(pcite.paragraph_index, int)

    def test_citation_kinds_match_frontend_to_chinese_source_kind(self) -> None:
        # 场景：所有 backend CITATION_KINDS keys 都能被 frontend toChineseSourceKind
        #       正确映射为中文标签，确保前端渲染不回落落到 raw kind 值。
        from orion_agent.core.citation_map import CITATION_KINDS

        # These are the kinds registered by _build_citation_map
        runtime_kinds = {"memory", "profile", "session_message", "source_summary"}

        # Frontend map (must match markdownUtils.tsx toChineseSourceKind)
        frontend_map = {
            "memory": "记忆",
            "profile": "画像",
            "session_message": "会话消息",
            "source_summary": "外部材料摘要",
            "web_search": "网络搜索",
            "file": "本地文件",
        }

        for kind in runtime_kinds:
            self.assertIn(kind, frontend_map, f"frontend map must contain kind '{kind}' from CITATION_KINDS")
            self.assertIn(kind, CITATION_KINDS, f"CITATION_KINDS must contain kind '{kind}'")


if __name__ == "__main__":
    unittest.main()

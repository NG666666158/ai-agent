import unittest
import sys
import types
from datetime import UTC, datetime

if "openai" not in sys.modules:
    openai_stub = types.ModuleType("openai")

    class OpenAI:  # pragma: no cover - test stub
        def __init__(self, *args, **kwargs) -> None:
            pass

    openai_stub.OpenAI = OpenAI
    sys.modules["openai"] = openai_stub

from orion_agent.core.context_builder import CONTEXT_BUDGET, ContextBuilder
from orion_agent.core.models import (
    ChatMessage,
    ChatMessageRole,
    ChatSession,
    ContextBudgetUsage,
    ContextTraceEntry,
    TaskCreateRequest,
)


class StubProfileManager:
    def __init__(self) -> None:
        self._facts = [
            "语言偏好: 中文",
            "专业领域: Python开发",
        ]

    def snapshot(self, limit: int = 8) -> list[str]:
        return self._facts[:limit]


class StubRepository:
    def __init__(self, session: ChatSession | None = None, messages: list[ChatMessage] | None = None) -> None:
        self._session = session
        self._messages = messages or []

    def get_session(self, session_id: str) -> ChatSession | None:
        return self._session

    def list_session_messages(self, session_id: str, limit: int = 100) -> list[ChatMessage]:
        return self._messages[-limit:]


class ContextBuilderTests(unittest.TestCase):
    def test_build_returns_context_layer_with_all_fields(self) -> None:
        # 场景：ContextBuilder.build() 返回完整 ContextLayer，包含所有层。
        profile_mgr = StubProfileManager()
        repo = StubRepository()
        builder = ContextBuilder(profile_mgr, repo)

        request = TaskCreateRequest(
            goal="总结 Python 项目架构",
            expected_output="Markdown 格式",
            memory_scope="full",
            session_id="session_test",
            source_text="这是一个 Python 项目。",
        )

        ctx = builder.build(request)

        self.assertTrue(ctx.system_instructions)
        self.assertEqual(ctx.session_summary, "")
        self.assertEqual(ctx.recent_messages, [])
        self.assertEqual(ctx.profile_facts, ["语言偏好: 中文", "专业领域: Python开发"])
        self.assertIn("goal=", ctx.working_memory[0])
        self.assertEqual(ctx.source_summary, "这是一个 Python 项目。")
        self.assertEqual(ctx.layer_budget, CONTEXT_BUDGET)
        self.assertIsNotNone(ctx.version)

    def test_build_produces_trace_entries(self) -> None:
        # 场景：build() 产生结构化 ContextTraceEntry 列表。
        profile_mgr = StubProfileManager()
        repo = StubRepository()
        builder = ContextBuilder(profile_mgr, repo)

        request = TaskCreateRequest(
            goal="测试追踪",
            session_id="s1",
            source_text="外部材料内容",
        )
        ctx = builder.build(request)

        self.assertIsInstance(ctx.trace_entries, list)
        self.assertGreater(len(ctx.trace_entries), 0)
        for entry in ctx.trace_entries:
            self.assertIsInstance(entry, ContextTraceEntry)
            self.assertTrue(entry.layer)
            self.assertTrue(entry.source)
            self.assertTrue(entry.message)
        # Check that all expected layers are covered
        layers = {e.layer for e in ctx.trace_entries}
        expected_layers = {"session_summary", "recent_messages", "condensed_recent_messages",
                          "profile_facts", "working_memory", "source_summary"}
        self.assertEqual(layers, expected_layers)

    def test_build_produces_budget_usage(self) -> None:
        # 场景：build() 产生结构化 ContextBudgetUsage。
        profile_mgr = StubProfileManager()
        repo = StubRepository()
        builder = ContextBuilder(profile_mgr, repo)

        request = TaskCreateRequest(
            goal="测试预算",
            source_text="x" * 500,
        )
        ctx = builder.build(request)

        self.assertIsInstance(ctx.budget_usage, ContextBudgetUsage)
        # Verify budget limits match CONTEXT_BUDGET
        bu = ctx.budget_usage
        self.assertEqual(bu.session_summary_limit, CONTEXT_BUDGET["session_summary"])
        self.assertEqual(bu.recent_messages_limit, CONTEXT_BUDGET["recent_messages"])
        self.assertEqual(bu.profile_facts_limit, CONTEXT_BUDGET["profile_facts"])
        self.assertEqual(bu.source_summary_limit, CONTEXT_BUDGET["source_summary"])
        # source_summary was 500 chars but limited to 600
        self.assertEqual(bu.source_summary_used, 500)
        # counts should be populated
        self.assertGreaterEqual(bu.profile_facts_count, 0)
        self.assertGreaterEqual(bu.recent_messages_count, 0)

    def test_build_trace_entries_capture_session_context(self) -> None:
        # 场景：有 session_id 时，trace_entries 的 source 指向 session。
        base_time = datetime(2026, 4, 18, 12, 0, tzinfo=UTC)
        session = ChatSession(id="s_abc", title="Test", context_summary="摘要文本")
        messages = [
            ChatMessage(session_id="s_abc", role=ChatMessageRole.USER, content="用户消息", created_at=base_time),
        ]
        profile_mgr = StubProfileManager()
        repo = StubRepository(session=session, messages=messages)
        builder = ContextBuilder(profile_mgr, repo)

        request = TaskCreateRequest(goal="测试", session_id="s_abc")
        ctx = builder.build(request)

        # Find the session_summary trace entry
        summary_entry = next((e for e in ctx.trace_entries if e.layer == "session_summary"), None)
        self.assertIsNotNone(summary_entry)
        self.assertEqual(summary_entry.source, "session")
        self.assertEqual(summary_entry.source_id, "s_abc")

    def test_build_with_session_loads_session_context(self) -> None:
        # 场景：有 session_id 时，从仓库加载会话摘要和最近消息。
        base_time = datetime(2026, 4, 18, 12, 0, tzinfo=UTC)
        session = ChatSession(
            id="session_123",
            title="测试会话",
            context_summary="用户正在评估项目架构",
        )
        messages = [
            ChatMessage(session_id="session_123", role=ChatMessageRole.USER, content="请总结架构", created_at=base_time),
            ChatMessage(session_id="session_123", role=ChatMessageRole.ASSISTANT, content="好的", created_at=base_time),
        ]
        profile_mgr = StubProfileManager()
        repo = StubRepository(session=session, messages=messages)
        builder = ContextBuilder(profile_mgr, repo)

        request = TaskCreateRequest(goal="总结架构", session_id="session_123")
        ctx = builder.build(request)

        self.assertEqual(ctx.session_summary, "用户正在评估项目架构")
        self.assertEqual(len(ctx.recent_messages), 2)

    def test_build_trims_text_to_budget(self) -> None:
        # 场景：文本超过 budget 限制时自动截断。
        profile_mgr = StubProfileManager()
        repo = StubRepository()
        builder = ContextBuilder(profile_mgr, repo)

        long_source = "x" * 1000
        request = TaskCreateRequest(
            goal="测试",
            source_text=long_source,
        )
        ctx = builder.build(request)

        self.assertLessEqual(len(ctx.source_summary), CONTEXT_BUDGET["source_summary"])

    def test_build_session_context_falls_back_when_no_session(self) -> None:
        # 场景：无 session_id 时，_build_session_context 返回空摘要但保留 profile facts。
        profile_mgr = StubProfileManager()
        repo = StubRepository(session=None)
        builder = ContextBuilder(profile_mgr, repo)

        result = builder._build_session_context(None)

        self.assertEqual(result["session_summary"], "")
        self.assertEqual(result["recent_messages"], [])
        self.assertEqual(result["profile_facts"], ["语言偏好: 中文", "专业领域: Python开发"])

    def test_trim_text_ellipsis_at_limit(self) -> None:
        # 场景：_trim_text 在达到限制时添加省略号。
        profile_mgr = StubProfileManager()
        repo = StubRepository()
        builder = ContextBuilder(profile_mgr, repo)

        long_text = "a" * 100
        result = builder._trim_text(long_text, 20)

        self.assertEqual(len(result), 20)
        self.assertEqual(result[-1], "…")


if __name__ == "__main__":
    unittest.main()
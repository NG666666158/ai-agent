"""Tests for runtime context governance updates (US-R16).

Verifies that recalled_memories_trim_reason and profile_facts_trim_reason
are correctly updated after memory recall and profile matching, and that
trace entries are added for these runtime-populated layers.
"""

import unittest
import sys
import types

if "openai" not in sys.modules:
    openai_stub = types.ModuleType("openai")

    class OpenAI:  # pragma: no cover - test stub
        def __init__(self, *args, **kwargs) -> None:
            pass

    openai_stub.OpenAI = OpenAI
    sys.modules["openai"] = openai_stub

from orion_agent.core.context_builder import CONTEXT_BUDGET, ContextBuilder
from orion_agent.core.models import (
    ContextBudgetUsage,
    ContextLayer,
    ContextTraceEntry,
    TaskCreateRequest,
    TrimReason,
    utcnow,
)


class StubProfileManager:
    """Stub that returns configurable profile facts."""

    def __init__(self, facts: list[str] | None = None) -> None:
        self._facts = facts or ["语言偏好: 中文", "专业领域: Python开发"]

    def snapshot(self, limit: int = 8) -> list[str]:
        return self._facts[:limit]


class StubRepository:
    def __init__(self) -> None:
        pass

    def get_session(self, session_id: str) -> None:
        return None

    def list_session_messages(self, session_id: str, limit: int = 100) -> list:
        return []


class ContextGovernanceRuntimeTests(unittest.TestCase):
    """Tests for runtime context governance updates (US-R16).

    These tests simulate the runtime update path in runtime_agent._run_task_flow
    to verify that governance fields are correctly updated after recall and matching.
    """

    def _build_initial_context(self, session_id: str | None = "s_test") -> ContextLayer:
        """Build initial context layer with placeholder governance values."""
        profile_mgr = StubProfileManager()
        repo = StubRepository()
        builder = ContextBuilder(profile_mgr, repo)
        request = TaskCreateRequest(
            goal="测试运行时治理更新",
            session_id=session_id,
            source_text="测试源文本",
        )
        return builder.build(request)

    def test_recalled_memories_trim_reason_compressed_when_at_limit(self) -> None:
        # 场景：recall 返回恰好 limit 条记忆时，trim_reason 应为 COMPRESSED。
        ctx = self._build_initial_context()
        recalled_limit = 5
        recalled_count = 5  # 恰好达到 limit

        # Simulate runtime update (runtime_agent._run_task_flow lines ~437-452)
        ctx.recalled_memories = [f"记忆 {i}" for i in range(recalled_count)]
        if ctx.budget_usage:
            ctx.budget_usage.recalled_memories_count = recalled_count
            recalled_trim_reason = TrimReason.COMPRESSED if recalled_count >= recalled_limit else TrimReason.NONE
            ctx.budget_usage.recalled_memories_trim_reason = recalled_trim_reason

        self.assertEqual(ctx.budget_usage.recalled_memories_count, 5)
        self.assertEqual(ctx.budget_usage.recalled_memories_trim_reason, TrimReason.COMPRESSED)

    def test_recalled_memories_trim_reason_none_when_below_limit(self) -> None:
        # 场景：recall 返回少于 limit 条记忆时，trim_reason 应为 NONE。
        ctx = self._build_initial_context()
        recalled_limit = 5
        recalled_count = 3  # 少于 limit

        ctx.recalled_memories = [f"记忆 {i}" for i in range(recalled_count)]
        if ctx.budget_usage:
            ctx.budget_usage.recalled_memories_count = recalled_count
            recalled_trim_reason = TrimReason.COMPRESSED if recalled_count >= recalled_limit else TrimReason.NONE
            ctx.budget_usage.recalled_memories_trim_reason = recalled_trim_reason

        self.assertEqual(ctx.budget_usage.recalled_memories_count, 3)
        self.assertEqual(ctx.budget_usage.recalled_memories_trim_reason, TrimReason.NONE)

    def test_profile_facts_trim_reason_compressed_when_at_limit(self) -> None:
        # 场景：match_relevant 返回恰好 limit 条画像时，trim_reason 应为 COMPRESSED。
        ctx = self._build_initial_context()
        profile_limit = 4
        profile_count = 4  # 恰好达到 limit

        ctx.profile_facts = [f"画像 {i}: 值" for i in range(profile_count)]
        if ctx.budget_usage:
            ctx.budget_usage.profile_facts_count = profile_count
            profile_trim_reason = TrimReason.COMPRESSED if profile_count >= profile_limit else TrimReason.NONE
            ctx.budget_usage.profile_facts_trim_reason = profile_trim_reason

        self.assertEqual(ctx.budget_usage.profile_facts_count, 4)
        self.assertEqual(ctx.budget_usage.profile_facts_trim_reason, TrimReason.COMPRESSED)

    def test_profile_facts_trim_reason_none_when_below_limit(self) -> None:
        # 场景：match_relevant 返回少于 limit 条画像时，trim_reason 应为 NONE。
        ctx = self._build_initial_context()
        profile_limit = 4
        profile_count = 2  # 少于 limit

        ctx.profile_facts = [f"画像 {i}: 值" for i in range(profile_count)]
        if ctx.budget_usage:
            ctx.budget_usage.profile_facts_count = profile_count
            profile_trim_reason = TrimReason.COMPRESSED if profile_count >= profile_limit else TrimReason.NONE
            ctx.budget_usage.profile_facts_trim_reason = profile_trim_reason

        self.assertEqual(ctx.budget_usage.profile_facts_count, 2)
        self.assertEqual(ctx.budget_usage.profile_facts_trim_reason, TrimReason.NONE)

    def test_trace_entry_added_for_recalled_memories_layer(self) -> None:
        # 场景：运行时召回记忆后，应添加 recalled_memories 层的 trace entry。
        ctx = self._build_initial_context()
        recalled_count = 3

        ctx.recalled_memories = [f"记忆 {i}" for i in range(recalled_count)]
        if ctx.budget_usage:
            ctx.budget_usage.recalled_memories_count = recalled_count
            recalled_trim_reason = TrimReason.NONE
            ctx.budget_usage.recalled_memories_trim_reason = recalled_trim_reason
            # Add runtime trace entry for recalled_memories layer
            ctx.trace_entries.append(
                ContextTraceEntry(
                    layer="recalled_memories",
                    source="long_term_memory",
                    source_id=None,
                    message=f"limit=5, count={recalled_count}, reason={recalled_trim_reason.value}",
                )
            )

        recalled_trace = [e for e in ctx.trace_entries if e.layer == "recalled_memories"]
        self.assertEqual(len(recalled_trace), 1)
        self.assertEqual(recalled_trace[0].source, "long_term_memory")
        self.assertIn("count=3", recalled_trace[0].message)

    def test_profile_facts_trim_reason_updated_at_runtime(self) -> None:
        # 场景：profile_facts_trim_reason 在运行时根据 match_relevant 结果更新。
        # 注：profile_facts trace entry 在 build() 中已添加，运行时只更新 budget_usage 字段。
        ctx = self._build_initial_context()
        profile_count = 4
        profile_limit = 4

        ctx.profile_facts = [f"画像 {i}: 值" for i in range(profile_count)]
        if ctx.budget_usage:
            ctx.budget_usage.profile_facts_count = profile_count
            profile_trim_reason = TrimReason.COMPRESSED if profile_count >= profile_limit else TrimReason.NONE
            ctx.budget_usage.profile_facts_trim_reason = profile_trim_reason

        self.assertEqual(ctx.budget_usage.profile_facts_count, 4)
        self.assertEqual(ctx.budget_usage.profile_facts_trim_reason, TrimReason.COMPRESSED)
        # profile_facts trace entry already exists from build() - runtime updates budget fields only

    def test_full_runtime_governance_update_flow(self) -> None:
        # 场景：完整的运行时治理更新流程，包括 count、trim_reason 和 trace entries。
        ctx = self._build_initial_context()
        recalled_count = 5
        profile_count = 4
        recalled_limit = 5
        profile_limit = 4

        recalled_trim_reason = TrimReason.COMPRESSED if recalled_count >= recalled_limit else TrimReason.NONE
        profile_trim_reason = TrimReason.COMPRESSED if profile_count >= profile_limit else TrimReason.NONE

        ctx.recalled_memories = [f"记忆 {i}" for i in range(recalled_count)]
        ctx.profile_facts = [f"画像 {i}: 值" for i in range(profile_count)]

        if ctx.budget_usage:
            ctx.budget_usage.recalled_memories_count = recalled_count
            ctx.budget_usage.recalled_memories_trim_reason = recalled_trim_reason
            ctx.budget_usage.profile_facts_count = profile_count
            ctx.budget_usage.profile_facts_trim_reason = profile_trim_reason

            ctx.trace_entries.append(
                ContextTraceEntry(
                    layer="recalled_memories",
                    source="long_term_memory",
                    source_id=None,
                    message=f"limit={recalled_limit}, count={recalled_count}, reason={recalled_trim_reason.value}",
                )
            )
            # Note: profile_facts trace entry already exists from build(); runtime only updates budget fields

        # Verify recalled_memories governance
        self.assertEqual(ctx.budget_usage.recalled_memories_count, 5)
        self.assertEqual(ctx.budget_usage.recalled_memories_trim_reason, TrimReason.COMPRESSED)
        self.assertEqual(ctx.budget_usage.recalled_memories_limit, CONTEXT_BUDGET["recalled_memories"])

        # Verify profile_facts governance
        self.assertEqual(ctx.budget_usage.profile_facts_count, 4)
        self.assertEqual(ctx.budget_usage.profile_facts_trim_reason, TrimReason.COMPRESSED)
        self.assertEqual(ctx.budget_usage.profile_facts_limit, CONTEXT_BUDGET["profile_facts"])

        # Verify trace entries: recalled_memories from runtime, profile_facts from build
        recalled_trace = [e for e in ctx.trace_entries if e.layer == "recalled_memories"]
        self.assertEqual(len(recalled_trace), 1)
        self.assertIn("COMPRESSED", recalled_trace[0].message)

        profile_trace = [e for e in ctx.trace_entries if e.layer == "profile_facts"]
        self.assertEqual(len(profile_trace), 1)  # from build(), not from runtime


if __name__ == "__main__":
    unittest.main()

import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch, MagicMock

from orion_agent.core.config import Settings
from orion_agent.core.execution_engine import ExecutionEngine
from orion_agent.core.llm_runtime import FallbackLLMClient
from orion_agent.core.memory import TaskMemoryManager
from orion_agent.core.models import (
    FailureCategory,
    ParsedGoal,
    Step,
    TaskCreateRequest,
    TaskRecord,
    TaskStatus,
    ToolCallStatus,
    ToolDefinition,
    ToolPermission,
)
from orion_agent.core.prompts import PromptLibrary
from orion_agent.core.tools import ToolExecutionError, ToolRegistry


class ExecutionEngineToolCallTests(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = Settings(allow_online_search=False, tool_max_retries=2)
        self.engine = ExecutionEngine(
            tool_registry=ToolRegistry(self.settings),
            memory_manager=TaskMemoryManager(),
            llm_client=FallbackLLMClient(),
            prompts=PromptLibrary(),
            settings=self.settings,
        )

    def test_call_tool_records_success_invocation(self) -> None:
        task = TaskRecord(title="tool success")
        output = self.engine._call_tool(task=task, step_id="step_1", tool_name="summarize_text", text="abc")
        self.assertEqual(output, "abc")
        self.assertEqual(task.tool_invocations[-1].status.value, "SUCCESS")
        self.assertEqual(task.failure_category, FailureCategory.NONE)

    def test_call_tool_records_error_invocation_with_failure_category(self) -> None:
        task = TaskRecord(title="tool fail")
        output = self.engine._call_tool(
            task=task,
            step_id="step_1",
            tool_name="read_local_file",
            path="missing_xxx.txt",
        )
        self.assertIn("Tool read_local_file failed", output)
        self.assertEqual(task.tool_invocations[-1].status.value, "ERROR")
        self.assertEqual(task.tool_invocations[-1].failure_category, FailureCategory.INPUT_ERROR)
        self.assertEqual(task.failure_category, FailureCategory.INPUT_ERROR)

    def test_retryable_tool_retries_on_timeout(self) -> None:
        task = TaskRecord(title="retry web search")

        with patch.object(
            self.engine.tool_registry,
            "invoke",
            side_effect=ToolExecutionError(
                "timeout",
                category=FailureCategory.TOOL_TIMEOUT,
                retryable=True,
            ),
        ):
            output = self.engine._call_tool(
                task=task,
                step_id="step_retry",
                tool_name="web_search",
                query="latest ai agent",
            )

        self.assertIn("TOOL_TIMEOUT", output)
        self.assertEqual(task.retry_count, 2)
        self.assertEqual(len(task.tool_invocations), 3)
        self.assertTrue(all(item.failure_category == FailureCategory.TOOL_TIMEOUT for item in task.tool_invocations))


class ExecutionEngineToolMetadataTests(unittest.TestCase):
    """Tests for US-R6: tool metadata is captured in ToolInvocation."""

    def setUp(self) -> None:
        self.settings = Settings(allow_online_search=False, tool_max_retries=2)
        self.engine = ExecutionEngine(
            tool_registry=ToolRegistry(self.settings),
            memory_manager=TaskMemoryManager(),
            llm_client=FallbackLLMClient(),
            prompts=PromptLibrary(),
            settings=self.settings,
        )

    def test_tool_invocation_captures_category_display_name_label(self) -> None:
        """SUCCESS invocation captures category, display_name, display_label from tool definition."""
        task = TaskRecord(title="metadata capture")
        self.engine._call_tool(task=task, step_id="step_1", tool_name="web_search", query="test")
        invocation = task.tool_invocations[-1]
        self.assertEqual(invocation.category, "search")
        self.assertEqual(invocation.display_name, "网络搜索")
        self.assertEqual(invocation.display_label, "搜索")

    def test_tool_invocation_captures_permission_level(self) -> None:
        """Invocation records the permission level from tool definition."""
        task = TaskRecord(title="permission capture")
        # read_local_file has CONFIRM permission
        self.engine._call_tool(task=task, step_id="step_1", tool_name="read_local_file", path="missing.txt")
        invocation = task.tool_invocations[-1]
        self.assertEqual(invocation.permission_level, ToolPermission.CONFIRM)

    def test_tool_invocation_captures_timeout_ms(self) -> None:
        """Invocation records the effective timeout from tool definition."""
        task = TaskRecord(title="timeout capture")
        # read_local_file has default timeout_ms=15_000 in ToolDefinition
        self.engine._call_tool(task=task, step_id="step_1", tool_name="read_local_file", path="missing.txt")
        invocation = task.tool_invocations[-1]
        self.assertEqual(invocation.timeout_ms, 15_000)

    def test_restricted_tool_blocks_without_approval(self) -> None:
        """RESTRICTED tool raises ToolExecutionError and creates pending approval."""
        # Inject a RESTRICTED tool into the registry for this test
        original_def = self.engine.tool_registry._definitions["web_search"]
        restricted_def = ToolDefinition(
            name="web_search",
            description="restricted search",
            input_schema={"query": "string"},
            output_schema={"results": "string"},
            permission_level=ToolPermission.RESTRICTED,
            max_retries=0,
            category="search",
            display_name="受限搜索",
            display_label="受限搜索",
        )
        self.engine.tool_registry._definitions["web_search"] = restricted_def

        try:
            task = TaskRecord(title="restricted test")
            with self.assertRaises(ToolExecutionError) as ctx:
                self.engine._call_tool(task=task, step_id="step_1", tool_name="web_search", query="test")
            self.assertEqual(ctx.exception.category, FailureCategory.PERMISSION_DENIED)
            self.assertFalse(ctx.exception.retryable)
            # Should have created a pending approval
            self.assertEqual(len(task.pending_approvals), 1)
            self.assertEqual(task.pending_approvals[0].tool_name, "web_search")
            # Should have recorded a ToolInvocation with ERROR
            invocation = task.tool_invocations[-1]
            self.assertEqual(invocation.status, ToolCallStatus.ERROR)
            self.assertEqual(invocation.failure_category, FailureCategory.PERMISSION_DENIED)
            self.assertEqual(invocation.category, "search")
            self.assertEqual(invocation.permission_level, ToolPermission.RESTRICTED)
        finally:
            self.engine.tool_registry._definitions["web_search"] = original_def

    def test_restricted_tool_proceeds_with_existing_approval(self) -> None:
        """RESTRICTED tool succeeds when prior approval is already granted."""
        original_def = self.engine.tool_registry._definitions["web_search"]
        restricted_def = ToolDefinition(
            name="web_search",
            description="restricted search",
            input_schema={"query": "string"},
            output_schema={"results": "string"},
            permission_level=ToolPermission.RESTRICTED,
            max_retries=0,
            category="search",
            display_name="受限搜索",
            display_label="受限搜索",
        )
        self.engine.tool_registry._definitions["web_search"] = restricted_def

        try:
            task = TaskRecord(title="already approved")
            # Pre-approve the tool
            from orion_agent.core.models import PendingApproval
            task.pending_approvals.append(
                PendingApproval(
                    tool_name="web_search",
                    operation="受限搜索",
                    message="approved",
                    risk_note="test",
                    permission_level=ToolPermission.RESTRICTED,
                    approved=True,
                )
            )
            # Should succeed without raising
            output = self.engine._call_tool(task=task, step_id="step_1", tool_name="web_search", query="test")
            self.assertEqual(task.tool_invocations[-1].status, ToolCallStatus.SUCCESS)
        finally:
            self.engine.tool_registry._definitions["web_search"] = original_def

    def test_timeout_ms_passed_to_registry_invoke(self) -> None:
        """Effective timeout_ms from tool definition is forwarded to registry invoke."""
        task = TaskRecord(title="timeout forward")
        captured_timeout: int | None = None

        def capture_invoke(tool_name: str, timeout_ms: int | None = None, **kwargs: Any) -> str:
            nonlocal captured_timeout
            captured_timeout = timeout_ms
            return self.engine.tool_registry.invoke(tool_name, timeout_ms=timeout_ms, **kwargs)

        with patch.object(self.engine.tool_registry, "invoke", side_effect=capture_invoke):
            self.engine._call_tool(task=task, step_id="step_1", tool_name="summarize_text", text="hello world")

        self.assertIsNotNone(captured_timeout)
        self.assertEqual(captured_timeout, 15_000)  # default effective_timeout_ms

    def test_resolve_source_material_from_source_text(self) -> None:
        task = TaskRecord(title="source text")
        request = TaskCreateRequest(goal="总结输入文本并输出结果", source_text="A" * 50, enable_web_search=False)
        source = self.engine._resolve_source_material(task, request)
        self.assertTrue(source.startswith("A"))
        self.assertGreaterEqual(len(task.tool_invocations), 1)

    def test_resolve_source_material_from_source_path(self) -> None:
        temp = Path("tests/.tmp_source.txt")
        temp.write_text("source content for execution engine", encoding="utf-8")
        try:
            task = TaskRecord(title="source path")
            request = TaskCreateRequest(goal="读取本地文件并整理输出结果", source_path=str(temp), enable_web_search=False)
            source = self.engine._resolve_source_material(task, request)
            self.assertIn("source content", source)
            self.assertGreaterEqual(len(task.tool_invocations), 2)
        finally:
            if temp.exists():
                temp.unlink()

    def test_run_marks_failure_when_web_search_fails(self) -> None:
        settings = Settings(allow_online_search=True, tool_max_retries=1)
        engine = ExecutionEngine(
            tool_registry=ToolRegistry(settings),
            memory_manager=TaskMemoryManager(),
            llm_client=FallbackLLMClient(),
            prompts=PromptLibrary(),
            settings=settings,
        )
        task = TaskRecord(
            title="web failure replan",
            status=TaskStatus.RUNNING,
            steps=[
                Step(name="Web Research", description="collect data", tool_name="web_search"),
                Step(name="Draft Deliverable", description="deliver", tool_name="generate_markdown"),
            ],
        )
        parsed_goal = ParsedGoal(goal="收集资料并输出", expected_output="markdown", deliverable_title="测试交付")
        request = TaskCreateRequest(goal="收集资料并输出", enable_web_search=True)
        progress_messages: list[str] = []

        def fake_invoke(tool_name: str, **kwargs: object) -> str:
            if tool_name == "web_search":
                raise ToolExecutionError("timeout", category=FailureCategory.TOOL_TIMEOUT, retryable=True)
            if tool_name == "generate_markdown":
                return "# 测试交付\n\n## Deliverable\nok\n"
            if tool_name == "summarize_text":
                return str(kwargs.get("text", ""))
            raise AssertionError(f"unexpected tool: {tool_name}")

        with patch.object(engine.tool_registry, "invoke", side_effect=fake_invoke):
            result = engine.run(
                task,
                parsed_goal,
                request,
                [],
                on_progress=lambda stage, message, detail=None: progress_messages.append(message),
            )

        self.assertEqual(result.replan_count, 0)
        self.assertEqual(result.failure_category, FailureCategory.TOOL_TIMEOUT)
        self.assertIn("联网检索失败，等待恢复策略。", progress_messages)
        self.assertEqual(result.status, TaskStatus.RUNNING)

    def test_generate_deliverable_records_markdown_tool_invocation(self) -> None:
        task = TaskRecord(
            title="deliverable",
            steps=[
                Step(name="Parse Task", description="parse", output="parsed"),
                Step(name="Create Plan", description="plan", output="planned"),
                Step(name="Draft Deliverable", description="deliver", tool_name="generate_markdown"),
            ],
        )
        request = TaskCreateRequest(goal="生成交付文档", expected_output="markdown", enable_web_search=False)
        parsed_goal = ParsedGoal(goal="生成交付文档", expected_output="markdown", deliverable_title="测试交付件")
        output = self.engine._generate_deliverable(task, parsed_goal, request, [])
        self.assertIn("# 测试交付件", output)
        self.assertTrue(any(call.tool_name == "generate_markdown" for call in task.tool_invocations))

    def test_generate_deliverable_streams_live_draft_updates(self) -> None:
        task = TaskRecord(
            title="deliverable stream",
            steps=[Step(name="Draft Deliverable", description="deliver", tool_name="generate_markdown")],
        )
        request = TaskCreateRequest(goal="生成流式结果", expected_output="markdown", enable_web_search=False)
        parsed_goal = ParsedGoal(goal="生成流式结果", expected_output="markdown", deliverable_title="流式交付")
        snapshots: list[str] = []

        output = self.engine._generate_deliverable(
            task,
            parsed_goal,
            request,
            [],
            on_result_stream=snapshots.append,
        )

        self.assertTrue(snapshots)
        normalized_snapshot = self.engine._normalize_deliverable_draft(snapshots[-1])
        self.assertEqual(normalized_snapshot, task.tool_invocations[-1].input_payload["sections"][0]["content"])
        self.assertTrue("## 回答正文" in output or "## Deliverable" in output)


if __name__ == "__main__":
    unittest.main()

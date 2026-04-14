import unittest
from pathlib import Path
from unittest.mock import patch

from orion_agent.core.config import Settings
from orion_agent.core.execution_engine import ExecutionEngine
from orion_agent.core.llm_runtime import FallbackLLMClient
from orion_agent.core.memory import TaskMemoryManager
from orion_agent.core.models import FailureCategory, ParsedGoal, Step, TaskCreateRequest, TaskRecord, TaskStatus
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

    def test_run_triggers_replanning_when_web_search_fails(self) -> None:
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

        self.assertEqual(result.replan_count, 1)
        self.assertIn("联网检索失败，切换为离线执行。", progress_messages)
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
        parsed_goal = ParsedGoal(goal="生成交付文档", expected_output="markdown", deliverable_title="测试交付物")
        output = self.engine._generate_deliverable(task, parsed_goal, request, [])
        self.assertIn("# 测试交付物", output)
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
        self.assertEqual(snapshots[-1], task.tool_invocations[-1].input_payload["sections"][0]["content"])
        self.assertIn("## Deliverable", output)


if __name__ == "__main__":
    unittest.main()

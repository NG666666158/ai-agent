import unittest
from pathlib import Path
import time
from unittest.mock import Mock

from orion_agent.core.llm_runtime import FallbackLLMClient
from orion_agent.core.models import FailureCategory, TaskCreateRequest, TaskReview, TaskStatus
from orion_agent.core.repository import TaskRepository
from orion_agent.core.runtime_agent import AgentService


class AgentServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = AgentService(
            repository=TaskRepository(db_path=":memory:"),
            llm_client=FallbackLLMClient(),
        )

    def tearDown(self) -> None:
        self.service.repository.close()

    def test_create_task_completes_mvp_flow(self) -> None:
        response = self.service.create_and_run_task(
            TaskCreateRequest(
                goal="Implement AI Agent MVP",
                constraints=["Focus on project planning workflow", "Output markdown"],
                expected_output="markdown",
                source_text=(
                    "The system should support task parsing, planning, tool usage, "
                    "short-term memory, and structured result delivery."
                ),
                enable_web_search=False,
            )
        )

        self.assertEqual(response.status, TaskStatus.COMPLETED)
        self.assertGreaterEqual(len(response.steps), 5)
        self.assertIn("AI Agent MVP", response.result)
        self.assertTrue(response.review and response.review.passed)
        self.assertGreaterEqual(len(response.tool_invocations), 2)

    def test_create_task_reads_source_file(self) -> None:
        source_file = Path("AI Agent 项目规划文档.md").resolve()

        response = self.service.create_and_run_task(
            TaskCreateRequest(
                goal="Generate a deliverable from a local document",
                source_path=str(source_file),
                expected_output="markdown",
                enable_web_search=False,
            )
        )

        self.assertEqual(response.status, TaskStatus.COMPLETED)
        self.assertIn(str(source_file), response.result)
        self.assertTrue(any(call.tool_name == "read_local_file" for call in response.tool_invocations))

    def test_repository_persists_task_for_listing(self) -> None:
        created = self.service.create_and_run_task(
            TaskCreateRequest(goal="Generate project brief", expected_output="markdown", enable_web_search=False)
        )

        listed = self.service.list_tasks(limit=10)

        self.assertTrue(any(task.id == created.id for task in listed))

    def test_long_term_memory_is_written_and_recalled(self) -> None:
        self.service.create_and_run_task(
            TaskCreateRequest(
                goal="Prepare AI Agent roadmap",
                expected_output="markdown",
                enable_web_search=False,
                memory_scope="roadmap",
            )
        )

        recalled = self.service.search_memories(query="roadmap", scope="roadmap", limit=5)

        self.assertGreaterEqual(len(recalled), 1)
        self.assertIn("roadmap", recalled[0].topic.lower())

    def test_vector_memory_prefers_semantic_match(self) -> None:
        self.service.create_and_run_task(
            TaskCreateRequest(
                goal="Prepare frontend dashboard plan",
                expected_output="markdown",
                enable_web_search=False,
                memory_scope="semantic",
            )
        )
        self.service.create_and_run_task(
            TaskCreateRequest(
                goal="Document memory retrieval design",
                expected_output="markdown",
                enable_web_search=False,
                memory_scope="semantic",
            )
        )

        recalled = self.service.search_memories(query="frontend dashboard", scope="semantic", limit=1)

        self.assertEqual(len(recalled), 1)
        self.assertIn("frontend", recalled[0].topic.lower())

    def test_task_evaluation_reports_quality_score(self) -> None:
        created = self.service.create_and_run_task(
            TaskCreateRequest(
                goal="Evaluate AI Agent MVP output",
                expected_output="markdown",
                enable_web_search=False,
            )
        )

        evaluation = self.service.evaluate_task(created.id)

        self.assertIsNotNone(evaluation)
        self.assertGreaterEqual(evaluation.score, 0.8)
        self.assertTrue(any("task completed" in item for item in evaluation.checks))

    def test_create_task_async_eventually_completes(self) -> None:
        launched = self.service.create_task_async(
            TaskCreateRequest(
                goal="Stream task progress for the UI",
                expected_output="markdown",
                enable_web_search=False,
            )
        )

        self.assertIn(launched.status, {TaskStatus.CREATED, TaskStatus.PARSED, TaskStatus.PLANNED, TaskStatus.RUNNING})

        deadline = time.time() + 5
        latest = None
        while time.time() < deadline:
            latest = self.service.get_task(launched.id)
            if latest and latest.status in {TaskStatus.COMPLETED, TaskStatus.FAILED}:
                break
            time.sleep(0.05)

        self.assertIsNotNone(latest)
        self.assertEqual(latest.status, TaskStatus.COMPLETED)
        self.assertGreaterEqual(len(latest.progress_updates), 3)

    def test_review_failure_triggers_single_replan_then_completes(self) -> None:
        self.service.reflector.review = Mock(
            side_effect=[
                TaskReview(
                    passed=False,
                    summary="第一次评审发现结构不完整，需要补充。",
                    checklist=["补充结论", "补充步骤说明"],
                ),
                TaskReview(
                    passed=True,
                    summary="修订后通过评审。",
                    checklist=["通过"],
                ),
            ]
        )

        response = self.service.create_and_run_task(
            TaskCreateRequest(
                goal="生成一个需要修订后再通过的交付结果",
                expected_output="markdown",
                enable_web_search=False,
            )
        )

        self.assertEqual(response.status, TaskStatus.COMPLETED)
        self.assertEqual(response.replan_count, 1)
        self.assertEqual(response.failure_category, FailureCategory.NONE)
        self.assertTrue(any(item.stage == "replanning" for item in response.progress_updates))


if __name__ == "__main__":
    unittest.main()

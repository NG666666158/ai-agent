import unittest
from pathlib import Path

from orion_agent.core.llm_runtime import FallbackLLMClient
from orion_agent.core.models import TaskCreateRequest, TaskStatus
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


if __name__ == "__main__":
    unittest.main()

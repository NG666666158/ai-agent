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
        self.temp_files: list[Path] = []

    def tearDown(self) -> None:
        self.service.repository.close()
        for path in self.temp_files:
            if path.exists():
                path.unlink()

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

    def test_create_task_reads_source_file_requires_confirmation(self) -> None:
        source_file = Path("AI Agent 项目规划文档.md").resolve()

        response = self.service.create_and_run_task(
            TaskCreateRequest(
                goal="Generate a deliverable from a local document",
                source_path=str(source_file),
                expected_output="markdown",
                enable_web_search=False,
            )
        )

        self.assertEqual(response.status, TaskStatus.WAITING_APPROVAL)
        self.assertEqual(len(response.pending_approvals), 1)
        self.assertEqual(response.pending_approvals[0].tool_name, "read_local_file")

    def test_repository_persists_task_for_listing(self) -> None:
        created = self.service.create_and_run_task(
            TaskCreateRequest(goal="Generate project brief", expected_output="markdown", enable_web_search=False)
        )

        listed = self.service.list_tasks(limit=10)

        self.assertTrue(any(task.id == created.id for task in listed))


if __name__ == "__main__":
    unittest.main()

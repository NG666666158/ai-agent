import unittest
from pathlib import Path
from uuid import uuid4

from orion_agent.core.llm_runtime import FallbackLLMClient
from orion_agent.core.models import TaskCreateRequest, TaskStatus
from orion_agent.core.repository import TaskRepository
from orion_agent.core.runtime_agent import AgentService


class AgentServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.db_path = Path(f"test_agent_{uuid4().hex}.db").resolve()
        self.service = AgentService(
            repository=TaskRepository(db_path=str(self.db_path)),
            llm_client=FallbackLLMClient(),
        )
        self.temp_files: list[Path] = [self.db_path]

    def tearDown(self) -> None:
        self.service.repository.close()
        for path in self.temp_files:
            if path.exists():
                path.unlink()

    def test_create_task_completes_mvp_flow(self) -> None:
        response = self.service.create_and_run_task(
            TaskCreateRequest(
                goal="实现 AI Agent MVP",
                constraints=["聚焦项目规划场景", "输出 markdown"],
                expected_output="markdown",
                source_text="系统需要具备任务解析、计划生成、工具调用、短期记忆和结果输出能力。",
                enable_web_search=False,
            )
        )

        self.assertEqual(response.status, TaskStatus.COMPLETED)
        self.assertGreaterEqual(len(response.steps), 5)
        self.assertIn("AI Agent MVP", response.result)
        self.assertTrue(response.review and response.review.passed)
        self.assertGreaterEqual(len(response.tool_invocations), 2)

    def test_create_task_reads_source_file(self) -> None:
        source_file = Path(f"test_notes_{uuid4().hex}.md").resolve()
        source_file.write_text("这是一个用于验证文件读取工具的本地文档。", encoding="utf-8")
        self.temp_files.append(source_file)

        response = self.service.create_and_run_task(
            TaskCreateRequest(
                goal="基于本地文档生成交付物",
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
            TaskCreateRequest(goal="生成项目说明", expected_output="markdown", enable_web_search=False)
        )

        listed = self.service.list_tasks(limit=10)

        self.assertTrue(any(task.id == created.id for task in listed))


if __name__ == "__main__":
    unittest.main()

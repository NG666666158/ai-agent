import unittest

from tests.integration.fixture_utils import PipelineFixture


class PipelineFixtureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = PipelineFixture.build()

    def tearDown(self) -> None:
        self.fixture.close()

    # 对应 test_spec.md：验证典型“输入 -> 解析 -> 规划 -> 执行 -> 输出”的全链路流程。
    def test_fixture_runs_parse_plan_execute_end_to_end(self) -> None:
        response = self.fixture.run_request(
            goal="读取 data.txt 并总结核心观点",
            source_text="AI Agent 可以把复杂任务拆解为多个步骤，并输出结构化结果。",
            expected_output="markdown",
            enable_web_search=False,
        )
        self.fixture.assert_completed(response)
        self.assertGreaterEqual(len(response.steps), 5)
        self.fixture.assert_tool_sequence_contains(response, ["summarize_text", "generate_markdown"])

    # 对应 test_spec.md：验证工具输出在步骤之间可以连续传递，不出现上下文丢失。
    def test_fixture_propagates_tool_output_between_steps(self) -> None:
        response = self.fixture.run_request(
            goal="整理输入并输出 markdown 报告",
            source_text="第一段：需求背景。第二段：实施约束。",
            expected_output="markdown",
            enable_web_search=False,
        )
        self.fixture.assert_completed(response)
        tool_names = [item.tool_name for item in response.tool_invocations]
        self.assertIn("summarize_text", tool_names)
        self.assertIn("generate_markdown", tool_names)

    # 对应 test_spec.md：验证 parse / plan / execute 阶段的上下文信息在结果中可追踪。
    def test_fixture_preserves_context_between_parse_plan_and_execution(self) -> None:
        response = self.fixture.run_request(
            goal="整理会议纪要并输出行动项",
            constraints=["输出 markdown", "保留责任人"],
            source_text="Action: Alice draft plan. Action: Bob review API.",
            expected_output="markdown",
            enable_web_search=False,
        )
        self.fixture.assert_completed(response)
        self.assertIsNotNone(response.parsed_goal)
        self.assertGreaterEqual(len(response.progress_updates), 3)
        self.assertTrue(any(step.output for step in response.steps))


if __name__ == "__main__":
    unittest.main()

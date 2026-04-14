import json
import unittest
from pathlib import Path

from tests.integration.fixture_utils import PipelineFixture
from tests.mocks.tool_mocks import (
    mock_file_read_not_found,
    mock_file_read_success,
    mock_summarize_success,
    mock_tool_timeout,
)


class PipelineDDTTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = PipelineFixture.build()
        raw = Path("tests/fixtures/test_cases.yaml").read_text(encoding="utf-8")
        self.cases = json.loads(raw)["cases"]

    def tearDown(self) -> None:
        self.fixture.close()

    def _tool_overrides_for_case(self, mock_mode: str):
        if mock_mode == "file_read_success":
            return {"read_local_file": mock_file_read_success}
        if mock_mode == "file_read_not_found":
            return {"read_local_file": mock_file_read_not_found}
        if mock_mode == "summarize_success":
            return {"summarize_text": mock_summarize_success}
        if mock_mode == "tool_timeout":
            return {"summarize_text": mock_tool_timeout}
        return {}

    # 对应 test_spec.md：20 个业务与鲁棒性场景应转换为结构化数据并可批量执行。
    def test_scenarios_from_dataset(self) -> None:
        self.assertEqual(len(self.cases), 20)
        for case in self.cases:
            with self.subTest(case=case["id"]):
                overrides = self._tool_overrides_for_case(case.get("mock_mode", "none"))
                with self.fixture.tool_overrides(overrides):
                    response = self.fixture.run_request(
                        goal=case["goal"],
                        constraints=case.get("constraints", []),
                        source_text=case.get("source_text"),
                        expected_output=case.get("expected_output", "markdown"),
                        enable_web_search=case.get("enable_web_search", False),
                    )
                self.assertEqual(response.status.value, case["expected_status"])
                self.assertTrue(response.result)
                self.fixture.assert_tool_sequence_contains(response, case["expected_tools"])
                self.fixture.assert_result_contains_keywords(response, case["expected_output_keywords"])

    # 对应 test_spec.md：文件读取成功 Mock 应用于真实工具调用路径。
    def test_mock_file_read_success(self) -> None:
        with self.fixture.tool_overrides({"read_local_file": mock_file_read_success}):
            output = self.fixture.service.tool_registry.invoke("read_local_file", path="foo.txt")
        self.assertIn("[mocked file content]", output)

    # 对应 test_spec.md：文件不存在 Mock 应作用于真实工具调用路径。
    def test_mock_file_read_not_found(self) -> None:
        with self.fixture.tool_overrides({"read_local_file": mock_file_read_not_found}):
            with self.assertRaises(FileNotFoundError):
                self.fixture.service.tool_registry.invoke("read_local_file", path="missing.txt")

    # 对应 test_spec.md：文本总结成功 Mock 应覆盖 summarize 工具调用。
    def test_mock_summarize_success(self) -> None:
        with self.fixture.tool_overrides({"summarize_text": mock_summarize_success}):
            output = self.fixture.service.tool_registry.invoke("summarize_text", text="hello world test")
        self.assertTrue(output.startswith("summary::"))

    # 对应 test_spec.md：工具超时 Mock 应可用于鲁棒性验证。
    def test_mock_tool_timeout(self) -> None:
        with self.fixture.tool_overrides({"summarize_text": mock_tool_timeout}):
            with self.assertRaises(TimeoutError):
                self.fixture.service.tool_registry.invoke("summarize_text", text="timeout")


if __name__ == "__main__":
    unittest.main()

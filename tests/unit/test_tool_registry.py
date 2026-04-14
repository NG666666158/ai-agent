import json
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx

from orion_agent.core.config import Settings
from orion_agent.core.models import FailureCategory
from orion_agent.core.tools import ToolExecutionError, ToolRegistry


class ToolRegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = ToolRegistry(Settings())

    # 对应 test_spec.md：未知工具调用应被立即拒绝。
    def test_invoke_unknown_tool_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            self.registry.invoke("unknown_tool")

    # 对应 test_spec.md：文件读取工具在正常路径下应返回文件内容。
    def test_read_local_file_returns_content(self) -> None:
        temp = Path("tests/.tmp_tool_read.txt")
        temp.write_text("hello tool registry", encoding="utf-8")
        try:
            content = self.registry.invoke("read_local_file", path=str(temp))
            self.assertIn("hello tool registry", content)
        finally:
            if temp.exists():
                temp.unlink()

    # 对应 test_spec.md：文件不存在时，应返回带 INPUT_ERROR 分类的工具异常。
    def test_read_local_file_missing_path_raises_categorized_error(self) -> None:
        with self.assertRaises(ToolExecutionError) as context:
            self.registry.invoke("read_local_file", path="tests/not_exists_123.txt")
        self.assertEqual(context.exception.category, FailureCategory.INPUT_ERROR)
        self.assertFalse(context.exception.retryable)

    # 对应 test_spec.md：长文本摘要应触发截断逻辑。
    def test_summarize_text_truncates_long_text(self) -> None:
        text = "x" * 300
        summary = self.registry.invoke("summarize_text", text=text)
        self.assertEqual(len(summary), 180)
        self.assertTrue(summary.endswith("..."))

    # 对应 test_spec.md：关键词提取应去重并控制数量上限。
    def test_extract_keywords_deduplicates_and_limits_count(self) -> None:
        keywords = self.registry.invoke(
            "extract_keywords",
            text="python python testing automation automation framework integration reliability robust",
        )
        parts = [item.strip() for item in keywords.split(",") if item.strip()]
        self.assertLessEqual(len(parts), 8)
        self.assertEqual(len(parts), len(set(parts)))

    # 对应 test_spec.md：联网开关关闭时，web_search 应直接降级为空数组。
    def test_web_search_returns_empty_when_disabled(self) -> None:
        registry = ToolRegistry(Settings(allow_online_search=False))
        payload = registry.invoke("web_search", query="ai agent")
        self.assertEqual(json.loads(payload), [])

    # 对应 test_spec.md：请求超时时，web_search 应抛出可重试的 TOOL_TIMEOUT 异常。
    def test_web_search_raises_retryable_timeout_error(self) -> None:
        with patch("orion_agent.core.tools.httpx.get", side_effect=httpx.TimeoutException("timeout")):
            with self.assertRaises(ToolExecutionError) as context:
                self.registry.invoke("web_search", query="ai agent")
        self.assertEqual(context.exception.category, FailureCategory.TOOL_TIMEOUT)
        self.assertTrue(context.exception.retryable)

    # 对应 test_spec.md：HTTP 错误时，web_search 应抛出可重试的 NETWORK_ERROR 异常。
    def test_web_search_raises_retryable_network_error(self) -> None:
        request = httpx.Request("GET", "https://example.com")
        response = httpx.Response(500, request=request)
        with patch(
            "orion_agent.core.tools.httpx.get",
            side_effect=httpx.HTTPStatusError("boom", request=request, response=response),
        ):
            with self.assertRaises(ToolExecutionError) as context:
                self.registry.invoke("web_search", query="ai agent")
        self.assertEqual(context.exception.category, FailureCategory.NETWORK_ERROR)
        self.assertTrue(context.exception.retryable)

    # 对应 test_spec.md：Markdown 输出应保持标题与章节结构。
    def test_generate_markdown_builds_expected_structure(self) -> None:
        md = self.registry.invoke(
            "generate_markdown",
            title="测试标题",
            sections=[{"heading": "小节A", "content": "内容A"}],
        )
        self.assertIn("# 测试标题", md)
        self.assertIn("## 小节A", md)
        self.assertIn("内容A", md)


if __name__ == "__main__":
    unittest.main()

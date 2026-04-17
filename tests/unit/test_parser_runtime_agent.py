import unittest
from collections.abc import Iterator

from pydantic import ValidationError

from orion_agent.core.llm_runtime import BaseLLMClient, FallbackLLMClient
from orion_agent.core.models import TaskCreateRequest
from orion_agent.core.repository import TaskRepository
from orion_agent.core.runtime_agent import AgentService


class StubLLMClient(BaseLLMClient):
    def __init__(self, payload: dict):
        self.payload = payload

    def generate_json(self, *, system_prompt: str, user_prompt: str) -> dict:
        return self.payload

    def generate_text(self, *, system_prompt: str, user_prompt: str) -> str:
        return "ok"

    def stream_text(self, *, system_prompt: str, user_prompt: str) -> Iterator[str]:
        yield "ok"

    def health(self) -> dict[str, str]:
        return {"provider": "stub", "mode": "test", "last_error": ""}

    def probe(self) -> dict:
        return {"status": "ready"}


class ParserRuntimeAgentTests(unittest.TestCase):
    def _build_service(self, payload: dict) -> AgentService:
        return AgentService(repository=TaskRepository(db_path=":memory:"), llm_client=StubLLMClient(payload))

    # 对应 test_spec.md：Parser 正常结构化提取用户意图与参数。
    def test_parse_goal_success_with_valid_llm_json(self) -> None:
        service = self._build_service(
            {
                "goal": "整理会议纪要并输出 markdown",
                "constraints": ["中文输出"],
                "expected_output": "markdown",
                "priority": "high",
                "domain": "office",
                "deliverable_title": "会议整理结果",
            }
        )
        parsed = service._parse_goal(TaskCreateRequest(goal="整理会议纪要并输出 markdown"))
        self.assertEqual(parsed.goal, "整理会议纪要并输出 markdown")
        self.assertEqual(parsed.expected_output, "markdown")
        self.assertEqual(parsed.priority, "high")
        service.repository.close()

    # 对应 test_spec.md：Parser 返回异常结构时，应由 Pydantic 校验拦截。
    def test_parse_goal_rejects_invalid_llm_schema(self) -> None:
        service = self._build_service({"constraints": ["missing goal"]})
        with self.assertRaises(ValidationError):
            service._parse_goal(TaskCreateRequest(goal="修复构建流程并输出结果"))
        service.repository.close()

    # 对应 test_spec.md：空任务与过短任务属于边界输入，必须被请求模型拦截。
    def test_task_create_request_rejects_empty_or_short_goal(self) -> None:
        with self.assertRaises(ValidationError):
            TaskCreateRequest(goal="")
        with self.assertRaises(ValidationError):
            TaskCreateRequest(goal="abc")

    # 对应 test_spec.md：乱码或弱语义输入时，Parser 仍应返回结构化结果。
    def test_parse_goal_handles_garbled_semantic_input(self) -> None:
        service = self._build_service(
            {
                "goal": "???###@@@",
                "constraints": [],
                "expected_output": "markdown",
                "priority": "medium",
                "domain": "general",
                "deliverable_title": "异常输入处理结果",
            }
        )
        parsed = service._parse_goal(TaskCreateRequest(goal="???###@@@-----"))
        self.assertEqual(parsed.goal, "???###@@@")
        self.assertEqual(parsed.domain, "general")
        service.repository.close()

    # 对应 test_spec.md：使用 fallback 解析时，应能从请求 JSON 中提取 goal 与 constraints。
    def test_fallback_parser_extracts_goal_and_constraints_from_request_payload(self) -> None:
        service = AgentService(repository=TaskRepository(db_path=":memory:"), llm_client=FallbackLLMClient())
        parsed = service._parse_goal(
            TaskCreateRequest(
                goal="整理会议纪要并输出 Markdown",
                constraints=["中文输出", "保留行动项"],
                expected_output="markdown",
            )
        )
        self.assertEqual(parsed.goal, "整理会议纪要并输出 Markdown")
        self.assertEqual(parsed.constraints, ["中文输出", "保留行动项"])
        self.assertEqual(parsed.expected_output, "markdown")
        service.repository.close()

    # 对应 test_spec.md：无有效 JSON 载荷时，fallback Parser 应给出默认结构而不是崩溃。
    def test_fallback_parser_handles_missing_json_payload(self) -> None:
        client = FallbackLLMClient()
        payload = client.generate_json(
            system_prompt="You are an AI agent task parser.",
            user_prompt="goal: summarize a local file without any json payload",
        )
        self.assertIn("goal", payload)
        self.assertEqual(payload["expected_output"], "markdown")
        self.assertIsInstance(payload["constraints"], list)

    # 对应 test_spec.md：fallback 正文生成不能只返回空模板，至少要对简单开放问题给出可读回答。
    def test_fallback_stream_text_returns_substantive_story_answer(self) -> None:
        client = FallbackLLMClient()
        text = "".join(
            client.stream_text(
                system_prompt="You are an AI execution agent.",
                user_prompt='Goal:\n{"goal":"讲个故事啊"}',
            )
        )
        self.assertIn("## 回答内容", text)
        self.assertIn("从前", text)


if __name__ == "__main__":
    unittest.main()

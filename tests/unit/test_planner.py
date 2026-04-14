import unittest
from collections.abc import Iterator

from orion_agent.core.llm_runtime import BaseLLMClient
from orion_agent.core.models import ParsedGoal
from orion_agent.core.planner import Planner
from orion_agent.core.prompts import PromptLibrary


class PlannerLLMStub(BaseLLMClient):
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


class PlannerTests(unittest.TestCase):
    def _parsed_goal(self, goal: str = "读取并总结文件") -> ParsedGoal:
        return ParsedGoal(goal=goal, expected_output="markdown", constraints=[])

    # 对应 test_spec.md：步骤名应正确映射到工具名。
    def test_build_plan_maps_known_step_names_to_expected_tools(self) -> None:
        planner = Planner(
            PlannerLLMStub(
                {
                    "steps": [
                        {"name": "Parse Task", "description": "parse", "tool_name": None},
                        {"name": "Read Source Material", "description": "read", "tool_name": None},
                        {"name": "Web Research", "description": "web", "tool_name": None},
                        {"name": "Draft Deliverable", "description": "write", "tool_name": None},
                    ]
                }
            ),
            PromptLibrary(),
        )
        steps = planner.build_plan(self._parsed_goal(), [], source_available=True, enable_web_search=True)
        mapped = {s.name: s.tool_name for s in steps}
        self.assertEqual(mapped["Read Source Material"], "read_local_file")
        self.assertEqual(mapped["Web Research"], "web_search")
        self.assertEqual(mapped["Draft Deliverable"], "generate_markdown")

    # 对应 test_spec.md：单步任务也应能规划出可执行结果。
    def test_build_plan_supports_single_step_like_goal(self) -> None:
        planner = Planner(
            PlannerLLMStub({"steps": [{"name": "Draft Deliverable", "description": "single", "tool_name": None}]}),
            PromptLibrary(),
        )
        steps = planner.build_plan(self._parsed_goal("仅输出结果"), [], source_available=False, enable_web_search=False)
        self.assertEqual(len(steps), 1)
        self.assertEqual(steps[0].tool_name, "generate_markdown")

    # 对应 test_spec.md：步骤缺少必要字段时，应直接暴露结构问题。
    def test_build_plan_raises_on_missing_required_step_fields(self) -> None:
        planner = Planner(
            PlannerLLMStub({"steps": [{"name": "Parse Task", "tool_name": None}]}),
            PromptLibrary(),
        )
        with self.assertRaises(KeyError):
            planner.build_plan(self._parsed_goal(), [], source_available=False, enable_web_search=False)

    # 对应 test_spec.md：模糊意图下仍要返回可执行步骤列表。
    def test_build_plan_handles_ambiguous_goal_with_fallback_steps(self) -> None:
        planner = Planner(
            PlannerLLMStub(
                {
                    "steps": [
                        {"name": "Parse Task", "description": "clarify", "tool_name": None},
                        {"name": "Create Plan", "description": "plan", "tool_name": None},
                        {"name": "Review Output", "description": "review", "tool_name": None},
                    ]
                }
            ),
            PromptLibrary(),
        )
        steps = planner.build_plan(self._parsed_goal("帮我处理一个需求"), [], source_available=False, enable_web_search=False)
        self.assertEqual([s.name for s in steps], ["Parse Task", "Create Plan", "Review Output"])

    # 对应 test_spec.md：source_available 为真时，规划器应支持读取材料步骤。
    def test_build_plan_includes_source_step_only_when_source_available(self) -> None:
        planner = Planner(
            PlannerLLMStub(
                {
                    "steps": [
                        {"name": "Parse Task", "description": "parse", "tool_name": None},
                        {"name": "Read Source Material", "description": "read", "tool_name": None},
                        {"name": "Create Plan", "description": "plan", "tool_name": None},
                    ]
                }
            ),
            PromptLibrary(),
        )
        steps = planner.build_plan(self._parsed_goal(), [], source_available=True, enable_web_search=False)
        self.assertTrue(any(step.name == "Read Source Material" for step in steps))
        self.assertEqual(next(step for step in steps if step.name == "Read Source Material").tool_name, "read_local_file")

    # 对应 test_spec.md：启用联网检索时，Web 步骤应映射为 web_search 工具。
    def test_build_plan_includes_web_step_only_when_search_enabled(self) -> None:
        planner = Planner(
            PlannerLLMStub(
                {
                    "steps": [
                        {"name": "Parse Task", "description": "parse", "tool_name": None},
                        {"name": "Web Research", "description": "web", "tool_name": None},
                        {"name": "Review Output", "description": "review", "tool_name": None},
                    ]
                }
            ),
            PromptLibrary(),
        )
        steps = planner.build_plan(self._parsed_goal(), [], source_available=False, enable_web_search=True)
        web_step = next(step for step in steps if step.name == "Web Research")
        self.assertEqual(web_step.tool_name, "web_search")


if __name__ == "__main__":
    unittest.main()

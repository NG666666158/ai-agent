from __future__ import annotations

import json

from orion_agent.core.llm_runtime import BaseLLMClient
from orion_agent.core.models import LongTermMemoryRecord, ParsedGoal, Step
from orion_agent.core.prompts import PromptLibrary


class Planner:
    """Plan tasks with a prompt-driven LLM, with deterministic fallback behavior."""

    def __init__(self, llm_client: BaseLLMClient, prompts: PromptLibrary) -> None:
        self.llm_client = llm_client
        self.prompts = prompts

    def build_plan(
        self,
        parsed_goal: ParsedGoal,
        recalled_memories: list[LongTermMemoryRecord],
        source_available: bool,
        enable_web_search: bool,
    ) -> list[Step]:
        system_prompt, user_prompt = self.prompts.plan_messages(
            parsed_goal_payload=parsed_goal.model_dump_json(indent=2),
            recalled_memories_payload=json.dumps(
                [item.model_dump(mode="json") for item in recalled_memories],
                ensure_ascii=False,
            ),
            enable_web_search=enable_web_search,
            has_source=source_available,
        )
        data = self.llm_client.generate_json(system_prompt=system_prompt, user_prompt=user_prompt)
        steps_payload = data.get("steps", [])
        steps: list[Step] = []
        for item in steps_payload:
            name = item["name"]
            tool_name = item.get("tool_name")
            if name == "Draft Deliverable":
                tool_name = "generate_markdown"
            elif name == "Read Source Material":
                tool_name = "read_local_file"
            elif name == "Web Research":
                tool_name = "web_search"
            steps.append(
                Step(
                    name=name,
                    description=item["description"],
                    tool_name=tool_name,
                )
            )
        return steps

from __future__ import annotations

from orion_agent.core.llm_runtime import BaseLLMClient
from orion_agent.core.models import ParsedGoal, TaskRecord, TaskReview
from orion_agent.core.prompts import PromptLibrary


class Reflector:
    """LLM-based reviewer for the MVP deliverable."""

    def __init__(self, llm_client: BaseLLMClient, prompts: PromptLibrary) -> None:
        self.llm_client = llm_client
        self.prompts = prompts

    def review(self, task: TaskRecord, parsed_goal: ParsedGoal) -> TaskReview:
        system_prompt, user_prompt = self.prompts.review_messages(
            parsed_goal_payload=parsed_goal.model_dump_json(indent=2),
            result_payload=task.result or "",
        )
        payload = self.llm_client.generate_json(system_prompt=system_prompt, user_prompt=user_prompt)
        return TaskReview(
            passed=bool(payload.get("passed", False)),
            summary=payload.get("summary", "No review summary generated."),
            checklist=[str(item) for item in payload.get("checklist", [])],
        )

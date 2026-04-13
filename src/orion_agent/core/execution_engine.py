from __future__ import annotations

import json

from orion_agent.core.llm_runtime import BaseLLMClient
from orion_agent.core.memory import TaskMemoryManager
from orion_agent.core.models import (
    LongTermMemoryRecord,
    ParsedGoal,
    StepStatus,
    TaskCreateRequest,
    TaskRecord,
    TaskStatus,
    ToolCallStatus,
    ToolInvocation,
)
from orion_agent.core.prompts import PromptLibrary
from orion_agent.core.state_machine import transition_task
from orion_agent.core.tools import ToolRegistry


class ExecutionEngine:
    """Run plan steps, call tools, and synthesize the final deliverable."""

    def __init__(
        self,
        tool_registry: ToolRegistry,
        memory_manager: TaskMemoryManager,
        llm_client: BaseLLMClient,
        prompts: PromptLibrary,
    ) -> None:
        self.tool_registry = tool_registry
        self.memory_manager = memory_manager
        self.llm_client = llm_client
        self.prompts = prompts

    def run(
        self,
        task: TaskRecord,
        parsed_goal: ParsedGoal,
        request: TaskCreateRequest,
        recalled_memories: list[LongTermMemoryRecord],
    ) -> TaskRecord:
        source_material = self._resolve_source_material(task, request)

        for step in task.steps:
            if task.status == TaskStatus.CANCELLED:
                break

            step.status = StepStatus.DOING

            if step.name == "Parse Task":
                step.output = self._describe_goal(parsed_goal)
                self.memory_manager.write(task, "parsed_goal", step.output)
            elif step.name == "Recall Memory":
                step.output = self._format_recalled_memories(recalled_memories)
                self.memory_manager.write(task, "recalled_memories", step.output)
            elif step.tool_name == "read_local_file":
                transition_task(task, TaskStatus.WAITING_TOOL)
                step.output = source_material or "No source material was provided."
                transition_task(task, TaskStatus.RUNNING)
                self.memory_manager.write(task, "source_material", step.output)
            elif step.tool_name == "web_search":
                transition_task(task, TaskStatus.WAITING_TOOL)
                step.output = self._call_tool(
                    task=task,
                    step_id=step.id,
                    tool_name="web_search",
                    query=parsed_goal.goal,
                )
                transition_task(task, TaskStatus.RUNNING)
                self.memory_manager.write(task, "web_results", step.output)
            elif step.name == "Create Plan":
                step.output = self._summarize_plan(task, source_material)
                self.memory_manager.write(task, "execution_plan", step.output)
            elif step.tool_name == "generate_markdown":
                transition_task(task, TaskStatus.WAITING_TOOL)
                step.output = self._generate_deliverable(task, parsed_goal, request, recalled_memories)
                transition_task(task, TaskStatus.RUNNING)
            elif step.name == "Review Output":
                step.output = "Reflection checkpoint reached. Final review will be produced by the reviewer."
            else:
                step.output = "Step completed."

            step.status = StepStatus.DONE

        task.result = next(
            (step.output for step in task.steps if step.tool_name == "generate_markdown"),
            task.result,
        )
        return task

    def _resolve_source_material(self, task: TaskRecord, request: TaskCreateRequest) -> str:
        if request.source_path:
            content = self._call_tool(
                task=task,
                step_id="bootstrap",
                tool_name="read_local_file",
                path=request.source_path,
            )
            return self._call_tool(
                task=task,
                step_id="bootstrap",
                tool_name="summarize_text",
                text=content,
            )
        if request.source_text:
            return self._call_tool(
                task=task,
                step_id="bootstrap",
                tool_name="summarize_text",
                text=request.source_text,
            )
        return ""

    def _describe_goal(self, parsed_goal: ParsedGoal) -> str:
        constraints = "; ".join(parsed_goal.constraints) if parsed_goal.constraints else "No explicit constraints"
        return (
            f"Goal: {parsed_goal.goal}\n"
            f"Expected output: {parsed_goal.expected_output}\n"
            f"Priority: {parsed_goal.priority}\n"
            f"Domain: {parsed_goal.domain}\n"
            f"Constraints: {constraints}"
        )

    def _format_recalled_memories(self, recalled_memories: list[LongTermMemoryRecord]) -> str:
        if not recalled_memories:
            return "No long-term memories were recalled for this task."
        return "\n".join(f"- {item.topic}: {item.summary}" for item in recalled_memories)

    def _summarize_plan(self, task: TaskRecord, source_material: str) -> str:
        lines = []
        for step in task.steps:
            if step.status == StepStatus.DONE and step.output:
                lines.append(f"- {step.name}: {step.output}")
        if source_material:
            lines.append(f"- Source summary: {source_material}")
        return "\n".join(lines)

    def _generate_deliverable(
        self,
        task: TaskRecord,
        parsed_goal: ParsedGoal,
        request: TaskCreateRequest,
        recalled_memories: list[LongTermMemoryRecord],
    ) -> str:
        system_prompt, user_prompt = self.prompts.deliverable_messages(
            parsed_goal_payload=parsed_goal.model_dump_json(indent=2),
            step_outputs_payload=self._serialize_step_outputs(task),
            recalled_memories_payload=json.dumps(
                [item.model_dump(mode="json") for item in recalled_memories],
                ensure_ascii=False,
            ),
        )
        draft = self.llm_client.generate_text(system_prompt=system_prompt, user_prompt=user_prompt)
        sections = [
            {"heading": "Deliverable", "content": draft},
            {"heading": "Tool Invocations", "content": self._serialize_tool_invocations(task)},
        ]
        if request.source_path:
            sections.append({"heading": "Source File", "content": request.source_path})
        return self._call_tool(
            task=task,
            step_id=next(step.id for step in task.steps if step.tool_name == "generate_markdown"),
            tool_name="generate_markdown",
            title=parsed_goal.deliverable_title,
            sections=sections,
        )

    def _serialize_step_outputs(self, task: TaskRecord) -> str:
        payload = []
        for step in task.steps:
            payload.append(
                {
                    "name": step.name,
                    "description": step.description,
                    "status": step.status.value,
                    "output": step.output,
                }
            )
        return json.dumps(payload, ensure_ascii=False, indent=2)

    def _serialize_tool_invocations(self, task: TaskRecord) -> str:
        if not task.tool_invocations:
            return "- No tools were called."
        lines = []
        for item in task.tool_invocations:
            preview = item.output_preview or item.error or ""
            lines.append(f"- {item.tool_name} ({item.status.value}): {preview}")
        return "\n".join(lines)

    def _call_tool(self, task: TaskRecord, step_id: str, tool_name: str, **kwargs: str) -> str:
        try:
            output = self.tool_registry.invoke(tool_name, **kwargs)
            task.tool_invocations.append(
                ToolInvocation(
                    step_id=step_id,
                    tool_name=tool_name,
                    status=ToolCallStatus.SUCCESS,
                    input_payload=kwargs,
                    output_preview=output[:240],
                )
            )
            return output
        except Exception as exc:
            task.tool_invocations.append(
                ToolInvocation(
                    step_id=step_id,
                    tool_name=tool_name,
                    status=ToolCallStatus.ERROR,
                    input_payload=kwargs,
                    error=str(exc),
                )
            )
            return f"Tool {tool_name} failed: {exc}"

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from orion_agent.core.config import Settings
from orion_agent.core.llm_runtime import BaseLLMClient
from orion_agent.core.memory import TaskMemoryManager
from orion_agent.core.models import (
    FailureCategory,
    LongTermMemoryRecord,
    ParsedGoal,
    Step,
    StepStatus,
    TaskCreateRequest,
    TaskRecord,
    TaskStatus,
    ToolCallStatus,
    ToolInvocation,
)
from orion_agent.core.prompts import PromptLibrary
from orion_agent.core.state_machine import transition_task
from orion_agent.core.tools import ToolExecutionError, ToolRegistry


class ExecutionEngine:
    """Run plan steps, call tools, and synthesize the final deliverable."""

    def __init__(
        self,
        tool_registry: ToolRegistry,
        memory_manager: TaskMemoryManager,
        llm_client: BaseLLMClient,
        prompts: PromptLibrary,
        settings: Settings,
    ) -> None:
        self.tool_registry = tool_registry
        self.memory_manager = memory_manager
        self.llm_client = llm_client
        self.prompts = prompts
        self.settings = settings

    def run(
        self,
        task: TaskRecord,
        parsed_goal: ParsedGoal,
        request: TaskCreateRequest,
        recalled_memories: list[LongTermMemoryRecord],
        on_progress: Callable[[str, str, str | None], None] | None = None,
        on_result_stream: Callable[[str], None] | None = None,
        on_task_update: Callable[[TaskRecord], None] | None = None,
    ) -> TaskRecord:
        if on_progress is not None:
            on_progress("preparing", "正在准备执行上下文。", "整理源文本、步骤状态和工具运行环境。")

        source_material = self._resolve_source_material(task, request)
        if on_task_update is not None:
            on_task_update(task)

        for step in task.steps:
            if task.status == TaskStatus.CANCELLED:
                break

            step.status = StepStatus.DOING
            if on_task_update is not None:
                on_task_update(task)

            if on_progress is not None:
                on_progress(
                    "step_started",
                    f"正在执行步骤：{self._localize_step_name(step.name)}",
                    step.description,
                )

            if step.name == "Parse Task":
                if on_progress is not None:
                    on_progress("step_detail", "正在解析任务目标。", "提取目标、输出形式和优先级。")
                step.output = self._describe_goal(parsed_goal)
                self.memory_manager.write(task, "parsed_goal", step.output)
            elif step.name == "Recall Memory":
                if on_progress is not None:
                    on_progress("step_detail", "正在整理召回记忆。", "把历史经验转换为可参考摘要。")
                step.output = self._format_recalled_memories(recalled_memories)
                self.memory_manager.write(task, "recalled_memories", step.output)
            elif step.tool_name == "read_local_file":
                transition_task(task, TaskStatus.WAITING_TOOL)
                if on_task_update is not None:
                    on_task_update(task)
                if on_progress is not None:
                    on_progress("tool", "正在读取参考材料。", "从本地输入中提取后续执行所需内容。")
                step.output = source_material or "未提供参考材料。"
                transition_task(task, TaskStatus.RUNNING)
                self.memory_manager.write(task, "source_material", step.output)
            elif step.tool_name == "web_search":
                transition_task(task, TaskStatus.WAITING_TOOL)
                if on_task_update is not None:
                    on_task_update(task)
                if on_progress is not None:
                    on_progress("tool", "正在联网检索。", "收集与当前任务相关的外部信息。")
                step.output = self._call_tool(
                    task=task,
                    step_id=step.id,
                    tool_name="web_search",
                    query=parsed_goal.goal,
                )
                transition_task(task, TaskStatus.RUNNING)
                self.memory_manager.write(task, "web_results", step.output)
                if task.failure_category != FailureCategory.NONE:
                    self._trigger_replan(
                        task,
                        reason="联网检索失败，切换为离线执行。",
                        detail=task.failure_message,
                        on_progress=on_progress,
                        on_task_update=on_task_update,
                    )
            elif step.name == "Create Plan":
                if on_progress is not None:
                    on_progress("planning", "正在整理执行步骤。", "汇总已知信息并形成可执行方案。")
                step.output = self._summarize_plan(task, source_material)
                self.memory_manager.write(task, "execution_plan", step.output)
            elif step.tool_name == "generate_markdown":
                transition_task(task, TaskStatus.WAITING_TOOL)
                if on_task_update is not None:
                    on_task_update(task)
                step.output = self._generate_deliverable(
                    task,
                    parsed_goal,
                    request,
                    recalled_memories,
                    on_progress=on_progress,
                    on_result_stream=on_result_stream,
                )
                transition_task(task, TaskStatus.RUNNING)
            elif step.name == "Review Output":
                if on_progress is not None:
                    on_progress("review", "正在检查结果完整性。", "确认输出结构、内容覆盖和表达质量。")
                step.output = "已进入结果复核阶段，准备生成最终评估。"
            else:
                step.output = "步骤已完成。"

            if on_task_update is not None:
                on_task_update(task)

            step.status = StepStatus.DONE
            if on_task_update is not None:
                on_task_update(task)

            if on_progress is not None:
                on_progress(
                    "step_completed",
                    f"步骤已完成：{self._localize_step_name(step.name)}",
                    self._progress_detail_for_step(step),
                )

        task.result = next(
            (step.output for step in task.steps if step.tool_name == "generate_markdown"),
            task.result,
        )
        if on_task_update is not None:
            on_task_update(task)
        return task

    def revise_after_review(
        self,
        task: TaskRecord,
        parsed_goal: ParsedGoal,
        request: TaskCreateRequest,
        recalled_memories: list[LongTermMemoryRecord],
        review_summary: str,
        review_checklist: list[str],
        on_progress: Callable[[str, str, str | None], None] | None = None,
        on_result_stream: Callable[[str], None] | None = None,
        on_task_update: Callable[[TaskRecord], None] | None = None,
    ) -> TaskRecord:
        deliverable_step = next((step for step in task.steps if step.tool_name == "generate_markdown"), None)
        if deliverable_step is None:
            return task

        deliverable_step.status = StepStatus.RETRYING
        if on_task_update is not None:
            on_task_update(task)
        if on_progress is not None:
            on_progress("replanning", "正在重规划最终回答。", review_summary)

        revision_notes = "\n".join([review_summary, *review_checklist]).strip()
        deliverable_step.output = self._generate_deliverable(
            task,
            parsed_goal,
            request,
            recalled_memories,
            revision_notes=revision_notes,
            on_progress=on_progress,
            on_result_stream=on_result_stream,
        )
        deliverable_step.status = StepStatus.DONE
        task.result = deliverable_step.output
        task.failure_category = FailureCategory.NONE
        task.failure_message = None
        if on_task_update is not None:
            on_task_update(task)
        return task

    def _trigger_replan(
        self,
        task: TaskRecord,
        *,
        reason: str,
        detail: str | None,
        on_progress: Callable[[str, str, str | None], None] | None = None,
        on_task_update: Callable[[TaskRecord], None] | None = None,
    ) -> None:
        transition_task(task, TaskStatus.REPLANNING)
        task.replan_count += 1
        if on_progress is not None:
            on_progress("replanning", reason, detail)
        if on_task_update is not None:
            on_task_update(task)
        transition_task(task, TaskStatus.RUNNING)
        if on_task_update is not None:
            on_task_update(task)

    def _localize_step_name(self, step_name: str) -> str:
        mapping = {
            "Parse Task": "解析任务",
            "Recall Memory": "召回记忆",
            "Read Source Material": "读取参考材料",
            "Web Research": "联网检索",
            "Create Plan": "生成计划",
            "Draft Deliverable": "撰写结果",
            "Review Output": "结果复核",
        }
        return mapping.get(step_name, step_name)

    def _progress_detail_for_step(self, step: Step) -> str | None:
        if not step.output:
            return None
        return step.output[:180]

    def _resolve_source_material(self, task: TaskRecord, request: TaskCreateRequest) -> str:
        if request.source_path:
            content = self._call_tool(
                task=task,
                step_id="bootstrap",
                tool_name="read_local_file",
                path=request.source_path,
            )
            if task.failure_category != FailureCategory.NONE:
                return ""
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
        constraints = "; ".join(parsed_goal.constraints) if parsed_goal.constraints else "无显式约束"
        return (
            f"目标：{parsed_goal.goal}\n"
            f"期望输出：{parsed_goal.expected_output}\n"
            f"优先级：{parsed_goal.priority}\n"
            f"领域：{parsed_goal.domain}\n"
            f"约束：{constraints}"
        )

    def _format_recalled_memories(self, recalled_memories: list[LongTermMemoryRecord]) -> str:
        if not recalled_memories:
            return "当前任务未召回到长期记忆。"
        return "\n".join(f"- {item.topic}: {item.summary}" for item in recalled_memories)

    def _summarize_plan(self, task: TaskRecord, source_material: str) -> str:
        lines = []
        for step in task.steps:
            if step.status in {StepStatus.DONE, StepStatus.ERROR} and step.output:
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
        revision_notes: str | None = None,
        on_progress: Callable[[str, str, str | None], None] | None = None,
        on_result_stream: Callable[[str], None] | None = None,
    ) -> str:
        if on_progress is not None:
            on_progress("writing", "正在生成回答结构。", "先整理回答章节、重点和输出顺序。")

        system_prompt, user_prompt = self.prompts.deliverable_messages(
            parsed_goal_payload=parsed_goal.model_dump_json(indent=2),
            step_outputs_payload=self._serialize_step_outputs(task),
            recalled_memories_payload=json.dumps(
                [item.model_dump(mode="json") for item in recalled_memories],
                ensure_ascii=False,
            ),
        )
        if revision_notes:
            user_prompt = f"{user_prompt}\n\nRevision notes:\n{revision_notes}"

        if on_progress is not None:
            on_progress("writing", "正在撰写回答正文。", "系统会持续流式输出回答内容。")

        draft = self._stream_deliverable_draft(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            on_result_stream=on_result_stream,
        )

        if on_progress is not None:
            on_progress("writing", "正在整理 Markdown 结构。", "补充标题、工具调用摘要和来源信息。")

        sections = [
            {"heading": "Deliverable", "content": draft},
            {"heading": "Tool Invocations", "content": self._serialize_tool_invocations(task)},
        ]
        if request.source_path:
            sections.append({"heading": "Source File", "content": request.source_path})

        result = self._call_tool(
            task=task,
            step_id=next(step.id for step in task.steps if step.tool_name == "generate_markdown"),
            tool_name="generate_markdown",
            title=parsed_goal.deliverable_title,
            sections=sections,
        )

        if on_progress is not None:
            on_progress("writing", "回答结构整理完成。", "最终结果已经封装为 Markdown 输出。")
        return result

    def _stream_deliverable_draft(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        on_result_stream: Callable[[str], None] | None = None,
    ) -> str:
        chunks: list[str] = []
        pending = ""

        for chunk in self.llm_client.stream_text(system_prompt=system_prompt, user_prompt=user_prompt):
            if not chunk:
                continue
            chunks.append(chunk)
            pending += chunk
            if on_result_stream is not None and self._should_flush_stream_buffer(pending):
                on_result_stream("".join(chunks))
                pending = ""

        final_text = "".join(chunks).strip()
        if on_result_stream is not None:
            on_result_stream(final_text)
        return final_text

    def _should_flush_stream_buffer(self, buffer_text: str) -> bool:
        if len(buffer_text) >= 24:
            return True
        return buffer_text.endswith(("\n", "。", "，", "！", "？", ".", "!", "?", ";"))

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
            lines.append(
                f"- {item.tool_name} ({item.status.value}, attempt {item.attempt_count}, category {item.failure_category.value}): {preview}"
            )
        return "\n".join(lines)

    def _call_tool(self, task: TaskRecord, step_id: str, tool_name: str, **kwargs: Any) -> str:
        definition = self.tool_registry.get_definition(tool_name)
        attempts_allowed = 1 + max(
            definition.max_retries,
            self.settings.tool_max_retries if definition.max_retries > 0 else 0,
        )
        last_error = ""
        last_category = FailureCategory.INTERNAL_ERROR

        for attempt in range(1, attempts_allowed + 1):
            try:
                output = self.tool_registry.invoke(tool_name, **kwargs)
                task.tool_invocations.append(
                    ToolInvocation(
                        step_id=step_id,
                        tool_name=tool_name,
                        status=ToolCallStatus.SUCCESS,
                        input_payload=kwargs,
                        output_preview=output[:240],
                        attempt_count=attempt,
                    )
                )
                task.failure_category = FailureCategory.NONE
                task.failure_message = None
                return output
            except ToolExecutionError as exc:
                last_error = str(exc)
                last_category = exc.category
                task.tool_invocations.append(
                    ToolInvocation(
                        step_id=step_id,
                        tool_name=tool_name,
                        status=ToolCallStatus.ERROR,
                        input_payload=kwargs,
                        error=last_error,
                        failure_category=last_category,
                        attempt_count=attempt,
                    )
                )
                if exc.retryable and attempt < attempts_allowed:
                    task.retry_count += 1
                    continue
                break
            except Exception as exc:
                last_error = str(exc)
                last_category = FailureCategory.INTERNAL_ERROR
                task.tool_invocations.append(
                    ToolInvocation(
                        step_id=step_id,
                        tool_name=tool_name,
                        status=ToolCallStatus.ERROR,
                        input_payload=kwargs,
                        error=last_error,
                        failure_category=last_category,
                        attempt_count=attempt,
                    )
                )
                break

        task.failure_category = last_category
        task.failure_message = last_error
        return f"Tool {tool_name} failed [{last_category.value}]: {last_error}"

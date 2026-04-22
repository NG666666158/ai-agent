from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from orion_agent.core.config import Settings
from orion_agent.core.llm_runtime import BaseLLMClient
from orion_agent.core.memory import TaskMemoryManager
from orion_agent.core.models import (
    ApprovalStatus,
    EnforcementResult,
    FailureCategory,
    LongTermMemoryRecord,
    ParsedGoal,
    PendingApproval,
    Step,
    StepStatus,
    TaskCreateRequest,
    TaskRecord,
    TaskStatus,
    ToolCallStatus,
    ToolInvocation,
    ToolPermission,
)
from orion_agent.core.prompts import PromptLibrary
from orion_agent.core.state_machine import transition_task
from orion_agent.core.tools import ToolExecutionError, ToolRegistry


def _step_memory_kind(step: Step) -> str | None:
    """Return the memory kind for a completed step's raw output, or None if not applicable."""
    if step.name == "Parse Task":
        return "parsed_goal"
    if step.name == "Recall Memory":
        return "recalled_memories"
    if step.tool_name == "read_local_file":
        return "source_material"
    if step.tool_name == "web_search":
        return "web_results"
    if step.name == "Create Plan":
        return "execution_plan"
    return None


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
            on_progress("preparing", "正在准备执行上下文。", "整理源材料、步骤状态和工具运行环境。")

        try:
            source_material = self._resolve_source_material(task, request)
        except ToolExecutionError as exc:
            self._apply_tool_exception(task, exc, on_progress=on_progress)
            if on_task_update is not None:
                on_task_update(task)
            return task

        task.context_layers.source_summary = source_material or task.context_layers.source_summary
        if on_task_update is not None:
            on_task_update(task)

        for step in task.steps:
            if task.status == TaskStatus.CANCELLED:
                break
            if step.status in {StepStatus.DONE, StepStatus.SKIPPED}:
                continue

            task.checkpoint.current_step_id = step.id
            task.checkpoint.current_stage = f"step:{step.name}"
            step.status = StepStatus.DOING
            if on_task_update is not None:
                on_task_update(task)

            if on_progress is not None:
                on_progress("step_started", f"正在执行步骤：{self._localize_step_name(step.name, step.tool_name)}", step.description)

            try:
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
                    if task.status != TaskStatus.WAITING_APPROVAL:
                        transition_task(task, TaskStatus.RUNNING)
                    self.memory_manager.write(task, "source_material", step.output)
                elif step.tool_name == "web_search":
                    transition_task(task, TaskStatus.WAITING_TOOL)
                    if on_task_update is not None:
                        on_task_update(task)
                    if on_progress is not None:
                        on_progress("tool", "正在联网检索。", "收集与当前任务相关的外部信息。")
                    step.output = self._call_tool(task=task, step_id=step.id, tool_name="web_search", query=parsed_goal.goal)
                    if task.status != TaskStatus.WAITING_APPROVAL:
                        transition_task(task, TaskStatus.RUNNING)
                    self.memory_manager.write(task, "web_results", step.output)
                    if task.failure_category != FailureCategory.NONE and on_progress is not None:
                        on_progress("tool_failed", "联网检索失败，等待恢复策略。", task.failure_message)
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
                    if task.status != TaskStatus.WAITING_APPROVAL:
                        transition_task(task, TaskStatus.RUNNING)
                elif step.name == "Review Output":
                    if on_progress is not None:
                        on_progress("review", "正在检查结果完整性。", "确认输出结构、内容覆盖和表达质量。")
                    step.output = "已进入结果复核阶段，准备生成最终评估。"
                else:
                    step.output = "步骤已完成。"
            except ToolExecutionError as exc:
                self._apply_tool_exception(task, exc, on_progress=on_progress)
                step.output = str(exc)

            if task.failure_category != FailureCategory.NONE and step.status == StepStatus.DOING:
                step.status = StepStatus.ERROR
            else:
                step.status = StepStatus.DONE
                task.checkpoint.last_completed_step_id = step.id
                task.checkpoint.last_completed_step_name = step.name
                # US-R21: write compact summary, mark raw intermediate as discardable
                self._summarize_step(task, step)

            if on_task_update is not None:
                on_task_update(task)

            if on_progress is not None:
                on_progress(
                    "step_completed",
                    f"步骤已完成：{self._localize_step_name(step.name, step.tool_name)}",
                    self._progress_detail_for_step(step),
                )

            if task.failure_category != FailureCategory.NONE:
                break

        task.result = next((step.output for step in task.steps if step.tool_name == "generate_markdown"), task.result)
        task.checkpoint.current_step_id = None
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
        task.checkpoint.current_step_id = deliverable_step.id
        task.checkpoint.current_stage = "replanning:generate_markdown"
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

    def _localize_step_name(self, step_name: str, tool_name: str | None = None) -> str:
        if tool_name:
            try:
                definition = self.tool_registry.get_definition(tool_name)
                if definition.display_label:
                    return definition.display_label
            except ValueError:
                pass
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
            content = self._call_tool(task=task, step_id="bootstrap", tool_name="read_local_file", path=request.source_path)
            if task.failure_category != FailureCategory.NONE:
                return ""
            return self._call_tool(task=task, step_id="bootstrap", tool_name="summarize_text", text=content)
        if request.source_text:
            return self._call_tool(task=task, step_id="bootstrap", tool_name="summarize_text", text=request.source_text)
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
            if step.status in {StepStatus.DONE, StepStatus.ERROR, StepStatus.SKIPPED} and step.output:
                lines.append(f"- {step.name}: {step.output}")
        if source_material:
            lines.append(f"- Source summary: {source_material}")
        return "\n".join(lines)

    def _summarize_step(self, task: TaskRecord, step: Step) -> None:
        """US-R21: write compact summary for a completed step, mark raw output as discardable.

        After a step completes, its raw output can be large (tool results, web search,
        source material). Instead of keeping the full text in working memory, we write
        a compact summary and mark the raw entry as discardable so the context builder
        can omit it.
        """
        # Find raw entries for this step's output kind and mark them discardable
        kind = _step_memory_kind(step)
        if kind is None:
            return

        # Mark existing raw entries for this step as discardable
        for entry in task.memory:
            if entry.kind == kind and not entry.discardable:
                entry.discardable = True

        # Write a compact summary entry
        summary_content = f"[{step.name}] {step.output[:120] if step.output else '(no output)'}"
        self.memory_manager.write(task, f"{kind}_summary", summary_content)

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
            recalled_memories_payload=json.dumps([item.model_dump(mode="json") for item in recalled_memories], ensure_ascii=False),
            session_context=self._serialize_context_layers(task),
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
        draft = self._normalize_deliverable_draft(draft, title=parsed_goal.deliverable_title)

        if on_progress is not None:
            on_progress("writing", "正在整理 Markdown 结构。", "补充标题、工具调用摘要和来源信息。")

        result = self._compose_deliverable_markdown(
            task=task,
            title=parsed_goal.deliverable_title,
            draft=draft,
            source_path=request.source_path,
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
        if len(buffer_text) >= 32:
            return True
        return buffer_text.endswith(("\n", "。", "！", "？", "；", ".", "!", "?", ";"))

    def _normalize_deliverable_draft(self, draft: str, *, title: str | None = None) -> str:
        normalized = draft.replace("\r\n", "\n").strip()
        if not normalized:
            return normalized

        lines = normalized.split("\n")
        while lines and not lines[0].strip():
            lines.pop(0)

        if lines and lines[0].startswith("# "):
            lines.pop(0)
            while lines and not lines[0].strip():
                lines.pop(0)

        if lines and lines[0].strip() in {"## 回答正文", "## Deliverable"}:
            lines.pop(0)
            while lines and not lines[0].strip():
                lines.pop(0)

        if title and lines and lines[0].strip() in {f"# {title}", f"## {title}"}:
            lines.pop(0)
            while lines and not lines[0].strip():
                lines.pop(0)

        cleaned = "\n".join(lines).strip()
        for marker in ("\n## 工具调用", "\n## Tool Invocations", "\n## 来源文件", "\n## Source"):
            if marker in cleaned:
                cleaned = cleaned.split(marker, 1)[0].rstrip()

        return cleaned

    def _compose_deliverable_markdown(
        self,
        *,
        task: TaskRecord,
        title: str,
        draft: str,
        source_path: str | None,
    ) -> str:
        step_id = next(step.id for step in task.steps if step.tool_name == "generate_markdown")
        return self._call_tool(
            task=task,
            step_id=step_id,
            tool_name="generate_markdown",
            title="",
            sections=[{"heading": "", "content": draft}],
        )
        sections = [
            {"heading": "回答正文", "content": draft},
            {"heading": "工具调用", "content": self._serialize_tool_invocations(task)},
        ]
        if source_path:
            sections.append({"heading": "来源文件", "content": source_path})

        return self._call_tool(
            task=task,
            step_id=step_id,
            tool_name="generate_markdown",
            title=title,
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
            return "- 本轮对话未调用外部工具。"
        lines = []
        for item in task.tool_invocations:
            tool_label = item.display_name or item.display_label or item.tool_name
            if item.tool_name == "generate_markdown" and item.status == ToolCallStatus.SUCCESS:
                preview = "已生成最终 Markdown 结果。"
            else:
                preview = item.output_preview or item.error or ""
            lines.append(
                f"- {item.tool_name} ({item.status.value}, attempt {item.attempt_count}, category {item.failure_category.value}): {preview}"
            )
        return "\n".join(lines)

    def _serialize_context_layers(self, task: TaskRecord) -> str:
        context = task.context_layers
        payload = {
            "session_summary": context.session_summary,
            "recent_messages": context.recent_messages,
            "condensed_recent_messages": context.condensed_recent_messages,
            "recalled_memories": context.recalled_memories,
            "profile_facts": context.profile_facts,
            "working_memory": context.working_memory,
            "source_summary": context.source_summary,
            "build_notes": context.build_notes,
        }
        return json.dumps(payload, ensure_ascii=False, indent=2)

    def _call_tool(self, task: TaskRecord, step_id: str, tool_name: str, **kwargs: Any) -> str:
        definition = self.tool_registry.get_definition(tool_name)

        if definition.permission_level == ToolPermission.RESTRICTED:
            has_granted_approval = any(
                approval.tool_name == tool_name and approval.approved is True
                for approval in task.pending_approvals
            )
            has_open_approval = any(
                approval.tool_name == tool_name and approval.approved is None
                for approval in task.pending_approvals
            )
            if not has_granted_approval:
                task.tool_invocations.append(
                    ToolInvocation(
                        step_id=step_id,
                        tool_name=tool_name,
                        status=ToolCallStatus.ERROR,
                        input_payload=kwargs,
                        error=f"Tool {tool_name} requires user approval.",
                        failure_category=FailureCategory.PERMISSION_DENIED,
                        category=definition.category,
                        display_name=definition.display_name,
                        display_label=definition.display_label,
                        permission_level=definition.permission_level,
                        timeout_ms=definition.effective_timeout_ms,
                        approval_required=True,
                        # This blocked call always leaves the task waiting on user input:
                        # either an approval is already open, or we create one below.
                        approval_status=ApprovalStatus.PENDING,
                        enforcement_result=EnforcementResult.BLOCKED,
                    )
                )
                if not has_open_approval:
                    task.pending_approvals.append(
                        PendingApproval(
                            tool_name=tool_name,
                            operation=definition.display_name or tool_name,
                            message=f"操作「{definition.display_name or tool_name}」需要确认。",
                            risk_note=definition.description,
                            permission_level=ToolPermission.RESTRICTED,
                            input_payload=kwargs,
                        )
                    )
                raise ToolExecutionError(
                    f"Tool {tool_name} requires user approval.",
                    category=FailureCategory.PERMISSION_DENIED,
                    retryable=False,
                )

        attempts_allowed = 1 + max(
            definition.max_retries,
            self.settings.tool_max_retries if definition.max_retries > 0 else 0,
        )
        timeout_ms = definition.effective_timeout_ms
        last_error = ""
        last_category = FailureCategory.INTERNAL_ERROR

        def _make_invocation(
            status: ToolCallStatus,
            *,
            error: str | None = None,
            attempt: int = 1,
            output_preview: str | None = None,
            failure_category: FailureCategory,
        ) -> ToolInvocation:
            # Determine permission context based on tool's permission level.
            # SAFE: no approval required.
            # CONFIRM: approval required but treated as granted (implicit confirmation).
            # RESTRICTED: approval required and was explicitly granted to reach this point.
            is_approval_required = definition.permission_level != ToolPermission.SAFE
            approval_status: ApprovalStatus | None = (
                ApprovalStatus.APPROVED if is_approval_required else ApprovalStatus.NOT_REQUIRED
            )
            return ToolInvocation(
                step_id=step_id,
                tool_name=tool_name,
                status=status,
                input_payload=kwargs,
                output_preview=output_preview,
                error=error,
                failure_category=failure_category,
                attempt_count=attempt,
                category=definition.category,
                display_name=definition.display_name,
                display_label=definition.display_label,
                permission_level=definition.permission_level,
                timeout_ms=timeout_ms,
                approval_required=is_approval_required,
                approval_status=approval_status,
                enforcement_result=EnforcementResult.ALLOWED,
            )

        for attempt in range(1, attempts_allowed + 1):
            try:
                output = self.tool_registry.invoke(tool_name, timeout_ms=timeout_ms, **kwargs)
                task.tool_invocations.append(
                    _make_invocation(
                        ToolCallStatus.SUCCESS,
                        attempt=attempt,
                        output_preview=output[:240],
                        failure_category=FailureCategory.NONE,
                    )
                )
                task.failure_category = FailureCategory.NONE
                task.failure_message = None
                return output
            except ToolExecutionError as exc:
                last_error = str(exc)
                last_category = exc.category
                task.tool_invocations.append(
                    _make_invocation(
                        ToolCallStatus.ERROR,
                        error=last_error,
                        attempt=attempt,
                        failure_category=last_category,
                    )
                )
                if exc.retryable and attempt < attempts_allowed:
                    task.retry_count += 1
                    continue
                if exc.category == FailureCategory.PERMISSION_DENIED:
                    raise
                break
            except Exception as exc:
                last_error = str(exc)
                last_category = FailureCategory.INTERNAL_ERROR
                task.tool_invocations.append(
                    _make_invocation(
                        ToolCallStatus.ERROR,
                        error=last_error,
                        attempt=attempt,
                        failure_category=last_category,
                    )
                )
                break

        task.failure_category = last_category
        task.failure_message = last_error
        return f"Tool {tool_name} failed [{last_category.value}]: {last_error}"

    def _apply_tool_exception(
        self,
        task: TaskRecord,
        exc: ToolExecutionError,
        *,
        on_progress: Callable[[str, str, str | None], None] | None = None,
    ) -> None:
        task.failure_category = exc.category
        task.failure_message = str(exc)

        if exc.category == FailureCategory.PERMISSION_DENIED:
            transition_task(task, TaskStatus.WAITING_APPROVAL)
            if on_progress is not None:
                latest_pending = next(
                    (item for item in reversed(task.pending_approvals) if item.approved is None),
                    None,
                )
                on_progress(
                    "approval",
                    "等待用户确认高风险操作。",
                    latest_pending.message if latest_pending is not None else str(exc),
                )

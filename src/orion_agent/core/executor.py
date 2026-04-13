from __future__ import annotations

from pathlib import Path

from orion_agent.core.memory import TaskMemoryManager
from orion_agent.core.models import (
    ParsedGoal,
    StepStatus,
    TaskCreateRequest,
    TaskRecord,
    TaskStatus,
    ToolCallStatus,
    ToolInvocation,
)
from orion_agent.core.state_machine import transition_task
from orion_agent.core.tools import ToolRegistry


class Executor:
    """Run plan steps sequentially and produce a deliverable."""

    def __init__(self, tool_registry: ToolRegistry, memory_manager: TaskMemoryManager) -> None:
        self.tool_registry = tool_registry
        self.memory_manager = memory_manager

    def run(self, task: TaskRecord, parsed_goal: ParsedGoal, request: TaskCreateRequest) -> TaskRecord:
        source_content = self._resolve_source_content(task, request)

        for step in task.steps:
            if task.status == TaskStatus.CANCELLED:
                break

            step.status = StepStatus.DOING

            if step.name == "解析任务":
                step.output = self._describe_goal(parsed_goal)
                self.memory_manager.write(task, "parsed_goal", step.output)
            elif step.name == "检索短期记忆":
                matches = self.memory_manager.search(task, parsed_goal.goal.split()[0], limit=3)
                if matches:
                    step.output = "\n".join(f"- {entry.content}" for entry in matches)
                else:
                    step.output = "当前没有可复用的历史结论，按新任务继续推进。"
            elif step.name == "读取参考材料":
                transition_task(task, TaskStatus.WAITING_TOOL)
                step.output = source_content or "未提供参考材料。"
                transition_task(task, TaskStatus.RUNNING)
                self.memory_manager.write(task, "source_summary", step.output)
            elif step.name == "生成执行计划":
                keywords = self._call_tool(
                    task=task,
                    step_id=step.id,
                    tool_name="extract_keywords",
                    text=f"{parsed_goal.goal}\n{source_content}",
                )
                step.output = (
                    "阶段一：任务解析与数据建模；\n"
                    "阶段二：Planner、Executor、Tool Registry 闭环；\n"
                    "阶段三：状态展示、短期记忆、结果复核；\n"
                    f"当前提炼关键词：{keywords or '无'}。"
                )
                self.memory_manager.write(task, "execution_plan", step.output)
            elif step.name == "生成交付结果":
                transition_task(task, TaskStatus.WAITING_TOOL)
                step.output = self._build_deliverable(task, parsed_goal, request)
                transition_task(task, TaskStatus.RUNNING)
            elif step.name == "结果复核":
                step.output = "已完成基础结果检查，等待 Reflector 输出最终审核结论。"
            else:
                step.output = "步骤已执行。"

            step.status = StepStatus.DONE

        task.result = next(
            (step.output for step in task.steps if step.name == "生成交付结果"),
            task.result,
        )
        return task

    def _resolve_source_content(self, task: TaskRecord, request: TaskCreateRequest) -> str:
        if request.source_path:
            transition_task(task, TaskStatus.WAITING_TOOL)
            content = self._call_tool(
                task=task,
                step_id="bootstrap",
                tool_name="read_local_file",
                path=request.source_path,
            )
            transition_task(task, TaskStatus.RUNNING)
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
        constraints = "；".join(parsed_goal.constraints) if parsed_goal.constraints else "无额外约束"
        return (
            f"目标：{parsed_goal.goal}。\n"
            f"输出：{parsed_goal.expected_output}。\n"
            f"优先级：{parsed_goal.priority}。\n"
            f"约束：{constraints}。"
        )

    def _build_deliverable(
        self,
        task: TaskRecord,
        parsed_goal: ParsedGoal,
        request: TaskCreateRequest,
    ) -> str:
        plan_step = next(step for step in task.steps if step.name == "生成执行计划")
        source_step = next((step for step in task.steps if step.name == "读取参考材料"), None)
        sections = [
            {"heading": "任务目标", "content": parsed_goal.goal},
            {
                "heading": "关键约束",
                "content": "\n".join(f"- {item}" for item in parsed_goal.constraints) or "- 无",
            },
            {"heading": "执行计划", "content": plan_step.output or "待补充"},
            {
                "heading": "已实现能力",
                "content": (
                    "- 任务解析\n"
                    "- 步骤规划\n"
                    "- 工具注册与调用日志\n"
                    "- 短期记忆\n"
                    "- Markdown 结果输出\n"
                    "- 任务状态追踪"
                ),
            },
            {
                "heading": "后续迭代建议",
                "content": (
                    "1. 接入真实 LLM。\n"
                    "2. 接入 Web 搜索工具。\n"
                    "3. 引入长期记忆与向量检索。\n"
                    "4. 增加前端任务时间线与结果预览。"
                ),
            },
        ]
        if source_step and source_step.output:
            sections.append({"heading": "参考材料摘要", "content": source_step.output})
        if request.source_path:
            sections.append({"heading": "来源文件", "content": str(Path(request.source_path))})

        return self._call_tool(
            task=task,
            step_id=next(step.id for step in task.steps if step.name == "生成交付结果"),
            tool_name="generate_markdown",
            title=parsed_goal.deliverable_title,
            sections=sections,
        )

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
        except Exception as exc:  # pragma: no cover - defensive branch
            task.tool_invocations.append(
                ToolInvocation(
                    step_id=step_id,
                    tool_name=tool_name,
                    status=ToolCallStatus.ERROR,
                    input_payload=kwargs,
                    error=str(exc),
                )
            )
            raise

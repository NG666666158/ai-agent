from __future__ import annotations

from orion_agent.core.executor import Executor
from orion_agent.core.memory import TaskMemoryManager
from orion_agent.core.models import ParsedGoal, TaskCreateRequest, TaskRecord, TaskResponse, TaskStatus
from orion_agent.core.planner import Planner
from orion_agent.core.reflection import Reflector
from orion_agent.core.repository import TaskRepository
from orion_agent.core.state_machine import transition_task
from orion_agent.core.tools import ToolRegistry


class AgentService:
    """Orchestrates parsing, planning, execution, and reflection."""

    def __init__(self, repository: TaskRepository | None = None) -> None:
        self.repository = repository or TaskRepository()
        self.memory_manager = TaskMemoryManager()
        self.tool_registry = ToolRegistry()
        self.planner = Planner()
        self.executor = Executor(self.tool_registry, self.memory_manager)
        self.reflector = Reflector()

    def create_and_run_task(self, request: TaskCreateRequest) -> TaskResponse:
        task = TaskRecord(title=request.goal, metadata=request.metadata)
        self.repository.save(task)

        task.parsed_goal = self._parse_goal(request)
        self.memory_manager.write(task, "user_goal", request.goal)
        transition_task(task, TaskStatus.PARSED)
        self.repository.save(task)

        task.steps = self.planner.build_plan(
            parsed_goal=task.parsed_goal,
            source_available=bool(request.source_text or request.source_path),
        )
        transition_task(task, TaskStatus.PLANNED)
        self.repository.save(task)

        transition_task(task, TaskStatus.RUNNING)
        task = self.executor.run(task, task.parsed_goal, request)
        self.repository.save(task)

        transition_task(task, TaskStatus.REFLECTING)
        task.review = self.reflector.review(task, task.parsed_goal)
        transition_task(task, TaskStatus.COMPLETED if task.review.passed else TaskStatus.FAILED)
        self.repository.save(task)
        return TaskResponse.from_record(task)

    def get_task(self, task_id: str) -> TaskResponse | None:
        task = self.repository.get(task_id)
        if task is None:
            return None
        return TaskResponse.from_record(task)

    def list_tasks(self, limit: int = 20) -> list[TaskResponse]:
        return [TaskResponse.from_record(task) for task in self.repository.list(limit=limit)]

    def cancel_task(self, task_id: str) -> TaskResponse | None:
        task = self.repository.get(task_id)
        if task is None:
            return None
        if task.status not in {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED}:
            transition_task(task, TaskStatus.CANCELLED)
            self.repository.save(task)
        return TaskResponse.from_record(task)

    def list_tools(self):
        return self.tool_registry.list_definitions()

    def _parse_goal(self, request: TaskCreateRequest) -> ParsedGoal:
        domain = "general"
        lowered_goal = request.goal.lower()

        if "研究" in request.goal or "paper" in lowered_goal:
            domain = "research"
        elif "文档" in request.goal or "规划" in request.goal:
            domain = "documentation"
        elif "开发" in request.goal or "mvp" in lowered_goal:
            domain = "software_project"

        priority = "high" if request.constraints else "medium"
        deliverable_title = "AI Agent MVP 交付结果" if domain == "software_project" else "Agent 执行结果"
        return ParsedGoal(
            goal=request.goal,
            constraints=request.constraints,
            expected_output=request.expected_output,
            priority=priority,
            domain=domain,
            deliverable_title=deliverable_title,
        )
